from collections.abc import Mapping
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.time import format_local_date
from app.feature.bouquets.catalog import FLOWERS, VASES
from app.feature.bouquets.models import VirtualBouquet
from app.feature.flowers.keyboards import REACTION_EMOJI
from app.feature.flowers.models import FlowerReaction

FLOWERS_PER_ROW = 2
VASES_PER_ROW = 2


class BouquetNew(CallbackData, prefix="bouquet_new"):
    pass


class BouquetOpen(CallbackData, prefix="bouquet_open"):
    bouquet_id: UUID


class BouquetAdd(CallbackData, prefix="bouquet_add"):
    """Добавить в собираемый букет один цветок."""

    flower: str


class BouquetUndo(CallbackData, prefix="bouquet_undo"):
    """Убрать последний добавленный цветок."""


class BouquetClear(CallbackData, prefix="bouquet_clear"):
    pass


class BouquetDone(CallbackData, prefix="bouquet_done"):
    pass


class BouquetVase(CallbackData, prefix="bouquet_vase"):
    """Выбрать ёмкость. Без кода — букет в обёртке."""

    vase: str | None = None


class BouquetChangeVase(CallbackData, prefix="bouquet_change_vase"):
    """Вернуться из превью к выбору ёмкости."""


class BouquetConfirm(CallbackData, prefix="bouquet_confirm"):
    """Превью понравилось — к открытке."""


class BouquetEdit(CallbackData, prefix="bouquet_edit"):
    """Вернуться из превью в конструктор с тем же составом."""


class BouquetNoCard(CallbackData, prefix="bouquet_no_card"):
    pass


class BouquetReact(CallbackData, prefix="bouquet_react"):
    bouquet_id: UUID
    reaction: FlowerReaction


def short_composition(bouquet: VirtualBouquet) -> str:
    """«🌹7 🌿3» — для кнопок."""
    return " ".join(f"{flower.emoji}{count}" for flower, count in bouquet.items)


def bouquet_button_text(bouquet: VirtualBouquet, user_id: int, tz: str) -> str:
    icon = "💐" if bouquet.sender_id == user_id else "🎁"
    reaction = f" {REACTION_EMOJI[bouquet.reaction]}" if bouquet.reaction else ""
    return f"{icon} {format_local_date(bouquet.created_at, tz)} · {short_composition(bouquet)}{reaction}"


def bouquets_list_keyboard(bouquets: list[VirtualBouquet], user_id: int, tz: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=bouquet_button_text(bouquet, user_id, tz),
                callback_data=BouquetOpen(bouquet_id=bouquet.id).pack(),
            )
        ]
        for bouquet in bouquets
    ]
    rows.append([InlineKeyboardButton(text="🌸 Собрать букет", callback_data=BouquetNew().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def compose_keyboard(counts: Mapping[str, int]) -> InlineKeyboardMarkup:
    """Конструктор: кнопка на каждый цветок каталога, на ней — сколько уже добавлено."""
    buttons = [
        InlineKeyboardButton(
            text=f"{flower.emoji} {flower.name}" + (f" · {counts[code]}" if counts.get(code) else ""),
            callback_data=BouquetAdd(flower=code).pack(),
        )
        for code, flower in FLOWERS.items()
    ]
    rows = [buttons[i : i + FLOWERS_PER_ROW] for i in range(0, len(buttons), FLOWERS_PER_ROW)]
    if counts:
        rows.append(
            [
                InlineKeyboardButton(text="↩️ Убрать последний", callback_data=BouquetUndo().pack()),
                InlineKeyboardButton(text="🗑 Заново", callback_data=BouquetClear().pack()),
            ]
        )
        rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=BouquetDone().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vase_keyboard() -> InlineKeyboardMarkup:
    """Выбор ёмкости: номера на кнопках совпадают с номерами на картинке."""
    buttons = [
        InlineKeyboardButton(text=f"{vase.number}. {vase.name}", callback_data=BouquetVase(vase=code).pack())
        for code, vase in VASES.items()
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎀 Без вазы, в обёртке", callback_data=BouquetVase().pack())],
            *(buttons[i : i + VASES_PER_ROW] for i in range(0, len(buttons), VASES_PER_ROW)),
            [InlineKeyboardButton(text="✏️ Изменить цветы", callback_data=BouquetEdit().pack())],
        ]
    )


def preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Цветы", callback_data=BouquetEdit().pack()),
                InlineKeyboardButton(text="🏺 Ёмкость", callback_data=BouquetChangeVase().pack()),
            ],
            [InlineKeyboardButton(text="✅ Нравится", callback_data=BouquetConfirm().pack())],
        ]
    )


def no_card_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Без открытки", callback_data=BouquetNoCard().pack())]]
    )


def reaction_keyboard(bouquet_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=emoji, callback_data=BouquetReact(bouquet_id=bouquet_id, reaction=reaction).pack()
                )
                for reaction, emoji in REACTION_EMOJI.items()
            ]
        ]
    )


def bouquet_detail_keyboard(bouquet: VirtualBouquet, user_id: int) -> InlineKeyboardMarkup | None:
    """Под картинкой букета: получателю — реакции, отправителю кнопок нет."""
    return reaction_keyboard(bouquet.id) if bouquet.recipient_id == user_id else None
