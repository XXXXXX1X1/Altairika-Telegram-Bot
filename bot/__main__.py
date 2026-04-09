import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings
from bot.handlers.admin import router as admin_router
from bot.repositories.ai_sessions import cleanup_expired
from bot.handlers.ai_movie import router as ai_movie_router
from bot.handlers.catalog import router as catalog_router
from bot.handlers.compare import router as compare_router
from bot.handlers.faq import router as faq_router
from bot.handlers.franchise import router as franchise_router
from bot.handlers.freetext import router as freetext_router
from bot.handlers.lead import router as lead_router
from bot.handlers.start import router as start_router
from bot.middleware import CallbackDebounceMiddleware, DbSessionMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_SESSION_CLEANUP_INTERVAL = 3600  # секунд (1 час)


async def _session_cleanup_loop(session_factory: async_sessionmaker) -> None:
    """Фоновая задача: удаляет истёкшие AI-сессии раз в час."""
    while True:
        await asyncio.sleep(_SESSION_CLEANUP_INTERVAL)
        try:
            async with session_factory() as db:
                await cleanup_expired(db)
            logger.debug("AI-сессии: очистка истёкших записей выполнена")
        except Exception as e:
            logger.exception("Ошибка при очистке AI-сессий: %s", e)


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.callback_query.middleware(CallbackDebounceMiddleware())

    dp.include_router(start_router)
    dp.include_router(admin_router)
    # lead_router и faq_router раньше остальных: StateFilter перехватывает FSM-прерывания
    dp.include_router(lead_router)
    dp.include_router(faq_router)
    dp.include_router(catalog_router)
    dp.include_router(franchise_router)
    dp.include_router(compare_router)
    # ai_movie_router до freetext: перехватывает сообщения в состоянии AiPick
    dp.include_router(ai_movie_router)
    # freetext_router последним: ловит всё, что не поймали выше
    dp.include_router(freetext_router)

    cleanup_task = asyncio.create_task(_session_cleanup_loop(session_factory))
    logger.info("Bot started (polling)")
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
