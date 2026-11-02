from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.feature.ideas.models import DateIdea


class IdeaMenu(CallbackData, prefix="idea_menu"):
    pass


class IdeaNext(CallbackData, prefix="idea_next"):
    """Следующая идея из колоды."""


class IdeaAnswer(CallbackData, prefix="idea_answer"):
    idea_id: UUID
    yes: bool


class IdeaNew(CallbackData, prefix="idea_new"):
    pass


class IdeaMatches(CallbackData, prefix="idea_matches"):
    pass


class IdeaMine(CallbackData, prefix="idea_mine"):
    pass


class IdeaOpen(CallbackData, prefix="idea_open"):
    idea_id: UUID


class IdeaPlan(CallbackData, prefix="idea_plan"):
    idea_id: UUID


class IdeaDelete(CallbackData, prefix="idea_delete"):
    idea_id: UUID


def _button(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def menu_keyboard(matches: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🃏 Листать идеи", IdeaNext())],
            [_button(f"💞 Совпадения ({matches})", IdeaMatches())],
            [_button("➕ Своя идея", IdeaNew()), _button("📝 Мои идеи", IdeaMine())],
        ]
    )


def back_button() -> InlineKeyboardButton:
    return _button("⬅️ К идеям", IdeaMenu())


def card_keyboard(idea_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("👎 Не хочу", IdeaAnswer(idea_id=idea_id, yes=False)),
                _button("👍 Хочу", IdeaAnswer(idea_id=idea_id, yes=True)),
            ],
            [back_button()],
        ]
    )


def deck_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("➕ Своя идея", IdeaNew())], [back_button()]])


def ideas_list_keyboard(ideas: list[DateIdea]) -> InlineKeyboardMarkup:
    rows = [[_button(f"💡 {idea.title}", IdeaOpen(idea_id=idea.id))] for idea in ideas]
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_button(idea_id: UUID) -> InlineKeyboardButton:
    return _button("📅 Назначить свидание", IdeaPlan(idea_id=idea_id))


def match_keyboard(idea_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[plan_button(idea_id)]])


def idea_detail_keyboard(idea: DateIdea, user_id: int, can_plan: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_plan:
        rows.append([plan_button(idea.id)])
    if idea.created_by == user_id:
        rows.append([_button("🗑 Удалить идею", IdeaDelete(idea_id=idea.id))])
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)
