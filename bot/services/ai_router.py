"""Intent router: определяет намерение пользователя по эвристикам и скорингу."""
import re

from bot.services.ai_catalog import extract_movie_title_candidate, extract_params as extract_params_regex

_DEFAULT_INTENT = "general_chat"

_GENERAL_CHAT_PHRASES = (
    "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "хай", "hello", "начнем", "начнём", "поговорим", "что ты умеешь",
    "что умеешь", "помоги", "помощь",
)
_NEUTRAL_ACK_PHRASES = (
    "понятно", "ясно", "хорошо", "спасибо", "благодарю", "понял",
    "поняла", "ок", "окей", "ладно", "ясненько",
)
_NEUTRAL_NEGATIVE_PHRASES = (
    "нет", "не надо", "не нужно", "не интересно", "неа", "не хочу",
    "не сейчас", "не, спасибо",
)

_LEAD_BOOKING_PHRASES = (
    "запишите", "записаться", "запись", "забронировать", "хочу заказать",
    "перезвоните", "перезвонить", "свяжитесь со мной", "оставить заявку",
    "оставить контакт", "хочу попробовать", "хочу записаться", "оставить номер",
    "оставить телефон", "свяжитесь", "нужен звонок", "хочу сеанс",
)
_LEAD_FRANCHISE_PHRASES = (
    "хочу франшизу", "купить франшизу", "стать партнером", "стать партнёром",
    "обсудить партнерство", "обсудить партнёрство", "заявка на франшизу",
    "хочу открыть", "оставить заявку на франшизу", "связаться по франшизе",
    "звонок по франшизе", "нужен звонок по франшизе", "свяжитесь по франшизе",
)
_FRANCHISE_INFO_ONLY_PHRASES = (
    "сколько стоит франшиза", "стоимость франшизы", "цена франшизы",
    "какая цена франшизы", "сколько нужно вложить", "какие вложения",
    "какие условия франшизы", "что входит во франшизу", "что входит",
    "какие условия", "паушальный взнос", "роялти", "окупаемость",
)
_COMPETITOR_PHRASES = (
    "конкурент", "конкуренты", "о ваших конкурентах", "ваши конкуренты",
    "лучше чем", "чем вы лучше", "сравни", "сравните",
    "чем отличаетесь", "другие компании", "аналоги", "альтернативы",
    "сравнение", "сопоставь", "в чем отличие", "в чем разница",
    "анализ конкурентов", "про конкурентов", "рынок и конкуренты",
    "анализ рынка", "конкурентный анализ", "разбор конкурентов",
)
_COMPETITOR_NAMES = ("vizerra", "vr concept", "vr arena")
_FRANCHISE_PHRASES = (
    "франшиза", "франшизу", "франшизе", "партнерство", "партнёрство",
    "паушальный", "роялти", "окупаемость", "инвестиции", "открыть бизнес",
    "свое дело", "свое дело", "своё дело", "вложения", "условия франшизы",
    "стоимость франшизы", "поддержка франшизы",
)
_FAQ_PHRASES = (
    "безопасно", "вредно", "здоровье", "зрение", "очки", "как проходит",
    "что нужно подготовить", "сколько человек", "как работает", "как устроено",
    "оборудование", "что такое vr", "что такое вр", "это безопасно",
    "для детей", "подходит детям", "как проходит сеанс", "что нужно для показа",
)
_COMPANY_PHRASES = (
    "что такое альтаирика", "расскажи о компании", "кто вы", "о вас",
    "ваша компания", "чем занимаетесь", "как давно", "сколько фильмов",
    "сколько партнеров", "сколько партнёров", "где работаете", "в каких городах",
    "ваши контакты", "где вы работаете", "кто такие", "чем вы занимаетесь",
    "юридический адрес", "юр адрес", "реквизиты", "как связаться", "связаться с вами",
    "ваш адрес", "ваш телефон", "ваш сайт", "контакты компании", "контакты альтаирика",
)

