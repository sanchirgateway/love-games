"""Рисует картинки-заглушки для виртуальных букетов: цветы каталога, обёртку и ленту.

    uv run python -m app.scripts.make_bouquet_placeholders           # только недостающие
    uv run python -m app.scripts.make_bouquet_placeholders --force   # перерисовать все

Заглушки нужны, чтобы отрисовка работала до появления настоящих картинок. Настоящие кладутся
в ту же папку под теми же именами — и тогда скрипт без --force их не тронет.
Формат цветка — см. render.py: холст FLOWER_SIZE, головка в FLOWER_HEAD, стебель до низа по центру.
"""

import math
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

from app.feature.bouquets import render
from app.feature.bouquets.catalog import ASSETS_DIR, FLOWERS, FLOWERS_DIR

SS = 2  # рисуем в 2 раза крупнее и уменьшаем — так края сглаживаются
STEM = (76, 128, 62)
LEAF = (98, 150, 80)

Color = tuple[int, int, int]
Draw = Callable[[ImageDraw.ImageDraw, float, float], None]


def _petals(draw: ImageDraw.ImageDraw, cx: float, cy: float, n: int, length: float, width: float, color: Color,
            phase: float = 0) -> None:
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        # Лепесток — ромб из центра наружу: проще эллипса под углом и выглядит так же
        tip = (cx + math.cos(a) * length, cy + math.sin(a) * length)
        mid = (cx + math.cos(a) * length * 0.5, cy + math.sin(a) * length * 0.5)
        side = (math.cos(a + math.pi / 2) * width, math.sin(a + math.pi / 2) * width)
        draw.polygon([(cx, cy), (mid[0] + side[0], mid[1] + side[1]), tip, (mid[0] - side[0], mid[1] - side[1])],
                     fill=color, outline=_darker(color), width=2 * SS)


def _circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: Color) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color, outline=_darker(color), width=2 * SS)


def _darker(color: Color, k: float = 0.75) -> Color:
    return (int(color[0] * k), int(color[1] * k), int(color[2] * k))


