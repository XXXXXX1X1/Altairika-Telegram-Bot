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

CATALOG_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "catalog.png"

EMPTY_CATALOG_TEXT = (
    "Каталог временно недоступен.\n"
    "Оставьте контакт — мы ответим на все вопросы."
)


def _theme_label(theme_key: str, themes: list[tuple[str, str]]) -> str:
    for key, label in themes:
        if key == theme_key:
            return label
    return ""


def _s(value: str | None) -> str:
    return value or ""


def _empty_filters() -> dict[str, list[str]]:
    return {"ages": [], "durations": [], "genres": []}


async def _get_applied_filters(state: FSMContext) -> dict[str, list[str]]:
    return (await state.get_data()).get("catalog_filters_applied", _empty_filters())


async def _get_draft_filters(state: FSMContext) -> dict[str, list[str]]:
    return (await state.get_data()).get("catalog_filters_draft", _empty_filters())


async def _set_applied_filters(state: FSMContext, filters: dict[str, list[str]]) -> None:
    await state.update_data(catalog_filters_applied=filters)


async def _set_draft_filters(state: FSMContext, filters: dict[str, list[str]]) -> None:
    await state.update_data(catalog_filters_draft=filters)


def _toggle_value(values: list[str], value: str) -> list[str]:
    if not value:
        return values
    current = list(values)
    if value in current:
        current.remove(value)
    else:
        current.append(value)
    return current


@router.callback_query(F.data == "catalog")
async def catalog_entry(callback: CallbackQuery, session, state: FSMContext) -> None:
    await _set_applied_filters(state, _empty_filters())
    await _set_draft_filters(state, _empty_filters())
    await _show_categories(callback, session)


@router.callback_query(CatalogCb.filter(F.action == "cats"))
async def show_categories(callback: CallbackQuery, session, state: FSMContext) -> None:
    await _set_applied_filters(state, _empty_filters())
    await _set_draft_filters(state, _empty_filters())
    await _show_categories(callback, session)


async def _show_categories(callback: CallbackQuery, session) -> None:
    categories = await get_active_categories(session)

    if not categories:
        await show_text_screen(callback, EMPTY_CATALOG_TEXT)
        await callback.answer()
        return

    if len(categories) == 1:
        cat = categories[0]
        await _render_list(callback, session, cat_id=cat.id, page=1)
        return

    text = "<b>Каталог</b>\n\nВыберите категорию или просмотрите всё:"
    await show_text_screen(
        callback,
        text,
        reply_markup=categories_keyboard(categories),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "list"))
async def show_list(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    filters = await _get_applied_filters(state)
    await _render_list(
        callback,
        session,
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
    total = await count_active_items(
        session,
        cat_id,
        ages=ages,
        durations=durations,
        genres=genres,
    )

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

    items = await get_items_page(
        session,
        cat_id,
        page,
        ages=ages,
        durations=durations,
        genres=genres,
    )

    categories = await get_active_categories(session)
    show_categories_back = len(categories) > 1
    available_genres = await get_available_genre_filters(session, cat_id)

    if cat_id == 0:
        category_name = "Каталог фильмов"
    else:
        cat = next((c for c in categories if c.id == cat_id), None)
        category_name = cat.name if cat else "Каталог"

    text = format_items_list(
        items,
        page,
        total,
        title_override or category_name,
        ages=ages or [],
        durations=durations or [],
        genre_labels=[
            _theme_label(genre_key_value, available_genres)
            for genre_key_value in (genres or [])
            if _theme_label(genre_key_value, available_genres)
        ],
    )
    keyboard = items_list_keyboard(
        items,
        page,
        pages,
        cat_id,
        show_categories_back=show_categories_back,
    )

    await show_local_photo_screen(
        callback,
        CATALOG_IMAGE_PATH,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "item"))
async def show_item(callback: CallbackQuery, callback_data: CatalogCb, session) -> None:
    item = await get_item_by_id(session, callback_data.item_id)

    if not item:
        await callback.answer("Позиция не найдена.", show_alert=True)
        return

    similar = await has_similar_items(session, item.category_id, item.id)
    similar_theme = primary_theme_key(item) if similar else None
    keyboard = item_text_keyboard(
        item.id,
        callback_data.cat_id,
        callback_data.page,
        similar_theme,
    )

    if item.image_url:
        caption = format_item_text(item, include_poster_link=False)
        await show_photo_screen(
            callback,
            photo=item.image_url,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        text = format_item_text(item)
        await show_text_screen(callback, text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action == "similar"))
async def show_similar(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    theme = _s(callback_data.theme)
    filters = {"ages": [], "durations": [], "genres": []}
    await _set_applied_filters(state, filters)
    await _set_draft_filters(state, filters)
    available_themes = await get_available_theme_filters(session, callback_data.cat_id)
    theme_name = _theme_label(theme, available_themes)
    title = f"Похожие фильмы: {theme_name}" if theme_name else "Похожие фильмы"
    await _render_list(
        callback,
        session,
        cat_id=callback_data.cat_id,
        page=1,
        ages=filters["ages"],
        durations=filters["durations"],
        genres=filters["genres"],
        title_override=title,
    )


@router.callback_query(CatalogCb.filter(F.action == "filters"))
async def show_filters(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    draft = await _get_draft_filters(state)
    if not any(draft.values()):
        applied = await _get_applied_filters(state)
        draft = {
            "ages": list(applied["ages"]),
            "durations": list(applied["durations"]),
            "genres": list(applied["genres"]),
        }
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
    values = [(value, value) for value in await get_available_age_filters(session, callback_data.cat_id)]
    draft = await _get_draft_filters(state)
    await show_text_screen(
        callback,
        "<b>Фильтр по возрасту</b>\n\nМожно выбрать несколько вариантов.",
        reply_markup=filter_values_keyboard(
            callback_data.cat_id,
            "age",
            values,
            selected_values=set(draft["ages"]),
        ),
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
        reply_markup=filter_values_keyboard(
            callback_data.cat_id,
            "duration",
            values,
            selected_values=set(draft["durations"]),
        ),
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
        reply_markup=filter_values_keyboard(
            callback_data.cat_id,
            "genre",
            values,
            selected_values=set(draft["genres"]),
        ),
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
        callback,
        session,
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
        callback,
        session,
        cat_id=callback_data.cat_id,
        page=callback_data.page,
        ages=filters["ages"],
        durations=filters["durations"],
        genres=filters["genres"],
    )


@router.callback_query(CatalogCb.filter(F.action == "full"))
async def show_full_text(callback: CallbackQuery, callback_data: CatalogCb, session) -> None:
    item = await get_item_by_id(session, callback_data.item_id)

    if not item:
        await callback.answer("Позиция не найдена.", show_alert=True)
        return

    text = format_item_text(item)
    similar = await has_similar_items(session, item.category_id, item.id)
    keyboard = item_text_keyboard(
        item.id,
        callback_data.cat_id,
        callback_data.page,
        similar,
    )

    await show_text_screen(callback, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
