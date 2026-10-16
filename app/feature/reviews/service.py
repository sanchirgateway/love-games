import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import images, storage
from app.core.errors import AppError, ConflictError, NotFoundError
from app.feature.dates.models import DateEvent
from app.feature.dates.service import DateService
from app.feature.reviews.models import MAX_REVIEW_PHOTOS, DateReview, DateReviewPhoto, is_video_type
from app.feature.reviews.repository import REVIEWABLE_STATUS, ReviewRepository
from app.feature.user.models import User

logger = logging.getLogger(__name__)

# Через сколько после того, как свидание состоялось, мягко напомнить об отзыве
REVIEW_REMINDER_AFTER = timedelta(days=1)
# О давних свиданиях не напоминаем: после простоя бота такие напоминания пришли бы пачкой
REVIEW_REMINDER_MAX_AGE = timedelta(days=2)
# Отзыв партнёра скрыт, пока не напишешь свой. Если так и не написал — откроется через это время
REVIEWS_REVEAL_AFTER = timedelta(days=7)

# Форматы, которые Telegram принимает как фото: сигнатура файла -> (content_type, расширение)
PHOTO_FORMATS = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # лимит Telegram на фото

# Видео — только MP4: его Telegram показывает в альбоме (MOV ушёл бы документом)
VIDEO_TYPE = "video/mp4"
# Бот может скачать из Telegram файл не больше 20 МБ (getFile) — тот же лимит и для Mini App
MAX_VIDEO_SIZE = 20 * 1024 * 1024


@dataclass(frozen=True)
class NewPhoto:
    """Фото или видео для отзыва."""

    data: bytes
    content_type: str
    tg_file_id: str | None = None


def detect_media_type(data: bytes) -> str | None:
    """content_type по содержимому файла (заявленному клиентом типу не верим) или None, если формат не поддержан."""
    photo_type = next((ct for magic, (ct, _) in PHOTO_FORMATS.items() if data.startswith(magic)), None)
    if photo_type is not None:
        return photo_type
    # MP4: с 4-го байта «ftyp», за ним бренд. Бренд «qt  » — это MOV
    if data[4:8] == b"ftyp" and data[8:12] != b"qt  ":
        return VIDEO_TYPE
    return None


def max_media_size(content_type: str) -> int:
    return MAX_VIDEO_SIZE if is_video_type(content_type) else MAX_PHOTO_SIZE


async def _optimize(photo: NewPhoto) -> NewPhoto:
    """Сжимает фото из Mini App: там приходят оригиналы с камеры (5–10 МБ, с GPS в EXIF).

    Фото из Telegram уже сжаты и без EXIF — пережатие только ухудшило бы их. Видео не трогаем.
    """
    if photo.tg_file_id is not None or is_video_type(photo.content_type):
        return photo
    try:
        data = await images.compress_photo(photo.data)
    except images.ImageError as e:
        raise AppError("Не удалось открыть одно из фото — возможно, файл повреждён") from e
    return NewPhoto(data=data, content_type="image/jpeg")


def _media_extension(content_type: str) -> str:
    if is_video_type(content_type):
        return "mp4"
    return next((ext for ct, ext in PHOTO_FORMATS.values() if ct == content_type), "jpg")


def can_review(date: DateEvent, reviews: list[DateReview], user_id: int) -> bool:
    """Те же условия, что в check_can_review, но по уже загруженным данным — для показа кнопки."""
    return (
        date.status == REVIEWABLE_STATUS
        and all(review.author_id != user_id for review in reviews)
    )


def reviews_reveal_at(date: DateEvent) -> datetime:
    """Когда отзывы открываются всем, даже тем, кто свой не написал."""
    return (date.done_at or date.starts_at) + REVIEWS_REVEAL_AFTER


