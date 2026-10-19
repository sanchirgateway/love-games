from datetime import UTC, datetime, timedelta
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_day_start, parse_local_date
from app.feature.flowers import notify
from app.feature.flowers.keyboards import (
    OCCASION_LABELS,
    PHOTOS_DONE,
    REACTION_EMOJI,
    FlowerAddPhotos,
    FlowerGive,
    FlowerList,
    FlowerNew,
    FlowerOccasionPick,
    FlowerOpen,
    FlowerPhotos,
    FlowerReact,
    FlowerWhen,
    flowers_list_keyboard,
    gift_detail_keyboard,
    occasion_keyboard,
    photos_done_keyboard,
    when_keyboard,
)
from app.feature.flowers.models import MAX_FLOWER_PHOTOS, FlowerGift, FlowerOccasion
from app.feature.flowers.service import FLOWERS_MAX, PRICE_MAX, TEXT_MAX, FlowerService, NewFlowerPhoto
from app.feature.user.service import UserService

router = Router()

# Обычный текст, не команда — чтобы /cancel и другие команды не попадали в ответы диалога
plain_text = F.text & ~F.text.startswith("/")

SKIP_HINT = "Напишите ответ или «-», чтобы пропустить"
GIFTS_IN_LIST = 20


class GiftForm(StatesGroup):
    flowers = State()
    occasion = State()
    comment = State()
    price = State()
    photos = State()
    when = State()


class AddPhotos(StatesGroup):
    photos = State()


def _skip(text: str | None, limit: int = TEXT_MAX) -> str | None:
    """«-» — пропустить шаг."""
    text = (text or "").strip()
    return None if text == "-" else text[:limit]


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if callback.message is not None and not isinstance(callback.message, InaccessibleMessage):
        _ = await callback.message.edit_text(text, reply_markup=reply_markup)


# --- /flowers: журнал ---


