from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.api import SessionDep
from app.feature.admin.dependencies import AdminDep
from app.feature.dates.models import DateEvent, DateStatus
from app.feature.dates.schemas import DateOut
from app.feature.dates.service import DateService

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[AdminDep])


@router.get("/dates", response_model=list[DateOut])
async def list_dates(
    session: SessionDep,
    user_id: int | None = None,
    status: DateStatus | None = None,
    upcoming: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DateEvent]:
    return await DateService(session).list_all(
        user_id=user_id, status=status, upcoming_only=upcoming, limit=limit, offset=offset
    )


@router.get("/dates/{date_id}", response_model=DateOut)
async def get_date(date_id: UUID, session: SessionDep) -> DateEvent:
    return await DateService(session).get(date_id)
