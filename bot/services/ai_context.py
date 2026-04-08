"""Сборка контекста из БД и базы знаний для передачи в LLM."""
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import (
    ComparisonParameter, ComparisonValue, Competitor,
    FaqItem, FaqTopic, FranchiseContent, FranchiseSection,
)

logger = logging.getLogger(__name__)

# Путь к базе знаний компании
_KNOWLEDGE_FILE = Path(__file__).parent.parent.parent / "docs" / "work" / "10_company_knowledge.md"

_knowledge_cache: str | None = None


def load_company_knowledge() -> str:
    """Загружает базу знаний из файла (кешируется в памяти)."""
    global _knowledge_cache
    if _knowledge_cache is not None:
        return _knowledge_cache
    try:
        _knowledge_cache = _KNOWLEDGE_FILE.read_text(encoding="utf-8")
        return _knowledge_cache
    except FileNotFoundError:
        logger.error("Файл базы знаний не найден: %s", _KNOWLEDGE_FILE)
        return ""


async def get_faq_context(db: AsyncSession) -> str:
    """Возвращает все FAQ в виде текста."""
    result = await db.execute(
        select(FaqTopic)
        .where(FaqTopic.is_active.is_(True))
        .order_by(FaqTopic.order)
    )
    topics = list(result.scalars())
    if not topics:
        return ""

    lines = ["=== Частые вопросы (FAQ) ==="]
    for topic in topics:
        faq_result = await db.execute(
            select(FaqItem)
            .where(FaqItem.topic_id == topic.id, FaqItem.is_active.is_(True))
            .order_by(FaqItem.order)
        )
        items = list(faq_result.scalars())
        if not items:
            continue
        lines.append(f"\n[{topic.title}]")
        for item in items:
            lines.append(f"В: {item.question}")
            lines.append(f"О: {item.answer}")
    return "\n".join(lines)


async def get_franchise_context(db: AsyncSession) -> str:
    """Возвращает содержимое разделов франшизы."""
    result = await db.execute(select(FranchiseContent))
    rows = list(result.scalars())
    if not rows:
        return ""

    import html
    import re

    def strip_html(text: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()

    section_labels = {
        FranchiseSection.pitch: "Краткое описание франшизы",
        FranchiseSection.conditions: "Условия и инвестиции",
        FranchiseSection.support: "Поддержка партнёра",
        FranchiseSection.faq: "FAQ по франшизе",
    }

    lines = ["=== Информация о франшизе ==="]
    for row in rows:
        label = section_labels.get(row.section, row.section.value)
        lines.append(f"\n[{label}]")
        lines.append(strip_html(row.content))
    return "\n".join(lines)


async def get_compare_context(db: AsyncSession) -> str:
    """Возвращает таблицу сравнения с конкурентами."""
    params_result = await db.execute(
        select(ComparisonParameter).order_by(ComparisonParameter.order)
    )
    params = list(params_result.scalars())
    if not params:
        return ""

    competitors_result = await db.execute(
        select(Competitor).where(Competitor.is_active.is_(True))
    )
    competitors = list(competitors_result.scalars())

    lines = ["=== Сравнение с конкурентами ==="]
    for param in params:
        altairika_value = param.altairika_value
        # Нормализуем устаревшее seeded-значение, чтобы бот не отвечал "68+ фильмов".
        if param.name == "Размер каталога" and altairika_value.strip() == "68+ фильмов":
            altairika_value = "135 на главной странице, 150+ в разделе франшизы"
        lines.append(f"\n{param.name}:")
        lines.append(f"  Альтаирика: {altairika_value}")
        values_result = await db.execute(
            select(ComparisonValue)
            .where(ComparisonValue.parameter_id == param.id)
        )
        values = list(values_result.scalars())
        for val in values:
            comp = next((c for c in competitors if c.id == val.competitor_id), None)
            if comp:
                lines.append(f"  {comp.name}: {val.value}")

    return "\n".join(lines)


async def build_context(
    db: AsyncSession,
    intent: str,
    extra_catalog_text: str = "",
) -> str:
    """Собирает контекст для конкретного intent'а."""
    parts: list[str] = []

    # Базовые знания о компании — всегда
    knowledge = load_company_knowledge()
    if knowledge:
        parts.append(knowledge)

    # FAQ — для всех кроме movie_selection и competitor_compare
    if intent not in ("movie_selection", "competitor_compare"):
        faq = await get_faq_context(db)
        if faq:
            parts.append(faq)

    # Франшиза — только для franchise_info и lead_franchise
    if intent in ("franchise_info", "lead_franchise"):
        franchise = await get_franchise_context(db)
        if franchise:
            parts.append(franchise)

    # Конкуренты — только для competitor_compare
    if intent == "competitor_compare":
        compare = await get_compare_context(db)
        if compare:
            parts.append(compare)

    # Каталог фильмов — для подбора и вопросов о конкретном фильме
    if intent in ("movie_selection", "movie_details") and extra_catalog_text:
        if intent == "movie_selection" and not extra_catalog_text.startswith("==="):
            parts.append(f"=== Подобранные фильмы ===\n{extra_catalog_text}")
        else:
            parts.append(extra_catalog_text)

    return "\n\n".join(parts)
