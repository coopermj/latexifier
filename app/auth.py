from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from .config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> str | None:
    """
    Verify API key from header.

    Returns the API key if valid, None if auth disabled.
    Raises HTTPException if key is invalid.
    """
    settings = get_settings()

    # If no API keys configured, allow all requests (dev mode)
    if not settings.api_key_list:
        return None

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )

    # Check against environment variable keys
    if api_key in settings.api_key_list:
        return api_key

    raise HTTPException(
        status_code=401,
        detail="Invalid API key."
    )


# Dependency for routes that require authentication
RequireAPIKey = Annotated[str | None, Security(verify_api_key)]
