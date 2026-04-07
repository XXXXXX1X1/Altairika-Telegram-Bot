from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import Lead, LeadStatus, LeadType


async def create_lead(
    session: AsyncSession,
    telegram_user_id: int,
    name: str,
    phone: str,
    lead_type: LeadType,
    catalog_item_id: int | None = None,
    preferred_time: str | None = None,
    city: str | None = None,
) -> Lead:
    lead = Lead(
        telegram_user_id=telegram_user_id,
        name=name,
        phone=phone,
        lead_type=lead_type,
        catalog_item_id=catalog_item_id,
        preferred_time=preferred_time,
        city=city,
        status=LeadStatus.new,
    )
    session.add(lead)
    await session.commit()
    return lead
