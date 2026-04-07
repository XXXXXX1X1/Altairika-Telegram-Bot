from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def compare_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Оставить заявку", callback_data="lead:franchise")
    builder.button(text="Частые вопросы", callback_data="faq")
    builder.button(text="← Назад", callback_data="franchise:main")
    builder.adjust(2, 1)
    return builder.as_markup()
