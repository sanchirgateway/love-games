import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

MAX_FLOWER_PHOTOS = 10  # от каждого участника: столько влезает в один media group при показе


class FlowerOccasion(enum.StrEnum):
    """Повод. Подписи для показа — в keyboards."""

    NO_REASON = "no_reason"
    DATE = "date"
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    HOLIDAY = "holiday"
    APOLOGY = "apology"


class FlowerReaction(enum.StrEnum):
    """Реакция получателя одной кнопкой. Эмодзи для показа — в keyboards."""

    LOVED = "loved"  # 😍
    TOUCHED = "touched"  # 🥹
    HAPPY = "happy"  # 😊
    MEH = "meh"  # 😐


class FlowerPhotoAuthor(enum.StrEnum):
    """Чьи фото букетов показывать в общей ленте."""

    MINE = "mine"
    PARTNER = "partner"
    ALL = "all"


class FlowerGift(Base):
    """Подаренный букет. Пока given_at пустой — это сюрприз: получатель запись не видит."""

    __tablename__ = "flower_gifts"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_flower_gifts_price_non_negative"),
        CheckConstraint("giver_id <> recipient_id", name="ck_flower_gifts_not_self"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    giver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date_id: Mapped[UUID | None] = mapped_column(ForeignKey("dates.id", ondelete="SET NULL"))

    flowers: Mapped[str] = mapped_column(Text)  # «15 белых роз»
    occasion: Mapped[FlowerOccasion | None] = mapped_column(
        Enum(FlowerOccasion, name="flower_occasion", values_callable=lambda e: [m.value for m in e])
    )
    comment: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int | None] = mapped_column(Integer)  # в рублях; видит только тот, кто дарил

    given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)  # UTC
    reaction: Mapped[FlowerReaction | None] = mapped_column(
        Enum(FlowerReaction, name="flower_reaction", values_callable=lambda e: [m.value for m in e])
    )
    reacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Удаление строк каскадное, но файлы в хранилище нужно удалять отдельно по key
    photos: Mapped[list["FlowerGiftPhoto"]] = relationship(
        back_populates="gift",
        lazy="selectin",
        order_by="FlowerGiftPhoto.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_given(self) -> bool:
        return self.given_at is not None

    def photos_by(self, author_id: int) -> list["FlowerGiftPhoto"]:
        return [photo for photo in self.photos if photo.author_id == author_id]


class FlowerGiftPhoto(Base):
    """Фото букета от дарителя (сам букет) или от получателя (например, букет в вазе).

    Всегда JPEG: из Telegram приходит JPEG, из Mini App сжимается в JPEG. position — свой у каждого автора.
    """

    __tablename__ = "flower_gift_photos"
    __table_args__ = (
        UniqueConstraint("gift_id", "author_id", "position", name="uq_flower_gift_photos_position"),
        CheckConstraint(
            f"position BETWEEN 0 AND {MAX_FLOWER_PHOTOS - 1}", name="ck_flower_gift_photos_position_range"
        ),
        CheckConstraint("size > 0", name="ck_flower_gift_photos_size_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    gift_id: Mapped[UUID] = mapped_column(ForeignKey("flower_gifts.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)

    key: Mapped[str] = mapped_column(Text, unique=True)  # flowers/<gift_id>/<photo_id>.jpg
    # file_id в Telegram: есть у фото, присланных боту. У загруженных через Mini App — None
    tg_file_id: Mapped[str | None] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)

    gift: Mapped[FlowerGift] = relationship(back_populates="photos")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
