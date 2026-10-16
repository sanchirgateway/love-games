import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile, status

from app.core import storage
from app.core.api import BotDep, SessionDep
from app.feature.games import notify
from app.feature.games.models import Game, GameSession, GameSessionReview
from app.feature.games.schemas import (
    GameCreate,
    GameOut,
    GameReviewCreate,
    GameReviewCreated,
    GameReviewOut,
    GameSessionCreate,
    GameSessionOut,
    GameUpdate,
    LockedGameReviewOut,
)
from app.feature.games.service import COVER_MAX_SIZE, GameService, can_review, can_see_review, reviews_reveal_at
from app.feature.user.dependencies import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["games"])


def _session_out(game_session: GameSession, reviews: list[GameSessionReview], user_id: int) -> GameSessionOut:
    visible = [review for review in reviews if can_see_review(game_session, reviews, review, user_id)]
    return GameSessionOut(
        id=game_session.id,
        game_id=game_session.game_id,
        date_id=game_session.date_id,
        created_by=game_session.created_by,
        played_at=game_session.played_at,
        description=game_session.description,
        created_at=game_session.created_at,
        can_review=can_review(reviews, user_id),
        reviews=[GameReviewOut.model_validate(review) for review in visible],
        locked=[LockedGameReviewOut.model_validate(review) for review in reviews if review not in visible],
        reveal_at=reviews_reveal_at(game_session),
    )


# --- игры ---


@router.get("/games", response_model=list[GameOut])
async def list_games(user: CurrentUser, session: SessionDep) -> list[Game]:
    """Игры пары: сначала те, что проходим сейчас."""
    return await GameService(session).list_games(user.id)


@router.post("/games", response_model=GameOut, status_code=status.HTTP_201_CREATED)
async def create_game(body: GameCreate, user: CurrentUser, session: SessionDep) -> Game:
    return await GameService(session).create_game(user.id, body.title, body.description)


@router.get("/games/{game_id}", response_model=GameOut)
async def get_game(game_id: UUID, user: CurrentUser, session: SessionDep) -> Game:
    return await GameService(session).get_game(game_id, user.id)


@router.patch("/games/{game_id}", response_model=GameOut)
async def update_game(game_id: UUID, body: GameUpdate, user: CurrentUser, session: SessionDep) -> Game:
    return await GameService(session).update_game(game_id, user.id, body.title, body.description, body.status)


@router.put("/games/{game_id}/cover", response_model=GameOut)
async def set_cover(
    game_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="Картинка до 10 МБ. Сохраняется сжатой в JPEG")],
) -> Game:
    data = await file.read(COVER_MAX_SIZE + 1)
    if len(data) > COVER_MAX_SIZE:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Обложка больше {COVER_MAX_SIZE // 1024 // 1024} МБ")
    return await GameService(session).set_cover(game_id, user.id, data)


@router.get(
    "/games/{game_id}/cover",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}, 304: {"description": "Обложка не менялась"}},
)
async def get_cover(
    game_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    game = await GameService(session).get_cover(game_id, user.id)
    assert game.cover_key is not None
    # URL обложки не меняется, а файл при замене — новый (новый ключ): по ETag клиент перекачивает только новую
    etag = f'"{game.cover_key.rsplit("/", 1)[-1]}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    data = await storage.download(game.cover_key)
    return Response(content=data, media_type=game.cover_content_type or "image/jpeg", headers=headers)


# --- игровые вечера ---


@router.get("/games/{game_id}/sessions", response_model=list[GameSessionOut])
async def list_sessions(game_id: UUID, user: CurrentUser, session: SessionDep) -> list[GameSessionOut]:
    """Вечера игры, свежие первыми, с отзывами (с учётом скрытия)."""
    sessions = await GameService(session).list_sessions(game_id, user.id)
    return [_session_out(game_session, game_session.reviews, user.id) for game_session in sessions]


@router.post("/games/{game_id}/sessions", response_model=GameSessionOut, status_code=status.HTTP_201_CREATED)
async def log_session(
    game_id: UUID, body: GameSessionCreate, user: CurrentUser, session: SessionDep, bot: BotDep
) -> GameSessionOut:
    """Записать вечер. Партнёру в Telegram приходит просьба поделиться впечатлениями."""
    service = GameService(session)
    game_session = await service.log_session(game_id, user.id, body.played_at, body.description, body.date_id)
    author, partner = await service.couple(user.id)
    await notify.send_review_request(bot, game_session, game_session.game, author, partner)
    return _session_out(game_session, [], user.id)


@router.get("/game-sessions/{session_id}", response_model=GameSessionOut)
async def get_session(session_id: UUID, user: CurrentUser, session: SessionDep) -> GameSessionOut:
    service = GameService(session)
    game_session = await service.get_session(session_id, user.id)
    return _session_out(game_session, await service.list_reviews(game_session.id), user.id)


@router.post(
    "/game-sessions/{session_id}/reviews", response_model=GameReviewCreated, status_code=status.HTTP_201_CREATED
)
async def create_review(
    session_id: UUID, body: GameReviewCreate, user: CurrentUser, session: SessionDep, bot: BotDep
) -> GameReviewCreated:
    service = GameService(session)
    review = await service.create_review(session_id, user.id, **body.model_dump())

    game_session = await service.get_session(session_id, user.id)
    reviews = await service.list_reviews(game_session.id)
    author, partner = await service.couple(user.id)
    locked = not can_see_review(game_session, reviews, review, partner.id)
    # Отзыв уже сохранён: сбой уведомлений не должен превращать ответ в ошибку
    try:
        await notify.announce_review(bot, review, reviews, game_session.game, author, partner, locked)
    except Exception:
        logger.exception("Не удалось разослать уведомления об отзыве на вечер %s", review.id)

    return GameReviewCreated(review=GameReviewOut.model_validate(review), locked_for_partner=locked)
