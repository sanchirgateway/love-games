from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.dates.models import DateEvent


class DateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, date: DateEvent) -> DateEvent:
        self.session.add(date)
        await self.session.flush()
        await self.session.refresh(date, ["creator", "invitee"])
        return date

    async def get(self, date_id: UUID) -> DateEvent | None:
        return await self.session.get(DateEvent, date_id)

    async def list_for_user(self, user_id: int, upcoming_only: bool = False) -> list[DateEvent]:
        stmt = (
            select(DateEvent)
            .where(or_(DateEvent.created_by == user_id, DateEvent.invitee_id == user_id))
            .order_by(DateEvent.starts_at)
        )
        if upcoming_only:
            stmt = stmt.where(DateEvent.starts_at >= datetime.now(UTC))
        result = await self.session.scalars(stmt)
        return list(result)