_MOVIE_SELECTION_PHRASES = (
    "подобрать", "подберите", "посоветуй", "посоветуйте", "рекомендуй",
    "рекомендуйте", "что есть про", "есть ли фильм", "фильм для", "фильмы для",
    "что посмотреть", "покажи фильм", "подборка", "нужен фильм", "подскажи фильм",
    "подберите фильм", "какие фильмы", "что у вас есть", "нужны фильмы",
    "хочу фильм", "ищу фильм", "мне нужен фильм",
)
_MOVIE_SELECTION_THEME_WORDS = (
    "космос", "природа", "история", "животные", "наука", "физика",
    "биология", "география", "английский", "обж", "пдд", "динозавры",
    "путешествие", "путешествия", "города", "страны", "транспорт", "машины",
)
_MOVIE_AUDIENCE_WORDS = (
    "класс", "класса", "классу", "возраст", "лет", "дошкольник", "дошкольники",
    "детский сад", "малыши", "начальная школа", "средняя школа", "школьник",
)
_MOVIE_DURATION_WORDS = ("минут", "мин", "длительность", "короткий", "короткое")
_MOVIE_DETAILS_PHRASES = (
    "расскажи про фильм", "расскажи о фильме", "что за фильм", "описание фильма",
    "информация о фильме", "о фильме", "про фильм", "сколько длится",
    "для какого возраста", "про что фильм", "что это за фильм",
    "по конкретному фильму", "о конкретном фильме", "конкретный фильм",
)
_MOVIE_TITLE_EXCLUDE = {
    "цена", "цены", "стоимость", "контакты", "адрес", "где", "как", "почему",
    "зачем", "когда", "можно", "нужно", "сколько", "альтаирика", "франшиза",
    "компания", "безопасно", "сеанс", "показ", "оборудование", "каталог",
    "вопрос", "ответ", "условия", "инвестиции", "заявка", "заявку",
    "оставить", "оставлю", "оставьте", "хочу", "привет", "здравствуйте",
    "добрый", "день", "вечер", "утро", "поговорить", "помоги",
    "понятно", "ясно", "хорошо", "спасибо", "благодарю", "понял", "поняла",
    "ок", "окей", "ладно", "нет", "не", "неа", "интересно", "надо",
    "контент", "отличия", "отличаетесь", "разница", "конкуренты", "конкурентах",
    "конкурентами", "конкурент", "сравни", "сравните", "сравнение", "анализ",
    "лучше", "хуже", "сравнение",
}


