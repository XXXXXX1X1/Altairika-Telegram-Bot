"""
AI-подбор фильма.

Флоу:
  cb ai_pick_movie → задаём первый вопрос → AiPick.waiting
  msg (AiPick.waiting / AiPick.refine) → extract_params → find_relevant_films → показываем карточки
  cb aip:nav → листаем карточки
  cb aip:newtopic → сбрасываем параметры, снова AiPick.waiting
  cb aip:refine → сохраняем параметры, AiPick.refine
  cb aip:exit → главное меню
"""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.ai_movie import (
    AiPickCb,
    ai_pick_cancel_keyboard,
    ai_pick_empty_keyboard,
    ai_pick_results_keyboard,
)
from bot.keyboards.ai import after_ai_keyboard
from bot.repositories.catalog import get_item_by_id
from bot.services.ai_catalog import extract_params, find_relevant_films
from bot.services.ai_router import detect_intent
from bot.services.catalog import format_item_text
from bot.states.ai_movie import AiPick
from bot.utils.message_render import show_photo_screen, show_text_screen

logger = logging.getLogger(__name__)
router = Router()

_FIRST_QUESTION = (
    "🎬 <b>Подбор фильма</b>\n\n"
    "Расскажите что нужно найти.\n\n"
    "Например:\n"
    "• «ПДД для 2 класса»\n"
    "• «природа, до 20 минут»\n"
    "• «что-нибудь про космос для детсада»\n\n"
    "Или просто напишите тему — покажу всё что есть."
)

_REFINE_QUESTION = (
    "Уточните запрос — например по возрасту, длительности или теме:"
)

_NEW_TOPIC_QUESTION = (
    "Хорошо! Напишите новую тему или параметры — подберу другие фильмы:"
)

_REFINE_REQUEST_HINTS = (
    "уточним", "уточнить", "давай уточним", "хочу уточнить",
    "давай подробнее", "подробнее", "сузим", "сужай", "давай сузим",
)

_NO_NEW_PARAMS_TEXT = (
    "Пока не вижу новых параметров.\n\n"
    "Напишите, что именно уточнить: тему, возраст, класс или длительность.\n\n"
    "Например: «ПДД, 7 лет» или «до 15 минут, начальная школа»."
)

_LEAD_INTENTS = {"lead_booking", "lead_franchise"}


# ---------------------------------------------------------------------------
# Вход — кнопка «Подобрать фильм» из главного меню
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ai_pick_movie")
async def cb_ai_pick_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AiPick.waiting)
    sent = await show_text_screen(
        callback,
        _FIRST_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Другая тема» — сбросить параметры, начать заново
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "newtopic"))
async def cb_newtopic(callback: CallbackQuery, state: FSMContext) -> None:
    await _clear_ai_pick_messages(callback.bot, state)
    await state.set_data({})
    await state.set_state(AiPick.waiting)
    sent = await show_text_screen(
        callback,
        _NEW_TOPIC_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Уточнить» — сохранить параметры, задать вопрос
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "refine"))
async def cb_refine(callback: CallbackQuery, state: FSMContext) -> None:
    await _delete_ai_pick_header(callback.bot, state)
    await state.set_state(AiPick.refine)
    sent = await show_text_screen(
        callback,
        _REFINE_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
    await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
    await callback.answer()


# ---------------------------------------------------------------------------
# Листание карточек ← →
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "nav"))
async def cb_nav(callback: CallbackQuery, callback_data: AiPickCb, state: FSMContext, session) -> None:
    data = await state.get_data()
    item_ids: list[int] = data.get("ai_item_ids", [])
    if not item_ids:
        await callback.answer("Подборка устарела — начните поиск заново.", show_alert=True)
        return

    idx = max(0, min(callback_data.idx, len(item_ids) - 1))
    item = await get_item_by_id(session, item_ids[idx])
    if not item:
        await callback.answer("Фильм не найден.", show_alert=True)
        return

    await _show_item_card(callback, state, item, idx, len(item_ids))
    await callback.answer()


# ---------------------------------------------------------------------------
# Ответ пользователя — обработка запроса
# ---------------------------------------------------------------------------

