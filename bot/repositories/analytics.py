# Логирование аналитических событий.
# Ошибки записи не прерывают основной флоу.

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import AnalyticsEvent


async def log_event(
    session: AsyncSession,
    telegram_user_id: int | None,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload_json: str | None = None,
) -> None:
    try:
        session.add(AnalyticsEvent(
            telegram_user_id=telegram_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
        ))
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
