"""Уведомления об отзывах в Telegram."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto
from aiogram.types.media_union import MediaUnion

from app.core import storage
from app.feature.dates.models import DateEvent
from app.feature.reviews.keyboards import review_request_keyboard
from app.feature.reviews.models import DateReview
from app.feature.user.models import User

logger = logging.getLogger(__name__)


def describe(review: DateReview, max_field_length: int | None = None) -> str:
    """Текст отзыва. max_field_length обрезает поля, когда несколько отзывов идут в одном сообщении."""

    def field(value: str) -> str:
        if max_field_length is not None and len(value) > max_field_length:
            value = value[:max_field_length].rstrip() + "…"
        return escape(value)

    lines = ["⭐" * review.rating + "☆" * (5 - review.rating)]
    if review.liked:
        lines.append(f"👍 {field(review.liked)}")
    if review.disliked:
        lines.append(f"👎 {field(review.disliked)}")
    if review.food:
        lines.append(f"🍽 {field(review.food)}")
    if review.comment:
        lines.append(f"\n{field(review.comment)}")
    return "\n".join(lines)


async def send_review_request(bot: Bot, date: DateEvent) -> None:
    """Просит обоих участников оставить отзыв о состоявшемся свидании."""
    text = f"💭 Как прошло свидание «{escape(date.title)}»? Поделитесь впечатлениями"
    for user in (date.creator, date.invitee):
        await _ask_review(bot, date, user, text)


async def send_marked_done(bot: Bot, date: DateEvent, author: User, partner: User) -> None:
    """Сообщает партнёру, что author отметил свидание состоявшимся, и просит отзыв."""
    text = (
        f"💞 {escape(author.first_name)} отметил(а), что свидание «{escape(date.title)}» состоялось\n\n"
        "Как вам? Поделитесь впечатлениями"
    )
    await _ask_review(bot, date, partner, text)


async def send_review_teaser(bot: Bot, review: DateReview, date: DateEvent) -> None:
    """Сообщает партнёру, что отзыв есть, но не показывает его: откроется, когда партнёр напишет свой."""
    author, partner = (date.creator, date.invitee) if review.author_id == date.created_by else (date.invitee, date.creator)
    text = (
        f"💬 {escape(author.first_name)} оставил(а) отзыв о свидании «{escape(date.title)}»\n\n"
        "🔒 Напишите свой — и отзывы откроются вам обоим"
    )
    await _ask_review(bot, date, partner, text)


async def send_review_reminder(bot: Bot, date: DateEvent, user: User) -> None:
    text = (
        f"🙂 Вы ещё не рассказали, как прошло свидание «{escape(date.title)}»\n\n"
        "Если найдётся минутка — пара слов и пара фото, и воспоминание останется с вами"
    )
    await _ask_review(bot, date, user, text)


async def _ask_review(bot: Bot, date: DateEvent, user: User, text: str) -> None:
    # Просьба не критична: ошибка отправки (например, бот заблокирован) не должна мешать остальным
    try:
        _ = await bot.send_message(user.id, text, reply_markup=review_request_keyboard(date.id))
    except TelegramAPIError:
        logger.exception("Не удалось попросить отзыв о свидании %s у пользователя %s", date.id, user.id)


async def send_review(bot: Bot, review: DateReview, date: DateEvent) -> None:
    """Показывает отзыв партнёру автора."""
    author, partner = (date.creator, date.invitee) if review.author_id == date.created_by else (date.invitee, date.creator)
    text = (
        f"💬 {escape(author.first_name)} оставил(а) отзыв о свидании «{escape(date.title)}»\n\n{describe(review)}"
    )
    # Отзыв уже сохранён — ошибка отправки (например, бот заблокирован) не должна его откатывать
    try:
        _ = await bot.send_message(partner.id, text)
        await send_photos(bot, partner.id, review)
    except TelegramAPIError:
        logger.exception("Не удалось отправить отзыв %s пользователю %s", review.id, partner.id)


async def send_photos(bot: Bot, chat_id: int, review: DateReview, caption: str | None = None) -> None:
    """Отправляет фото отзыва альбомом. Подпись (HTML) ставится на первое фото."""
    if not review.photos:
        return
    try:
        # По file_id Telegram отправляет мгновенно, без скачивания из хранилища
        files: list[str | BufferedInputFile] = [p.tg_file_id for p in review.photos]
        _ = await bot.send_media_group(chat_id, _album(files, caption))
    except TelegramBadRequest:
        # file_id перестал работать (например, сменился бот) — берём оригиналы из хранилища
        logger.warning("file_id фото отзыва %s недоступны, отправляю из хранилища", review.id)
        files = [BufferedInputFile(await storage.download(p.key), filename=f"{p.id}.jpg") for p in review.photos]
        _ = await bot.send_media_group(chat_id, _album(files, caption))


def _album(files: list[str | BufferedInputFile], caption: str | None) -> list[MediaUnion]:
    return [InputMediaPhoto(media=file, caption=caption if i == 0 else None) for i, file in enumerate(files)]
