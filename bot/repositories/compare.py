from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models.db import ComparisonParameter, Competitor


async def get_active_competitors(session: AsyncSession) -> list[Competitor]:
    result = await session.execute(
        select(Competitor)
        .where(Competitor.is_active.is_(True))
        .order_by(Competitor.id)
    )
    return list(result.scalars())


async def get_parameters_with_values(
    session: AsyncSession,
) -> list[ComparisonParameter]:
    result = await session.execute(
        select(ComparisonParameter)
        .options(selectinload(ComparisonParameter.values))
        .order_by(ComparisonParameter.order, ComparisonParameter.name)
    )
    return list(result.scalars())
