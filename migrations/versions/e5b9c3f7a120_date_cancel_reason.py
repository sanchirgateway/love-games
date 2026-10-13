"""date cancel reason

Revision ID: e5b9c3f7a120
Revises: d4a8b2e6f913
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b9c3f7a120'
down_revision: Union[str, Sequence[str], None] = 'd4a8b2e6f913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('dates', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dates', sa.Column('cancelled_by', sa.BigInteger(), nullable=True))
    op.add_column('dates', sa.Column('cancel_reason', sa.Text(), nullable=True))
    op.create_foreign_key(
        'fk_dates_cancelled_by_users', 'dates', 'users', ['cancelled_by'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_dates_cancelled_by_users', 'dates', type_='foreignkey')
    op.drop_column('dates', 'cancel_reason')
    op.drop_column('dates', 'cancelled_by')
    op.drop_column('dates', 'cancelled_at')
