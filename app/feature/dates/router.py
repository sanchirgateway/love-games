from uuid import UUID

from fastapi import APIRouter, status

from app.core.api import BotDep, SessionDep
from app.feature.dates import notify
from app.feature.dates.models import DateEvent
from app.feature.dates.schemas import DateCreate, DateOut
from app.feature.dates.service import DateService
from app.feature.user.dependencies import CurrentUser

router = APIRouter(prefix="/dates", tags=["dates"])


@router.get("", response_model=list[DateOut])
async def list_dates(user: CurrentUser, session: SessionDep, upcoming: bool = False) -> list[DateEvent]:
    return await DateService(session).list_for_user(user.id, upcoming_only=upcoming)


@router.post("", response_model=DateOut, status_code=status.HTTP_201_CREATED)
async def create_date(body: DateCreate, user: CurrentUser, session: SessionDep, bot: BotDep) -> DateEvent:
    date = await DateService(session).propose(author_id=user.id, **body.model_dump())
    _ = await notify.send_invite(bot, date)
    return date


@router.get("/{date_id}", response_model=DateOut)
async def get_date(date_id: UUID, user: CurrentUser, session: SessionDep) -> DateEvent:
    return await DateService(session).get_for_user(date_id, user.id)


@router.post("/{date_id}/accept", response_model=DateOut)
async def accept_date(date_id: UUID, user: CurrentUser, session: SessionDep, bot: BotDep) -> DateEvent:
    date = await DateService(session).respond(date_id, user.id, accept=True)
    await notify.send_answer(bot, date)
    return date


@router.post("/{date_id}/decline", response_model=DateOut)
async def decline_date(date_id: UUID, user: CurrentUser, session: SessionDep, bot: BotDep) -> DateEvent:
    date = await DateService(session).respond(date_id, user.id, accept=False)
    await notify.send_answer(bot, date)
    return date
