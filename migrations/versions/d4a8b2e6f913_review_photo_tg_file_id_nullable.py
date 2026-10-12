"""review photo tg_file_id nullable

Revision ID: d4a8b2e6f913
Revises: c7e2d91a4f10
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a8b2e6f913'
down_revision: Union[str, Sequence[str], None] = 'c7e2d91a4f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('date_review_photos', 'tg_file_id', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Фото из Mini App не имеют file_id — без них NOT NULL не поставить
    op.execute("DELETE FROM date_review_photos WHERE tg_file_id IS NULL")
    op.alter_column('date_review_photos', 'tg_file_id', existing_type=sa.Text(), nullable=False)
