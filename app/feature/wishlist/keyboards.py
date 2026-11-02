from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.feature.wishlist.models import WishItem
from app.feature.wishlist.service import reserved_by_viewer


class WishMenu(CallbackData, prefix="wish_menu"):
    pass


class WishMine(CallbackData, prefix="wish_mine"):
    pass


class WishPartner(CallbackData, prefix="wish_partner"):
    pass


class WishNew(CallbackData, prefix="wish_new"):
    pass


class WishOpen(CallbackData, prefix="wish_open"):
    item_id: UUID


class WishReserve(CallbackData, prefix="wish_reserve"):
    item_id: UUID
    on: bool  # False — снять бронь


class WishReceive(CallbackData, prefix="wish_receive"):
    item_id: UUID
    on: bool  # False — «снова хочу»


class WishDelete(CallbackData, prefix="wish_delete"):
    item_id: UUID


def _button(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def menu_keyboard(mine: int, partners: int, partner_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(f"🎁 Мой вишлист ({mine})", WishMine())],
            [_button(f"💝 Вишлист {partner_name} ({partners})", WishPartner())],
            [_button("➕ Добавить желание", WishNew())],
        ]
    )


def back_button() -> InlineKeyboardButton:
    return _button("⬅️ К вишлисту", WishMenu())


def item_icon(item: WishItem, viewer_id: int) -> str:
    if item.is_received:
        return "✅"
    return "🔒" if reserved_by_viewer(item, viewer_id) else "🎁"


def items_list_keyboard(items: list[WishItem], viewer_id: int) -> InlineKeyboardMarkup:
    rows = [[_button(f"{item_icon(item, viewer_id)} {item.title}", WishOpen(item_id=item.id))] for item in items]
    rows.append([back_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def item_detail_keyboard(item: WishItem, viewer_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if item.owner_id == viewer_id:
        if item.is_received:
            rows.append([_button("↩️ Снова хочу", WishReceive(item_id=item.id, on=False))])
        else:
            rows.append([_button("✅ Уже получил(а)", WishReceive(item_id=item.id, on=True))])
        rows.append([_button("🗑 Удалить", WishDelete(item_id=item.id))])
        rows.append([_button("⬅️ Мой вишлист", WishMine())])
    else:
        if not item.is_received:
            if reserved_by_viewer(item, viewer_id):
                rows.append([_button("❌ Снять бронь", WishReserve(item_id=item.id, on=False))])
            else:
                rows.append([_button("🔒 Забронировать — подарю я", WishReserve(item_id=item.id, on=True))])
        rows.append([_button("⬅️ Вишлист партнёра", WishPartner())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
