"""Работа с session state диалога пользователя."""
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.repositories.ai_sessions import get_session, save_session, clear_session

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 8


async def load_state(db: AsyncSession, telegram_user_id: int) -> dict:
    """Загружает состояние диалога. Возвращает пустой dict если сессии нет."""
    session = await get_session(db, telegram_user_id)
    if session is None:
        return {}
    try:
        return json.loads(session.state_json or "{}")
    except json.JSONDecodeError:
        logger.warning("Невалидный state_json для user %d", telegram_user_id)
        return {}


async def update_state(
    db: AsyncSession,
    telegram_user_id: int,
    intent: str,
    state: dict,
) -> None:
    """Сохраняет состояние диалога."""
    await save_session(db, telegram_user_id, intent, state)


async def reset_state(db: AsyncSession, telegram_user_id: int) -> None:
    """Сбрасывает сессию (например, после перехода в форму)."""
    await clear_session(db, telegram_user_id)


def merge_params(existing: dict, new_params: dict) -> dict:
    """Объединяет старые параметры с новыми (новые перезаписывают старые)."""
    result = {**existing}
    for key, value in new_params.items():
        if value is not None:
            result[key] = value
    return result


def get_history(state: dict[str, Any]) -> list[dict[str, str]]:
    """Возвращает валидную историю диалога из state."""
    history = state.get("history", [])
    if not isinstance(history, list):
        return []

    valid_messages: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        valid_messages.append({"role": role, "content": content.strip()})
    return valid_messages[-_MAX_HISTORY_MESSAGES:]


def append_history(
    state: dict[str, Any],
    *,
    user_text: str,
    assistant_text: str,
) -> dict[str, Any]:
    """Добавляет новый обмен репликами в историю и обрезает хвост."""
    updated_state = dict(state)
    history = get_history(updated_state)
    history.extend([
        {"role": "user", "content": user_text.strip()},
        {"role": "assistant", "content": assistant_text.strip()},
    ])
    updated_state["history"] = history[-_MAX_HISTORY_MESSAGES:]
    return updated_state
