from fastapi import APIRouter
from sqlalchemy import text

from src.database import AsyncSessionLocal

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Basic liveness check."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict:
    """Database connectivity check."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "error", "database": str(exc)}
