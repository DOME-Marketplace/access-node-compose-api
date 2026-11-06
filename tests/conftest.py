from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from access_node_compose_api.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE = "fedcba9876543210fedcba9876543210fedcba98"
NOW = datetime(2026, 11, 6, 10, 15, tzinfo=UTC)


@pytest.fixture
def sbx_manifest() -> str:
    return (FIXTURES / "rendered-sbx.yaml").read_text()


@pytest.fixture
def prd_manifest(sbx_manifest: str) -> str:
    """Like sbx, but party-role is not deployed and a hashnet adapter is."""
    docs = [
        doc
        for doc in yaml.safe_load_all(sbx_manifest)
        if not (doc and doc.get("metadata", {}).get("name") == "party-role")
    ]
    docs.append(make_deployment("dlt-adapter-hashnet", "quay.io/hashnet/dlt-adapter:8.0.0"))
    return yaml.safe_dump_all(docs)


def make_deployment(name: str, image: str) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": [{"name": name, "image": image}]}}},
    }


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "access_node_chart_path": "ionos_sbx/marketplace/access-node",
            "work_dir": tmp_path / "work",
            "refresh_interval_seconds": 300,
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    return factory
