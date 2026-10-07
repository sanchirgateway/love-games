from datetime import UTC, datetime
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.time import format_local
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.reviews.keyboards import ReviewPick


class DateAnswer(CallbackData, prefix="date"):
    date_id: UUID
    accept: bool


def invite_keyboard(date_id: UUID) -> InlineKeyboardMarkup:
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


_STATUS_LABELS = {
    DateStatus.PROPOSED: ("⏳", "Ждёт ответа"),
    DateStatus.DECLINED: ("❌", "Отклонено"),
    DateStatus.DONE: ("✅", "Состоялось"),
    DateStatus.CANCELLED: ("🚫", "Отменено"),
}


def status_label(date: DateEvent) -> tuple[str, str]:
    """Значок и подпись статуса. Принятое свидание, время которого прошло, считаем состоявшимся."""
    if date.status == DateStatus.PLANNED:
        return ("✅", "Состоялось") if date.starts_at <= datetime.now(UTC) else ("📅", "Запланировано")
    return _STATUS_LABELS[date.status]


class DateOpen(CallbackData, prefix="date_open"):
    date_id: UUID


class DateList(CallbackData, prefix="date_list"):
    pass


class DatePhotos(CallbackData, prefix="date_photos"):
    date_id: UUID


def dates_list_keyboard(dates: list[DateEvent], tz: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{status_label(date)[0]} {date.title} · {format_local(date.starts_at, tz)}",
                    callback_data=DateOpen(date_id=date.id).pack(),
                )
            ]
            for date in dates
        ]
    )


def date_detail_keyboard(date_id: UUID, can_review: bool, photos_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if photos_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📷 Фото ({photos_count})", callback_data=DatePhotos(date_id=date_id).pack()
                )
            ]
        )
    if can_review:
        rows.append(
            [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data=ReviewPick(date_id=date_id).pack())]
        )
    rows.append([InlineKeyboardButton(text="← Все свидания", callback_data=DateList().pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
