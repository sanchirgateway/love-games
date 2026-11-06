from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.feature.bouquets.catalog import Flower, in_catalog_order
from app.feature.flowers.models import FlowerOccasion, FlowerReaction


class VirtualBouquet(Base):
    """Виртуальный букет, собранный из цветов каталога. Партнёр видит его сразу после отправки.

    Хранится только состав, картинка рисуется по нему: так перерисованные цветы обновят и старые букеты.
    """

    __tablename__ = "virtual_bouquets"
    __table_args__ = (CheckConstraint("sender_id <> recipient_id", name="ck_virtual_bouquets_not_self"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # [{"flower": "rose_red", "count": 7}, ...] — коды из catalog.FLOWERS, проверяются в сервисе
    composition: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    vase: Mapped[str | None] = mapped_column(Text)  # код из catalog.VASES; пусто — букет в обёртке
    # Типы enum общие с журналом настоящих букетов
    occasion: Mapped[FlowerOccasion | None] = mapped_column(
        Enum(FlowerOccasion, name="flower_occasion", values_callable=lambda e: [m.value for m in e])
    )
    card: Mapped[str | None] = mapped_column(Text)  # текст открытки
    # Картинка, уже загруженная в Telegram: показываем её повторно, не перерисовывая.
    # После смены картинок цветов старые file_id стоит обнулить — иначе останутся старые картинки
    tg_file_id: Mapped[str | None] = mapped_column(Text)

    reaction: Mapped[FlowerReaction | None] = mapped_column(
        Enum(FlowerReaction, name="flower_reaction", values_callable=lambda e: [m.value for m in e])
    )
    reacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def items(self) -> list[tuple[Flower, int]]:
        """Состав с цветами из каталога. Цветок, убранный из каталога, пропускается, а не роняет показ."""
        return in_catalog_order({item["flower"]: item["count"] for item in self.composition})

    @property
    def total(self) -> int:
        return sum(count for _, count in self.items)
