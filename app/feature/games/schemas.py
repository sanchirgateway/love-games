from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.feature.games.models import GameMood, GameStatus
from app.feature.games.service import TEXT_MAX, TITLE_MAX


class GameCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX, examples=["Cuphead"])
    description: str | None = Field(default=None, max_length=TEXT_MAX)


class GameUpdate(BaseModel):
    """Меняются только переданные поля. description: "" — стереть описание."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    status: GameStatus | None = None


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    status: GameStatus
    created_by: int
    has_cover: bool  # файл: GET /api/v1/games/{id}/cover
    created_at: datetime
    updated_at: datetime


class GameSessionCreate(BaseModel):
    played_at: AwareDatetime = Field(examples=["2026-10-12T21:00:00+03:00"])
    description: str | None = Field(default=None, max_length=TEXT_MAX, examples=["Прошли первый остров"])
    date_id: UUID | None = None  # свидание, во время которого играли


class GameReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    mood: GameMood | None = None
    liked: str | None = Field(default=None, max_length=TEXT_MAX)
    disliked: str | None = Field(default=None, max_length=TEXT_MAX)
    comment: str | None = Field(default=None, max_length=TEXT_MAX)


class GameReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    author_id: int
    rating: int
    mood: GameMood | None
    liked: str | None
    disliked: str | None
    comment: str | None
    created_at: datetime


class LockedGameReviewOut(BaseModel):
    """Отзыв партнёра, который пока скрыт: известно только, что он есть."""

    model_config = ConfigDict(from_attributes=True)

    author_id: int
    created_at: datetime


class GameSessionOut(BaseModel):
    id: UUID
    game_id: UUID
    date_id: UUID | None
    created_by: int
    played_at: datetime
    description: str | None
    created_at: datetime
    can_review: bool  # можно ли текущему пользователю оставить отзыв
    reviews: list[GameReviewOut]  # открытые текущему пользователю (включая его собственный)
    locked: list[LockedGameReviewOut]  # скрытые, пока пользователь не напишет свой
    reveal_at: datetime  # когда скрытые отзывы откроются, даже если свой не написан


class GameReviewCreated(BaseModel):
    review: GameReviewOut
    locked_for_partner: bool  # партнёр увидит отзыв только после того, как напишет свой
