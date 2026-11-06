import pytest

from access_node_compose_api.manifest import ManifestError, extract_containers


def test_extracts_only_deployment_containers(sbx_manifest):
    containers = extract_containers(sbx_manifest)
    names = [name for name, _ in containers]
    assert ("desmos", "in2workspace/in2-desmos-api:v1.4.2") in containers
    assert "wait-for-db" not in names  # init containers are ignored
    assert "postgis" not in names  # StatefulSet is ignored
    assert "log-shipper" in names  # every container of a Deployment is collected


def test_empty_documents_and_other_kinds_are_skipped():
    rendered = "---\n---\nkind: Service\nmetadata: {name: x}\n---\n# only a comment\n"
    assert extract_containers(rendered) == []


def test_deployment_without_containers_is_skipped():
    assert extract_containers("kind: Deployment\nmetadata: {name: x}\nspec: {}\n") == []


def test_invalid_yaml_raises():
    with pytest.raises(ManifestError, match="invalid YAML"):
        extract_containers("kind: Deployment\n  bad: [indent\n")


def test_container_without_image_raises():
    rendered = "kind: Deployment\nspec: {template: {spec: {containers: [{name: desmos}]}}}\n"
    with pytest.raises(ManifestError, match="without a string name or image"):
        extract_containers(rendered)


def test_containers_not_a_list_raises():
    rendered = "kind: Deployment\nspec: {template: {spec: {containers: {name: desmos}}}}\n"
    with pytest.raises(ManifestError, match="not a list"):
        extract_containers(rendered)
