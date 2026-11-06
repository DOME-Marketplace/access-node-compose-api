"""Extraction of container images from a rendered Helm manifest."""

from typing import Any

import yaml

try:  # The C loader is much faster on large renders; fall back if libyaml is missing.
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _SafeLoader  # type: ignore[assignment]


class ManifestError(Exception):
    """The rendered manifest cannot be parsed or has an unexpected shape."""


def _get(mapping: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(mapping, dict):
            return None
        mapping = mapping.get(key)
    return mapping


def extract_containers(rendered: str) -> list[tuple[str, str]]:
    """Return (container name, image) for every container of every Deployment.

    Init containers are ignored. Duplicates are kept on purpose, so that the
    mapping can detect ambiguous matches.
    """
    try:
        documents = list(yaml.load_all(rendered, Loader=_SafeLoader))
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in rendered manifest: {exc}") from exc

    containers: list[tuple[str, str]] = []
    for document in documents:
        if not isinstance(document, dict) or document.get("kind") != "Deployment":
            continue
        deployment = _get(document, "metadata", "name") or "<unnamed>"
        pod_containers = _get(document, "spec", "template", "spec", "containers") or []
        if not isinstance(pod_containers, list):
            raise ManifestError(f"Deployment {deployment}: containers is not a list")
        for container in pod_containers:
            name = _get(container, "name")
            image = _get(container, "image")
            if not isinstance(name, str) or not isinstance(image, str):
                raise ManifestError(
                    f"Deployment {deployment}: container without a string name or image"
                )
            containers.append((name, image))
    return containers
