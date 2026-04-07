from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def step_keyboard(*, allow_skip: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if allow_skip:
        builder.button(text="Пропустить", callback_data="lead:skip")
    builder.button(text="Отмена", callback_data="lead:cancel")
    builder.adjust(2 if allow_skip else 1)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Всё верно, отправить", callback_data="lead:submit"),
                InlineKeyboardButton(text="Изменить", callback_data="lead:edit"),
            ],
            [
                InlineKeyboardButton(text="Отмена", callback_data="lead:cancel"),
            ],
        ]
    )


def after_submit_keyboard(has_catalog: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_catalog:
        builder.button(text="← Вернуться в каталог", callback_data="catalog")
    builder.button(text="Главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def exit_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Продолжить", callback_data="lead:continue"),
                InlineKeyboardButton(text="Выйти", callback_data="lead:exit"),
            ],
        ]
    )
