# 05. Архитектура

## Обзор

```
Пользователь / Администратор
         │
         ▼
    Telegram API
         │
         ▼
  aiogram Dispatcher
         │
    ┌────┴─────────────────────────────┐
    │           Middleware              │
    │  DbSessionMiddleware              │
    │  CallbackDebounceMiddleware       │
    └────┬─────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────────────┐
    │                      Routers                           │
    │  start  admin  lead  faq  catalog  franchise  compare │
    │  ai_movie  freetext (catch-all)                       │
    └────┬──────────────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │                  Services                      │
    │  catalog  lead  compare  admin                 │
    │  ─────────── AI-слой ──────────────────────── │
    │  ai_client  ai_router  ai_decision  ai_branch  │
    │  ai_catalog  ai_memory  ai_context  ai_answer  │
    │  ai_movie_params                               │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼────────────┐    ┌──────────────────┐
    │  Repositories   │    │   OpenRouter API  │
    │  catalog        │    │  (LLM вызовы)     │
    │  leads          │    └──────────────────┘
    │  faq            │
    │  admin          │
    │  analytics      │
    │  users          │
    │  ai_sessions    │
    └────┬────────────┘
         │
   ┌─────▼──────┐
   │ PostgreSQL  │
   └────────────┘
```

## Стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.11+ |
| Bot framework | aiogram 3.x (async, polling) |
| ORM | SQLAlchemy 2.x (async) |
| База данных | PostgreSQL 16 |
| Миграции | Alembic |
| Настройки | pydantic-settings (.env) |
| AI API | OpenRouter (openai SDK, async) |
| Деплой | Docker + docker-compose |

## Структура модулей

```
bot/
├── __main__.py              # Точка входа, сборка Dispatcher
├── config.py                # Настройки из .env (BOT_TOKEN, DATABASE_URL, AI_*)
├── middleware.py             # DbSessionMiddleware, CallbackDebounceMiddleware
│
├── handlers/
│   ├── start.py             # /start, главное меню, о компании
│   ├── admin.py             # /admin, панель администратора
│   ├── catalog.py           # Каталог фильмов, фильтры, пагинация
│   ├── lead.py              # FSM-формы заявок (booking, franchise, contact)
│   ├── faq.py               # FAQ, вопросы пользователей
│   ├── franchise.py         # Раздел франшизы
│   ├── compare.py           # Сравнение с конкурентами
│   ├── ai_movie.py          # AI-подбор фильмов (FSM AiPick)
│   └── freetext.py          # Точка входа AI, catch-all свободного текста
│
├── services/
│   ├── catalog.py           # Форматирование карточек
│   ├── lead.py              # Нормализация телефона, тексты форм
│   ├── compare.py           # Форматирование таблицы сравнения
│   ├── admin.py             # Форматирование заявок, вопросов, статистики
│   │
│   ├── ai_client.py         # Клиент OpenRouter API (call_llm, call_llm_json)
│   ├── ai_router.py         # Скоринг intent по ключевым словам (без LLM)
│   ├── ai_decision.py       # LLM-маршрутизатор (intent + action + confidence)
│   ├── ai_branch.py         # Эвристика продолжения ветки диалога
│   ├── ai_catalog.py        # Поиск и ранжирование фильмов
│   ├── ai_memory.py         # Сессионная память (чтение/запись ai_sessions)
│   ├── ai_context.py        # Сборка контекста по intent для LLM
│   ├── ai_answer.py         # Pipeline генерации ответа
│   └── ai_movie_params.py   # AI-извлечение параметров подбора
│
├── keyboards/
│   ├── main_menu.py
│   ├── admin.py             # AdminLeadsCb, AdminQCb, AdminStatsCb
│   ├── catalog.py           # CatalogCb
│   ├── lead.py, faq.py, franchise.py, compare.py
│   ├── ai.py                # after_ai_keyboard, ai_fallback_keyboard
│   └── ai_movie.py          # AiPickCb, ai_pick_*_keyboard
│
├── repositories/
│   ├── catalog.py           # get_active_items, get_filtered_active_items
│   ├── leads.py, faq.py, franchise.py, compare.py, admin.py
│   ├── analytics.py         # log_event()
│   ├── users.py             # upsert_user()
│   └── ai_sessions.py       # get_session, save_session, clear_session
│
├── states/
│   ├── lead.py              # LeadForm FSM
│   ├── admin.py             # AdminStates.waiting_reply
│   ├── faq.py               # UserQuestionForm.waiting_text
│   └── ai_movie.py          # AiPick.waiting, AiPick.refine
│
├── models/
│   └── db.py                # SQLAlchemy ORM (все таблицы)
│
├── utils/
│   └── message_render.py    # show_text_screen, show_photo_screen
│
└── parser/
    ├── parser.py            # Tilda Store API парсер
    └── sync.py              # Синхронизация каталога с БД
```

