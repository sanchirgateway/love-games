"""Каталог цветов для виртуальных букетов.

Каталог живёт в коде, а не в БД: набор цветов меняется вместе с картинками и деплоится вместе с ними.
В БД букет хранит только коды цветов, поэтому код цветка менять нельзя — только добавлять новые.
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"
FLOWERS_DIR = ASSETS_DIR / "flowers"
VASES_DIR = Path(__file__).parent / "vase"

MAX_BOUQUET_FLOWERS = 15  # всего стеблей в букете: столько мест в шаблоне раскладки
MAX_BOUQUET_KINDS = 5  # разных цветов в одном букете — больше смотрится пёстро и не влезает в кнопки


class FlowerRole(enum.StrEnum):
    """Роль цветка в букете: от неё зависит порядок слоёв при отрисовке."""

    MAIN = "main"  # основные цветы — на переднем плане
    FILLER = "filler"  # гипсофила, лаванда, зелень — заполняют фон, одни букет не составляют


@dataclass(frozen=True, slots=True, kw_only=True)
class Flower:
    code: str  # стабильный id: хранится в БД и в callback_data
    name: str  # «Красная роза»
    emoji: str  # для кнопок в боте
    role: FlowerRole = FlowerRole.MAIN
    scale: float = 1.0  # относительный размер при отрисовке: пион крупнее ромашки

    @property
    def asset(self) -> Path:
        """PNG с прозрачным фоном: один цветок со стеблем, бутоном вверх. Формат — в render.py."""
        return FLOWERS_DIR / f"{self.code}.png"


_FLOWERS = (
    Flower(code="rose_red", name="Красная роза", emoji="🌹"),
    Flower(code="rose_white", name="Белая роза", emoji="🤍"),
    Flower(code="rose_pink", name="Розовая роза", emoji="🩷"),
    Flower(code="tulip", name="Тюльпан", emoji="🌷"),
    Flower(code="peony", name="Пион", emoji="🌸", scale=1.3),
    Flower(code="sunflower", name="Подсолнух", emoji="🌻", scale=1.4),
    Flower(code="chamomile", name="Ромашка", emoji="🌼", scale=0.8),
    Flower(code="lily", name="Лилия", emoji="🪷", scale=1.2),
    Flower(code="gypsophila", name="Гипсофила", emoji="☁️", role=FlowerRole.FILLER, scale=0.7),
    Flower(code="lavender", name="Лаванда", emoji="💜", role=FlowerRole.FILLER, scale=0.9),
    Flower(code="eucalyptus", name="Эвкалипт", emoji="🌿", role=FlowerRole.FILLER),
)

FLOWERS: dict[str, Flower] = {flower.code: flower for flower in _FLOWERS}


def get_flower(code: str) -> Flower | None:
    return FLOWERS.get(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class Vase:
    code: str  # стабильный id: хранится в БД и в callback_data
    number: int  # номер на картинке выбора, он же имя файла
    name: str
    # Передний край горлышка слева направо, в координатах картинки 200×200. Над этой линией цветы видны,
    # под ней — скрыты: так стебли уходят внутрь вазы, а её задний край и ручка остаются за букетом
    rim: tuple[tuple[int, int], ...]

    @property
    def asset(self) -> Path:
        return VASES_DIR / f"{self.number}.png"


_VASES = (
    Vase(code="pink_pot", number=1, name="Розовое кашпо", rim=((52, 65), (75, 76), (100, 81), (125, 77), (150, 58))),
    Vase(code="mint_round", number=2, name="Мятная ваза", rim=((68, 72), (84, 78), (100, 80), (116, 78), (132, 72))),
    Vase(code="purple_box", number=3, name="Сиреневый ящик", rim=((42, 62), (100, 85), (158, 62))),
    Vase(
        code="beige_basket",
        number=4,
        name="Бежевая корзинка",
        rim=((30, 87), (50, 107), (100, 127), (150, 131), (175, 125)),
    ),
    Vase(
        code="rope_basket",
        number=5,
        name="Плетёная корзина",
        rim=((42, 75), (60, 95), (95, 107), (130, 98), (148, 75)),
    ),
    Vase(code="blue_swirl", number=6, name="Голубая ваза", rim=((40, 40), (75, 47), (115, 45), (150, 28))),
    Vase(code="cream_cone", number=7, name="Кремовый рожок", rim=((50, 55), (75, 64), (100, 68), (125, 65), (150, 53))),
    Vase(code="heart", number=8, name="Сердце", rim=((40, 65), (60, 80), (120, 89), (150, 75), (157, 60))),
    Vase(code="coral", number=9, name="Коралловая ваза", rim=((52, 48), (75, 55), (100, 58), (125, 55), (148, 47))),
    Vase(
        code="raspberry_box",
        number=10,
        name="Малиновая коробка",
        rim=((40, 50), (70, 63), (100, 67), (135, 63), (167, 50)),
    ),
    Vase(code="green_pot", number=11, name="Зелёное кашпо", rim=((35, 55), (60, 77), (100, 85), (140, 77), (165, 55))),
    Vase(
        code="wicker_basket",
        number=12,
        name="Корзинка с ручкой",
        rim=((52, 90), (72, 105), (100, 111), (130, 106), (152, 92)),
    ),
    Vase(code="orange_cone", number=13, name="Оранжевый рожок", rim=((25, 50), (75, 62), (100, 80), (125, 62), (175, 50))),
    Vase(code="blue_pot", number=14, name="Синее кашпо", rim=((40, 50), (70, 60), (100, 65), (130, 60), (160, 50))),
)

VASES: dict[str, Vase] = {vase.code: vase for vase in _VASES}


def get_vase(code: str | None) -> Vase | None:
    """None — букет в обёртке. Так же показывается букет с вазой, убранной из каталога."""
    return VASES.get(code) if code else None


def in_catalog_order(counts: Mapping[str, int]) -> list[tuple[Flower, int]]:
    """Состав {код: количество} → пары (цветок, количество) в порядке каталога. Неизвестные коды пропускаются."""
    return [(flower, counts[code]) for code, flower in FLOWERS.items() if counts.get(code)]
