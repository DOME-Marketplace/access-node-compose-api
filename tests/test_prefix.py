"""Nothing may be served outside BASE_PATH: the public host is shared with the DOME portal."""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Route

from access_node_compose_api.main import create_app
from access_node_compose_api.state import State

from .test_api import publish

BASE = "/access-node-compose-api"

OUTSIDE_PREFIX = [
    "/",
    "/v1/versions",
    "/v1/health",
    "/v1/ready",
    "/v1/docs",
    "/docs",
    "/docs/",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
    "/healthz",
    "/readyz",
    "/metrics",
    "/favicon.ico",
    BASE,
    f"{BASE}/",
    f"{BASE}/v1",
    f"{BASE}/v1/",
    f"{BASE}/docs",
    f"{BASE}/openapi.json",
    f"{BASE}/v1/versions/",
    f"{BASE}/v1/health/",
    f"{BASE}/v1/docs/",
    f"{BASE}/v1/redoc",
    f"{BASE}/v1/docs/oauth2-redirect",
    f"{BASE}/access-node-compose-api/v1/versions",
]


@pytest.fixture
def client(make_settings, sbx_manifest) -> TestClient:
    state = State()
    publish(state, sbx_manifest)  # Ready, so a 404 cannot be confused with a 503.
    app = create_app(make_settings(base_path=BASE), state=state, start_refresher=False)
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", OUTSIDE_PREFIX)
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
def test_paths_outside_prefix_are_404(client, path, method):
    response = client.request(method, path)
    assert response.status_code == 404
    assert "location" not in response.headers


@pytest.mark.parametrize(
    "path", [f"{BASE}/v1/versions", f"{BASE}/v1/health", f"{BASE}/v1/ready", f"{BASE}/v1/docs"]
)
def test_valid_paths_never_redirect(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "location" not in response.headers


def test_every_route_is_under_prefix(make_settings):
    app = create_app(make_settings(base_path=BASE), state=State(), start_refresher=False)
    paths = [route.path for route in app.routes if isinstance(route, Route | APIRoute)]
    assert paths  # guard against an empty route table
    for path in paths:
        assert path.startswith(f"{BASE}/v1/"), path


def test_docs_reference_openapi_under_prefix(client):
    html = client.get(f"{BASE}/v1/docs").text
    assert f"'{BASE}/v1/openapi.json'" in html or f'"{BASE}/v1/openapi.json"' in html
    assert "oauth2-redirect" not in html
    schema = client.get(f"{BASE}/v1/openapi.json").json()
    assert "servers" not in schema  # no absolute URLs
    assert all(path.startswith(f"{BASE}/v1/") for path in schema["paths"])


@pytest.mark.parametrize("raw, normalized", [("", ""), ("/", ""), (f"{BASE}/", BASE), (BASE, BASE)])
def test_base_path_normalization(make_settings, raw, normalized):
    assert make_settings(base_path=raw).base_path == normalized


@pytest.mark.parametrize("raw", ["access-node-compose-api", "/a//b", "/a b", "/a?x"])
def test_invalid_base_path_is_rejected(make_settings, raw):
    with pytest.raises(ValueError):
        make_settings(base_path=raw)
