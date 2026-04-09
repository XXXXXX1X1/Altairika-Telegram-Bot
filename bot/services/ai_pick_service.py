"""Чистая бизнес-логика FSM-подбора фильмов. Без Telegram-объектов."""
from bot.services.ai_catalog import extract_params as extract_params_regex

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

LEAD_INTENTS: frozenset[str] = frozenset({"lead_booking", "lead_franchise"})
MOVIE_PARAM_KEYS: tuple[str, ...] = ("theme", "grade", "age", "audience", "duration")

_THEME_LIST_HINTS: tuple[str, ...] = (
    "какие есть темы", "какие темы", "список тем", "покажи темы",
    "какие есть направления", "какие направления", "что есть по темам",
)
_REFINE_REQUEST_HINTS: tuple[str, ...] = (
    "уточним", "уточнить", "давай уточним", "хочу уточнить",
    "давай подробнее", "подробнее", "сузим", "сужай", "давай сузим",
)

NO_NEW_PARAMS_TEXT = (
    "Пока не вижу новых параметров.\n\n"
    "Напишите, что именно уточнить: тему, возраст, класс или длительность.\n\n"
    "Например: «ПДД, 7 лет» или «до 15 минут, начальная школа»."
)

_SELECTION_START_QUESTION = (
    "🎬 <b>Давайте подберём фильм</b>\n\n"
    "Напишите, что важно для подбора: тему, возраст, класс или длительность.\n\n"
    "Например:\n"
    "• «ПДД для 2 класса»\n"
    "• «история, 7 лет»\n"
    "• «природа, до 20 минут»\n\n"
    "Можно начать и с одного параметра, например: «космос»."
)

_DURATION_LABELS: dict[str, str] = {
    "d5": "до 5 мин",
    "d15": "до 15 мин",
    "d30": "до 30 мин",
    "d30p": "30+ мин",
}

_THEME_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Космос", ("космос", "вселен", "астроном", "солн", "звезд", "планет", "галак")),
    ("История", ("истори", "древн", "рим", "средневек", "войн", "цивилиза")),
    ("Природа", ("природ", "живот", "океан", "водопад", "эколог", "лес", "мор", "земл")),
    ("Города и путешествия", ("город", "страна", "путешеств", "россия", "москва", "алтай")),
    ("Наука", ("математ", "физик", "биолог", "хим", "наук", "анатом")),
    ("ПДД и безопасность", ("пдд", "дорож", "безопас")),
]


# ---------------------------------------------------------------------------
# Чистые функции
# ---------------------------------------------------------------------------

def describe_params(params: dict) -> str:
    """Краткое описание параметров для заголовка подборки."""
    parts = []
    if theme := params.get("theme"):
        parts.append(f"тема «{theme}»")
    if grade := params.get("grade"):
        parts.append(f"{grade} класс")
    elif params.get("audience") == "preschool":
        parts.append("дошкольники")
    elif params.get("audience") == "primary":
        parts.append("начальная школа")
    if duration := params.get("duration"):
        label = _DURATION_LABELS.get(duration, "")
        if label:
            parts.append(label)
    return ", ".join(p for p in parts if p)


def has_meaningful_movie_params(params: dict) -> bool:
    """Есть ли хотя бы один параметр подбора."""
    return any(params.get(key) for key in MOVIE_PARAM_KEYS)


def looks_like_refine_request(text: str) -> bool:
    """Пользователь хочет уточнить текущую подборку?"""
    lower = text.lower().strip()
    return any(hint in lower for hint in _REFINE_REQUEST_HINTS)


def wants_theme_list(text: str) -> bool:
    """Пользователь просит список тем?"""
    lower = text.lower().strip()
    return any(hint in lower for hint in _THEME_LIST_HINTS)


def has_new_constraints(existing_params: dict, new_params: dict) -> bool:
    """Появились ли в новом запросе параметры, которых не было раньше."""
    for key in MOVIE_PARAM_KEYS:
        if existing_params.get(key) != new_params.get(key):
            return True
    return False


