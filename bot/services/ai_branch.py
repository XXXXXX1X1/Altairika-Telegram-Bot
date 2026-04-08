"""Решение, продолжать ли текущую ветку диалога или переключаться на другую."""

from bot.services.ai_catalog import extract_movie_title_candidate, extract_params
from bot.services.ai_router import detect_intent

_DETAIL_FOLLOWUP_HINTS = (
    "подробнее", "расскажи подробнее", "больше деталей", "подробно",
    "про этот фильм", "об этом фильме", "что это за фильм", "про него",
)
_OPEN_CARD_HINTS = (
    "открой карточку фильма", "открой карточку", "покажи карточку",
    "открой фильм", "покажи фильм", "открой карточку этого фильма",
)
_MOVIE_CONSTRAINT_HINTS = (
    "тема", "возраст", "лет", "класс", "длительность", "минут", "мин",
    "дошколь", "начальн", "средн", "пдд", "космос", "природ", "истори",
    "животн", "наук", "географ", "биолог", "обж", "английск",
)
_FRANCHISE_FOLLOWUP_HINTS = (
    "да", "давай", "да расскажи", "расскажи", "подробнее", "хочу подробнее",
    "интересно", "да интересно", "расскажи подробнее", "давай подробнее",
    "какие условия", "что входит", "что вы даете", "что вы даете как партнеру",
)
_COMPARE_FOLLOWUP_HINTS = (
    "цена", "цены", "стоимость", "контент", "фильмы", "библиотека",
    "отличия", "разница", "условия", "оборудование", "масштаб", "франшиза",
    "подробнее", "да", "давай", "интересно", "чем лучше", "чем хуже",
)


def _get_existing_movie_params(state: dict) -> dict:
    return state.get("ai_params") or state.get("params") or {}


def _has_new_constraints(existing_params: dict, new_params: dict) -> bool:
    for key in ("theme", "grade", "age", "audience", "duration"):
        if existing_params.get(key) != new_params.get(key):
            return True
    return False


def _should_continue_movie_selection(user_text: str, state: dict) -> bool:
    existing_params = _get_existing_movie_params(state)
    if not existing_params:
        return False

    lower = user_text.lower()
    new_params = extract_params(user_text, existing_params)
    if _has_new_constraints(existing_params, new_params):
        return True

    return any(hint in lower for hint in _MOVIE_CONSTRAINT_HINTS)


def _should_open_current_movie_details(user_text: str, state: dict) -> bool:
    lower = user_text.lower().strip()
    current_item_title = state.get("ai_current_item_title")
    if not current_item_title:
        return False
    if extract_movie_title_candidate(user_text):
        return False
    return any(hint in lower for hint in _DETAIL_FOLLOWUP_HINTS)


def _should_continue_franchise_info(user_text: str, state: dict) -> bool:
    current_intent = state.get("_active_intent") or state.get("active_intent")
    if current_intent != "franchise_info":
        return False
    lower = user_text.lower().strip()
    return lower in _FRANCHISE_FOLLOWUP_HINTS or any(hint in lower for hint in _FRANCHISE_FOLLOWUP_HINTS)


def _should_continue_competitor_compare(user_text: str, state: dict) -> bool:
    current_intent = state.get("_active_intent") or state.get("active_intent")
    if current_intent != "competitor_compare":
        return False
    lower = user_text.lower().strip()
    return lower in _COMPARE_FOLLOWUP_HINTS or any(hint in lower for hint in _COMPARE_FOLLOWUP_HINTS)


def decide_next_intent(user_text: str, state: dict | None = None) -> dict[str, object]:
    """Возвращает решение о ветке диалога с учётом текущего контекста."""
    state = state or {}
    current_intent = state.get("_active_intent") or state.get("active_intent")
    detected_intent = detect_intent(user_text)

    decision: dict[str, object] = {
        "intent": detected_intent,
        "use_current_movie": False,
        "open_current_movie_card": False,
    }

    if current_intent in {"movie_selection", "movie_details"} and state.get("ai_current_item_id"):
        lower = user_text.lower().strip()
        if any(hint in lower for hint in _OPEN_CARD_HINTS):
            return {
                "intent": "movie_details",
                "use_current_movie": True,
                "open_current_movie_card": True,
            }
        if current_intent == "movie_details" and _should_open_current_movie_details(user_text, state):
            return {
                "intent": "movie_details",
                "use_current_movie": True,
                "open_current_movie_card": False,
            }

    if current_intent != "movie_selection":
        if _should_continue_competitor_compare(user_text, state):
            return {
                "intent": "competitor_compare",
                "action": "answer",
                "use_current_movie": False,
                "open_current_movie_card": False,
            }
        if _should_continue_franchise_info(user_text, state):
            return {
                "intent": "franchise_info",
                "action": "answer",
                "use_current_movie": False,
                "open_current_movie_card": False,
            }
        return decision

    if _should_open_current_movie_details(user_text, state):
        return {
            "intent": "movie_details",
            "use_current_movie": True,
        }

    if detected_intent in {"lead_booking", "lead_franchise", "company_info", "faq_answer", "franchise_info", "competitor_compare"}:
        return decision

    if detected_intent == "movie_details":
        return decision

    if _should_continue_movie_selection(user_text, state):
        return {
            "intent": "movie_selection",
            "use_current_movie": False,
        }

    return decision
