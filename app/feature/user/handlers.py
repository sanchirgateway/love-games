from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from aiogram.utils.deep_linking import create_start_link
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bot import commands_help
from app.core.errors import AppError
from app.feature.user.keyboards import open_app_keyboard
from app.feature.user.service import (
    PAIR_PREFIX,
    UserService,
    make_pair_payload,
    parse_pair_payload,
)
from config.config import bot_settings

router = Router()


# Должен стоять раньше обычного /start: ловит переход по ссылке-приглашению t.me/<bot>?start=pair_...
@router.message(CommandStart(deep_link=True, magic=F.args.startswith(PAIR_PREFIX)))
async def cmd_start_pair(message: Message, command: CommandObject, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return

    service = UserService(session)
    await service.register(message.from_user)

    inviter_id = parse_pair_payload(command.args or "")
    if inviter_id is None:
        await message.answer("Ссылка-приглашение недействительна 😔")
        return

    try:
        user, inviter = await service.pair(message.from_user.id, inviter_id)
    except AppError as e:
        await message.answer(e.message)
        return

    await message.answer(f"Готово! Теперь вы в паре с {inviter.first_name} 💞\nСоздать свидание: /new")
    await bot.send_message(inviter.id, f"{user.first_name} принял(а) приглашение — теперь вы пара 💞")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    await UserService(session).register(message.from_user)

    text = (
        f"Привет, {message.from_user.first_name}! 💐\n\n"
        "Я помогу планировать свидания и напомню о них заранее.\n\n"
        f"{commands_help()}"
    )
    if bot_settings.webapp_url:
        await message.answer(text, reply_markup=open_app_keyboard(bot_settings.webapp_url))
    else:
        await message.answer(text)


@router.message(Command("pair"))
async def cmd_pair(message: Message, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return

    user = await UserService(session).get(message.from_user.id)
    if user.partner_id is not None:
        partner = await UserService(session).get(user.partner_id)
        await message.answer(f"Вы уже в паре с {partner.first_name} 💞")
        return

    link = await create_start_link(bot, make_pair_payload(user.id))
    await message.answer(f"Отправьте эту ссылку партнёру — после перехода по ней вы станете парой:\n\n{link}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(f"Что я умею:\n\n{commands_help()}")
