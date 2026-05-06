"""update_embedding_dimension_to_1024

Revision ID: e3f1c7fa505b
Revises: 0004
Create Date: 2026-05-04 12:34:20.931260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f1c7fa505b'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE dt_memory_items ALTER COLUMN embedding TYPE vector(1024)")


def downgrade() -> None:
    op.execute("ALTER TABLE dt_memory_items ALTER COLUMN embedding TYPE vector(1536)")
