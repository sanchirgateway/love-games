"""dates uuid id

Revision ID: 75c781494181
Revises: 5a04ec76f41e
Create Date: 2026-10-06 15:09:16.772267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75c781494181'
down_revision: Union[str, Sequence[str], None] = '5a04ec76f41e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate не умеет менять int → uuid с данными, поэтому вручную.
    # Существующим строкам выдаются новые случайные UUID (на dates пока никто не ссылается).
    op.execute("ALTER TABLE dates ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE dates ALTER COLUMN id TYPE uuid USING gen_random_uuid()")
    op.execute("DROP SEQUENCE IF EXISTS dates_id_seq")


def downgrade() -> None:
    """Downgrade schema."""
    # Обратно: строки получают новые числовые id из восстановленной последовательности
    op.execute("CREATE SEQUENCE dates_id_seq")
    op.execute("ALTER TABLE dates ALTER COLUMN id TYPE integer USING nextval('dates_id_seq')")
    op.execute("ALTER TABLE dates ALTER COLUMN id SET DEFAULT nextval('dates_id_seq')")
    op.execute("ALTER SEQUENCE dates_id_seq OWNED BY dates.id")
