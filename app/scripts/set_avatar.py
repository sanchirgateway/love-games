"""Ставит аватарку бота: uv run python -m app.scripts.set_avatar photo/heart.png

Запускать разово: каждый вызов загружает новое фото в профиль бота.
"""

import asyncio
import io
import sys
from pathlib import Path

from aiogram.types import BufferedInputFile, InputProfilePhotoStatic
from PIL import Image

from app.core.bot import create_bot

DEFAULT_PHOTO = Path("photo/heart.png")
MAX_SIDE = 1024


def to_jpeg(path: Path) -> bytes:
    """Telegram принимает статичную аватарку только в JPG — конвертируем любой формат."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def main(path: Path) -> None:
    if not path.is_file():
        sys.exit(f"Файл не найден: {path}")

    photo = BufferedInputFile(to_jpeg(path), filename="avatar.jpg")
    bot = create_bot()
    async with bot.session:
        _ = await bot.set_my_profile_photo(InputProfilePhotoStatic(photo=photo))
    print(f"Avatar updated: {path}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PHOTO))
