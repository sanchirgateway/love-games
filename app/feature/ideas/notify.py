"""Уведомления об идеях в Telegram. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.feature.ideas.keyboards import match_keyboard
from app.feature.ideas.models import DateIdea
from app.feature.user.models import User

logger = logging.getLogger(__name__)


def describe(idea: DateIdea, viewer_id: int, partner_name: str) -> str:
    """Карточка идеи. Чья идея — для того, кто смотрит."""
    lines = [f"💡 <b>{escape(idea.title)}</b>"]
    if idea.description:
        lines.append(escape(idea.description))
    if idea.place:
        lines.append(f"📍 {escape(idea.place)}")
    if idea.created_by == viewer_id:
        lines.append("\n✍️ Ваша идея")
    elif idea.created_by is not None:
        lines.append(f"\n💌 Идея от {escape(partner_name)}")
    return "\n".join(lines)


async def send_match(bot: Bot, idea: DateIdea, user: User, partner: User) -> None:
    """Совпадение: обоим — карточка идеи и кнопка «Назначить свидание»."""
    for viewer, other in ((user, partner), (partner, user)):
        card = describe(idea, viewer.id, other.first_name)
        text = f"💞 Совпадение! Вы с {escape(other.first_name)} оба хотите:\n\n{card}"
        try:
            _ = await bot.send_message(viewer.id, text, reply_markup=match_keyboard(idea.id))
        except TelegramAPIError:
            logger.exception("Не удалось отправить совпадение по идее %s пользователю %s", idea.id, viewer.id)
