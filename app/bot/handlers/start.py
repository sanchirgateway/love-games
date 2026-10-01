from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import open_app_keyboard
from app.services.users import upsert_user
from config.config import bot_settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    await upsert_user(session, message.from_user)

    text = (
        f"Привет, {message.from_user.first_name}! 💐\n\n"
        "Я помогу планировать свидания и напомню о них заранее."
    )
    if bot_settings.webapp_url:
        await message.answer(text, reply_markup=open_app_keyboard(bot_settings.webapp_url))
    else:
        await message.answer(text)