def _normalize_text(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[\"'`«»„“”()\[\]{}<>:;!?.,/\\|*_+=~№-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokens(text: str) -> list[str]:
    return [token for token in _normalize_text(text).split() if token]


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_grade_pattern(text: str) -> bool:
    return bool(re.search(r"\d{1,2}\s*класс", text))


def _has_age_pattern(text: str) -> bool:
    return bool(
        re.search(r"\d{1,2}\s*лет", text)
        or re.search(r"возраст\s*\d{1,2}", text)
        or re.search(r"от\s*\d{1,2}\s*лет", text)
    )


def _has_duration_pattern(text: str) -> bool:
    return bool(
        re.search(r"до\s*\d+\s*мин", text)
        or re.search(r"\d+\s*мин", text)
    )


def _looks_like_movie_selection(text: str) -> bool:
    extracted = extract_params_regex(text, {})
    if extracted.get("theme"):
        return True
    if _contains_any(text, _MOVIE_SELECTION_PHRASES):
        return True
    if text.startswith("тема "):
        return True
    if _has_grade_pattern(text) or _has_age_pattern(text) or _has_duration_pattern(text):
        return True
    if any(word in text for word in _MOVIE_AUDIENCE_WORDS + _MOVIE_DURATION_WORDS):
        return True
    tokens = _tokens(text)
    if len(tokens) <= 2 and any(token in _MOVIE_SELECTION_THEME_WORDS for token in tokens):
        return True
    if any(word in text for word in _MOVIE_SELECTION_THEME_WORDS) and (
        "фильм" in text or "фильмы" in text or "подоб" in text or "что есть" in text or "тема" in text
    ):
        return True
    return False


def _looks_like_movie_details(text: str) -> bool:
    extracted = extract_params_regex(text, {})
    if extracted.get("theme"):
        return False
    if _contains_any(text, _MOVIE_DETAILS_PHRASES):
        return True

    tokens = _tokens(text)
    if len(tokens) <= 2 and any(token in _MOVIE_SELECTION_THEME_WORDS for token in tokens):
        return False
    if text.startswith("тема "):
        return False

    title_candidate = extract_movie_title_candidate(text)
    if not title_candidate:
        return False

    title_tokens = _tokens(title_candidate)
    if not 1 <= len(title_tokens) <= 5:
        return False
    if any(token in _MOVIE_TITLE_EXCLUDE for token in title_tokens):
        return False
    if any(char.isdigit() for char in title_candidate):
        return False
    return True


def _score_lead_booking(text: str) -> int:
    score = 0
    if _contains_any(text, _LEAD_BOOKING_PHRASES):
        score += 4
    if "сеанс" in text and any(word in text for word in ("запис", "брон", "заявк", "контакт")):
        score += 3
    if "заявк" in text and "франшиз" not in text:
        score += 2
    return score


def _score_lead_franchise(text: str) -> int:
    score = 0
    if _contains_any(text, _FRANCHISE_INFO_ONLY_PHRASES):
        return 0
    if _contains_any(text, _LEAD_FRANCHISE_PHRASES):
        score += 5
    if "франшиз" in text and any(word in text for word in ("заявк", "контакт", "обсуд", "связ")):
        score += 3
    if "франшиз" in text and any(word in text for word in ("звонок", "перезвон", "созвон")):
        score += 3
    return score


def _score_competitor_compare(text: str) -> int:
    score = 0
    if _contains_any(text, _COMPETITOR_PHRASES):
        score += 4
    if any(name in text for name in _COMPETITOR_NAMES):
        score += 4
    if "конкурент" in text and any(word in text for word in ("анализ", "разбор", "рынок")):
        score += 4
    if "альтаирика" in text and any(word in text for word in ("лучше", "отлич", "разниц", "сравн")):
        score += 3
    return score


def _score_franchise_info(text: str) -> int:
    score = 0
    if _contains_any(text, _FRANCHISE_PHRASES):
        score += 4
    if "франшиз" in text:
        score += 2
    return score


def _score_faq_answer(text: str) -> int:
    score = 0
    if _contains_any(text, _FAQ_PHRASES):
        score += 4
    if "vr" in text or "вр" in text:
        score += 1
    return score


def _score_company_info(text: str) -> int:
    score = 0
    if _contains_any(text, _COMPANY_PHRASES):
        score += 4
    if "альтаирика" in text and any(word in text for word in ("кто", "что", "где", "чем", "сколько")):
        score += 2
    return score


def _score_general_chat(text: str) -> int:
    score = 0
    if _contains_any(text, _GENERAL_CHAT_PHRASES):
        score += 4
    if text in _NEUTRAL_ACK_PHRASES:
        score += 5
    if text in _NEUTRAL_NEGATIVE_PHRASES:
        score += 5
    tokens = _tokens(text)
    if len(tokens) <= 3 and any(token in {"привет", "здравствуйте", "помоги", "понятно", "ясно", "спасибо", "понял", "нет"} for token in tokens):
        score += 4
    return score


def _score_movie_selection(text: str) -> int:
    score = 0
    extracted = extract_params_regex(text, {})
    if extracted.get("theme"):
        score += 4
    if _contains_any(text, _MOVIE_SELECTION_PHRASES):
        score += 4
    if text.startswith("тема "):
        score += 4
    if _has_grade_pattern(text):
        score += 3
    if _has_age_pattern(text):
        score += 3
    if _has_duration_pattern(text):
        score += 3
    if any(word in text for word in _MOVIE_SELECTION_THEME_WORDS):
        score += 2
    tokens = _tokens(text)
    if len(tokens) <= 2 and any(token in _MOVIE_SELECTION_THEME_WORDS for token in tokens):
        score += 3
    if any(word in text for word in _MOVIE_AUDIENCE_WORDS):
        score += 2
    if "фильм" in text or "фильмы" in text:
        score += 1
    return score


def _score_movie_details(text: str) -> int:
    score = 0
    if _score_competitor_compare(text) > 0:
        return 0
    if _contains_any(text, _MOVIE_DETAILS_PHRASES):
        score += 4
    tokens = _tokens(text)
    if len(tokens) <= 2 and any(token in _MOVIE_SELECTION_THEME_WORDS for token in tokens):
        return 0
    if text.startswith("тема "):
        return 0
    if _looks_like_movie_details(text):
        score += 3
    if "фильм" in text and any(word in text for word in ("расскажи", "описание", "про что", "длится", "возраст")):
        score += 2
    return score


def detect_intent(text: str) -> str:
    """Определяет intent по свободному тексту."""
    normalized = _normalize_text(text)
    if not normalized:
        return _DEFAULT_INTENT

    scores = {
        "general_chat": _score_general_chat(normalized),
        "lead_booking": _score_lead_booking(normalized),
        "lead_franchise": _score_lead_franchise(normalized),
        "competitor_compare": _score_competitor_compare(normalized),
        "franchise_info": _score_franchise_info(normalized),
        "faq_answer": _score_faq_answer(normalized),
        "company_info": _score_company_info(normalized),
        "movie_selection": _score_movie_selection(normalized),
        "movie_details": _score_movie_details(normalized),
    }

    if _looks_like_movie_selection(normalized):
        scores["movie_selection"] += 2
    if _looks_like_movie_details(normalized):
        scores["movie_details"] += 2

    is_neutral_reply = normalized in _NEUTRAL_ACK_PHRASES or normalized in _NEUTRAL_NEGATIVE_PHRASES
    non_general_scores = {k: v for k, v in scores.items() if k != "general_chat"}
    if not is_neutral_reply and any(score > 0 for score in non_general_scores.values()) and len(_tokens(normalized)) > 1:
        scores["general_chat"] = 0

    # В конфликте между подбором и карточкой фильма отдаём приоритет подбору,
    # если пользователь явно задаёт параметры аудитории/длительности.
    if scores["movie_selection"] >= 5 and (
        _has_grade_pattern(normalized) or _has_age_pattern(normalized) or _has_duration_pattern(normalized)
    ):
        scores["movie_selection"] += 2

    # Для лидов и сравнения оставляем более высокий приоритет, чтобы не уводить
    # явные коммерческие намерения в общую консультацию.
    priority = [
        "general_chat",
        "lead_franchise",
        "lead_booking",
        "competitor_compare",
        "franchise_info",
        "movie_selection",
        "movie_details",
        "faq_answer",
        "company_info",
    ]

    best_intent = _DEFAULT_INTENT
    best_score = 0
    for intent in priority:
        score = scores[intent]
        if score > best_score:
            best_intent = intent
            best_score = score

    return best_intent if best_score > 0 else _DEFAULT_INTENT
