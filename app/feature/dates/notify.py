"""Уведомления о свиданиях в Telegram. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.time import format_local
from app.feature.dates.keyboards import invite_keyboard
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.dates.reminders import Reminder
from app.feature.user.keyboards import open_app_keyboard
from app.feature.user.models import User
from config.config import bot_settings

logger = logging.getLogger(__name__)


def describe(date: DateEvent, viewer: User) -> str:
    """Карточка свидания, время — в часовом поясе того, кто смотрит."""
    lines = [f"<b>{escape(date.title)}</b>", f"🗓 {format_local(date.starts_at, viewer.timezone)}"]
    if date.place:
        lines.append(f"📍 {escape(date.place)}")
    if date.address:
        lines.append(f"🏠 {escape(date.address)}")
    if date.description:
        lines.append(f"\n{escape(date.description)}")
    return "\n".join(lines)


async def send_invite(bot: Bot, date: DateEvent) -> bool:
    """Отправляет приглашение. False — не дошло (например, партнёр заблокировал бота)."""
    text = f"💐 {escape(date.creator.first_name)} приглашает на свидание\n\n{describe(date, date.invitee)}"
    return await _safe_send(bot, date.invitee.id, text, date)


async def send_app_invite(bot: Bot, date: DateEvent) -> bool:
    """Приглашение, созданное в Mini App: в чат бота — только уведомление, ответ даётся в приложении."""
    text = (
        f"💐 {escape(date.creator.first_name)} приглашает вас на свидание «{escape(date.title)}»\n\n"
        "Откройте Bloomy, чтобы посмотреть детали и ответить"
    )
    reply_markup = open_app_keyboard(bot_settings.webapp_url) if bot_settings.webapp_url else None
    try:
        _ = await bot.send_message(date.invitee.id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.exception("Не удалось отправить уведомление о свидании %s пользователю %s", date.id, date.invitee.id)
        return False
    return True


async def send_answer(bot: Bot, date: DateEvent) -> None:
    name = escape(date.invitee.first_name)
    if date.status == DateStatus.PLANNED:
        text = f"🎉 {name} принял(а) приглашение!\n\n{describe(date, date.creator)}"
    else:
        text = f"😔 {name} отказался(ась) от свидания\n\n{describe(date, date.creator)}"
    _ = await _safe_send(bot, date.creator.id, text, date)


async def send_reminder(bot: Bot, date: DateEvent, reminder: Reminder) -> None:
    for user, partner in ((date.creator, date.invitee), (date.invitee, date.creator)):
        text = f"⏰ Свидание с {escape(partner.first_name)} {reminder.when}\n\n{describe(date, user)}"
        _ = await _safe_send(bot, user.id, text, date)


async def _safe_send(bot: Bot, chat_id: int, text: str, date: DateEvent) -> bool:
    # Свидание уже сохранено — ошибка отправки (например, бот заблокирован) не должна его откатывать
    try:
        reply_markup = invite_keyboard(date.id) if date.status == DateStatus.PROPOSED else None
        _ = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.exception("Не удалось отправить уведомление о свидании %s пользователю %s", date.id, chat_id)
        return False
    return True
