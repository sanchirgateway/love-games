from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.dates.repository import DateRepository
from app.feature.user.service import UserService


class DateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DateRepository(session)
        self.users = UserService(session)

    async def propose(
        self,
        author_id: int,
        title: str,
        starts_at: datetime,
        place: str | None = None,
        address: str | None = None,
        description: str | None = None,
        ends_at: datetime | None = None,
    ) -> DateEvent:
        """Создаёт свидание с партнёром автора в статусе «предложено»."""
        if starts_at.tzinfo is None:
            raise AppError("Время должно быть с часовым поясом")
        if starts_at <= datetime.now(UTC):
            raise AppError("Нельзя назначить свидание в прошлом")
        if ends_at is not None and ends_at <= starts_at:
            raise AppError("Конец свидания должен быть позже начала")

        partner = await self.users.get_partner(author_id)
        date = await self.repo.create(
            DateEvent(
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                place=place,
                address=address,
                description=description,
                status=DateStatus.PROPOSED,
                created_by=author_id,
                invitee_id=partner.id,
            )
        )
        await self.session.commit()
        return date

    async def respond(self, date_id: UUID, user_id: int, accept: bool) -> DateEvent:
        """Ответ приглашённого: принять или отказаться."""
        date = await self.get_for_user(date_id, user_id)
        if date.invitee_id != user_id:
            raise ForbiddenError("Ответить на приглашение может только приглашённый")
        if date.status != DateStatus.PROPOSED:
            raise ConflictError("На это приглашение уже ответили")

        date.status = DateStatus.PLANNED if accept else DateStatus.DECLINED
        await self.session.commit()
        return date

    async def get_for_user(self, date_id: UUID, user_id: int) -> DateEvent:
        date = await self.repo.get(date_id)
        if date is None or user_id not in (date.created_by, date.invitee_id):
            raise NotFoundError("Свидание не найдено")
        return date

    async def list_for_user(self, user_id: int, upcoming_only: bool = False) -> list[DateEvent]:
        return await self.repo.list_for_user(user_id, upcoming_only)

    # --- Для админ-API: без проверки, что пользователь участник свидания ---

    async def get(self, date_id: UUID) -> DateEvent:
        date = await self.repo.get(date_id)
        if date is None:
            raise NotFoundError("Свидание не найдено")
        return date

    async def list_all(
        self,
        user_id: int | None = None,
        status: DateStatus | None = None,
        upcoming_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DateEvent]:
        return await self.repo.list_all(
            user_id=user_id, status=status, upcoming_only=upcoming_only, limit=limit, offset=offset
        )
