"""Сжатие фото перед сохранением в хранилище."""

import asyncio
import io

from PIL import Image, ImageOps, UnidentifiedImageError

# Длинная сторона после сжатия: на экране телефона разницы с оригиналом не видно
MAX_SIDE = 2048
JPEG_QUALITY = 82


class ImageError(Exception):
    """Файл не удалось открыть как картинку."""


def _compress(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            # Для JPEG декодирует сразу в уменьшенном масштабе — быстрее и меньше памяти на больших фото
            source.draft("RGB", (MAX_SIDE, MAX_SIDE))
            icc_profile = source.info.get("icc_profile")
            # Телефоны пишут поворот в EXIF, а не в пиксели — без этого фото ляжет боком
            img = ImageOps.exif_transpose(source)
            if img.mode in ("RGBA", "LA", "P"):
                # У JPEG нет прозрачности: прозрачное — на белый фон, а не на чёрный
                rgba = img.convert("RGBA")
                img = Image.new("RGB", rgba.size, "white")
                img.paste(rgba, mask=rgba.getchannel("A"))
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS, reducing_gap=3.0)

            out = io.BytesIO()
            # EXIF не передаём — так из файла пропадают GPS-координаты и модель телефона.
            # ICC-профиль оставляем: без него у фото с iPhone (Display P3) поплывут цвета
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True, icc_profile=icc_profile)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError(str(e)) from e


async def compress_photo(data: bytes) -> bytes:
    """Уменьшает фото до MAX_SIDE, поворачивает по EXIF, убирает метаданные. Результат — всегда JPEG.

    Работает в отдельном потоке: сжатие занимает процессор, и без этого на это время встал бы весь бот.
    """
    return await asyncio.to_thread(_compress, data)
