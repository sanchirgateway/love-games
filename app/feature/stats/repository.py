from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.dates.models import DateEvent
from app.feature.flowers.models import FlowerGift
from app.feature.games.models import Game, GameSession
from app.feature.reviews.models import DateReview


class StatsRepository:
    """Сырые данные пары для статистики. Видимость (сюрпризы, скрытые отзывы) проверяет сервис."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_dates(
        self, user_id: int, partner_id: int, since: datetime | None, until: datetime | None
    ) -> list[DateEvent]:
        stmt = select(DateEvent).where(
            or_(
                and_(DateEvent.created_by == user_id, DateEvent.invitee_id == partner_id),
                and_(DateEvent.created_by == partner_id, DateEvent.invitee_id == user_id),
            )
        )
        if since is not None:
            stmt = stmt.where(DateEvent.starts_at >= since)
        if until is not None:
            stmt = stmt.where(DateEvent.starts_at < until)
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_date_reviews(self, date_ids: list[UUID]) -> list[DateReview]:
        if not date_ids:
            return []
        # Фото подтягиваются автоматически: у relationship стоит lazy="selectin"
        result = await self.session.scalars(select(DateReview).where(DateReview.date_id.in_(date_ids)))
        return list(result)

    async def list_gifts(self, user_id: int, partner_id: int) -> list[FlowerGift]:
        """Букеты пары в обе стороны, включая невручённые. Период — по given_at, его фильтрует сервис."""
        stmt = select(FlowerGift).where(
            or_(
                and_(FlowerGift.giver_id == user_id, FlowerGift.recipient_id == partner_id),
                and_(FlowerGift.giver_id == partner_id, FlowerGift.recipient_id == user_id),
            )
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_games(self, owner_ids: list[int]) -> list[Game]:
        result = await self.session.scalars(select(Game).where(Game.created_by.in_(owner_ids)))
        return list(result)

    async def list_game_sessions(
        self, owner_ids: list[int], since: datetime | None, until: datetime | None
    ) -> list[GameSession]:
        # Игра и отзывы подтягиваются автоматически: lazy="joined" и lazy="selectin" у relationship
        stmt = select(GameSession).join(Game, Game.id == GameSession.game_id).where(Game.created_by.in_(owner_ids))
        if since is not None:
            stmt = stmt.where(GameSession.played_at >= since)
        if until is not None:
            stmt = stmt.where(GameSession.played_at < until)
        result = await self.session.scalars(stmt)
        return list(result)
