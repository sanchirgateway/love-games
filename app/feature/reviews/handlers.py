import logging
from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature.dates.service import DateService
from app.feature.reviews import notify
from app.feature.reviews.keyboards import (
    PHOTOS_DONE,
    ReviewPick,
    ReviewRating,
    photos_done_keyboard,
    pick_date_keyboard,
    rating_keyboard,
)
from app.feature.reviews.models import MAX_REVIEW_PHOTOS, MAX_REVIEW_TEXT_LENGTH
from app.feature.reviews.service import (
    MAX_VIDEO_SIZE,
    VIDEO_TYPE,
    NewPhoto,
    ReviewService,
    can_see_review,
    detect_media_type,
)
from app.feature.user.service import UserService

logger = logging.getLogger(__name__)

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")

SKIP_HINT = "Напишите ответ или «-», чтобы пропустить"


class ReviewForm(StatesGroup):
    rating = State()
    liked = State()
    disliked = State()
    food = State()
    comment = State()
    photos = State()


# Текстовые шаги: состояние -> (поле отзыва, следующее состояние, вопрос для следующего шага)
TEXT_STEPS: dict[str | None, tuple[str, State, str]] = {
    ReviewForm.liked.state: ("liked", ReviewForm.disliked, "Что не понравилось?"),
    ReviewForm.disliked.state: ("disliked", ReviewForm.food, "Что ели и пили? Понравилось?"),
    ReviewForm.food.state: ("food", ReviewForm.comment, "Что-нибудь ещё? Общие впечатления"),
    ReviewForm.comment.state: ("comment", ReviewForm.photos, ""),
}

PHOTOS_PROMPT = (
    f"Пришлите фото или видео со свидания — можно альбомом, до {MAX_REVIEW_PHOTOS} штук "
    f"(видео до {MAX_VIDEO_SIZE // 1024 // 1024} МБ).\n"
    f"Когда закончите (или если их нет), нажмите «{PHOTOS_DONE}»"
)


@router.message(Command("review"))
async def cmd_review(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    dates = await ReviewService(session).list_reviewable_dates(message.from_user.id)
    if not dates:
        await message.answer("Пока нет состоявшихся свиданий без отзыва 🙂")
        return
    user = await UserService(session).get(message.from_user.id)
    await message.answer("О каком свидании оставим отзыв?", reply_markup=pick_date_keyboard(dates, user.timezone))


@router.callback_query(ReviewPick.filter())
async def review_pick(
    callback: CallbackQuery, callback_data: ReviewPick, state: FSMContext, session: AsyncSession
) -> None:
    date = await ReviewService(session).check_can_review(callback_data.date_id, callback.from_user.id)
    await state.clear()
    await state.set_state(ReviewForm.rating)
    await state.update_data(date_id=str(date.id))

    text = f"Отзыв о свидании «{escape(date.title)}»\n\nКак оцените?\n\n/cancel — отменить"
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=rating_keyboard())
    _ = await callback.answer()


@router.callback_query(ReviewForm.rating, ReviewRating.filter())
async def review_rating(callback: CallbackQuery, callback_data: ReviewRating, state: FSMContext) -> None:
    await state.update_data(rating=callback_data.rating)
    await state.set_state(ReviewForm.liked)

    stars = "⭐" * callback_data.rating
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(f"Оценка: {stars}")
        _ = await callback.message.answer(f"Что понравилось?\n\n{SKIP_HINT}")
    _ = await callback.answer()


@router.message(StateFilter(*(state for state in TEXT_STEPS if state is not None)), plain_text)
async def review_text(message: Message, state: FSMContext) -> None:
    field, next_state, question = TEXT_STEPS[await state.get_state()]
    text = (message.text or "").strip()
    await state.update_data({field: None if text == "-" else text[:MAX_REVIEW_TEXT_LENGTH]})
    await state.set_state(next_state)

    if next_state == ReviewForm.photos:
        await message.answer(PHOTOS_PROMPT, reply_markup=photos_done_keyboard)
    else:
        await message.answer(f"{question}\n\n{SKIP_HINT}")


