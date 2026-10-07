from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

MAX_REVIEW_PHOTOS = 10  # столько влезает в один media group при показе


class DateReview(Base):
    __tablename__ = "date_reviews"
    __table_args__ = (
        UniqueConstraint("date_id", "author_id", name="uq_date_reviews_date_author"),  # один отзыв от участника
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_date_reviews_rating_range"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    date_id: Mapped[UUID] = mapped_column(ForeignKey("dates.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    rating: Mapped[int] = mapped_column(SmallInteger)
    liked: Mapped[str | None] = mapped_column(Text)
    disliked: Mapped[str | None] = mapped_column(Text)
    food: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)

    # lazy="selectin": фото подгружаются одним доп. запросом (joined размножил бы строки отзыва).
    # Удаление строк каскадное, но файлы в хранилище нужно удалять отдельно по key.
    photos: Mapped[list["DateReviewPhoto"]] = relationship(
        back_populates="review",
        lazy="selectin",
        order_by="DateReviewPhoto.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DateReviewPhoto(Base):
    __tablename__ = "date_review_photos"
    __table_args__ = (
        UniqueConstraint("review_id", "position", name="uq_date_review_photos_position"),
        CheckConstraint(
            f"position BETWEEN 0 AND {MAX_REVIEW_PHOTOS - 1}", name="ck_date_review_photos_position_range"
        ),
        CheckConstraint("size > 0", name="ck_date_review_photos_size_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("date_reviews.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)

    key: Mapped[str] = mapped_column(Text, unique=True)
    tg_file_id: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)

    review: Mapped[DateReview] = relationship(back_populates="photos")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
