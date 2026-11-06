"""GitopsRepo against a local repository (no network)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from access_node_compose_api.gitops import GitError, GitopsRepo

CHART = "ionos_sbx/marketplace/access-node"
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    (origin / CHART).mkdir(parents=True)
    (origin / CHART / "Chart.yaml").write_text("apiVersion: v2\nname: access-node\n")
    (origin / "ionos_prd" / "other").mkdir(parents=True)
    (origin / "ionos_prd" / "other" / "file.yaml").write_text("x: 1\n")
    git(origin, "init", "--initial-branch=main")
    git(origin, "add", ".")
    git(origin, "commit", "-m", "init")
    return origin


@pytest.fixture
def repo(origin: Path, tmp_path: Path) -> GitopsRepo:
    return GitopsRepo(
        repo_url=origin.as_uri(), branch="main", chart_path=CHART, clone_dir=tmp_path / "clone"
    )


def test_clone_is_sparse(repo, origin, tmp_path):
    commit = repo.sync()
    assert commit == git(origin, "rev-parse", "HEAD")
    assert (repo.chart_dir / "Chart.yaml").is_file()
    assert not (tmp_path / "clone" / "ionos_prd").exists()


def test_tree_hash_changes_only_when_chart_changes(repo, origin):
    repo.sync()
    first = repo.tree_hash()

    (origin / "ionos_prd" / "other" / "file.yaml").write_text("x: 2\n")
    git(origin, "commit", "-am", "unrelated")
    repo.sync()
    assert repo.tree_hash() == first

    (origin / CHART / "values.yaml").write_text("a: 1\n")
    git(origin, "add", ".")
    git(origin, "commit", "-m", "chart change")
    commit = repo.sync()
    assert commit == git(origin, "rev-parse", "HEAD")
    assert repo.tree_hash() != first
    assert (repo.chart_dir / "values.yaml").is_file()


def test_local_changes_are_discarded(repo):
    repo.sync()
    (repo.chart_dir / "Chart.yaml").write_text("dirty")
    (repo.chart_dir / "untracked.txt").write_text("x")
    repo.sync()
    assert (repo.chart_dir / "Chart.yaml").read_text().startswith("apiVersion")
    assert not (repo.chart_dir / "untracked.txt").exists()


def test_broken_clone_is_recreated(repo, tmp_path):
    repo.sync()
    shutil.rmtree(tmp_path / "clone" / ".git" / "objects")
    (tmp_path / "clone" / ".git" / "objects").mkdir()
    repo.sync()
    assert (repo.chart_dir / "Chart.yaml").is_file()


def test_missing_chart_path_raises(origin, tmp_path):
    repo = GitopsRepo(
        repo_url=origin.as_uri(),
        branch="main",
        chart_path="ionos_xxx/marketplace/access-node",
        clone_dir=tmp_path / "clone",
    )
    repo.sync()
    with pytest.raises(GitError, match="not found"):
        repo.tree_hash()


def test_unreachable_repo_raises(tmp_path):
    repo = GitopsRepo(
        repo_url=(tmp_path / "nope").as_uri(),
        branch="main",
        chart_path=CHART,
        clone_dir=tmp_path / "clone",
    )
    with pytest.raises(GitError, match="clone failed"):
        repo.sync()
