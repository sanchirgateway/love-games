from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.api import BotDep, SessionDep
from app.feature.dates import notify as dates_notify
from app.feature.dates.models import DateEvent
from app.feature.dates.schemas import DateOut
from app.feature.ideas import notify
from app.feature.ideas.models import DateIdea
from app.feature.ideas.schemas import IdeaCreate, IdeaOut, IdeaPlanIn, IdeaVoteIn, IdeaVoteOut
from app.feature.ideas.service import DECK_LIMIT_MAX, IdeaService
from app.feature.user.dependencies import CurrentUser

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.get("/deck", response_model=list[IdeaOut])
async def get_deck(
    user: CurrentUser, session: SessionDep, limit: Annotated[int, Query(ge=1, le=DECK_LIMIT_MAX)] = 20
) -> list[DateIdea]:
    """Идеи, на которые пользователь ещё не ответил: сначала идеи партнёра, остальные вперемешку."""
    return await IdeaService(session).deck(user.id, limit)


@router.get("/matches", response_model=list[IdeaOut])
async def get_matches(
    user: CurrentUser,
    session: SessionDep,
    planned: Annotated[
        bool | None, Query(description="false — ещё без свидания (по умолчанию), true — уже назначенные, пусто — все")
    ] = False,
) -> list[DateIdea]:
    """Совпадения: идеи, которые хотят оба. Свежие первыми."""
    return await IdeaService(session).matches(user.id, planned)


@router.get("/mine", response_model=list[IdeaOut])
async def get_mine(user: CurrentUser, session: SessionDep) -> list[DateIdea]:
    return await IdeaService(session).list_mine(user.id)


@router.post("", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
async def create_idea(body: IdeaCreate, user: CurrentUser, session: SessionDep) -> DateIdea:
    """Своя идея. Автор сразу считается «хочу»: совпадение будет, как только партнёр ответит «хочу»."""
    return await IdeaService(session).create(user.id, body.title, body.description, body.place)


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(idea_id: UUID, user: CurrentUser, session: SessionDep) -> None:
    """Удалить свою идею. Встроенные и идеи партнёра удалить нельзя — 403."""
    await IdeaService(session).delete(idea_id, user.id)


@router.put("/{idea_id}/vote", response_model=IdeaVoteOut)
async def vote_idea(
    idea_id: UUID, body: IdeaVoteIn, user: CurrentUser, session: SessionDep, bot: BotDep
) -> IdeaVoteOut:
    """Ответ «хочу» / «не хочу», можно поменять. При совпадении обоим приходит сообщение в Telegram."""
    service = IdeaService(session)
    result = await service.vote(idea_id, user.id, body.vote)
    if result.matched:
        me, partner = await service.couple(user.id)
        await notify.send_match(bot, result.idea, me, partner)
    return IdeaVoteOut(idea=IdeaOut.model_validate(result.idea), matched=result.matched)


@router.post("/{idea_id}/plan", response_model=DateOut, status_code=status.HTTP_201_CREATED)
async def plan_idea(idea_id: UUID, body: IdeaPlanIn, user: CurrentUser, session: SessionDep, bot: BotDep) -> DateEvent:
    """Предложить свидание по совпадению — как POST /dates, название и описание берутся из идеи."""
    date = await IdeaService(session).plan(idea_id, user.id, body.starts_at, body.place)
    _ = await dates_notify.send_app_invite(bot, date)
    return date
