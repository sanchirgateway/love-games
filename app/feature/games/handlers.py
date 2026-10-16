from datetime import UTC, datetime, timedelta
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import format_local, local_day_start, parse_local_date
from app.feature.games import notify
from app.feature.games.keyboards import (
    MOOD_EMOJI,
    GameCover,
    GameCoverSet,
    GameList,
    GameNew,
    GameOpen,
    GameReviewMood,
    GameReviewRating,
    GameSetStatus,
    PlayedPick,
    PlayedWhen,
    SessionOpen,
    SessionReview,
    game_detail_keyboard,
    games_list_keyboard,
    mood_keyboard,
    pick_game_keyboard,
    rating_keyboard,
    session_button_text,
    session_detail_keyboard,
    status_label,
    when_keyboard,
)
from app.feature.games.models import Game, GameMood, GameSession
from app.feature.games.service import (
    TEXT_MAX,
    TITLE_MAX,
    GameService,
    can_review,
    can_see_review,
    reviews_reveal_at,
)
from app.feature.user.service import UserService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")

SKIP_HINT = "Напишите ответ или «-», чтобы пропустить"
SESSIONS_IN_CARD = 10
REVIEW_FIELD_PREVIEW = 300  # в карточке вечера длинные отзывы обрезаем, чтобы влезть в лимит сообщения


class NewGame(StatesGroup):
    title = State()
    description = State()
    cover = State()


class LogSession(StatesGroup):
    when = State()
    description = State()


class GameReviewForm(StatesGroup):
    rating = State()
    mood = State()
    liked = State()
    disliked = State()
    comment = State()


class SetCover(StatesGroup):
    photo = State()


def _skip(text: str | None, limit: int = TEXT_MAX) -> str | None:
    """«-» — пропустить шаг."""
    text = (text or "").strip()
    return None if text == "-" else text[:limit]


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=reply_markup)


# --- /played: записать вечер ---


@router.message(Command("played"))
async def cmd_played(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    service = GameService(session)
    _ = await service.couple(message.from_user.id)  # AppError, если пары нет
    await state.clear()
    games = await service.list_games(message.from_user.id)
    if not games:
        await state.set_state(NewGame.title)
        await state.update_data(log_after=True)
        await message.answer("Записываем игровой вечер 🎮\n\nВо что играли? Напишите название\n\n/cancel — отменить")
        return
    await message.answer("Во что играли? 🎮", reply_markup=pick_game_keyboard(games))


@router.callback_query(GameNew.filter())
async def new_game_start(callback: CallbackQuery, callback_data: GameNew, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewGame.title)
    await state.update_data(log_after=callback_data.log_after)
    await _edit_or_answer(callback, "Новая игра 🎮\n\nКак называется?\n\n/cancel — отменить")
    _ = await callback.answer()


@router.message(NewGame.title, plain_text)
async def new_game_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:TITLE_MAX])
    await state.set_state(NewGame.description)
    await message.answer(f"Пара слов об игре?\n\n{SKIP_HINT}")


@router.message(NewGame.description, plain_text)
async def new_game_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=_skip(message.text))
    await state.set_state(NewGame.cover)
    await message.answer("Пришлите обложку игры картинкой или «-», чтобы пропустить")


