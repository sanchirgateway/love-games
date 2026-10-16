"""Уведомления об играх в Telegram. Используются и из бота, и из API."""

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from app.core import storage
from app.core.time import format_local_date
from app.feature.games.keyboards import MOOD_EMOJI, review_request_keyboard
from app.feature.games.models import Game, GameSession, GameSessionReview
from app.feature.user.models import User

logger = logging.getLogger(__name__)


def describe_review(review: GameSessionReview, max_field_length: int | None = None) -> str:
    """Текст отзыва. max_field_length обрезает поля, когда несколько отзывов идут в одном сообщении."""

    def field(value: str) -> str:
        if max_field_length is not None and len(value) > max_field_length:
            value = value[:max_field_length].rstrip() + "…"
        return escape(value)

    stars = "⭐" * review.rating + "☆" * (5 - review.rating)
    lines = [f"{stars} {MOOD_EMOJI[review.mood]}" if review.mood else stars]
    if review.liked:
        lines.append(f"👍 {field(review.liked)}")
    if review.disliked:
        lines.append(f"👎 {field(review.disliked)}")
    if review.comment:
        lines.append(f"\n{field(review.comment)}")
    return "\n".join(lines)


def describe_session(game_session: GameSession, game: Game, viewer: User) -> str:
    lines = [f"🎮 <b>{escape(game.title)}</b>", f"📅 {format_local_date(game_session.played_at, viewer.timezone)}"]
    if game_session.description:
        lines.append(f"\n{escape(game_session.description)}")
    return "\n".join(lines)


async def send_review_request(bot: Bot, game_session: GameSession, game: Game, author: User, partner: User) -> None:
    """Партнёру того, кто записал вечер: поделись впечатлениями."""
    text = (
        f"🎮 {escape(author.first_name)} записал(а) ваш вечер в «{escape(game.title)}»\n\n"
        f"{describe_session(game_session, game, partner)}\n\nКак вам? Поделитесь впечатлениями"
    )
    await _safe_send(bot, partner.id, text, review_request_keyboard(game_session.id))


async def announce_review(
    bot: Bot,
    review: GameSessionReview,
    reviews: list[GameSessionReview],
    game: Game,
    author: User,
    partner: User,
    locked: bool,
) -> None:
    """Рассылает новый отзыв партнёру автора: сам отзыв или, если он ему пока скрыт (locked), только факт.
    Если партнёр уже оставил свой, его отзыв теперь открывается автору.
    """
    if locked:
        text = (
            f"💬 {escape(author.first_name)} поделился(ась) впечатлениями о вечере в «{escape(game.title)}»\n\n"
            "🔒 Напишите свои — и отзывы откроются вам обоим"
        )
        await _safe_send(bot, partner.id, text, review_request_keyboard(review.session_id))
    else:
        text = f"💬 {escape(author.first_name)} о вечере в «{escape(game.title)}»\n\n{describe_review(review)}"
        await _safe_send(bot, partner.id, text)

    partner_review = next((other for other in reviews if other.author_id != review.author_id), None)
    if partner_review is not None:
        text = f"💬 {escape(partner.first_name)} о вечере в «{escape(game.title)}»\n\n{describe_review(partner_review)}"
        await _safe_send(bot, author.id, text)


async def send_cover(bot: Bot, chat_id: int, game: Game) -> None:
    if game.cover_key is None:
        return
    caption = f"🖼 {escape(game.title)}"
    # По file_id Telegram отправляет мгновенно; у обложек из Mini App его нет — берём из хранилища
    if game.cover_tg_file_id:
        try:
            _ = await bot.send_photo(chat_id, game.cover_tg_file_id, caption=caption)
            return
        except TelegramBadRequest:
            logger.warning("file_id обложки игры %s недоступен, отправляю из хранилища", game.id)
    photo = BufferedInputFile(await storage.download(game.cover_key), filename="cover.jpg")
    _ = await bot.send_photo(chat_id, photo, caption=caption)


async def _safe_send(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    # Данные уже сохранены — ошибка отправки (например, бот заблокирован) не должна их откатывать
    try:
        _ = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.exception("Не удалось отправить уведомление об игре пользователю %s", chat_id)
