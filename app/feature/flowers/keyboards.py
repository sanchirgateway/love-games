from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.core.time import format_local_date
from app.feature.flowers.models import MAX_FLOWER_PHOTOS, FlowerGift, FlowerOccasion, FlowerReaction

PHOTOS_DONE = "✅ Готово"

REACTION_EMOJI = {
    FlowerReaction.LOVED: "😍",
    FlowerReaction.TOUCHED: "🥹",
    FlowerReaction.HAPPY: "😊",
    FlowerReaction.MEH: "😐",
}

OCCASION_LABELS = {
    FlowerOccasion.NO_REASON: "💝 Без повода",
    FlowerOccasion.DATE: "🥂 Свидание",
    FlowerOccasion.BIRTHDAY: "🎂 День рождения",
    FlowerOccasion.ANNIVERSARY: "💍 Годовщина",
    FlowerOccasion.HOLIDAY: "🎉 Праздник",
    FlowerOccasion.APOLOGY: "🙏 Извинение",
}


class FlowerList(CallbackData, prefix="flower_list"):
    pass


class FlowerNew(CallbackData, prefix="flower_new"):
    pass


class FlowerOpen(CallbackData, prefix="flower_open"):
    gift_id: UUID


class FlowerPhotos(CallbackData, prefix="flower_photos"):
    gift_id: UUID


class FlowerAddPhotos(CallbackData, prefix="flower_add_photos"):
    """Дослать фото к букету: получатель — букет в вазе, даритель — то, что не приложил сразу."""

    gift_id: UUID


class FlowerGive(CallbackData, prefix="flower_give"):
    """Даритель подтверждает, что вручил букет."""

    gift_id: UUID


class FlowerReact(CallbackData, prefix="flower_react"):
    gift_id: UUID
    reaction: FlowerReaction


class FlowerOccasionPick(CallbackData, prefix="flower_occasion"):
    occasion: FlowerOccasion | None  # None — пропустить


class FlowerWhen(CallbackData, prefix="flower_when"):
    days_ago: int | None  # 0 — сегодня, 1 — вчера, None — ещё не вручил (сюрприз)


def gift_button_text(gift: FlowerGift, user_id: int, tz: str) -> str:
    if not gift.is_given:
        return f"🤫 {gift.flowers} · ещё не вручён"
    assert gift.given_at is not None
    icon = "💐" if gift.giver_id == user_id else "🎁"
    reaction = f" {REACTION_EMOJI[gift.reaction]}" if gift.reaction else ""
    return f"{icon} {format_local_date(gift.given_at, tz)} · {gift.flowers}{reaction}"


def flowers_list_keyboard(gifts: list[FlowerGift], user_id: int, tz: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=gift_button_text(gift, user_id, tz), callback_data=FlowerOpen(gift_id=gift.id).pack())]
        for gift in gifts
    ]
    rows.append([InlineKeyboardButton(text="💐 Записать букет", callback_data=FlowerNew().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def occasion_keyboard() -> InlineKeyboardMarkup:
    labels = list(OCCASION_LABELS.items())
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=FlowerOccasionPick(occasion=occasion).pack())
            for occasion, label in labels[i : i + 2]
        ]
        for i in range(0, len(labels), 2)
    ]
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data=FlowerOccasionPick(occasion=None).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def when_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data=FlowerWhen(days_ago=0).pack()),
                InlineKeyboardButton(text="Вчера", callback_data=FlowerWhen(days_ago=1).pack()),
            ],
            [InlineKeyboardButton(text="🤫 Ещё не вручили — сюрприз", callback_data=FlowerWhen(days_ago=None).pack())],
        ]
    )


def reaction_keyboard(gift_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=emoji, callback_data=FlowerReact(gift_id=gift_id, reaction=reaction).pack())
                for reaction, emoji in REACTION_EMOJI.items()
            ]
        ]
    )


def add_photos_button(gift_id: UUID, label: str = "📷 Добавить фото") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=FlowerAddPhotos(gift_id=gift_id).pack())


def received_keyboard(gift_id: UUID) -> InlineKeyboardMarkup:
    """Получателю вместе с букетом: реакция и фото букета в вазе."""
    rows = reaction_keyboard(gift_id).inline_keyboard
    return InlineKeyboardMarkup(inline_keyboard=[*rows, [add_photos_button(gift_id, "🏺 Прислать фото в вазе")]])


def gift_detail_keyboard(gift: FlowerGift, user_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if gift.giver_id == user_id and not gift.is_given:
        rows.append([InlineKeyboardButton(text="🎁 Вручено!", callback_data=FlowerGive(gift_id=gift.id).pack())])
    if gift.recipient_id == user_id:
        rows.extend(reaction_keyboard(gift.id).inline_keyboard)
    if len(gift.photos_by(user_id)) < MAX_FLOWER_PHOTOS:
        rows.append([add_photos_button(gift.id)])
    if gift.photos:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📷 Фото ({len(gift.photos)})", callback_data=FlowerPhotos(gift_id=gift.id).pack()
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Все букеты", callback_data=FlowerList().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Обычная (не inline) клавиатура: кнопка остаётся внизу, пока пользователь присылает фото
photos_done_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=PHOTOS_DONE)]], resize_keyboard=True, one_time_keyboard=True
)
