import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.feature.user.models import User


class DateStatus(enum.StrEnum):
    PROPOSED = "proposed"  # предложено, ждём ответа приглашённого
    PLANNED = "planned"  # принято
    DECLINED = "declined"  # приглашённый отказался
    DONE = "done"
    CANCELLED = "cancelled"


class DateEvent(Base):
    __tablename__ = "dates"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_dates_ends_after_starts"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
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

    remind_two_day_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_day_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_hours_before_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # lazy="joined": автор и приглашённый подгружаются тем же запросом (в async ленивая загрузка не работает)
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")
    invitee: Mapped[User] = relationship(foreign_keys=[invitee_id], lazy="joined")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
