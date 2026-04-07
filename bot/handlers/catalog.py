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
    get_available_theme_filters,
    get_item_by_id,
    get_items_page,
    has_similar_items,
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
    return {"ages": [], "durations": [], "themes": []}


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
        themes=filters["themes"],
    )


async def _render_list(
    callback: CallbackQuery,
    session,
    cat_id: int,
    page: int,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    themes: list[str] | None = None,
) -> None:
    total = await count_active_items(
        session,
        cat_id,
        ages=ages,
        durations=durations,
        themes=themes,
    )

    if total == 0:
        await show_text_screen(
            callback,
            "По выбранным фильтрам ничего не найдено.\n\nПопробуйте сбросить фильтры.",
            reply_markup=filter_menu_keyboard(
                cat_id,
                selected_ages=ages or [],
                selected_durations=durations or [],
                selected_themes=themes or [],
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
        themes=themes,
    )

    categories = await get_active_categories(session)
    show_categories_back = len(categories) > 1
    available_themes = await get_available_theme_filters(session, cat_id)

    if cat_id == 0:
        category_name = "Каталог фильмов"
    else:
        cat = next((c for c in categories if c.id == cat_id), None)
        category_name = cat.name if cat else "Каталог"

    text = format_items_list(
        items,
        page,
        total,
        category_name,
        ages=ages or [],
        durations=durations or [],
        theme_labels=[
            _theme_label(theme_key_value, available_themes)
            for theme_key_value in (themes or [])
            if _theme_label(theme_key_value, available_themes)
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
    keyboard = item_text_keyboard(
        item.id,
        callback_data.cat_id,
        callback_data.page,
        similar,
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


@router.callback_query(CatalogCb.filter(F.action == "filters"))
async def show_filters(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    draft = await _get_draft_filters(state)
    if not any(draft.values()):
        applied = await _get_applied_filters(state)
        draft = {
            "ages": list(applied["ages"]),
            "durations": list(applied["durations"]),
            "themes": list(applied["themes"]),
        }
        await _set_draft_filters(state, draft)
    themes = await get_available_theme_filters(session, callback_data.cat_id)
    await show_text_screen(
        callback,
        "<b>Фильтры каталога</b>\n\nВыберите, как отфильтровать фильмы:",
        reply_markup=filter_menu_keyboard(
            callback_data.cat_id,
            selected_ages=draft["ages"],
            selected_durations=draft["durations"],
            selected_themes=draft["themes"],
            has_themes=bool(themes),
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


@router.callback_query(CatalogCb.filter(F.action == "filter_theme"))
async def show_filter_theme(callback: CallbackQuery, callback_data: CatalogCb, session, state: FSMContext) -> None:
    values = await get_available_theme_filters(session, callback_data.cat_id)
    if not values:
        await callback.answer("Темы появятся после следующей синхронизации каталога.", show_alert=True)
        return
    draft = await _get_draft_filters(state)
    await show_text_screen(
        callback,
        "<b>Фильтр по темам</b>\n\nМожно выбрать несколько вариантов.",
        reply_markup=filter_values_keyboard(
            callback_data.cat_id,
            "theme",
            values,
            selected_values=set(draft["themes"]),
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(CatalogCb.filter(F.action.in_(["toggle_age", "toggle_duration", "toggle_theme"])))
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
    draft["themes"] = _toggle_value(draft["themes"], _s(callback_data.theme))
    await _set_draft_filters(state, draft)
    await show_filter_theme(callback, callback_data, session, state)


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
        themes=draft["themes"],
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
        themes=filters["themes"],
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
