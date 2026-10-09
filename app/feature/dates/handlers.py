from datetime import UTC, datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import parse_local_datetime
from app.feature.dates import notify
from app.feature.dates.keyboards import (
    DateAnswer,
    DateDone,
    DateList,
    DateOpen,
    DatePhotos,
    DateResend,
    can_mark_done,
    can_resend_invite,
    date_detail_keyboard,
    dates_list_keyboard,
    status_label,
)
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.dates.service import DateService
from app.feature.reviews import notify as review_notify
from app.feature.reviews.service import ReviewService, can_review
from app.feature.user.service import UserService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")


class NewDate(StatesGroup):
    title = State()
    starts_at = State()
    place = State()


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Нечего отменять 🙂")
        return
    await state.clear()
    await message.answer("Отменил.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    partner = await UserService(session).get_partner(message.from_user.id)  # AppError, если пары нет
    await state.set_state(NewDate.title)
    await message.answer(
        f"Создаём свидание с {partner.first_name} 💐\n\nКак назовём? Например: «Ужин» или «Кино»\n\n/cancel — отменить"
    )


@router.message(NewDate.title, plain_text)
async def new_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()[:200]
    await state.update_data(title=title)
    await state.set_state(NewDate.starts_at)
    await message.answer("Когда? Напишите дату и время: <code>12.10 19:00</code> или <code>12.10.2026 19:00</code>")


@router.message(NewDate.starts_at, plain_text)
async def new_starts_at(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService(session).get(message.from_user.id)
    starts_at = parse_local_datetime(message.text or "", user.timezone)
    if starts_at is None:
        await message.answer("Не понял дату 🤔 Формат: <code>12.10 19:00</code>")
        return
    if starts_at <= datetime.now(UTC):
        await message.answer("Это время уже прошло, укажите будущее 🙂")
        return

    await state.update_data(starts_at=starts_at.isoformat())
    await state.set_state(NewDate.place)
    await message.answer("Где? Напишите место или «-», чтобы пропустить")


@router.message(NewDate.place, plain_text)
async def new_place(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    place = (message.text or "").strip()
    data = await state.get_data()
    await state.clear()

    date = await DateService(session).propose(
        author_id=message.from_user.id,
        title=str(data["title"]),
        starts_at=datetime.fromisoformat(str(data["starts_at"])),
        place=None if place == "-" else place[:200],
    )
    name = escape(date.invitee.first_name)
    if await notify.send_invite(bot, date):
        result = f"Отправил приглашение {name} 💌"
    else:
        result = (
            f"😕 Не получилось доставить приглашение {name} — возможно, бот у партнёра остановлен.\n"
            "Попросите открыть бота и отправьте ещё раз из карточки свидания: /dates"
        )
    await message.answer(f"{result}\n\n{notify.describe(date, date.creator)}")


@router.callback_query(DateAnswer.filter())
async def answer_invite(
    callback: CallbackQuery, callback_data: DateAnswer, session: AsyncSession, bot: Bot
) -> None:
    date = await DateService(session).respond(callback_data.date_id, callback.from_user.id, callback_data.accept)
    await notify.send_answer(bot, date)

    result = "✅ Вы приняли приглашение" if date.status == DateStatus.PLANNED else "❌ Вы отказались"
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(f"{notify.describe(date, date.invitee)}\n\n{result}")
    _ = await callback.answer()


DATES_LIST_LIMIT = 20
REVIEW_FIELD_PREVIEW = 300  # в карточке свидания длинные отзывы обрезаем, чтобы влезть в лимит сообщения


async def _dates_list(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    dates = await DateService(session).list_for_user(user_id)
    if not dates:
        return "У вас пока нет свиданий. Предложить: /new", None
    recent = sorted(dates, key=lambda d: d.starts_at, reverse=True)[:DATES_LIST_LIMIT]
    user = await UserService(session).get(user_id)
    return "Ваши свидания:", dates_list_keyboard(recent, user.timezone)


@router.message(Command("dates"))
async def cmd_dates(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text, keyboard = await _dates_list(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(DateList.filter())
async def back_to_dates(callback: CallbackQuery, session: AsyncSession) -> None:
    text, keyboard = await _dates_list(session, callback.from_user.id)
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=keyboard)
    _ = await callback.answer()


async def _date_card(session: AsyncSession, date: DateEvent, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    reviews = await ReviewService(session).list_for_date(date.id)

    viewer = date.creator if date.created_by == user_id else date.invitee
    icon, label = status_label(date)
    parts = [notify.describe(date, viewer), f"{icon} {label}"]
    for review in reviews:
        author = date.creator if review.author_id == date.created_by else date.invitee
        title = "Ваш отзыв" if review.author_id == user_id else f"Отзыв от {escape(author.first_name)}"
        photos = f"\n📷 {len(review.photos)} фото" if review.photos else ""
        parts.append(f"<b>{title}</b>\n{review_notify.describe(review, REVIEW_FIELD_PREVIEW)}{photos}")

    photos_count = sum(len(review.photos) for review in reviews)
    keyboard = date_detail_keyboard(
        date.id,
        can_review(date, reviews, user_id),
        photos_count,
        can_mark_done(date),
        can_resend_invite(date, user_id),
    )
    return "\n\n".join(parts), keyboard


@router.callback_query(DateOpen.filter())
async def open_date(callback: CallbackQuery, callback_data: DateOpen, session: AsyncSession) -> None:
    date = await DateService(session).get_for_user(callback_data.date_id, callback.from_user.id)
    text, keyboard = await _date_card(session, date, callback.from_user.id)
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=keyboard)
    _ = await callback.answer()


@router.callback_query(DateResend.filter())
async def resend_invite(callback: CallbackQuery, callback_data: DateResend, session: AsyncSession, bot: Bot) -> None:
    date = await DateService(session).get_invite_to_resend(callback_data.date_id, callback.from_user.id)
    if await notify.send_invite(bot, date):
        _ = await callback.answer(f"Отправил приглашение {date.invitee.first_name} ещё раз 💌")
    else:
        _ = await callback.answer(
            f"Не получилось доставить приглашение {date.invitee.first_name}. "
            "Скорее всего, бот у партнёра остановлен — попросите открыть его и нажать «Старт»",
            show_alert=True,
        )


@router.callback_query(DateDone.filter())
async def mark_date_done(callback: CallbackQuery, callback_data: DateDone, session: AsyncSession, bot: Bot) -> None:
    user_id = callback.from_user.id
    date = await DateService(session).mark_done(callback_data.date_id, user_id)
    author, partner = (date.creator, date.invitee) if date.created_by == user_id else (date.invitee, date.creator)
    await review_notify.send_marked_done(bot, date, author, partner)

    text, keyboard = await _date_card(session, date, user_id)
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=keyboard)
    _ = await callback.answer("Отметили 💞 Теперь можно оставить отзыв")


@router.callback_query(DatePhotos.filter())
async def date_photos(callback: CallbackQuery, callback_data: DatePhotos, session: AsyncSession, bot: Bot) -> None:
    user_id = callback.from_user.id
    date = await DateService(session).get_for_user(callback_data.date_id, user_id)  # проверка доступа
    reviews = [review for review in await ReviewService(session).list_for_date(date.id) if review.photos]
    if not reviews:
        _ = await callback.answer("Фото пока нет", show_alert=True)
        return

    _ = await callback.answer()
    # Отдельный альбом на каждый отзыв: в одном media group максимум 10 фото
    for review in reviews:
        author = date.creator if review.author_id == date.created_by else date.invitee
        who = "Ваши фото" if review.author_id == user_id else f"Фото от {escape(author.first_name)}"
        await review_notify.send_photos(bot, user_id, review, caption=f"{who} · «{escape(date.title)}»")
