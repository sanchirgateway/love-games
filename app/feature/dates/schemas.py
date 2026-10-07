from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.feature.dates.models import DateStatus
from app.feature.user.schemas import UserShort


class DateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, examples=["Ужин в итальянском ресторане"])
    starts_at: AwareDatetime = Field(examples=["2026-10-12T19:00:00+03:00"])
    ends_at: AwareDatetime | None = None
    place: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    description: str | None = None


class DateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    place: str | None
    address: str | None
    starts_at: datetime
    ends_at: datetime | None
    status: DateStatus
    creator: UserShort
    invitee: UserShort
    created_at: datetime
