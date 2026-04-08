# Точка входа бота: /start, главное меню, о компании, /sync.

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.keyboards.main_menu import about_company_keyboard, main_menu_keyboard
from bot.repositories.analytics import log_event
from bot.repositories.users import upsert_user
from bot.utils.message_render import show_local_photo_screen, show_text_screen

router = Router()

WELCOME_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "brand" / "logo.png"
ABOUT_COMPANY_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "sections" / "about_company.png"

_WELCOME_TEXT = (
    "Добро пожаловать в Альтаирику!\n\n"
    "Мы создаём образовательные VR/360° фильмы для школ, планетариев и семей.\n\n"
    "Выберите раздел ниже или просто напишите в чат, что вам нужно.\n\n"
    "Например: «подберите фильм про космос», «расскажи о фильме Бангкок», "
    "«как проходит сеанс»."
)

_ABOUT_COMPANY_TEXT = (
    "<b>🏢 О компании Альтаирика</b>\n\n"
    "Альтаирика создаёт образовательные VR и 360° фильмы для детей, школ, планетариев, "
    "лагерей и семейного досуга.\n\n"
    "<b>Что делаем</b>\n"
    "• показываем детям космос, природу, историю, географию и науку через эффект погружения\n"
    "• проводим выездные сеансы в школах и на мероприятиях\n"
    "• помогаем сделать обучение более наглядным и интересным\n\n"
    "<b>Как проходит сеанс</b>\n"
    "• ребёнок надевает VR-очки и смотрит фильм в формате 360°\n"
    "• показ проходит в безопасном и понятном формате для детской аудитории\n"
    "• программы есть для разных возрастов\n\n"
    "<b>Почему нас выбирают</b>\n"
    "• большой каталог образовательных фильмов\n"
    "• международная работа и показы в разных странах\n"
    "• формат подходит как для занятий, так и для событий\n"
    "• сочетание технологий, контента и понятной методики показа\n\n"
    "Можете не только пользоваться кнопками, но и писать в чат обычными сообщениями."
)


# ---------------------------------------------------------------------------
# /start и /menu
# ---------------------------------------------------------------------------

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
    await log_event(session, message.from_user.id, "open_main_menu")
    await message.answer_photo(
        photo=FSInputFile(str(WELCOME_IMAGE_PATH)),
        caption=_WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Главное меню (callback)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_local_photo_screen(
        callback,
        WELCOME_IMAGE_PATH,
        _WELCOME_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# О компании
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "about_company")
async def cb_about_company(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_local_photo_screen(
        callback,
        ABOUT_COMPANY_IMAGE_PATH,
        _ABOUT_COMPANY_TEXT,
        reply_markup=about_company_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# /sync — ручной запуск парсинга (только для администратора)
# ---------------------------------------------------------------------------

@router.message(Command("sync"))
async def cmd_sync(message: Message) -> None:
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        return

    await message.answer("Запускаю парсинг каталога...")

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker as _sf

    from bot.parser.sync import sync_catalog

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        result = await sync_catalog(_sf(engine, expire_on_commit=False))
    finally:
        await engine.dispose()

    await message.answer(
        f"Синхронизация завершена:\n"
        f"Добавлено: {result.added}\n"
        f"Обновлено: {result.updated}\n"
        f"Деактивировано: {result.deactivated}\n"
        f"Ошибок: {result.errors}"
    )
