"""Картинка виртуального букета: слои PNG, сложенные через Pillow.

Порядок слоёв: фон → задняя часть обёртки → цветы (от задних мест к передним) → передняя часть обёртки → лента.
Передняя часть обёртки закрывает стебли, поэтому видны только головки — их и раскладываем по местам.

Формат картинки цветка (и заглушек, и настоящих): PNG с прозрачным фоном размером FLOWER_SIZE,
центр головки — в FLOWER_HEAD, стебель идёт вниз по центру до нижнего края.
Обёртка и лента — PNG размером CANVAS с прозрачным фоном.

В вазе порядок другой: фон → ваза → цветы, в пределах горлышка обрезанные по его переднему краю (Vase.rim).
Картинка вазы — квадратный PNG с прозрачным фоном, один слой.
"""

import asyncio
import io
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

from app.feature.bouquets.catalog import ASSETS_DIR, MAX_BOUQUET_FLOWERS, VASES, Flower, FlowerRole, Vase

CANVAS = (1024, 1280)
BACKGROUND = (252, 246, 240)
JPEG_QUALITY = 88

FLOWER_SIZE = (400, 800)
FLOWER_HEAD = (200, 200)
FLOWER_SCALE = 0.75  # цветок со scale=1 на итоговой картинке: головка ~220 px

WRAP_BACK = ASSETS_DIR / "wrap_back.png"
WRAP_FRONT = ASSETS_DIR / "wrap_front.png"
RIBBON = ASSETS_DIR / "ribbon.png"

# Точка, где сходятся стебли (под лентой): от неё считается наклон цветка — букет раскрывается веером
BINDING = (512, 1000)
JITTER_PX = 14
JITTER_DEG = 4.0

VASE_UNITS = 200  # Vase.rim задан в этих единицах
VASE_BOX = 620  # ваза вписывается в такой квадрат
VASE_RIM_Y = 700  # горлышко — под нижними местами SLOTS
VASE_BINDING_DEPTH = 250  # стебли сходятся глубоко под горлышком: так все проходят через узкое горлышко
BOUQUET_TOP = 170  # выше этой линии (при shift_y=0) цветов нет: по ней центруется композиция
STEM_EXTRA = 500
MASK_SS = 2  # маску рисуем крупнее и уменьшаем — так край сглаживается

SHEET_CELL = 200
SHEET_COLUMNS = 5
SHEET_FONT_SIZE = 26
SHEET_NUMBER = (120, 80, 70)


@dataclass(frozen=True, slots=True)
class Slot:
    x: int  # центр головки
    y: int
    depth: int  # больше — ближе к зрителю, рисуется позже


# Места по важности: первые — в центре и впереди. Букет из n цветов занимает первые n мест,
# поэтому маленький букет получается плотным, а не дырявым
SLOTS = (
    Slot(512, 470, 2),
    Slot(420, 500, 2),
    Slot(604, 500, 2),
    Slot(466, 380, 1),
    Slot(558, 380, 1),
    Slot(340, 430, 1),
    Slot(684, 430, 1),
    Slot(512, 290, 0),
    Slot(390, 320, 0),
    Slot(634, 320, 0),
    Slot(270, 400, 0),
    Slot(754, 400, 0),
    Slot(330, 560, 2),
    Slot(694, 560, 2),
    Slot(512, 590, 3),
)
assert len(SLOTS) >= MAX_BOUQUET_FLOWERS


@dataclass(frozen=True, slots=True)
class Placed:
    flower: Flower
    x: float
    y: float
    tilt: float  # градусы, плюс — наклон вправо
    depth: int


def _interleave(groups: list[list[Flower]]) -> list[Flower]:
    """По одному из каждой группы по кругу: роза, пион, роза, пион, роза — а не все розы кучкой."""
    result: list[Flower] = []
    while any(groups):
        for group in groups:
            if group:
                result.append(group.pop())
    return result


