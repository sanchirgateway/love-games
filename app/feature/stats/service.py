from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.time import local_day_start
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.flowers.models import FlowerGift, FlowerOccasion, FlowerReaction
from app.feature.flowers.service import can_see as can_see_gift
from app.feature.games.models import Game, GameMood, GameSession, GameStatus
from app.feature.games.service import can_see_review as can_see_game_review
from app.feature.ideas.service import IdeaService
from app.feature.reviews.models import DateReview
from app.feature.reviews.service import can_see_review as can_see_date_review
from app.feature.stats.repository import StatsRepository
from app.feature.user.service import UserService

MIN_YEAR = 2000


@dataclass(frozen=True)
class BestDate:
    id: UUID
    title: str
    starts_at: datetime
    rating: float


@dataclass(frozen=True)
class TopPlace:
    place: str
    count: int


@dataclass(frozen=True)
class DateStats:
    done: int
    upcoming: int  # предложенные и принятые, которые ещё не начались
    cancelled: int  # отменённые и отклонённые
    first_at: datetime | None  # первое состоявшееся свидание за период
    avg_rating: float | None  # по всем видимым отзывам
    my_avg_rating: float | None
    partner_avg_rating: float | None  # только по отзывам, которые пользователю уже открыты
    best: BestDate | None
    top_place: TopPlace | None


@dataclass(frozen=True)
class FlowerStats:
    given_by_me: int
    given_by_partner: int
    my_spent: int  # сумма цен своих врученных букетов: цену видит только даритель
    pending_surprises: int  # свои ещё не врученные — за всё время, без учёта периода
    top_occasion: FlowerOccasion | None
    reactions_to_mine: dict[FlowerReaction, int] = field(default_factory=dict)
    reactions_to_partner: dict[FlowerReaction, int] = field(default_factory=dict)  # мои реакции на букеты партнёра


@dataclass(frozen=True)
class TopGame:
    id: UUID
    title: str
    sessions: int


