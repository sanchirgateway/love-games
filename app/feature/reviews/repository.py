from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.dates.models import DateEvent, DateStatus
from app.feature.reviews.models import DateReview

# Отзыв можно оставить на принятое свидание, время которого уже наступило
REVIEWABLE_STATUSES = (DateStatus.PLANNED, DateStatus.DONE)


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, review: DateReview) -> DateReview:
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_by_author(self, date_id: UUID, author_id: int) -> DateReview | None:
        stmt = select(DateReview).where(DateReview.date_id == date_id, DateReview.author_id == author_id)
        return await self.session.scalar(stmt)

    async def list_all(self) -> list[DateReview]:
        # Фото подтягиваются автоматически: у relationship стоит lazy="selectin"
        stmt = select(DateReview).order_by(DateReview.created_at.desc())
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_for_date(self, date_id: UUID) -> list[DateReview]:
        stmt = select(DateReview).where(DateReview.date_id == date_id).order_by(DateReview.created_at)
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_reviewable_dates(self, user_id: int, limit: int = 10) -> list[DateEvent]:
        """Прошедшие свидания пользователя, на которые он ещё не оставил отзыв (свежие первыми)."""
        already_reviewed = exists().where(DateReview.date_id == DateEvent.id, DateReview.author_id == user_id)
        stmt = (
            select(DateEvent)
            .where(
                or_(DateEvent.created_by == user_id, DateEvent.invitee_id == user_id),
                DateEvent.status.in_(REVIEWABLE_STATUSES),
                DateEvent.starts_at <= datetime.now(UTC),
                ~already_reviewed,
            )
            .order_by(DateEvent.starts_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)
