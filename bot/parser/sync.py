"""
Синхронизация результатов парсинга с базой данных.

Логика:
- Новые позиции → INSERT
- Существующие (по title) → UPDATE полей
- Позиции, которых нет на сайте → is_active = False
- После синхронизации пересчитываются item_count в категориях
"""

import logging
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.models.db import CatalogItem, Category
from bot.parser.parser import ParsedItem, parse_catalog

logger = logging.getLogger(__name__)

SHORT_DESC_LEN = 200


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    deactivated: int = 0
    errors: int = 0


def _short_desc(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= SHORT_DESC_LEN:
        return text
    return text[:SHORT_DESC_LEN].rsplit(" ", 1)[0] + "..."


async def _get_or_create_category(
    session: AsyncSession, name: str, cat_cache: dict[str, Category]
) -> Category:
    if name in cat_cache:
        return cat_cache[name]
    result = await session.execute(select(Category).where(Category.name == name))
    cat = result.scalar_one_or_none()
    if cat is None:
        cat = Category(name=name, order=len(cat_cache))
        session.add(cat)
        await session.flush()
    cat_cache[name] = cat
    return cat


async def sync_catalog(
    session_factory: async_sessionmaker,
    parsed: list[ParsedItem] | None = None,
) -> SyncResult:
    """
    Запускает парсинг и синхронизирует результат с БД.
    Возвращает SyncResult с количеством изменений.
    """
    result = SyncResult()

    if parsed is None:
        parsed = await parse_catalog()
    if not parsed:
        logger.warning("Синхронизация: парсер вернул 0 позиций — пропускаем обновление БД")
        result.errors = 1
        return result

    async with session_factory() as session:
        # Загрузить все активные позиции из БД (по title)
        db_result = await session.execute(select(CatalogItem))
        existing: dict[str, CatalogItem] = {
            item.title: item for item in db_result.scalars()
        }

        cat_cache: dict[str, Category] = {}
        seen_titles: set[str] = set()

        for p in parsed:
            seen_titles.add(p.title)
            item = existing.get(p.title)

            # Категория
            cat_id = None
            if p.category:
                cat = await _get_or_create_category(session, p.category, cat_cache)
                cat_id = cat.id

            if item is None:
                # Новая позиция
                item = CatalogItem(
                    title=p.title,
                    description=p.description,
                    short_description=_short_desc(p.description),
                    category_id=cat_id,
                    tags=json.dumps(p.tags, ensure_ascii=False) if p.tags else None,
                    image_url=p.image_url,
                    price=p.price,
                    duration=p.duration,
                    age_rating=p.age_rating,
                    url=p.url,
                    is_active=True,
                )
                session.add(item)
                result.added += 1
            else:
                # Обновить изменившиеся поля
                changed = False
                for attr, val in [
                    ("description", p.description),
                    ("short_description", _short_desc(p.description)),
                    ("category_id", cat_id),
                    ("tags", json.dumps(p.tags, ensure_ascii=False) if p.tags else None),
                    ("image_url", p.image_url),
                    ("price", p.price),
                    ("duration", p.duration),
                    ("age_rating", p.age_rating),
                    ("url", p.url),
                ]:
                    if getattr(item, attr) != val:
                        setattr(item, attr, val)
                        changed = True
                if not item.is_active:
                    item.is_active = True
                    changed = True
                if changed:
                    result.updated += 1

        # Деактивировать позиции, которых нет в новом парсинге
        for title, item in existing.items():
            if title not in seen_titles and item.is_active:
                item.is_active = False
                result.deactivated += 1

        await session.flush()

        # Пересчёт item_count в категориях
        all_cats_result = await session.execute(select(Category))
        for cat in all_cats_result.scalars():
            count_result = await session.execute(
                select(CatalogItem).where(
                    CatalogItem.category_id == cat.id,
                    CatalogItem.is_active.is_(True),
                )
            )
            cat.item_count = len(count_result.scalars().all())

        await session.commit()

    logger.info(
        "Синхронизация завершена: добавлено %d, обновлено %d, деактивировано %d",
        result.added, result.updated, result.deactivated,
    )
    return result
