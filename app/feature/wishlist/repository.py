from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.wishlist.models import WishItem


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, item: WishItem) -> WishItem:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item, ["created_at", "updated_at"])  # server_default, нужны для ответа API
        return item

    async def get(self, item_id: UUID) -> WishItem | None:
        return await self.session.get(WishItem, item_id)

    async def list_by_owner(self, owner_id: int, limit: int | None = None) -> list[WishItem]:
        """Сначала то, что ещё хочется (свежие первыми), потом полученное."""
        stmt = (
            select(WishItem)
            .where(WishItem.owner_id == owner_id)
            .order_by(WishItem.received_at.desc().nulls_first(), WishItem.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def count_active(self, owner_id: int) -> int:
        stmt = select(func.count()).where(WishItem.owner_id == owner_id, WishItem.received_at.is_(None))
        return await self.session.scalar(stmt) or 0
