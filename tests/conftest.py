"""
pytest configuration and shared fixtures.

Uses in-memory SQLite for unit tests — no external database required.
Integration tests (marked with @pytest.mark.integration) require a running
PostgreSQL + pgvector instance.
"""

import json
import sqlite3
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.models.base import Base
from src.models.channel_config import ChannelConfig, ChannelType, PermissionLevel

# ---------------------------------------------------------------------------
# Register sqlite3 type adapters so UUID and list objects are accepted as
# parameter bindings without errors. These adapters are process-global but
# harmless: they only affect the sqlite3 driver, not PostgreSQL.
# ---------------------------------------------------------------------------
sqlite3.register_adapter(uuid.UUID, str)
sqlite3.register_adapter(list, json.dumps)

# ---------------------------------------------------------------------------
# In-memory async SQLite engine for unit tests
# ---------------------------------------------------------------------------

def _create_tables_sqlite(conn) -> None:
    """
    Create tables in SQLite by temporarily replacing PG-specific column types.
    sqlite3 adapters (uuid.UUID→str, list→json) handle INSERT/SELECT binding.
    """
    import sqlalchemy as sa
    import src.models  # noqa: F401 — registers all models on Base.metadata
    from src.models.base import Base

    _PG_TYPE_NAMES = {"JSONB", "UUID", "ARRAY", "Vector"}
    overrides: dict = {}
    for table in Base.metadata.tables.values():
        for col in table.columns:
            type_name = type(col.type).__name__
            if type_name in _PG_TYPE_NAMES:
                overrides[col] = col.type
                col.type = sa.Text()  # all PG types → Text for DDL only

    try:
        Base.metadata.create_all(conn)
    finally:
        for col, original in overrides.items():
            col.type = original


@pytest_asyncio.fixture
async def async_engine():
    """Create a fresh in-memory SQLite engine per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_create_tables_sqlite)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    """Provide a transactional async database session, rolled back after each test."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------

class MockLLMProvider:
    """
    Minimal LLM provider for unit tests.
    embed() raises NotImplementedError so MemoryService falls back to
    recency-sorted retrieval, avoiding pgvector's <=> operator which
    SQLite does not support.
    """

    async def complete(self, messages, max_tokens=1024, temperature=0.7, **kwargs):
        from src.llm.base import LLMResponse
        return LLMResponse(content="mock response", model="mock", usage={})

    async def embed(self, text: str):
        # Raise NotImplementedError so MemoryService uses the recency fallback,
        # keeping tests compatible with SQLite.
        raise NotImplementedError("MockLLMProvider does not generate embeddings")

    def build_memory_prompt(self, system_instruction, memory_context, user_message):
        from src.llm.base import LLMMessage
        return [LLMMessage(role="system", content=system_instruction)]


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


# ---------------------------------------------------------------------------
# Channel config fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def readonly_channel(db_session: AsyncSession) -> ChannelConfig:
    config = ChannelConfig(
        channel_id="slack:C_READONLY",
        channel_type=ChannelType.slack,
        permission_level=PermissionLevel.read_only_chat,
        is_active=True,
    )
    db_session.add(config)
    await db_session.flush()
    return config


@pytest_asyncio.fixture
async def learn_channel(db_session: AsyncSession) -> ChannelConfig:
    config = ChannelConfig(
        channel_id="slack:C_LEARN",
        channel_type=ChannelType.slack,
        permission_level=PermissionLevel.learn_candidate,
        is_active=True,
    )
    db_session.add(config)
    await db_session.flush()
    return config


@pytest_asyncio.fixture
async def admin_channel(db_session: AsyncSession) -> ChannelConfig:
    config = ChannelConfig(
        channel_id="slack:C_ADMIN",
        channel_type=ChannelType.slack,
        permission_level=PermissionLevel.admin,
        is_active=True,
        allowed_user_ids=["U_ADMIN_1"],
    )
    db_session.add(config)
    await db_session.flush()
    return config
