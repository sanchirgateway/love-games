from aiogram import Router

from app.bot.handlers import start

router = Router()
router.include_router(start.router)
