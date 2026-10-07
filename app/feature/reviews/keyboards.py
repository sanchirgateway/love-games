from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.core.time import format_local
from app.feature.dates.models import DateEvent

PHOTOS_DONE = "✅ Готово"


class ReviewPick(CallbackData, prefix="review_pick"):
    date_id: UUID


class ReviewRating(CallbackData, prefix="review_rating"):
    rating: int


def pick_date_keyboard(dates: list[DateEvent], tz: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{date.title} · {format_local(date.starts_at, tz)}",
                    callback_data=ReviewPick(date_id=date.id).pack(),
                )
            ]
            for date in dates
        ]
    )


def rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{n}⭐", callback_data=ReviewRating(rating=n).pack())
                for n in range(1, 6)
            ]
        ]
    )


# Обычная (не inline) клавиатура: кнопка остаётся внизу, пока пользователь присылает фото
photos_done_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=PHOTOS_DONE)]], resize_keyboard=True, one_time_keyboard=True
)
