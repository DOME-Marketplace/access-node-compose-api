"""HTTP endpoints. Every route lives under {BASE_PATH}/v1."""

from datetime import datetime

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__
from .auth import api_key_dependencies
from .config import Settings
from .snapshot import format_timestamp
from .state import State

RETRY_AFTER_SECONDS = 30
TEXT_PLAIN = "text/plain; charset=utf-8"


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    version: str  # version of this service, not of the access-node images
    gitops_commit: str | None
    generated_at: str | None
    last_success: str | None
    last_attempt: str | None
    last_error: str | None
    last_fetched_commit: str | None


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Weak comparison as required for If-None-Match (RFC 9110, 13.1.2)."""
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    opaque = etag.removeprefix("W/")
    return any(
        candidate.strip().removeprefix("W/") == opaque for candidate in if_none_match.split(",")
    )


def _ts(value: datetime | None) -> str | None:
    return format_timestamp(value) if value is not None else None


def build_router(settings: Settings, state: State) -> APIRouter:
    router = APIRouter(prefix=settings.api_prefix)

    @router.get(
        "/versions",
        response_class=Response,
        dependencies=api_key_dependencies(settings.api_key),
        summary="Container image versions of this environment",
        responses={
            200: {"content": {TEXT_PLAIN: {}}, "description": "KEY=image lines"},
            304: {"description": "Not modified (If-None-Match matched the ETag)"},
            503: {"content": {TEXT_PLAIN: {}}, "description": "No valid render yet"},
        },
    )
    async def versions(request: Request) -> Response:
        snapshot = state.snapshot  # Read the reference once.
        if snapshot is None:
            return Response(
                "No versions available yet, retry later.\n",
                status_code=503,
                media_type=TEXT_PLAIN,
                headers={"Retry-After": str(RETRY_AFTER_SECONDS), "Cache-Control": "no-store"},
            )
        headers = {"ETag": snapshot.etag, "Cache-Control": "no-cache"}
        if etag_matches(request.headers.get("if-none-match"), snapshot.etag):
            return Response(status_code=304, headers=headers)
        return Response(snapshot.body, media_type=TEXT_PLAIN, headers=headers)

    @router.get("/health", response_model=HealthResponse, summary="Liveness probe")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})

    @router.get(
        "/ready",
        response_model=ReadyResponse,
        summary="Readiness probe",
        responses={503: {"model": ReadyResponse, "description": "No valid render yet"}},
    )
    async def ready() -> JSONResponse:
        snapshot = state.snapshot
        status = state.status
        body = ReadyResponse(
            status="ready" if snapshot is not None else "not_ready",
            version=__version__,
            gitops_commit=snapshot.gitops_commit if snapshot is not None else None,
            generated_at=_ts(snapshot.generated_at) if snapshot is not None else None,
            last_success=_ts(status.last_success),
            last_attempt=_ts(status.last_attempt),
            last_error=status.last_error,
            last_fetched_commit=status.last_fetched_commit,
        )
        return JSONResponse(
            body.model_dump(),
            status_code=200 if snapshot is not None else 503,
            headers={"Cache-Control": "no-store"},
        )

    return router
