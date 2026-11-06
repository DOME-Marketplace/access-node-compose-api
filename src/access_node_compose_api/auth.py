"""Optional API-key authentication.

Disabled unless API_KEY is set. When enabled, clients must send the key in the
X-API-Key header.
"""

import hmac

from fastapi import Depends, HTTPException, Security, status
from fastapi.params import Depends as DependsParam
from fastapi.security import APIKeyHeader
from pydantic import SecretStr

API_KEY_HEADER = "X-API-Key"


def api_key_dependencies(api_key: SecretStr | None) -> list[DependsParam]:
    """Return the route dependencies enforcing the API key, or none if disabled."""
    if api_key is None:
        return []

    expected = api_key.get_secret_value().encode()
    header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)

    async def check_api_key(provided: str | None = Security(header)) -> None:
        if provided is None or not hmac.compare_digest(provided.encode(), expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
                headers={"WWW-Authenticate": "APIKey"},
            )

    return [Depends(check_api_key)]
