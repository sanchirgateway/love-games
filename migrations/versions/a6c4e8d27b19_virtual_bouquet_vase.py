"""virtual bouquet vase

Revision ID: a6c4e8d27b19
Revises: d9f1e6b3a527
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6c4e8d27b19'
down_revision: Union[str, Sequence[str], None] = 'd9f1e6b3a527'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('virtual_bouquets', sa.Column('vase', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('virtual_bouquets', 'vase')
