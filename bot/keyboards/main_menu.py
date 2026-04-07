from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каталог фильмов", callback_data="catalog")],
        [InlineKeyboardButton(text="Франшиза", callback_data="franchise")],
        [InlineKeyboardButton(text="Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="Связаться с нами", callback_data="contact")],
    ])
