"""
Импорт каталога из CSV-файла.

Формат CSV (заголовки обязательны):
    title, description, category, image_url, price, duration, age_rating, url

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/import_csv.py catalog.csv

Логика:
- Если категория с таким именем уже есть — переиспользуется.
- Если позиция с таким title уже есть — обновляется.
- После импорта пересчитываются item_count в категориях.
"""

import asyncio
import csv
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Добавляем корень проекта в путь, чтобы импортировать bot.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.models.db import CatalogItem, Category  # noqa: E402


SHORT_DESC_LEN = 200


def _short_desc(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= SHORT_DESC_LEN:
        return text
    return text[:SHORT_DESC_LEN].rsplit(" ", 1)[0] + "..."


async def import_csv(path: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Читаю {len(rows)} строк из {path}")

    async with session_factory() as session:
        category_cache: dict[str, Category] = {}

        # Загрузим существующие категории
        existing_cats = await session.execute(select(Category))
        for cat in existing_cats.scalars():
            category_cache[cat.name] = cat

        added = updated = 0

        for row in rows:
            title = row.get("title", "").strip()
            if not title:
                print(f"  SKIP: пустой title в строке {reader.line_num}")
                continue

            # Категория
            cat_name = row.get("category", "").strip()
            cat: Category | None = None
            if cat_name:
                if cat_name not in category_cache:
                    cat = Category(name=cat_name, order=len(category_cache))
                    session.add(cat)
                    await session.flush()  # получаем id
                    category_cache[cat_name] = cat
                cat = category_cache[cat_name]

            # Позиция каталога
            result = await session.execute(
                select(CatalogItem).where(CatalogItem.title == title)
            )
            item = result.scalar_one_or_none()

            description = row.get("description", "").strip() or None

            if item is None:
                item = CatalogItem(title=title)
                session.add(item)
                added += 1
            else:
                updated += 1

            item.description = description
            item.short_description = _short_desc(description)
            item.category_id = cat.id if cat else None
            item.image_url = row.get("image_url", "").strip() or None
            item.price = row.get("price", "").strip() or None
            item.duration = row.get("duration", "").strip() or None
            item.age_rating = row.get("age_rating", "").strip() or None
            item.url = row.get("url", "").strip() or None
            item.is_active = True

        await session.flush()

        # Пересчёт item_count в категориях
        for cat in category_cache.values():
            result = await session.execute(
                select(CatalogItem).where(
                    CatalogItem.category_id == cat.id,
                    CatalogItem.is_active.is_(True),
                )
            )
            cat.item_count = len(result.scalars().all())

        await session.commit()

    await engine.dispose()
    print(f"Готово: добавлено {added}, обновлено {updated}.")
    print(f"Категорий в кэше: {len(category_cache)}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Использование: python {sys.argv[0]} <path_to_csv>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(import_csv(sys.argv[1]))
