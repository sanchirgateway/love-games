import hashlib
import hmac

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.feature.user.models import User
from app.feature.user.repository import UserRepository
from config.config import bot_settings

PAIR_PREFIX = "pair_"


def make_pair_payload(user_id: int) -> str:
    """Payload для ссылки t.me/<bot>?start=..., подписанный токеном бота, чтобы его нельзя было подделать."""
    return f"{PAIR_PREFIX}{user_id}_{_sign(user_id)}"


def parse_pair_payload(payload: str) -> int | None:
    try:
        user_id_str, signature = payload.removeprefix(PAIR_PREFIX).split("_", 1)
        user_id = int(user_id_str)
    except ValueError:
        return None
    return user_id if hmac.compare_digest(signature, _sign(user_id)) else None


def _sign(user_id: int) -> str:
    return hmac.new(bot_settings.token.encode(), f"pair:{user_id}".encode(), hashlib.sha256).hexdigest()[:16]


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def register(self, tg_user: TgUser) -> None:
        """Создаёт пользователя или обновляет его данные из Telegram."""
        await self.repo.upsert(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        await self.session.commit()

    async def get(self, user_id: int) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден. Сначала нажмите /start в боте.")
        return user

    async def get_partner(self, user_id: int) -> User:
        user = await self.get(user_id)
        if user.partner_id is None:
            raise ConflictError("У вас ещё нет пары. Отправьте партнёру ссылку из команды /pair.")
        return await self.get(user.partner_id)

    async def pair(self, user_id: int, partner_id: int) -> tuple[User, User]:
        if user_id == partner_id:
            raise AppError("Нельзя создать пару с самим собой 🙂")

        user = await self.get(user_id)
        partner = await self.get(partner_id)
        if user.partner_id not in (None, partner.id) or partner.partner_id not in (None, user.id):
            raise ConflictError("Кто-то из вас уже состоит в другой паре.")

        await self.repo.set_partner(user.id, partner.id)
        await self.repo.set_partner(partner.id, user.id)
        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(partner)
        return user, partner
