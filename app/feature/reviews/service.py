import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.errors import AppError, ConflictError
from app.feature.dates.models import DateEvent
from app.feature.dates.service import DateService
from app.feature.reviews.models import MAX_REVIEW_PHOTOS, DateReview, DateReviewPhoto
from app.feature.reviews.repository import REVIEWABLE_STATUS, ReviewRepository
from app.feature.user.models import User

logger = logging.getLogger(__name__)

# Через сколько после того, как свидание состоялось, мягко напомнить об отзыве
REVIEW_REMINDER_AFTER = timedelta(days=1)
# О давних свиданиях не напоминаем: после простоя бота такие напоминания пришли бы пачкой
REVIEW_REMINDER_MAX_AGE = timedelta(days=2)
# Отзыв партнёра скрыт, пока не напишешь свой. Если так и не написал — откроется через это время
REVIEWS_REVEAL_AFTER = timedelta(days=7)


@dataclass(frozen=True)
class NewPhoto:
    data: bytes
    content_type: str
    tg_file_id: str


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
            raise AppError(f"Можно прикрепить не больше {MAX_REVIEW_PHOTOS} фото")
        _ = await self.check_can_review(date_id, author_id)

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
                key = f"reviews/{review.id}/{photo_id}.jpg"
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
