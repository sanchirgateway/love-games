import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import images, storage
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.feature.dates.service import DateService
from app.feature.flowers.models import (
    MAX_FLOWER_PHOTOS,
    FlowerGift,
    FlowerGiftPhoto,
    FlowerOccasion,
    FlowerReaction,
)
from app.feature.flowers.repository import FlowerRepository
from app.feature.user.models import User
from app.feature.user.service import UserService

logger = logging.getLogger(__name__)

FLOWERS_MAX = 200
TEXT_MAX = 2000
PRICE_MAX = 10_000_000
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # исходный файл; после сжатия фото намного меньше
# Запас на расхождение часов клиента и сервера, когда given_at — «сейчас»
GIVEN_AT_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class NewFlowerPhoto:
    data: bytes
    tg_file_id: str | None = None


def can_see(gift: FlowerGift, user_id: int) -> bool:
    """Даритель видит запись всегда, получатель — только после того, как даритель подтвердил вручение."""
    return gift.giver_id == user_id or (gift.recipient_id == user_id and gift.is_given)


def _clean(value: str | None, field: str, limit: int = TEXT_MAX) -> str | None:
    """Пустая строка — «не заполнено»."""
    value = (value or "").strip()
    if len(value) > limit:
        raise AppError(f"{field}: не больше {limit} символов")
    return value or None


def _check_given_at(given_at: datetime) -> None:
    if given_at.tzinfo is None:
        raise AppError("Время должно быть с часовым поясом")
    if given_at > datetime.now(UTC) + GIVEN_AT_SKEW:
        raise AppError("Нельзя отметить вручение в будущем")


class FlowerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = FlowerRepository(session)
        self.users = UserService(session)

    async def couple(self, user_id: int) -> tuple[User, User]:
        """Пользователь и его партнёр. Без пары дарить некому — AppError."""
        return await self.users.get(user_id), await self.users.get_partner(user_id)

    async def participants(self, gift: FlowerGift) -> tuple[User, User]:
        """Даритель и получатель букета."""
        return await self.users.get(gift.giver_id), await self.users.get(gift.recipient_id)

    async def create(
        self,
        giver_id: int,
        flowers: str,
        occasion: FlowerOccasion | None = None,
        comment: str | None = None,
        price: int | None = None,
        date_id: UUID | None = None,
        given_at: datetime | None = None,
        photos: list[NewFlowerPhoto] | None = None,
    ) -> FlowerGift:
        """Записывает букет партнёру. given_at=None — ещё не вручён (сюрприз), партнёр его не видит.

        Сначала файлы в хранилище, потом строки в БД.
        """
        photos = photos or []
        _, partner = await self.couple(giver_id)
        flowers_text = _clean(flowers, "Цветы", FLOWERS_MAX)
        if flowers_text is None:
            raise AppError("Напишите, какие цветы")
        if price is not None and not 0 <= price <= PRICE_MAX:
            raise AppError("Цена должна быть от 0 до 10 000 000")
        if given_at is not None:
            _check_given_at(given_at)
        if date_id is not None:
            _ = await DateService(self.session).get_for_user(date_id, giver_id)  # свидание этой пары
        photos = await _prepare_photos(photos, already=0)

        gift = FlowerGift(
            id=uuid4(),
            giver_id=giver_id,
            recipient_id=partner.id,
            date_id=date_id,
            flowers=flowers_text,
            occasion=occasion,
            comment=_clean(comment, "Комментарий"),
            price=price,
            given_at=given_at,
            # Явно пустой список: без фото коллекция иначе не загружена, и обращение к ней — ленивый запрос (MissingGreenlet)
            photos=[],
        )
        uploaded: list[str] = []
        try:
            await _attach_photos(gift, giver_id, photos, uploaded)
            _ = await self.repo.create(gift)
            await self.session.commit()
        except Exception:
            # Запись не сохранилась — убираем уже загруженные файлы, чтобы не копить мусор в бакете
            await self.session.rollback()
            await _delete_files(uploaded)
            raise
        return gift

    async def add_photos(self, gift_id: UUID, user_id: int, photos: list[NewFlowerPhoto]) -> FlowerGift:
        """Досылает фото к букету: получатель — например, букет в вазе, даритель — то, что не успел приложить.

        Получателю невручённый букет не виден (get — NotFoundError), так что сюрприз не раскроется.
        """
        if not photos:
            raise AppError("Пришлите хотя бы одно фото")
        gift = await self.get(gift_id, user_id)
        mine = gift.photos_by(user_id)
        photos = await _prepare_photos(photos, already=len(mine))

        uploaded: list[str] = []
        try:
            await _attach_photos(gift, user_id, photos, uploaded, start=len(mine))
            await self._commit(gift)
        except Exception:
            await self.session.rollback()
            await _delete_files(uploaded)
            raise
        return gift

    async def get(self, gift_id: UUID, user_id: int) -> FlowerGift:
        gift = await self.repo.get(gift_id)
        # Невручённый букет для получателя не существует — 404, а не 403, чтобы не выдать сюрприз
        if gift is None or not can_see(gift, user_id):
            raise NotFoundError("Букет не найден")
        return gift

    async def list_for_user(self, user_id: int, limit: int | None = None) -> list[FlowerGift]:
        return await self.repo.list_for_user(user_id, limit)

    async def count_given(self, user_id: int) -> int:
        return await self.repo.count_given(user_id)

    async def get_photo(self, photo_id: UUID, user_id: int) -> FlowerGiftPhoto:
        photo = await self.repo.get_photo(photo_id)
        if photo is None:
            raise NotFoundError("Фото не найдено")
        _ = await self.get(photo.gift_id, user_id)  # NotFoundError, если букет пользователю не виден
        return photo

    async def give(self, gift_id: UUID, user_id: int, given_at: datetime | None = None) -> FlowerGift:
        """Даритель подтверждает, что вручил букет: с этого момента его видит получатель."""
        gift = await self.get(gift_id, user_id)
        if gift.giver_id != user_id:
            raise ForbiddenError("Подтвердить вручение может только тот, кто дарит")
        if gift.is_given:
            raise ConflictError("Букет уже отмечен врученным")
        if given_at is not None:
            _check_given_at(given_at)
        gift.given_at = given_at or datetime.now(UTC)
        await self._commit(gift)
        return gift

    async def react(self, gift_id: UUID, user_id: int, reaction: FlowerReaction) -> FlowerGift:
        """Реакция получателя. Можно поменять."""
        gift = await self.get(gift_id, user_id)
        if gift.recipient_id != user_id:
            raise ForbiddenError("Реакцию оставляет тот, кому подарили")
        gift.reaction = reaction
        gift.reacted_at = datetime.now(UTC)
        await self._commit(gift)
        return gift

    async def delete(self, gift_id: UUID, user_id: int) -> None:
        """Удаляет запись (только даритель): сначала строки в БД, файлы — в самом конце."""
        gift = await self.get(gift_id, user_id)
        if gift.giver_id != user_id:
            raise ForbiddenError("Удалить запись может только тот, кто дарил")
        keys = [photo.key for photo in gift.photos]
        await self.session.delete(gift)
        await self.session.commit()
        await _delete_files(keys)

    async def _commit(self, gift: FlowerGift) -> None:
        await self.session.commit()
        # updated_at считает база (onupdate) — без перечитывания async-сессия упадёт при попытке его прочитать
        await self.session.refresh(gift, ["updated_at"])


