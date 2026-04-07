from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import FranchiseContent, FranchiseSection


async def get_franchise_content(
    session: AsyncSession, section: FranchiseSection
) -> FranchiseContent | None:
    result = await session.execute(
        select(FranchiseContent).where(FranchiseContent.section == section)
    )
    return result.scalar_one_or_none()
