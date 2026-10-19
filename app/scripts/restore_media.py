"""Докачивает из Telegram файлы, которых нет в хранилище (например, после потери тома SeaweedFS).

    uv run python -m app.scripts.restore_media           # только посчитать, ничего не меняя
    uv run python -m app.scripts.restore_media --apply   # скачать и загрузить

Восстановить можно только то, что присылали боту: у файлов из Mini App нет tg_file_id, их копии есть
только в хранилище. Файл кладётся под тем же ключом, что записан в БД, — строки в БД не меняются.
Скрипт можно запускать повторно: файлы, которые уже есть в хранилище, пропускаются.
"""

import asyncio
import sys

from aiogram import Bot
from sqlalchemy import select

from app.core import storage
from app.core.bot import create_bot
from app.core.db import engine, session_maker
from app.feature.flowers.models import FlowerGiftPhoto
from app.feature.games.models import Game
from app.feature.reviews.models import DateReviewPhoto


async def main(apply: bool) -> None:
    async with session_maker() as session:
        photos = await session.scalars(select(DateReviewPhoto).where(DateReviewPhoto.tg_file_id.is_not(None)))
        games = await session.scalars(
            select(Game).where(Game.cover_key.is_not(None), Game.cover_tg_file_id.is_not(None))
        )
        flowers = await session.scalars(select(FlowerGiftPhoto).where(FlowerGiftPhoto.tg_file_id.is_not(None)))
        # (ключ в хранилище, file_id в Telegram, content_type). None отсеял WHERE — проверки для типизации
        files = [(p.key, p.tg_file_id, p.content_type) for p in photos if p.tg_file_id]
        files += [
            (g.cover_key, g.cover_tg_file_id, g.cover_content_type or "image/jpeg")
            for g in games
            if g.cover_key and g.cover_tg_file_id
        ]
        files += [(p.key, p.tg_file_id, "image/jpeg") for p in flowers if p.tg_file_id]
    await engine.dispose()
    print(f"Files with tg_file_id: {len(files)}{'' if apply else ' (dry run, add --apply to write)'}")

    bot: Bot = create_bot()
    missing = restored = failed = 0
    async with bot.session:
        for key, file_id, content_type in files:
            try:
                if await storage.exists(key):
                    continue
                missing += 1
                print(f"  missing: {key}")
                if not apply:
                    continue
                file = await bot.download(file_id)
                if file is None:
                    raise RuntimeError("Telegram не отдал файл")
                await storage.upload(key, file.read(), content_type)
                restored += 1
            except Exception as e:
                failed += 1
                print(f"  FAIL {key}: {e}")

    print(f"Missing: {missing}, restored: {restored}, failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv[1:]))
