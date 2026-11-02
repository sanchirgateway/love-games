"""wishlist items

Revision ID: c2d7f4a9e381
Revises: b8e45f12931e
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d7f4a9e381'
down_revision: Union[str, Sequence[str], None] = 'b8e45f12931e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('wish_items',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('reserved_by', sa.BigInteger(), nullable=True),
    sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price IS NULL OR price >= 0', name='ck_wish_items_price_non_negative'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reserved_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wish_items_owner_id'), 'wish_items', ['owner_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_wish_items_owner_id'), table_name='wish_items')
    op.drop_table('wish_items')
