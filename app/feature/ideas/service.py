from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.feature.dates.models import DateEvent
from app.feature.dates.service import DateService
from app.feature.ideas.models import DateIdea, DateIdeaVote, IdeaVote
from app.feature.ideas.repository import IdeaRepository
from app.feature.user.models import User
from app.feature.user.service import UserService

TITLE_MAX = 200
PLACE_MAX = 200
TEXT_MAX = 2000
DECK_LIMIT_MAX = 50
OWN_IDEAS_MAX = 200


@dataclass(frozen=True)
class VoteResult:
    idea: DateIdea
    matched: bool  # совпадение случилось именно сейчас — пора уведомить обоих


def _clean(value: str | None, field: str, limit: int) -> str | None:
    """Пустая строка — «не заполнено»."""
    value = (value or "").strip()
    if len(value) > limit:
        raise AppError(f"{field}: не больше {limit} символов")
    return value or None


class IdeaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = IdeaRepository(session)
        self.users = UserService(session)

    async def couple(self, user_id: int) -> tuple[User, User]:
        """Пользователь и его партнёр. Идеи — общие для пары, без пары — ConflictError."""
        return await self.users.get(user_id), await self.users.get_partner(user_id)

    async def get(self, idea_id: UUID, user_id: int) -> DateIdea:
        """Идея, видимая пользователю: встроенная, своя или текущего партнёра."""
        _, partner = await self.couple(user_id)
        idea = await self.repo.get(idea_id)
        if idea is None or idea.created_by not in (None, user_id, partner.id):
            raise NotFoundError("Идея не найдена")
        return idea

    async def create(
        self, user_id: int, title: str, description: str | None = None, place: str | None = None
    ) -> DateIdea:
        """Своя идея. Автор её, понятно, хочет — сразу голос «хочу»: совпадение будет, когда ответит партнёр."""
        _ = await self.couple(user_id)
        title_text = _clean(title, "Название", TITLE_MAX)
        if title_text is None:
            raise AppError("Напишите, что за идея")
        if len(await self.repo.list_by_author(user_id)) >= OWN_IDEAS_MAX:
            raise AppError(f"Можно завести не больше {OWN_IDEAS_MAX} своих идей — удалите ненужные")
        idea = await self.repo.create(
            DateIdea(
                created_by=user_id,
                title=title_text,
                description=_clean(description, "Описание", TEXT_MAX),
                place=_clean(place, "Место", PLACE_MAX),
            )
        )
        self.repo.add_vote(DateIdeaVote(idea_id=idea.id, user_id=user_id, vote=IdeaVote.YES))
        await self.session.commit()
        return idea

    async def delete(self, idea_id: UUID, user_id: int) -> None:
        """Удалить можно только свою идею. Ответы удаляются каскадом, у свиданий idea_id обнуляется."""
        idea = await self.get(idea_id, user_id)
        if idea.created_by != user_id:
            raise ForbiddenError("Удалить можно только свою идею")
        await self.session.delete(idea)
        await self.session.commit()

    async def deck(self, user_id: int, limit: int = 20) -> list[DateIdea]:
        """Идеи, на которые пользователь ещё не ответил."""
        _, partner = await self.couple(user_id)
        return await self.repo.list_deck(user_id, partner.id, min(max(limit, 1), DECK_LIMIT_MAX))

    async def list_mine(self, user_id: int) -> list[DateIdea]:
        return await self.repo.list_by_author(user_id)

    async def matches(self, user_id: int, planned: bool | None = False) -> list[DateIdea]:
        _, partner = await self.couple(user_id)
        return await self.repo.list_matches(user_id, partner.id, planned)

    async def vote(self, idea_id: UUID, user_id: int, vote: IdeaVote) -> VoteResult:
        """Ответ на идею, можно поменять. «Не хочу» партнёру не показывается: у него просто не будет совпадения."""
        idea = await self.get(idea_id, user_id)
        if idea.created_by == user_id:
            raise ConflictError("Это ваша идея — вы её уже хотите. Если передумали, удалите её")
        _, partner = await self.couple(user_id)

        current = await self.repo.get_vote(idea.id, user_id)
        was_yes = current is not None and current.vote == IdeaVote.YES
        if current is None:
            self.repo.add_vote(DateIdeaVote(idea_id=idea.id, user_id=user_id, vote=vote))
        else:
            current.vote = vote
        await self.session.commit()

        # Повторное «хочу» не должно второй раз присылать уведомление о совпадении
        matched = vote == IdeaVote.YES and not was_yes and await self._wants(idea.id, partner.id)
        return VoteResult(idea=idea, matched=matched)

    async def can_plan(self, idea: DateIdea, user_id: int) -> bool:
        """Оба хотят и свидания по идее ещё нет (или его отклонили / отменили)."""
        _, partner = await self.couple(user_id)
        return (
            await self._wants(idea.id, user_id)
            and await self._wants(idea.id, partner.id)
            and not await self.repo.has_active_date(idea.id, user_id, partner.id)
        )

    async def check_can_plan(self, idea_id: UUID, user_id: int) -> DateIdea:
        idea = await self.get(idea_id, user_id)
        _, partner = await self.couple(user_id)
        if not await self._wants(idea.id, user_id) or not await self._wants(idea.id, partner.id):
            raise ConflictError("Это ещё не совпадение — свидание можно назначить, когда идею хотят оба")
        if await self.repo.has_active_date(idea.id, user_id, partner.id):
            raise ConflictError("По этой идее свидание уже назначено")
        return idea

    async def _wants(self, idea_id: UUID, user_id: int) -> bool:
        vote = await self.repo.get_vote(idea_id, user_id)
        return vote is not None and vote.vote == IdeaVote.YES

    async def plan(self, idea_id: UUID, user_id: int, starts_at: datetime, place: str | None = None) -> DateEvent:
        """Назначить свидание по совпадению: название и описание — из идеи, место — переданное или из идеи."""
        idea = await self.check_can_plan(idea_id, user_id)
        return await DateService(self.session).propose(
            author_id=user_id,
            title=idea.title,
            starts_at=starts_at,
            place=_clean(place, "Место", PLACE_MAX) or idea.place,
            description=idea.description,
            idea_id=idea.id,
        )