@router.message(StateFilter(AiPick.waiting, AiPick.refine))
async def msg_ai_pick_answer(message: Message, state: FSMContext, session) -> None:
    await run_ai_pick_flow(message, state, session)


async def run_ai_pick_flow(message: Message, state: FSMContext, session) -> None:
    """Общий flow подбора фильмов для кнопки и свободного текста."""
    user_text = (message.text or "").strip()
    if not user_text:
        return

    current_state = await state.get_state()
    data = await state.get_data()
    detected_intent = detect_intent(user_text)

    if detected_intent in _LEAD_INTENTS:
        await _clear_ai_pick_messages(message.bot, state)
        await state.clear()
        if detected_intent == "lead_booking":
            reply = "Отлично! Нажмите кнопку ниже чтобы оставить заявку на сеанс:"
        else:
            reply = "Хорошо! Нажмите кнопку ниже чтобы оставить заявку на франшизу:"
        await message.answer(reply, reply_markup=after_ai_keyboard(detected_intent))
        return

    # При уточнении берём существующие параметры, при новой теме — чистые
    existing_params = {}
    if current_state == AiPick.refine.state:
        existing_params = data.get("ai_params", {})
    elif _should_refine_existing_selection(user_text, data):
        existing_params = data.get("ai_params", {})

    if current_state == AiPick.waiting.state and _looks_like_refine_request(user_text):
        await _delete_ai_pick_prompt(message.bot, state)
        await state.set_state(AiPick.refine)
        sent = await message.answer(
            _REFINE_QUESTION,
            reply_markup=ai_pick_cancel_keyboard(),
            parse_mode="HTML",
        )
        await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
        return

    # Извлекаем параметры из запроса пользователя
    params = extract_params(user_text, existing_params)

    if current_state == AiPick.refine.state and not _has_new_constraints(existing_params, params):
        await _delete_ai_pick_prompt(message.bot, state)
        sent = await message.answer(
            _NO_NEW_PARAMS_TEXT,
            reply_markup=ai_pick_cancel_keyboard(),
            parse_mode="HTML",
        )
        await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
        return

    # Ищем фильмы
    await message.bot.send_chat_action(message.chat.id, "typing")
    films = await find_relevant_films(session, params, limit=50)

    if not films and any(k in params for k in ("grade", "age", "audience")):
        # Нет фильмов под этот возраст — пробуем только по теме
        params_no_age = {k: v for k, v in params.items() if k not in ("grade", "age", "audience")}
        films = await find_relevant_films(session, params_no_age, limit=50)

    if not films:
        await _clear_ai_pick_messages(message.bot, state)
        sent = await message.answer(
            "По вашему запросу ничего не нашлось. Попробуйте другую тему или более общий запрос.",
            reply_markup=ai_pick_empty_keyboard(),
        )
        await state.update_data(ai_prompt_msg_id=sent.message_id, ai_prompt_chat_id=sent.chat.id)
        return

    await _clear_ai_pick_messages(message.bot, state)

    # Сохраняем результаты в state
    item_ids = [f.id for f in films]
    await state.update_data(ai_item_ids=item_ids, ai_params=params)

    # Формируем заголовок подборки
    topic = _describe_params(params)
    header = f"Нашёл <b>{len(films)}</b> фильм{'ов' if len(films) >= 5 else 'а' if len(films) >= 2 else ''}"
    if topic:
        header += f" — {topic}"
    header += ".\n\nМожем посмотреть другие темы или уточнить параметры."

    header_message = await message.answer(header, parse_mode="HTML")
    await state.update_data(ai_header_msg_id=header_message.message_id, ai_header_chat_id=header_message.chat.id)

    # Показываем первую карточку
    first = films[0]
    card_message = await _show_item_card_message(message, first, 0, len(films))
    await state.update_data(ai_card_msg_id=card_message.message_id, ai_card_chat_id=card_message.chat.id)
    await state.set_state(AiPick.waiting)


