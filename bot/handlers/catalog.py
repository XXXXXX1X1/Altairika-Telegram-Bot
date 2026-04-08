# Обработчики каталога фильмов: категории, список, карточка, фильтры, похожие.

from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.catalog import (
    CatalogCb,
    categories_keyboard,
    filter_menu_keyboard,
    filter_values_keyboard,
    item_text_keyboard,
    items_list_keyboard,
)
from bot.repositories.analytics import log_event
from bot.repositories.catalog import (
    count_active_items,
    get_active_categories,
    get_available_age_filters,
    get_available_duration_filters,
    get_available_genre_filters,
    get_available_theme_filters,
    get_item_by_id,
    get_items_page,
    has_similar_items,
    primary_theme_key,
)
from bot.services.catalog import (
    format_item_text,
    format_items_list,
    total_pages,
)
from bot.utils.message_render import (
    show_local_photo_screen,
    show_photo_screen,
    show_text_screen,
)

router = Router()

CATALOG_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "sections" / "catalog_cover.png"

_EMPTY_CATALOG_TEXT = (
    "Каталог временно недоступен.\n"
    "Оставьте контакт — мы ответим на все вопросы."
)


# ---------------------------------------------------------------------------
# Вспомогательные функции фильтрации
# ---------------------------------------------------------------------------

def _theme_label(theme_key: str, themes: list[tuple[str, str]]) -> str:
    for key, label in themes:
        if key == theme_key:
            return label
    return ""


def _s(value: str | None) -> str:
    return value or ""


def _empty_filters() -> dict[str, list[str]]:
    return {"ages": [], "durations": [], "genres": []}


def _toggle_value(values: list[str], value: str) -> list[str]:
    current = list(values)
    if not value:
        return current
    if value in current:
        current.remove(value)
    else:
        current.append(value)
    return current


async def _get_applied_filters(state: FSMContext) -> dict[str, list[str]]:
    return (await state.get_data()).get("catalog_filters_applied", _empty_filters())


async def _get_draft_filters(state: FSMContext) -> dict[str, list[str]]:
    return (await state.get_data()).get("catalog_filters_draft", _empty_filters())


async def _set_applied_filters(state: FSMContext, filters: dict[str, list[str]]) -> None:
    await state.update_data(catalog_filters_applied=filters)


async def _set_draft_filters(state: FSMContext, filters: dict[str, list[str]]) -> None:
    await state.update_data(catalog_filters_draft=filters)


# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "catalog")
async def catalog_entry(callback: CallbackQuery, session, state: FSMContext) -> None:
    await _set_applied_filters(state, _empty_filters())
    await _set_draft_filters(state, _empty_filters())
    await log_event(session, callback.from_user.id, "open_catalog")
    await _show_categories(callback, session)


@router.callback_query(CatalogCb.filter(F.action == "cats"))
async def show_categories(callback: CallbackQuery, session, state: FSMContext) -> None:
    await _set_applied_filters(state, _empty_filters())
    await _set_draft_filters(state, _empty_filters())
    await _show_categories(callback, session)


