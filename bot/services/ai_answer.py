"""Генерация ответа: сборка промпта, вызов LLM, форматирование."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.ai_catalog import (
    extract_movie_title_candidate,
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
from bot.services.ai_movie_params import extract_movie_params

logger = logging.getLogger(__name__)

_EXPLICIT_MOVIE_REQUEST_HINTS = (
    "расскажи про фильм", "расскажи о фильме", "что за фильм", "описание фильма",
    "информация о фильме", "о фильме", "про фильм", "фильм ",
    "по конкретному фильму", "о конкретном фильме", "конкретный фильм",
)
_GENERIC_MOVIE_REQUEST_VALUES = {
    "фильм", "о фильме", "про фильм", "конкретный фильм", "конкретному фильму",
    "по конкретному фильму", "о конкретном фильме",
}

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
- Строго запрещено упоминать сайт как источник в обычном ответе: не пиши «на сайте указано», «на сайте», «на странице», «по данным сайта», даже если эти слова есть в контексте
- Не упоминай источник данных в обычном ответе: не пиши «в базе знаний сказано», «по данным контекста», если пользователь сам не просит источник
- Сообщай факты напрямую и естественно, как ответ ассистента, а не как пересказ документа

--- ДАННЫЕ АЛЬТАИРИКИ ---
{context}
"""

# Дополнительные инструкции по intent'у
_INTENT_INSTRUCTIONS: dict[str, str] = {
    "general_chat": (
        "Пользователь пока не сформулировал точный запрос. "
        "Ответь нейтрально и коротко: поздоровайся, предложи выбрать направление. "
        "Например: подбор фильма, рассказ о компании, франшиза, FAQ. "
        "Не запускай подбор сам и не перечисляй фильмы без запроса."
    ),
    "movie_selection": (
        "Пользователь хочет подобрать фильм. "
        "Из списка выше выбери 2-3 наиболее подходящих и кратко объясни почему. "
        "Если параметров мало — задай один уточняющий вопрос. "
        "Никогда не придумывай названия фильмов."
    ),
    "movie_details": (
        "Пользователь спрашивает про конкретный фильм. "
        "Если в контексте есть один найденный фильм — ответь только по нему. "
        "Ответ должен быть содержательным: коротко объясни, о чём фильм, чем он может быть интересен, "
        "и добавь важные факты вроде возраста, длительности, темы или предметов, если они есть в контексте. "
        "Не ограничивайся простым повторением одной строки описания. "
        "Если точный фильм не найден, но есть похожие варианты — не говори, что фильма точно нет, "
        "а предложи похожие названия и попроси уточнить. "
        "Никогда не придумывай описание фильма, которого нет в контексте."
    ),
    "franchise_info": (
        "Пользователь интересуется франшизой. "
        "Отвечай по данным из раздела франшизы. "
        "Не пиши формулировки вроде «на сайте указано», «на странице франшизы», «на разных страницах сайта». "
        "Если по стоимости или условиям есть несколько значений, сообщай это как факт напрямую: например, что сумма зависит от территории и в данных встречаются разные ориентиры. "
        "В конце предложи оставить заявку если вопрос ведёт к покупке."
    ),
    "competitor_compare": (
        "Пользователь хочет сравнить Альтаирику с конкурентами. "
        "Строй ответ на основе таблицы сравнения. "
        "Выдели ключевые преимущества Альтаирики. "
        "Не перечисляй недостатки Альтаирики и не формулируй ответ как список слабых сторон. "
        "Даже если пользователь прямо спрашивает о минусах, отвечай аккуратно: "
        "не называй это недостатками, а мягко переводи разговор в плоскость различий форматов, особенностей модели и того, кому какой формат подходит лучше. "
        "Сравнение подавай через различия, сильные стороны, позиционирование и особенности подхода. "
        "Если пользователь спрашивает в общем про преимущества, отвечай прежде всего качественно по категориям: опыт, формат, контент, аудитория, мобильность, поддержка. "
        "Не добавляй точные цифры и сроки, если пользователь сам не просил числовое сравнение. "
        "Не делай выводы по цифрам, которых явно нет в таблице сравнения. "
        "Не утверждай, что у конкурентов больше языков, больше контента или другие количественные преимущества, "
        "если в контексте нет прямого подтверждённого сравнения по этой метрике. "
        "Если по языкам нет точных сопоставимых данных у конкурентов, говори нейтрально: у Altairika есть многоязычный контент, "
        "а прямое сравнение по языкам подтверждено не для всех игроков. "
        "Если по одной метрике в данных встречаются разные числа, прямо скажи, что цифры различаются в зависимости от раздела, и не выбирай случайное одно значение. "
        "Не оформляй ответ markdown-списком со звёздочками. Используй короткий абзац или строки без '*'. "
        "Если в контексте есть исследование рынка и конкурентов, используй его и не говори, что информации о конкурентах нет."
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
        "Расскажи о компании на основе базы знаний. "
        "Не ссылайся на сайт, контекст, базу знаний или документы в формулировках ответа, если пользователь сам не просит источник. "
        "Если пользователь спрашивает юридический адрес, телефон, email, реквизиты или другие контакты, "
        "отвечай только если эти данные явно есть в контексте. "
        "Если точных данных нет, честно скажи, что сейчас не видишь подтверждённой информации, "
        "и предложи оставить заявку через бота."
    ),
}


