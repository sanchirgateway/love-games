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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DatePhoto(Base):
    __tablename__ = "date_photos"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    date_id: Mapped[UUID] = mapped_column(ForeignKey("dates.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)  

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
