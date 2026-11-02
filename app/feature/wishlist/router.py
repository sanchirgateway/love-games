from uuid import UUID

from fastapi import APIRouter, status

from app.core.api import BotDep, SessionDep
from app.feature.user.dependencies import CurrentUser
from app.feature.wishlist import notify
from app.feature.wishlist.schemas import WishCreate, WishOut, WishUpdate
from app.feature.wishlist.service import WishlistService

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.get("/mine", response_model=list[WishOut])
async def list_mine(user: CurrentUser, session: SessionDep) -> list[WishOut]:
    """Свой вишлист: сначала то, что ещё хочется, потом исполненное. Брони партнёра здесь не видно."""
    return [WishOut.build(item, user.id) for item in await WishlistService(session).list_mine(user.id)]


@router.get("/partner", response_model=list[WishOut])
async def list_partner(user: CurrentUser, session: SessionDep) -> list[WishOut]:
    """Вишлист партнёра. reserved_by_me — вы забронировали это желание."""
    return [WishOut.build(item, user.id) for item in await WishlistService(session).list_partner(user.id)]


@router.post("", response_model=WishOut, status_code=status.HTTP_201_CREATED)
async def create_wish(body: WishCreate, user: CurrentUser, session: SessionDep, bot: BotDep) -> WishOut:
    """Добавить желание. Партнёру в Telegram приходит уведомление с кнопкой брони."""
    service = WishlistService(session)
    item = await service.create(user.id, body.title, body.url, body.price, body.note)
    owner, partner = await service.couple(user.id)
    await notify.send_new_wish(bot, item, owner, partner)
    return WishOut.build(item, user.id)


@router.get("/{item_id}", response_model=WishOut)
async def get_wish(item_id: UUID, user: CurrentUser, session: SessionDep) -> WishOut:
    return WishOut.build(await WishlistService(session).get(item_id, user.id), user.id)


@router.patch("/{item_id}", response_model=WishOut)
async def update_wish(item_id: UUID, body: WishUpdate, user: CurrentUser, session: SessionDep) -> WishOut:
    """Изменить своё желание. Чужое — 403."""
    item = await WishlistService(session).update(
        item_id,
        user.id,
        title=body.title,
        url=body.url,
        note=body.note,
        price=body.price,
        clear_price="price" in body.model_fields_set and body.price is None,
    )
    return WishOut.build(item, user.id)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wish(item_id: UUID, user: CurrentUser, session: SessionDep, bot: BotDep) -> None:
    """Удалить своё желание. Если партнёр его забронировал, ему приходит уведомление."""
    service = WishlistService(session)
    title, reserver = await service.delete(item_id, user.id)
    if reserver is not None:
        await notify.send_deleted(bot, title, await service.users.get(user.id), reserver)


@router.post("/{item_id}/reserve", response_model=WishOut)
async def reserve_wish(item_id: UUID, user: CurrentUser, session: SessionDep) -> WishOut:
    """Тайно забронировать желание партнёра: «подарю я». Своё — 403, исполненное или уже своё — 409."""
    return WishOut.build(await WishlistService(session).reserve(item_id, user.id), user.id)


@router.delete("/{item_id}/reserve", response_model=WishOut)
async def unreserve_wish(item_id: UUID, user: CurrentUser, session: SessionDep) -> WishOut:
    return WishOut.build(await WishlistService(session).unreserve(item_id, user.id), user.id)


@router.post("/{item_id}/receive", response_model=WishOut)
async def receive_wish(item_id: UUID, user: CurrentUser, session: SessionDep, bot: BotDep) -> WishOut:
    """Отметить своё желание исполненным. Если партнёр его бронировал, ему приходит уведомление."""
    service = WishlistService(session)
    item, reserver = await service.receive(item_id, user.id)
    if reserver is not None:
        await notify.send_received(bot, item, await service.users.get(user.id), reserver)
    return WishOut.build(item, user.id)


@router.delete("/{item_id}/receive", response_model=WishOut)
async def unreceive_wish(item_id: UUID, user: CurrentUser, session: SessionDep) -> WishOut:
    """«Снова хочу»: вернуть исполненное желание в список, бронь сбрасывается."""
    return WishOut.build(await WishlistService(session).unreceive(item_id, user.id), user.id)