## Пользовательский контур

Вся навигация по кнопкам — редактирование текущего сообщения (`edit_message_text` / `edit_message_caption`). Новое сообщение создаётся только:

1. **Карточка с изображением** — `sendPhoto`
2. **Форма FSM** — новое сообщение при старте, затем редактирование его же
3. **AI-ответ** — всегда новое сообщение (не редактирование)

Защита от двойного нажатия: `CallbackDebounceMiddleware` блокирует повторный callback с тем же `(user_id, message_id, callback_data)` в течение 1.2 сек.

### Основные флоу

- **Каталог** → категории → список (5/стр.) → карточка → запись
- **Заявка** (FSM): имя → телефон → [время/город] → подтверждение → отправка
- **FAQ** → темы → вопросы → ответ / задать свой вопрос
- **Франшиза** → условия / поддержка / FAQ / сравнение
- **Свободный текст** → AI-pipeline → ответ + кнопки

### AI-флоу

```
Свободный текст
      │
      ├── навигационная фраза? → открыть нужный раздел
      │
      └── AI pipeline:
            load_state (ai_sessions)
            analyze_dialog_scenario (LLM, confidence)
              └── confidence < 0.45? → decide_next_intent (эвристики)
            routing по intent:
              lead_* → форма
              movie_selection → AiPick FSM
              movie_card → send_movie_card_message
              остальные → generate_answer
            generate_answer → build_context → call_llm
            update_state
            ответ + after_ai_keyboard
```

## Админский контур

Вход: `/admin`. Доступ только по `ADMIN_TELEGRAM_ID`. Проверка на каждом handler и callback.

| Раздел | Функционал |
|--------|-----------|
| Заявки | Список с сортировкой (new → in_progress → done), карточка, смена статуса |
| Вопросы | Список (неотвеченные сначала), карточка, ответ через FSM, отметить отвеченным |
| Статистика | Метрики за сегодня / 7 дней / 30 дней / всё время |

## Модели БД

| Таблица | Назначение |
|---------|-----------|
| `categories` | Категории каталога |
| `catalog_items` | Фильмы (title, description, tags JSON, image_url, age_rating, duration) |
| `bot_users` | Зарегистрированные пользователи |
| `leads` | Заявки (booking, franchise, contact) |
| `faq_topics` / `faq_items` | FAQ |
| `user_questions` | Вопросы пользователей операторам |
| `franchise_content` | Контент раздела франшизы (4 секции) |
| `competitors` / `comparison_parameters` / `comparison_values` | Сравнение с конкурентами |
| `analytics_events` | Аналитические события |
| `ai_sessions` | Сессионная память AI-ассистента |

## Аналитика

Таблица `analytics_events` собирает события. Логирование через `repositories/analytics.log_event()`. Ошибки не прерывают основной флоу.

Логируемые события: `open_main_menu`, `open_catalog`, `open_catalog_item`, `start_lead_form`, `submit_lead`, `ask_question`.

## Деплой

Два режима запуска (см. `docker-compose.yml`):

```bash
# Без парсера
docker compose up --build -d

# С парсером каталога (profile with-parser)
docker compose --profile with-parser up --build -d
```

## Ограничения текущей реализации

- Режим polling (не webhook)
- FSM storage — MemoryStorage (сбрасывается при перезапуске)
- AI-сессии хранятся в PostgreSQL (переживают перезапуск)
- Нет Redis (кеширование и FSM для multi-instance)
- Нет Sentry / внешнего мониторинга
- Нет шифрования персональных данных в БД
- База знаний (`docs/work/10_company_knowledge.md`) кешируется in-memory
