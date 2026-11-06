"""Mapping between access-node-compose service keys and rendered container names.

The keys must stay identical to the keys expected by compose-template.yaml in
DOME-Marketplace/access-node-compose: service name in UPPER_SNAKE_CASE + "_IMAGE".
TM Forum services are named "tm-forum-api-<name>" there, hence the TM_FORUM_API_
prefix; the matched container names in the rendered chart have no prefix.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

Matcher = Callable[[str], bool]


class AmbiguousMatchError(Exception):
    """A service key matches more than one container in the rendered chart."""


def _exact(container_name: str) -> Matcher:
    return lambda name: name == container_name


def is_dlt_adapter_alastria(name: str) -> bool:
    # The container name depends on the fullnameOverride inherited from the
    # "dlt-adapter-alastria" alias, so it is not stable: match by prefix and
    # exclude the hashnet adapter.
    return name.startswith("dlt-adapter") and "hashnet" not in name


SERVICES: tuple[tuple[str, Matcher], ...] = (
    ("DESMOS_IMAGE", _exact("desmos")),
    ("DLT_ADAPTER_ALASTRIA_IMAGE", is_dlt_adapter_alastria),
    ("SCORPIO_IMAGE", _exact("scorpio")),
    ("TM_FORUM_API_PARTY_CATALOG_IMAGE", _exact("party-catalog")),
    ("TM_FORUM_API_CUSTOMER_BILL_MANAGEMENT_IMAGE", _exact("customer-bill-management")),
    ("TM_FORUM_API_CUSTOMER_MANAGEMENT_IMAGE", _exact("customer-management")),
    ("TM_FORUM_API_PRODUCT_CATALOG_IMAGE", _exact("product-catalog")),
    ("TM_FORUM_API_PRODUCT_INVENTORY_IMAGE", _exact("product-inventory")),
    ("TM_FORUM_API_PRODUCT_ORDERING_MANAGEMENT_IMAGE", _exact("product-ordering-management")),
    ("TM_FORUM_API_RESOURCE_CATALOG_IMAGE", _exact("resource-catalog")),
    ("TM_FORUM_API_RESOURCE_FUNCTION_ACTIVATION_IMAGE", _exact("resource-function-activation")),
    ("TM_FORUM_API_RESOURCE_INVENTORY_IMAGE", _exact("resource-inventory")),
    ("TM_FORUM_API_SERVICE_CATALOG_IMAGE", _exact("service-catalog")),
    ("TM_FORUM_API_SERVICE_INVENTORY_IMAGE", _exact("service-inventory")),
    ("TM_FORUM_API_ACCOUNT_IMAGE", _exact("account")),
    ("TM_FORUM_API_AGREEMENT_IMAGE", _exact("agreement")),
    ("TM_FORUM_API_PARTY_ROLE_IMAGE", _exact("party-role")),
    ("TM_FORUM_API_USAGE_MANAGEMENT_IMAGE", _exact("usage-management")),
    ("TM_FORUM_API_QUOTE_IMAGE", _exact("quote")),
    ("TM_FORUM_API_DOCUMENT_MANAGEMENT_IMAGE", _exact("document-management")),
)


@dataclass(frozen=True)
class Resolution:
    """Result of resolving the service keys against the rendered containers."""

    images: tuple[tuple[str, str], ...]  # (key, image), sorted by key
    missing: tuple[str, ...]  # keys with no matching container, sorted


def resolve(containers: Iterable[tuple[str, str]]) -> Resolution:
    """Resolve every service key to exactly one image.

    `containers` is a list of (container name, image) pairs. A key with no match
    is reported as missing; a key with more than one match raises
    AmbiguousMatchError, so the whole render is rejected.
    """
    containers = list(containers)
    images: dict[str, str] = {}
    missing: list[str] = []
    for key, matcher in SERVICES:
        matches = [(name, image) for name, image in containers if matcher(name)]
        if not matches:
            missing.append(key)
        elif len(matches) > 1:
            found = ", ".join(f"{name}={image}" for name, image in matches)
            raise AmbiguousMatchError(f"{key} matches more than one container: {found}")
        else:
            images[key] = matches[0][1]
    return Resolution(images=tuple(sorted(images.items())), missing=tuple(sorted(missing)))
