# 09. AI-ассистент — реализация

> **Статус:** реализовано (Фаза 8)  
> Дата реализации: апрель 2026 (~5 часов разработки)

---

## Обзор

AI-ассистент встроен в `freetext_router` — перехватчик свободного текста вне FSM-форм. Если `OPENROUTER_API_KEY` не задан, бот возвращает заглушку с кнопками FAQ/оператор. При заданном ключе — запускается полный pipeline.

**Модель:** `google/gemini-2.0-flash-001` через [OpenRouter API](https://openrouter.ai) (совместим с OpenAI SDK). Модель меняется через переменную `AI_MODEL` в `.env`.

---

## Поддерживаемые сценарии (intents)

| Intent | Описание | Пример запроса |
|--------|---------|---------------|
| `general_chat` | Приветствие, общие фразы | «Привет», «Помоги» |
| `movie_selection` | Подбор фильма по параметрам | «Фильм для 3 класса про космос» |
| `movie_details` | Вопрос о конкретном фильме | «Расскажи про фильм Динозавры» |
| `company_info` | Вопросы о компании | «Что такое Альтаирика?» |
| `franchise_info` | Вопросы о франшизе | «Сколько стоит франшиза?» |
| `competitor_compare` | Сравнение с конкурентами | «Чем вы лучше VR Concept?» |
| `faq_answer` | Типовые вопросы | «Безопасен ли VR для детей?» |
| `lead_booking` | Намерение записаться | «Хочу записаться» |
| `lead_franchise` | Намерение обсудить франшизу | «Хочу оставить заявку на франшизу» |

---

## Архитектура

```
Пользователь пишет текст
        │
        ▼
freetext.py: _detect_ui_action()
  ├── Текст — команда навигации? → открыть каталог / франшизу / меню
  └── Нет → AI pipeline
        │
        ▼
load_state() — загрузка сессии из БД (ai_sessions)
        │
        ▼
analyze_dialog_scenario() — LLM определяет intent + action + confidence
  └── confidence < 0.45? → decide_next_intent() (эвристики)
        │
        ▼
Intent routing:
  ├── lead_booking / lead_franchise → предложить форму, выход
  ├── movie_selection → run_ai_pick_flow() (ai_movie.py)
  ├── open_current_movie_card → send_movie_card_message()
  └── остальные → generate_answer()
        │
        ▼
generate_answer() (ai_answer.py):
  ├── movie_selection: extract_movie_params() → find_relevant_films()
  ├── movie_details: find_movie_by_title() / find_similar_movies()
  └── остальные: только контекст из БД и базы знаний
        │
        ▼
build_context() — сборка контекста по intent
        │
        ▼
call_llm() — вызов OpenRouter API
        │
        ▼
update_state() — сохранение истории и параметров в БД
        │
        ▼
Ответ пользователю + кнопки after_ai_keyboard()
```

---

## Модули

### `bot/services/ai_client.py`

Клиент OpenRouter API на базе `openai` SDK. Поддерживает:
- `call_llm(system_prompt, user_message, history, max_tokens)` → `str | None`
- `call_llm_json(...)` → `dict | None` (парсит JSON из ответа, fallback через regex)
- Таймаут 20 сек, логирование ошибок без проброса исключений

### `bot/services/ai_router.py`

Определение intent через **скоринг ключевых слов** (без LLM). Каждый intent имеет свою scoring-функцию. Побеждает intent с наибольшим суммарным баллом. При ничьей — приоритет по списку (lead > compare > franchise > movie > faq > company).

Используется как fallback когда LLM-решение (ai_decision.py) вернуло низкую уверенность (< 0.45).

### `bot/services/ai_decision.py`

**LLM-маршрутизатор** — первый вызов модели на каждый запрос. Отправляет в модель:
- системный промпт с описанием допустимых intent и action
- текущее состояние сессии (active_intent, params, последние 6 сообщений истории)
- текст пользователя

Возвращает JSON: `{ intent, action, use_current_movie, open_current_movie_card, continue_current_flow, confidence, reason }`.

Допустимые `action`: `answer`, `switch_intent`, `ask_clarification`, `show_themes`, `run_search`, `open_current_movie_card`.

### `bot/services/ai_branch.py`

Эвристический модуль. Решает, продолжать ли текущую ветку диалога или переключаться, учитывая:
- текущий active_intent и наличие ai_current_item_id
- фразы-подсказки для franchise_info, competitor_compare, movie_details
- наличие новых параметров подбора (тема, возраст, класс, длительность)

Работает без вызова LLM.

### `bot/services/ai_catalog.py`

Поиск и ранжирование фильмов:

1. **`find_movie_by_title()`** — точный поиск по названию через `SequenceMatcher` + токенное пересечение. Возвращает фильм если score ≥ 0.82 или exact/prefix match.

2. **`find_similar_movies()`** — ищет похожие названия (score ≥ 0.38), возвращает top-N.

3. **`find_relevant_films()`** — полный pipeline подбора:
   - фильтрация по age_rating и duration через SQL
   - скоринг по теме (совпадение тегов) и raw_query (токенное пересечение)
   - если score = 0 и есть сырой запрос → `_ai_rank_films_by_query()` (второй вызов LLM)

4. **`extract_params()`** — regex-извлечение параметров: класс, возраст, длительность, тема, аудитория.

### `bot/services/ai_movie_params.py`

**AI-извлечение параметров** — первичный парсер запроса через LLM с fallback на regex. Модель возвращает JSON с полями `theme, grade, age, audience, duration, needs_clarification`. Результат санируется и объединяется с regex-результатом.

### `bot/services/ai_context.py`

Сборка контекста по intent. Каждый intent получает только нужные данные:

| Intent | Источники контекста |
|--------|-------------------|
| `general_chat` | company_knowledge + FAQ |
| `movie_selection` | company_knowledge + список найденных фильмов |
| `movie_details` | company_knowledge + карточка фильма |
| `company_info` | company_knowledge + FAQ |
| `faq_answer` | company_knowledge + FAQ |
| `franchise_info` | company_knowledge + FAQ + franchise_content |
| `lead_franchise` | company_knowledge + FAQ + franchise_content |
| `competitor_compare` | company_knowledge + таблица сравнения |

База знаний компании (`docs/work/10_company_knowledge.md`) кешируется в памяти при первом обращении.

### `bot/services/ai_memory.py`

Сессионная память на базе PostgreSQL (`ai_sessions`). Хранит:
- `active_intent` — текущий сценарий
- `state_json` — JSON с параметрами подбора + история (до 8 сообщений)
- `ai_current_item_id / ai_current_item_title` — последний показанный фильм

Методы: `load_state()`, `update_state()`, `reset_state()`, `get_history()`, `append_history()`, `merge_params()`.

### `bot/services/ai_answer.py`

Главный pipeline генерации ответа:
1. `load_state()` — загрузить сессию
2. Если `movie_selection` — `extract_movie_params()` → `find_relevant_films()`
3. Если `movie_details` — `find_movie_by_title()`, при промахе → `find_similar_movies()` + шаблонный ответ (без LLM)
4. `build_context()` — собрать контекст
5. `_build_system_prompt()` — базовые правила + инструкция по intent
6. `call_llm()` — вызов модели
7. `update_state()` — сохранить историю и параметры

### `bot/handlers/ai_movie.py`

FSM-флоу подбора фильма (состояния `AiPick.waiting`, `AiPick.refine`):

```
cb ai_pick_movie → вопрос → AiPick.waiting
msg (waiting/refine) → extract_movie_params → find_relevant_films → карточки
cb aip:nav → листание карточек ← →
cb aip:newtopic → сброс параметров, AiPick.waiting
cb aip:refine → сохранение параметров, AiPick.refine
cb aip:back → восстановление предыдущего состояния
cb aip:exit → главное меню
```

При обнаружении non-movie intent в процессе подбора (например пользователь написал «хочу записаться») — FSM очищается, управление передаётся соответствующему сценарию.

---

## Сценарий подбора фильма

### Параметры

| Параметр | Тип | Пример |
|---------|-----|--------|
| `theme` | str | `"космос"`, `"природа"`, `"история"` |
| `grade` | int | `3` (3 класс) |
| `age` | int | `8` (8 лет) |
| `audience` | str | `preschool`, `primary`, `secondary` |
| `duration` | str | `d5`, `d15`, `d30`, `d30p` |

### Маппинг класса → age_rating

| Класс | age_rating |
|-------|-----------|
| 1–3 | 6+, 7+ |
| 4 | 7+, 10+ |
| 5–6 | 10+, 12+ |
| 7 | 12+ |
| 8–9 | 12+, 16+ |
| 10–11 | 16+ |

### Темы

Встроенные темы с keyword-маппингом: `космос`, `природа`, `история`, `динозавры`, `физика`, `биология`, `география`, `английский`, `обж`, `пдд`.

Запросы вне этих тем обрабатываются через AI-ранжирование (`_ai_rank_films_by_query`).

---

## Кнопки после AI-ответа

После ответа показываются кнопки из `after_ai_keyboard(intent)`:

| Intent | Кнопки |
|--------|--------|
| `movie_selection`, `movie_details` | Каталог, Записаться |
| `franchise_info`, `lead_franchise` | Франшиза, Оставить заявку |
| `company_info`, `faq_answer` | FAQ, Каталог |
| `competitor_compare` | Сравнение, Каталог |
| остальные | FAQ, Главное меню |

При ошибке LLM показывается `ai_fallback_keyboard()`: FAQ + Написать оператору + Главное меню.

---

## Fallback-поведение

| Ситуация | Поведение |
|---------|---------|
| `OPENROUTER_API_KEY` не задан | Заглушка + кнопки FAQ / оператор |
| LLM вернул None | Текст «Не удалось обработать» + fallback кнопки |
| `general_chat` + LLM None | Статический приветственный текст с направлениями |
| Фильм не найден по названию (есть похожие) | Список похожих без LLM |
| Фильм не найден совсем | Предложение уточнить или написать параметры |

---

## Ограничения

- Нет векторного поиска (нет pgvector / RAG) — только keyword/token matching
- История диалога ограничена 8 сообщениями
- Один администратор на инстанс
- FSM storage — MemoryStorage (сессия подбора теряется при перезапуске бота)
- Сессия AI сохраняется в PostgreSQL и переживает перезапуск
