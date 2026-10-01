import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI

from app.api.routes import health
from app.bot.setup import create_bot, create_dispatcher
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    bot = create_bot()
    dp = create_dispatcher()
    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))

    yield

    await dp.stop_polling()
    await polling
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Bloomy API", lifespan=lifespan)

    api = APIRouter(prefix="/api/v1")
    api.include_router(health.router)
    app.include_router(api)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
