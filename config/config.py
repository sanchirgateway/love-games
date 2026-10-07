import os
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict

# Файл с переменными для локального запуска. Переменные окружения всегда важнее файла,
# а если файла нет (как в Docker-образе), он просто пропускается.
ENV_FILE = os.getenv("ENV_FILE", ".env.dev")


class DbSettings(BaseSettings):
    host: str
    port: int
    user: str
    password: str
    database: str

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="DB_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


db_settings = DbSettings()  # pyright: ignore[reportCallIssue]  # поля читаются из env


class BotSettings(BaseSettings):
    token: str
    webapp_url: str | None = None

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


bot_settings = BotSettings()  # pyright: ignore[reportCallIssue]  # поля читаются из env


class AppSettings(BaseSettings):
    # В debug-режиме API принимает заголовок X-Debug-User-Id вместо initData (для Swagger)
    debug: bool = False

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="APP_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


app_settings = AppSettings()

class S3Settings(BaseSettings):
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="S3_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


s3_settings = S3Settings()  # pyright: ignore[reportCallIssue]  # поля читаются из env
