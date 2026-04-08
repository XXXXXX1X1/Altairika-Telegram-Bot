from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AiPickCb(CallbackData, prefix="aip"):
    action: str          # nav | book | refine | newtopic | catalog | exit
    idx: int = 0
    item_id: int = 0


def ai_pick_results_keyboard(
    idx: int,
    total: int,
    item_id: int,
) -> InlineKeyboardMarkup:
    """Клавиатура карточки в AI-подборке: листалка + действия."""
    builder = InlineKeyboardBuilder()

    # Листалка ← {i}/{total} →
    prev_btn = (
        InlineKeyboardButton(
            text="←",
            callback_data=AiPickCb(action="nav", idx=idx - 1, item_id=item_id).pack(),
        )
        if idx > 0
        else InlineKeyboardButton(text=" ", callback_data="noop")
    )
    counter_btn = InlineKeyboardButton(
        text=f"{idx + 1} / {total}",
        callback_data="noop",
    )
    next_btn = (
        InlineKeyboardButton(
            text="→",
            callback_data=AiPickCb(action="nav", idx=idx + 1, item_id=item_id).pack(),
        )
        if idx < total - 1
        else InlineKeyboardButton(text=" ", callback_data="noop")
    )
    builder.row(prev_btn, counter_btn, next_btn)

    # Записаться на этот фильм
    builder.row(
        InlineKeyboardButton(
            text="📝 Записаться на этот фильм",
            callback_data=f"lead:booking:{item_id}",
        )
    )

    # Действия с подборкой
    builder.row(
        InlineKeyboardButton(
            text="🔄 Другая тема",
            callback_data=AiPickCb(action="newtopic").pack(),
        ),
        InlineKeyboardButton(
            text="⚙️ Уточнить",
            callback_data=AiPickCb(action="refine").pack(),
        ),
    )

    builder.row(
        InlineKeyboardButton(text="🎬 Весь каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
    )

    return builder.as_markup()


def ai_pick_empty_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура когда ничего не нашлось."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Попробовать другой запрос",
                callback_data=AiPickCb(action="newtopic").pack(),
            ),
        ],
        [
            InlineKeyboardButton(text="🎬 Весь каталог", callback_data="catalog"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
        ],
    ])


def ai_pick_cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены во время диалога подбора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Весь каталог", callback_data="catalog"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
        ],
    ])
