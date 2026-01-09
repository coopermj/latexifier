import hashlib
from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from .config import get_settings
from .database import is_db_available

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_key(key: str) -> str:
    """Hash an API key for storage/comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> str | None:
    """
    Verify API key from header.

    Returns the API key if valid, None if no key provided (for optional auth).
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

    # Check against environment variable keys (bootstrap keys)
    if api_key in settings.api_key_list:
        return api_key

    # If database is available, check there too
    if is_db_available():
        try:
            from sqlalchemy import select, update
            from .database import get_session, APIKey

            async for session in get_session():
                key_hash = hash_key(api_key)
                result = await session.execute(
                    select(APIKey).where(APIKey.key_hash == key_hash)
                )
                db_key = result.scalar_one_or_none()

                if db_key:
                    # Update last_used timestamp
                    await session.execute(
                        update(APIKey)
                        .where(APIKey.id == db_key.id)
                        .values(last_used=datetime.utcnow())
                    )
                    await session.commit()
                    return api_key
        except Exception:
            pass  # Fall through to invalid key error

    raise HTTPException(
        status_code=401,
        detail="Invalid API key."
    )


# Dependency for routes that require authentication
RequireAPIKey = Annotated[str | None, Security(verify_api_key)]
