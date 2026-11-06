# Импорт всех моделей, чтобы они попали в Base.metadata (нужно Alembic'у и для связей между моделями)
from app.feature.bouquets.models import VirtualBouquet
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.flowers.models import FlowerGift, FlowerGiftPhoto, FlowerOccasion, FlowerReaction
from app.feature.games.models import Game, GameMood, GameSession, GameSessionReview, GameStatus
from app.feature.ideas.models import DateIdea, DateIdeaVote, IdeaVote
from app.feature.reviews.models import DateReview, DateReviewPhoto
from app.feature.user.models import User
from app.feature.wishlist.models import WishItem

__all__ = [
    "DateEvent",
    "DateIdea",
    "DateIdeaVote",
    "DateReview",
    "DateReviewPhoto",
    "DateStatus",
    "FlowerGift",
    "FlowerGiftPhoto",
    "FlowerOccasion",
    "FlowerReaction",
    "Game",
    "GameMood",
    "GameSession",
    "GameSessionReview",
    "GameStatus",
    "IdeaVote",
    "User",
    "VirtualBouquet",
    "WishItem",
]
