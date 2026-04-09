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
from bot.services.ai_pick_service import (
    LEAD_INTENTS,
    NO_NEW_PARAMS_TEXT,
    build_selection_question,
    describe_params,
    group_theme_labels,
    has_meaningful_movie_params,
    has_new_constraints,
    looks_like_refine_request,
    resolve_movie_action,
    should_ask_for_selection_details,
    should_refine_existing_selection,
)
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
        ai_back_enabled=False,
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
        ai_back_enabled=True,
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
        ai_back_enabled=True,
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
    action = resolve_movie_action(decision, user_text, current_state, data)

    inferred_params = extract_params_regex(user_text, {})
    if (
        current_state in {AiPick.waiting.state, AiPick.refine.state}
        and detected_intent in {"general_chat", "movie_details"}
        and not decision.get("open_current_movie_card")
        and has_meaningful_movie_params(inferred_params)
    ):
        detected_intent = "movie_selection"
        action = "run_search"

    if detected_intent != "movie_selection":
        await _clear_ai_pick_messages(message.bot, state)
        await state.clear()

        if decision.get("open_current_movie_card") and data.get("ai_current_item_id"):
            await send_movie_card_message(message, session, data["ai_current_item_id"])
            return

        if detected_intent in LEAD_INTENTS:
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
    elif should_refine_existing_selection(user_text, data):
        existing_params = data.get("ai_params", {})

    if current_state == AiPick.waiting.state and action == "ask_clarification" and looks_like_refine_request(user_text):
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
            ai_back_enabled=True,
        )
        return

    if action == "show_themes":
        await _send_theme_list(message, state, session)
        return

    # Извлекаем параметры из запроса пользователя
    params = await extract_movie_params(user_text, existing_params)

    if action == "ask_clarification" or should_ask_for_selection_details(current_state, existing_params, params):
        await _send_selection_question(
            message,
            state,
            session,
            existing_params=existing_params,
            params=params,
            data=data,
        )
        return

    if current_state == AiPick.refine.state and not has_new_constraints(existing_params, params):
        show_back = bool(data.get("ai_back_enabled"))
        await _delete_ai_pick_prompt(message.bot, state)
        sent = await message.answer(
            NO_NEW_PARAMS_TEXT,
            reply_markup=ai_pick_cancel_keyboard(show_back=show_back),
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
            "По такой теме пока не нашёл подходящих фильмов.\n\n"
            "Покажу популярные направления, чтобы можно было выбрать ближе к тому, что вам нужно:",
            reply_markup=ai_pick_cancel_keyboard(show_back=bool(data.get("ai_back_enabled"))),
        )
        await state.update_data(
            ai_prompt_msg_id=sent.message_id,
            ai_prompt_chat_id=sent.chat.id,
            ai_back_enabled=bool(data.get("ai_back_enabled")),
        )
        await _send_theme_list(message, state, session)
        return

    await _clear_ai_pick_messages(message.bot, state)

    # Сохраняем результаты в state
    item_ids = [f.id for f in films]
    await state.update_data(ai_item_ids=item_ids, ai_params=params, ai_back_enabled=False)

    # Формируем заголовок подборки
    topic = describe_params(params)
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
        ai_back_enabled=False,
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


async def show_movie_candidates(
    message: Message,
    state: FSMContext,
    session,
    films: list,
    *,
    header_text: str,
    params: dict | None = None,
) -> None:
    """Показывает список фильмов как карточную подборку с листанием."""
    if not films:
        return

    await _clear_ai_pick_messages(message.bot, state)

    item_ids = [f.id for f in films]
    params = params or {}
    await state.update_data(ai_item_ids=item_ids, ai_params=params, ai_back_enabled=False)

    header_message = await message.answer(header_text, parse_mode="HTML")
    await state.update_data(ai_header_msg_id=header_message.message_id, ai_header_chat_id=header_message.chat.id)

    first = films[0]
    card_message = await _show_item_card_message(message, first, 0, len(films))
    await state.update_data(
        ai_card_msg_id=card_message.message_id,
        ai_card_chat_id=card_message.chat.id,
        ai_current_item_id=first.id,
        ai_current_item_title=first.title,
        ai_current_idx=0,
        ai_flow_step="showing_results",
        ai_back_enabled=False,
    )

    persisted_state = await load_ai_state(session, message.from_user.id)
    persisted_state.update({
        "params": params,
        "ai_params": params,
        "last_recommended_ids": item_ids,
        "last_movie_match_ids": item_ids,
        "ai_current_item_id": first.id,
        "ai_current_item_title": first.title,
        "ai_current_idx": 0,
        "ai_flow_step": "showing_results",
    })
    await save_ai_state(session, message.from_user.id, "movie_selection", persisted_state)
    await state.set_state(AiPick.waiting)


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


async def _send_theme_list(message: Message, state: FSMContext, session) -> None:
    themes_text = await _build_theme_list_text(session)
    data = await state.get_data()
    sent = await message.answer(
        themes_text,
        reply_markup=ai_pick_cancel_keyboard(show_back=bool(data.get("ai_back_enabled"))),
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

    grouped = group_theme_labels([label for _, label in theme_filters])
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
    topic = describe_params(params)
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
        ai_back_enabled=False,
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
    show_back = bool(data.get("ai_back_enabled"))
    sent = await message.answer(
        build_selection_question(existing_params, params),
        reply_markup=ai_pick_cancel_keyboard(show_back=show_back),
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
