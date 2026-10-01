from aiogram.types import User as TgUser
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def upsert_user(session: AsyncSession, tg_user: TgUser) -> None:
    values = {
        "username": tg_user.username,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
    }
    stmt = insert(User).values(id=tg_user.id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[User.id], set_=values)
    await session.execute(stmt)
    await session.commit()
