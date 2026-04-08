"""Генерация ответа: сборка промпта, вызов LLM, форматирование."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.ai_catalog import (
    extract_movie_title_candidate,
    extract_params,
    find_movie_by_title,
    find_relevant_films,
    find_similar_movies,
    format_films_for_prompt,
    format_movie_for_prompt,
)
from bot.services.ai_client import call_llm
from bot.services.ai_context import build_context
from bot.services.ai_memory import (
    append_history,
    get_history,
    load_state,
    merge_params,
    update_state,
)

logger = logging.getLogger(__name__)

# Базовые правила для всех промптов
_BASE_RULES = """Ты — помощник компании Альтаирика в Telegram-боте.

Правила:
- Отвечай только по данным из переданного контекста
- Не выдумывай факты, цены, условия, названия фильмов
- Если данных нет — скажи честно и предложи написать оператору
- Отвечай кратко: 3-6 предложений, без воды
- Тон: дружелюбный, живой, не официальный
- Язык: только русский
- Если вопрос не про Альтаирику — мягко верни к теме компании
- Не называй конкретные цены без данных в контексте

--- ДАННЫЕ АЛЬТАИРИКИ ---
{context}
"""

# Дополнительные инструкции по intent'у
_INTENT_INSTRUCTIONS: dict[str, str] = {
    "movie_selection": (
        "Пользователь хочет подобрать фильм. "
        "Из списка выше выбери 2-3 наиболее подходящих и кратко объясни почему. "
        "Если параметров мало — задай один уточняющий вопрос. "
        "Никогда не придумывай названия фильмов."
    ),
    "movie_details": (
        "Пользователь спрашивает про конкретный фильм. "
        "Если в контексте есть один найденный фильм — ответь только по нему. "
        "Если точный фильм не найден, но есть похожие варианты — не говори, что фильма точно нет, "
        "а предложи похожие названия и попроси уточнить. "
        "Никогда не придумывай описание фильма, которого нет в контексте."
    ),
    "franchise_info": (
        "Пользователь интересуется франшизой. "
        "Отвечай по данным из раздела франшизы. "
        "В конце предложи оставить заявку если вопрос ведёт к покупке."
    ),
    "competitor_compare": (
        "Пользователь хочет сравнить Альтаирику с конкурентами. "
        "Строй ответ на основе таблицы сравнения. "
        "Выдели ключевые преимущества Альтаирики."
    ),
    "lead_booking": (
        "Пользователь хочет записаться или оставить контакт. "
        "Кратко подтверди и скажи что форма для заявки доступна по кнопке ниже."
    ),
    "lead_franchise": (
        "Пользователь хочет обсудить франшизу. "
        "Кратко ответь и скажи что форма заявки доступна по кнопке ниже."
    ),
    "faq_answer": (
        "Ответь на вопрос используя данные FAQ и базу знаний. "
        "Будь конкретен."
    ),
    "company_info": (
        "Расскажи о компании на основе базы знаний."
    ),
}


def _build_system_prompt(context: str, intent: str) -> str:
    base = _BASE_RULES.format(context=context)
    instruction = _INTENT_INSTRUCTIONS.get(intent, "")
    if instruction:
        return base + f"\n\nИнструкция для этого запроса: {instruction}"
    return base


async def generate_answer(
    db: AsyncSession,
    telegram_user_id: int,
    user_text: str,
    intent: str,
) -> str | None:
    """
    Полный pipeline: память → контекст → (каталог если нужно) → LLM → обновление памяти.
    Возвращает текст ответа или None при ошибке.
    """
    # Загрузка состояния сессии
    state = await load_state(db, telegram_user_id)
    history = get_history(state)

    catalog_text = ""
    new_params = {}

    # Для подбора фильмов — ищем в каталоге
    if intent == "movie_selection":
        new_params = extract_params(user_text, state.get("params", {}))
        films = await find_relevant_films(db, new_params)
        catalog_text = format_films_for_prompt(films)
        new_params["last_recommended_ids"] = [f.id for f in films]
    elif intent == "movie_details":
        title_query = extract_movie_title_candidate(user_text) or user_text
        title_query = title_query.strip()
        movie = await find_movie_by_title(db, title_query)

        if movie:
            catalog_text = f"=== Найденный фильм ===\n{format_movie_for_prompt(movie)}"
            new_params = {
                "last_movie_query": title_query,
                "last_movie_match_ids": [movie.id],
            }
        else:
            similar_movies = await find_similar_movies(db, title_query, limit=5)
            new_params = {
                "last_movie_query": title_query,
                "last_movie_match_ids": [item.id for item in similar_movies],
            }
            if similar_movies:
                titles = "\n".join(f"• {item.title}" for item in similar_movies)
                response_text = (
                    f"Точного совпадения по названию «{title_query}» не нашёл.\n\n"
                    f"Возможно, вы имели в виду:\n{titles}\n\n"
                    "Напишите точное название фильма, и я расскажу о нём подробнее."
                )
                updated_state = append_history(
                    {"params": merge_params(state.get("params", {}), new_params), "history": history},
                    user_text=user_text,
                    assistant_text=response_text,
                )
                await update_state(
                    db,
                    telegram_user_id,
                    intent,
                    updated_state,
                )
                return response_text

            response_text = (
                f"Не нашёл фильм с названием «{title_query}» в каталоге.\n\n"
                "Попробуйте написать название точнее или опишите тему, возраст и длительность — "
                "я подберу подходящие варианты."
            )
            updated_state = append_history(
                {"params": merge_params(state.get("params", {}), new_params), "history": history},
                user_text=user_text,
                assistant_text=response_text,
            )
            await update_state(
                db,
                telegram_user_id,
                intent,
                updated_state,
            )
            return response_text

    # Собираем контекст
    context = await build_context(db, intent, catalog_text)

    # Строим системный промпт
    system_prompt = _build_system_prompt(context, intent)

    # Вызов LLM
    answer = await call_llm(system_prompt, user_text, history=history)

    # Сохраняем state если есть что сохранять
    if answer:
        updated_state = dict(state)
        updated_state = append_history(
            updated_state,
            user_text=user_text,
            assistant_text=answer,
        )
        if intent in ("movie_selection", "movie_details") and new_params:
            updated_state["params"] = merge_params(state.get("params", {}), new_params)
        await update_state(db, telegram_user_id, intent, updated_state)
    elif intent in ("movie_selection", "movie_details") and new_params:
        updated_state = dict(state)
        updated_state["params"] = merge_params(state.get("params", {}), new_params)
        await update_state(db, telegram_user_id, intent, updated_state)

    return answer
