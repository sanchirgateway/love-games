from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config.config import db_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(db_settings.url, pool_pre_ping=True)
session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session
