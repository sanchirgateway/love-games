# Структура проекта

Bloomy — Telegram-бот и Mini App для планирования свиданий. Бот (aiogram) и REST API (FastAPI) работают в одном процессе: бот запускается polling'ом в `lifespan` FastAPI, рядом крутится фоновая задача напоминаний. Данные хранятся в PostgreSQL, фото и видео отзывов — в SeaweedFS (S3 API). Фронт Mini App — отдельный проект, в этом репозитории его нет.

```
Telegram ──► handlers (aiogram) ──┐
                                  ├──► service ──► repository ──► PostgreSQL
Mini App ──► router (FastAPI) ────┤        └──► core/storage ──► SeaweedFS
jobs (фон, раз в минуту) ─────────┘
```

## Дерево

```
bloomy_bot/
├── app/
│   ├── main.py                 # сборка FastAPI, запуск бота и фоновой задачи в lifespan
│   │
│   ├── core/                   # общая инфраструктура, не знает про фичи
│   │   ├── api.py              # FastAPI-зависимости: SessionDep, BotDep
│   │   ├── bot.py              # Bot, Dispatcher, middleware сессии БД, список команд, обработка AppError
│   │   ├── db.py               # Base, async engine, session_maker
│   │   ├── errors.py           # AppError и наследники (NotFound / Forbidden / Conflict)
│   │   ├── health.py           # GET /health
│   │   ├── images.py           # сжатие фото перед сохранением (Pillow)
│   │   ├── storage.py          # загрузка / скачивание / удаление файлов в S3
│   │   └── time.py             # разбор и форматирование дат в часовом поясе пользователя
│   │
│   ├── feature/                # фичи, каждая — отдельная папка
│   │   ├── __init__.py         # импорт всех моделей (для Alembic и связей)
│   │   ├── user/               # регистрация, пара, авторизация Mini App
│   │   ├── dates/              # свидания, напоминания, фоновые задачи
│   │   ├── reviews/            # отзывы, фото и видео
│   │   ├── games/              # журнал игр: каталог пары, игровые вечера, отзывы о вечерах
│   │   ├── flowers/            # журнал подаренных цветов: букеты, фото, реакция получателя
│   │   └── admin/              # админ-API по X-API-Key
│   │
│   └── scripts/
│       ├── set_avatar.py       # разовая установка аватарки бота
│       ├── compress_photos.py  # пережать старые фото из Mini App
│       └── restore_media.py    # докачать из Telegram файлы, пропавшие из хранилища
│
├── config/
│   └── config.py               # настройки из env / .env.dev (DB_, BOT_, APP_, S3_)
│
├── migrations/                 # Alembic, metadata берётся из app.feature
├── scripts/
│   └── dev.py                  # запуск uvicorn с автоперезапуском (замена --reload для Windows)
├── photo/                      # картинки для бота (аватарка)
├── docs/
│   └── STRUCTURE.md            # этот файл
│
├── docker-compose.dev.yml      # Postgres, SeaweedFS и приложение для разработки
├── docker-compose.prod.yml     # прод (Coolify)
├── Dockerfile
├── Taskfile.yml                # команды: БД, хранилище, миграции, запуск
├── alembic.ini
├── pyproject.toml
├── uv.lock
└── README.md                   # функционал, настройки, запуск
```

### Файлы внутри фичи

Набор файлов зависит от фичи, но роли у них одинаковые:

| Файл | Отвечает за |
|---|---|
| `models.py` | Модели SQLAlchemy |
| `repository.py` | Запросы к БД, без бизнес-правил |
| `service.py` | Бизнес-логика: проверки, смена статусов, коммит. Класс `<Name>Service(session)` |
| `handlers.py` | Хендлеры бота: команды, FSM-диалоги, колбэки |
| `keyboards.py` | Inline- и reply-клавиатуры, `CallbackData` |
| `notify.py` | Отправка сообщений в Telegram; вызывается и из бота, и из API, и из фоновых задач |
| `router.py` | Эндпоинты FastAPI |
| `schemas.py` | Pydantic-схемы API |
| `dependencies.py` | FastAPI-зависимости фичи (`CurrentUser`, `AdminDep`) |
| `jobs.py`, `reminders.py` | (dates) фоновый цикл и правила напоминаний |

## Правила зависимостей

| Слой | Может импортировать |
|---|---|
| `handlers`, `router`, `jobs` | `service`, `notify`, `keyboards`, `schemas`, `core`, `config` |
| `notify` | `models`, `keyboards`, `core.time`, `core.storage` |
| `service` | `repository`, `models`, сервисы других фич, `core.errors`, `core.storage` |
| `repository` | `models` |
| `core` | `config` |
| `config` | ничего из проекта |

Основное правило: **зависимости идут сверху вниз.** `service` ничего не знает про aiogram-хендлеры и FastAPI, поэтому одну и ту же функцию (например, `DateService.propose`) вызывают и хендлер бота, и роут API.

Между фичами можно ходить через сервисы: `reviews` использует `DateService`, `dates` — `UserService`.

