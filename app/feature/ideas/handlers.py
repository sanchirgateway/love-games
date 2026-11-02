from datetime import UTC, datetime
from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import parse_local_datetime
from app.feature.dates import notify as dates_notify
from app.feature.ideas import notify
from app.feature.ideas.keyboards import (
    IdeaAnswer,
    IdeaDelete,
    IdeaMatches,
    IdeaMenu,
    IdeaMine,
    IdeaNew,
    IdeaNext,
    IdeaOpen,
    IdeaPlan,
    card_keyboard,
    deck_empty_keyboard,
    idea_detail_keyboard,
    ideas_list_keyboard,
    menu_keyboard,
)
from app.feature.ideas.models import IdeaVote
from app.feature.ideas.service import PLACE_MAX, TEXT_MAX, TITLE_MAX, IdeaService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")


class NewIdea(StatesGroup):
    title = State()
    description = State()
    place = State()


class PlanIdea(StatesGroup):
    starts_at = State()
    place = State()


def _skip(text: str | None, limit: int) -> str | None:
    """«-» — пропустить шаг."""
    text = (text or "").strip()
    return None if text == "-" else text[:limit]


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=reply_markup)


async def _menu(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    service = IdeaService(session)
    _, partner = await service.couple(user_id)  # AppError, если пары нет
    matches = await service.matches(user_id)
    text = (
        "💡 <b>Идеи для свиданий</b>\n\n"
        "Листайте идеи и отвечайте «хочу» или «не хочу». "
        f"Если вы с {escape(partner.first_name)} оба захотите одно и то же — "
        "это совпадение 💞, и из него можно сразу назначить свидание.\n\n"
        "Ваши «не хочу» партнёр не видит."
    )
    return text, menu_keyboard(len(matches))


async def _next_card(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    service = IdeaService(session)
    _, partner = await service.couple(user_id)
    deck = await service.deck(user_id, limit=1)
    if not deck:
        return "Идеи закончились 🙂 Добавьте свою — партнёр увидит её первой", deck_empty_keyboard()
    idea = deck[0]
    return notify.describe(idea, user_id, partner.first_name), card_keyboard(idea.id)


@router.message(Command("ideas"))
async def cmd_ideas(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    await state.clear()
    text, keyboard = await _menu(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(IdeaMenu.filter())
async def show_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    text, keyboard = await _menu(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


@router.callback_query(IdeaNext.filter())
async def show_next(callback: CallbackQuery, session: AsyncSession) -> None:
    text, keyboard = await _next_card(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


@router.callback_query(IdeaAnswer.filter())
async def answer_idea(callback: CallbackQuery, callback_data: IdeaAnswer, session: AsyncSession, bot: Bot) -> None:
    service = IdeaService(session)
    vote = IdeaVote.YES if callback_data.yes else IdeaVote.NO
    result = await service.vote(callback_data.idea_id, callback.from_user.id, vote)
    if result.matched:
        user, partner = await service.couple(callback.from_user.id)
        await notify.send_match(bot, result.idea, user, partner)
    text, keyboard = await _next_card(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer("💞 Совпадение!" if result.matched else None)


@router.callback_query(IdeaMatches.filter())
async def show_matches(callback: CallbackQuery, session: AsyncSession) -> None:
    matches = await IdeaService(session).matches(callback.from_user.id)
    text = (
        "💞 <b>Совпадения</b> — идеи, которые хотите вы оба. Откройте, чтобы назначить свидание"
        if matches
        else "Совпадений пока нет. Листайте идеи — как только вы оба захотите одно и то же, оно появится здесь"
    )
    await _edit_or_answer(callback, text, ideas_list_keyboard(matches))
    _ = await callback.answer()


@router.callback_query(IdeaMine.filter())
async def show_mine(callback: CallbackQuery, session: AsyncSession) -> None:
    ideas = await IdeaService(session).list_mine(callback.from_user.id)
    text = "📝 <b>Ваши идеи</b>" if ideas else "Своих идей пока нет — добавьте через «➕ Своя идея»"
    await _edit_or_answer(callback, text, ideas_list_keyboard(ideas))
    _ = await callback.answer()


@router.callback_query(IdeaOpen.filter())
async def open_idea(callback: CallbackQuery, callback_data: IdeaOpen, session: AsyncSession) -> None:
    service = IdeaService(session)
    _, partner = await service.couple(callback.from_user.id)
    idea = await service.get(callback_data.idea_id, callback.from_user.id)
    can_plan = await service.can_plan(idea, callback.from_user.id)
    text = notify.describe(idea, callback.from_user.id, partner.first_name)
    if can_plan:
        text += "\n\n💞 Вы оба этого хотите"
    await _edit_or_answer(callback, text, idea_detail_keyboard(idea, callback.from_user.id, can_plan))
    _ = await callback.answer()


@router.callback_query(IdeaDelete.filter())
async def delete_idea(callback: CallbackQuery, callback_data: IdeaDelete, session: AsyncSession) -> None:
    service = IdeaService(session)
    await service.delete(callback_data.idea_id, callback.from_user.id)
    ideas = await service.list_mine(callback.from_user.id)
    await _edit_or_answer(callback, "🗑 Идея удалена\n\n📝 <b>Ваши идеи</b>", ideas_list_keyboard(ideas))
    _ = await callback.answer()


# --- своя идея ---


@router.callback_query(IdeaNew.filter())
async def new_idea(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    _ = await IdeaService(session).couple(callback.from_user.id)  # AppError, если пары нет
    await state.set_state(NewIdea.title)
    if callback.message is not None:
        _ = await callback.message.answer(
            "➕ Новая идея для свидания\n\n"
            "Что хотите сделать вместе? Например: «Сплав на байдарках»\n\n/cancel — отменить"
        )
    _ = await callback.answer()


@router.message(NewIdea.title, plain_text)
async def new_idea_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:TITLE_MAX])
    await state.set_state(NewIdea.description)
    await message.answer("Пару слов подробнее? Или «-», чтобы пропустить")


@router.message(NewIdea.description, plain_text)
async def new_idea_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=_skip(message.text, TEXT_MAX))
    await state.set_state(NewIdea.place)
    await message.answer("Где? Напишите место или «-», чтобы пропустить")


@router.message(NewIdea.place, plain_text)
async def new_idea_place(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    await state.clear()
    service = IdeaService(session)
    idea = await service.create(
        message.from_user.id,
        title=str(data["title"]),
        description=data.get("description"),
        place=_skip(message.text, PLACE_MAX),
    )
    _, partner = await service.couple(message.from_user.id)
    text, keyboard = await _menu(session, message.from_user.id)
    await message.answer(
        f"Добавил ✨ {escape(partner.first_name)} увидит идею первой в своей колоде.\n\n"
        f"{notify.describe(idea, message.from_user.id, partner.first_name)}"
    )
    await message.answer(text, reply_markup=keyboard)


# --- свидание из совпадения ---


@router.callback_query(IdeaPlan.filter())
async def plan_idea(callback: CallbackQuery, callback_data: IdeaPlan, state: FSMContext, session: AsyncSession) -> None:
    idea = await IdeaService(session).check_can_plan(callback_data.idea_id, callback.from_user.id)
    await state.set_state(PlanIdea.starts_at)
    await state.update_data(idea_id=str(idea.id))
    if callback.message is not None:
        _ = await callback.message.answer(
            f"📅 Назначаем «{escape(idea.title)}»\n\n"
            "Когда? Напишите дату и время: <code>12.10 19:00</code> или <code>12.10.2026 19:00</code>\n\n"
            "/cancel — отменить"
        )
    _ = await callback.answer()


@router.message(PlanIdea.starts_at, plain_text)
async def plan_starts_at(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    service = IdeaService(session)
    user, _ = await service.couple(message.from_user.id)
    starts_at = parse_local_datetime(message.text or "", user.timezone)
    if starts_at is None:
        await message.answer("Не понял дату 🤔 Формат: <code>12.10 19:00</code>")
        return
    if starts_at <= datetime.now(UTC):
        await message.answer("Это время уже прошло, укажите будущее 🙂")
        return
    await state.update_data(starts_at=starts_at.isoformat())
    await state.set_state(PlanIdea.place)

    data = await state.get_data()
    idea = await service.get(UUID(str(data["idea_id"])), message.from_user.id)
    hint = f"«-» — оставить «{escape(idea.place)}»" if idea.place else "«-» — пропустить"
    await message.answer(f"Где? Напишите место, {hint}")


@router.message(PlanIdea.place, plain_text)
async def plan_place(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    await state.clear()
    date = await IdeaService(session).plan(
        UUID(str(data["idea_id"])),
        message.from_user.id,
        starts_at=datetime.fromisoformat(str(data["starts_at"])),
        place=_skip(message.text, PLACE_MAX),
    )
    name = escape(date.invitee.first_name)
    if await dates_notify.send_invite(bot, date):
        result = f"Отправил приглашение {name} 💌"
    else:
        result = (
            f"😕 Не получилось доставить приглашение {name} — возможно, бот у партнёра остановлен.\n"
            "Попросите открыть бота и отправьте ещё раз из карточки свидания: /dates"
        )
    await message.answer(f"{result}\n\n{dates_notify.describe(date, date.creator)}")
