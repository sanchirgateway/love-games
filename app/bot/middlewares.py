from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.session import session_maker


class DbSessionMiddleware(BaseMiddleware):
    """Кладёт сессию БД в хендлер как аргумент `session`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with session_maker() as session:
            data["session"] = session
            return await handler(event, data)