@router.message(ReviewForm.photos, F.photo | F.video)
async def review_photo(message: Message, state: FSMContext) -> None:
    if message.video is not None:
        # Больше 20 МБ бот скачать не сможет, а не MP4 Telegram не покажет в альбоме — проверяем сразу,
        # а не при сохранении, чтобы не ронять весь отзыв
        if (message.video.file_size or 0) > MAX_VIDEO_SIZE:
            await message.answer(
                f"Видео больше {MAX_VIDEO_SIZE // 1024 // 1024} МБ — такое бот сохранить не может. "
                "Пришлите покороче или обрежьте"
            )
            return
        if message.video.mime_type not in (None, VIDEO_TYPE):
            await message.answer("Видео в этом формате не поддерживается — пришлите MP4")
            return
        file_id = message.video.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id  # последнее — в максимальном разрешении
    else:
        return

    # Альбом приходит отдельными сообщениями с общим media_group_id; обрабатываются они по очереди
    # (SimpleEventIsolation в диспетчере), поэтому список в FSM не теряет элементы
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])
    first_in_group = message.media_group_id is None or message.media_group_id != data.get("media_group_id")

    if len(photos) >= MAX_REVIEW_PHOTOS:
        if first_in_group:
            await message.answer(
                f"Больше {MAX_REVIEW_PHOTOS} фото и видео добавить нельзя — нажмите «{PHOTOS_DONE}»"
            )
        await state.update_data(media_group_id=message.media_group_id)
        return

    photos.append(file_id)
    await state.update_data(photos=photos, media_group_id=message.media_group_id)
    # На альбом отвечаем один раз, а не на каждый файл
    if first_in_group:
        await message.answer(
            f"📷 Принял. Пришлите ещё или нажмите «{PHOTOS_DONE}»", reply_markup=photos_done_keyboard
        )


@router.message(ReviewForm.photos, F.text == PHOTOS_DONE)
async def review_done(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    file_ids: list[str] = data.get("photos", [])
    if file_ids:
        await message.answer("Сохраняю отзыв, фото и видео…", reply_markup=ReplyKeyboardRemove())

    photos: list[NewPhoto] = []
    for file_id in file_ids:
        file = await bot.download(file_id)
        if file is None:
            continue
        content = file.read()
        # Фото от Telegram всегда JPEG, видео — MP4; тип всё равно берём по содержимому
        content_type = detect_media_type(content)
        if content_type is None:
            logger.warning("Неизвестный формат файла %s в отзыве, пропускаю", file_id)
            continue
        photos.append(NewPhoto(data=content, content_type=content_type, tg_file_id=file_id))

    review = await ReviewService(session).create(
        date_id=UUID(str(data["date_id"])),
        author_id=message.from_user.id,
        rating=int(data["rating"]),
        liked=data.get("liked"),
        disliked=data.get("disliked"),
        food=data.get("food"),
        comment=data.get("comment"),
        photos=photos,
    )
    # Состояние чистим только после сохранения: если что-то упало, можно ещё раз нажать «Готово»
    await state.clear()

    date = await DateService(session).get_for_user(review.date_id, message.from_user.id)
    reviews = await ReviewService(session).list_for_date(date.id)
    partner = date.invitee if review.author_id == date.created_by else date.creator
    locked = not can_see_review(date, reviews, review, partner.id)

    if locked:
        note = f"🔒 {escape(partner.first_name)} увидит его, когда напишет свой — тогда откроется и отзыв для вас"
    else:
        note = f"Ваш отзыв отправлен {escape(partner.first_name)}"
    await message.answer(
        f"Спасибо! Отзыв сохранён 💝\n\n{notify.describe(review)}\n\n{note}", reply_markup=ReplyKeyboardRemove()
    )
    await notify.announce_review(bot, review, date, reviews, locked)


@router.message(ReviewForm.photos)
async def review_photos_other(message: Message) -> None:
    await message.answer(f"Пришлите фото или видео (именно так, не файлом) или нажмите «{PHOTOS_DONE}»")