@router.message(NewGame.cover, F.photo | (plain_text & (F.text.strip() == "-")))
async def new_game_cover(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    service = GameService(session)
    game = await service.create_game(message.from_user.id, str(data["title"]), data.get("description"))
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await bot.download(file_id)
        if file is not None:
            game = await service.set_cover(game.id, message.from_user.id, file.read(), tg_file_id=file_id)

    if data.get("log_after"):
        await _ask_when(message, state, game)
        return
    await state.clear()
    text, keyboard = await _game_card(session, game, message.from_user.id)
    await message.answer(f"Добавил игру ✅\n\n{text}", reply_markup=keyboard)


@router.message(NewGame.cover)
async def new_game_cover_other(message: Message) -> None:
    await message.answer("Пришлите картинку (как фото, не файлом) или «-», чтобы пропустить")


async def _ask_when(message: Message, state: FSMContext, game: Game) -> None:
    await state.clear()
    await state.set_state(LogSession.when)
    await state.update_data(game_id=str(game.id))
    await message.answer(
        f"«{escape(game.title)}» — когда играли?\n\nНажмите кнопку или напишите дату: <code>12.10</code>",
        reply_markup=when_keyboard(),
    )


@router.callback_query(PlayedPick.filter())
async def played_pick(
    callback: CallbackQuery, callback_data: PlayedPick, state: FSMContext, session: AsyncSession
) -> None:
    game = await GameService(session).get_game(callback_data.game_id, callback.from_user.id)
    _ = await callback.answer()
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        await _ask_when(callback.message, state, game)


async def _save_when(state: FSMContext, played_at: datetime, reply: Message) -> None:
    await state.update_data(played_at=played_at.isoformat())
    await state.set_state(LogSession.description)
    await reply.answer(f"Что успели за вечер? Например: «прошли первый остров»\n\n{SKIP_HINT}")


def _played_at(day_start: datetime, tz: str) -> datetime:
    """Сегодня — текущий момент; другой день — его полдень: так дата не съедет у партнёра в другом часовом поясе."""
    if day_start.date() == datetime.now(ZoneInfo(tz)).date():
        return datetime.now(UTC)
    return day_start + timedelta(hours=12)


@router.callback_query(LogSession.when, PlayedWhen.filter())
async def played_when_button(
    callback: CallbackQuery, callback_data: PlayedWhen, state: FSMContext, session: AsyncSession
) -> None:
    user = await UserService(session).get(callback.from_user.id)
    day = datetime.now(ZoneInfo(user.timezone)).date() - timedelta(days=callback_data.days_ago)
    _ = await callback.answer()
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_reply_markup(reply_markup=None)
        await _save_when(state, _played_at(local_day_start(day, user.timezone), user.timezone), callback.message)


@router.message(LogSession.when, plain_text)
async def played_when_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService(session).get(message.from_user.id)
    day = parse_local_date(message.text or "", user.timezone)
    if day is None:
        await message.answer("Не понял дату 🤔 Формат: <code>12.10</code> или <code>12.10.2026</code>")
        return
    if day > datetime.now(ZoneInfo(user.timezone)).date():
        await message.answer("Этот день ещё не наступил 🙂 Укажите прошедший")
        return
    await _save_when(state, _played_at(local_day_start(day, user.timezone), user.timezone), message)


@router.message(LogSession.description, plain_text)
async def played_description(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    await state.clear()

    service = GameService(session)
    game_session = await service.log_session(
        game_id=UUID(str(data["game_id"])),
        user_id=message.from_user.id,
        played_at=datetime.fromisoformat(str(data["played_at"])),
        description=_skip(message.text),
    )
    author, partner = await service.couple(message.from_user.id)
    await notify.send_review_request(bot, game_session, game_session.game, author, partner)

    # Сразу предлагаем автору оставить свой отзыв — пока впечатления свежие
    await state.set_state(GameReviewForm.rating)
    await state.update_data(session_id=str(game_session.id))
    await message.answer(
        f"Записал вечер ✅ {escape(partner.first_name)} попрошу поделиться впечатлениями\n\n"
        f"{notify.describe_session(game_session, game_session.game, author)}\n\n"
        "А вам как? Оцените вечер\n\n/cancel — без отзыва",
        reply_markup=rating_keyboard(),
    )


# --- Отзыв о вечере ---

# Текстовые шаги: состояние -> (поле отзыва, следующее состояние, вопрос для следующего шага)
TEXT_STEPS: dict[str | None, tuple[str, State | None, str]] = {
    GameReviewForm.liked.state: ("liked", GameReviewForm.disliked, "Что не понравилось?"),
    GameReviewForm.disliked.state: ("disliked", GameReviewForm.comment, "Что-нибудь ещё? Общие впечатления"),
    GameReviewForm.comment.state: ("comment", None, ""),
}


@router.callback_query(SessionReview.filter())
async def review_start(
    callback: CallbackQuery, callback_data: SessionReview, state: FSMContext, session: AsyncSession
) -> None:
    game_session = await GameService(session).check_can_review(callback_data.session_id, callback.from_user.id)
    await state.clear()
    await state.set_state(GameReviewForm.rating)
    await state.update_data(session_id=str(game_session.id))
    _ = await callback.answer()
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.answer(
            f"Впечатления о вечере в «{escape(game_session.game.title)}»\n\nКак оцените?\n\n/cancel — отменить",
            reply_markup=rating_keyboard(),
        )


@router.callback_query(GameReviewForm.rating, GameReviewRating.filter())
async def review_rating(callback: CallbackQuery, callback_data: GameReviewRating, state: FSMContext) -> None:
    await state.update_data(rating=callback_data.rating)
    await state.set_state(GameReviewForm.mood)
    await _edit_or_answer(callback, f"Оценка: {'⭐' * callback_data.rating}")
    if callback.message is not None:
        _ = await callback.message.answer("Какие эмоции после вечера?", reply_markup=mood_keyboard())
    _ = await callback.answer()


@router.callback_query(GameReviewForm.mood, GameReviewMood.filter())
async def review_mood(callback: CallbackQuery, callback_data: GameReviewMood, state: FSMContext) -> None:
    mood = callback_data.mood
    await state.update_data(mood=mood.value if mood else None)
    await state.set_state(GameReviewForm.liked)
    await _edit_or_answer(callback, f"Эмоция: {MOOD_EMOJI[mood]}" if mood else "Эмоция: пропущено")
    if callback.message is not None:
        _ = await callback.message.answer(f"Что понравилось?\n\n{SKIP_HINT}")
    _ = await callback.answer()


@router.message(StateFilter(*(state for state in TEXT_STEPS if state is not None)), plain_text)
async def review_text(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    field, next_state, question = TEXT_STEPS[await state.get_state()]
    await state.update_data({field: _skip(message.text)})
    if next_state is not None:
        await state.set_state(next_state)
        await message.answer(f"{question}\n\n{SKIP_HINT}")
        return
    await _save_review(message, state, session, bot)


async def _save_review(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    service = GameService(session)
    review = await service.create_review(
        session_id=UUID(str(data["session_id"])),
        author_id=message.from_user.id,
        rating=int(data["rating"]),
        mood=GameMood(data["mood"]) if data.get("mood") else None,
        liked=data.get("liked"),
        disliked=data.get("disliked"),
        comment=data.get("comment"),
    )
    # Состояние чистим только после сохранения: если что-то упало, можно ответить ещё раз
    await state.clear()

    game_session = await service.get_session(review.session_id, message.from_user.id)
    reviews = await service.list_reviews(game_session.id)
    author, partner = await service.couple(message.from_user.id)
    locked = not can_see_review(game_session, reviews, review, partner.id)
    if locked:
        note = f"🔒 {escape(partner.first_name)} увидит его, когда поделится своими — тогда откроется и отзыв для вас"
    else:
        note = f"Отправил {escape(partner.first_name)}"
    await message.answer(f"Спасибо! Сохранил 💝\n\n{notify.describe_review(review)}\n\n{note}")
    await notify.announce_review(bot, review, reviews, game_session.game, author, partner, locked)


# --- /games: каталог игр ---


async def _games_list(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    games = await GameService(session).list_games(user_id)
    if not games:
        return "У вас пока нет игр. Добавьте первую или запишите вечер: /played", games_list_keyboard([])
    return "Ваши игры:", games_list_keyboard(games)


@router.message(Command("games"))
async def cmd_games(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text, keyboard = await _games_list(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(GameList.filter())
async def back_to_games(callback: CallbackQuery, session: AsyncSession) -> None:
    text, keyboard = await _games_list(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


def _session_marks(game_session: GameSession, user_id: int) -> str:
    """Эмоции и оценки к кнопке вечера: видимые отзывы — эмодзи (или звёзды), скрытые — замок."""
    marks: list[str] = []
    for review in game_session.reviews:
        if not can_see_review(game_session, game_session.reviews, review, user_id):
            marks.append("🔒")
        elif review.mood:
            marks.append(MOOD_EMOJI[review.mood])
        else:
            marks.append(f"{review.rating}⭐")
    return " ".join(marks)


async def _game_card(session: AsyncSession, game: Game, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    service = GameService(session)
    sessions = await service.list_sessions(game.id, user_id)
    user = await UserService(session).get(user_id)

    icon, label = status_label(game)
    parts = [f"🎮 <b>{escape(game.title)}</b>", f"{icon} {label}"]
    if game.description:
        parts.append(escape(game.description))
    if sessions:
        more = f" (последние {SESSIONS_IN_CARD})" if len(sessions) > SESSIONS_IN_CARD else ""
        parts.append(f"Вечеров: {len(sessions)}{more}")
    else:
        parts.append("Вечеров пока нет")

    buttons = [
        (game_session, session_button_text(game_session, user.timezone, _session_marks(game_session, user_id)))
        for game_session in sessions[:SESSIONS_IN_CARD]
    ]
    return "\n\n".join(parts), game_detail_keyboard(game, buttons)


@router.callback_query(GameOpen.filter())
async def open_game(callback: CallbackQuery, callback_data: GameOpen, session: AsyncSession) -> None:
    game = await GameService(session).get_game(callback_data.game_id, callback.from_user.id)
    text, keyboard = await _game_card(session, game, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


@router.callback_query(GameSetStatus.filter())
async def set_status(callback: CallbackQuery, callback_data: GameSetStatus, session: AsyncSession) -> None:
    game = await GameService(session).update_game(
        callback_data.game_id, callback.from_user.id, status=callback_data.status
    )
    text, keyboard = await _game_card(session, game, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    icon, label = status_label(game)
    _ = await callback.answer(f"{icon} {label}")


@router.callback_query(GameCover.filter())
async def show_cover(callback: CallbackQuery, callback_data: GameCover, session: AsyncSession, bot: Bot) -> None:
    game = await GameService(session).get_cover(callback_data.game_id, callback.from_user.id)
    _ = await callback.answer()
    await notify.send_cover(bot, callback.from_user.id, game)


@router.callback_query(GameCoverSet.filter())
async def set_cover_start(
    callback: CallbackQuery, callback_data: GameCoverSet, state: FSMContext, session: AsyncSession
) -> None:
    game = await GameService(session).get_game(callback_data.game_id, callback.from_user.id)
    await state.clear()
    await state.set_state(SetCover.photo)
    await state.update_data(game_id=str(game.id))
    _ = await callback.answer()
    if callback.message is not None:
        _ = await callback.message.answer(
            f"Пришлите обложку для «{escape(game.title)}» картинкой\n\n/cancel — отменить"
        )


@router.message(SetCover.photo, F.photo)
async def set_cover_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None or not message.photo:
        return
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    file = await bot.download(file_id)
    if file is None:
        await message.answer("Не получилось скачать картинку, попробуйте ещё раз")
        return
    game = await GameService(session).set_cover(
        UUID(str(data["game_id"])), message.from_user.id, file.read(), tg_file_id=file_id
    )
    await state.clear()
    text, keyboard = await _game_card(session, game, message.from_user.id)
    await message.answer(f"Обложка обновлена 🖼\n\n{text}", reply_markup=keyboard)


@router.message(SetCover.photo)
async def set_cover_other(message: Message) -> None:
    await message.answer("Пришлите картинку (как фото, не файлом) или /cancel")


@router.callback_query(SessionOpen.filter())
async def open_session(callback: CallbackQuery, callback_data: SessionOpen, session: AsyncSession) -> None:
    user_id = callback.from_user.id
    service = GameService(session)
    game_session = await service.get_session(callback_data.session_id, user_id)
    reviews = await service.list_reviews(game_session.id)
    viewer, partner = await service.couple(user_id)

    parts = [notify.describe_session(game_session, game_session.game, viewer)]
    for review in reviews:
        mine = review.author_id == user_id
        if not can_see_review(game_session, reviews, review, user_id):
            reveal_at = format_local(reviews_reveal_at(game_session), viewer.timezone)
            parts.append(
                f"<b>🔒 Отзыв от {escape(partner.first_name)}</b>\nОткроется, когда оставите свой, или {reveal_at}"
            )
            continue
        title = "Ваш отзыв" if mine else f"Отзыв от {escape(partner.first_name)}"
        parts.append(f"<b>{title}</b>\n{notify.describe_review(review, REVIEW_FIELD_PREVIEW)}")

    keyboard = session_detail_keyboard(game_session, can_review(reviews, user_id))
    await _edit_or_answer(callback, "\n\n".join(parts), keyboard)
    _ = await callback.answer()
