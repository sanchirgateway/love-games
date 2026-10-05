from fastapi import APIRouter
from sqlalchemy import text

from app.core.api import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    _ = await session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
