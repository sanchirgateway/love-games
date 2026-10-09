import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import health
from app.core.bot import create_bot, create_dispatcher, set_commands
from app.core.db import engine
from app.core.errors import AppError
from app.feature.admin import router as admin_router
from app.feature.dates import handlers as dates_handlers
from app.feature.dates import jobs as dates_jobs
from app.feature.dates import router as dates_router
from app.feature.reviews import handlers as reviews_handlers
from app.feature.user import handlers as user_handlers
from app.feature.user import router as user_router
from config.config import app_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    bot = create_bot()
    app.state.bot = bot
    dp = create_dispatcher(user_handlers.router, dates_handlers.router, reviews_handlers.router)
    await set_commands(bot)
    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    dates_jobs_task = asyncio.create_task(dates_jobs.dates_loop(bot))

    yield

    _ = dates_jobs_task.cancel()
    with suppress(asyncio.CancelledError):
        await dates_jobs_task
    await dp.stop_polling()
    await polling
    await engine.dispose()


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def cors_origins() -> list[str]:
    """В debug — любой домен (ngrok, localhost и т.п.), в проде — только APP_CORS_ORIGINS."""
    if app_settings.debug:
        return ["*"]
    return [o.strip().rstrip("/") for o in app_settings.cors_origins.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="Bloomy API", lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"] if app_settings.debug else ["Authorization", "Content-Type"],
    )

    api = APIRouter(prefix="/api/v1")
    api.include_router(health.router)
    api.include_router(user_router.router)
    api.include_router(dates_router.router)
    api.include_router(admin_router.router)
    app.include_router(api)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
