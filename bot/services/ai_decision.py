"""AI-анализатор сценария: определяет, что делать с новым сообщением пользователя."""
from typing import Any

from bot.services.ai_client import call_llm_json
from bot.services.ai_memory import get_history

_ALLOWED_INTENTS = {
    "general_chat",
    "movie_selection",
    "movie_details",
    "company_info",
    "faq_answer",
    "franchise_info",
    "competitor_compare",
    "lead_booking",
    "lead_franchise",
}

_ALLOWED_ACTIONS = {
    "answer",
    "switch_intent",
    "ask_clarification",
    "show_themes",
    "run_search",
    "open_current_movie_card",
}

_DECISION_PROMPT = """Ты — маршрутизатор сценариев Telegram-бота Альтаирика.

Твоя задача: по сообщению пользователя и текущему состоянию решить, какой сценарий нужно запустить СЕЙЧАС.

Допустимые intent:
- general_chat
- movie_selection
- movie_details
- company_info
- faq_answer
- franchise_info
- competitor_compare
- lead_booking
- lead_franchise

Верни ТОЛЬКО JSON такого вида:
{
  "intent": "movie_selection",
  "action": "ask_clarification",
  "use_current_movie": false,
  "open_current_movie_card": false,
  "continue_current_flow": true,
  "confidence": 0.0,
  "reason": "short text"
}

Правила:
- action описывает следующий шаг системы, а не просто тему сообщения.
- Если пользователь хочет подобрать фильм по теме/возрасту/длительности, это movie_selection.
- Если пользователь только начинает подбор, но ещё не дал тему или параметры, используй intent=movie_selection и action=ask_clarification.
- Если пользователь спрашивает, какие есть темы или направления для подбора, используй intent=movie_selection и action=show_themes.
- Если пользователь уже дал достаточно данных для подбора, используй intent=movie_selection и action=run_search.
- Если пользователь просто поздоровался, не сформулировал запрос или написал что-то слишком общее, это general_chat.
- Короткие нейтральные реплики вроде "понятно", "ясно", "хорошо", "спасибо", "понял" тоже относятся к general_chat, если в них нет нового вопроса или явного продолжения текущей темы.
- Если пользователь спрашивает о конкретном фильме или просит подробнее о текущем фильме, это movie_details.
- Если пользователь просит открыть карточку текущего фильма, то open_current_movie_card=true, action=open_current_movie_card и intent=movie_details.
- Если пользователь переключился на компанию, FAQ, франшизу, сравнение или заявку, НЕ продолжай старый сценарий.
- Если в активной ветке был фильм и пользователь пишет "расскажи подробнее", "про этот фильм", "открой карточку", используй текущий фильм.
- Если активная ветка franchise_info и ассистент только что предложил рассказать подробнее, ответы вроде "да", "да расскажи", "интересно", "хочу подробнее" оставляй в franchise_info с action=answer.
- Если активная ветка competitor_compare и пользователь уточняет аспект сравнения короткой фразой вроде "цена", "контент", "про количество франшиз", "по партнёрам", "по странам", оставляй intent=competitor_compare.
- Запросы вроде "расскажи про конкурентов", "проведи анализ конкурентов", "рынок и конкуренты", "сделай конкурентный анализ" относятся к competitor_compare.
- Вопросы о стоимости франшизы, вложениях, паушальном взносе, роялти, окупаемости и условиях — это franchise_info, а не lead_franchise.
- В lead_franchise переходи только при явном намерении оставить заявку, связаться, обсудить покупку, созвониться или получить контакт.
- Для intent, который не movie_selection, обычно используй action=answer или action=switch_intent.
- Не выдумывай новый intent вне списка.
- Не выдумывай action вне списка.
"""


def _build_state_snapshot(state: dict[str, Any]) -> str:
    history = get_history(state)
    history_lines = [
        f"{item['role']}: {item['content']}"
        for item in history[-6:]
    ]
    parts = [
        f"active_intent={state.get('_active_intent') or state.get('active_intent') or ''}",
        f"ai_flow_step={state.get('ai_flow_step') or ''}",
        f"ai_params={state.get('ai_params') or state.get('params') or {}}",
        f"ai_current_item_title={state.get('ai_current_item_title') or ''}",
        f"ai_current_item_id={state.get('ai_current_item_id') or ''}",
    ]
    if history_lines:
        parts.append("history:\n" + "\n".join(history_lines))
    return "\n".join(parts)


async def analyze_dialog_scenario(user_text: str, state: dict[str, Any]) -> dict[str, Any] | None:
    """Просит модель определить нужный сценарий и действие."""
    snapshot = _build_state_snapshot(state)
    payload = await call_llm_json(
        _DECISION_PROMPT + "\n\nТекущее состояние:\n" + snapshot,
        user_text,
        max_tokens=220,
    )
    if not payload:
        return None

    intent = payload.get("intent")
    if intent not in _ALLOWED_INTENTS:
        return None

    action = payload.get("action")
    if action not in _ALLOWED_ACTIONS:
        action = "open_current_movie_card" if payload.get("open_current_movie_card") else "answer"

    return {
        "intent": intent,
        "action": action,
        "use_current_movie": bool(payload.get("use_current_movie")),
        "open_current_movie_card": bool(payload.get("open_current_movie_card")),
        "continue_current_flow": bool(payload.get("continue_current_flow", False)),
        "confidence": float(payload.get("confidence", 0.0) or 0.0),
        "reason": str(payload.get("reason", "") or ""),
    }
