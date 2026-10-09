"""date done_at and review reminder

Revision ID: c7e2d91a4f10
Revises: b3a3f3aab717
Create Date: 2026-10-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e2d91a4f10'
down_revision: Union[str, Sequence[str], None] = 'b3a3f3aab717'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('dates', sa.Column('done_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dates', sa.Column('review_reminder_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dates', 'review_reminder_sent_at')
    op.drop_column('dates', 'done_at')