def _describe_params(params: dict) -> str:
    """Краткое описание найденных параметров для заголовка."""
    parts = []
    theme = params.get("theme")
    if theme:
        parts.append(f"тема «{theme}»")
    grade = params.get("grade")
    if grade:
        parts.append(f"{grade} класс")
    elif params.get("audience") == "preschool":
        parts.append("дошкольники")
    elif params.get("audience") == "primary":
        parts.append("начальная школа")
    duration = params.get("duration")
    if duration:
        labels = {"d5": "до 5 мин", "d15": "до 15 мин", "d30": "до 30 мин", "d30p": "30+ мин"}
        parts.append(labels.get(duration, ""))
    return ", ".join(p for p in parts if p)


async def _show_item_card(
    callback: CallbackQuery,
    state: FSMContext,
    item,
    idx: int,
    total: int,
) -> None:
    """Показывает карточку фильма через edit (для листания)."""
    keyboard = ai_pick_results_keyboard(idx, total, item.id)
    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        if len(caption) > 1024:
            caption = caption[:1020] + "…"
        sent = await show_photo_screen(callback, photo=item.image_url, caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        sent = await show_text_screen(callback, format_item_text(item), reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(ai_card_msg_id=sent.message_id, ai_card_chat_id=sent.chat.id, ai_prompt_msg_id=None, ai_prompt_chat_id=None)


async def _show_item_card_message(message: Message, item, idx: int, total: int):
    """Показывает карточку фильма как новое сообщение (первый результат)."""
    keyboard = ai_pick_results_keyboard(idx, total, item.id)
    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        if len(caption) > 1024:
            caption = caption[:1020] + "…"
        try:
            return await message.answer_photo(
                photo=item.image_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass

    return await message.answer(
        format_item_text(item),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _looks_like_refine_request(text: str) -> bool:
    lower = text.lower().strip()
    return any(hint in lower for hint in _REFINE_REQUEST_HINTS)


def _has_new_constraints(existing_params: dict, new_params: dict) -> bool:
    for key in ("theme", "grade", "age", "audience", "duration"):
        if existing_params.get(key) != new_params.get(key):
            return True
    return False


def _should_refine_existing_selection(user_text: str, data: dict) -> bool:
    existing_params = data.get("ai_params") or {}
    if not existing_params or not data.get("ai_item_ids"):
        return False

    lower = user_text.lower()
    new_params = extract_params(user_text, existing_params)
    if _has_new_constraints(existing_params, new_params):
        return True

    return any(
        hint in lower
        for hint in (
            "тема", "возраст", "лет", "класс", "длительность", "минут", "мин",
            "дошколь", "начальн", "средн", "пдд", "космос", "природ", "истори",
            "животн", "наук", "географ", "биолог", "обж", "английск",
        )
    )


async def _delete_ai_pick_header(bot, state: FSMContext) -> None:
    data = await state.get_data()
    message_id = data.get("ai_header_msg_id")
    chat_id = data.get("ai_header_chat_id")
    if not message_id or not chat_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass
    await state.update_data(ai_header_msg_id=None, ai_header_chat_id=None)


async def _delete_ai_pick_prompt(bot, state: FSMContext) -> None:
    data = await state.get_data()
    message_id = data.get("ai_prompt_msg_id")
    chat_id = data.get("ai_prompt_chat_id")
    if not message_id or not chat_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass
    await state.update_data(ai_prompt_msg_id=None, ai_prompt_chat_id=None)


async def _clear_ai_pick_messages(bot, state: FSMContext) -> None:
    data = await state.get_data()
    for message_key, chat_key in (
        ("ai_prompt_msg_id", "ai_prompt_chat_id"),
        ("ai_header_msg_id", "ai_header_chat_id"),
        ("ai_card_msg_id", "ai_card_chat_id"),
    ):
        message_id = data.get(message_key)
        chat_id = data.get(chat_key)
        if not message_id or not chat_id:
            continue
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramBadRequest:
            pass

    await state.update_data(
        ai_prompt_msg_id=None,
        ai_prompt_chat_id=None,
        ai_header_msg_id=None,
        ai_header_chat_id=None,
        ai_card_msg_id=None,
        ai_card_chat_id=None,
    )
