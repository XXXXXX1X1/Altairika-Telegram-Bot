# Перехват свободного текста вне активных FSM-форм.
# Pipeline: определение intent → сборка контекста → вызов LLM → ответ.
# Для администратора — подсказка /admin.

import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.ai_movie import run_ai_pick_flow, send_movie_card_message, show_movie_candidates
from bot.handlers.catalog import send_catalog_entry_message
from bot.handlers.franchise import send_franchise_main_message
from bot.handlers.start import send_main_menu_message
from bot.config import settings
from bot.keyboards.ai import after_ai_keyboard, ai_fallback_keyboard
from bot.keyboards.faq import freetext_keyboard
from bot.services.ai_answer import generate_answer
from bot.services.ai_branch import decide_next_intent
from bot.services.ai_catalog import extract_movie_title_candidate, find_movie_by_title, find_similar_movies
from bot.services.ai_decision import analyze_dialog_scenario
from bot.services.ai_memory import append_history, get_history, load_state, update_state
from bot.services.ai_rate_limit import check_ai_rate_limit

logger = logging.getLogger(__name__)
router = Router()

_ADMIN_HINT = "Введите /admin для перехода в панель администратора."

_FALLBACK_TEXT = (
    "Не удалось обработать запрос автоматически.\n"
    "Напишите нам напрямую — ответим в рабочее время."
)

_GENERAL_CHAT_FALLBACK = (
    "Здравствуйте! Могу помочь с несколькими направлениями:\n\n"
    "• подобрать фильм\n"
    "• рассказать о компании\n"
    "• ответить по франшизе\n"
    "• подсказать по частым вопросам\n\n"
    "Напишите, что вам интересно."
)

# Интенты, которые переводят пользователя в форму без LLM-ответа
_LEAD_INTENTS = {"lead_booking", "lead_franchise"}
_CATALOG_OPEN_HINTS = (
    "открой каталог", "открыть каталог", "покажи каталог", "показать каталог",
    "в каталог", "откройте каталог",
)
_FRANCHISE_OPEN_HINTS = (
    "открой франшизу", "открыть франшизу", "покажи франшизу", "в франшизу",
)
_MAIN_MENU_HINTS = (
    "главное меню", "в меню", "открой меню", "открыть меню", "в главное меню",
)
_FRANCHISE_INFO_GUARD_HINTS = (
    "сколько стоит франшиза", "стоимость франшизы", "цена франшизы",
    "сколько нужно вложить", "какие вложения", "какие условия франшизы",
    "какие условия", "что входит во франшизу", "паушальный взнос",
    "роялти", "окупаемость",
)
_UI_CATALOG_INVITE_HINTS = (
    "открыть каталог", "открой каталог", "показать каталог", "покажи каталог",
    "скинуть каталог", "перейти в каталог",
)
_UI_FRANCHISE_INVITE_HINTS = (
    "открыть раздел франшизы", "открой франшизу", "показать франшизу",
    "перейти в раздел франшизы", "открыть франшизу",
)


