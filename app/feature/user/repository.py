from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.user.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def upsert(self, user_id: int, **fields: str | None) -> None:
        stmt = insert(User).values(id=user_id, **fields)
        stmt = stmt.on_conflict_do_update(index_elements=[User.id], set_=fields)
        _ = await self.session.execute(stmt)

    async def set_partner(self, user_id: int, partner_id: int | None) -> None:
        _ = await self.session.execute(update(User).where(User.id == user_id).values(partner_id=partner_id))
