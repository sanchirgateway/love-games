# Структура проекта

Bloomy — Telegram-бот и Mini App для планирования свиданий. Бот (aiogram) и REST API (FastAPI) работают в одном процессе, данные хранятся в PostgreSQL, фронт Mini App — отдельная статика.

```
Telegram ──► Бот (aiogram) ──┐
                             ├──► services ──► PostgreSQL
Mini App (webapp/) ──► API (FastAPI) ──┘
```

## Дерево

```
bloomy_bot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # сборка FastAPI + запуск бота в lifespan
│   │
│   ├── bot/                    # всё, что касается Telegram-бота
│   │   ├── __init__.py
│   │   ├── setup.py            # создание Bot и Dispatcher, подключение роутеров
│   │   ├── handlers/           # хендлеры команд и колбэков (/start, ...)
│   │   │   ├── __init__.py
│   │   │   └── start.py
│   │   ├── keyboards.py        # inline-клавиатуры, кнопка открытия Mini App
│   │   └── middlewares.py      # сессия БД, вайтлист пользователей
│   │
│   ├── api/                    # REST API для Mini App
│   │   ├── __init__.py
│   │   ├── deps.py             # зависимости: сессия БД, текущий пользователь
│   │   ├── auth.py             # проверка Telegram initData
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── dates.py        # /api/v1/dates
│   │       └── users.py        # /api/v1/me
│   │
│   ├── schemas/                # Pydantic-схемы запросов и ответов API
│   │   ├── __init__.py
│   │   └── dates.py
│   │
│   ├── services/               # бизнес-логика, не зависит от бота и API
│   │   ├── __init__.py
│   │   ├── dates.py            # создать / изменить / список свиданий
│   │   ├── users.py            # upsert пользователя из Telegram
│   │   └── reminders.py        # фоновая задача напоминаний
│   │
│   └── db/
│       ├── __init__.py
│       ├── base.py             # DeclarativeBase
│       ├── models.py           # модели SQLAlchemy (User, DateEvent)
│       └── session.py          # async engine и sessionmaker
│
├── config/
│   └── config.py               # настройки из .env.dev (pydantic-settings)
│
├── migrations/                 # Alembic
│   ├── env.py                  # берёт URL из config, metadata из app.db
│   ├── script.py.mako
│   └── versions/               # файлы миграций (генерируются)
│
├── webapp/                     # фронт Mini App (Vite)
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── api.ts              # fetch к /api/v1 с заголовком initData
│       ├── telegram.ts         # обёртка над Telegram.WebApp
│       └── pages/              # список, форма, карточка свидания
│
├── docs/
│   └── STRUCTURE.md            # этот файл
│
├── main.py                     # точка входа: запускает uvicorn с app.main
├── alembic.ini
├── docker-compose.dev.yml      # Postgres для разработки
├── Dockerfile
├── Taskfile.yml                # команды: БД, миграции, запуск
├── pyproject.toml
├── uv.lock
├── .env.dev                    # локальные переменные (не в git)
└── README.md
```

## Слои и правила зависимостей

| Слой | Отвечает за | Может импортировать |
|---|---|---|
| `bot/` | Приём апдейтов Telegram, ответы пользователю | `services`, `db.session`, `config` |
| `api/` | HTTP-эндпоинты для Mini App, авторизация | `services`, `schemas`, `db.session`, `config` |
| `schemas/` | Форма данных на входе и выходе API | ничего из проекта, кроме enum'ов из `db.models` |
| `services/` | Логика: правила, запросы к БД | `db`, `config` |
| `db/` | Модели, движок, сессии | `config` |
| `config/` | Настройки | ничего из проекта |

Основное правило: **зависимости идут только сверху вниз.** `services` ничего не знает про aiogram и FastAPI, поэтому одну и ту же функцию (например, «создать свидание») вызывают и хендлер бота, и роут API.

Чего не делать:
- писать SQL-запросы прямо в хендлерах и роутах — для этого есть `services`;
- импортировать `bot` из `api` и наоборот;
- возвращать из API модели SQLAlchemy напрямую — только через `schemas`.

## Как проходит запрос из Mini App

1. Фронт отправляет `GET /api/v1/dates` с заголовком `Authorization: tma <initData>`.
2. `api/auth.py` проверяет подпись initData токеном бота и сверяет `user.id` с вайтлистом.
3. `api/deps.py` выдаёт сессию БД и текущего пользователя.
4. `api/routes/dates.py` вызывает `services.dates.list_upcoming(session, user_id)`.
5. Результат превращается в `schemas.dates.DateOut` и уходит в ответ.

## Куда что добавлять

| Задача | Где |
|---|---|
| Новая таблица или поле | `app/db/models.py` → `task migrate:new -- "описание"` → проверить файл → `task migrate` |
| Новая команда бота | `app/bot/handlers/<name>.py`, подключить роутер в `bot/setup.py` |
| Новый эндпоинт | `app/api/routes/<name>.py` + схемы в `app/schemas/`, подключить в `app/main.py` |
| Новая логика | функция в `app/services/<name>.py` |
| Новая настройка | поле в `config/config.py` + переменная в `.env.dev` |

## Соглашения

- Время в БД хранится в UTC (`DateTime(timezone=True)`), в часовой пояс пользователя переводится только при показе.
- `users.id` — это Telegram user id (`BigInteger`), отдельного автоинкремента нет.
- Переменные окружения базы — с префиксом `DB_` (`DB_HOST`, `DB_PORT`, ...).
- Миграции генерируются Alembic'ом и всегда просматриваются перед `task migrate`.
- Все `__init__.py` пустые, кроме тех, где собираются роутеры.

## Команды

```bash
task db:up                       # поднять Postgres
task migrate:new -- "описание"   # сгенерировать миграцию
task migrate                     # накатить миграции
task migrate:status              # текущая ревизия
task run                         # запустить приложение
task dev                         # всё вместе
```

## Текущее состояние

Уже есть: `app/db/models.py`, `config/config.py`, `migrations/` с первой миграцией, `docker-compose.dev.yml`, `Taskfile.yml`.

Осталось создать: `app/db/base.py` и `session.py`, `app/bot/`, `app/api/`, `app/schemas/`, `app/services/`, `app/main.py`, `webapp/`.
