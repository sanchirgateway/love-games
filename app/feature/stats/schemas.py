from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.feature.flowers.models import FlowerOccasion, FlowerReaction
from app.feature.games.models import GameMood


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BestDateOut(_Out):
    id: UUID
    title: str
    starts_at: datetime
    rating: float


class TopPlaceOut(_Out):
    place: str
    count: int


class DateStatsOut(_Out):
    done: int
    upcoming: int  # предложенные и принятые, которые ещё не начались
    cancelled: int  # отменённые и отклонённые
    first_at: datetime | None
    avg_rating: float | None  # по всем видимым отзывам
    my_avg_rating: float | None
    partner_avg_rating: float | None  # скрытые пока отзывы партнёра не учитываются
    best: BestDateOut | None
    top_place: TopPlaceOut | None


class FlowerStatsOut(_Out):
    given_by_me: int
    given_by_partner: int
    my_spent: int  # в рублях, только свои букеты
    pending_surprises: int  # свои невручённые, за всё время
    top_occasion: FlowerOccasion | None
    reactions_to_mine: dict[FlowerReaction, int]
    reactions_to_partner: dict[FlowerReaction, int]


class TopGameOut(_Out):
    id: UUID
    title: str
    sessions: int


class GameStatsOut(_Out):
    sessions: int
    playing: int  # статусы игр — текущие, без учёта периода
    completed: int
    dropped: int
    avg_rating: float | None
    top_game: TopGameOut | None
    moods: dict[GameMood, int]


class IdeaStatsOut(_Out):
    matches: int  # за всё время
    dates_from_ideas: int


class MediaStatsOut(_Out):
    photos: int
    videos: int


class CoupleStatsOut(_Out):
    year: int | None  # null — за всё время
    partner_id: int
    partner_name: str
    dates: DateStatsOut
    flowers: FlowerStatsOut
    games: GameStatsOut
    ideas: IdeaStatsOut
    media: MediaStatsOut
