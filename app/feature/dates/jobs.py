"""Фоновые задачи по свиданиям."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot

from app.core.db import session_maker
from app.feature.dates import notify
from app.feature.dates.service import DONE_AFTER, DateService
from app.feature.reviews import notify as review_notify
from app.feature.reviews.service import ReviewService

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 60

# Просим отзыв только о свиданиях, отмеченных вовремя. Старые свидания, которые задача доразметит
# после простоя или при первом запуске, пусть остаются без просьбы — иначе придёт пачка сообщений
REVIEW_REQUEST_MAX_AGE = DONE_AFTER + timedelta(days=1)


async def dates_loop(bot: Bot) -> None:
    """Раз в INTERVAL_SECONDS шлёт напоминания и отмечает прошедшие свидания. Работает, пока задачу не отменят."""
    steps = (
        (send_reminders, "Не удалось отправить напоминания о свиданиях"),
        (complete_past_dates, "Не удалось отметить прошедшие свидания"),
        (send_review_reminders, "Не удалось напомнить об отзывах"),
    )
    while True:
        # Шаги независимы: падение одного (например, БД недоступна) не должно мешать другим и останавливать цикл
        for step, error in steps:
            try:
                await step(bot)
            except Exception:
                logger.exception(error)
        await asyncio.sleep(INTERVAL_SECONDS)


async def send_reminders(bot: Bot) -> None:
    async with session_maker() as session:
        due = await DateService(session).take_due_reminders()
    for date, reminder in due:
        await notify.send_reminder(bot, date, reminder)


async def complete_past_dates(bot: Bot) -> None:
    async with session_maker() as session:
        dates = await DateService(session).complete_past()
    if not dates:
        return
    logger.info("Отмечено состоявшимися свиданий: %s", len(dates))
    oldest = datetime.now(UTC) - REVIEW_REQUEST_MAX_AGE
    for date in dates:
        if date.starts_at >= oldest:
            await review_notify.send_review_request(bot, date)


async def send_review_reminders(bot: Bot) -> None:
    async with session_maker() as session:
        due = await ReviewService(session).take_review_reminders()
    for date, users in due:
        for user in users:
            await review_notify.send_review_reminder(bot, date, user)
