from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.feature.wishlist.models import WishItem
from app.feature.wishlist.service import PRICE_MAX, TEXT_MAX, TITLE_MAX, URL_MAX, reserved_by_viewer


class WishCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX, examples=["Плёночный фотоаппарат"])
    url: str | None = Field(default=None, max_length=URL_MAX, examples=["https://example.com/camera"])
    price: int | None = Field(default=None, ge=0, le=PRICE_MAX)
    note: str | None = Field(default=None, max_length=TEXT_MAX)


class WishUpdate(BaseModel):
    """Меняются только переданные поля. url, note: "" — стереть; price: null — стереть."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    url: str | None = Field(default=None, max_length=URL_MAX)
    price: int | None = Field(default=None, ge=0, le=PRICE_MAX)
    note: str | None = Field(default=None, max_length=TEXT_MAX)


class WishOut(BaseModel):
    id: UUID
    owner_id: int
    title: str
    url: str | None
    price: int | None
    note: str | None
    reserved_by_me: bool  # владельцу всегда false: бронь партнёра — сюрприз
    received_at: datetime | None  # не null — желание исполнено
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, item: WishItem, viewer_id: int) -> "WishOut":
        return cls(
            id=item.id,
            owner_id=item.owner_id,
            title=item.title,
            url=item.url,
            price=item.price,
            note=item.note,
            reserved_by_me=reserved_by_viewer(item, viewer_id),
            received_at=item.received_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
