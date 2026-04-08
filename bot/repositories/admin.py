# Запросы к БД для панели администратора.

from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import (
    AnalyticsEvent,
    BotUser,
    Lead,
    LeadStatus,
    LeadType,
    UserQuestion,
)

LEADS_PER_PAGE = 10
QUESTIONS_PER_PAGE = 10


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------

async def get_leads_page(
    session: AsyncSession,
    *,
    only_new: bool = False,
    page: int = 1,
) -> tuple[list[Lead], int]:
    q = select(Lead)
    if only_new:
        q = q.where(Lead.status == LeadStatus.new)
    # Сортировка: new → in_progress → done, внутри статуса новые сверху
    q = q.order_by(
        case(
            (Lead.status == LeadStatus.new, 0),
            (Lead.status == LeadStatus.in_progress, 1),
            else_=2,
        ),
        Lead.created_at.desc(),
    )
    total: int = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * LEADS_PER_PAGE
    leads = list((await session.execute(q.offset(offset).limit(LEADS_PER_PAGE))).scalars())
    return leads, total


async def get_lead_by_id(session: AsyncSession, lead_id: int) -> Lead | None:
    return (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()


async def update_lead_status(
    session: AsyncSession, lead_id: int, status: LeadStatus
) -> Lead | None:
    lead = await get_lead_by_id(session, lead_id)
    if lead is None:
        return None
    lead.status = status
    await session.commit()
    return lead


# ---------------------------------------------------------------------------
# Вопросы
# ---------------------------------------------------------------------------

async def get_questions_page(
    session: AsyncSession,
    *,
    only_unanswered: bool = False,
    page: int = 1,
) -> tuple[list[UserQuestion], int]:
    q = select(UserQuestion)
    if only_unanswered:
        q = q.where(UserQuestion.is_answered.is_(False))
    # Сортировка: неотвеченные сначала, затем по дате убывания
    q = q.order_by(
        case((UserQuestion.is_answered.is_(False), 0), else_=1),
        UserQuestion.created_at.desc(),
    )
    total: int = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * QUESTIONS_PER_PAGE
    questions = list((await session.execute(q.offset(offset).limit(QUESTIONS_PER_PAGE))).scalars())
    return questions, total


async def get_question_by_id(session: AsyncSession, q_id: int) -> UserQuestion | None:
    return (
        await session.execute(select(UserQuestion).where(UserQuestion.id == q_id))
    ).scalar_one_or_none()


async def mark_question_answered(
    session: AsyncSession,
    q_id: int,
    answer_text: str,
    answered_by: int,
) -> UserQuestion | None:
    question = await get_question_by_id(session, q_id)
    if question is None:
        return None
    question.is_answered = True
    question.answer_text = answer_text
    question.answered_by = answered_by
    question.answered_at = datetime.now(timezone.utc)
    await session.commit()
    return question


async def mark_question_answered_no_text(
    session: AsyncSession,
    q_id: int,
    answered_by: int,
) -> UserQuestion | None:
    question = await get_question_by_id(session, q_id)
    if question is None:
        return None
    question.is_answered = True
    question.answered_by = answered_by
    question.answered_at = datetime.now(timezone.utc)
    await session.commit()
    return question


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

async def get_stats(session: AsyncSession, since: datetime | None) -> dict:
    """Метрики за период [since, now]. since=None → всё время."""

    def _apply_since(q, col):
        return q.where(col >= since) if since is not None else q

    # --- Пользователи ---
    total_users: int = (
        await session.execute(select(func.count()).select_from(BotUser))
    ).scalar_one()
    users_period: int = (
        await session.execute(_apply_since(select(func.count()).select_from(BotUser), BotUser.created_at))
    ).scalar_one()

    # --- Заявки ---
    total_leads: int = (
        await session.execute(select(func.count()).select_from(Lead))
    ).scalar_one()
    leads_period: int = (
        await session.execute(_apply_since(select(func.count()).select_from(Lead), Lead.created_at))
    ).scalar_one()

    async def _count_lead_type(lt: LeadType) -> int:
        return (await session.execute(
            select(func.count()).select_from(Lead).where(Lead.lead_type == lt)
        )).scalar_one()

    # --- Вопросы ---
    total_questions: int = (
        await session.execute(select(func.count()).select_from(UserQuestion))
    ).scalar_one()
    questions_period: int = (
        await session.execute(
            _apply_since(select(func.count()).select_from(UserQuestion), UserQuestion.created_at)
        )
    ).scalar_one()

    # --- Аналитические события ---
    async def _count_event(event_type: str) -> int:
        q = select(func.count()).select_from(AnalyticsEvent).where(
            AnalyticsEvent.event_type == event_type
        )
        return (await session.execute(_apply_since(q, AnalyticsEvent.created_at))).scalar_one()

    return {
        "total_users": total_users,
        "users_period": users_period,
        "total_leads": total_leads,
        "leads_period": leads_period,
        "leads_booking": await _count_lead_type(LeadType.booking),
        "leads_franchise": await _count_lead_type(LeadType.franchise),
        "leads_contact": await _count_lead_type(LeadType.contact),
        "total_questions": total_questions,
        "questions_period": questions_period,
        "open_catalog": await _count_event("open_catalog"),
        "open_catalog_item": await _count_event("open_catalog_item"),
        "click_site_link": await _count_event("click_site_link"),
        "start_lead_form": await _count_event("start_lead_form"),
        "submit_lead": await _count_event("submit_lead"),
    }
