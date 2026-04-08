"""Подбор фильмов из каталога по параметрам запроса."""
import re

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import CatalogItem
from bot.repositories.catalog import get_filtered_active_items, item_metadata

# Сопоставление тем из текста пользователя → ключевые слова для поиска в тегах
_THEME_KEYWORDS: dict[str, list[str]] = {
    "космос": ["космос", "вселенная", "планета", "астрономия", "звезда", "орбита"],
    "природа": ["природа", "животные", "экология", "лес", "океан", "море", "земля"],
    "история": ["история", "древний", "средневековье", "война", "прошлое"],
    "физика": ["физика", "наука", "эксперимент", "энергия"],
    "биология": ["биология", "организм", "клетка", "тело", "анатомия"],
    "география": ["география", "страна", "континент", "путешествие", "мир"],
    "английский": ["английский", "english", "язык", "иностранный"],
    "обж": ["обж", "безопасность", "пожар", "первая помощь"],
    "пдд": ["пдд", "дорога", "правила", "транспорт"],
}

# Сопоставление класса/возраста → age_rating значения
_GRADE_TO_AGE: dict[int, list[str]] = {
    1: ["6+", "7+"],
    2: ["6+", "7+"],
    3: ["6+", "7+"],
    4: ["7+", "10+"],
    5: ["10+", "12+"],
    6: ["10+", "12+"],
    7: ["12+"],
    8: ["12+", "16+"],
    9: ["12+", "16+"],
    10: ["16+"],
    11: ["16+"],
}


def extract_params(text: str, existing_state: dict) -> dict:
    """Извлекает параметры подбора из текста пользователя."""
    params = dict(existing_state)
    lower = text.lower()

    # Класс
    grade_match = re.search(r"(\d{1,2})\s*класс", lower)
    if grade_match:
        params["grade"] = int(grade_match.group(1))

    # Возраст
    age_match = re.search(r"(\d{1,2})\s*лет", lower)
    if age_match:
        params["age"] = int(age_match.group(1))

    # Длительность
    duration_match = re.search(r"до\s*(\d+)\s*минут", lower)
    if duration_match:
        minutes = int(duration_match.group(1))
        if minutes <= 5:
            params["duration"] = "d5"
        elif minutes <= 15:
            params["duration"] = "d15"
        elif minutes <= 30:
            params["duration"] = "d30"
        else:
            params["duration"] = "d30p"

    # Тема
    for theme, keywords in _THEME_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            params["theme"] = theme
            break

    # Аудитория
    if any(w in lower for w in ["дошкольник", "детский сад", "малыш"]):
        params["audience"] = "preschool"
    elif any(w in lower for w in ["начальная школа", "младший класс"]):
        params["audience"] = "primary"
    elif any(w in lower for w in ["средняя школа", "старший класс"]):
        params["audience"] = "secondary"

    return params


def _age_ratings_for_params(params: dict) -> list[str] | None:
    """Возвращает список подходящих age_rating по классу или возрасту."""
    grade = params.get("grade")
    if grade and isinstance(grade, int) and grade in _GRADE_TO_AGE:
        return _GRADE_TO_AGE[grade]

    age = params.get("age")
    if age and isinstance(age, int):
        if age <= 7:
            return ["4+", "6+", "7+"]
        if age <= 10:
            return ["4+", "6+", "7+", "10+"]
        if age <= 12:
            return ["10+", "12+"]
        return ["12+", "16+"]

    audience = params.get("audience")
    if audience == "preschool":
        return ["4+", "6+"]
    if audience == "primary":
        return ["6+", "7+", "10+"]
    if audience == "secondary":
        return ["10+", "12+", "16+"]

    return None


def _score_item(item: CatalogItem, params: dict) -> int:
    """Оценивает релевантность фильма. Чем выше — тем лучше."""
    score = 0
    meta = item_metadata(item)
    all_tags = " ".join(
        meta["genres"] + meta["themes"] + meta["languages"] + meta["formats"]
    ).lower()

    theme = params.get("theme")
    if theme and theme in _THEME_KEYWORDS:
        for kw in _THEME_KEYWORDS[theme]:
            if kw in all_tags or (item.title and kw in item.title.lower()):
                score += 3
                break

    if item.description and theme:
        for kw in _THEME_KEYWORDS.get(theme, []):
            if kw in item.description.lower():
                score += 1
                break

    return score


async def find_relevant_films(
    db: AsyncSession, params: dict, limit: int = 5
) -> list[CatalogItem]:
    """Находит наиболее релевантные фильмы по параметрам."""
    age_ratings = _age_ratings_for_params(params)
    duration = [params["duration"]] if "duration" in params else None
    theme = params.get("theme")

    items = await get_filtered_active_items(
        db,
        ages=age_ratings,
        durations=duration,
    )

    if not items:
        items = await get_filtered_active_items(db)

    # Ранжируем по релевантности темы
    scored = sorted(
        [(item, _score_item(item, params)) for item in items],
        key=lambda x: x[1],
        reverse=True,
    )

    # Если тема задана — возвращаем ТОЛЬКО фильмы с ненулевым score.
    # Это предотвращает показ случайных фильмов когда тема не совпадает с тегами.
    if theme:
        relevant = [item for item, score in scored if score > 0]
        if relevant:
            return relevant[:limit]
        # Нет совпадений по тегам — ищем по названию и описанию расширенно
        keywords = _THEME_KEYWORDS.get(theme, [theme])
        fallback = [
            item for item in items
            if any(
                kw in (item.title or "").lower()
                or kw in (item.description or "").lower()
                or kw in (item.short_description or "").lower()
                for kw in keywords
            )
        ]
        if fallback:
            return fallback[:limit]
        # Совсем ничего — возвращаем пустой список (честнее чем нерелевантное)
        return []

    # Без темы — возвращаем топ по score (или просто первые если score=0 у всех)
    return [item for item, _ in scored[:limit]]


def format_films_for_prompt(items: list[CatalogItem]) -> str:
    """Форматирует список фильмов для вставки в промпт."""
    if not items:
        return "Фильмы по запросу не найдены."

    lines = []
    for item in items:
        parts = [f"• {item.title}"]
        if item.age_rating:
            parts.append(f"Возраст: {item.age_rating}")
        if item.duration:
            parts.append(f"Длительность: {item.duration}")
        if item.short_description:
            parts.append(item.short_description[:200])
        elif item.description:
            parts.append(item.description[:200])
        lines.append(" | ".join(parts))

    return "\n".join(lines)
