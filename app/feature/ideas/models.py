import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IdeaVote(enum.StrEnum):
    YES = "yes"  # 👍 хочу
    NO = "no"  # 👎 не хочу


class DateIdea(Base):
    """Идея для свидания. created_by пустой — встроенная, её видят все пары; иначе — видит автор и его партнёр."""

    __tablename__ = "date_ideas"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    place: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def is_builtin(self) -> bool:
        return self.created_by is None


class DateIdeaVote(Base):
    """Ответ пользователя на идею. Совпадение — когда оба из пары ответили «хочу»."""

    __tablename__ = "date_idea_votes"

    idea_id: Mapped[UUID] = mapped_column(ForeignKey("date_ideas.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    vote: Mapped[IdeaVote] = mapped_column(
        Enum(IdeaVote, name="idea_vote", values_callable=lambda e: [m.value for m in e])
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
