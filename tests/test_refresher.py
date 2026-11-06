from pathlib import Path

import pytest

from access_node_compose_api.gitops import GitError
from access_node_compose_api.refresher import STARTUP_RETRY_SECONDS, Refresher
from access_node_compose_api.render import RenderError
from access_node_compose_api.state import State

from .conftest import COMMIT, NOW, make_deployment


class FakeRepo:
    def __init__(self) -> None:
        self.commit = COMMIT
        self.tree = "tree-1"
        self.sync_error: Exception | None = None

    @property
    def chart_dir(self) -> Path:
        return Path("/nonexistent")

    def sync(self) -> str:
        if self.sync_error:
            raise self.sync_error
        return self.commit

    def tree_hash(self) -> str:
        return self.tree


class FakeRenderer:
    def __init__(self, output: str) -> None:
        self.output = output
        self.error: Exception | None = None
        self.calls = 0

    def cleanup_stale(self) -> None:
        pass

    def render(self, chart_dir: Path) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.output


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def renderer(sbx_manifest) -> FakeRenderer:
    return FakeRenderer(sbx_manifest)


@pytest.fixture
def state() -> State:
    return State()


@pytest.fixture
def refresher(make_settings, state, repo, renderer) -> Refresher:
    return Refresher(
        settings=make_settings(), state=state, repo=repo, renderer=renderer, clock=lambda: NOW
    )


def test_first_refresh_publishes_snapshot(refresher, state):
    assert refresher.refresh_once() is True
    assert state.snapshot is not None
    assert state.snapshot.gitops_commit == COMMIT
    assert state.snapshot.tree_hash == "tree-1"
    assert state.status.last_success == NOW
    assert state.status.last_error is None


def test_unchanged_tree_is_not_rendered_again(refresher, renderer, state, repo):
    refresher.refresh_once()
    first = state.snapshot
    repo.commit = "f" * 40  # new commit that does not touch the chart
    assert refresher.refresh_once() is False
    assert renderer.calls == 1
    assert state.snapshot is first
    assert state.status.last_fetched_commit == "f" * 40


def test_changed_tree_is_rendered(refresher, renderer, state, repo):
    refresher.refresh_once()
    repo.tree = "tree-2"
    repo.commit = "f" * 40
    assert refresher.refresh_once() is True
    assert renderer.calls == 2
    assert state.snapshot.gitops_commit == "f" * 40


@pytest.mark.parametrize(
    "break_it",
    [
        lambda repo, renderer: setattr(repo, "sync_error", GitError("network down")),
        lambda repo, renderer: setattr(renderer, "error", RenderError("helm failed")),
        lambda repo, renderer: setattr(renderer, "output", "kind: Deployment\n  bad: [x\n"),
        lambda repo, renderer: setattr(
            renderer,
            "output",
            renderer.output
            + "\n---\n"
            + __import__("yaml").safe_dump(make_deployment("dlt-adapter-x", "x:1")),
        ),
    ],
    ids=["git", "helm", "yaml", "ambiguous"],
)
def test_failed_refresh_keeps_previous_snapshot(refresher, state, repo, renderer, break_it):
    refresher.refresh_once()
    previous = state.snapshot
    repo.tree = "tree-2"
    break_it(repo, renderer)

    assert refresher.refresh_once() is False
    assert state.snapshot is previous
    assert state.status.last_error
    assert state.status.last_success == NOW


def test_failed_render_is_retried_on_same_tree(refresher, state, repo, renderer):
    refresher.refresh_once()
    repo.tree = "tree-2"
    renderer.error = RenderError("transient")
    refresher.refresh_once()
    renderer.error = None
    assert refresher.refresh_once() is True
    assert state.snapshot.tree_hash == "tree-2"
    assert state.status.last_error is None


def test_failure_before_first_render_keeps_not_ready(refresher, state, renderer):
    renderer.error = RenderError("helm failed")
    assert refresher.refresh_once() is False
    assert state.snapshot is None
    assert "RenderError: helm failed" in state.status.last_error


def test_long_errors_are_truncated(refresher, state, renderer):
    renderer.error = RenderError("x" * 5000)
    refresher.refresh_once()
    assert len(state.status.last_error) <= 500


def test_retry_delay(refresher, state, make_settings, repo, renderer):
    assert refresher.next_delay() == STARTUP_RETRY_SECONDS
    refresher.refresh_once()
    assert refresher.next_delay() == 300
