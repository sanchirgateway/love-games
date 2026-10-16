import enum
from datetime import datetime
import uuid

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class GameStatus(enum.StrEnum):
    PLAYING = "playing"  # проходим
    COMPLETED = "completed"  # прошли
    DROPPED = "dropped"  # бросили


class Game(Base):
    """Игра в каталоге пары. Видна обоим: автору и его партнёру."""

    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, name="game_status", values_callable=lambda e: [m.value for m in e]),
        default=GameStatus.PLAYING,
        server_default=GameStatus.PLAYING.value,
    )

    # Обложка лежит в S3 под ключом games/<game_id>/<cover_id>.jpg (сжимается в JPEG). Без обложки все три поля — None.
    # При замене ключ новый, поэтому клиент не покажет старую картинку из кэша; старый файл удалить отдельно
    cover_key: Mapped[str | None] = mapped_column(Text, unique=True)
    # file_id в Telegram: есть у обложки, присланной боту, — по нему бот показывает её без скачивания
    cover_tg_file_id: Mapped[str | None] = mapped_column(Text)
    cover_content_type: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_cover(self) -> bool:
        return self.cover_key is not None


class GameSession(Base):
    """Один игровой вечер: «играли в Cuphead 12.10, прошли первый остров»."""

    __tablename__ = "game_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    date_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dates.id", ondelete="SET NULL"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # UTC, можно задним числом
    description: Mapped[str | None] = mapped_column(Text)  # что сделали за вечер

    game: Mapped[Game] = relationship(lazy="joined")
    reviews: Mapped[list["GameSessionReview"]] = relationship(
        back_populates="session",
        lazy="selectin",
        order_by="GameSessionReview.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GameMood(enum.StrEnum):
    """Эмоция после вечера одной кнопкой. Эмодзи для показа — в keyboards."""

    LOVED = "loved"  # 😍
    FUN = "fun"  # 😂
    ANGRY = "angry"  # 😤
    TIRED = "tired"  # 😴


class GameSessionReview(Base):
    """Впечатления одного из участников после игрового вечера."""

    __tablename__ = "game_session_reviews"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "author_id", name="uq_game_session_reviews_session_author"
        ),  # один отзыв от участника
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_game_session_reviews_rating_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    rating: Mapped[int] = mapped_column(SmallInteger)
    mood: Mapped[GameMood | None] = mapped_column(
        Enum(GameMood, name="game_mood", values_callable=lambda e: [m.value for m in e])
    )
    liked: Mapped[str | None] = mapped_column(Text)
    disliked: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)

    session: Mapped[GameSession] = relationship(back_populates="reviews")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
