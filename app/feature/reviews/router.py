import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.core import storage
from app.core.api import BotDep, SessionDep
from app.feature.dates.models import DateEvent
from app.feature.dates.schemas import DateOut
from app.feature.dates.service import DateService
from app.feature.reviews import notify
from app.feature.reviews.models import MAX_REVIEW_PHOTOS, MAX_REVIEW_TEXT_LENGTH
from app.feature.reviews.schemas import (
    DateReviewsOut,
    LockedReviewOut,
    ReviewCreated,
    ReviewOut,
)
from app.feature.reviews.service import (
    MAX_PHOTO_SIZE,
    NewPhoto,
    ReviewService,
    can_review,
    can_see_review,
    detect_photo_type,
    reviews_reveal_at,
)
from app.feature.user.dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])

ReviewText = Annotated[str | None, Form(max_length=MAX_REVIEW_TEXT_LENGTH)]


def _clean(value: str | None) -> str | None:
    """Пустая строка из формы — это «не заполнено»."""
    value = (value or "").strip()
    return value or None


async def _read_photos(files: list[UploadFile]) -> list[NewPhoto]:
    if len(files) > MAX_REVIEW_PHOTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Можно прикрепить не больше {MAX_REVIEW_PHOTOS} фото")
    photos: list[NewPhoto] = []
    for file in files:
        data = await file.read(MAX_PHOTO_SIZE + 1)
        if len(data) > MAX_PHOTO_SIZE:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, f"Фото {file.filename} больше {MAX_PHOTO_SIZE // 1024 // 1024} МБ"
            )
        content_type = detect_photo_type(data)
        if content_type is None:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Фото {file.filename}: поддерживаются только JPEG и PNG"
            )
        photos.append(NewPhoto(data=data, content_type=content_type))
    return photos


@router.get("/reviews/pending", response_model=list[DateOut])
async def list_pending(user: CurrentUser, session: SessionDep) -> list[DateEvent]:
    """Состоявшиеся свидания, на которые пользователь ещё не оставил отзыв."""
    return await ReviewService(session).list_reviewable_dates(user.id)


@router.get("/dates/{date_id}/reviews", response_model=DateReviewsOut)
async def list_reviews(date_id: UUID, user: CurrentUser, session: SessionDep) -> DateReviewsOut:
    date = await DateService(session).get_for_user(date_id, user.id)
    reviews = await ReviewService(session).list_for_date(date.id)
    visible = [review for review in reviews if can_see_review(date, reviews, review, user.id)]
    return DateReviewsOut(
        can_review=can_review(date, reviews, user.id),
        reviews=[ReviewOut.model_validate(review) for review in visible],
        locked=[LockedReviewOut.model_validate(review) for review in reviews if review not in visible],
        reveal_at=reviews_reveal_at(date),
    )


@router.post("/dates/{date_id}/reviews", response_model=ReviewCreated, status_code=status.HTTP_201_CREATED)
async def create_review(
    date_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bot: BotDep,
    rating: Annotated[int, Form(ge=1, le=5)],
    liked: ReviewText = None,
    disliked: ReviewText = None,
    food: ReviewText = None,
    comment: ReviewText = None,
    photos: Annotated[list[UploadFile] | None, File(description=f"До {MAX_REVIEW_PHOTOS} фото, JPEG или PNG")] = None,
) -> ReviewCreated:
    service = ReviewService(session)
    review = await service.create(
        date_id=date_id,
        author_id=user.id,
        rating=rating,
        liked=_clean(liked),
        disliked=_clean(disliked),
        food=_clean(food),
        comment=_clean(comment),
        photos=await _read_photos(photos or []),
    )

    date = await DateService(session).get_for_user(date_id, user.id)
    reviews = await service.list_for_date(date.id)
    partner = date.invitee if review.author_id == date.created_by else date.creator
    locked = not can_see_review(date, reviews, review, partner.id)
    # Отзыв уже сохранён: сбой уведомлений не должен превращать ответ в ошибку
    try:
        await notify.announce_review(bot, review, date, reviews, locked)
    except Exception:
        logger.exception("Не удалось разослать уведомления об отзыве %s", review.id)

    return ReviewCreated(review=ReviewOut.model_validate(review), locked_for_partner=locked)


@router.get(
    "/reviews/photos/{photo_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
)
async def get_photo(photo_id: UUID, user: CurrentUser, session: SessionDep) -> Response:
    photo = await ReviewService(session).get_photo(photo_id, user.id)
    data = await storage.download(photo.key)
    # Файл по id никогда не меняется — пусть клиент кэширует
    return Response(content=data, media_type=photo.content_type, headers={"Cache-Control": "private, max-age=604800"})
