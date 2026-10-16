from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.games.models import Game, GameSession, GameSessionReview, GameStatus


class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- игры ---

    async def create_game(self, game: Game) -> Game:
        self.session.add(game)
        await self.session.flush()
        await self.session.refresh(game, ["created_at", "updated_at"])  # server_default, нужны для ответа API
        return game

    async def get_game(self, game_id: UUID) -> Game | None:
        return await self.session.get(Game, game_id)

    async def list_games(self, owner_ids: list[int]) -> list[Game]:
        """Игры, заведённые кем-то из owner_ids (пользователь и его партнёр). Сначала те, что проходим сейчас."""
        stmt = (
            select(Game)
            .where(Game.created_by.in_(owner_ids))
            .order_by((Game.status == GameStatus.PLAYING).desc(), Game.updated_at.desc())
        )
        result = await self.session.scalars(stmt)
        return list(result)

    # --- игровые вечера ---

    async def create_session(self, game_session: GameSession) -> GameSession:
        self.session.add(game_session)
        await self.session.flush()
        await self.session.refresh(game_session, ["game", "reviews", "created_at", "updated_at"])
        return game_session

    async def get_session(self, session_id: UUID) -> GameSession | None:
        # Игра и отзывы подтягиваются автоматически: lazy="joined" и lazy="selectin" у relationship
        return await self.session.get(GameSession, session_id)

    async def list_sessions_for_game(self, game_id: UUID) -> list[GameSession]:
        """Вечера одной игры, свежие первыми."""
        stmt = select(GameSession).where(GameSession.game_id == game_id).order_by(GameSession.played_at.desc())
        result = await self.session.scalars(stmt)
        return list(result)

    # --- отзывы ---

    async def create_review(self, review: GameSessionReview) -> GameSessionReview:
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review, ["created_at", "updated_at"])
        return review

    async def get_review_by_author(self, session_id: UUID, author_id: int) -> GameSessionReview | None:
        stmt = select(GameSessionReview).where(
            GameSessionReview.session_id == session_id, GameSessionReview.author_id == author_id
        )
        return await self.session.scalar(stmt)

    async def list_reviews(self, session_id: UUID) -> list[GameSessionReview]:
        # Отдельным запросом, а не через GameSession.reviews: тот загружен один раз и не видит только что созданный отзыв
        stmt = (
            select(GameSessionReview)
            .where(GameSessionReview.session_id == session_id)
            .order_by(GameSessionReview.created_at)
        )
        result = await self.session.scalars(stmt)
        return list(result)
