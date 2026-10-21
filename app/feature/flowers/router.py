import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.core import storage
from app.core.api import BotDep, SessionDep
from app.feature.flowers import notify
from app.feature.flowers.models import MAX_FLOWER_PHOTOS, FlowerGift, FlowerOccasion, FlowerPhotoAuthor
from app.feature.flowers.schemas import FlowerGiftOut, FlowerGive, FlowerPhotoListOut, FlowerReactionIn
from app.feature.flowers.service import (
    FLOWERS_MAX,
    MAX_PHOTO_SIZE,
    PRICE_MAX,
    TEXT_MAX,
    FlowerService,
    NewFlowerPhoto,
)
from app.feature.user.dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["flowers"])


async def _read_photos(files: list[UploadFile]) -> list[NewFlowerPhoto]:
    if len(files) > MAX_FLOWER_PHOTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Можно прикрепить не больше {MAX_FLOWER_PHOTOS} фото")
    photos: list[NewFlowerPhoto] = []
    for file in files:
        data = await file.read(MAX_PHOTO_SIZE + 1)
        if len(data) > MAX_PHOTO_SIZE:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, f"{file.filename} больше {MAX_PHOTO_SIZE // 1024 // 1024} МБ"
            )
        photos.append(NewFlowerPhoto(data=data))
    return photos


async def _notify(session: SessionDep, bot: BotDep, gift: FlowerGift, reaction: bool = False) -> None:
    """Получателю — врученный букет, дарителю (reaction=True) — реакция на него."""
    giver, recipient = await FlowerService(session).participants(gift)
    # Запись уже сохранена: сбой уведомления не должен превращать ответ в ошибку
    try:
        if reaction:
            await notify.send_reaction(bot, gift, giver, recipient)
        else:
            await notify.send_gift(bot, gift, giver, recipient)
    except Exception:
        logger.exception("Не удалось отправить уведомление о букете %s", gift.id)


@router.get("/flowers", response_model=list[FlowerGiftOut])
async def list_flowers(user: CurrentUser, session: SessionDep) -> list[FlowerGiftOut]:
    """Букеты от пользователя (включая невручённые) и врученные ему. Сначала невручённые, потом свежие."""
    gifts = await FlowerService(session).list_for_user(user.id)
    return [FlowerGiftOut.for_viewer(gift, user.id) for gift in gifts]


# Объявлен раньше /flowers/{gift_id}, иначе "photos" попадёт туда как gift_id
@router.get("/flowers/photos", response_model=list[FlowerPhotoListOut])
async def list_photos(
    user: CurrentUser,
    session: SessionDep,
    author: Annotated[
        FlowerPhotoAuthor, Query(description="mine — свои, partner — партнёра, all — свои и партнёра")
    ] = FlowerPhotoAuthor.MINE,
) -> list[FlowerPhotoListOut]:
    """Фото из всех видимых букетов, свежие первыми. Сюрприз партнёра (невручённый букет) не раскрывается."""
    photos = await FlowerService(session).list_photos(user.id, author)
    return [FlowerPhotoListOut.model_validate(photo) for photo in photos]


@router.post("/flowers", response_model=FlowerGiftOut, status_code=status.HTTP_201_CREATED)
async def create_flowers(
    user: CurrentUser,
    session: SessionDep,
    bot: BotDep,
    flowers: Annotated[str, Form(min_length=1, max_length=FLOWERS_MAX)],
    occasion: Annotated[FlowerOccasion | None, Form()] = None,
    comment: Annotated[str | None, Form(max_length=TEXT_MAX)] = None,
    price: Annotated[int | None, Form(ge=0, le=PRICE_MAX)] = None,
    date_id: Annotated[UUID | None, Form()] = None,
    given_at: Annotated[
        datetime | None, Form(description="Когда вручили, с часовым поясом. Не передано — сюрприз, партнёр не видит")
    ] = None,
    photos: Annotated[
        list[UploadFile] | None,
        File(description=f"До {MAX_FLOWER_PHOTOS} фото до 10 МБ. Сохраняются сжатыми в JPEG"),
    ] = None,
) -> FlowerGiftOut:
    """Записать букет партнёру. Если передан given_at, партнёру в Telegram сразу приходят фото и просьба отреагировать."""
    gift = await FlowerService(session).create(
        giver_id=user.id,
        flowers=flowers,
        occasion=occasion,
        comment=comment,
        price=price,
        date_id=date_id,
        given_at=given_at,
        photos=await _read_photos(photos or []),
    )
    if gift.is_given:
        await _notify(session, bot, gift)
    return FlowerGiftOut.for_viewer(gift, user.id)


@router.get("/flowers/{gift_id}", response_model=FlowerGiftOut)
async def get_flowers(gift_id: UUID, user: CurrentUser, session: SessionDep) -> FlowerGiftOut:
    gift = await FlowerService(session).get(gift_id, user.id)
    return FlowerGiftOut.for_viewer(gift, user.id)


@router.post("/flowers/{gift_id}/give", response_model=FlowerGiftOut)
async def give_flowers(
    gift_id: UUID, user: CurrentUser, session: SessionDep, bot: BotDep, body: FlowerGive | None = None
) -> FlowerGiftOut:
    """Даритель подтверждает вручение: партнёр начинает видеть запись и получает её в Telegram."""
    gift = await FlowerService(session).give(gift_id, user.id, body.given_at if body else None)
    await _notify(session, bot, gift)
    return FlowerGiftOut.for_viewer(gift, user.id)


@router.put("/flowers/{gift_id}/reaction", response_model=FlowerGiftOut)
async def react_flowers(
    gift_id: UUID, body: FlowerReactionIn, user: CurrentUser, session: SessionDep, bot: BotDep
) -> FlowerGiftOut:
    """Реакция того, кому подарили. Можно поменять; дарителю приходит уведомление."""
    gift = await FlowerService(session).react(gift_id, user.id, body.reaction)
    await _notify(session, bot, gift, reaction=True)
    return FlowerGiftOut.for_viewer(gift, user.id)


@router.post("/flowers/{gift_id}/photos", response_model=FlowerGiftOut)
async def add_photos(
    gift_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bot: BotDep,
    photos: Annotated[
        list[UploadFile], File(description=f"Фото до 10 МБ; всего от одного участника — до {MAX_FLOWER_PHOTOS}")
    ],
) -> FlowerGiftOut:
    """Дослать фото к букету: получатель — например, букет в вазе, даритель — то, что не приложил сразу.

    Второму участнику фото приходят в Telegram (получателю — только если букет уже вручён).
    """
    service = FlowerService(session)
    added = await _read_photos(photos)
    gift = await service.add_photos(gift_id, user.id, added)
    giver, recipient = await service.participants(gift)
    author, other = (giver, recipient) if user.id == giver.id else (recipient, giver)
    try:
        await notify.send_added_photos(bot, gift, gift.photos_by(author.id)[-len(added) :], author, other)
    except Exception:
        logger.exception("Не удалось отправить новые фото букета %s", gift.id)
    return FlowerGiftOut.for_viewer(gift, user.id)


@router.delete("/flowers/{gift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flowers(gift_id: UUID, user: CurrentUser, session: SessionDep) -> None:
    """Удалить запись вместе с фото. Только даритель."""
    await FlowerService(session).delete(gift_id, user.id)


@router.get(
    "/flowers/photos/{photo_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_photo(photo_id: UUID, user: CurrentUser, session: SessionDep) -> Response:
    photo = await FlowerService(session).get_photo(photo_id, user.id)
    data = await storage.download(photo.key)
    # Файл по id никогда не меняется — пусть клиент кэширует
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})
