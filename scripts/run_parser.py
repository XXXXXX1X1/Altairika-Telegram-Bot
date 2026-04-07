"""
Ручной запуск парсинга и синхронизации каталога.

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/run_parser.py

Флаги:
    --dry-run   Только распарсить и вывести результат, без записи в БД
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from dotenv import load_dotenv
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main(dry_run: bool = False) -> None:
    from bot.parser.parser import parse_catalog

    print("Запуск парсинга altairika.ru/catalog_full ...")
    items = await parse_catalog()

    if not items:
        print("Ничего не найдено. Проверьте подключение или структуру страницы.")
        return

    print(f"\nНайдено позиций: {len(items)}\n")

    if dry_run:
        for i, item in enumerate(items, 1):
            print(f"{i:3}. {item.title}")
            if item.age_rating or item.duration:
                meta = " | ".join(filter(None, [item.age_rating, item.duration]))
                print(f"     {meta}")
            if item.price:
                print(f"     Цена: {item.price}")
            if item.image_url:
                print(f"     Фото: {item.image_url[:60]}...")

        print("\n[dry-run] Запись в БД пропущена.")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("\nERROR: DATABASE_URL не задан — запись в БД пропущена.")
        return

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from bot.parser.sync import sync_catalog

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    print("\nСинхронизация с БД ...")
    result = await sync_catalog(session_factory)
    await engine.dispose()

    print(f"Готово: добавлено {result.added}, обновлено {result.updated}, "
          f"деактивировано {result.deactivated}, ошибок {result.errors}.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
