from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.models.db import BotUser


async def upsert_user(session: AsyncSession, telegram_user_id: int, username: str | None,
                      first_name: str, language_code: str | None) -> BotUser:
    result = await session.execute(
        select(BotUser).where(BotUser.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = BotUser(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.language_code = language_code
        # last_seen_at обновляется через onupdate

    await session.commit()
    return user
