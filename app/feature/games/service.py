import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import images, storage
from app.core.errors import AppError, ConflictError, NotFoundError
from app.feature.dates.service import DateService
from app.feature.games.models import Game, GameMood, GameSession, GameSessionReview, GameStatus
from app.feature.games.repository import GameRepository
from app.feature.user.models import User
from app.feature.user.service import UserService

logger = logging.getLogger(__name__)

TITLE_MAX = 200
TEXT_MAX = 2000  # описание игры, описание вечера, каждое текстовое поле отзыва
# Отзыв партнёра о вечере скрыт, пока не напишешь свой. Если так и не написал — откроется через это время
REVIEWS_REVEAL_AFTER = timedelta(days=7)
COVER_MAX_SIZE = 10 * 1024 * 1024  # исходный файл; после сжатия обложка намного меньше
# Запас на расхождение часов клиента и сервера, когда played_at — «сейчас»
PLAYED_AT_SKEW = timedelta(minutes=5)


def reviews_reveal_at(game_session: GameSession) -> datetime:
    """Когда отзывы о вечере открываются всем. Отсчёт от записи, а не от played_at: вечер могут записать задним числом."""
    return game_session.created_at + REVIEWS_REVEAL_AFTER


def can_see_review(
    game_session: GameSession, reviews: list[GameSessionReview], review: GameSessionReview, user_id: int
) -> bool:
    """Отзыв партнёра виден, только если пользователь оставил свой или прошло REVIEWS_REVEAL_AFTER."""
    return (
        review.author_id == user_id
        or any(other.author_id == user_id for other in reviews)
        or datetime.now(UTC) >= reviews_reveal_at(game_session)
    )


def can_review(reviews: list[GameSessionReview], user_id: int) -> bool:
    return all(review.author_id != user_id for review in reviews)


def _clean(value: str | None, field: str) -> str | None:
    """Пустая строка — «не заполнено»."""
    value = (value or "").strip()
    if len(value) > TEXT_MAX:
        raise AppError(f"{field}: не больше {TEXT_MAX} символов")
    return value or None


