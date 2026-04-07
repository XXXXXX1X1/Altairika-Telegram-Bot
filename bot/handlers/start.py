from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.keyboards.main_menu import main_menu_keyboard
from bot.repositories.users import upsert_user
from bot.utils.message_render import show_local_photo_screen

router = Router()

WELCOME_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "Logo.png"

WELCOME_TEXT = (
    "Добро пожаловать в Альтаирику!\n\n"
    "Мы создаём образовательные VR/360° фильмы для школ, планетариев и семей.\n\n"
    "Выберите раздел:"
)


@router.message(Command("start", "menu"))
async def cmd_start(message: Message, session, state: FSMContext) -> None:
    await state.clear()
    await upsert_user(
        session=session,
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        language_code=message.from_user.language_code,
    )
    await message.answer_photo(
        photo=FSInputFile(str(WELCOME_IMAGE_PATH)),
        caption=WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_local_photo_screen(
        callback,
        WELCOME_IMAGE_PATH,
        WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("sync"))
async def cmd_sync(message: Message, session_factory: async_sessionmaker = None) -> None:
    """Ручной запуск парсинга — только для администратора."""
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    await message.answer("Запускаю парсинг каталога...")

    from bot.parser.sync import sync_catalog
    # session_factory пробрасывается через middleware data
    # но здесь нам нужна фабрика напрямую — получим её из app data
    # Для простоты создаём движок на лету из settings
    from sqlalchemy.ext.asyncio import async_sessionmaker as sf, create_async_engine
    engine = create_async_engine(settings.DATABASE_URL)
    factory = sf(engine, expire_on_commit=False)

    result = await sync_catalog(factory)
    await engine.dispose()

    await message.answer(
        f"Синхронизация завершена:\n"
        f"Добавлено: {result.added}\n"
        f"Обновлено: {result.updated}\n"
        f"Деактивировано: {result.deactivated}\n"
        f"Ошибок: {result.errors}"
    )
