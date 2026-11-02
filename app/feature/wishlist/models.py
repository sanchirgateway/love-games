from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WishItem(Base):
    """Желание из вишлиста. Видят владелец и его партнёр.

    Бронь (reserved_by) — тайная: партнёр отмечает, что купит это, а владелец её не видит, чтобы был сюрприз.
    """

    __tablename__ = "wish_items"
    __table_args__ = (CheckConstraint("price IS NULL OR price >= 0", name="ck_wish_items_price_non_negative"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))
    price: Mapped[int | None] = mapped_column(Integer)  # примерная цена в рублях
    note: Mapped[str | None] = mapped_column(Text)  # размер, цвет, где купить

    reserved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # владелец отметил «получил»

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_received(self) -> bool:
        return self.received_at is not None
