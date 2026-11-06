"""Виртуальные букеты в Telegram: картинка и подпись. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message

from app.core.time import format_local_date
from app.feature.bouquets import render
from app.feature.bouquets.catalog import MAX_BOUQUET_FLOWERS, Flower, get_vase
from app.feature.bouquets.keyboards import reaction_keyboard
from app.feature.bouquets.models import VirtualBouquet
from app.feature.flowers.keyboards import OCCASION_LABELS, REACTION_EMOJI
from app.feature.user.models import User

logger = logging.getLogger(__name__)


def emoji_picture(items: list[tuple[Flower, int]]) -> str:
    """Букет строкой эмодзи: «🌹🌹🌹🌿🌿». Для текстовых сообщений, где нет картинки."""
    return "".join(flower.emoji * count for flower, count in items)


def composition_text(items: list[tuple[Flower, int]]) -> str:
    """Состав букета: строка эмодзи и под ней — что сколько."""
    total = sum(count for _, count in items)
    lines = [f"{flower.emoji} {escape(flower.name)} × {count}" for flower, count in items]
    return f"{emoji_picture(items)}\n\n" + "\n".join(lines) + f"\n\nВсего: {total}/{MAX_BOUQUET_FLOWERS}"


def describe(bouquet: VirtualBouquet, viewer: User) -> str:
    """Подпись к картинке букета. Состав видно на картинке — здесь только дата, повод, открытка и реакция.

    Подпись к фото в Telegram — до 1024 символов; открытка ограничена CARD_MAX, так что влезает.
    """
    header = "💐 Букет от вас" if bouquet.sender_id == viewer.id else "🎁 Букет вам"
    lines = [f"<b>{header}</b> · {format_local_date(bouquet.created_at, viewer.timezone)}"]
    if bouquet.occasion:
        lines.append(OCCASION_LABELS[bouquet.occasion])
    if bouquet.card:
        lines.append(f"\n💌 <i>{escape(bouquet.card)}</i>")
    if bouquet.reaction:
        lines.append(f"\nРеакция: {REACTION_EMOJI[bouquet.reaction]}")
    return "\n".join(lines)


async def photo(bouquet: VirtualBouquet) -> str | BufferedInputFile:
    """Картинка для отправки: уже загруженная в Telegram или нарисованная заново."""
    if bouquet.tg_file_id:
        return bouquet.tg_file_id
    image = await render.render_bouquet(bouquet.items, bouquet.id, get_vase(bouquet.vase))
    return BufferedInputFile(image, "bouquet.jpg")


def sent_file_id(message: Message) -> str | None:
    """file_id отправленной картинки — чтобы в следующий раз не рисовать."""
    return message.photo[-1].file_id if message.photo else None


async def send_bouquet(bot: Bot, bouquet: VirtualBouquet, sender: User, recipient: User) -> str | None:
    """Получателю: тебе собрали букет — и просьба отреагировать. Возвращает file_id картинки."""
    # Букет уже сохранён — ошибка отправки (например, бот заблокирован) не должна его откатывать
    try:
        message = await bot.send_photo(
            recipient.id,
            await photo(bouquet),
            caption=f"🌸 {escape(sender.first_name)} собрал(а) для вас букет\n\n{describe(bouquet, recipient)}"
            "\n\nКак вам?",
            reply_markup=reaction_keyboard(bouquet.id),
        )
    except TelegramAPIError:
        logger.exception("Не удалось отправить виртуальный букет %s пользователю %s", bouquet.id, recipient.id)
        return None
    return sent_file_id(message)


async def send_reaction(bot: Bot, bouquet: VirtualBouquet, sender: User, recipient: User) -> None:
    """Отправителю: как получатель отреагировал на букет."""
    if bouquet.reaction is None:
        return
    picture = emoji_picture(bouquet.items)
    text = f"{REACTION_EMOJI[bouquet.reaction]} {escape(recipient.first_name)} — о вашем букете {picture}"
    try:
        _ = await bot.send_message(sender.id, text)
    except TelegramAPIError:
        logger.exception("Не удалось отправить реакцию на букет %s пользователю %s", bouquet.id, sender.id)
