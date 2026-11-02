"""Уведомления о вишлисте в Telegram. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from app.core.time import format_local_date
from app.feature.user.models import User
from app.feature.wishlist.keyboards import item_detail_keyboard
from app.feature.wishlist.models import WishItem
from app.feature.wishlist.service import reserved_by_viewer

logger = logging.getLogger(__name__)


def describe(item: WishItem, viewer: User) -> str:
    """Карточка желания. Бронь видит только тот, кто бронировал."""
    lines = [f"🎁 <b>{escape(item.title)}</b>"]
    if item.price is not None:
        lines.append(f"💸 ~{item.price:,} ₽".replace(",", " "))
    if item.url:
        lines.append(f'🔗 <a href="{escape(item.url, quote=True)}">Ссылка</a>')
    if item.note:
        lines.append(f"\n{escape(item.note)}")
    if item.received_at is not None:
        lines.append(f"\n✅ Исполнено {format_local_date(item.received_at, viewer.timezone)}")
    elif reserved_by_viewer(item, viewer.id):
        lines.append("\n🔒 Вы забронировали — партнёр об этом не знает")
    return "\n".join(lines)


async def _send(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    # Изменение уже сохранено — ошибка отправки (например, бот заблокирован) не должна его откатывать
    try:
        _ = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.exception("Не удалось отправить уведомление о вишлисте пользователю %s", chat_id)


async def send_new_wish(bot: Bot, item: WishItem, owner: User, partner: User) -> None:
    """Партнёру: в вишлисте новое желание — можно тайно забронировать."""
    text = (
        f"🎁 {escape(owner.first_name)} добавил(а) в вишлист:\n\n{describe(item, partner)}\n\n"
        f"Забронируйте, если подарите вы, — {escape(owner.first_name)} об этом не узнает"
    )
    await _send(bot, partner.id, text, item_detail_keyboard(item, partner.id))


async def send_received(bot: Bot, item: WishItem, owner: User, reserver: User) -> None:
    """Тому, кто бронировал: владелец отметил подарок полученным."""
    text = f"✅ {escape(owner.first_name)} отметил(а), что получил(а) «{escape(item.title)}» 💝"
    await _send(bot, reserver.id, text)


async def send_deleted(bot: Bot, title: str, owner: User, reserver: User) -> None:
    """Тому, кто бронировал: владелец удалил желание — покупать уже не нужно."""
    text = (
        f"🗑 {escape(owner.first_name)} удалил(а) из вишлиста «{escape(title)}», "
        "которое вы забронировали. Если уже купили — подарок всё равно будет кстати 🙂"
    )
    await _send(bot, reserver.id, text)
