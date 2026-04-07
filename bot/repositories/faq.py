from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import FaqItem, FaqTopic, UserQuestion


async def get_active_topics(session: AsyncSession) -> list[FaqTopic]:
    result = await session.execute(
        select(FaqTopic)
        .where(FaqTopic.is_active.is_(True))
        .order_by(FaqTopic.order, FaqTopic.title)
    )
    return list(result.scalars())


async def get_topic_by_id(session: AsyncSession, topic_id: int) -> FaqTopic | None:
    result = await session.execute(
        select(FaqTopic).where(FaqTopic.id == topic_id)
    )
    return result.scalar_one_or_none()


async def get_items_by_topic(session: AsyncSession, topic_id: int) -> list[FaqItem]:
    result = await session.execute(
        select(FaqItem)
        .where(FaqItem.topic_id == topic_id, FaqItem.is_active.is_(True))
        .order_by(FaqItem.order, FaqItem.question)
    )
    return list(result.scalars())


async def get_item_by_id(session: AsyncSession, item_id: int) -> FaqItem | None:
    result = await session.execute(
        select(FaqItem).where(FaqItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def save_user_question(
    session: AsyncSession, telegram_user_id: int, text: str
) -> UserQuestion:
    question = UserQuestion(telegram_user_id=telegram_user_id, text=text)
    session.add(question)
    await session.commit()
    return question
