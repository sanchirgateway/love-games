from aiogram.utils.deep_linking import create_start_link
from fastapi import APIRouter

from app.core.api import BotDep, SessionDep
from app.feature.user.dependencies import CurrentUser
from app.feature.user.models import User
from app.feature.user.schemas import PairOut, UserOut, UserShort
from app.feature.user.service import UserService, make_pair_payload

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> User:
    return user


@router.get("/pair", response_model=PairOut)
async def get_pair(user: CurrentUser, session: SessionDep, bot: BotDep) -> PairOut:
    """Пара пользователя. Без пары — ссылка-приглашение, как в /pair: партнёр открывает её и жмёт «Старт»."""
    if user.partner_id is not None:
        partner = await UserService(session).get(user.partner_id)
        return PairOut(partner=UserShort.model_validate(partner), invite_link=None)
    return PairOut(partner=None, invite_link=await create_start_link(bot, make_pair_payload(user.id)))