Чего не делать:
- писать SQL прямо в хендлерах, роутах и сервисах — для этого `repository`;
- импортировать хендлеры из роутов и наоборот;
- возвращать из API модели SQLAlchemy без `response_model` — только через `schemas`.

## Ошибки

Сервис бросает `AppError` (или `NotFoundError` / `ForbiddenError` / `ConflictError`) с текстом для пользователя.
- В боте их ловит `on_app_error` в `core/bot.py`: в колбэке — alert, в сообщении — ответ текстом.
- В API — `app_error_handler` в `main.py`: `{"detail": message}` с `status_code` ошибки.

Поэтому в хендлерах и роутах проверять права и статусы вручную не нужно.

## Как проходит запрос из Mini App

1. Фронт отправляет `GET /api/v1/dates` с заголовком `Authorization: tma <initData>`.
2. `feature/user/dependencies.py` проверяет подпись initData токеном бота и срок (сутки), загружает пользователя.
3. `core/api.py` выдаёт сессию БД (`SessionDep`) и бота (`BotDep`).
4. `feature/dates/router.py` вызывает `DateService(session).list_for_user(user.id)`.
5. Результат сериализуется через `schemas.DateOut`.

## Фоновые задачи

`feature/dates/jobs.py: dates_loop` запускается в `lifespan` и раз в минуту выполняет независимые шаги (падение одного не останавливает остальные):
1. `send_reminders` — напоминания о свиданиях (правила в `reminders.py`);
2. `complete_past_dates` — переводит прошедшие свидания в `done` и просит отзыв;
3. `send_review_reminders` — повторное напоминание об отзыве.

Факт отправки хранится в колонках `*_sent_at` модели `DateEvent`, поэтому после перезапуска ничего не дублируется.

## Куда что добавлять

| Задача | Где |
|---|---|
| Новая таблица или поле | `app/feature/<name>/models.py` (новую модель — импортировать в `app/feature/__init__.py`) → `task migrate:new -- "описание"` → проверить файл → `task migrate` |
| Новая команда бота | хендлер в `app/feature/<name>/handlers.py`, команду — в `BOT_COMMANDS` в `core/bot.py`; новый роутер — в `create_dispatcher(...)` в `main.py` |
| Новый эндпоинт | `app/feature/<name>/router.py` + схемы в `schemas.py`; новый роутер — в `create_app()` в `main.py` |
| Новая логика | метод в `app/feature/<name>/service.py` |
| Новая фоновая задача | шаг в `steps` в `feature/dates/jobs.py` или отдельная задача в `lifespan` |
| Новая настройка | поле в `config/config.py` + переменная в `.env.dev` и `docker-compose.prod.yml` |

## Соглашения

- Время в БД хранится в UTC (`DateTime(timezone=True)`), в часовой пояс пользователя (`users.timezone`) переводится только при вводе и показе — через `core/time.py`.
- `users.id` — это Telegram user id (`BigInteger`), автоинкремента нет. Пара — `users.partner_id`.
- `dates.id`, `date_reviews.id`, `games.id`, `game_sessions.id`, `game_session_reviews.id`, `flower_gifts.id` — UUID.
- Игра принадлежит паре: `games.created_by` — тот, кто завёл, доступ — у него и его партнёра (`users.partner_id`). Обложки игр — в S3 под `games/<game_id>/<cover_id>.jpg`, при замене ключ новый.
- Фото и видео отзывов лежат в таблице `date_review_photos` (видео отличается по `content_type = video/mp4`) и в S3 под ключом `reviews/<review_id>/<photo_id>.<jpg|png|mp4>`. `tg_file_id` есть только у файлов, присланных боту: по нему бот пересылает их без скачивания. Видео ограничено 20 МБ — больше бот не может скачать из Telegram. Файлы из Mini App (`tg_file_id = NULL`) бот отправляет из хранилища, а API отдаёт их через `GET /reviews/photos/{id}`.
- Букет (`flower_gifts`) с пустым `given_at` — сюрприз: его видит только даритель (`service.can_see`), для получателя он и его фото — `404`. Фото букетов — в `flower_gift_photos` и в S3 под `flowers/<gift_id>/<photo_id>.jpg`, всегда JPEG.
- Логика рассылки после нового отзыва (`notify.announce_review`) общая для бота и API.
- Сообщения бота — в HTML (`ParseMode.HTML`), пользовательский текст экранируется через `html.escape`.
- Апдейты одного чата обрабатываются по очереди (`SimpleEventIsolation`) — иначе фото из альбома теряются в FSM.
- Переменные окружения сгруппированы по префиксам: `DB_`, `BOT_`, `APP_`, `S3_`.
- Миграции генерируются Alembic'ом и всегда просматриваются перед `task migrate`.

## Команды

```bash
task install                     # зависимости
task db:up                       # поднять Postgres
task storage:up                  # поднять SeaweedFS и создать bucket
task migrate:new -- "описание"   # сгенерировать миграцию
task migrate                     # накатить миграции
task migrate:status              # текущая ревизия
task run                         # запустить приложение
task dev                         # всё вместе
task up                          # всё в Docker
```
