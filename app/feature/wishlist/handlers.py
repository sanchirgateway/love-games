from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.wishlist import notify
from app.feature.wishlist.keyboards import (
    WishDelete,
    WishMenu,
    WishMine,
    WishNew,
    WishOpen,
    WishPartner,
    WishReceive,
    WishReserve,
    item_detail_keyboard,
    items_list_keyboard,
    menu_keyboard,
)
from app.feature.wishlist.service import PRICE_MAX, TEXT_MAX, TITLE_MAX, URL_MAX, WishlistService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")

SKIP_HINT = "Напишите ответ или «-», чтобы пропустить"
WISHES_IN_LIST = 30


class NewWish(StatesGroup):
    title = State()
    price = State()
    url = State()
    note = State()


def _skip(text: str | None, limit: int = TEXT_MAX) -> str | None:
    """«-» — пропустить шаг."""
    text = (text or "").strip()
    return None if text == "-" else text[:limit]


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=reply_markup)


async def _menu(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    service = WishlistService(session)
    _, partner = await service.couple(user_id)  # AppError, если пары нет
    mine = [item for item in await service.list_mine(user_id) if not item.is_received]
    partners = [item for item in await service.list_partner(user_id) if not item.is_received]
    name = escape(partner.first_name)
    text = (
        "🎁 <b>Вишлист</b>\n\n"
        f"Записывайте, что хотели бы получить в подарок, — {name} увидит ваш список.\n\n"
        f"В вишлисте {name} можно тайно забронировать желание: «подарю я». "
        "Владелец брони не видит, так что сюрприз останется сюрпризом 🤫"
    )
    return text, menu_keyboard(len(mine), len(partners), partner.first_name)


async def _show_item(callback: CallbackQuery, session: AsyncSession, item_id: UUID) -> None:
    service = WishlistService(session)
    user, _ = await service.couple(callback.from_user.id)
    item = await service.get(item_id, user.id)
    await _edit_or_answer(callback, notify.describe(item, user), item_detail_keyboard(item, user.id))


@router.message(Command("wishlist"))
async def cmd_wishlist(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    await state.clear()
    text, keyboard = await _menu(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(WishMenu.filter())
async def show_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    text, keyboard = await _menu(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


@router.callback_query(WishMine.filter())
async def show_mine(callback: CallbackQuery, session: AsyncSession) -> None:
    items = await WishlistService(session).list_mine(callback.from_user.id, WISHES_IN_LIST)
    text = (
        "🎁 <b>Ваш вишлист</b>\n✅ — уже исполнено"
        if items
        else "Ваш вишлист пока пуст — добавьте первое желание через «➕ Добавить желание»"
    )
    await _edit_or_answer(callback, text, items_list_keyboard(items, callback.from_user.id))
    _ = await callback.answer()


@router.callback_query(WishPartner.filter())
async def show_partner(callback: CallbackQuery, session: AsyncSession) -> None:
    service = WishlistService(session)
    _, partner = await service.couple(callback.from_user.id)
    items = await service.list_partner(callback.from_user.id, WISHES_IN_LIST)
    name = escape(partner.first_name)
    text = (
        f"💝 <b>Вишлист {name}</b>\n🔒 — забронировано вами, ✅ — уже исполнено"
        if items
        else f"{name} пока ничего не добавил(а) в вишлист"
    )
    await _edit_or_answer(callback, text, items_list_keyboard(items, callback.from_user.id))
    _ = await callback.answer()


@router.callback_query(WishOpen.filter())
async def open_item(callback: CallbackQuery, callback_data: WishOpen, session: AsyncSession) -> None:
    await _show_item(callback, session, callback_data.item_id)
    _ = await callback.answer()


@router.callback_query(WishReserve.filter())
async def reserve_item(callback: CallbackQuery, callback_data: WishReserve, session: AsyncSession) -> None:
    service = WishlistService(session)
    if callback_data.on:
        _ = await service.reserve(callback_data.item_id, callback.from_user.id)
    else:
        _ = await service.unreserve(callback_data.item_id, callback.from_user.id)
    await _show_item(callback, session, callback_data.item_id)
    _ = await callback.answer("🔒 Забронировано" if callback_data.on else "Бронь снята")


@router.callback_query(WishReceive.filter())
async def receive_item(callback: CallbackQuery, callback_data: WishReceive, session: AsyncSession, bot: Bot) -> None:
    service = WishlistService(session)
    if callback_data.on:
        item, reserver = await service.receive(callback_data.item_id, callback.from_user.id)
        if reserver is not None:
            owner = await service.users.get(callback.from_user.id)
            await notify.send_received(bot, item, owner, reserver)
    else:
        _ = await service.unreceive(callback_data.item_id, callback.from_user.id)
    await _show_item(callback, session, callback_data.item_id)
    _ = await callback.answer("Ура, желание исполнено 🎉" if callback_data.on else "Снова в вишлисте")


@router.callback_query(WishDelete.filter())
async def delete_item(callback: CallbackQuery, callback_data: WishDelete, session: AsyncSession, bot: Bot) -> None:
    service = WishlistService(session)
    title, reserver = await service.delete(callback_data.item_id, callback.from_user.id)
    if reserver is not None:
        owner = await service.users.get(callback.from_user.id)
        await notify.send_deleted(bot, title, owner, reserver)
    items = await service.list_mine(callback.from_user.id, WISHES_IN_LIST)
    await _edit_or_answer(
        callback, "🗑 Желание удалено\n\n🎁 <b>Ваш вишлист</b>", items_list_keyboard(items, callback.from_user.id)
    )
    _ = await callback.answer()


# --- новое желание ---


@router.callback_query(WishNew.filter())
async def new_wish(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    _ = await WishlistService(session).couple(callback.from_user.id)  # AppError, если пары нет
    await state.set_state(NewWish.title)
    if callback.message is not None:
        _ = await callback.message.answer(
            "➕ Новое желание\n\nЧто хотели бы получить? Например: «Плёночный фотоаппарат»\n\n/cancel — отменить"
        )
    _ = await callback.answer()


@router.message(NewWish.title, plain_text)
async def new_wish_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:TITLE_MAX])
    await state.set_state(NewWish.price)
    await message.answer(f"Сколько примерно стоит, в рублях?\n\n{SKIP_HINT}")


@router.message(NewWish.price, plain_text)
async def new_wish_price(message: Message, state: FSMContext) -> None:
    text = _skip(message.text)
    price = None
    if text is not None:
        digits = text.replace(" ", "").removesuffix("₽").removesuffix("р")
        if not digits.isdigit() or int(digits) > PRICE_MAX:
            await message.answer("Напишите сумму числом, например <code>3500</code>, или «-»")
            return
        price = int(digits)
    await state.update_data(price=price)
    await state.set_state(NewWish.url)
    await message.answer(f"Ссылка на товар? Начинается с <code>https://</code>\n\n{SKIP_HINT}")


@router.message(NewWish.url, plain_text)
async def new_wish_url(message: Message, state: FSMContext) -> None:
    url = _skip(message.text, URL_MAX)
    if url is not None and not url.startswith(("http://", "https://")):
        await message.answer("Ссылка должна начинаться с <code>https://</code> — пришлите её ещё раз или «-»")
        return
    await state.update_data(url=url)
    await state.set_state(NewWish.note)
    await message.answer(f"Что важно знать? Размер, цвет, где купить\n\n{SKIP_HINT}")


@router.message(NewWish.note, plain_text)
async def new_wish_note(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    await state.clear()
    service = WishlistService(session)
    item = await service.create(
        message.from_user.id,
        title=str(data["title"]),
        price=data.get("price"),
        url=data.get("url"),
        note=_skip(message.text),
    )
    owner, partner = await service.couple(message.from_user.id)
    await notify.send_new_wish(bot, item, owner, partner)
    await message.answer(
        f"Добавил ✨ {escape(partner.first_name)} получит уведомление.\n\n{notify.describe(item, owner)}"
    )
    text, keyboard = await _menu(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)
