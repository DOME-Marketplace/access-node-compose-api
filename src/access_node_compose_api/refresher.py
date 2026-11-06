"""Background loop that keeps the served snapshot up to date."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .config import Settings
from .gitops import GitopsRepo
from .manifest import extract_containers
from .mapping import resolve
from .render import HelmRenderer
from .snapshot import Snapshot
from .state import State

logger = logging.getLogger(__name__)

# Retry delay while nothing valid has been rendered yet (capped by the refresh interval).
STARTUP_RETRY_SECONDS = 30
MAX_ERROR_LENGTH = 500


class Repo(Protocol):
    @property
    def chart_dir(self) -> Path: ...
    def sync(self) -> str: ...
    def tree_hash(self) -> str: ...


class Renderer(Protocol):
    def cleanup_stale(self) -> None: ...
    def render(self, chart_dir: Path) -> str: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Refresher:
    def __init__(
        self,
        *,
        settings: Settings,
        state: State,
        repo: Repo,
        renderer: Renderer,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._settings = settings
        self._state = state
        self._repo = repo
        self._renderer = renderer
        self._clock = clock

    @classmethod
    def from_settings(cls, settings: Settings, state: State) -> "Refresher":
        repo = GitopsRepo(
            repo_url=settings.gitops_repo_url,
            branch=settings.gitops_branch,
            chart_path=settings.access_node_chart_path,
            clone_dir=settings.work_dir / "gitops",
        )
        renderer = HelmRenderer(settings.work_dir / "render")
        return cls(settings=settings, state=state, repo=repo, renderer=renderer)

    def next_delay(self) -> float:
        interval = self._settings.refresh_interval_seconds
        if self._state.snapshot is None:
            return min(STARTUP_RETRY_SECONDS, interval)
        return interval

    async def run(self) -> None:
        await asyncio.to_thread(self._renderer.cleanup_stale)
        while True:
            await asyncio.to_thread(self.refresh_once)
            await asyncio.sleep(self.next_delay())

    def refresh_once(self) -> bool:
        """Run one refresh cycle. Return True if a new snapshot was published.

        Any failure leaves the current snapshot untouched: responses are never partial.
        """
        attempt = self._clock()
        self._update_status(last_attempt=attempt)
        try:
            commit = self._repo.sync()
            self._update_status(last_fetched_commit=commit)
            tree = self._repo.tree_hash()

            current = self._state.snapshot
            if current is not None and current.tree_hash == tree:
                logger.debug("Chart tree %s unchanged, nothing to render", tree)
                self._update_status(last_error=None)
                return False

            logger.info("Rendering chart tree %s (commit %s)", tree, commit)
            rendered = self._renderer.render(self._repo.chart_dir)
            resolution = resolve(extract_containers(rendered))
            snapshot = Snapshot.build(
                resolution=resolution,
                chart_path=self._settings.access_node_chart_path,
                gitops_commit=commit,
                tree_hash=tree,
                generated_at=self._clock(),
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if len(message) > MAX_ERROR_LENGTH:
                message = message[: MAX_ERROR_LENGTH - 3] + "..."
            logger.error("Refresh failed, keeping the previous versions: %s", message)
            self._update_status(last_error=message)
            return False

        self._state.snapshot = snapshot  # Atomic swap.
        self._update_status(last_success=snapshot.generated_at, last_error=None)
        logger.info(
            "Published versions for commit %s (missing: %s)",
            commit,
            ", ".join(snapshot.missing) or "none",
        )
        return True

    def _update_status(self, **changes: object) -> None:
        self._state.status = replace(self._state.status, **changes)