@router.message(StateFilter(default_state))
async def freetext_handler(message: Message, session: AsyncSession, state: FSMContext) -> None:
    # Если AI не настроен — возвращаем старую заглушку
    if not settings.OPENROUTER_API_KEY:
        await message.answer(
            "Я работаю через кнопки.\n\n"
            "Возможно, ответ есть в разделе «Частые вопросы», "
            "или оставьте вопрос — менеджер ответит в рабочее время.",
            reply_markup=freetext_keyboard(),
        )
        return

    user_text = message.text or ""

    # Rate limiting: не более 50 AI-запросов за 5 минут с одного пользователя
    if not check_ai_rate_limit(message.from_user.id):
        await message.answer(
            "Слишком много запросов. Пожалуйста, подождите несколько минут и попробуйте снова.",
            reply_markup=ai_fallback_keyboard(),
        )
        return

    ai_state = await load_state(session, message.from_user.id)
    ui_action = _detect_ui_action(user_text, ai_state)
    if ui_action == "catalog":
        await send_catalog_entry_message(message, session, state)
        return
    if ui_action == "franchise":
        await send_franchise_main_message(message, session)
        return
    if ui_action == "main_menu":
        await send_main_menu_message(message, session, state)
        return

    decision = await analyze_dialog_scenario(user_text, ai_state)
    if not decision or decision.get("confidence", 0.0) < 0.45:
        decision = decide_next_intent(user_text, ai_state)
    intent = str(decision["intent"])
    action = str(decision.get("action") or "")
    lower_user_text = user_text.lower().strip()
    if intent == "lead_franchise" and any(hint in lower_user_text for hint in _FRANCHISE_INFO_GUARD_HINTS):
        intent = "franchise_info"
        action = "answer"
    logger.info("user=%d intent=%s action=%s text=%r", message.from_user.id, intent, action, user_text[:80])

    # Для явных заявок — не тратим токены, сразу предлагаем форму
    if intent in _LEAD_INTENTS:
        if intent == "lead_booking":
            reply = "Отлично! Нажмите кнопку ниже чтобы оставить заявку на сеанс:"
        else:
            reply = "Хорошо! Нажмите кнопку ниже чтобы оставить заявку на франшизу:"
        await message.answer(reply, reply_markup=after_ai_keyboard(intent))
        return

    if intent == "movie_selection":
        await run_ai_pick_flow(message, state, session)
        return

    if decision.get("open_current_movie_card") and ai_state.get("ai_current_item_id"):
        await send_movie_card_message(message, session, ai_state["ai_current_item_id"])
        return

    if intent == "movie_details":
        title_query = (extract_movie_title_candidate(user_text) or user_text).strip()
        movie = await find_movie_by_title(session, title_query)
        if movie:
            updated_state = dict(ai_state)
            updated_state.update({
                "ai_current_item_id": movie.id,
                "ai_current_item_title": movie.title,
                "last_movie_query": title_query,
                "last_movie_match_ids": [movie.id],
            })
            updated_state = append_history(
                updated_state,
                user_text=user_text,
                assistant_text=f"Открываю карточку фильма «{movie.title}».",
            )
            await update_state(session, message.from_user.id, "movie_details", updated_state)
            await send_movie_card_message(message, session, movie.id)
            return
        similar_movies = await find_similar_movies(session, title_query, limit=5)
        if similar_movies:
            header = (
                f"Точного совпадения по названию «{title_query}» не нашёл.\n\n"
                "Возможно, вы имели в виду один из этих фильмов:"
            )
            await show_movie_candidates(
                message,
                state,
                session,
                similar_movies,
                header_text=header,
                params={"last_movie_query": title_query},
            )
            return

    ai_query = user_text
    if decision.get("use_current_movie") and ai_state.get("ai_current_item_title"):
        ai_query = f"Расскажи подробнее о фильме {ai_state['ai_current_item_title']}"

    # Показываем индикатор загрузки
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Генерируем ответ через LLM
    try:
        answer = await generate_answer(
            db=session,
            telegram_user_id=message.from_user.id,
            user_text=ai_query,
            intent=intent,
        )
    except Exception as e:
        logger.exception("Ошибка generate_answer для user=%d: %s", message.from_user.id, e)
        answer = None

    if answer:
        await message.answer(answer, reply_markup=after_ai_keyboard(intent))
    elif intent == "general_chat":
        await message.answer(_GENERAL_CHAT_FALLBACK, reply_markup=after_ai_keyboard(intent))
    else:
        logger.warning("AI вернул None для user=%d intent=%s", message.from_user.id, intent)
        await message.answer(_FALLBACK_TEXT, reply_markup=ai_fallback_keyboard())


def _detect_ui_action(user_text: str, ai_state: dict) -> str | None:
    lower = (user_text or "").lower().strip()
    if not lower:
        return None
    if any(hint in lower for hint in _MAIN_MENU_HINTS):
        return "main_menu"
    if any(hint in lower for hint in _CATALOG_OPEN_HINTS):
        return "catalog"
    if any(hint in lower for hint in _FRANCHISE_OPEN_HINTS):
        return "franchise"

    if lower in {"да", "давай", "покажи", "открой"}:
        history = get_history(ai_state)
        assistant_messages = [item["content"].lower() for item in history if item["role"] == "assistant"]
        if not assistant_messages:
            return None
        last_assistant = assistant_messages[-1]
        if any(hint in last_assistant for hint in _UI_CATALOG_INVITE_HINTS):
            return "catalog"
        if any(hint in last_assistant for hint in _UI_FRANCHISE_INVITE_HINTS):
            return "franchise"

    return None
