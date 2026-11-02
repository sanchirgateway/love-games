from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.feature.dates.models import DateEvent, DateStatus
from app.feature.ideas.models import DateIdea, DateIdeaVote, IdeaVote


def _visible(user_id: int, partner_id: int):
    """Встроенные идеи, свои и партнёра."""
    return or_(DateIdea.created_by.is_(None), DateIdea.created_by.in_((user_id, partner_id)))


def _active_date(user_id: int, partner_id: int):
    """По идее у этой пары уже есть свидание, которое не отклонили и не отменили."""
    return exists().where(
        DateEvent.idea_id == DateIdea.id,
        DateEvent.status.not_in((DateStatus.DECLINED, DateStatus.CANCELLED)),
        or_(
            and_(DateEvent.created_by == user_id, DateEvent.invitee_id == partner_id),
            and_(DateEvent.created_by == partner_id, DateEvent.invitee_id == user_id),
        ),
    )


class IdeaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, idea: DateIdea) -> DateIdea:
        self.session.add(idea)
        await self.session.flush()
        await self.session.refresh(idea, ["created_at"])  # server_default, нужен для ответа API
        return idea

    async def get(self, idea_id: UUID) -> DateIdea | None:
        return await self.session.get(DateIdea, idea_id)

    async def get_vote(self, idea_id: UUID, user_id: int) -> DateIdeaVote | None:
        return await self.session.get(DateIdeaVote, (idea_id, user_id))

    def add_vote(self, vote: DateIdeaVote) -> None:
        self.session.add(vote)

    async def list_deck(self, user_id: int, partner_id: int, limit: int) -> list[DateIdea]:
        """Идеи без ответа пользователя: сначала идеи партнёра (он их уже хочет), потом остальные вперемешку."""
        voted = exists().where(DateIdeaVote.idea_id == DateIdea.id, DateIdeaVote.user_id == user_id)
        stmt = (
            select(DateIdea)
            .where(_visible(user_id, partner_id), ~voted)
            .order_by(case((DateIdea.created_by == partner_id, 0), else_=1), func.random())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_by_author(self, user_id: int) -> list[DateIdea]:
        stmt = select(DateIdea).where(DateIdea.created_by == user_id).order_by(DateIdea.created_at.desc())
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_matches(self, user_id: int, partner_id: int, planned: bool | None = False) -> list[DateIdea]:
        """Идеи, которые хотят оба. planned: False — ещё без свидания, True — уже назначенные, None — все."""
        mine, theirs = aliased(DateIdeaVote), aliased(DateIdeaVote)
        stmt = (
            select(DateIdea)
            .join(mine, and_(mine.idea_id == DateIdea.id, mine.user_id == user_id, mine.vote == IdeaVote.YES))
            .join(
                theirs, and_(theirs.idea_id == DateIdea.id, theirs.user_id == partner_id, theirs.vote == IdeaVote.YES)
            )
            .where(_visible(user_id, partner_id))
            # Совпало, когда второй ответил «хочу»: свежие совпадения первыми
            .order_by(func.greatest(mine.updated_at, theirs.updated_at).desc())
        )
        if planned is not None:
            stmt = stmt.where(_active_date(user_id, partner_id) if planned else ~_active_date(user_id, partner_id))
        result = await self.session.scalars(stmt)
        return list(result)

    async def has_active_date(self, idea_id: UUID, user_id: int, partner_id: int) -> bool:
        stmt = select(_active_date(user_id, partner_id)).select_from(DateIdea).where(DateIdea.id == idea_id)
        return bool(await self.session.scalar(stmt))
