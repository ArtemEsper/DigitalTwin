"""
FastAPI dependency injection helpers.
"""

from fastapi import Header, HTTPException, status
from fastapi.security import APIKeyHeader

from src.config import settings

_admin_key_scheme = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(x_admin_key: str | None = Header(default=None)) -> str:
    """
    Dependency that enforces the admin API key header.
    Returns the key value if valid; raises 403 otherwise.
    """
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Key header",
        )
    return x_admin_key
