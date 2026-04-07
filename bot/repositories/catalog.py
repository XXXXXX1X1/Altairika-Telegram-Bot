import json
import re
from hashlib import md5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.catalog import ITEMS_PER_PAGE
from bot.models.db import CatalogItem, Category


_THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Космос",
        (
            "космос", "планет", "галактик", "звезд", "звёзд", "астро", "марс",
            "луна", "солнечн", "вселен", "космонав", "ракет", "спутник",
        ),
    ),
    (
        "Страны и города",
        (
            "страны", "страна", "город", "города", "путешеств", "столица",
            "бангкок", "париж", "лондон", "рим", "росси", "итал", "франц",
            "япони", "кита", "таиланд", "тайланд", "егип", "инд", "африк",
            "европ", "ази", "америк",
        ),
    ),
    (
        "Природа и география",
        (
            "океан", "море", "река", "озер", "пустын", "лес", "джунгл",
            "гор", "вулкан", "водопад", "материк", "остров", "климат",
            "природ", "географ", "экосистем",
        ),
    ),
    (
        "Животные",
        (
            "животн", "динозав", "акул", "кит", "дельфин", "тигр", "лев",
            "слон", "птиц", "рыб", "насеком", "медвед", "кошк", "собак",
            "зоопарк", "обитател",
        ),
    ),
    (
        "История и цивилизации",
        (
            "истор", "древн", "цивилиза", "импер", "рыцар", "замок", "фараон",
            "египет", "рим", "греци", "средневек", "войн", "археолог",
        ),
    ),
    (
        "Человек и тело",
        (
            "человек", "тело", "орган", "сердц", "мозг", "скелет", "мышц",
            "здоров", "медицин", "анатом", "иммун",
        ),
    ),
    (
        "Технологии и изобретения",
        (
            "робот", "технолог", "изобрет", "машин", "электр", "энерги",
            "компьют", "интернет", "программ", "инженер", "механ", "завод",
        ),
    ),
    (
        "Профессии и общество",
        (
            "профес", "работ", "пожарн", "врач", "учител", "строител",
            "космонавт", "полиц", "спасател", "фермер", "повар",
        ),
    ),
    (
        "Искусство и культура",
        (
            "искусств", "культур", "театр", "музык", "живопис", "худож",
            "балет", "кино", "литератур", "музей", "архитект",
        ),
    ),
]


def _duration_code(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower()
    if "до 5" in normalized:
        return "d5"
    if "5" in normalized and "15" in normalized:
        return "d15"
    if "15" in normalized and "30" in normalized:
        return "d30"
    if "30" in normalized:
        return "d30p"
    return ""


def _item_tags(item: CatalogItem) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    try:
        values = json.loads(item.tags) if item.tags else []
    except json.JSONDecodeError:
        values = []

    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        tags.append(text)

    haystack = " ".join(
        part for part in [item.title or "", item.description or ""] if part
    ).lower()
    haystack = re.sub(r"[^a-zа-я0-9+\s-]+", " ", haystack)

    for theme, keywords in _THEME_RULES:
        if any(keyword in haystack for keyword in keywords):
            if theme not in seen:
                seen.add(theme)
                tags.append(theme)

    return tags


def theme_key(value: str) -> str:
    return md5(value.encode("utf-8")).hexdigest()[:8]


async def get_active_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(
        select(Category)
        .where(Category.item_count > 0)
        .order_by(Category.order, Category.name)
    )
    return list(result.scalars())


async def get_filtered_active_items(
    session: AsyncSession,
    category_id: int = 0,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    themes: list[str] | None = None,
) -> list[CatalogItem]:
    q = (
        select(CatalogItem)
        .where(CatalogItem.is_active.is_(True))
        .order_by(CatalogItem.id)
    )
    if category_id:
        q = q.where(CatalogItem.category_id == category_id)

    result = await session.execute(q)
    items = list(result.scalars())

    if ages:
        items = [item for item in items if (item.age_rating or "") in set(ages)]
    if durations:
        items = [item for item in items if _duration_code(item.duration) in set(durations)]
    if themes:
        items = [
            item for item in items
            if set(themes) & {theme_key(tag) for tag in _item_tags(item)}
        ]

    return items


async def count_active_items(
    session: AsyncSession,
    category_id: int = 0,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    themes: list[str] | None = None,
) -> int:
    items = await get_filtered_active_items(
        session,
        category_id,
        ages=ages,
        durations=durations,
        themes=themes,
    )
    return len(items)


async def get_items_page(
    session: AsyncSession,
    category_id: int = 0,
    page: int = 1,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    themes: list[str] | None = None,
) -> list[CatalogItem]:
    items = await get_filtered_active_items(
        session,
        category_id,
        ages=ages,
        durations=durations,
        themes=themes,
    )
    offset = (page - 1) * ITEMS_PER_PAGE
    return items[offset: offset + ITEMS_PER_PAGE]


async def get_item_by_id(session: AsyncSession, item_id: int) -> CatalogItem | None:
    result = await session.execute(
        select(CatalogItem).where(CatalogItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def has_similar_items(
    session: AsyncSession, category_id: int | None, exclude_id: int
) -> bool:
    if not category_id:
        return False
    result = await session.execute(
        select(CatalogItem.id)
        .where(
            CatalogItem.is_active.is_(True),
            CatalogItem.category_id == category_id,
            CatalogItem.id != exclude_id,
        )
        .limit(1)
    )
    return result.first() is not None


async def get_available_age_filters(session: AsyncSession, category_id: int = 0) -> list[str]:
    items = await get_filtered_active_items(session, category_id)
    values = sorted({item.age_rating for item in items if item.age_rating}, key=lambda x: (len(x), x))
    return values


async def get_available_duration_filters(session: AsyncSession, category_id: int = 0) -> list[tuple[str, str]]:
    labels = {
        "d5": "До 5 минут",
        "d15": "5–15 минут",
        "d30": "15–30 минут",
        "d30p": "30+ минут",
    }
    items = await get_filtered_active_items(session, category_id)
    present = []
    for code in ("d5", "d15", "d30", "d30p"):
        if any(_duration_code(item.duration) == code for item in items):
            present.append((code, labels[code]))
    return present


async def get_available_theme_filters(session: AsyncSession, category_id: int = 0) -> list[tuple[str, str]]:
    items = await get_filtered_active_items(session, category_id)
    themes: dict[str, str] = {}
    for item in items:
        for tag in _item_tags(item):
            themes[theme_key(tag)] = tag
    return sorted(themes.items(), key=lambda pair: pair[1].lower())
