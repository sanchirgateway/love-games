"""Напоминания о предстоящих свиданиях."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.feature.dates.models import DateEvent


@dataclass(frozen=True)
class Reminder:
    offset: timedelta  # за сколько до начала свидания напоминать
    field: str  # колонка DateEvent, где хранится время отправки
    when: str  # «Свидание {when}»


REMINDERS = (
    Reminder(timedelta(days=2), "remind_two_day_before_sent_at", "послезавтра"),
    Reminder(timedelta(days=1), "remind_day_before_sent_at", "уже завтра"),
    Reminder(timedelta(hours=3), "remind_hours_before_sent_at", "через 3 часа"),
)

# Самое раннее напоминание: свидания, до которых дольше, проверять не нужно
MAX_OFFSET = max(reminder.offset for reminder in REMINDERS)


def take_due_reminder(date: DateEvent, now: datetime) -> Reminder | None:
    """Отмечает отправленными все напоминания, время которых наступило, и возвращает ближайшее к началу.

    Пропущенные напоминания задним числом не шлём: если свидание приняли за 20 часов до начала,
    «послезавтра» и «завтра» уже неактуальны — отметятся без отправки, и придёт только «через 3 часа».
    """
    if date.starts_at <= now:
        return None
    pending = [
        reminder
        for reminder in REMINDERS
        if date.starts_at - reminder.offset <= now and getattr(date, reminder.field) is None
    ]
    for reminder in pending:
        setattr(date, reminder.field, now)
    return min(pending, key=lambda reminder: reminder.offset, default=None)
