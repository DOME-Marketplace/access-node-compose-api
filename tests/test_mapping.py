import pytest

from access_node_compose_api.manifest import extract_containers
from access_node_compose_api.mapping import (
    SERVICES,
    AmbiguousMatchError,
    is_dlt_adapter_alastria,
    resolve,
)


def test_service_keys_follow_compose_template_convention():
    keys = [key for key, _ in SERVICES]
    assert len(keys) == 20
    assert len(set(keys)) == len(keys)
    for key in keys:
        assert key.endswith("_IMAGE")
        assert key == key.upper()


# Services of compose-template.yaml (access-node-compose) whose image comes from the API.
# minio, postgres, caddy and dozzle are pinned statically in the template.
COMPOSE_TEMPLATE_SERVICES = [
    "tm-forum-api-account",
    "tm-forum-api-agreement",
    "tm-forum-api-customer-bill-management",
    "tm-forum-api-customer-management",
    "tm-forum-api-party-catalog",
    "tm-forum-api-party-role",
    "tm-forum-api-product-catalog",
    "tm-forum-api-product-inventory",
    "tm-forum-api-product-ordering-management",
    "tm-forum-api-quote",
    "tm-forum-api-resource-catalog",
    "tm-forum-api-resource-function-activation",
    "tm-forum-api-resource-inventory",
    "tm-forum-api-service-catalog",
    "tm-forum-api-service-inventory",
    "tm-forum-api-usage-management",
    "tm-forum-api-document-management",
    "desmos",
    "dlt-adapter-alastria",
    "scorpio",
]


def test_keys_match_compose_template_services():
    # Same rule as wizard.py: service name upper-cased, '-' and '.' to '_', plus "_IMAGE".
    expected = {
        service.upper().replace("-", "_").replace(".", "_") + "_IMAGE"
        for service in COMPOSE_TEMPLATE_SERVICES
    }
    assert {key for key, _ in SERVICES} == expected


@pytest.mark.parametrize(
    "name",
    ["dlt-adapter", "dlt-adapter-alastria", "dlt-adapter-alastria-access-node", "dlt-adapterx"],
)
def test_dlt_matcher_accepts_alastria_names(name):
    assert is_dlt_adapter_alastria(name)


@pytest.mark.parametrize(
    "name", ["dlt-adapter-hashnet", "dlt-adapter-hashnet-prd", "desmos", "my-dlt-adapter"]
)
def test_dlt_matcher_rejects_other_names(name):
    assert not is_dlt_adapter_alastria(name)


def test_resolve_full_sbx(sbx_manifest):
    resolution = resolve(extract_containers(sbx_manifest))
    images = dict(resolution.images)
    assert resolution.missing == ()
    assert len(images) == 20
    assert images["DESMOS_IMAGE"] == "in2workspace/in2-desmos-api:v1.4.2"
    assert images["DLT_ADAPTER_ALASTRIA_IMAGE"] == "quay.io/digitelts/dlt-adapter:2.1.0"
    assert images["SCORPIO_IMAGE"] == "scorpiobroker/all-in-one-runner:java-4.1.11"
    assert [key for key, _ in resolution.images] == sorted(images)


def test_resolve_prd_reports_party_role_missing(prd_manifest):
    resolution = resolve(extract_containers(prd_manifest))
    assert resolution.missing == ("TM_FORUM_API_PARTY_ROLE_IMAGE",)
    images = dict(resolution.images)
    assert "TM_FORUM_API_PARTY_ROLE_IMAGE" not in images
    # The hashnet adapter must not be picked up as the Alastria one.
    assert images["DLT_ADAPTER_ALASTRIA_IMAGE"] == "quay.io/digitelts/dlt-adapter:2.1.0"


def test_resolve_empty_reports_everything_missing():
    resolution = resolve([])
    assert resolution.images == ()
    assert len(resolution.missing) == 20


def test_two_dlt_adapters_are_ambiguous():
    with pytest.raises(AmbiguousMatchError, match="DLT_ADAPTER_ALASTRIA_IMAGE"):
        resolve([("dlt-adapter", "a:1"), ("dlt-adapter-alastria", "b:2")])


def test_duplicate_exact_name_is_ambiguous_even_with_same_image():
    with pytest.raises(AmbiguousMatchError, match="DESMOS_IMAGE"):
        resolve([("desmos", "a:1"), ("desmos", "a:1")])
