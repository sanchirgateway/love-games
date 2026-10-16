from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.time import format_local_date
from app.feature.games.models import Game, GameMood, GameSession, GameStatus

MOOD_EMOJI = {
    GameMood.LOVED: "😍",
    GameMood.FUN: "😂",
    GameMood.ANGRY: "😤",
    GameMood.TIRED: "😴",
}

STATUS_LABELS = {
    GameStatus.PLAYING: ("🎮", "Проходим"),
    GameStatus.COMPLETED: ("🏆", "Прошли"),
    GameStatus.DROPPED: ("💤", "Бросили"),
}


class GameOpen(CallbackData, prefix="game_open"):
    game_id: UUID


class GameList(CallbackData, prefix="game_list"):
    pass


class GameNew(CallbackData, prefix="game_new"):
    log_after: bool  # после создания сразу записать вечер (из /played)


class GameSetStatus(CallbackData, prefix="game_status"):
    game_id: UUID
    status: GameStatus


class GameCover(CallbackData, prefix="game_cover"):
    game_id: UUID


class GameCoverSet(CallbackData, prefix="game_cover_set"):
    game_id: UUID


class PlayedPick(CallbackData, prefix="played_pick"):
    """Выбрана игра, в которую играли, — дальше спрашиваем, когда."""

    game_id: UUID


class PlayedWhen(CallbackData, prefix="played_when"):
    days_ago: int  # 0 — сегодня, 1 — вчера


class SessionOpen(CallbackData, prefix="gsession_open"):
    session_id: UUID


class SessionReview(CallbackData, prefix="gsession_review"):
    session_id: UUID


class GameReviewRating(CallbackData, prefix="greview_rating"):
    rating: int


class GameReviewMood(CallbackData, prefix="greview_mood"):
    mood: GameMood | None  # None — пропустить


def status_label(game: Game) -> tuple[str, str]:
    return STATUS_LABELS[game.status]


def pick_game_keyboard(games: list[Game]) -> InlineKeyboardMarkup:
    """Для /played: в какую игру играли."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{status_label(game)[0]} {game.title}", callback_data=PlayedPick(game_id=game.id).pack()
            )
        ]
        for game in games
    ]
    rows.append([InlineKeyboardButton(text="➕ Новая игра", callback_data=GameNew(log_after=True).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def when_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data=PlayedWhen(days_ago=0).pack()),
                InlineKeyboardButton(text="Вчера", callback_data=PlayedWhen(days_ago=1).pack()),
            ]
        ]
    )


def games_list_keyboard(games: list[Game]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{status_label(game)[0]} {game.title}", callback_data=GameOpen(game_id=game.id).pack()
            )
        ]
        for game in games
    ]
    rows.append([InlineKeyboardButton(text="➕ Новая игра", callback_data=GameNew(log_after=False).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_button_text(game_session: GameSession, tz: str, visible_moods: str) -> str:
    return f"📅 {format_local_date(game_session.played_at, tz)} {visible_moods}".rstrip()


def game_detail_keyboard(game: Game, sessions: list[tuple[GameSession, str]]) -> InlineKeyboardMarkup:
    """sessions — вечера с готовым текстом кнопки."""
    rows = [
        [InlineKeyboardButton(text=text, callback_data=SessionOpen(session_id=game_session.id).pack())]
        for game_session, text in sessions
    ]
    rows.append([InlineKeyboardButton(text="🎮 Записать вечер", callback_data=PlayedPick(game_id=game.id).pack())])
    status_buttons = [
        InlineKeyboardButton(text=f"{icon} {label}", callback_data=GameSetStatus(game_id=game.id, status=status).pack())
        for status, (icon, label) in STATUS_LABELS.items()
        if status != game.status
    ]
    rows.append(status_buttons)
    cover_row = [
        InlineKeyboardButton(
            text="🖼 Сменить обложку" if game.has_cover else "🖼 Добавить обложку",
            callback_data=GameCoverSet(game_id=game.id).pack(),
        )
    ]
    if game.has_cover:
        cover_row.insert(0, InlineKeyboardButton(text="🖼 Обложка", callback_data=GameCover(game_id=game.id).pack()))
    rows.append(cover_row)
    rows.append([InlineKeyboardButton(text="← Все игры", callback_data=GameList().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_detail_keyboard(game_session: GameSession, can_review: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_review:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✍️ Оставить отзыв", callback_data=SessionReview(session_id=game_session.id).pack()
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← К игре", callback_data=GameOpen(game_id=game_session.game_id).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_request_keyboard(session_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Поделиться впечатлениями", callback_data=SessionReview(session_id=session_id).pack()
                )
            ]
        ]
    )


def rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{n}⭐", callback_data=GameReviewRating(rating=n).pack()) for n in range(1, 6)]
        ]
    )


def mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=emoji, callback_data=GameReviewMood(mood=mood).pack())
                for mood, emoji in MOOD_EMOJI.items()
            ],
            [InlineKeyboardButton(text="Пропустить", callback_data=GameReviewMood(mood=None).pack())],
        ]
    )
