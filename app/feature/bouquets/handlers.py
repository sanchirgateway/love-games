from collections import Counter
from html import escape
from uuid import UUID, uuid4

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.bouquets import notify, render
from app.feature.bouquets.catalog import MAX_BOUQUET_FLOWERS, MAX_BOUQUET_KINDS, in_catalog_order
from app.feature.bouquets.keyboards import (
    BouquetAdd,
    BouquetChangeVase,
    BouquetClear,
    BouquetConfirm,
    BouquetDone,
    BouquetEdit,
    BouquetNew,
    BouquetNoCard,
    BouquetOpen,
    BouquetReact,
    BouquetUndo,
    BouquetVase,
    bouquet_detail_keyboard,
    bouquets_list_keyboard,
    compose_keyboard,
    no_card_keyboard,
    preview_keyboard,
    vase_keyboard,
)
from app.feature.bouquets.service import CARD_MAX, BouquetService, build_composition, check_vase, count_flowers
from app.feature.flowers.keyboards import REACTION_EMOJI
from app.feature.user.service import UserService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")

BOUQUETS_IN_LIST = 20


class BouquetForm(StatesGroup):
    compose = State()
    vase = State()
    preview = State()
    card = State()


def _message(callback: CallbackQuery) -> Message | None:
    if callback.message is None or isinstance(callback.message, InaccessibleMessage):
        return None
    return callback.message


