import math
from html import escape

from bot.keyboards.catalog import ITEMS_PER_PAGE
from bot.models.db import CatalogItem
from bot.repositories.catalog import item_metadata


def total_pages(total_items: int) -> int:
    return max(1, math.ceil(total_items / ITEMS_PER_PAGE))


def duration_label(code: str) -> str:
    return {
        "d5": "До 5 минут",
        "d15": "5–15 минут",
        "d30": "15–30 минут",
        "d30p": "30+ минут",
    }.get(code, "")


def format_item_text(item: CatalogItem, include_poster_link: bool = True) -> str:
    """Полный текст карточки для текстового сообщения."""
    parts = [f"<b>{escape(item.title)}</b>"]

    if item.short_description:
        parts.append(escape(item.short_description))

    if item.description:
        parts.append(escape(item.description))

    meta = []
    if item.age_rating:
        meta.append(f"Возраст: {escape(item.age_rating)}")
    if item.duration:
        meta.append(f"Длительность: {escape(item.duration)}")

    if meta:
        parts.append(" | ".join(meta))

    metadata = item_metadata(item)
    if metadata["genres"]:
        parts.append(f"Предметы: {escape(', '.join(metadata['genres']))}")
    if metadata["themes"]:
        parts.append(f"Тема: {escape(', '.join(metadata['themes']))}")
    if metadata["languages"]:
        parts.append(f"Языки: {escape(', '.join(metadata['languages']))}")

    if item.price:
        parts.append(f"Цена: {escape(item.price)}")

    if include_poster_link and item.image_url:
        parts.append(f'<a href="{escape(item.image_url, quote=True)}">Постер</a>')

    return "\n\n".join(parts)


def format_items_list(
    items: list[CatalogItem],
    page: int,
    total_items: int,
    category_name: str,
    *,
    ages: list[str] | None = None,
    durations: list[str] | None = None,
    genre_labels: list[str] | None = None,
) -> str:
    start = (page - 1) * ITEMS_PER_PAGE + 1
    end = min(page * ITEMS_PER_PAGE, total_items)

    header = f"<b>{escape(category_name)}</b>"
    counter = f"Показано {start}–{end} из {total_items}"
    filters = []
    if ages:
        filters.append(f"Возраст: {escape(', '.join(ages))}")
    if durations:
        filters.append(
            f"Длительность: {escape(', '.join(duration_label(code) for code in durations if duration_label(code)))}"
        )
    if genre_labels:
        filters.append(f"Предметы: {escape(', '.join(genre_labels))}")

    parts = [header, counter]
    if filters:
        parts.append(filters[0] if len(filters) == 1 else "\n".join(filters))
    return "\n\n".join(parts)
