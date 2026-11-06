"""Application factory."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .api import build_router
from .config import Settings
from .refresher import Refresher
from .state import State

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings,
    *,
    state: State | None = None,
    refresher: Refresher | None = None,
    start_refresher: bool = True,
) -> FastAPI:
    state = state if state is not None else State()
    if refresher is None and start_refresher:
        refresher = Refresher.from_settings(settings, state)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(refresher.run()) if start_refresher and refresher else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    prefix = settings.api_prefix
    app = FastAPI(
        title="access-node-compose-api",
        version=__version__,
        description="Container image versions of a DOME access-node environment, "
        "read from dome-gitops.",
        # Nothing may live outside BASE_PATH: the public host is shared with the portal.
        docs_url=f"{prefix}/docs",
        openapi_url=f"{prefix}/openapi.json",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.versions_state = state
    app.include_router(build_router(settings, state))
    logger.info("Serving under %s/", prefix)
    return app
