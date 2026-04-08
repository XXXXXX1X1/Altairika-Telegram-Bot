import html
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import FranchiseContent, FranchiseSection


@dataclass(slots=True)
class FranchiseFaqItem:
    id: int
    question: str
    answer: str


async def get_franchise_content(
    session: AsyncSession, section: FranchiseSection
) -> FranchiseContent | None:
    result = await session.execute(
        select(FranchiseContent).where(FranchiseContent.section == section)
    )
    return result.scalar_one_or_none()


def parse_franchise_faq(content: str) -> list[FranchiseFaqItem]:
    matches = re.findall(
        r"<b>(\d+)\.\s*(.*?)</b>\s*(.*?)(?=\n\n<b>\d+\.|\Z)",
        content,
        flags=re.S,
    )
    items: list[FranchiseFaqItem] = []
    for raw_id, raw_question, raw_answer in matches:
        question = html.unescape(re.sub(r"<[^>]+>", "", raw_question)).strip()
        answer = html.unescape(re.sub(r"<[^>]+>", "", raw_answer)).strip()
        if question and answer:
            items.append(
                FranchiseFaqItem(
                    id=int(raw_id),
                    question=question,
                    answer=answer,
                )
            )
    return items
