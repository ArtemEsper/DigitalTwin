"""enable pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-04-27

This must be the first migration. The vector PostgreSQL extension must exist
before any table with a vector(N) column can be created.
CREATE EXTENSION IF NOT EXISTS vector is idempotent — safe to run repeatedly.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Dropping the extension would destroy all vector columns — only do this
    # if you are tearing down the entire database.
    op.execute("DROP EXTENSION IF EXISTS vector")
