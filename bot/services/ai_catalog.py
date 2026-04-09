"""Подбор фильмов из каталога по параметрам запроса и названию."""
import re
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.db import CatalogItem
from bot.services.ai_client import call_llm_json
from bot.repositories.catalog import (
    get_active_items,
    get_filtered_active_items,
    item_metadata,
)

# Сопоставление тем из текста пользователя → ключевые слова для поиска в тегах
_THEME_KEYWORDS: dict[str, list[str]] = {
    "космос": ["космос", "вселенная", "планета", "астрономия", "звезда", "орбита"],
    "природа": ["природа", "животные", "экология", "лес", "океан", "море", "земля"],
    "история": ["история", "древний", "средневековье", "война", "прошлое"],
    "динозавры": ["динозавр", "динозавры", "динозавров", "доистор", "юрский"],
    "физика": ["физика", "наука", "эксперимент", "энергия"],
    "биология": ["биология", "организм", "клетка", "тело", "анатомия"],
    "география": ["география", "страна", "континент", "путешествие", "путешествия", "путешеств", "мир"],
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

_TITLE_PREFIX_PATTERNS = [
    r"(?:расскажи|подскажи|покажи|опиши)\s+(?:мне\s+)?(?:о|про)\s+(?:фильме|мультфильме|кино)\s+(.+)",
    r"(?:что\s+за|информация\s+о|описание\s+)(?:фильма|мультфильма|кино)\s+(.+)",
    r"(?:о|про)\s+(?:фильме|мультфильме|кино)\s+(.+)",
    r"(?:фильм|мультфильм|кино)\s+(.+)",
]

_TITLE_TRAILING_WORDS = {
    "пожалуйста", "плиз", "если", "можно", "подробнее", "кратко",
}
_QUERY_STOPWORDS = {
    "расскажи", "подскажи", "покажи", "опиши", "мне", "о", "про",
    "фильм", "фильме", "фильма", "кино", "мультфильм", "мультфильме",
    "что", "за", "информация", "описание", "пожалуйста", "хочу",
    "нужен", "нужна", "нужно", "нужны", "об", "для", "какой", "какие",
    "дай", "дайте", "подборку", "подбери", "подберите", "по", "есть",
    "какие", "какая", "какое", "какую", "у", "вас", "мне", "нужно",
    "нужна", "нужен", "нужны", "хочу", "давай",
}

_AI_MOVIE_SEARCH_PROMPT = """Ты помогаешь подобрать фильмы из каталога Альтаирики по свободному запросу пользователя.

Тебе передан запрос и список кандидатов из каталога. Нужно выбрать только те фильмы, которые действительно подходят по смыслу.

Верни ТОЛЬКО JSON такого вида:
{
  "matched_ids": [1, 2, 3]
}

Правила:
- Выбирай фильмы по теме, описанию и смыслу запроса пользователя.
- Если тема пользователя не совпадает с готовыми тегами, всё равно ищи по описанию и содержанию фильма.
- Не добавляй id, если фильм явно не подходит.
- Если подходящих фильмов нет, верни пустой список.
- Не выбирай фильм только из-за одного случайного слова.
"""


def normalize_text(text: str) -> str:
    """Нормализует текст для сопоставления без учёта регистра и пунктуации."""
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[\"'`«»„“”()\[\]{}<>:;!?.,/\\|*_+=~№-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def tokenize_text(text: str) -> list[str]:
    """Разбивает нормализованный текст на токены без короткого мусора."""
    return [token for token in normalize_text(text).split() if len(token) >= 3]


def normalize_theme_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_text(value)
    if not normalized:
        return None
    if normalized in _THEME_KEYWORDS:
        return normalized
    for theme, keywords in _THEME_KEYWORDS.items():
        if normalized == theme:
            return theme
        if any(keyword in normalized or normalized in keyword for keyword in keywords):
            return theme
    return normalized


def _token_matches(token: str, searchable_tokens: set[str]) -> bool:
    if token in searchable_tokens:
        return True
    if len(token) < 4:
        return False
    prefix = token[:5]
    return any(
        candidate.startswith(prefix) or prefix.startswith(candidate[:5])
        for candidate in searchable_tokens
        if len(candidate) >= 4
    )


def _cleanup_title_candidate(text: str) -> str:
    candidate = normalize_text(text)
    tokens = candidate.split()
    while tokens and tokens[-1] in _TITLE_TRAILING_WORDS:
        tokens.pop()
    return " ".join(tokens)


def extract_movie_title_candidate(text: str) -> str | None:
    """Пытается извлечь название фильма из свободного текста."""
    raw = (text or "").strip()
    if not raw:
        return None

    quoted_match = re.search(r"[«\"“„']([^»\"”']+)[»\"”']", raw)
    if quoted_match:
        candidate = _cleanup_title_candidate(quoted_match.group(1))
        return candidate or None

    lower = raw.lower().replace("ё", "е").strip()
    for pattern in _TITLE_PREFIX_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            candidate = _cleanup_title_candidate(match.group(1))
            return candidate or None

    tokens = tokenize_text(raw)
    if 1 <= len(tokens) <= 4 and not any(token in _QUERY_STOPWORDS for token in tokens):
        return " ".join(tokens)

    return None


def _title_match_score(item: CatalogItem, query: str) -> float:
    """Считает релевантность названия фильма запросу пользователя."""
    query_norm = normalize_text(query)
    title_norm = normalize_text(item.title or "")
    if not query_norm or not title_norm:
        return 0.0

    if title_norm == query_norm:
        return 1.0

    query_tokens = set(tokenize_text(query_norm))
    title_tokens = set(tokenize_text(title_norm))
    if not query_tokens or not title_tokens:
        return 0.0

    token_overlap = len(query_tokens & title_tokens) / max(len(query_tokens), len(title_tokens))
    ratio = SequenceMatcher(None, query_norm, title_norm).ratio()
    substring_bonus = 0.18 if query_norm in title_norm or title_norm in query_norm else 0.0

    return max(ratio, token_overlap + substring_bonus)


def _is_confident_title_match(item: CatalogItem, query: str, score: float) -> bool:
    query_norm = normalize_text(query)
    title_norm = normalize_text(item.title or "")
    if not query_norm or not title_norm:
        return False

    if title_norm == query_norm:
        return True
    if query_norm in title_norm and len(query_norm) >= 4:
        return True

    query_tokens = set(tokenize_text(query_norm))
    title_tokens = set(tokenize_text(title_norm))
    if query_tokens and query_tokens == title_tokens:
        return True

    return score >= 0.82


async def find_movie_by_title(db: AsyncSession, query: str) -> CatalogItem | None:
    """Ищет конкретный фильм по названию."""
    query_norm = normalize_text(query)
    if not query_norm:
        return None

    items = await get_active_items(db)
    if not items:
        return None

    scored = sorted(
        ((item, _title_match_score(item, query_norm)) for item in items),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top_item, top_score = scored[0]
    return top_item if _is_confident_title_match(top_item, query_norm, top_score) else None


async def find_similar_movies(
    db: AsyncSession,
    query: str,
    *,
    limit: int = 5,
    exclude_ids: set[int] | None = None,
) -> list[CatalogItem]:
    """Возвращает фильмы с наиболее похожими названиями."""
    query_norm = normalize_text(query)
    if not query_norm:
        return []

    items = await get_active_items(db)
    if exclude_ids:
        items = [item for item in items if item.id not in exclude_ids]

    scored = []
    for item in items:
        score = _title_match_score(item, query_norm)
        if score >= 0.55:
            scored.append((item, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in scored[:limit]]


def extract_params(text: str, existing_state: dict) -> dict:
    """Извлекает параметры подбора из текста пользователя."""
    params = dict(existing_state)
    lower = text.lower()
    params["raw_query"] = normalize_text(text)

    # Класс
    grade_match = re.search(r"(\d{1,2})\s*класс", lower)
    if grade_match:
        params["grade"] = int(grade_match.group(1))

    # Возраст
    age_match = re.search(r"(\d{1,2})\s*лет", lower)
    if not age_match:
        age_match = re.search(r"возраст\s*(\d{1,2})", lower)
    if not age_match:
        age_match = re.search(r"от\s*(\d{1,2})\s*лет", lower)
    if age_match:
        params["age"] = int(age_match.group(1))

    # Длительность
    duration_match = re.search(r"до\s*(\d+)\s*минут", lower)
    if not duration_match:
        duration_match = re.search(r"(?:длительность|минут|мин)\s*(\d+)", lower)
    if not duration_match:
        duration_match = re.search(r"(\d+)\s*минут", lower)
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

    raw_query = params.get("raw_query")
    if raw_query:
        query_tokens = [token for token in tokenize_text(raw_query) if token not in _QUERY_STOPWORDS]
        searchable = " ".join([
            normalize_text(item.title or ""),
            normalize_text(item.short_description or ""),
            normalize_text(item.description or ""),
            all_tags,
        ])
        searchable_tokens = set(tokenize_text(searchable))
        overlap = sum(1 for token in query_tokens if _token_matches(token, searchable_tokens))
        if overlap:
            score += min(overlap, 4)

    return score


def _searchable_text(item: CatalogItem) -> str:
    meta = item_metadata(item)
    return " ".join([
        normalize_text(item.title or ""),
        normalize_text(item.short_description or ""),
        normalize_text(item.description or ""),
        normalize_text(" ".join(meta["genres"])),
        normalize_text(" ".join(meta["themes"])),
    ]).strip()


def _semantic_shortlist(items: list[CatalogItem], params: dict, limit: int = 12) -> list[CatalogItem]:
    raw_query = params.get("raw_query", "")
    query_tokens = [token for token in tokenize_text(raw_query) if token not in _QUERY_STOPWORDS]
    scored: list[tuple[CatalogItem, float]] = []

    for item in items:
        searchable_text = _searchable_text(item)
        searchable_tokens = set(tokenize_text(searchable_text))
        overlap = sum(1 for token in query_tokens if _token_matches(token, searchable_tokens))
        base_score = _score_item(item, params)
        score = base_score + overlap * 2
        if overlap > 0 or base_score > 0:
            scored.append((item, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in scored[:limit]]


def _format_candidate_for_ai(item: CatalogItem) -> str:
    meta = item_metadata(item)
    parts = [f"id={item.id}", f"title={item.title}"]
    if item.short_description:
        parts.append(f"short={item.short_description[:220]}")
    if item.description:
        parts.append(f"description={item.description[:420]}")
    if meta["themes"]:
        parts.append(f"themes={', '.join(meta['themes'])}")
    if meta["genres"]:
        parts.append(f"genres={', '.join(meta['genres'])}")
    if item.age_rating:
        parts.append(f"age={item.age_rating}")
    if item.duration:
        parts.append(f"duration={item.duration}")
    return " | ".join(parts)


async def _ai_rank_films_by_query(
    raw_query: str,
    candidates: list[CatalogItem],
    limit: int,
) -> list[CatalogItem]:
    if not raw_query or not candidates:
        return []

    candidates_text = "\n".join(_format_candidate_for_ai(item) for item in candidates)
    payload = await call_llm_json(
        _AI_MOVIE_SEARCH_PROMPT + f"\n\nЗапрос пользователя: {raw_query}\n\nКандидаты:\n{candidates_text}",
        raw_query,
        max_tokens=220,
    )
    if not payload:
        return []

    matched_ids = payload.get("matched_ids")
    if not isinstance(matched_ids, list):
        return []

    matched_id_set = {int(value) for value in matched_ids if isinstance(value, int) or (isinstance(value, str) and value.isdigit())}
    if not matched_id_set:
        return []

    ordered = [item for item in candidates if item.id in matched_id_set]
    return ordered[:limit]


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
        raw_query = params.get("raw_query")
        if raw_query:
            ai_candidates = _semantic_shortlist(items, params, limit=max(limit * 3, 10))
            ai_ranked = await _ai_rank_films_by_query(raw_query, ai_candidates, limit)
            if ai_ranked:
                return ai_ranked
        return []

    raw_query = params.get("raw_query")
    if raw_query:
        ai_candidates = _semantic_shortlist(items, params, limit=max(limit * 3, 10))
        ai_ranked = await _ai_rank_films_by_query(raw_query, ai_candidates, limit)
        if ai_ranked:
            return ai_ranked

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


def format_movie_for_prompt(item: CatalogItem) -> str:
    """Форматирует одну карточку фильма для контекста модели."""
    meta = item_metadata(item)
    parts = [f"Название: {item.title}"]
    if item.age_rating:
        parts.append(f"Возраст: {item.age_rating}")
    if item.duration:
        parts.append(f"Длительность: {item.duration}")
    if item.short_description:
        parts.append(f"Краткое описание: {item.short_description}")
    if item.description:
        parts.append(f"Описание: {item.description}")
    if meta["genres"]:
        parts.append(f"Предметы: {', '.join(meta['genres'])}")
    if meta["themes"]:
        parts.append(f"Тема: {', '.join(meta['themes'])}")
    if meta["languages"]:
        parts.append(f"Языки: {', '.join(meta['languages'])}")
    return "\n".join(parts)


def format_similar_movies_for_prompt(items: list[CatalogItem]) -> str:
    """Форматирует список похожих фильмов для контекста модели."""
    if not items:
        return "Похожих фильмов не найдено."

    lines = []
    for item in items:
        line = f"• {item.title}"
        extras = []
        if item.age_rating:
            extras.append(item.age_rating)
        if item.duration:
            extras.append(item.duration)
        if extras:
            line += " | " + " | ".join(extras)
        lines.append(line)
    return "\n".join(lines)