def _rose(color: Color) -> Draw:
    def draw(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
        for i, r in enumerate((110, 85, 60, 36, 16)):
            _circle(d, cx + (i % 2) * 4 * SS, cy, r * SS, _darker(color, 1 - i * 0.06))
    return draw


def _tulip(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    color = (236, 92, 120)
    s = SS
    d.ellipse((cx - 70 * s, cy - 40 * s, cx + 70 * s, cy + 90 * s), fill=color, outline=_darker(color), width=2 * s)
    for dx in (-45, 0, 45):
        d.polygon([(cx + (dx - 35) * s, cy + 10 * s), (cx + dx * s, cy - 95 * s), (cx + (dx + 35) * s, cy + 10 * s)],
                  fill=color, outline=_darker(color), width=2 * s)


def _peony(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    color = (244, 168, 196)
    _petals(d, cx, cy, 10, 125 * SS, 55 * SS, _darker(color, 0.95))
    _petals(d, cx, cy, 8, 90 * SS, 45 * SS, color, phase=0.3)
    _circle(d, cx, cy, 45 * SS, (250, 196, 214))


def _sunflower(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    _petals(d, cx, cy, 16, 125 * SS, 22 * SS, (250, 200, 40))
    _circle(d, cx, cy, 60 * SS, (110, 70, 30))


def _chamomile(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    _petals(d, cx, cy, 14, 110 * SS, 18 * SS, (252, 252, 248))
    _circle(d, cx, cy, 34 * SS, (245, 196, 40))


def _lily(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    _petals(d, cx, cy, 6, 125 * SS, 38 * SS, (250, 226, 232), phase=-math.pi / 2)
    _circle(d, cx, cy, 18 * SS, (230, 150, 60))


def _gypsophila(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    # Облачко мелких цветков на тонких веточках
    for i in range(40):
        a, r = i * 2.4, 120 * SS * math.sqrt(i / 40)
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r * 0.8
        d.line([(cx, cy + 120 * SS), (x, y)], fill=STEM, width=2 * SS)
        _circle(d, x, y, 9 * SS, (250, 250, 250))


def _lavender(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    # Колосок: пары бутонов вдоль стебля
    for i in range(9):
        y = cy - 120 * SS + i * 30 * SS
        for dx in (-14, 14):
            _circle(d, cx + dx * SS, y, 15 * SS, (150, 110, 200))


def _eucalyptus(d: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    # Круглые листья по обе стороны ветки
    for i in range(6):
        y = cy - 130 * SS + i * 55 * SS
        for side in (-1, 1):
            _circle(d, cx + side * 38 * SS, y + side * 12 * SS, 30 * SS, (140, 176, 160))


SHAPES: dict[str, Draw] = {
    "rose_red": _rose((206, 32, 52)),
    "rose_white": _rose((248, 244, 236)),
    "rose_pink": _rose((240, 130, 160)),
    "tulip": _tulip,
    "peony": _peony,
    "sunflower": _sunflower,
    "chamomile": _chamomile,
    "lily": _lily,
    "gypsophila": _gypsophila,
    "lavender": _lavender,
    "eucalyptus": _eucalyptus,
}


def _canvas(size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size[0] * SS, size[1] * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _save(img: Image.Image, size: tuple[int, int], path: Path) -> None:
    img.resize(size, Image.Resampling.LANCZOS).save(path)
    print(f"  {path.relative_to(ASSETS_DIR)}")


def make_flower(code: str, path: Path) -> None:
    w, h = render.FLOWER_SIZE
    hx, hy = render.FLOWER_HEAD
    img, d = _canvas(render.FLOWER_SIZE)
    d.line([(hx * SS, hy * SS), (w / 2 * SS, h * SS)], fill=STEM, width=10 * SS)
    d.ellipse(((hx + 6) * SS, (hy + 300) * SS, (hx + 70) * SS, (hy + 330) * SS), fill=LEAF)  # листик на стебле
    SHAPES[code](d, hx * SS, hy * SS)
    _save(img, render.FLOWER_SIZE, path)


def make_wrap(path_back: Path, path_front: Path, path_ribbon: Path) -> None:
    kraft = (205, 170, 128)

    img, d = _canvas(render.CANVAS)
    # Задняя часть — веер за цветами
    d.polygon([(130 * SS, 330 * SS), (512 * SS, 190 * SS), (894 * SS, 330 * SS), (600 * SS, 1180 * SS),
               (424 * SS, 1180 * SS)], fill=_darker(kraft, 0.9))
    _save(img, render.CANVAS, path_back)

    img, d = _canvas(render.CANVAS)
    # Передняя часть — конус, закрывает стебли; складки — линиями
    cone = [(210 * SS, 660 * SS), (512 * SS, 740 * SS), (814 * SS, 660 * SS), (590 * SS, 1200 * SS),
            (434 * SS, 1200 * SS)]
    d.polygon(cone, fill=kraft, outline=_darker(kraft), width=3 * SS)
    for x in (360, 512, 664):
        d.line([(x * SS, 700 * SS), (512 * SS, 1190 * SS)], fill=_darker(kraft, 0.85), width=3 * SS)
    _save(img, render.CANVAS, path_front)

    img, d = _canvas(render.CANVAS)
    red = (196, 30, 58)
    bx, by = 512 * SS, 960 * SS
    for side in (-1, 1):
        d.polygon([(bx, by), (bx + side * 110 * SS, by - 60 * SS), (bx + side * 110 * SS, by + 60 * SS)],
                  fill=red, outline=_darker(red), width=3 * SS)
        d.polygon([(bx, by), (bx + side * 70 * SS, by + 170 * SS), (bx + side * 20 * SS, by + 180 * SS)], fill=red)
    _circle(d, bx, by, 26 * SS, _darker(red, 0.9))
    _save(img, render.CANVAS, path_ribbon)


def main(force: bool) -> None:
    FLOWERS_DIR.mkdir(parents=True, exist_ok=True)
    print("Заглушки:")
    for code, flower in FLOWERS.items():
        if force or not flower.asset.exists():
            make_flower(code, flower.asset)
    wraps = (render.WRAP_BACK, render.WRAP_FRONT, render.RIBBON)
    if force or not all(p.exists() for p in wraps):
        make_wrap(*wraps)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
