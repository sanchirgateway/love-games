from typing import Annotated

from fastapi import APIRouter, Query

from app.core.api import SessionDep
from app.feature.stats.schemas import CoupleStatsOut
from app.feature.stats.service import StatsService
from app.feature.user.dependencies import CurrentUser

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=CoupleStatsOut)
async def get_stats(
    user: CurrentUser,
    session: SessionDep,
    year: Annotated[
        int | None, Query(description="Календарный год в часовом поясе пользователя. Нет — за всё время")
    ] = None,
) -> CoupleStatsOut:
    """Статистика пары: свидания, цветы, игры, фото. Без пары — 409.

    Сюрпризы и скрытые отзывы партнёра не учитываются, пока они не видны пользователю.
    """
    stats = await StatsService(session).for_couple(user.id, year)
    return CoupleStatsOut.model_validate(stats)
