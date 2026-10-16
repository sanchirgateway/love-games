from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReviewPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID  # файл: GET /api/v1/reviews/photos/{id}
    position: int
    content_type: str  # image/jpeg, image/png или video/mp4
    size: int


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date_id: UUID
    author_id: int
    rating: int
    liked: str | None
    disliked: str | None
    food: str | None
    comment: str | None
    photos: list[ReviewPhotoOut]
    created_at: datetime


class LockedReviewOut(BaseModel):
    """Отзыв партнёра, который пока скрыт: известно только, что он есть."""

    model_config = ConfigDict(from_attributes=True)

    author_id: int
    created_at: datetime


class DateReviewsOut(BaseModel):
    can_review: bool  # можно ли текущему пользователю оставить отзыв
    reviews: list[ReviewOut]  # открытые текущему пользователю (включая его собственный)
    locked: list[LockedReviewOut]  # скрытые до тех пор, пока пользователь не напишет свой
    reveal_at: datetime  # когда скрытые отзывы откроются, даже если свой не написан


class ReviewCreated(BaseModel):
    review: ReviewOut
    locked_for_partner: bool  # партнёр увидит отзыв только после того, как напишет свой
