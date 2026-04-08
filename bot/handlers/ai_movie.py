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
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.ai_movie import (
    AiPickCb,
    ai_pick_cancel_keyboard,
    ai_pick_empty_keyboard,
    ai_pick_results_keyboard,
)
from bot.repositories.catalog import get_item_by_id
from bot.services.ai_catalog import extract_params, find_relevant_films
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


# ---------------------------------------------------------------------------
# Вход — кнопка «Подобрать фильм» из главного меню
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ai_pick_movie")
async def cb_ai_pick_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AiPick.waiting)
    await show_text_screen(
        callback,
        _FIRST_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Другая тема» — сбросить параметры, начать заново
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "newtopic"))
async def cb_newtopic(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_data({})
    await state.set_state(AiPick.waiting)
    await show_text_screen(
        callback,
        _NEW_TOPIC_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Уточнить» — сохранить параметры, задать вопрос
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "refine"))
async def cb_refine(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AiPick.refine)
    await show_text_screen(
        callback,
        _REFINE_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(),
        parse_mode="HTML",
    )
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

    await _show_item_card(callback, item, idx, len(item_ids))
    await callback.answer()


# ---------------------------------------------------------------------------
# Ответ пользователя — обработка запроса
# ---------------------------------------------------------------------------

@router.message(StateFilter(AiPick.waiting, AiPick.refine))
async def msg_ai_pick_answer(message: Message, state: FSMContext, session) -> None:
    user_text = (message.text or "").strip()
    if not user_text:
        return

    current_state = await state.get_state()
    data = await state.get_data()

    # При уточнении берём существующие параметры, при новой теме — чистые
    existing_params = data.get("ai_params", {}) if current_state == AiPick.refine.state else {}

    # Извлекаем параметры из запроса пользователя
    params = extract_params(user_text, existing_params)

    # Ищем фильмы
    await message.bot.send_chat_action(message.chat.id, "typing")
    films = await find_relevant_films(session, params, limit=50)

    if not films and any(k in params for k in ("grade", "age", "audience")):
        # Нет фильмов под этот возраст — пробуем только по теме
        params_no_age = {k: v for k, v in params.items() if k not in ("grade", "age", "audience")}
        films = await find_relevant_films(session, params_no_age, limit=50)

    if not films:
        sent = await message.answer(
            "По вашему запросу ничего не нашлось. Попробуйте другую тему или более общий запрос.",
            reply_markup=ai_pick_empty_keyboard(),
        )
        await state.update_data(ai_last_msg_id=sent.message_id)
        return

    # Сохраняем результаты в state
    item_ids = [f.id for f in films]
    await state.update_data(ai_item_ids=item_ids, ai_params=params)

    # Формируем заголовок подборки
    topic = _describe_params(params)
    header = f"Нашёл <b>{len(films)}</b> фильм{'ов' if len(films) >= 5 else 'а' if len(films) >= 2 else ''}"
    if topic:
        header += f" — {topic}"
    header += ".\n\nМожем посмотреть другие темы или уточнить параметры."

    await message.answer(header, parse_mode="HTML")

    # Показываем первую карточку
    first = films[0]
    await _show_item_card_message(message, first, 0, len(films))


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


async def _show_item_card(callback: CallbackQuery, item, idx: int, total: int) -> None:
    """Показывает карточку фильма через edit (для листания)."""
    keyboard = ai_pick_results_keyboard(idx, total, item.id)
    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        if len(caption) > 1024:
            caption = caption[:1020] + "…"
        await show_photo_screen(callback, photo=item.image_url, caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await show_text_screen(callback, format_item_text(item), reply_markup=keyboard, parse_mode="HTML")


async def _show_item_card_message(message: Message, item, idx: int, total: int) -> None:
    """Показывает карточку фильма как новое сообщение (первый результат)."""
    keyboard = ai_pick_results_keyboard(idx, total, item.id)
    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        if len(caption) > 1024:
            caption = caption[:1020] + "…"
        await message.answer_photo(
            photo=item.image_url,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            format_item_text(item),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
