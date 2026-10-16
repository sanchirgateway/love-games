"""Уведомления об отзывах в Telegram."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.types.media_union import MediaUnion

from app.core import storage
from app.feature.dates.models import DateEvent
from app.feature.reviews.keyboards import review_request_keyboard
from app.feature.reviews.models import DateReview, DateReviewPhoto
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


async def announce_review(
    bot: Bot, review: DateReview, date: DateEvent, reviews: list[DateReview], locked: bool
) -> None:
    """Рассылает новый отзыв. Партнёру автора — сам отзыв или, если он ему ещё скрыт (locked), только факт.
    Если партнёр уже оставил свой, его отзыв теперь открывается автору.
    """
    if locked:
        await send_review_teaser(bot, review, date)
    else:
        await send_review(bot, review, date)
    partner_review = next((other for other in reviews if other.author_id != review.author_id), None)
    if partner_review is not None:
        await send_review(bot, partner_review, date)


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


def media_summary(photos: list[DateReviewPhoto]) -> str:
    """«3 фото и 1 видео» — для подписей в карточке свидания."""
    videos = sum(1 for p in photos if p.is_video)
    parts = [f"{len(photos) - videos} фото" if len(photos) > videos else "", f"{videos} видео" if videos else ""]
    return " и ".join(part for part in parts if part)


async def send_photos(bot: Bot, chat_id: int, review: DateReview, caption: str | None = None) -> None:
    """Отправляет фото и видео отзыва одним альбомом. Подпись (HTML) ставится на первый файл."""
    if not review.photos:
        return
    # По file_id Telegram отправляет мгновенно, без скачивания из хранилища.
    # У файлов, загруженных через Mini App, file_id нет — их сразу берём из хранилища
    file_ids = [p.tg_file_id for p in review.photos if p.tg_file_id]
    if len(file_ids) == len(review.photos):
        try:
            _ = await bot.send_media_group(chat_id, _album(review.photos, list(file_ids), caption))
            return
        except TelegramBadRequest:
            # file_id перестал работать (например, сменился бот) — берём оригиналы из хранилища
            logger.warning("file_id медиа отзыва %s недоступны, отправляю из хранилища", review.id)
    files: list[str | BufferedInputFile] = [
        BufferedInputFile(await storage.download(p.key), filename=p.key.rsplit("/", 1)[-1]) for p in review.photos
    ]
    _ = await bot.send_media_group(chat_id, _album(review.photos, files, caption))


def _album(
    photos: list[DateReviewPhoto], files: list[str | BufferedInputFile], caption: str | None
) -> list[MediaUnion]:
    # Фото и видео Telegram разрешает смешивать в одном альбоме
    album: list[MediaUnion] = []
    for i, (photo, file) in enumerate(zip(photos, files, strict=True)):
        file_caption = caption if i == 0 else None
        if photo.is_video:
            album.append(InputMediaVideo(media=file, caption=file_caption, supports_streaming=True))
        else:
            album.append(InputMediaPhoto(media=file, caption=file_caption))
    return album
