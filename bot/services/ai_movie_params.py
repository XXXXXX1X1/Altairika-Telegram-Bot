"""AI-парсер параметров подбора фильма с fallback на regex."""
from typing import Any

from bot.services.ai_client import call_llm_json
from bot.services.ai_catalog import extract_params as extract_params_regex, normalize_theme_key
from bot.services.ai_memory import get_history

_PARAMS_PROMPT = """Ты анализируешь запрос пользователя для подбора фильма в Telegram-боте Альтаирика.

Нужно вернуть ТОЛЬКО JSON:
{
  "theme": null,
  "grade": null,
  "age": null,
  "audience": null,
  "duration": null,
  "needs_clarification": false,
  "clarification_reason": ""
}

Правила:
- theme: короткая тема запроса пользователя, если она явно понятна.
- grade: номер класса, если указан.
- age: возраст в годах, если указан.
- audience: только one of preschool | primary | secondary | null.
- duration: только one of d5 | d15 | d30 | d30p | null.
- Если пользователь просто уточняет предыдущий подбор, используй контекст прошлых сообщений.
- Если тема выражена свободно, всё равно постарайся выделить короткую осмысленную тему.
- clarification_reason должен быть коротким и пользовательским.
- Не пиши служебные формулировки вроде «пользователь хочет», «пользователь уточняет», «нужен дополнительный запрос».
- Пиши так, как бот сказал бы человеку напрямую.
- Не добавляй лишних полей.
"""


def _sanitize_clarification_reason(value: str) -> str:
    cleaned = " ".join(value.split())
    replacements = (
        ("Пользователь хочет ", ""),
        ("Пользователь хочет", ""),
        ("Пользователь уточняет ", ""),
        ("Пользователь уточняет", ""),
        ("нужен дополнительный запрос для определения темы", "нужно чуть больше деталей"),
        ("нужен дополнительный запрос", "нужно чуть больше деталей"),
    )
    for source, target in replacements:
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.strip(" .,-:")
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def _normalize_duration(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"d5", "d15", "d30", "d30p"}:
            return value
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            minutes = int(digits)
            if minutes <= 5:
                return "d5"
            if minutes <= 15:
                return "d15"
            if minutes <= 30:
                return "d30"
            return "d30p"
    if isinstance(value, (int, float)):
        minutes = int(value)
        if minutes <= 5:
            return "d5"
        if minutes <= 15:
            return "d15"
        if minutes <= 30:
            return "d30"
        return "d30p"
    return None


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    theme = payload.get("theme")
    if isinstance(theme, str) and theme.strip():
        normalized_theme = normalize_theme_key(theme.strip().lower())
        if normalized_theme:
            result["theme"] = normalized_theme

    grade = payload.get("grade")
    if isinstance(grade, (int, float)):
        result["grade"] = int(grade)
    elif isinstance(grade, str) and grade.strip().isdigit():
        result["grade"] = int(grade.strip())

    age = payload.get("age")
    if isinstance(age, (int, float)):
        result["age"] = int(age)
    elif isinstance(age, str) and age.strip().isdigit():
        result["age"] = int(age.strip())

    audience = payload.get("audience")
    if audience in {"preschool", "primary", "secondary"}:
        result["audience"] = audience

    duration = _normalize_duration(payload.get("duration"))
    if duration:
        result["duration"] = duration

    result["needs_clarification"] = bool(payload.get("needs_clarification"))
    clarification_reason = payload.get("clarification_reason")
    if isinstance(clarification_reason, str) and clarification_reason.strip():
        result["clarification_reason"] = _sanitize_clarification_reason(clarification_reason.strip())

    return result


async def extract_movie_params(
    user_text: str,
    existing_state: dict[str, Any],
) -> dict[str, Any]:
    """Извлекает параметры фильма через AI с fallback на regex."""
    history = get_history(existing_state)
    payload = await call_llm_json(
        _PARAMS_PROMPT + f"\n\nТекущее состояние: {existing_state.get('ai_params') or existing_state.get('params') or {}}",
        user_text,
        history=history[-4:],
        max_tokens=180,
    )

    regex_params = extract_params_regex(user_text, existing_state)
    if not payload:
        return regex_params

    parsed = _sanitize_payload(payload)
    result = dict(existing_state)
    for key in ("theme", "grade", "age", "audience", "duration"):
        if key in parsed and parsed[key] is not None:
            result[key] = parsed[key]

    if "raw_query" in regex_params:
        result["raw_query"] = regex_params["raw_query"]

    for key in ("theme", "grade", "age", "audience", "duration"):
        if key not in result and key in regex_params:
            result[key] = regex_params[key]

    if parsed.get("needs_clarification"):
        result["needs_clarification"] = True
        result["clarification_reason"] = parsed.get("clarification_reason", "")
    else:
        result.pop("needs_clarification", None)
        result.pop("clarification_reason", None)

    return result