@dataclass(frozen=True)
class GameStats:
    sessions: int
    playing: int  # статусы игр — текущие, без учёта периода
    completed: int
    dropped: int
    avg_rating: float | None
    top_game: TopGame | None
    moods: dict[GameMood, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaStats:
    photos: int  # фото отзывов о свиданиях и фото букетов
    videos: int


@dataclass(frozen=True)
class IdeaStats:
    matches: int  # все совпадения пары — за всё время, без учёта периода
    dates_from_ideas: int  # свидания из совпадений за период, кроме отклонённых и отменённых


@dataclass(frozen=True)
class CoupleStats:
    year: int | None
    partner_id: int
    partner_name: str
    dates: DateStats
    flowers: FlowerStats
    games: GameStats
    ideas: IdeaStats
    media: MediaStats


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _counts[T](values: list[T]) -> dict[T, int]:
    return dict(Counter(values).most_common())


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = StatsRepository(session)
        self.users = UserService(session)
        self.ideas = IdeaService(session)

    async def for_couple(self, user_id: int, year: int | None = None) -> CoupleStats:
        """Статистика пары за всё время или за календарный год (в часовом поясе пользователя).

        Считается только то, что пользователь и так может увидеть: без невручённых букетов партнёра
        и без скрытых отзывов партнёра. Без пары — ConflictError.
        """
        user = await self.users.get(user_id)
        partner = await self.users.get_partner(user_id)
        since = until = None
        if year is not None:
            if not MIN_YEAR <= year <= datetime.now(UTC).year + 1:
                raise AppError("Неверный год")
            since = local_day_start(date(year, 1, 1), user.timezone)
            until = local_day_start(date(year + 1, 1, 1), user.timezone)

        dates = await self.repo.list_dates(user_id, partner.id, since, until)
        reviews = await self.repo.list_date_reviews([d.id for d in dates])
        gifts = [g for g in await self.repo.list_gifts(user_id, partner.id) if can_see_gift(g, user_id)]
        owners = [user_id, partner.id]
        games = await self.repo.list_games(owners)
        sessions = await self.repo.list_game_sessions(owners, since, until)

        visible_reviews = _visible_date_reviews(dates, reviews, user_id)
        in_period = [g for g in gifts if g.given_at is not None and _in_period(g.given_at, since, until)]
        review_media = [p for r in visible_reviews for p in r.photos]
        flower_photos = sum(len(g.photos) for g in in_period)

        return CoupleStats(
            year=year,
            partner_id=partner.id,
            partner_name=partner.first_name,
            dates=_date_stats(dates, visible_reviews, user_id),
            flowers=_flower_stats(gifts, in_period, user_id),
            games=_game_stats(games, sessions, user_id),
            ideas=IdeaStats(
                matches=len(await self.ideas.matches(user_id, planned=None)),
                dates_from_ideas=sum(
                    d.idea_id is not None and d.status not in (DateStatus.DECLINED, DateStatus.CANCELLED) for d in dates
                ),
            ),
            media=MediaStats(
                photos=sum(not p.is_video for p in review_media) + flower_photos,
                videos=sum(p.is_video for p in review_media),
            ),
        )


def _in_period(moment: datetime, since: datetime | None, until: datetime | None) -> bool:
    return (since is None or moment >= since) and (until is None or moment < until)


def _visible_date_reviews(dates: list[DateEvent], reviews: list[DateReview], user_id: int) -> list[DateReview]:
    by_date: dict[UUID, list[DateReview]] = defaultdict(list)
    for review in reviews:
        by_date[review.date_id].append(review)
    return [review for d in dates for review in by_date[d.id] if can_see_date_review(d, by_date[d.id], review, user_id)]


def _date_stats(dates: list[DateEvent], reviews: list[DateReview], user_id: int) -> DateStats:
    now = datetime.now(UTC)
    done = sorted((d for d in dates if d.status == DateStatus.DONE), key=lambda d: d.starts_at)

    ratings: dict[UUID, list[int]] = defaultdict(list)
    for review in reviews:
        ratings[review.date_id].append(review.rating)
    best = None
    rated = [d for d in done if ratings[d.id]]
    if rated:
        # При равной оценке — более позднее свидание
        top = max(rated, key=lambda d: (sum(ratings[d.id]) / len(ratings[d.id]), d.starts_at))
        best = BestDate(id=top.id, title=top.title, starts_at=top.starts_at, rating=_avg(ratings[top.id]) or 0)

    # Одно и то же место пишут по-разному («Кофемания» / «кофемания ») — сравниваем без регистра и пробелов
    places: dict[str, list[str]] = defaultdict(list)
    for d in done:
        if d.place and d.place.strip():
            places[d.place.strip().casefold()].append(d.place.strip())
    top_place = None
    if places:
        variants = max(places.values(), key=len)
        top_place = TopPlace(place=Counter(variants).most_common(1)[0][0], count=len(variants))

    return DateStats(
        done=len(done),
        upcoming=sum(d.status in (DateStatus.PROPOSED, DateStatus.PLANNED) and d.starts_at > now for d in dates),
        cancelled=sum(d.status in (DateStatus.CANCELLED, DateStatus.DECLINED) for d in dates),
        first_at=done[0].starts_at if done else None,
        avg_rating=_avg([r.rating for r in reviews]),
        my_avg_rating=_avg([r.rating for r in reviews if r.author_id == user_id]),
        partner_avg_rating=_avg([r.rating for r in reviews if r.author_id != user_id]),
        best=best,
        top_place=top_place,
    )


def _flower_stats(gifts: list[FlowerGift], in_period: list[FlowerGift], user_id: int) -> FlowerStats:
    mine = [g for g in in_period if g.giver_id == user_id]
    partners = [g for g in in_period if g.giver_id != user_id]
    occasions = _counts([g.occasion for g in in_period if g.occasion is not None])
    return FlowerStats(
        given_by_me=len(mine),
        given_by_partner=len(partners),
        my_spent=sum(g.price or 0 for g in mine),
        pending_surprises=sum(g.giver_id == user_id and not g.is_given for g in gifts),
        top_occasion=next(iter(occasions), None),
        reactions_to_mine=_counts([g.reaction for g in mine if g.reaction is not None]),
        reactions_to_partner=_counts([g.reaction for g in partners if g.reaction is not None]),
    )


def _game_stats(games: list[Game], sessions: list[GameSession], user_id: int) -> GameStats:
    reviews = [review for s in sessions for review in s.reviews if can_see_game_review(s, s.reviews, review, user_id)]
    per_game = Counter(s.game_id for s in sessions)
    top_game = None
    if per_game:
        game_id, count = per_game.most_common(1)[0]
        game = next(s.game for s in sessions if s.game_id == game_id)
        top_game = TopGame(id=game.id, title=game.title, sessions=count)
    return GameStats(
        sessions=len(sessions),
        playing=sum(g.status == GameStatus.PLAYING for g in games),
        completed=sum(g.status == GameStatus.COMPLETED for g in games),
        dropped=sum(g.status == GameStatus.DROPPED for g in games),
        avg_rating=_avg([r.rating for r in reviews]),
        top_game=top_game,
        moods=_counts([r.mood for r in reviews if r.mood is not None]),
    )