def should_refine_existing_selection(user_text: str, data: dict) -> bool:
    """Нужно ли применить новые параметры к уже существующей подборке."""
    existing_params = data.get("ai_params") or {}
    if not existing_params or not data.get("ai_item_ids"):
        return False
    lower = user_text.lower()
    new_params = extract_params_regex(user_text, existing_params)
    if has_new_constraints(existing_params, new_params):
        return True
    return any(
        hint in lower
        for hint in (
            "тема", "возраст", "лет", "класс", "длительность", "минут", "мин",
            "дошколь", "начальн", "средн", "пдд", "космос", "природ", "истори",
            "животн", "наук", "географ", "биолог", "обж", "английск",
        )
    )


def should_ask_for_selection_details(
    current_state: str | None,
    existing_params: dict,
    params: dict,
) -> bool:
    """Нужно ли задать уточняющий вопрос перед поиском."""
    if has_meaningful_movie_params(params):
        return False
    if current_state and current_state.endswith("refine"):
        return True
    if existing_params:
        return False
    return True


def _format_clarification_reason(reason: str) -> str:
    """Очищает текст причины уточнения от технических артефактов LLM."""
    cleaned = " ".join((reason or "").split()).strip(" .,-:")
    if not cleaned:
        return "Нужно чуть больше деталей."
    blocked_starts = (
        "пользователь хочет",
        "пользователь уточняет",
        "нужен дополнительный запрос",
    )
    lower = cleaned.lower()
    if any(lower.startswith(prefix) for prefix in blocked_starts):
        return "Нужно чуть больше деталей."
    return cleaned


def build_selection_question(existing_params: dict, params: dict) -> str:
    """Текст уточняющего вопроса для экрана подбора."""
    if params.get("needs_clarification"):
        reason = params.get("clarification_reason")
        if isinstance(reason, str) and reason.strip():
            return (
                "🎬 <b>Давайте уточним подбор</b>\n\n"
                f"{_format_clarification_reason(reason)}\n\n"
                "Напишите тему, возраст, класс или длительность.\n\n"
                "Например: «история, 7 лет» или «ПДД до 20 минут»."
            )
    if existing_params:
        return NO_NEW_PARAMS_TEXT
    return _SELECTION_START_QUESTION


def resolve_movie_action(
    decision: dict,
    user_text: str,
    current_state: str | None,
    data: dict,
) -> str:
    """Определяет следующее действие в сценарии подбора фильма."""
    from bot.states.ai_movie import AiPick  # локальный импорт чтобы не было циклического

    action = str(decision.get("action") or "").strip()
    if action:
        return action

    existing_params = data.get("ai_params") or {}
    inferred_params = extract_params_regex(user_text, existing_params)

    if has_meaningful_movie_params(inferred_params):
        return "run_search"
    if wants_theme_list(user_text):
        return "show_themes"
    if current_state == AiPick.waiting.state and looks_like_refine_request(user_text):
        return "ask_clarification"
    if existing_params or data.get("ai_item_ids"):
        return "run_search"
    return "ask_clarification"


def group_theme_labels(labels: list[str]) -> list[tuple[str, list[str]]]:
    """Группирует метки тем по категориям для отображения списка."""
    grouped: dict[str, list[str]] = {name: [] for name, _ in _THEME_GROUPS}
    other: list[str] = []

    for label in labels:
        normalized = label.lower().replace("ё", "е")
        matched = False
        for group_name, keywords in _THEME_GROUPS:
            if any(keyword in normalized for keyword in keywords):
                grouped[group_name].append(label)
                matched = True
                break
        if not matched:
            other.append(label)

    result = [(name, values[:4]) for name, values in grouped.items() if values]
    if other:
        result.append(("Другое", other[:4]))
    return result[:6]
