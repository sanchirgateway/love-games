from fastapi import APIRouter

from app.feature.user.dependencies import CurrentUser
from app.feature.user.models import User
from app.feature.user.schemas import UserOut

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> User:
    return user
