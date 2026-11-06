"""Read-only access to the dome-gitops repository through the git CLI."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS = 120


class GitError(Exception):
    """A git command failed or timed out."""


class GitopsRepo:
    """Shallow, sparse clone of a single branch, limited to the chart path."""

    def __init__(
        self,
        *,
        repo_url: str,
        branch: str,
        chart_path: str,
        clone_dir: Path,
        timeout: float = GIT_TIMEOUT_SECONDS,
    ) -> None:
        self._repo_url = repo_url
        self._branch = branch
        self._chart_path = chart_path
        self._clone_dir = clone_dir
        self._timeout = timeout

    @property
    def chart_dir(self) -> Path:
        return self._clone_dir / self._chart_path

    def sync(self) -> str:
        """Clone or update the repository and return the HEAD commit sha."""
        if (self._clone_dir / ".git").is_dir():
            try:
                self._update()
            except GitError:
                if self._is_healthy():
                    raise  # Most likely a transient network error: keep the clone.
                logger.warning("Local clone is broken, cloning again")
                self._clone()
        else:
            self._clone()
        return self._git("rev-parse", "HEAD")

    def tree_hash(self) -> str:
        """Return the hash of the chart tree at HEAD."""
        try:
            return self._git("rev-parse", "--verify", f"HEAD:{self._chart_path}")
        except GitError as exc:
            raise GitError(
                f"chart path {self._chart_path!r} not found on branch {self._branch!r}"
            ) from exc

    def _clone(self) -> None:
        shutil.rmtree(self._clone_dir, ignore_errors=True)
        self._clone_dir.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Cloning %s (branch %s)", self._repo_url, self._branch)
        self._git(
            "clone",
            "--depth=1",
            "--filter=blob:none",
            "--sparse",
            "--single-branch",
            f"--branch={self._branch}",
            "--",
            self._repo_url,
            str(self._clone_dir),
            cwd=self._clone_dir.parent,
        )
        self._git("sparse-checkout", "set", "--", self._chart_path)

    def _update(self) -> None:
        self._git("fetch", "--depth=1", "--filter=blob:none", "origin", "--", self._branch)
        self._git("reset", "--hard", "FETCH_HEAD")
        self._git("clean", "-ffdx")

    def _is_healthy(self) -> bool:
        try:
            self._git("rev-parse", "--verify", "HEAD")
        except GitError:
            return False
        return True

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd or self._clone_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"git {args[0]} timed out after {self._timeout}s") from exc
        except OSError as exc:
            raise GitError(f"git {args[0]} could not be started: {exc}") from exc
        if result.returncode != 0:
            raise GitError(f"git {args[0]} failed ({result.returncode}): {_tail(result.stderr)}")
        return result.stdout.strip()


def _tail(text: str, limit: int = 1000) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]
