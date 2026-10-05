from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import parse_local_datetime
from app.feature.dates import notify
from app.feature.dates.keyboards import DateAnswer
from app.feature.dates.models import DateStatus
from app.feature.dates.service import DateService
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
    await message.answer("Отменил создание свидания.")


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
    await notify.send_invite(bot, date)
    await message.answer(
        f"Отправил приглашение {date.invitee.first_name} 💌\n\n{notify.describe(date, date.creator)}"
    )


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
