"""flower gifts and photos

Revision ID: f3c1a8d5e702
Revises: e48a37debf11
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c1a8d5e702'
down_revision: Union[str, Sequence[str], None] = 'e48a37debf11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('flower_gifts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('giver_id', sa.BigInteger(), nullable=False),
    sa.Column('recipient_id', sa.BigInteger(), nullable=False),
    sa.Column('date_id', sa.Uuid(), nullable=True),
    sa.Column('flowers', sa.Text(), nullable=False),
    sa.Column('occasion', sa.Enum('no_reason', 'date', 'birthday', 'anniversary', 'holiday', 'apology', name='flower_occasion'), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('given_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reaction', sa.Enum('loved', 'touched', 'happy', 'meh', name='flower_reaction'), nullable=True),
    sa.Column('reacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('price IS NULL OR price >= 0', name='ck_flower_gifts_price_non_negative'),
    sa.CheckConstraint('giver_id <> recipient_id', name='ck_flower_gifts_not_self'),
    sa.ForeignKeyConstraint(['giver_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['date_id'], ['dates.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_flower_gifts_giver_id'), 'flower_gifts', ['giver_id'], unique=False)
    op.create_index(op.f('ix_flower_gifts_recipient_id'), 'flower_gifts', ['recipient_id'], unique=False)
    op.create_index(op.f('ix_flower_gifts_given_at'), 'flower_gifts', ['given_at'], unique=False)
    op.create_table('flower_gift_photos',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('gift_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.BigInteger(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('tg_file_id', sa.Text(), nullable=True),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('position BETWEEN 0 AND 9', name='ck_flower_gift_photos_position_range'),
    sa.CheckConstraint('size > 0', name='ck_flower_gift_photos_size_positive'),
    sa.ForeignKeyConstraint(['gift_id'], ['flower_gifts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gift_id', 'author_id', 'position', name='uq_flower_gift_photos_position'),
    sa.UniqueConstraint('key')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('flower_gift_photos')
    op.drop_index(op.f('ix_flower_gifts_given_at'), table_name='flower_gifts')
    op.drop_index(op.f('ix_flower_gifts_recipient_id'), table_name='flower_gifts')
    op.drop_index(op.f('ix_flower_gifts_giver_id'), table_name='flower_gifts')
    op.drop_table('flower_gifts')
    # Enum-типы Postgres создаются вместе с таблицами, но сами не удаляются
    sa.Enum(name='flower_reaction').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='flower_occasion').drop(op.get_bind(), checkfirst=True)
