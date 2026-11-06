"""Rendering of the access-node chart with the helm CLI."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

HELM_DEPENDENCY_TIMEOUT_SECONDS = 180
HELM_TEMPLATE_TIMEOUT_SECONDS = 120


class RenderError(Exception):
    """helm failed or timed out."""


class HelmRenderer:
    """Renders a chart in a throwaway copy, so the git clone is never modified."""

    def __init__(
        self,
        render_root: Path,
        *,
        dependency_timeout: float = HELM_DEPENDENCY_TIMEOUT_SECONDS,
        template_timeout: float = HELM_TEMPLATE_TIMEOUT_SECONDS,
    ) -> None:
        self._render_root = render_root
        self._dependency_timeout = dependency_timeout
        self._template_timeout = template_timeout

    def cleanup_stale(self) -> None:
        """Remove leftovers of renders interrupted by a previous run."""
        shutil.rmtree(self._render_root, ignore_errors=True)

    def render(self, chart_dir: Path) -> str:
        if not (chart_dir / "Chart.yaml").is_file():
            raise RenderError(f"no Chart.yaml in {chart_dir}")
        self._render_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="render-", dir=self._render_root))
        try:
            chart = work / "chart"
            shutil.copytree(chart_dir, chart, symlinks=True)
            self._helm(["dependency", "build", "."], chart, self._dependency_timeout)
            return self._helm(["template", "extract", "."], chart, self._template_timeout)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def _helm(args: list[str], cwd: Path, timeout: float) -> str:
        command = "helm " + " ".join(args[:2])
        logger.info("Running %s", command)
        try:
            result = subprocess.run(
                ["helm", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"{command} timed out after {timeout}s") from exc
        except OSError as exc:
            raise RenderError(f"{command} could not be started: {exc}") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if len(stderr) > 1000:
                stderr = "..." + stderr[-1000:]
            raise RenderError(f"{command} failed ({result.returncode}): {stderr}")
        return result.stdout
