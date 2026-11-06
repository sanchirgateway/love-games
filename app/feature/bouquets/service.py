from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.feature.bouquets.catalog import (
    FLOWERS,
    MAX_BOUQUET_FLOWERS,
    MAX_BOUQUET_KINDS,
    FlowerRole,
    Vase,
    get_vase,
    in_catalog_order,
)
from app.feature.bouquets.models import VirtualBouquet
from app.feature.bouquets.repository import BouquetRepository
from app.feature.flowers.models import FlowerOccasion, FlowerReaction
from app.feature.user.models import User
from app.feature.user.service import UserService

CARD_MAX = 500  # открытка, а не письмо: текст должен помещаться в подпись к фото (1024 символа)


def count_flowers(items: Iterable[tuple[str, int]]) -> Counter[str]:
    """Складывает состав по кодам и проверяет лимиты. Подходит и для недособранного букета (в боте — на каждое нажатие).

    items — пары (код цветка, количество); один код может встречаться несколько раз, количества сложатся.
    """
    counts: Counter[str] = Counter()
    for code, count in items:
        if code not in FLOWERS:
            raise AppError(f"Нет такого цветка: {code}")
        if count <= 0:
            raise AppError("Количество цветов должно быть больше нуля")
        counts[code] += count

    if len(counts) > MAX_BOUQUET_KINDS:
        raise AppError(f"В букете может быть не больше {MAX_BOUQUET_KINDS} разных цветов")
    if counts.total() > MAX_BOUQUET_FLOWERS:
        raise AppError(f"В букете может быть не больше {MAX_BOUQUET_FLOWERS} цветов")
    return counts


def build_composition(items: Iterable[tuple[str, int]]) -> list[dict[str, Any]]:
    """Проверяет готовый букет и приводит состав к виду для БД: без повторов, в порядке каталога."""
    counts = count_flowers(items)
    if not counts:
        raise AppError("Добавьте в букет хотя бы один цветок")
    if all(FLOWERS[code].role is FlowerRole.FILLER for code in counts):
        raise AppError("Добавьте хотя бы один основной цветок — из одной зелени букет не собрать")
    return [{"flower": flower.code, "count": count} for flower, count in in_catalog_order(counts)]


def check_vase(code: str | None) -> Vase | None:
    """Ваза по коду; None — букет в обёртке."""
    vase = get_vase(code)
    if code and vase is None:
        raise AppError(f"Нет такой вазы: {code}")
    return vase


def _clean_card(card: str | None) -> str | None:
    card = (card or "").strip()
    if len(card) > CARD_MAX:
        raise AppError(f"Открытка: не больше {CARD_MAX} символов")
    return card or None


class BouquetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BouquetRepository(session)
        self.users = UserService(session)

    async def participants(self, bouquet: VirtualBouquet) -> tuple[User, User]:
        """Отправитель и получатель букета."""
        return await self.users.get(bouquet.sender_id), await self.users.get(bouquet.recipient_id)

    async def create(
        self,
        sender_id: int,
        items: Iterable[tuple[str, int]],
        vase: str | None = None,
        occasion: FlowerOccasion | None = None,
        card: str | None = None,
        bouquet_id: UUID | None = None,
        tg_file_id: str | None = None,
    ) -> VirtualBouquet:
        """Собирает букет и отправляет партнёру. Без пары — ConflictError из get_partner.

        bouquet_id задают заранее, когда уже показали превью: от id зависит раскладка, и картинка не изменится.
        tg_file_id — это превью, уже загруженное в Telegram.
        """
        partner = await self.users.get_partner(sender_id)
        _ = check_vase(vase)
        bouquet = VirtualBouquet(
            id=bouquet_id or uuid4(),
            sender_id=sender_id,
            recipient_id=partner.id,
            composition=build_composition(items),
            vase=vase,
            occasion=occasion,
            card=_clean_card(card),
            tg_file_id=tg_file_id,
        )
        _ = await self.repo.create(bouquet)
        await self.session.commit()
        return bouquet

    async def get(self, bouquet_id: UUID, user_id: int) -> VirtualBouquet:
        bouquet = await self.repo.get(bouquet_id)
        if bouquet is None or user_id not in (bouquet.sender_id, bouquet.recipient_id):
            raise NotFoundError("Букет не найден")
        return bouquet

    async def list_for_user(self, user_id: int, limit: int | None = None) -> list[VirtualBouquet]:
        return await self.repo.list_for_user(user_id, limit)

    async def remember_photo(self, bouquet: VirtualBouquet, tg_file_id: str) -> None:
        """Запоминает картинку, загруженную в Telegram, чтобы не рисовать букет заново."""
        bouquet.tg_file_id = tg_file_id
        await self.session.commit()
        await self.session.refresh(bouquet, ["updated_at"])

    async def react(self, bouquet_id: UUID, user_id: int, reaction: FlowerReaction) -> VirtualBouquet:
        """Реакция получателя. Можно поменять."""
        bouquet = await self.get(bouquet_id, user_id)
        if bouquet.recipient_id != user_id:
            raise ForbiddenError("Реакцию оставляет тот, кому подарили")
        bouquet.reaction = reaction
        bouquet.reacted_at = datetime.now(UTC)
        await self.session.commit()
        # updated_at считает база (onupdate) — без перечитывания async-сессия упадёт при попытке его прочитать
        await self.session.refresh(bouquet, ["updated_at"])
        return bouquet
