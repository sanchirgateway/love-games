from typing import Annotated, cast

from aiogram import Bot
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_bot(request: Request) -> Bot:
    return cast(Bot, request.app.state.bot)


BotDep = Annotated[Bot, Depends(get_bot)]
