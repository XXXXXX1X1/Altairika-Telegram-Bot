from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def after_ai_keyboard(intent: str = "") -> InlineKeyboardMarkup:
    """Клавиатура после ответа AI. Кнопки зависят от intent'а."""
    builder = InlineKeyboardBuilder()

    if intent in ("movie_selection", "movie_details"):
        builder.row(
            InlineKeyboardButton(text="🎬 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="📝 Записаться", callback_data="lead_booking"),
        )
    elif intent in ("franchise_info", "lead_franchise"):
        builder.row(
            InlineKeyboardButton(text="🤝 Франшиза", callback_data="franchise"),
            InlineKeyboardButton(text="📩 Оставить заявку", callback_data="lead_franchise"),
        )
    elif intent in ("lead_booking",):
        builder.row(
            InlineKeyboardButton(text="📝 Оставить заявку", callback_data="lead_booking"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🎬 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="📝 Записаться", callback_data="lead_booking"),
        )

    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def ai_fallback_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура при ошибке / fallback."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq"),
            InlineKeyboardButton(text="✍️ Написать вопрос", callback_data="faq_question"),
        ],
        [
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
        ],
    ])