async def _show_categories(callback: CallbackQuery, session) -> None:
    categories = await get_active_categories(session)

    if not categories:
        await show_text_screen(callback, _EMPTY_CATALOG_TEXT)
        await callback.answer()
        return

    # Одна категория — сразу показываем список
    if len(categories) == 1:
        await _render_list(callback, session, cat_id=categories[0].id, page=1)
        return

    await show_text_screen(
        callback,
        "<b>Каталог</b>\n\nВыберите категорию или просмотрите всё:",
        reply_markup=categories_keyboard(categories),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Список фильмов
# ---------------------------------------------------------------------------

@router.callback_query(CatalogCb.filter(F.action == "list"))
async def show_list(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    filters = await _get_applied_filters(state)
    await _render_list(
        callback, session,
        cat_id=callback_data.cat_id,
        page=callback_data.page,
        ages=filters["ages"],
        durations=filters["durations"],
        genres=filters["genres"],
    )


async def _render_list(
    callback: CallbackQuery,
    session,
    cat_id: int,
    page: int,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    genres: list[str] | None = None,
    title_override: str | None = None,
) -> None:
    total = await count_active_items(session, cat_id, ages=ages, durations=durations, genres=genres)

    if total == 0:
        await show_text_screen(
            callback,
            "По выбранным фильтрам ничего не найдено.\n\nПопробуйте сбросить фильтры.",
            reply_markup=filter_menu_keyboard(
                cat_id,
                selected_ages=ages or [],
                selected_durations=durations or [],
                selected_genres=genres or [],
            ),
        )
        await callback.answer()
        return

    pages = total_pages(total)
    page = max(1, min(page, pages))
    items = await get_items_page(session, cat_id, page, ages=ages, durations=durations, genres=genres)
    categories = await get_active_categories(session)
    available_genres = await get_available_genre_filters(session, cat_id)

    if cat_id == 0:
        category_name = "Каталог фильмов"
    else:
        cat = next((c for c in categories if c.id == cat_id), None)
        category_name = cat.name if cat else "Каталог"

    text = format_items_list(
        items, page, total,
        title_override or category_name,
        ages=ages or [],
        durations=durations or [],
        genre_labels=[
            _theme_label(key, available_genres)
            for key in (genres or [])
            if _theme_label(key, available_genres)
        ],
    )
    keyboard = items_list_keyboard(
        items, page, pages, cat_id,
        show_categories_back=len(categories) > 1,
    )
    await show_local_photo_screen(callback, CATALOG_IMAGE_PATH, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# Карточка фильма
# ---------------------------------------------------------------------------

@router.callback_query(CatalogCb.filter(F.action == "item"))
async def show_item(callback: CallbackQuery, callback_data: CatalogCb, session) -> None:
    item = await get_item_by_id(session, callback_data.item_id)
    if not item:
        await callback.answer("Позиция не найдена.", show_alert=True)
        return

    category_id = callback_data.cat_id or 0
    item_id = item.id
    similar = await has_similar_items(session, category_id, item_id)
    keyboard = item_text_keyboard(
        item_id,
        category_id,
        callback_data.page,
        primary_theme_key(item) if similar else None,
        item_url=item.url,
    )

    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        await show_photo_screen(callback, photo=item.image_url, caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await show_text_screen(callback, format_item_text(item), reply_markup=keyboard, parse_mode="HTML")

    await log_event(session, callback.from_user.id, "open_catalog_item", entity_type="catalog_item", entity_id=item_id)
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "full"))
async def show_full_text(callback: CallbackQuery, callback_data: CatalogCb, session) -> None:
    item = await get_item_by_id(session, callback_data.item_id)
    if not item:
        await callback.answer("Позиция не найдена.", show_alert=True)
        return

    category_id = callback_data.cat_id or 0
    similar = await has_similar_items(session, category_id, item.id)
    keyboard = item_text_keyboard(
        item.id,
        category_id,
        callback_data.page,
        primary_theme_key(item) if similar else None,
        item_url=item.url,
    )
    await show_text_screen(callback, format_item_text(item), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# Похожие фильмы
# ---------------------------------------------------------------------------

@router.callback_query(CatalogCb.filter(F.action == "similar"))
async def show_similar(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    theme = _s(callback_data.theme)
    filters = _empty_filters()
    await _set_applied_filters(state, filters)
    await _set_draft_filters(state, filters)
    available_themes = await get_available_theme_filters(session, callback_data.cat_id)
    theme_name = _theme_label(theme, available_themes)
    await _render_list(
        callback, session,
        cat_id=callback_data.cat_id,
        page=1,
        title_override=f"Похожие фильмы: {theme_name}" if theme_name else "Похожие фильмы",
    )


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

@router.callback_query(CatalogCb.filter(F.action == "filters"))
async def show_filters(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    draft = await _get_draft_filters(state)
    if not any(draft.values()):
        applied = await _get_applied_filters(state)
        draft = {k: list(v) for k, v in applied.items()}
        await _set_draft_filters(state, draft)
    genres = await get_available_genre_filters(session, callback_data.cat_id)
    await show_text_screen(
        callback,
        "<b>Фильтры каталога</b>\n\nВыберите, как отфильтровать фильмы:",
        reply_markup=filter_menu_keyboard(
            callback_data.cat_id,
            selected_ages=draft["ages"],
            selected_durations=draft["durations"],
            selected_genres=draft["genres"],
            has_genres=bool(genres),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "filter_age"))
async def show_filter_age(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    values = [(v, v) for v in await get_available_age_filters(session, callback_data.cat_id)]
    draft = await _get_draft_filters(state)
    await show_text_screen(
        callback,
        "<b>Фильтр по возрасту</b>\n\nМожно выбрать несколько вариантов.",
        reply_markup=filter_values_keyboard(callback_data.cat_id, "age", values, selected_values=set(draft["ages"])),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "filter_duration"))
async def show_filter_duration(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    values = await get_available_duration_filters(session, callback_data.cat_id)
    draft = await _get_draft_filters(state)
    await show_text_screen(
        callback,
        "<b>Фильтр по длительности</b>\n\nМожно выбрать несколько вариантов.",
        reply_markup=filter_values_keyboard(callback_data.cat_id, "duration", values, selected_values=set(draft["durations"])),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "filter_genre"))
async def show_filter_genre(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    values = await get_available_genre_filters(session, callback_data.cat_id)
    if not values:
        await callback.answer("Предметы появятся после следующей синхронизации каталога.", show_alert=True)
        return
    draft = await _get_draft_filters(state)
    await show_text_screen(
        callback,
        "<b>Фильтр по предметам</b>\n\nМожно выбрать несколько вариантов.",
        reply_markup=filter_values_keyboard(callback_data.cat_id, "genre", values, selected_values=set(draft["genres"])),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action.in_(["toggle_age", "toggle_duration", "toggle_genre"])))
async def toggle_filter_value(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    draft = await _get_draft_filters(state)
    if callback_data.action == "toggle_age":
        draft["ages"] = _toggle_value(draft["ages"], _s(callback_data.age))
        await _set_draft_filters(state, draft)
        await show_filter_age(callback, callback_data, session, state)
        return
    if callback_data.action == "toggle_duration":
        draft["durations"] = _toggle_value(draft["durations"], _s(callback_data.duration))
        await _set_draft_filters(state, draft)
        await show_filter_duration(callback, callback_data, session, state)
        return
    draft["genres"] = _toggle_value(draft["genres"], _s(callback_data.genre))
    await _set_draft_filters(state, draft)
    await show_filter_genre(callback, callback_data, session, state)


@router.callback_query(CatalogCb.filter(F.action == "apply_filters"))
async def apply_filter(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    draft = await _get_draft_filters(state)
    await _set_applied_filters(state, draft)
    await _render_list(
        callback, session,
        cat_id=callback_data.cat_id,
        page=1,
        ages=draft["ages"],
        durations=draft["durations"],
        genres=draft["genres"],
    )


@router.callback_query(CatalogCb.filter(F.action == "clear_filters"))
async def clear_filters(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    await _set_applied_filters(state, _empty_filters())
    await _set_draft_filters(state, _empty_filters())
    await _render_list(callback, session, cat_id=callback_data.cat_id, page=1)


@router.callback_query(CatalogCb.filter(F.action == "back"))
async def back_from_photo(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    filters = await _get_applied_filters(state)
    await _render_list(
        callback, session,
        cat_id=callback_data.cat_id,
        page=callback_data.page,
        ages=filters["ages"],
        durations=filters["durations"],
        genres=filters["genres"],
    )


# ---------------------------------------------------------------------------
# Служебные
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


