"""virtual bouquets

Revision ID: d9f1e6b3a527
Revises: c2d7f4a9e381
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd9f1e6b3a527'
down_revision: Union[str, Sequence[str], None] = 'c2d7f4a9e381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Типы enum уже созданы миграцией flower_gifts — переиспользуем, не создаём заново
    occasion = postgresql.ENUM(name='flower_occasion', create_type=False)
    reaction = postgresql.ENUM(name='flower_reaction', create_type=False)
    op.create_table('virtual_bouquets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('sender_id', sa.BigInteger(), nullable=False),
    sa.Column('recipient_id', sa.BigInteger(), nullable=False),
    sa.Column('composition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('occasion', occasion, nullable=True),
    sa.Column('card', sa.Text(), nullable=True),
    sa.Column('tg_file_id', sa.Text(), nullable=True),
    sa.Column('reaction', reaction, nullable=True),
    sa.Column('reacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('sender_id <> recipient_id', name='ck_virtual_bouquets_not_self'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_virtual_bouquets_sender_id'), 'virtual_bouquets', ['sender_id'], unique=False)
    op.create_index(op.f('ix_virtual_bouquets_recipient_id'), 'virtual_bouquets', ['recipient_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_virtual_bouquets_recipient_id'), table_name='virtual_bouquets')
    op.drop_index(op.f('ix_virtual_bouquets_sender_id'), table_name='virtual_bouquets')
    op.drop_table('virtual_bouquets')
