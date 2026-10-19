"""Уведомления о цветах в Telegram. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto
from aiogram.types.media_union import MediaUnion

from app.core import storage
from app.core.time import format_local_date
from app.feature.flowers.keyboards import OCCASION_LABELS, REACTION_EMOJI, received_keyboard
from app.feature.flowers.models import FlowerGift, FlowerGiftPhoto
from app.feature.user.models import User

logger = logging.getLogger(__name__)


def describe(gift: FlowerGift, viewer: User) -> str:
    """Карточка букета. Цену видит только даритель."""
    lines = [f"💐 <b>{escape(gift.flowers)}</b>"]
    if gift.given_at is not None:
        lines.append(f"📅 {format_local_date(gift.given_at, viewer.timezone)}")
    else:
        lines.append("🤫 Ещё не вручён — партнёр не видит эту запись")
    if gift.occasion:
        lines.append(OCCASION_LABELS[gift.occasion])
    if gift.price is not None and gift.giver_id == viewer.id:
        lines.append(f"💸 {gift.price:,} ₽ (видно только вам)".replace(",", " "))
    if gift.comment:
        lines.append(f"\n{escape(gift.comment)}")
    if gift.reaction:
        lines.append(f"\nРеакция: {REACTION_EMOJI[gift.reaction]}")
    return "\n".join(lines)


async def send_gift(bot: Bot, gift: FlowerGift, giver: User, recipient: User) -> None:
    """Получателю: тебе подарили цветы — фото альбомом и просьба отреагировать."""
    # Запись уже сохранена — ошибка отправки (например, бот заблокирован) не должна её откатывать
    try:
        await send_photos(bot, recipient.id, gift, gift.photos_by(giver.id))
        _ = await bot.send_message(
            recipient.id,
            f"💐 {escape(giver.first_name)} подарил(а) вам цветы\n\n{describe(gift, recipient)}\n\n"
            "Как вам? А когда поставите в вазу — пришлите фото 📷",
            reply_markup=received_keyboard(gift.id),
        )
    except TelegramAPIError:
        logger.exception("Не удалось отправить букет %s пользователю %s", gift.id, recipient.id)


async def send_reaction(bot: Bot, gift: FlowerGift, giver: User, recipient: User) -> None:
    """Дарителю: как получатель отреагировал на букет."""
    if gift.reaction is None:
        return
    text = f"{REACTION_EMOJI[gift.reaction]} {escape(recipient.first_name)} — о букете «{escape(gift.flowers)}»"
    try:
        _ = await bot.send_message(giver.id, text)
    except TelegramAPIError:
        logger.exception("Не удалось отправить реакцию на букет %s пользователю %s", gift.id, giver.id)


async def send_added_photos(
    bot: Bot, gift: FlowerGift, photos: list[FlowerGiftPhoto], author: User, other: User
) -> None:
    """Второму участнику: author дослал фото к букету (например, букет в вазе)."""
    if not gift.is_given:
        return  # невручённый букет получателю не показываем — сюрприз
    caption = f"📷 {escape(author.first_name)} прислал(а) фото букета «{escape(gift.flowers)}»"
    try:
        await send_photos(bot, other.id, gift, photos, caption)
    except TelegramAPIError:
        logger.exception("Не удалось отправить новые фото букета %s пользователю %s", gift.id, other.id)


async def send_all_photos(bot: Bot, chat_id: int, gift: FlowerGift, giver: User, recipient: User) -> None:
    """Все фото букета: отдельно альбом дарителя и альбом получателя."""
    for author in (giver, recipient):
        photos = gift.photos_by(author.id)
        if photos:
            await send_photos(bot, chat_id, gift, photos, f"📷 Фото от {escape(author.first_name)}")


async def send_photos(
    bot: Bot, chat_id: int, gift: FlowerGift, photos: list[FlowerGiftPhoto], caption: str | None = None
) -> None:
    """Фото одним альбомом. Подпись (HTML) ставится на первое фото."""
    if not photos:
        return
    # По file_id Telegram отправляет мгновенно; у фото из Mini App его нет — берём из хранилища
    file_ids = [p.tg_file_id for p in photos if p.tg_file_id]
    if len(file_ids) == len(photos):
        try:
            await _send_album(bot, chat_id, list(file_ids), caption)
            return
        except TelegramBadRequest:
            logger.warning("file_id фото букета %s недоступны, отправляю из хранилища", gift.id)
    files: list[str | BufferedInputFile] = [
        BufferedInputFile(await storage.download(p.key), filename=p.key.rsplit("/", 1)[-1]) for p in photos
    ]
    await _send_album(bot, chat_id, files, caption)


async def _send_album(bot: Bot, chat_id: int, files: list[str | BufferedInputFile], caption: str | None) -> None:
    # Альбом в Telegram — от 2 файлов, одно фото отправляется обычным сообщением
    if len(files) == 1:
        _ = await bot.send_photo(chat_id, files[0], caption=caption)
        return
    album: list[MediaUnion] = [
        InputMediaPhoto(media=file, caption=caption if i == 0 else None) for i, file in enumerate(files)
    ]
    _ = await bot.send_media_group(chat_id, album)
