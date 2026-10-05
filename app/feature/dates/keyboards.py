from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class DateAnswer(CallbackData, prefix="date"):
    date_id: int
    accept: bool


def invite_keyboard(date_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=DateAnswer(date_id=date_id, accept=True).pack()),
                InlineKeyboardButton(
                    text="❌ Отказаться", callback_data=DateAnswer(date_id=date_id, accept=False).pack()
                ),
            ]
        ]
    )
