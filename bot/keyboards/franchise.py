from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def franchise_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Условия и инвестиции", callback_data="franchise:conditions")
    builder.button(text="Поддержка и обучение", callback_data="franchise:support")
    builder.button(text="Рынок и конкуренты", callback_data="franchise:market")
    builder.button(text="Частые вопросы", callback_data="franchise:faq")
    builder.button(text="Оставить заявку", callback_data="lead:franchise")
    builder.button(text="← Главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def franchise_section_keyboard(show_market: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Оставить заявку", callback_data="lead:franchise")
    builder.button(text="← Назад", callback_data="franchise:main")
    builder.adjust(2)
    return builder.as_markup()
