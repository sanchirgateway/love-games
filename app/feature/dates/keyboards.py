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
    """Значок и подпись статуса. Принятое свидание, которое началось, но ещё не отмечено состоявшимся, — идёт."""
    if date.status == DateStatus.PLANNED:
        return ("💞", "Идёт") if date.starts_at <= datetime.now(UTC) else ("📅", "Запланировано")
    return _STATUS_LABELS[date.status]


class DateOpen(CallbackData, prefix="date_open"):
    date_id: UUID


class DateList(CallbackData, prefix="date_list"):
    pass


class DatePhotos(CallbackData, prefix="date_photos"):
    date_id: UUID


class DateDone(CallbackData, prefix="date_done"):
    date_id: UUID


class DateResend(CallbackData, prefix="date_resend"):
    date_id: UUID


def can_resend_invite(date: DateEvent, user_id: int) -> bool:
    """Автор может повторить приглашение, пока на него не ответили (например, если первое не дошло)."""
    return date.status == DateStatus.PROPOSED and date.created_by == user_id


def can_mark_done(date: DateEvent) -> bool:
    """Принятое свидание, которое уже началось, можно отметить состоявшимся, не дожидаясь автоматики."""
    return date.status == DateStatus.PLANNED and date.starts_at <= datetime.now(UTC)


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


def date_detail_keyboard(
    date_id: UUID, can_review: bool, photos_count: int, can_mark_done: bool, can_resend_invite: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_resend_invite:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Отправить приглашение ещё раз", callback_data=DateResend(date_id=date_id).pack()
                )
            ]
        )
    if can_mark_done:
        rows.append(
            [InlineKeyboardButton(text="✅ Свидание состоялось", callback_data=DateDone(date_id=date_id).pack())]
        )
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
