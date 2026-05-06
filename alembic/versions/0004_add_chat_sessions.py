"""add chat sessions table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-29

Adds dt_chat_sessions to store every question/response pair so that:
- The subject can correct a specific response.
- WhatsApp and other channels can reference conversation history.
- The audit trail links memories to the responses they informed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dt_chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("channel_id", sa.Text(), nullable=False, server_default="api:local"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("memories_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "has_correction", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_dt_chat_sessions_channel_id", "dt_chat_sessions", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_dt_chat_sessions_channel_id", table_name="dt_chat_sessions")
    op.drop_table("dt_chat_sessions")
