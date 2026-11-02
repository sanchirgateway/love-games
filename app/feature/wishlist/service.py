from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.feature.user.models import User
from app.feature.user.service import UserService
from app.feature.wishlist.models import WishItem
from app.feature.wishlist.repository import WishlistRepository

TITLE_MAX = 200
URL_MAX = 1000
TEXT_MAX = 2000
PRICE_MAX = 10_000_000
ACTIVE_WISHES_MAX = 100


def _clean(value: str | None, field: str, limit: int) -> str | None:
    """Пустая строка — «не заполнено»."""
    value = (value or "").strip()
    if len(value) > limit:
        raise AppError(f"{field}: не больше {limit} символов")
    return value or None


def _clean_url(value: str | None) -> str | None:
    url = _clean(value, "Ссылка", URL_MAX)
    if url is not None and (not url.startswith(("http://", "https://")) or any(c.isspace() for c in url)):
        raise AppError("Ссылка должна начинаться с http:// или https://")
    return url


def _check_price(price: int | None) -> int | None:
    if price is not None and not 0 <= price <= PRICE_MAX:
        raise AppError("Цена должна быть от 0 до 10 000 000")
    return price


def reserved_by_viewer(item: WishItem, viewer_id: int) -> bool:
    """Бронь видит только тот, кто бронировал: владельцу она не показывается никогда."""
    return item.reserved_by == viewer_id and item.owner_id != viewer_id


class WishlistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WishlistRepository(session)
        self.users = UserService(session)

    async def couple(self, user_id: int) -> tuple[User, User]:
        """Пользователь и его партнёр. Вишлист — для пары, без пары — ConflictError."""
        return await self.users.get(user_id), await self.users.get_partner(user_id)

    async def get(self, item_id: UUID, user_id: int) -> WishItem:
        """Желание, видимое пользователю: своё или текущего партнёра."""
        _, partner = await self.couple(user_id)
        item = await self.repo.get(item_id)
        if item is None or item.owner_id not in (user_id, partner.id):
            raise NotFoundError("Желание не найдено")
        return item

    async def list_mine(self, user_id: int, limit: int | None = None) -> list[WishItem]:
        _ = await self.couple(user_id)
        return await self.repo.list_by_owner(user_id, limit)

    async def list_partner(self, user_id: int, limit: int | None = None) -> list[WishItem]:
        _, partner = await self.couple(user_id)
        return await self.repo.list_by_owner(partner.id, limit)

    async def create(
        self,
        user_id: int,
        title: str,
        url: str | None = None,
        price: int | None = None,
        note: str | None = None,
    ) -> WishItem:
        _ = await self.couple(user_id)
        title_text = _clean(title, "Название", TITLE_MAX)
        if title_text is None:
            raise AppError("Напишите, что хотите получить")
        if await self.repo.count_active(user_id) >= ACTIVE_WISHES_MAX:
            raise AppError(f"В вишлисте может быть не больше {ACTIVE_WISHES_MAX} желаний — удалите ненужные")
        item = await self.repo.create(
            WishItem(
                owner_id=user_id,
                title=title_text,
                url=_clean_url(url),
                price=_check_price(price),
                note=_clean(note, "Комментарий", TEXT_MAX),
            )
        )
        await self.session.commit()
        return item

    async def update(
        self,
        item_id: UUID,
        user_id: int,
        title: str | None = None,
        url: str | None = None,
        note: str | None = None,
        price: int | None = None,
        clear_price: bool = False,
    ) -> WishItem:
        """Меняет переданные поля, только владелец. url="" / note="" — стереть, clear_price — стереть цену."""
        item = await self._own(item_id, user_id)
        if title is not None:
            title_text = _clean(title, "Название", TITLE_MAX)
            if title_text is None:
                raise AppError("Название не может быть пустым")
            item.title = title_text
        if url is not None:
            item.url = _clean_url(url)
        if note is not None:
            item.note = _clean(note, "Комментарий", TEXT_MAX)
        if clear_price:
            item.price = None
        elif price is not None:
            item.price = _check_price(price)
        await self._commit(item)
        return item

    async def delete(self, item_id: UUID, user_id: int) -> tuple[str, User | None]:
        """Удаляет своё желание. Возвращает название и партнёра, если он успел его забронировать, — его надо предупредить."""
        item = await self._own(item_id, user_id)
        reserver = await self._reserver(item, user_id)
        title = item.title
        await self.session.delete(item)
        await self.session.commit()
        return title, reserver

    async def reserve(self, item_id: UUID, user_id: int) -> WishItem:
        """Тайная бронь партнёра: «я это подарю». Владелец о ней не узнает."""
        item = await self.get(item_id, user_id)
        if item.owner_id == user_id:
            raise ForbiddenError("Своё желание бронировать не нужно 🙂")
        if item.is_received:
            raise ConflictError("Это желание уже исполнено")
        if item.reserved_by == user_id:
            raise ConflictError("Вы уже забронировали это желание")
        # Бронь бывшего партнёра (после смены пары) не мешает: она не видна и ни на что не влияет
        item.reserved_by = user_id
        item.reserved_at = datetime.now(UTC)
        await self._commit(item)
        return item

    async def unreserve(self, item_id: UUID, user_id: int) -> WishItem:
        item = await self.get(item_id, user_id)
        if not reserved_by_viewer(item, user_id):
            raise ConflictError("Вы не бронировали это желание")
        item.reserved_by = None
        item.reserved_at = None
        await self._commit(item)
        return item

    async def receive(self, item_id: UUID, user_id: int) -> tuple[WishItem, User | None]:
        """Владелец отмечает, что получил подарок. Возвращает партнёра, если бронь была его, — поблагодарить."""
        item = await self._own(item_id, user_id)
        if item.is_received:
            raise ConflictError("Желание уже отмечено исполненным")
        reserver = await self._reserver(item, user_id)
        item.received_at = datetime.now(UTC)
        await self._commit(item)
        return item, reserver

    async def unreceive(self, item_id: UUID, user_id: int) -> WishItem:
        """«Снова хочу»: желание опять в списке, старая бронь сбрасывается."""
        item = await self._own(item_id, user_id)
        if not item.is_received:
            raise ConflictError("Желание и так в списке")
        item.received_at = None
        item.reserved_by = None
        item.reserved_at = None
        await self._commit(item)
        return item

    async def _own(self, item_id: UUID, user_id: int) -> WishItem:
        item = await self.get(item_id, user_id)
        if item.owner_id != user_id:
            raise ForbiddenError("Это желание партнёра — менять его может только он(а)")
        return item

    async def _reserver(self, item: WishItem, owner_id: int) -> User | None:
        _, partner = await self.couple(owner_id)
        return partner if item.reserved_by == partner.id else None

    async def _commit(self, item: WishItem) -> None:
        await self.session.commit()
        # updated_at считает база (onupdate) — без перечитывания async-сессия упадёт при попытке его прочитать
        await self.session.refresh(item, ["updated_at"])
