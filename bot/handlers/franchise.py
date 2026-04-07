from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.franchise import franchise_main_keyboard, franchise_section_keyboard
from bot.models.db import FranchiseSection
from bot.repositories.franchise import get_franchise_content
from bot.utils.message_render import show_local_photo_screen, show_text_screen

router = Router()

FRANCHISE_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "fr.png"

_NO_CONTENT = (
    "Информация по этому разделу скоро появится.\n\n"
    "Оставьте заявку — мы расскажем подробнее."
)


# ---------------------------------------------------------------------------
# Главная страница франшизы
# ---------------------------------------------------------------------------

@router.callback_query(F.data.in_({"franchise", "franchise:main"}))
async def franchise_main(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.pitch)
    text = content.content if content else (
        "<b>Франшиза Альтаирика</b>\n\n"
        "Станьте партнёром и откройте собственный центр виртуальной реальности.\n"
        "Более 14 лет на рынке, 3 млн зрителей, партнёры в 12 странах."
    )
    await show_local_photo_screen(
        callback,
        FRANCHISE_IMAGE_PATH,
        text,
        reply_markup=franchise_main_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Условия и инвестиции
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "franchise:conditions")
async def franchise_conditions(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.conditions)
    text = content.content if content else _NO_CONTENT
    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_section_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Поддержка и обучение
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "franchise:support")
async def franchise_support(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.support)
    text = content.content if content else _NO_CONTENT
    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_section_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# franchise:market обрабатывается в compare_router (Фаза 6)
# franchise:faq обрабатывается в faq_router (Фаза 5)
