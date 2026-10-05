import re
from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_DATETIME_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})\s*$")


def parse_local_datetime(text: str, tz: str) -> datetime | None:
    """Разбирает «12.10 19:00» или «12.10.2026 19:00» в часовом поясе пользователя."""
    match = _DATETIME_RE.match(text)
    if match is None:
        return None
    day, month, year, hour, minute = match.groups()
    zone = ZoneInfo(tz)
    now = datetime.now(zone)
    try:
        result = datetime(int(year or now.year), int(month), int(day), int(hour), int(minute), tzinfo=zone)
    except ValueError:
        return None
    # Год не указан и дата уже прошла — значит, имеется в виду следующий год
    if year is None and result < now:
        result = result.replace(year=now.year + 1)
    return result


def format_local(dt: datetime, tz: str) -> str:
    local = dt.astimezone(ZoneInfo(tz))
    return f"{local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"
