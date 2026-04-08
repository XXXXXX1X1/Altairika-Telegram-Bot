from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 О компании", callback_data="about_company")],
        [
            InlineKeyboardButton(text="🎬 Каталог фильмов", callback_data="catalog"),
            InlineKeyboardButton(text="🤖 Подобрать фильм", callback_data="ai_pick_movie"),
        ],
        [InlineKeyboardButton(text="🚀 Франшиза", callback_data="franchise")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="📞 Связаться с нами", callback_data="contact")],
    ])


def about_company_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Каталог фильмов", callback_data="catalog")],
        [InlineKeyboardButton(text="📞 Связаться с нами", callback_data="contact")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])
