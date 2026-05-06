"""add authored_work memory types

Revision ID: 0003
Revises: 6e73234c7695
Create Date: 2026-04-29

Adds four new values to the memory_type_enum PostgreSQL type to support
extraction from documents written by the subject (not just about them):
  belief  — deep philosophical/spiritual conviction
  concept — personal term or framework used in a distinctive way
  voice   — characteristic rhetorical or stylistic pattern
  value   — core principle revealed as important through the writing
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "6e73234c7695"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE memory_type_enum ADD VALUE IF NOT EXISTS 'belief'")
    op.execute("ALTER TYPE memory_type_enum ADD VALUE IF NOT EXISTS 'concept'")
    op.execute("ALTER TYPE memory_type_enum ADD VALUE IF NOT EXISTS 'voice'")
    op.execute("ALTER TYPE memory_type_enum ADD VALUE IF NOT EXISTS 'value'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type.
    # To roll back, the enum would need to be recreated — out of scope here.
    raise NotImplementedError(
        "Downgrade not supported: PostgreSQL cannot remove enum values. "
        "Recreate the database from scratch if rollback is needed."
    )