async def _flowers_list(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    service = FlowerService(session)
    user = await UserService(session).get(user_id)
    gifts = await service.list_for_user(user_id, GIFTS_IN_LIST)
    if not gifts:
        return "Букетов пока нет. Запишите первый 💐", flowers_list_keyboard([], user_id, user.timezone)
    given = await service.count_given(user_id)
    text = f"💐 Цветы\n\nВы подарили букетов: {given}\n💐 — от вас, 🎁 — вам, 🤫 — ещё не вручён"
    return text, flowers_list_keyboard(gifts, user_id, user.timezone)


@router.message(Command("flowers"))
async def cmd_flowers(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text, keyboard = await _flowers_list(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(FlowerList.filter())
async def back_to_list(callback: CallbackQuery, session: AsyncSession) -> None:
    text, keyboard = await _flowers_list(session, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


async def _gift_card(session: AsyncSession, gift: FlowerGift, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    viewer = await UserService(session).get(user_id)
    return notify.describe(gift, viewer), gift_detail_keyboard(gift, user_id)


@router.callback_query(FlowerOpen.filter())
async def open_gift(callback: CallbackQuery, callback_data: FlowerOpen, session: AsyncSession) -> None:
    gift = await FlowerService(session).get(callback_data.gift_id, callback.from_user.id)
    text, keyboard = await _gift_card(session, gift, callback.from_user.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer()


@router.callback_query(FlowerPhotos.filter())
async def show_photos(callback: CallbackQuery, callback_data: FlowerPhotos, session: AsyncSession, bot: Bot) -> None:
    gift = await FlowerService(session).get(callback_data.gift_id, callback.from_user.id)
    _ = await callback.answer()
    giver, recipient = await FlowerService(session).participants(gift)
    await notify.send_all_photos(bot, callback.from_user.id, gift, giver, recipient)


@router.callback_query(FlowerGive.filter())
async def give_gift(callback: CallbackQuery, callback_data: FlowerGive, session: AsyncSession, bot: Bot) -> None:
    service = FlowerService(session)
    gift = await service.give(callback_data.gift_id, callback.from_user.id)
    giver, recipient = await service.participants(gift)
    text, keyboard = await _gift_card(session, gift, giver.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer(f"Отправил {recipient.first_name} 💐")
    await notify.send_gift(bot, gift, giver, recipient)


@router.callback_query(FlowerReact.filter())
async def react(callback: CallbackQuery, callback_data: FlowerReact, session: AsyncSession, bot: Bot) -> None:
    service = FlowerService(session)
    gift = await service.react(callback_data.gift_id, callback.from_user.id, callback_data.reaction)
    giver, recipient = await service.participants(gift)
    text, keyboard = await _gift_card(session, gift, recipient.id)
    await _edit_or_answer(callback, text, keyboard)
    _ = await callback.answer(REACTION_EMOJI[callback_data.reaction])
    await notify.send_reaction(bot, gift, giver, recipient)


# --- Записать букет ---


@router.callback_query(FlowerNew.filter())
async def new_gift(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    _, partner = await FlowerService(session).couple(callback.from_user.id)  # AppError, если пары нет
    await state.clear()
    await state.set_state(GiftForm.flowers)
    _ = await callback.answer()
    if callback.message is not None:
        _ = await callback.message.answer(
            f"Букет для {escape(partner.first_name)} 💐\n\n"
            "Какие цветы? Например: «15 белых роз»\n\n/cancel — отменить"
        )


@router.message(GiftForm.flowers, plain_text)
async def gift_flowers(message: Message, state: FSMContext) -> None:
    await state.update_data(flowers=(message.text or "").strip()[:FLOWERS_MAX])
    await state.set_state(GiftForm.occasion)
    await message.answer("По какому поводу?", reply_markup=occasion_keyboard())


@router.callback_query(GiftForm.occasion, FlowerOccasionPick.filter())
async def gift_occasion(callback: CallbackQuery, callback_data: FlowerOccasionPick, state: FSMContext) -> None:
    occasion = callback_data.occasion
    await state.update_data(occasion=occasion.value if occasion else None)
    await state.set_state(GiftForm.comment)
    await _edit_or_answer(callback, f"Повод: {OCCASION_LABELS[occasion]}" if occasion else "Повод: пропущено")
    if callback.message is not None:
        _ = await callback.message.answer(
            f"Пара слов о букете: где купили, почему именно эти цветы?\n\n{SKIP_HINT}"
        )
    _ = await callback.answer()


@router.message(GiftForm.comment, plain_text)
async def gift_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=_skip(message.text))
    await state.set_state(GiftForm.price)
    await message.answer(f"Сколько стоил букет, в рублях? Видно только вам\n\n{SKIP_HINT}")


@router.message(GiftForm.price, plain_text)
async def gift_price(message: Message, state: FSMContext) -> None:
    text = _skip(message.text)
    price = None
    if text is not None:
        digits = text.replace(" ", "").removesuffix("₽").removesuffix("р")
        if not digits.isdigit() or int(digits) > PRICE_MAX:
            await message.answer("Напишите сумму числом, например <code>3500</code>, или «-»")
            return
        price = int(digits)
    await state.update_data(price=price)
    await state.set_state(GiftForm.photos)
    await message.answer(
        f"Пришлите фото букета — можно альбомом, до {MAX_FLOWER_PHOTOS} штук.\n"
        f"Когда закончите (или если фото нет), нажмите «{PHOTOS_DONE}»",
        reply_markup=photos_done_keyboard,
    )


@router.message(StateFilter(GiftForm.photos, AddPhotos.photos), F.photo)
async def collect_photo(message: Message, state: FSMContext) -> None:
    """Фото и для нового букета, и досланные к существующему."""
    if not message.photo:
        return
    # Альбом приходит отдельными сообщениями с общим media_group_id; обрабатываются они по очереди
    # (SimpleEventIsolation в диспетчере), поэтому список в FSM не теряет элементы
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])
    limit = int(data.get("photo_limit", MAX_FLOWER_PHOTOS))
    first_in_group = message.media_group_id is None or message.media_group_id != data.get("media_group_id")

    if len(photos) >= limit:
        if first_in_group:
            await message.answer(f"Больше {limit} фото добавить нельзя — нажмите «{PHOTOS_DONE}»")
        await state.update_data(media_group_id=message.media_group_id)
        return

    photos.append(message.photo[-1].file_id)  # последнее — в максимальном разрешении
    await state.update_data(photos=photos, media_group_id=message.media_group_id)
    # На альбом отвечаем один раз, а не на каждый файл
    if first_in_group:
        await message.answer(f"📷 Принял. Пришлите ещё или нажмите «{PHOTOS_DONE}»", reply_markup=photos_done_keyboard)


@router.message(GiftForm.photos, F.text == PHOTOS_DONE)
async def gift_photos_done(message: Message, state: FSMContext) -> None:
    await state.set_state(GiftForm.when)
    await message.answer("Записал ✅", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Когда вручили? Нажмите кнопку или напишите дату: <code>12.10</code>\n\n"
        "Если это сюрприз на потом — партнёр не увидит запись, пока вы не нажмёте «Вручено»",
        reply_markup=when_keyboard(),
    )


def _given_at(day_start: datetime, tz: str) -> datetime:
    """Сегодня — текущий момент; другой день — его полдень: так дата не съедет у партнёра в другом часовом поясе."""
    if day_start.date() == datetime.now(ZoneInfo(tz)).date():
        return datetime.now(UTC)
    return day_start + timedelta(hours=12)


@router.callback_query(GiftForm.when, FlowerWhen.filter())
async def gift_when_button(
    callback: CallbackQuery, callback_data: FlowerWhen, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    _ = await callback.answer()
    if callback.message is None or isinstance(callback.message, InaccessibleMessage):
        return
    _ = await callback.message.edit_reply_markup(reply_markup=None)
    given_at = None
    if callback_data.days_ago is not None:
        user = await UserService(session).get(callback.from_user.id)
        day = datetime.now(ZoneInfo(user.timezone)).date() - timedelta(days=callback_data.days_ago)
        given_at = _given_at(local_day_start(day, user.timezone), user.timezone)
    await _save(callback.message, callback.from_user.id, state, session, bot, given_at)


@router.message(GiftForm.when, plain_text)
async def gift_when_text(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    user = await UserService(session).get(message.from_user.id)
    day = parse_local_date(message.text or "", user.timezone)
    if day is None:
        await message.answer("Не понял дату 🤔 Формат: <code>12.10</code> или <code>12.10.2026</code>")
        return
    if day > datetime.now(ZoneInfo(user.timezone)).date():
        await message.answer("Этот день ещё не наступил 🙂 Если вручите позже — нажмите «Ещё не вручили»")
        return
    await _save(message, user.id, state, session, bot, _given_at(local_day_start(day, user.timezone), user.timezone))


async def _save(
    reply: Message, user_id: int, state: FSMContext, session: AsyncSession, bot: Bot, given_at: datetime | None
) -> None:
    data = await state.get_data()
    file_ids: list[str] = data.get("photos", [])
    if file_ids:
        await reply.answer("Сохраняю букет и фото…")
    photos = await _download(bot, file_ids)

    service = FlowerService(session)
    gift = await service.create(
        giver_id=user_id,
        flowers=str(data["flowers"]),
        occasion=FlowerOccasion(data["occasion"]) if data.get("occasion") else None,
        comment=data.get("comment"),
        price=data.get("price"),
        given_at=given_at,
        photos=photos,
    )
    # Состояние чистим только после сохранения: если что-то упало, можно ответить ещё раз
    await state.clear()

    giver, recipient = await service.participants(gift)
    text, keyboard = await _gift_card(session, gift, user_id)
    if gift.is_given:
        note = f"Отправил {escape(recipient.first_name)} 💐"
    else:
        note = f"🤫 {escape(recipient.first_name)} не увидит запись, пока вы не нажмёте «Вручено»"
    await reply.answer(f"Сохранил ✅\n\n{text}\n\n{note}", reply_markup=keyboard)
    if gift.is_given:
        await notify.send_gift(bot, gift, giver, recipient)


async def _download(bot: Bot, file_ids: list[str]) -> list[NewFlowerPhoto]:
    photos: list[NewFlowerPhoto] = []
    for file_id in file_ids:
        file = await bot.download(file_id)
        if file is not None:
            photos.append(NewFlowerPhoto(data=file.read(), tg_file_id=file_id))
    return photos


# --- Дослать фото к букету ---


@router.callback_query(FlowerAddPhotos.filter())
async def add_photos_start(
    callback: CallbackQuery, callback_data: FlowerAddPhotos, state: FSMContext, session: AsyncSession
) -> None:
    gift = await FlowerService(session).get(callback_data.gift_id, callback.from_user.id)
    left = MAX_FLOWER_PHOTOS - len(gift.photos_by(callback.from_user.id))
    if left <= 0:
        _ = await callback.answer(f"Вы уже добавили {MAX_FLOWER_PHOTOS} фото", show_alert=True)
        return
    await state.clear()
    await state.set_state(AddPhotos.photos)
    await state.update_data(gift_id=str(gift.id), photo_limit=left)
    _ = await callback.answer()
    if callback.message is not None:
        hint = "Например, как букет стоит в вазе 🏺" if gift.recipient_id == callback.from_user.id else ""
        _ = await callback.message.answer(
            f"Пришлите фото букета «{escape(gift.flowers)}» — можно альбомом, до {left} штук. {hint}\n"
            f"Когда закончите, нажмите «{PHOTOS_DONE}»\n\n/cancel — отменить",
            reply_markup=photos_done_keyboard,
        )


@router.message(AddPhotos.photos, F.text == PHOTOS_DONE)
async def add_photos_done(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    file_ids: list[str] = data.get("photos", [])
    if not file_ids:
        await message.answer("Фото не прислали — ничего не добавил", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return
    await message.answer("Сохраняю фото…", reply_markup=ReplyKeyboardRemove())

    service = FlowerService(session)
    added = await _download(bot, file_ids)
    gift = await service.add_photos(UUID(str(data["gift_id"])), message.from_user.id, added)
    # Состояние чистим только после сохранения: если что-то упало, можно ещё раз нажать «Готово»
    await state.clear()

    giver, recipient = await service.participants(gift)
    author, other = (giver, recipient) if message.from_user.id == giver.id else (recipient, giver)
    new_photos = gift.photos_by(author.id)[-len(added) :]
    text, keyboard = await _gift_card(session, gift, author.id)
    note = f"Отправил {escape(other.first_name)} 📷" if gift.is_given else ""
    await message.answer(f"Добавил фото ✅ {note}\n\n{text}", reply_markup=keyboard)
    await notify.send_added_photos(bot, gift, new_photos, author, other)


# Последним: aiogram проверяет хендлеры по порядку, и этот перехватил бы «Готово» из обоих диалогов с фото
@router.message(StateFilter(GiftForm.photos, AddPhotos.photos))
async def photos_other(message: Message) -> None:
    await message.answer(f"Пришлите фото (именно фото, не файлом) или нажмите «{PHOTOS_DONE}»")
