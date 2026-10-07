import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeDefault, ErrorEvent, TelegramObject

from app.core.db import session_maker
from app.core.errors import AppError
from config.config import bot_settings

logger = logging.getLogger(__name__)

# Единый список команд: из него строится меню в Telegram и текст /help.
# /start сюда не входит: его уже нажали, а новому пользователю Telegram сам покажет кнопку «Старт»
BOT_COMMANDS = [
    BotCommand(command="new", description="Предложить свидание"),
    BotCommand(command="dates", description="Мои свидания"),
    BotCommand(command="pair", description="Связаться с партнёром"),
    BotCommand(command="review", description="Оставить отзыв о свидании"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
    BotCommand(command="help", description="Список команд"),
]


def commands_help() -> str:
    return "\n".join(f"/{c.command} — {c.description}" for c in BOT_COMMANDS)


async def set_commands(bot: Bot) -> None:
    """Регистрирует команды в Telegram: появляется кнопка «Меню» и подсказки при вводе «/»."""
    _ = await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())


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


async def on_app_error(event: ErrorEvent) -> None:
    """Ошибки бизнес-логики (AppError) показываем пользователю текстом, а не роняем хендлер."""
    assert isinstance(event.exception, AppError)
    text = event.exception.message
    if event.update.callback_query is not None:
        _ = await event.update.callback_query.answer(text, show_alert=True)
    elif event.update.message is not None:
        _ = await event.update.message.answer(text)


def create_bot() -> Bot:
    return Bot(token=bot_settings.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(*routers: Router) -> Dispatcher:
    # Апдейты одного чата обрабатываются по очереди: иначе фото из альбома гонятся за состояние FSM
    dp = Dispatcher(events_isolation=SimpleEventIsolation())
    dp.update.middleware(DbSessionMiddleware())
    _ = dp.errors.register(on_app_error, ExceptionTypeFilter(AppError))
    dp.include_routers(*routers)
    return dp
