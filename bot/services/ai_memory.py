"""Работа с session state диалога пользователя."""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.repositories.ai_sessions import get_session, save_session, clear_session

logger = logging.getLogger(__name__)


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