def arrange(
    items: list[tuple[Flower, int]], seed: int, binding: tuple[int, int] = BINDING, shift_y: int = 0
) -> list[Placed]:
    """Раскладывает цветы по местам. Возвращает в порядке отрисовки — от задних к передним.

    Основные цветы — в первые (центральные) места, крупные раньше; зелень — в оставшиеся, по краям и сзади.
    Мелкие сдвиги и повороты случайны, но зависят только от seed: один букет всегда выглядит одинаково.
    binding — точка схождения стеблей, shift_y — сдвиг всего букета по вертикали (для ваз разной высоты).
    """
    rng = random.Random(seed)
    by_size = sorted(items, key=lambda item: -item[0].scale)
    mains = _interleave([[flower] * count for flower, count in by_size if flower.role is FlowerRole.MAIN])
    fillers = _interleave([[flower] * count for flower, count in by_size if flower.role is FlowerRole.FILLER])

    placed: list[Placed] = []
    for flower, slot in zip([*mains, *fillers], SLOTS, strict=False):
        x = slot.x + rng.uniform(-JITTER_PX, JITTER_PX)
        y = slot.y + shift_y + rng.uniform(-JITTER_PX, JITTER_PX)
        tilt = math.degrees(math.atan2(x - binding[0], binding[1] - y)) + rng.uniform(-JITTER_DEG, JITTER_DEG)
        placed.append(Placed(flower, x, y, tilt, slot.depth))
    # На одной глубине зелень — под цветами
    placed.sort(key=lambda p: (p.depth, p.flower.role is FlowerRole.MAIN))
    return placed


@lru_cache
def _layer(path: Path) -> Image.Image:
    """Картинки читаются с диска один раз за процесс."""
    with Image.open(path) as img:
        return img.convert("RGBA")


@lru_cache
def _flower_image(flower: Flower) -> Image.Image:
    k = FLOWER_SCALE * flower.scale
    img = _layer(flower.asset)
    return img.resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS)


@lru_cache
def _long_stem_image(flower: Flower) -> Image.Image:
    """Цветок с удлинённым стеблем: в вазе он должен дотянуться до горлышка."""
    img = _flower_image(flower)
    long = Image.new("RGBA", (img.width, img.height + STEM_EXTRA), (0, 0, 0, 0))
    long.paste(img, (0, 0))
    # Стебель внизу вертикальный — нижнюю строку картинки можно просто растянуть
    bottom_row = img.crop((0, img.height - 1, img.width, img.height))
    long.paste(bottom_row.resize((img.width, STEM_EXTRA)), (0, img.height))
    return long


def _stem_to_binding(placed: Placed, binding: tuple[int, int]) -> Image.Image:
    """Стебель ровно до точки схождения: длиннее он вышел бы из-под горлышка сбоку или снизу вазы."""
    img = _long_stem_image(placed.flower)
    head_y = FLOWER_HEAD[1] * img.width / FLOWER_SIZE[0]
    height = round(head_y + math.dist((placed.x, placed.y), binding))
    return img.crop((0, 0, img.width, min(height, img.height)))


def _paste_flower(canvas: Image.Image, placed: Placed, img: Image.Image) -> None:
    k = img.width / FLOWER_SIZE[0]
    # Головка относительно центра картинки — после поворота с expand центр остаётся центром
    vx = FLOWER_HEAD[0] * k - img.width / 2
    vy = FLOWER_HEAD[1] * k - img.height / 2
    rotated = img.rotate(-placed.tilt, resample=Image.Resampling.BICUBIC, expand=True)
    a = math.radians(-placed.tilt)  # rotate крутит против часовой, ось y направлена вниз
    rx = vx * math.cos(a) + vy * math.sin(a)
    ry = -vx * math.sin(a) + vy * math.cos(a)
    left = placed.x - rotated.width / 2 - rx
    top = placed.y - rotated.height / 2 - ry
    # paste с маской, а не alpha_composite: тот не принимает отрицательные координаты, а край цветка может выйти за холст
    canvas.paste(rotated, (round(left), round(top)), rotated)


def _compose_wrapped(items: list[tuple[Flower, int]], seed: int) -> Image.Image:
    canvas = Image.new("RGB", CANVAS, BACKGROUND)
    back = _layer(WRAP_BACK)
    canvas.paste(back, (0, 0), back)
    for placed in arrange(items, seed):
        _paste_flower(canvas, placed, _flower_image(placed.flower))
    for path in (WRAP_FRONT, RIBBON):
        layer = _layer(path)
        canvas.paste(layer, (0, 0), layer)
    return canvas


@dataclass(frozen=True, slots=True)
class VaseStage:
    """Ваза, подогнанная под холст."""

    image: Image.Image
    position: tuple[int, int]
    flowers_mask: Image.Image  # белое — там, где цветы видны: всё выше переднего края горлышка
    binding: tuple[int, int]
    shift_y: int


