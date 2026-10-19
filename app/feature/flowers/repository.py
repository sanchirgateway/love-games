from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.flowers.models import FlowerGift, FlowerGiftPhoto


class FlowerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, gift: FlowerGift) -> FlowerGift:
        self.session.add(gift)
        await self.session.flush()
        await self.session.refresh(gift, ["created_at", "updated_at"])  # server_default, нужны для ответа API
        return gift

    async def get(self, gift_id: UUID) -> FlowerGift | None:
        # Фото подтягиваются автоматически: у relationship стоит lazy="selectin"
        return await self.session.get(FlowerGift, gift_id)

    async def get_photo(self, photo_id: UUID) -> FlowerGiftPhoto | None:
        return await self.session.get(FlowerGiftPhoto, photo_id)

    async def list_for_user(self, user_id: int, limit: int | None = None) -> list[FlowerGift]:
        """Подаренные пользователем (включая ещё не врученные) и подаренные ему (только врученные).

        Сначала невручённые, потом по дате вручения, свежие первыми.
        """
        stmt = (
            select(FlowerGift)
            .where(
                or_(
                    FlowerGift.giver_id == user_id,
                    and_(FlowerGift.recipient_id == user_id, FlowerGift.given_at.is_not(None)),
                )
            )
            .order_by(FlowerGift.given_at.desc().nulls_first(), FlowerGift.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def count_given(self, giver_id: int) -> int:
        stmt = select(func.count()).where(FlowerGift.giver_id == giver_id, FlowerGift.given_at.is_not(None))
        return await self.session.scalar(stmt) or 0