async def _edit(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Правит сообщение кнопки: у фото — подпись, у текста — текст."""
    message = _message(callback)
    if message is None:
        return
    if message.photo:
        _ = await message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        _ = await message.edit_text(text, reply_markup=reply_markup)


# --- /bouquets: отправленные и полученные ---


@router.message(Command("bouquets"))
async def cmd_bouquets(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService(session).get(message.from_user.id)
    bouquets = await BouquetService(session).list_for_user(user.id, BOUQUETS_IN_LIST)
    if not bouquets:
        text = "Виртуальных букетов пока нет. Соберите первый — из цветов на выбор 🌸"
    else:
        text = "🌸 Виртуальные букеты\n\n💐 — от вас, 🎁 — вам"
    await message.answer(text, reply_markup=bouquets_list_keyboard(bouquets, user.id, user.timezone))


@router.callback_query(BouquetOpen.filter())
async def open_bouquet(callback: CallbackQuery, callback_data: BouquetOpen, session: AsyncSession) -> None:
    """Картинка букета — отдельным сообщением: список остаётся выше, из него можно открыть другой букет."""
    service = BouquetService(session)
    bouquet = await service.get(callback_data.bouquet_id, callback.from_user.id)
    viewer = await UserService(session).get(callback.from_user.id)
    _ = await callback.answer()
    message = _message(callback)
    if message is None:
        return
    sent = await message.answer_photo(
        await notify.photo(bouquet),
        caption=notify.describe(bouquet, viewer),
        reply_markup=bouquet_detail_keyboard(bouquet, viewer.id),
    )
    if bouquet.tg_file_id is None and (file_id := notify.sent_file_id(sent)):
        await service.remember_photo(bouquet, file_id)


@router.callback_query(BouquetReact.filter())
async def react(callback: CallbackQuery, callback_data: BouquetReact, session: AsyncSession, bot: Bot) -> None:
    service = BouquetService(session)
    bouquet = await service.react(callback_data.bouquet_id, callback.from_user.id, callback_data.reaction)
    sender, recipient = await service.participants(bouquet)
    await _edit(callback, notify.describe(bouquet, recipient), bouquet_detail_keyboard(bouquet, recipient.id))
    _ = await callback.answer(REACTION_EMOJI[callback_data.reaction])
    await notify.send_reaction(bot, bouquet, sender, recipient)


# --- Собрать букет: каждое нажатие на цветок добавляет один стебель ---


def _compose_text(partner_name: str, added: list[str]) -> str:
    counts = Counter(added)
    preview = notify.composition_text(in_catalog_order(counts)) if counts else "Пока пусто — выберите цветы 👇"
    return (
        f"Букет для {escape(partner_name)} 🌸\n\n"
        f"Каждое нажатие добавляет один цветок. До {MAX_BOUQUET_FLOWERS} цветов, разных — до {MAX_BOUQUET_KINDS}.\n\n"
        f"{preview}\n\n/cancel — отменить"
    )


async def _show_compose(callback: CallbackQuery, state: FSMContext, added: list[str]) -> None:
    await state.update_data(added=added)
    data = await state.get_data()
    await _edit(callback, _compose_text(data["partner_name"], added), compose_keyboard(Counter(added)))


@router.callback_query(BouquetNew.filter())
async def new_bouquet(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    partner = await UserService(session).get_partner(callback.from_user.id)  # ConflictError, если пары нет
    await state.clear()
    await state.set_state(BouquetForm.compose)
    # id известен заранее: от него зависит раскладка, и превью совпадёт с тем, что получит партнёр
    await state.update_data(added=[], partner_name=partner.first_name, bouquet_id=str(uuid4()))
    _ = await callback.answer()
    if (message := _message(callback)) is not None:
        _ = await message.answer(_compose_text(partner.first_name, []), reply_markup=compose_keyboard({}))


@router.callback_query(BouquetForm.compose, BouquetAdd.filter())
async def add_flower(callback: CallbackQuery, callback_data: BouquetAdd, state: FSMContext) -> None:
    added: list[str] = (await state.get_data())["added"]
    added = [*added, callback_data.flower]
    _ = count_flowers((code, 1) for code in added)  # AppError — лимит превышен, покажется всплывающим окном
    await _show_compose(callback, state, added)
    _ = await callback.answer()


@router.callback_query(BouquetForm.compose, BouquetUndo.filter())
async def undo_flower(callback: CallbackQuery, state: FSMContext) -> None:
    added: list[str] = (await state.get_data())["added"]
    await _show_compose(callback, state, added[:-1])
    _ = await callback.answer()


@router.callback_query(BouquetForm.compose, BouquetClear.filter())
async def clear_bouquet(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_compose(callback, state, [])
    _ = await callback.answer()


async def _show_vases(message: Message, state: FSMContext) -> None:
    """Выбор ёмкости — картинкой со всеми вазами: на кнопку картинку не поставить, поэтому на них номера.

    Прошлое сообщение удаляем: текст нельзя превратить в фото, а новая картинка должна быть внизу чата.
    """
    sheet = await render.render_vase_sheet()
    _ = await message.delete()
    _ = await message.answer_photo(
        BufferedInputFile(sheet, "vases.jpg"),
        caption="Во что поставить букет? 🏺",
        reply_markup=vase_keyboard(),
    )
    await state.set_state(BouquetForm.vase)


@router.callback_query(BouquetForm.compose, BouquetDone.filter())
async def compose_done(callback: CallbackQuery, state: FSMContext) -> None:
    message = _message(callback)
    if message is None:
        return
    added: list[str] = (await state.get_data())["added"]
    _ = build_composition((code, 1) for code in added)  # AppError — например, одна зелень
    _ = await callback.answer()
    await _show_vases(message, state)


@router.callback_query(BouquetForm.vase, BouquetVase.filter())
async def choose_vase(callback: CallbackQuery, callback_data: BouquetVase, state: FSMContext) -> None:
    """Превью картинкой. id букета тот же, поэтому в другой вазе цветы лежат так же."""
    message = _message(callback)
    if message is None:
        return
    vase = check_vase(callback_data.vase)
    data = await state.get_data()
    _ = await callback.answer("Рисую букет…")
    image = await render.render_bouquet(in_catalog_order(Counter(data["added"])), UUID(data["bouquet_id"]), vase)
    _ = await message.delete()
    sent = await message.answer_photo(
        BufferedInputFile(image, "bouquet.jpg"),
        caption=f"Вот такой букет для {escape(data['partner_name'])} 🌸",
        reply_markup=preview_keyboard(),
    )
    # Превью уже в Telegram — партнёру отправим его же, без повторной отрисовки
    await state.update_data(vase=callback_data.vase, photo_id=notify.sent_file_id(sent))
    await state.set_state(BouquetForm.preview)


@router.callback_query(BouquetForm.preview, BouquetChangeVase.filter())
async def change_vase(callback: CallbackQuery, state: FSMContext) -> None:
    message = _message(callback)
    if message is None:
        return
    await state.update_data(photo_id=None)  # ваза поменяется — превью уже не то
    _ = await callback.answer()
    await _show_vases(message, state)


@router.callback_query(StateFilter(BouquetForm.vase, BouquetForm.preview), BouquetEdit.filter())
async def edit_bouquet(callback: CallbackQuery, state: FSMContext) -> None:
    message = _message(callback)
    if message is None:
        return
    data = await state.get_data()
    await state.update_data(photo_id=None)  # состав поменяется — превью уже не то
    await state.set_state(BouquetForm.compose)
    _ = await callback.answer()
    _ = await message.delete()
    added: list[str] = data["added"]
    _ = await message.answer(
        _compose_text(data["partner_name"], added), reply_markup=compose_keyboard(Counter(added))
    )


@router.callback_query(BouquetForm.preview, BouquetConfirm.filter())
async def confirm_bouquet(callback: CallbackQuery, state: FSMContext) -> None:
    message = _message(callback)
    if message is None:
        return
    data = await state.get_data()
    await state.set_state(BouquetForm.card)
    _ = await callback.answer()
    _ = await message.edit_reply_markup(reply_markup=None)  # чтобы букет не меняли после «Нравится»
    _ = await message.answer(
        f"Напишите открытку для {escape(data['partner_name'])} — до {CARD_MAX} символов",
        reply_markup=no_card_keyboard(),
    )


async def _send(state: FSMContext, session: AsyncSession, bot: Bot, user_id: int, card: str | None) -> None:
    """Сохраняет букет, отправляет партнёру и показывает отправителю, что ушло."""
    data = await state.get_data()
    service = BouquetService(session)
    bouquet = await service.create(
        user_id,
        ((code, 1) for code in data["added"]),
        vase=data.get("vase"),
        card=card,
        bouquet_id=UUID(data["bouquet_id"]),
        tg_file_id=data.get("photo_id"),
    )
    await state.clear()
    sender, recipient = await service.participants(bouquet)
    file_id = await notify.send_bouquet(bot, bouquet, sender, recipient)
    if bouquet.tg_file_id is None and file_id:
        await service.remember_photo(bouquet, file_id)
    _ = await bot.send_photo(
        sender.id,
        await notify.photo(bouquet),
        caption=f"Отправил {escape(recipient.first_name)} 🌸\n\n{notify.describe(bouquet, sender)}",
    )


@router.message(BouquetForm.card, plain_text)
async def bouquet_card(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    # Слишком длинная открытка — AppError из сервиса, состояние остаётся: можно написать короче
    await _send(state, session, bot, message.from_user.id, message.text)


@router.callback_query(BouquetForm.card, BouquetNoCard.filter())
async def bouquet_no_card(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    _ = await callback.answer()
    await _edit(callback, "Без открытки")
    await _send(state, session, bot, callback.from_user.id, None)
