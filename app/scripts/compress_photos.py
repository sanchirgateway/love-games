"""Пережимает фото отзывов, загруженные через Mini App до того, как появилось сжатие.

    uv run python -m app.scripts.compress_photos           # только посчитать, ничего не меняя
    uv run python -m app.scripts.compress_photos --apply   # пережать

Берёт только фото без tg_file_id: фото из бота Telegram уже сжал. Фото, которые уже не больше
MAX_SIDE и без EXIF (в том числе загруженные после появления сжатия), пропускает — повторное
сжатие JPEG только портит качество. Скрипт можно запускать повторно: сделанное не повторится.
"""

import asyncio
import io
import sys

from PIL import Image
from sqlalchemy import select

from app.core import images, storage
from app.core.db import engine, session_maker
from app.feature.reviews.models import DateReviewPhoto


def needs_compress(data: bytes) -> bool:
    """Большое фото или с метаданными (GPS) — пережимаем. Уже сжатое не трогаем."""
    with Image.open(io.BytesIO(data)) as img:
        return max(img.size) > images.MAX_SIDE or bool(img.getexif())


async def main(apply: bool) -> None:
    async with session_maker() as session:
        stmt = select(DateReviewPhoto).where(
            DateReviewPhoto.tg_file_id.is_(None), DateReviewPhoto.content_type.startswith("image/")
        )
        photos = list(await session.scalars(stmt))
        print(f"Mini App photos: {len(photos)}{'' if apply else ' (dry run, add --apply to write)'}")

        before = after = done = skipped = failed = 0
        for photo in photos:
            try:
                data = await storage.download(photo.key)
                if not needs_compress(data):
                    skipped += 1
                    continue
                compressed = await images.compress_photo(data)
            except Exception as e:
                failed += 1
                print(f"  FAIL {photo.id} ({photo.key}): {e}")
                continue

            before += len(data)
            after += len(compressed)
            done += 1
            print(f"  {photo.id}: {len(data) / 1e6:.2f} MB -> {len(compressed) / 1e6:.2f} MB")
            if not apply:
                continue

            old_key = photo.key
            new_key = f"{old_key.rsplit('.', 1)[0]}.jpg"  # PNG станет JPEG — меняется расширение
            # Порядок как в ReviewService: сначала файл, потом строка в БД, старый файл — в самом конце.
            # Упадёт посередине — в БД останется ссылка на рабочий файл
            await storage.upload(new_key, compressed, "image/jpeg")
            photo.key = new_key
            photo.content_type = "image/jpeg"
            photo.size = len(compressed)
            await session.commit()
            if new_key != old_key:
                await storage.delete(old_key)

    await engine.dispose()
    print(
        f"{'Compressed' if apply else 'Would compress'}: {done}, skipped (already small): {skipped}, failed: {failed}"
    )
    if done:
        print(f"Size: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv[1:]))
