import json
from hashlib import md5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.catalog import ITEMS_PER_PAGE
from bot.models.db import CatalogItem, Category


def _duration_code(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower()
    digits = [int(part) for part in "".join(ch if ch.isdigit() else " " for ch in normalized).split()]
    minutes = digits[0] if digits else 0
    if not minutes:
        return ""
    if minutes <= 5:
        return "d5"
    if minutes <= 15:
        return "d15"
    if minutes <= 30:
        return "d30"
    return "d30p"


def _load_tags_payload(item: CatalogItem) -> dict[str, list[str]]:
    if not item.tags:
        return {}

    try:
        payload = json.loads(item.tags)
    except json.JSONDecodeError:
        return {}

    if isinstance(payload, list):
        return {"themes": [str(value) for value in payload if str(value).strip()]}

    if not isinstance(payload, dict):
        return {}

    result: dict[str, list[str]] = {}
    for key, values in payload.items():
        if not isinstance(values, list):
            continue
        result[key] = [str(value).strip() for value in values if str(value).strip()]
    return result


def item_metadata(item: CatalogItem) -> dict[str, list[str]]:
    payload = _load_tags_payload(item)
    return {
        "genres": payload.get("genres", []),
        "themes": payload.get("themes", []),
        "languages": payload.get("languages", []),
        "formats": payload.get("formats", []),
    }


def theme_key(value: str) -> str:
    return md5(value.strip().lower().encode("utf-8")).hexdigest()[:8]


def primary_theme_key(item: CatalogItem) -> str | None:
    themes = item_metadata(item)["themes"]
    if not themes:
        return None
    return theme_key(themes[0])


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
    genres: list[str] | None = None,
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
    if genres:
        items = [
            item for item in items
            if set(genres) & {theme_key(value) for value in item_metadata(item)["genres"]}
        ]

    return items


async def get_active_items(session: AsyncSession) -> list[CatalogItem]:
    """Возвращает все активные фильмы каталога."""
    return await get_filtered_active_items(session)


async def count_active_items(
    session: AsyncSession,
    category_id: int = 0,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    genres: list[str] | None = None,
) -> int:
    items = await get_filtered_active_items(
        session,
        category_id,
        ages=ages,
        durations=durations,
        genres=genres,
    )
    return len(items)


async def get_items_page(
    session: AsyncSession,
    category_id: int = 0,
    page: int = 1,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    genres: list[str] | None = None,
) -> list[CatalogItem]:
    items = await get_filtered_active_items(
        session,
        category_id,
        ages=ages,
        durations=durations,
        genres=genres,
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


async def get_available_genre_filters(session: AsyncSession, category_id: int = 0) -> list[tuple[str, str]]:
    items = await get_filtered_active_items(session, category_id)
    genres: dict[str, str] = {}
    for item in items:
        for value in item_metadata(item)["genres"]:
            genres[theme_key(value)] = value
    return sorted(genres.items(), key=lambda pair: pair[1].lower())


async def get_available_theme_filters(session: AsyncSession, category_id: int = 0) -> list[tuple[str, str]]:
    items = await get_filtered_active_items(session, category_id)
    themes: dict[str, str] = {}
    for item in items:
        for value in item_metadata(item)["themes"]:
            themes[theme_key(value)] = value
    return sorted(themes.items(), key=lambda pair: pair[1].lower())
