from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.dates.models import DateEvent, DateStatus


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

    async def list_all(
        self,
        user_id: int | None = None,
        status: DateStatus | None = None,
        upcoming_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DateEvent]:
        stmt = select(DateEvent).order_by(DateEvent.starts_at.desc()).limit(limit).offset(offset)
        if user_id is not None:
            stmt = stmt.where(or_(DateEvent.created_by == user_id, DateEvent.invitee_id == user_id))
        if status is not None:
            stmt = stmt.where(DateEvent.status == status)
        if upcoming_only:
            stmt = stmt.where(DateEvent.starts_at >= datetime.now(UTC))
        result = await self.session.scalars(stmt)
        return list(result)

    async def mark_done_after(self, now: datetime, done_after: timedelta) -> list[UUID]:
        """Переводит в «состоялось» принятые свидания, с начала которых прошло done_after. Возвращает их id.

        done_at — момент, когда свидание должно было стать состоявшимся, а не время запуска задачи:
        иначе после простоя старые свидания выглядели бы свежими (и по ним пошли бы напоминания об отзыве).
        """
        stmt = (
            update(DateEvent)
            .where(DateEvent.status == DateStatus.PLANNED, DateEvent.starts_at <= now - done_after)
            .values(status=DateStatus.DONE, done_at=DateEvent.starts_at + done_after)
            .returning(DateEvent.id)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_by_ids(self, date_ids: list[UUID]) -> list[DateEvent]:
        result = await self.session.scalars(select(DateEvent).where(DateEvent.id.in_(date_ids)))
        return list(result)

    async def list_to_remind(self, now: datetime, horizon: datetime) -> list[DateEvent]:
        """Принятые свидания между now и horizon, по которым ещё не ушло последнее напоминание."""
        stmt = select(DateEvent).where(
            DateEvent.status == DateStatus.PLANNED,
            DateEvent.starts_at > now,
            DateEvent.starts_at <= horizon,
            # Последнее напоминание отмечается вместе со всеми предыдущими: раз его нет — что-то может быть к отправке
            DateEvent.remind_hours_before_sent_at.is_(None),
        )
        result = await self.session.scalars(stmt)
        return list(result)
