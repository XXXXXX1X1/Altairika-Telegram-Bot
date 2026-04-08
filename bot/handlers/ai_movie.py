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
from bot.keyboards.catalog import item_text_keyboard
from bot.repositories.catalog import get_available_theme_filters, get_item_by_id
from bot.services.ai_answer import generate_answer
from bot.services.ai_branch import decide_next_intent
from bot.services.ai_catalog import extract_params as extract_params_regex, find_relevant_films
from bot.services.ai_decision import analyze_dialog_scenario
from bot.services.ai_memory import load_state as load_ai_state, update_state as save_ai_state
from bot.services.ai_movie_params import extract_movie_params
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

_SELECTION_START_QUESTION = (
    "🎬 <b>Давайте подберём фильм</b>\n\n"
    "Напишите, что важно для подбора: тему, возраст, класс или длительность.\n\n"
    "Например:\n"
    "• «ПДД для 2 класса»\n"
    "• «история, 7 лет»\n"
    "• «природа, до 20 минут»\n\n"
    "Можно начать и с одного параметра, например: «космос»."
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
_MOVIE_PARAM_KEYS = ("theme", "grade", "age", "audience", "duration")
_THEME_LIST_HINTS = (
    "какие есть темы", "какие темы", "список тем", "покажи темы",
    "какие есть направления", "какие направления", "что есть по темам",
)


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
    await state.update_data(
        ai_prompt_msg_id=sent.message_id,
        ai_prompt_chat_id=sent.chat.id,
        ai_flow_step="waiting_theme",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Другая тема» — сбросить параметры, начать заново
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "newtopic"))
async def cb_newtopic(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_ai_pick_snapshot(state)
    snapshot = (await state.get_data()).get("ai_prev_snapshot")
    await _clear_ai_pick_messages(callback.bot, state)
    await state.set_data({"ai_prev_snapshot": snapshot} if snapshot else {})
    await state.set_state(AiPick.waiting)
    sent = await callback.message.answer(
        _NEW_TOPIC_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(show_back=True),
        parse_mode="HTML",
    )
    await state.update_data(
        ai_prompt_msg_id=sent.message_id,
        ai_prompt_chat_id=sent.chat.id,
        ai_flow_step="waiting_theme",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Кнопка «Уточнить» — сохранить параметры, задать вопрос
# ---------------------------------------------------------------------------

@router.callback_query(AiPickCb.filter(F.action == "refine"))
async def cb_refine(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_ai_pick_snapshot(state)
    await _clear_ai_pick_messages(callback.bot, state)
    await state.set_state(AiPick.refine)
    sent = await callback.message.answer(
        _REFINE_QUESTION,
        reply_markup=ai_pick_cancel_keyboard(show_back=True),
        parse_mode="HTML",
    )
    await state.update_data(
        ai_prompt_msg_id=sent.message_id,
        ai_prompt_chat_id=sent.chat.id,
        ai_flow_step="waiting_filters",
    )
    await callback.answer()


@router.callback_query(AiPickCb.filter(F.action == "back"))
async def cb_back(callback: CallbackQuery, state: FSMContext, session) -> None:
    restored = await _restore_ai_pick_snapshot(callback.message, state, session)
    if not restored:
        await callback.answer("Возвращаться некуда.", show_alert=True)
        return
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
    persisted_state = await load_ai_state(session, callback.from_user.id)
    persisted_state.update({
        "ai_current_item_id": item.id,
        "ai_current_item_title": item.title,
        "ai_current_idx": idx,
    })
    await save_ai_state(session, callback.from_user.id, "movie_selection", persisted_state)
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
    decision_state = {"_active_intent": "movie_selection", **data}
    decision = await analyze_dialog_scenario(user_text, decision_state)
    if not decision or decision.get("confidence", 0.0) < 0.45:
        decision = decide_next_intent(user_text, decision_state)
    detected_intent = decision["intent"]
    action = _resolve_movie_action(decision, user_text, current_state, data)

    if detected_intent != "movie_selection":
        await _clear_ai_pick_messages(message.bot, state)
        await state.clear()

        if decision.get("open_current_movie_card") and data.get("ai_current_item_id"):
            await send_movie_card_message(message, session, data["ai_current_item_id"])
            return

        if detected_intent in _LEAD_INTENTS:
            if detected_intent == "lead_booking":
                reply = "Отлично! Нажмите кнопку ниже чтобы оставить заявку на сеанс:"
            else:
                reply = "Хорошо! Нажмите кнопку ниже чтобы оставить заявку на франшизу:"
            await message.answer(reply, reply_markup=after_ai_keyboard(detected_intent))
            return

        ai_query = user_text
        if decision.get("use_current_movie") and data.get("ai_current_item_title"):
            ai_query = f"Расскажи подробнее о фильме {data['ai_current_item_title']}"

        answer = await generate_answer(
            db=session,
            telegram_user_id=message.from_user.id,
            user_text=ai_query,
            intent=str(detected_intent),
        )
        if answer:
            await message.answer(answer, reply_markup=after_ai_keyboard(str(detected_intent)))
        return

    # При уточнении берём существующие параметры, при новой теме — чистые
    existing_params = {}
    if current_state == AiPick.refine.state:
        existing_params = data.get("ai_params", {})
    elif _should_refine_existing_selection(user_text, data):
        existing_params = data.get("ai_params", {})

    if current_state == AiPick.waiting.state and action == "ask_clarification" and _looks_like_refine_request(user_text):
        await _delete_ai_pick_prompt(message.bot, state)
        await state.set_state(AiPick.refine)
        sent = await message.answer(
            _REFINE_QUESTION,
            reply_markup=ai_pick_cancel_keyboard(show_back=True),
            parse_mode="HTML",
        )
        await state.update_data(
            ai_prompt_msg_id=sent.message_id,
            ai_prompt_chat_id=sent.chat.id,
            ai_flow_step="waiting_filters",
        )
        return

    if action == "show_themes":
        await _send_theme_list(message, state, session)
        return

    # Извлекаем параметры из запроса пользователя
    params = await extract_movie_params(user_text, existing_params)

    if action == "ask_clarification" or _should_ask_for_selection_details(current_state, existing_params, params):
        await _send_selection_question(
            message,
            state,
            session,
            existing_params=existing_params,
            params=params,
            data=data,
        )
        return

    if current_state == AiPick.refine.state and not _has_new_constraints(existing_params, params):
        await _delete_ai_pick_prompt(message.bot, state)
        sent = await message.answer(
            _NO_NEW_PARAMS_TEXT,
            reply_markup=ai_pick_cancel_keyboard(show_back=True),
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
    await state.update_data(
        ai_card_msg_id=card_message.message_id,
        ai_card_chat_id=card_message.chat.id,
        ai_current_item_id=first.id,
        ai_current_item_title=first.title,
        ai_current_idx=0,
        ai_flow_step="showing_results",
    )
    persisted_state = await load_ai_state(session, message.from_user.id)
    persisted_state.update({
        "params": params,
        "ai_params": params,
        "last_recommended_ids": item_ids,
        "ai_current_item_id": first.id,
        "ai_current_item_title": first.title,
        "ai_current_idx": 0,
        "ai_flow_step": "showing_results",
    })
    await save_ai_state(session, message.from_user.id, "movie_selection", persisted_state)
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
    await state.update_data(
        ai_card_msg_id=sent.message_id,
        ai_card_chat_id=sent.chat.id,
        ai_prompt_msg_id=None,
        ai_prompt_chat_id=None,
        ai_current_item_id=item.id,
        ai_current_item_title=item.title,
        ai_current_idx=idx,
        ai_flow_step="showing_results",
    )


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


async def send_movie_card_message(message: Message, session, item_id: int) -> None:
    """Отправляет карточку конкретного фильма в чат."""
    item = await get_item_by_id(session, item_id)
    if not item:
        await message.answer("Фильм не найден.")
        return

    keyboard = item_text_keyboard(
        item_id=item.id,
        cat_id=0,
        page=1,
        similar_theme_key=None,
        item_url=item.url,
    )
    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        if len(caption) > 1024:
            caption = caption[:1020] + "…"
        try:
            await message.answer_photo(
                photo=item.image_url,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except TelegramBadRequest:
            pass

    await message.answer(
        format_item_text(item),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _looks_like_refine_request(text: str) -> bool:
    lower = text.lower().strip()
    return any(hint in lower for hint in _REFINE_REQUEST_HINTS)


def _resolve_movie_action(decision: dict, user_text: str, current_state: str | None, data: dict) -> str:
    action = str(decision.get("action") or "").strip()
    if action:
        return action
    existing_params = data.get("ai_params") or {}
    inferred_params = extract_params_regex(user_text, existing_params)
    if _has_meaningful_movie_params(inferred_params):
        return "run_search"
    if _wants_theme_list(user_text):
        return "show_themes"
    if current_state == AiPick.waiting.state and _looks_like_refine_request(user_text):
        return "ask_clarification"
    if existing_params or data.get("ai_item_ids"):
        return "run_search"
    return "ask_clarification"


def _wants_theme_list(text: str) -> bool:
    lower = text.lower().strip()
    return any(hint in lower for hint in _THEME_LIST_HINTS)


async def _send_theme_list(message: Message, state: FSMContext, session) -> None:
    themes_text = await _build_theme_list_text(session)
    sent = await message.answer(
        themes_text,
        reply_markup=ai_pick_cancel_keyboard(show_back=True),
        parse_mode="HTML",
    )
    await state.set_state(AiPick.waiting)
    await state.update_data(
        ai_theme_hint_msg_id=sent.message_id,
        ai_theme_hint_chat_id=sent.chat.id,
        ai_flow_step="waiting_theme",
    )
    persisted_state = await load_ai_state(session, message.from_user.id)
    persisted_state["ai_flow_step"] = "waiting_theme"
    await save_ai_state(session, message.from_user.id, "movie_selection", persisted_state)


async def _build_theme_list_text(session) -> str:
    theme_filters = await get_available_theme_filters(session)
    if not theme_filters:
        return (
            "🎬 <b>Подбор фильма</b>\n\n"
            "Пока не удалось получить список тем.\n"
            "Напишите тему своими словами, и я попробую подобрать фильм."
        )

    grouped = _group_theme_labels([label for _, label in theme_filters])
    lines = []
    for group_name, labels in grouped:
        preview = ", ".join(labels[:3])
        if len(labels) > 3:
            preview += " и другое"
        lines.append(f"• <b>{group_name}</b>: {preview}")
    return (
        "🎬 <b>Вот популярные темы</b>\n\n"
        f"{chr(10).join(lines)}\n\n"
        "Напишите тему, которая вам подходит, и я подберу фильмы."
    )


def _group_theme_labels(labels: list[str]) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("Космос", ("космос", "вселен", "астроном", "солн", "звезд", "планет", "галак")),
        ("История", ("истори", "древн", "рим", "средневек", "войн", "цивилиза")),
        ("Природа", ("природ", "живот", "океан", "водопад", "эколог", "лес", "мор", "земл")),
        ("Города и путешествия", ("город", "страна", "путешеств", "россия", "москва", "алтай")),
        ("Наука", ("математ", "физик", "биолог", "хим", "наук", "анатом")),
        ("ПДД и безопасность", ("пдд", "дорож", "безопас")),
    ]

    grouped: dict[str, list[str]] = {name: [] for name, _ in groups}
    other: list[str] = []

    for label in labels:
        normalized = label.lower().replace("ё", "е")
        matched = False
        for group_name, keywords in groups:
            if any(keyword in normalized for keyword in keywords):
                grouped[group_name].append(label)
                matched = True
                break
        if not matched:
            other.append(label)

    result = [(name, values[:4]) for name, values in grouped.items() if values]
    if other:
        result.append(("Другое", other[:4]))
    return result[:6]


def _has_meaningful_movie_params(params: dict) -> bool:
    return any(params.get(key) for key in _MOVIE_PARAM_KEYS)


async def _save_ai_pick_snapshot(state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("ai_item_ids"):
        return
    snapshot = {
        "ai_item_ids": data.get("ai_item_ids", []),
        "ai_params": data.get("ai_params", {}),
        "ai_current_item_id": data.get("ai_current_item_id"),
        "ai_current_item_title": data.get("ai_current_item_title"),
        "ai_current_idx": data.get("ai_current_idx", 0),
        "ai_flow_step": data.get("ai_flow_step", "showing_results"),
    }
    await state.update_data(ai_prev_snapshot=snapshot)


async def _restore_ai_pick_snapshot(message: Message, state: FSMContext, session) -> bool:
    data = await state.get_data()
    snapshot = data.get("ai_prev_snapshot")
    if not snapshot:
        return False

    item_ids = snapshot.get("ai_item_ids") or []
    if not item_ids:
        return False

    idx = max(0, min(int(snapshot.get("ai_current_idx", 0) or 0), len(item_ids) - 1))
    item = await get_item_by_id(session, item_ids[idx])
    if not item:
        return False

    params = snapshot.get("ai_params") or {}
    topic = _describe_params(params)
    header = f"Нашёл <b>{len(item_ids)}</b> фильм{'ов' if len(item_ids) >= 5 else 'а' if len(item_ids) >= 2 else ''}"
    if topic:
        header += f" — {topic}"
    header += ".\n\nМожем посмотреть другие темы или уточнить параметры."

    header_message = await message.answer(header, parse_mode="HTML")
    card_message = await _show_item_card_message(message, item, idx, len(item_ids))

    await state.update_data(
        ai_item_ids=item_ids,
        ai_params=params,
        ai_header_msg_id=header_message.message_id,
        ai_header_chat_id=header_message.chat.id,
        ai_card_msg_id=card_message.message_id,
        ai_card_chat_id=card_message.chat.id,
        ai_current_item_id=item.id,
        ai_current_item_title=item.title,
        ai_current_idx=idx,
        ai_flow_step="showing_results",
        ai_prev_snapshot=None,
    )
    await state.set_state(AiPick.waiting)
    return True


async def _send_selection_question(
    message: Message,
    state: FSMContext,
    session,
    *,
    existing_params: dict,
    params: dict,
    data: dict,
) -> None:
    await _delete_ai_pick_prompt(message.bot, state)
    await state.set_state(AiPick.waiting)
    sent = await message.answer(
        _build_selection_question(existing_params, params),
        reply_markup=ai_pick_cancel_keyboard(show_back=True),
        parse_mode="HTML",
    )
    next_step = "waiting_filters" if existing_params else "waiting_theme"
    await state.update_data(
        ai_prompt_msg_id=sent.message_id,
        ai_prompt_chat_id=sent.chat.id,
        ai_params=existing_params or data.get("ai_params", {}),
        ai_flow_step=next_step,
    )
    persisted_state = await load_ai_state(session, message.from_user.id)
    persisted_state.update({
        "params": existing_params or persisted_state.get("params", {}),
        "ai_params": existing_params or persisted_state.get("ai_params", {}),
        "ai_flow_step": next_step,
    })
    await save_ai_state(session, message.from_user.id, "movie_selection", persisted_state)


def _should_ask_for_selection_details(current_state: str | None, existing_params: dict, params: dict) -> bool:
    if _has_meaningful_movie_params(params):
        return False
    if current_state == AiPick.refine.state:
        return True
    if existing_params:
        return False
    return True


def _build_selection_question(existing_params: dict, params: dict) -> str:
    if params.get("needs_clarification"):
        reason = params.get("clarification_reason")
        if isinstance(reason, str) and reason.strip():
            return (
                "🎬 <b>Давайте уточним подбор</b>\n\n"
                f"{reason.strip()}\n\n"
                "Напишите тему, возраст, класс или длительность.\n\n"
                "Например: «история, 7 лет» или «ПДД до 20 минут»."
            )
    if existing_params:
        return _NO_NEW_PARAMS_TEXT
    return _SELECTION_START_QUESTION


def _has_new_constraints(existing_params: dict, new_params: dict) -> bool:
    for key in _MOVIE_PARAM_KEYS:
        if existing_params.get(key) != new_params.get(key):
            return True
    return False


def _should_refine_existing_selection(user_text: str, data: dict) -> bool:
    existing_params = data.get("ai_params") or {}
    if not existing_params or not data.get("ai_item_ids"):
        return False

    lower = user_text.lower()
    new_params = extract_params_regex(user_text, existing_params)
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
