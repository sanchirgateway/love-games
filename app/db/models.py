import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", server_default="Europe/Moscow")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    dates: Mapped[list["DateEvent"]] = relationship(back_populates="creator", cascade="all, delete-orphan")


class DateStatus(enum.StrEnum):
    PLANNED = "planned"
    DONE = "done"
    CANCELLED = "cancelled"


class DateEvent(Base):
    __tablename__ = "dates"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_dates_rating_range"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_dates_ends_after_starts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    place: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # UTC
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[DateStatus] = mapped_column(
        Enum(DateStatus, name="date_status", values_callable=lambda e: [m.value for m in e]),
        default=DateStatus.PLANNED,
        server_default=DateStatus.PLANNED.value,
        index=True,
    )


    rating: Mapped[int | None] = mapped_column(SmallInteger)
    review: Mapped[str | None] = mapped_column(Text)

    remind_two_day_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_day_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_hours_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    creator: Mapped["User"] = relationship(back_populates="dates")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