@lru_cache
def _vase_stage(vase: Vase) -> VaseStage:
    """Масштабирует вазу и ставит горлышко по центру: букет остаётся на месте, что бы ни было под ним."""
    source = _layer(vase.asset)
    bbox = source.getchannel("A").getbbox()
    assert bbox is not None
    units = source.width / VASE_UNITS  # rim задан для 200×200: картинки покрупнее подойдут без правки каталога
    k = min(VASE_BOX / (bbox[2] - bbox[0]), VASE_BOX / (bbox[3] - bbox[1]))
    cropped = source.crop(bbox)
    image = cropped.resize((round(cropped.width * k), round(cropped.height * k)), Image.Resampling.LANCZOS)

    rim = [(x * units, y * units) for x, y in vase.rim]
    rim_x = (rim[0][0] + rim[-1][0]) / 2
    rim_y = sum(y for _, y in rim) / len(rim)
    # Ставим композицию по центру холста: низкая ваза не должна оставлять пустоту снизу
    bottom = VASE_RIM_Y + (bbox[3] - rim_y) * k
    shift_y = round((CANVAS[1] - bottom - BOUQUET_TOP) / 2)
    left = round(CANVAS[0] / 2 - (rim_x - bbox[0]) * k)
    top = round(VASE_RIM_Y + shift_y - (rim_y - bbox[1]) * k)

    edge = [((x - bbox[0]) * k + left, (y - bbox[1]) * k + top) for x, y in rim]
    w, h = CANVAS
    # Обрезаем только в пределах горлышка: по бокам от него листья свисают поверх вазы, а не срезаются линией
    polygon = [(0, h), (edge[0][0], h), *edge, (edge[-1][0], h), (w, h), (w, 0), (0, 0)]
    mask = Image.new("L", (w * MASK_SS, h * MASK_SS), 0)
    ImageDraw.Draw(mask).polygon([(x * MASK_SS, y * MASK_SS) for x, y in polygon], fill=255)
    mask = mask.resize(CANVAS, Image.Resampling.LANCZOS)

    binding = (CANVAS[0] // 2, VASE_RIM_Y + shift_y + VASE_BINDING_DEPTH)
    return VaseStage(image, (left, top), mask, binding, shift_y)


def _compose_in_vase(items: list[tuple[Flower, int]], seed: int, vase: Vase) -> Image.Image:
    stage = _vase_stage(vase)
    canvas = Image.new("RGB", CANVAS, BACKGROUND)
    canvas.paste(stage.image, stage.position, stage.image)
    with_flowers = canvas.copy()
    for placed in arrange(items, seed, stage.binding, stage.shift_y):
        _paste_flower(with_flowers, placed, _stem_to_binding(placed, stage.binding))
    return Image.composite(with_flowers, canvas, stage.flowers_mask)


def _render(items: list[tuple[Flower, int]], seed: int, vase: Vase | None) -> bytes:
    canvas = _compose_in_vase(items, seed, vase) if vase else _compose_wrapped(items, seed)
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


async def render_bouquet(items: list[tuple[Flower, int]], bouquet_id: UUID, vase: Vase | None = None) -> bytes:
    """JPEG букета; без вазы — в обёртке. Раскладка зависит от id: превью до сохранения и готовый букет совпадают.

    Работает в отдельном потоке, как сжатие фото: Pillow занимает процессор.
    """
    return await asyncio.to_thread(_render, items, bouquet_id.int, vase)


@lru_cache(maxsize=1)
def _vase_sheet() -> bytes:
    """Все вазы одной картинкой с номерами. В исходном размере: так они не теряют резкость."""
    vases = list(VASES.values())
    rows = math.ceil(len(vases) / SHEET_COLUMNS)
    sheet = Image.new("RGB", (SHEET_CELL * SHEET_COLUMNS, SHEET_CELL * rows), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=SHEET_FONT_SIZE)
    for i, vase in enumerate(vases):
        row, column = divmod(i, SHEET_COLUMNS)
        x, y = column * SHEET_CELL, row * SHEET_CELL
        image = _layer(vase.asset)
        image = image.resize((SHEET_CELL, SHEET_CELL), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y), image)
        draw.text((x + 10, y + 6), str(vase.number), fill=SHEET_NUMBER, font=font)
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


async def render_vase_sheet() -> bytes:
    """JPEG для выбора вазы. Рисуется один раз за процесс."""
    return await asyncio.to_thread(_vase_sheet)
