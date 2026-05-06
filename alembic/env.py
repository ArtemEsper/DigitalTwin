import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Change 1 & 2: Import all ORM models so they register on Base.metadata,
# then point Alembic at that metadata for autogenerate support.
#
# The bare `import src.models` is essential — importing only Base is not
# enough because each model module registers itself on Base.metadata only
# when that module is first imported.
# ---------------------------------------------------------------------------
import src.models  # noqa: F401, E402
from src.models.base import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Change 3: Read the database URL from settings (.env), not from alembic.ini.
# alembic.ini is committed to git, so credentials must never live there.
# ---------------------------------------------------------------------------
from src.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# ---------------------------------------------------------------------------
# Change 6: Import Vector so Alembic knows how to render vector(N) columns
# in generated migration files.
# ---------------------------------------------------------------------------
from pgvector.sqlalchemy import Vector  # noqa: F401, E402


# ---------------------------------------------------------------------------
# Offline mode: generate SQL script without a live DB connection.
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode: connect to the database and run migrations.
#
# Changes 4 & 5: asyncpg is async-only, so we must use async_engine_from_config
# and wrap everything in asyncio.run(). Alembic's internal runner is sync, so
# the actual context.run_migrations() call goes inside connection.run_sync()
# which bridges async connection → sync Alembic internals.
# ---------------------------------------------------------------------------
def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