async def _prepare_photos(photos: list[NewFlowerPhoto], already: int) -> list[NewFlowerPhoto]:
    """Проверяет лимиты (already — сколько фото у автора уже есть) и сжимает фото из Mini App."""
    if already + len(photos) > MAX_FLOWER_PHOTOS:
        left = f" — осталось {MAX_FLOWER_PHOTOS - already}" if already else ""
        raise AppError(f"Можно прикрепить не больше {MAX_FLOWER_PHOTOS} фото{left}")
    if any(len(photo.data) > MAX_PHOTO_SIZE for photo in photos):
        raise AppError(f"Фото больше {MAX_PHOTO_SIZE // 1024 // 1024} МБ")
    return [await _optimize(photo) for photo in photos]


async def _attach_photos(
    gift: FlowerGift, author_id: int, photos: list[NewFlowerPhoto], uploaded: list[str], start: int = 0
) -> None:
    """Загружает файлы в хранилище и добавляет строки к букету. Ключи загруженных — в uploaded, для отката."""
    for position, photo in enumerate(photos, start=start):
        photo_id = uuid4()
        key = f"flowers/{gift.id}/{photo_id}.jpg"
        await storage.upload(key, photo.data, "image/jpeg")
        uploaded.append(key)
        gift.photos.append(
            FlowerGiftPhoto(
                id=photo_id,
                author_id=author_id,
                position=position,
                key=key,
                tg_file_id=photo.tg_file_id,
                size=len(photo.data),
            )
        )


async def _optimize(photo: NewFlowerPhoto) -> NewFlowerPhoto:
    """Сжимает фото из Mini App (оригиналы с камеры, с GPS в EXIF). Фото из Telegram уже сжаты — не трогаем."""
    if photo.tg_file_id is not None:
        return photo
    try:
        data = await images.compress_photo(photo.data)
    except images.ImageError as e:
        raise AppError("Не удалось открыть одно из фото — пришлите JPEG или PNG") from e
    return NewFlowerPhoto(data=data)


async def _delete_files(keys: list[str]) -> None:
    # Не удалился файл — останется мусор в бакете, но пользователю это не мешает
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.exception("Не удалось удалить файл %s из хранилища", key)
