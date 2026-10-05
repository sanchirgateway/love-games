"""pairs and invitations

Revision ID: 5a04ec76f41e
Revises: 41430de44f43
Create Date: 2026-10-06 02:11:29.698049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a04ec76f41e'
down_revision: Union[str, Sequence[str], None] = '41430de44f43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Новые значения enum Alembic не видит — добавляем вручную.
    # autocommit_block: значение enum нельзя использовать в той же транзакции, где оно добавлено
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE date_status ADD VALUE IF NOT EXISTS 'proposed' BEFORE 'planned'")
        op.execute("ALTER TYPE date_status ADD VALUE IF NOT EXISTS 'declined' AFTER 'planned'")

    # Пара пользователей
    op.add_column("users", sa.Column("partner_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("users_partner_id_key", "users", ["partner_id"])
    op.create_foreign_key(
        "users_partner_id_fkey", "users", "users", ["partner_id"], ["id"], ondelete="SET NULL"
    )

    # Приглашённый в свидании (в таблице dates пока нет строк, поэтому сразу NOT NULL)
    op.add_column("dates", sa.Column("invitee_id", sa.BigInteger(), nullable=False))
    op.create_index(op.f("ix_dates_invitee_id"), "dates", ["invitee_id"], unique=False)
    op.create_foreign_key(
        "dates_invitee_id_fkey", "dates", "users", ["invitee_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("dates_invitee_id_fkey", "dates", type_="foreignkey")
    op.drop_index(op.f("ix_dates_invitee_id"), table_name="dates")
    op.drop_column("dates", "invitee_id")

    op.drop_constraint("users_partner_id_fkey", "users", type_="foreignkey")
    op.drop_constraint("users_partner_id_key", "users", type_="unique")
    op.drop_column("users", "partner_id")

    # Значения 'proposed' и 'declined' остаются в типе date_status: Postgres не умеет удалять значения enum.
    # Переводим строки на старые статусы, чтобы старый код их понимал.
    op.execute("UPDATE dates SET status = 'planned' WHERE status = 'proposed'")
    op.execute("UPDATE dates SET status = 'cancelled' WHERE status = 'declined'")
