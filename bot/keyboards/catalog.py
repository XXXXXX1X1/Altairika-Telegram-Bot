from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models.db import CatalogItem, Category

ITEMS_PER_PAGE = 5


class CatalogCb(CallbackData, prefix="cat"):
    action: str
    cat_id: int = 0
    page: int = 1
    item_id: int = 0
    age: str | None = None
    duration: str | None = None
    theme: str | None = None
    genre: str | None = None


def _short_selection(prefix: str, values: list[str], fallback: str) -> str:
    if not values:
        return f"{prefix}: {fallback}"
    text = ", ".join(values)
    if len(text) > 24:
        text = f"{', '.join(values[:2])} +{len(values) - 2}"
    return f"{prefix}: {text}"


def _short_theme_selection(prefix: str, values: list[str], fallback: str) -> str:
    if not values:
        return f"{prefix}: {fallback}"
    count = len(values)
    return f"{prefix}: {count} выбрано"


def _noop() -> InlineKeyboardButton:
    return InlineKeyboardButton(text=" ", callback_data="noop")


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    total = sum(c.item_count for c in categories)
    builder.button(
        text=f"🎞️ Все ({total})",
        callback_data=CatalogCb(action="list", cat_id=0, page=1).pack(),
    )
    for cat in categories:
        builder.button(
            text=f"📁 {cat.name}",
            callback_data=CatalogCb(action="list", cat_id=cat.id, page=1).pack(),
        )
    if len(categories) > 5:
        builder.adjust(1)
    else:
        builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    )
    return builder.as_markup()


def items_list_keyboard(
    items: list[CatalogItem],
    page: int,
    total_pages: int,
    cat_id: int,
    *,
    show_categories_back: bool,
    show_filters_button: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for i, item in enumerate(items, start=1):
        builder.button(
            text=f"{i}. {item.title[:35]}{'…' if len(item.title) > 35 else ''}",
            callback_data=CatalogCb(
                action="item",
                cat_id=cat_id,
                page=page,
                item_id=item.id,
            ).pack(),
        )
    builder.adjust(1)

    prev_btn = (
        InlineKeyboardButton(
            text="←",
            callback_data=CatalogCb(
                action="list",
                cat_id=cat_id,
                page=page - 1,
            ).pack(),
        )
        if page > 1
        else _noop()
    )
    counter_btn = InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="noop")
    next_btn = (
        InlineKeyboardButton(
            text="→",
            callback_data=CatalogCb(
                action="list",
                cat_id=cat_id,
                page=page + 1,
            ).pack(),
        )
        if page < total_pages
        else _noop()
    )
    builder.row(prev_btn, counter_btn, next_btn)

    if show_filters_button:
        builder.row(
            InlineKeyboardButton(
                text="🔎 Фильтры",
                callback_data=CatalogCb(
                    action="filters",
                    cat_id=cat_id,
                    page=1,
                ).pack(),
            )
        )

    if show_categories_back:
        builder.row(
            InlineKeyboardButton(
                text="⬅️ Назад к категориям",
                callback_data=CatalogCb(action="cats").pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu",
            )
        )
    return builder.as_markup()


def item_text_keyboard(
    item_id: int,
    cat_id: int,
    page: int,
    similar_theme_key: str | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📝 Записаться", callback_data=f"lead:booking:{item_id}"),
        InlineKeyboardButton(
            text="⬅️ Назад к списку",
            callback_data=CatalogCb(
                action="list",
                cat_id=cat_id,
                page=page,
            ).pack(),
        ),
    )
    row2 = [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="faq")]
    if similar_theme_key:
        row2.append(
            InlineKeyboardButton(
                text="✨ Похожие",
                callback_data=CatalogCb(
                    action="similar",
                    cat_id=cat_id,
                    page=1,
                    theme=similar_theme_key,
                ).pack(),
            )
        )
    builder.row(*row2)

    return builder.as_markup()


def filter_menu_keyboard(
    cat_id: int,
    *,
    selected_ages: list[str],
    selected_durations: list[str],
    selected_genres: list[str],
    has_genres: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_short_selection("🎂 Возраст", selected_ages, "любой"),
        callback_data=CatalogCb(
            action="filter_age",
            cat_id=cat_id,
        ).pack(),
    )
    builder.button(
        text=_short_selection("⏱️ Длительность", selected_durations, "любая"),
        callback_data=CatalogCb(
            action="filter_duration",
            cat_id=cat_id,
        ).pack(),
    )
    if has_genres:
        builder.button(
            text=_short_theme_selection("📚 Предметы", selected_genres, "все"),
            callback_data=CatalogCb(
                action="filter_genre",
                cat_id=cat_id,
            ).pack(),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="✅ Применить фильтр",
            callback_data=CatalogCb(action="apply_filters", cat_id=cat_id).pack(),
        )
    )
    if selected_ages or selected_durations or selected_genres:
        builder.row(
            InlineKeyboardButton(
                text="🧹 Сбросить фильтры",
                callback_data=CatalogCb(action="clear_filters", cat_id=cat_id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к списку",
            callback_data=CatalogCb(
                action="list",
                cat_id=cat_id,
                page=1,
            ).pack(),
        )
    )
    return builder.as_markup()


def filter_values_keyboard(
    cat_id: int,
    field: str,
    values: list[tuple[str, str]],
    *,
    selected_values: set[str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for code, label in values:
        checked = "✅ " if code in selected_values else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{checked}{label}",
                callback_data=CatalogCb(
                    action=f"toggle_{field}",
                    cat_id=cat_id,
                    age=code if field == "age" else None,
                    duration=code if field == "duration" else None,
                    theme=code if field == "theme" else None,
                    genre=code if field == "genre" else None,
                ).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="✅ Применить фильтр",
            callback_data=CatalogCb(action="apply_filters", cat_id=cat_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад к фильтрам",
            callback_data=CatalogCb(action="filters", cat_id=cat_id).pack(),
        )
    )
    return builder.as_markup()
