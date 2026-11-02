from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.feature.ideas.models import IdeaVote
from app.feature.ideas.service import PLACE_MAX, TEXT_MAX, TITLE_MAX


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX, examples=["Сплав на байдарках"])
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    place: str | None = Field(default=None, max_length=PLACE_MAX)


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    place: str | None
    created_by: int | None  # null — встроенная идея
    is_builtin: bool
    created_at: datetime


class IdeaVoteIn(BaseModel):
    vote: IdeaVote


class IdeaVoteOut(BaseModel):
    idea: IdeaOut
    matched: bool  # true — совпадение случилось этим ответом, обоим ушло уведомление в Telegram


class IdeaPlanIn(BaseModel):
    starts_at: AwareDatetime = Field(examples=["2026-11-07T19:00:00+03:00"])
    place: str | None = Field(default=None, max_length=PLACE_MAX)  # не передано — место из идеи
