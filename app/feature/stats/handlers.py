from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import format_local_date
from app.feature.flowers.keyboards import OCCASION_LABELS, REACTION_EMOJI
from app.feature.games.keyboards import MOOD_EMOJI
from app.feature.stats.service import CoupleStats, StatsService
from app.feature.user.service import UserService

router = Router()


def _rating(value: float | None) -> str:
    return f"{value:.1f} ⭐" if value is not None else "—"


def _emoji_counts[T](counts: dict[T, int], emoji: dict[T, str]) -> str:
    return "  ".join(f"{emoji[key]} {count}" for key, count in counts.items())


def format_stats(stats: CoupleStats, tz: str) -> str:
    period = f"за {stats.year} год" if stats.year is not None else "за всё время"
    d, f, g, m = stats.dates, stats.flowers, stats.games, stats.media
    lines = [f"📊 <b>Вы и {escape(stats.partner_name)} {period}</b>", "", "<b>💑 Свидания</b>"]

    lines.append(f"Состоялось: {d.done}, впереди: {d.upcoming}, отменено: {d.cancelled}")
    if d.first_at is not None:
        lines.append(f"Первое: {format_local_date(d.first_at, tz)}")
    if d.avg_rating is not None:
        lines.append(
            f"Средняя оценка: {_rating(d.avg_rating)} (ваша {_rating(d.my_avg_rating)}, "
            f"партнёра {_rating(d.partner_avg_rating)})"
        )
    if d.best is not None:
        lines.append(f"Лучшее: «{escape(d.best.title)}» — {_rating(d.best.rating)}")
    if d.top_place is not None:
        lines.append(f"Любимое место: {escape(d.top_place.place)} ({d.top_place.count} раз)")

    lines += ["", "<b>💐 Цветы</b>", f"Вы подарили: {f.given_by_me}, вам подарили: {f.given_by_partner}"]
    if f.my_spent:
        lines.append(f"Вы потратили: {f.my_spent:,} ₽".replace(",", " "))
    if f.reactions_to_mine:
        lines.append(f"Реакции на ваши букеты: {_emoji_counts(f.reactions_to_mine, REACTION_EMOJI)}")
    if f.top_occasion is not None:
        lines.append(f"Частый повод: {OCCASION_LABELS[f.top_occasion]}")
    if f.pending_surprises:
        lines.append(f"🤫 Ждут вручения: {f.pending_surprises}")

    lines += ["", "<b>🎮 Игры</b>", f"Игровых вечеров: {g.sessions}"]
    lines.append(f"Проходим: {g.playing}, прошли: {g.completed}, бросили: {g.dropped}")
    if g.top_game is not None:
        lines.append(f"Чаще всего: {escape(g.top_game.title)} ({g.top_game.sessions})")
    if g.avg_rating is not None:
        lines.append(f"Средняя оценка вечеров: {_rating(g.avg_rating)}")
    if g.moods:
        lines.append(f"Настроение: {_emoji_counts(g.moods, MOOD_EMOJI)}")

    i = stats.ideas
    lines += ["", "<b>💡 Идеи</b>", f"Совпадений: {i.matches}, свиданий из них: {i.dates_from_ideas}"]

    lines += ["", f"📷 Фото: {m.photos}, 🎬 видео: {m.videos}"]
    return "\n".join(lines)


@router.message(Command("stats"))
async def cmd_stats(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """/stats — за всё время, /stats 2026 — за год."""
    if message.from_user is None:
        return
    arg = (command.args or "").strip()
    if arg and not arg.isdigit():
        await message.answer("Укажите год числом, например: /stats 2026")
        return
    user = await UserService(session).get(message.from_user.id)
    stats = await StatsService(session).for_couple(user.id, int(arg) if arg else None)
    await message.answer(format_stats(stats, user.timezone))
