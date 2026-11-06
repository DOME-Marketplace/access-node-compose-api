import pytest
from pydantic import ValidationError

from access_node_compose_api.config import Settings


def test_defaults_from_env(monkeypatch):
    monkeypatch.setenv("ACCESS_NODE_CHART_PATH", "ionos_sbx/marketplace/access-node/")
    monkeypatch.setenv("BASE_PATH", "/access-node-compose-api/")
    monkeypatch.setenv("API_KEY", "")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.access_node_chart_path == "ionos_sbx/marketplace/access-node"
    assert settings.base_path == "/access-node-compose-api"
    assert settings.api_prefix == "/access-node-compose-api/v1"
    assert settings.api_key is None
    assert settings.gitops_branch == "main"
    assert settings.refresh_interval_seconds == 300
    assert settings.port == 8080


def test_chart_path_is_required(monkeypatch):
    monkeypatch.delenv("ACCESS_NODE_CHART_PATH", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


@pytest.mark.parametrize("path", ["", "/", "../etc", "a/../../b", "-x/y"])
def test_invalid_chart_path(make_settings, path):
    with pytest.raises(ValidationError):
        make_settings(access_node_chart_path=path)


@pytest.mark.parametrize("field", ["gitops_branch", "gitops_repo_url"])
def test_option_injection_is_rejected(make_settings, field):
    with pytest.raises(ValidationError):
        make_settings(**{field: "--upload-pack=evil"})


def test_refresh_interval_lower_bound(make_settings):
    with pytest.raises(ValidationError):
        make_settings(refresh_interval_seconds=5)


def test_api_key_is_not_printed(make_settings):
    settings = make_settings(api_key="s3cret")
    assert "s3cret" not in repr(settings)
