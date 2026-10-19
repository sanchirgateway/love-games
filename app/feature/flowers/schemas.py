from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.feature.flowers.models import FlowerGift, FlowerOccasion, FlowerReaction


class FlowerPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID  # файл: GET /api/v1/flowers/photos/{id}
    author_id: int  # даритель — сам букет, получатель — например, букет в вазе
    position: int  # своя у каждого автора
    size: int


class FlowerGiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    giver_id: int
    recipient_id: int
    date_id: UUID | None
    flowers: str
    occasion: FlowerOccasion | None
    comment: str | None
    price: int | None  # только для дарителя, получателю всегда null
    given_at: datetime | None  # null — ещё не вручён: такие видит только даритель
    reaction: FlowerReaction | None
    reacted_at: datetime | None
    photos: list[FlowerPhotoOut]
    created_at: datetime

    @classmethod
    def for_viewer(cls, gift: FlowerGift, user_id: int) -> "FlowerGiftOut":
        out = cls.model_validate(gift)
        if gift.giver_id != user_id:
            out.price = None
        return out


class FlowerGive(BaseModel):
    given_at: AwareDatetime | None = None  # по умолчанию — сейчас


class FlowerReactionIn(BaseModel):
    reaction: FlowerReaction
