from datetime import UTC, datetime, timedelta
from typing import Annotated

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, status

from app.core.api import SessionDep
from app.feature.user.models import User
from app.feature.user.service import UserService
from config.config import app_settings, bot_settings

INIT_DATA_TTL = timedelta(days=1)


def _user_id_from_init_data(init_data: str) -> int:
    try:
        data = safe_parse_webapp_init_data(token=bot_settings.token, init_data=init_data)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная подпись initData") from None
    if data.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "В initData нет пользователя")
    if datetime.now(UTC) - data.auth_date > INIT_DATA_TTL:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData устарела, переоткройте Mini App")
    return data.user.id


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header(description="tma <initData из Telegram.WebApp.initData>")] = None,
    x_debug_user_id: Annotated[int | None, Header(description="Только при APP_DEBUG=true")] = None,
) -> User:
    if authorization and authorization.startswith("tma "):
        user_id = _user_id_from_init_data(authorization.removeprefix("tma "))
    elif app_settings.debug and x_debug_user_id is not None:
        user_id = x_debug_user_id
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужен заголовок Authorization: tma <initData>")

    return await UserService(session).get(user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
