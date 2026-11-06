from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.bouquets.models import VirtualBouquet


class BouquetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, bouquet: VirtualBouquet) -> VirtualBouquet:
        self.session.add(bouquet)
        await self.session.flush()
        await self.session.refresh(bouquet, ["created_at", "updated_at"])  # server_default, нужны для ответа API
        return bouquet

    async def get(self, bouquet_id: UUID) -> VirtualBouquet | None:
        return await self.session.get(VirtualBouquet, bouquet_id)

    async def list_for_user(self, user_id: int, limit: int | None = None) -> list[VirtualBouquet]:
        """Отправленные пользователем и полученные им, свежие первыми."""
        stmt = (
            select(VirtualBouquet)
            .where(or_(VirtualBouquet.sender_id == user_id, VirtualBouquet.recipient_id == user_id))
            .order_by(VirtualBouquet.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)
