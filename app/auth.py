import hashlib
from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session, APIKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_key(key: str) -> str:
    """Hash an API key for storage/comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
    session: AsyncSession = Depends(get_session)
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

    # Check against environment variable keys first (bootstrap keys)
    if api_key in settings.api_key_list:
        return api_key

    # Check against database
    key_hash = hash_key(api_key)
    result = await session.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    db_key = result.scalar_one_or_none()

    if not db_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )

    # Update last_used timestamp
    await session.execute(
        update(APIKey)
        .where(APIKey.id == db_key.id)
        .values(last_used=datetime.utcnow())
    )
    await session.commit()

    return api_key


# Dependency for routes that require authentication
RequireAPIKey = Annotated[str | None, Depends(verify_api_key)]
