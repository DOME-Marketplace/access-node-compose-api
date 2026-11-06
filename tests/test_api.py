import pytest
from fastapi.testclient import TestClient

from access_node_compose_api import __version__
from access_node_compose_api.main import create_app
from access_node_compose_api.manifest import extract_containers
from access_node_compose_api.mapping import resolve
from access_node_compose_api.snapshot import Snapshot
from access_node_compose_api.state import RefreshStatus, State

from .conftest import COMMIT, NOW, TREE

BASE = "/access-node-compose-api"


@pytest.fixture
def state() -> State:
    return State()


@pytest.fixture
def client(make_settings, state) -> TestClient:
    app = create_app(make_settings(base_path=BASE), state=state, start_refresher=False)
    return TestClient(app)


def publish(state: State, manifest: str) -> Snapshot:
    state.snapshot = Snapshot.build(
        resolution=resolve(extract_containers(manifest)),
        chart_path="ionos_sbx/marketplace/access-node",
        gitops_commit=COMMIT,
        tree_hash=TREE,
        generated_at=NOW,
    )
    state.status = RefreshStatus(last_attempt=NOW, last_success=NOW, last_fetched_commit=COMMIT)
    return state.snapshot


def test_versions_is_503_before_first_render(client):
    response = client.get(f"{BASE}/v1/versions")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "etag" not in response.headers


def test_ready_is_503_and_health_is_200_before_first_render(client):
    ready = client.get(f"{BASE}/v1/ready")
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["version"] == __version__
    health = client.get(f"{BASE}/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_versions_after_render(client, state, sbx_manifest):
    snapshot = publish(state, sbx_manifest)
    response = client.get(f"{BASE}/v1/versions")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["etag"] == snapshot.etag
    assert response.content == snapshot.body
    assert "DESMOS_IMAGE=in2workspace/in2-desmos-api:v1.4.2\n" in response.text


def test_ready_after_render(client, state, sbx_manifest):
    publish(state, sbx_manifest)
    response = client.get(f"{BASE}/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "version": __version__,
        "gitops_commit": COMMIT,
        "generated_at": "2026-11-06T10:15:00Z",
        "last_success": "2026-11-06T10:15:00Z",
        "last_attempt": "2026-11-06T10:15:00Z",
        "last_error": None,
        "last_fetched_commit": COMMIT,
    }


def test_ready_stays_200_with_last_error_after_failed_refresh(client, state, sbx_manifest):
    publish(state, sbx_manifest)
    state.status = RefreshStatus(last_success=NOW, last_error="RenderError: boom")
    response = client.get(f"{BASE}/v1/ready")
    assert response.status_code == 200
    assert response.json()["last_error"] == "RenderError: boom"


@pytest.mark.parametrize(
    "header", ["{etag}", "W/{etag}", '"other", {etag}', "*"], ids=["exact", "weak", "list", "star"]
)
def test_if_none_match_returns_304(client, state, sbx_manifest, header):
    snapshot = publish(state, sbx_manifest)
    response = client.get(
        f"{BASE}/v1/versions", headers={"If-None-Match": header.format(etag=snapshot.etag)}
    )
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == snapshot.etag


def test_if_none_match_with_other_etag_returns_200(client, state, sbx_manifest):
    publish(state, sbx_manifest)
    response = client.get(f"{BASE}/v1/versions", headers={"If-None-Match": '"stale"'})
    assert response.status_code == 200


def test_missing_services_are_reported(client, state, prd_manifest):
    publish(state, prd_manifest)
    body = client.get(f"{BASE}/v1/versions").text
    assert "# missing: TM_FORUM_API_PARTY_ROLE_IMAGE\n" in body
    assert "TM_FORUM_API_PARTY_ROLE_IMAGE=" not in body


def test_works_without_base_path(make_settings, state, sbx_manifest):
    client = TestClient(create_app(make_settings(), state=state, start_refresher=False))
    publish(state, sbx_manifest)
    assert client.get("/v1/versions").status_code == 200
    assert client.get("/v1/health").status_code == 200


class TestApiKey:
    @pytest.fixture
    def client(self, make_settings, state, sbx_manifest) -> TestClient:
        settings = make_settings(base_path=BASE, api_key="s3cret")
        publish(state, sbx_manifest)
        return TestClient(create_app(settings, state=state, start_refresher=False))

    def test_versions_requires_key(self, client):
        assert client.get(f"{BASE}/v1/versions").status_code == 401
        wrong = client.get(f"{BASE}/v1/versions", headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401
        ok = client.get(f"{BASE}/v1/versions", headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200

    def test_probes_and_docs_stay_open(self, client):
        assert client.get(f"{BASE}/v1/health").status_code == 200
        assert client.get(f"{BASE}/v1/ready").status_code == 200
        assert client.get(f"{BASE}/v1/docs").status_code == 200

    def test_auth_disabled_by_default(self, make_settings, state):
        settings = make_settings(base_path=BASE, api_key="")
        assert settings.api_key is None
        app = create_app(settings, state=state, start_refresher=False)
        schema = TestClient(app).get(f"{BASE}/v1/openapi.json").json()
        assert "securitySchemes" not in schema.get("components", {})
