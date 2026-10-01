from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSettings(BaseSettings):
    host: str
    port: int
    user: str
    password: str
    database: str

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


db_settings = DbSettings()  # pyright: ignore[reportCallIssue]  # поля читаются из env


class BotSettings(BaseSettings):
    token: str
    webapp_url: str | None = None  # https-адрес Mini App, без него кнопка не показывается

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
    )


bot_settings = BotSettings()  # pyright: ignore[reportCallIssue]  # поля читаются из env