def can_see_review(date: DateEvent, reviews: list[DateReview], review: DateReview, user_id: int) -> bool:
    """Отзыв партнёра виден, только если пользователь оставил свой или прошло REVIEWS_REVEAL_AFTER."""
    return (
        review.author_id == user_id
        or any(other.author_id == user_id for other in reviews)
        or datetime.now(UTC) >= reviews_reveal_at(date)
    )


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ReviewRepository(session)
        self.dates = DateService(session)

    async def check_can_review(self, date_id: UUID, author_id: int) -> DateEvent:
        """Проверяет, что пользователь может оставить отзыв, и возвращает свидание."""
        date = await self.dates.get_for_user(date_id, author_id)
        if date.status != REVIEWABLE_STATUS:
            raise ConflictError("Отзыв можно оставить только после того, как свидание состоялось")
        if await self.repo.get_by_author(date_id, author_id) is not None:
            raise ConflictError("Вы уже оставили отзыв на это свидание")
        return date

    async def list_reviewable_dates(self, user_id: int) -> list[DateEvent]:
        return await self.repo.list_reviewable_dates(user_id)

    async def take_review_reminders(self) -> list[tuple[DateEvent, list[User]]]:
        """Свидания, по которым пора напомнить об отзыве, и кому — тем, кто его ещё не оставил.

        Напоминание одно на свидание: оно сразу отмечается отправленным.
        """
        now = datetime.now(UTC)
        due: list[tuple[DateEvent, list[User]]] = []
        for date in await self.repo.list_to_remind(now - REVIEW_REMINDER_MAX_AGE, now - REVIEW_REMINDER_AFTER):
            date.review_reminder_sent_at = now
            reviewed = {review.author_id for review in await self.repo.list_for_date(date.id)}
            users = [user for user in (date.creator, date.invitee) if user.id not in reviewed]
            if users:
                due.append((date, users))
        await self.session.commit()
        return due

    async def list_for_date(self, date_id: UUID) -> list[DateReview]:
        return await self.repo.list_for_date(date_id)

    async def get_photo(self, photo_id: UUID, user_id: int) -> DateReviewPhoto:
        """Фото отзыва, если пользователь участник свидания и отзыв ему уже открыт."""
        photo = await self.repo.get_photo(photo_id)
        if photo is None:
            raise NotFoundError("Фото не найдено")
        review = await self.repo.get(photo.review_id)
        if review is None:
            raise NotFoundError("Фото не найдено")
        date = await self.dates.get_for_user(review.date_id, user_id)
        if not can_see_review(date, await self.repo.list_for_date(date.id), review, user_id):
            raise NotFoundError("Фото не найдено")
        return photo

    async def create(
        self,
        date_id: UUID,
        author_id: int,
        rating: int,
        liked: str | None = None,
        disliked: str | None = None,
        food: str | None = None,
        comment: str | None = None,
        photos: list[NewPhoto] | None = None,
    ) -> DateReview:
        """Сохраняет отзыв: сначала файлы в хранилище, потом строки в БД."""
        photos = photos or []
        if not 1 <= rating <= 5:
            raise AppError("Оценка должна быть от 1 до 5")
        if len(photos) > MAX_REVIEW_PHOTOS:
            raise AppError(f"Можно прикрепить не больше {MAX_REVIEW_PHOTOS} фото и видео")
        for photo in photos:
            if len(photo.data) > max_media_size(photo.content_type):
                kind = "Видео" if is_video_type(photo.content_type) else "Фото"
                raise AppError(f"{kind} больше {max_media_size(photo.content_type) // 1024 // 1024} МБ")
        _ = await self.check_can_review(date_id, author_id)
        photos = [await _optimize(photo) for photo in photos]

        review = DateReview(
            id=uuid4(),
            date_id=date_id,
            author_id=author_id,
            rating=rating,
            liked=liked,
            disliked=disliked,
            food=food,
            comment=comment,
        )
        uploaded: list[str] = []
        try:
            for position, photo in enumerate(photos):
                photo_id = uuid4()
                key = f"reviews/{review.id}/{photo_id}.{_media_extension(photo.content_type)}"
                await storage.upload(key, photo.data, photo.content_type)
                uploaded.append(key)
                review.photos.append(
                    DateReviewPhoto(
                        id=photo_id,
                        position=position,
                        key=key,
                        tg_file_id=photo.tg_file_id,
                        content_type=photo.content_type,
                        size=len(photo.data),
                    )
                )
            _ = await self.repo.create(review)
            await self.session.commit()
        except Exception as e:
            # Отзыв не сохранился — убираем уже загруженные файлы, чтобы не копить мусор в бакете
            await self.session.rollback()
            await self._delete_files(uploaded)
            if isinstance(e, IntegrityError):  # параллельный запрос успел создать отзыв раньше
                raise ConflictError("Вы уже оставили отзыв на это свидание") from e
            raise
        return review

    async def _delete_files(self, keys: list[str]) -> None:
        for key in keys:
            try:
                await storage.delete(key)
            except Exception:
                logger.exception("Не удалось удалить файл %s из хранилища", key)