class GameService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GameRepository(session)
        self.users = UserService(session)

    async def couple(self, user_id: int) -> tuple[User, User]:
        """Пользователь и его партнёр. Без пары играми пользоваться нельзя — AppError."""
        return await self.users.get(user_id), await self.users.get_partner(user_id)

    # --- игры ---

    async def create_game(self, user_id: int, title: str, description: str | None = None) -> Game:
        _ = await self.couple(user_id)  # игры — общие для пары, без пары заводить их некуда
        title = title.strip()
        if not title:
            raise AppError("Напишите название игры")
        if len(title) > TITLE_MAX:
            raise AppError(f"Название слишком длинное — не больше {TITLE_MAX} символов")
        game = await self.repo.create_game(
            Game(created_by=user_id, title=title, description=_clean(description, "Описание"))
        )
        await self.session.commit()
        return game

    async def get_game(self, game_id: UUID, user_id: int) -> Game:
        """Игра, если её завёл пользователь или его партнёр."""
        game = await self.repo.get_game(game_id)
        user = await self.users.get(user_id)
        if game is None or game.created_by not in (user.id, user.partner_id):
            raise NotFoundError("Игра не найдена")
        return game

    async def list_games(self, user_id: int) -> list[Game]:
        user = await self.users.get(user_id)
        owner_ids = [user.id] if user.partner_id is None else [user.id, user.partner_id]
        return await self.repo.list_games(owner_ids)

    async def update_game(
        self,
        game_id: UUID,
        user_id: int,
        title: str | None = None,
        description: str | None = None,
        status: GameStatus | None = None,
    ) -> Game:
        """Меняет переданные поля. description="" — стереть описание."""
        game = await self.get_game(game_id, user_id)
        if title is not None:
            title = title.strip()
            if not title or len(title) > TITLE_MAX:
                raise AppError(f"Название — от 1 до {TITLE_MAX} символов")
            game.title = title
        if description is not None:
            game.description = _clean(description, "Описание")
        if status is not None:
            game.status = status
        await self._commit_game(game)
        return game

    async def set_cover(self, game_id: UUID, user_id: int, data: bytes, tg_file_id: str | None = None) -> Game:
        """Ставит обложку: сначала новый файл в хранилище, потом строка в БД, старый файл — в самом конце."""
        game = await self.get_game(game_id, user_id)
        # Фото из Telegram уже сжаты — пережимаем только загруженные из Mini App (оригиналы с камеры, с EXIF)
        if tg_file_id is None:
            try:
                data = await images.compress_photo(data)
            except images.ImageError as e:
                raise AppError("Не удалось открыть картинку — пришлите JPEG или PNG") from e

        old_key = game.cover_key
        new_key = f"games/{game.id}/{uuid4()}.jpg"
        await storage.upload(new_key, data, "image/jpeg")
        try:
            game.cover_key = new_key
            game.cover_tg_file_id = tg_file_id
            game.cover_content_type = "image/jpeg"
            await self._commit_game(game)
        except Exception:
            await self.session.rollback()
            await _delete_file(new_key)
            raise
        if old_key is not None:
            await _delete_file(old_key)
        return game

    async def _commit_game(self, game: Game) -> None:
        await self.session.commit()
        # updated_at считает база (onupdate) — без перечитывания async-сессия упадёт при попытке его прочитать
        await self.session.refresh(game, ["updated_at"])

    async def get_cover(self, game_id: UUID, user_id: int) -> Game:
        game = await self.get_game(game_id, user_id)
        if game.cover_key is None:
            raise NotFoundError("У игры нет обложки")
        return game

    # --- игровые вечера ---

    async def log_session(
        self,
        game_id: UUID,
        user_id: int,
        played_at: datetime,
        description: str | None = None,
        date_id: UUID | None = None,
    ) -> GameSession:
        """Записывает вечер. Партнёру потом приходит просьба поделиться впечатлениями."""
        game = await self.get_game(game_id, user_id)
        if played_at.tzinfo is None:
            raise AppError("Время должно быть с часовым поясом")
        if played_at > datetime.now(UTC) + PLAYED_AT_SKEW:
            raise AppError("Нельзя записать вечер, который ещё не наступил")
        if date_id is not None:
            _ = await DateService(self.session).get_for_user(date_id, user_id)  # свидание этой пары

        game_session = await self.repo.create_session(
            GameSession(
                game_id=game.id,
                date_id=date_id,
                created_by=user_id,
                played_at=played_at,
                description=_clean(description, "Описание вечера"),
            )
        )
        await self.session.commit()
        return game_session

    async def get_session(self, session_id: UUID, user_id: int) -> GameSession:
        game_session = await self.repo.get_session(session_id)
        if game_session is None:
            raise NotFoundError("Вечер не найден")
        _ = await self.get_game(game_session.game_id, user_id)  # проверка, что игра этой пары
        return game_session

    async def list_sessions(self, game_id: UUID, user_id: int) -> list[GameSession]:
        game = await self.get_game(game_id, user_id)
        return await self.repo.list_sessions_for_game(game.id)

    # --- отзывы ---

    async def list_reviews(self, session_id: UUID) -> list[GameSessionReview]:
        return await self.repo.list_reviews(session_id)

    async def check_can_review(self, session_id: UUID, user_id: int) -> GameSession:
        game_session = await self.get_session(session_id, user_id)
        if await self.repo.get_review_by_author(game_session.id, user_id) is not None:
            raise ConflictError("Вы уже оставили отзыв об этом вечере")
        return game_session

    async def create_review(
        self,
        session_id: UUID,
        author_id: int,
        rating: int,
        mood: GameMood | None = None,
        liked: str | None = None,
        disliked: str | None = None,
        comment: str | None = None,
    ) -> GameSessionReview:
        if not 1 <= rating <= 5:
            raise AppError("Оценка должна быть от 1 до 5")
        game_session = await self.check_can_review(session_id, author_id)
        try:
            review = await self.repo.create_review(
                GameSessionReview(
                    session_id=game_session.id,
                    author_id=author_id,
                    rating=rating,
                    mood=mood,
                    liked=_clean(liked, "Что понравилось"),
                    disliked=_clean(disliked, "Что не понравилось"),
                    comment=_clean(comment, "Комментарий"),
                )
            )
            await self.session.commit()
        except IntegrityError as e:  # параллельный запрос успел создать отзыв раньше
            await self.session.rollback()
            raise ConflictError("Вы уже оставили отзыв об этом вечере") from e
        return review


async def _delete_file(key: str) -> None:
    # Не удалился файл — останется мусор в бакете, но пользователю это не мешает
    try:
        await storage.delete(key)
    except Exception:
        logger.exception("Не удалось удалить файл %s из хранилища", key)