def _build_system_prompt(context: str, intent: str) -> str:
    base = _BASE_RULES.format(context=context)
    instruction = _INTENT_INSTRUCTIONS.get(intent, "")
    if instruction:
        return base + f"\n\nИнструкция для этого запроса: {instruction}"
    return base


def _is_explicit_movie_request(text: str) -> bool:
    lower = (text or "").lower().replace("ё", "е").strip()
    return any(hint in lower for hint in _EXPLICIT_MOVIE_REQUEST_HINTS)


def _needs_movie_title_clarification(user_text: str, title_query: str) -> bool:
    normalized_query = " ".join((title_query or "").lower().replace("ё", "е").split())
    if normalized_query in _GENERIC_MOVIE_REQUEST_VALUES:
        return True
    lower = (user_text or "").lower().replace("ё", "е")
    return any(hint in lower for hint in ("конкретному фильму", "конкретный фильм", "о конкретном фильме"))


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
        new_params = await extract_movie_params(user_text, state.get("params", {}))
        films = await find_relevant_films(db, new_params)
        catalog_text = format_films_for_prompt(films)
        new_params["last_recommended_ids"] = [f.id for f in films]
    elif intent == "movie_details":
        title_query = extract_movie_title_candidate(user_text) or user_text
        title_query = title_query.strip()
        if _needs_movie_title_clarification(user_text, title_query):
            response_text = (
                "Напишите название фильма, и я расскажу о нём подробнее.\n\n"
                "Например: «Бангкок», «Париж» или «Время первых»."
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
        movie = await find_movie_by_title(db, title_query)

        if movie:
            catalog_text = f"=== Найденный фильм ===\n{format_movie_for_prompt(movie)}"
            new_params = {
                "last_movie_query": title_query,
                "last_movie_match_ids": [movie.id],
                "ai_current_item_id": movie.id,
                "ai_current_item_title": movie.title,
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

            if not _is_explicit_movie_request(user_text):
                response_text = (
                    "Не совсем понял запрос.\n\n"
                    "Могу помочь подобрать фильм, рассказать о компании, ответить по франшизе "
                    "или подсказать по конкретному фильму.\n"
                    "Напишите, что вам интересно."
                )
                updated_state = append_history(
                    {"params": merge_params(state.get("params", {}), new_params), "history": history},
                    user_text=user_text,
                    assistant_text=response_text,
                )
                await update_state(
                    db,
                    telegram_user_id,
                    "general_chat",
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
