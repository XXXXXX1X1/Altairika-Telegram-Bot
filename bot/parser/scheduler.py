"""
Планировщик автоматического парсинга (APScheduler).
Запускается вместе с ботом, работает в том же event loop.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.parser.sync import sync_catalog

logger = logging.getLogger(__name__)


def create_scheduler(session_factory: async_sessionmaker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    async def job() -> None:
        logger.info("Планировщик: запуск синхронизации каталога")
        result = await sync_catalog(session_factory)
        logger.info(
            "Планировщик: добавлено %d, обновлено %d, деактивировано %d, ошибок %d",
            result.added, result.updated, result.deactivated, result.errors,
        )

    # Ежедневно в 03:00 по московскому времени
    scheduler.add_job(
        job,
        trigger=CronTrigger(hour=3, minute=0, timezone="Europe/Moscow"),
        id="catalog_sync",
        replace_existing=True,
        misfire_grace_time=3600,  # допустимое опоздание — 1 час
    )

    return scheduler
