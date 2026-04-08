import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models.db import AiSession


async def get_session(db: AsyncSession, telegram_user_id: int) -> AiSession | None:
    result = await db.execute(
        select(AiSession).where(AiSession.telegram_user_id == telegram_user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    # Проверяем TTL
    if session.expires_at and session.expires_at < datetime.now(timezone.utc):
        await db.delete(session)
        await db.commit()
        return None
    return session


async def save_session(
    db: AsyncSession,
    telegram_user_id: int,
    intent: str,
    state: dict,
) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.AI_SESSION_TTL_MINUTES
    )
    existing = await db.execute(
        select(AiSession).where(AiSession.telegram_user_id == telegram_user_id)
    )
    session = existing.scalar_one_or_none()
    if session is None:
        session = AiSession(telegram_user_id=telegram_user_id)
        db.add(session)
    session.active_intent = intent
    session.state_json = json.dumps(state, ensure_ascii=False)
    session.expires_at = expires_at
    await db.commit()


async def clear_session(db: AsyncSession, telegram_user_id: int) -> None:
    await db.execute(
        delete(AiSession).where(AiSession.telegram_user_id == telegram_user_id)
    )
    await db.commit()


async def cleanup_expired(db: AsyncSession) -> None:
    await db.execute(
        delete(AiSession).where(
            AiSession.expires_at < datetime.now(timezone.utc)
        )
    )
    await db.commit()
