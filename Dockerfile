# syntax=docker/dockerfile:1

# ---------- Сборка: ставим зависимости в .venv ----------
FROM python:3.13-alpine AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=0

WORKDIR /app

# Только зависимости (без кода) — слой кэшируется, пока не меняются pyproject.toml и uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project \
 && find .venv -type d -name "__pycache__" -prune -exec rm -rf {} + \
 && find .venv -type d \( -name "tests" -o -name "test" \) -path "*/site-packages/*" -prune -exec rm -rf {} + \
 && find .venv -type f \( -name "*.pyx" -o -name "*.pxd" -o -name "*.c" -o -name "*.h" -o -name "*.pyi" \) -delete

# Убираем отладочные символы из скомпилированных расширений (asyncpg, pydantic-core, sqlalchemy, ...)
RUN apk add --no-cache binutils \
 && find .venv -name "*.so*" -type f -exec strip --strip-unneeded {} +

# ---------- Рантайм: только Python, .venv и код ----------
FROM python:3.13-alpine

RUN addgroup -S app && adduser -S -G app app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
