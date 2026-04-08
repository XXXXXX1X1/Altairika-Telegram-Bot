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
    ┌────▼──────────────────────────────────────────┐
    │                 Routers                        │
    │  start_router   admin_router   lead_router    │
    │  faq_router     catalog_router franchise_router│
    │  freetext_router                               │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼────────┐    ┌──────────────┐
    │  Services   │    │ Repositories │
    │  catalog    │    │  catalog     │
    │  lead       │◄───│  leads       │
    │  compare    │    │  faq         │
    │  admin      │    │  admin       │
    └─────────────┘    │  analytics   │
                       │  users       │
                       └──────┬───────┘
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
| Деплой | Docker + docker-compose |

## Структура модулей

```
bot/
├── __main__.py          # Точка входа, сборка Dispatcher
├── config.py            # Настройки из .env (BOT_TOKEN, DATABASE_URL, ADMIN_TELEGRAM_ID)
├── middleware.py         # DbSessionMiddleware, CallbackDebounceMiddleware
├── handlers/
│   ├── start.py         # /start, главное меню, о компании
│   ├── admin.py         # /admin, панель администратора
│   ├── catalog.py       # Каталог фильмов, фильтры, пагинация
│   ├── lead.py          # FSM-формы заявок (booking, franchise, contact)
│   ├── faq.py           # FAQ, вопросы пользователей
│   ├── franchise.py     # Раздел франшизы
│   ├── compare.py       # Сравнение с конкурентами
│   └── freetext.py      # Перехват свободного текста
├── keyboards/
│   ├── main_menu.py
│   ├── admin.py         # AdminLeadsCb, AdminQCb, AdminStatsCb
│   ├── catalog.py       # CatalogCb
│   ├── lead.py
│   ├── faq.py           # FaqCb
│   ├── franchise.py
│   └── compare.py
├── services/
│   ├── admin.py         # Форматирование заявок, вопросов, статистики
│   ├── catalog.py       # Форматирование карточек и списков
│   ├── lead.py          # Нормализация телефона, тексты форм
│   └── compare.py       # Форматирование таблицы сравнения
├── repositories/
│   ├── admin.py         # Запросы для заявок, вопросов, статистики
│   ├── analytics.py     # log_event()
│   ├── catalog.py
│   ├── leads.py
│   ├── faq.py
│   ├── franchise.py
│   ├── compare.py
│   └── users.py
├── states/
│   ├── lead.py          # LeadForm FSM (name, phone, time, city, confirm, exit_confirm)
│   ├── admin.py         # AdminStates.waiting_reply
│   └── faq.py           # UserQuestionForm.waiting_text
├── models/
│   └── db.py            # SQLAlchemy ORM модели
├── utils/
│   └── message_render.py # show_text_screen, show_photo_screen
└── parser/
    ├── parser.py        # Tilda Store API парсер
    └── sync.py          # Синхронизация каталога с БД
```

## Пользовательский контур

Все пользовательские сценарии работают через inline-кнопки. Навигация — редактирование текущего сообщения (`edit_message_text`), кроме двух исключений:

1. **Карточка с изображением** — `sendPhoto` + удаление предыдущего сообщения
2. **Форма FSM** — новое сообщение при старте формы, затем редактирование его же

Защита от двойного нажатия: `CallbackDebounceMiddleware` блокирует повторный callback с тем же `(user_id, message_id, callback_data)` в течение 1.2 сек.

### Основные флоу

- **Каталог** → категории → список (5/стр.) → карточка → запись
- **Заявка** (FSM): имя → телефон → [время/город] → подтверждение → отправка
- **FAQ** → темы → вопросы → ответ / задать свой вопрос
- **Франшиза** → условия / поддержка / FAQ / сравнение
- **Свободный текст** → предложение FAQ или вопрос оператору

## Админский контур

Вход: `/admin`. Доступ только по `ADMIN_TELEGRAM_ID`. Проверка на каждом handler и callback.

### Разделы

| Раздел | Функционал |
|--------|-----------|
| Заявки | Список с сортировкой (new → in_progress → done), карточка, смена статуса |
| Вопросы | Список (неотвеченные сначала), карточка, ответ пользователю через FSM, отметить отвеченным |
| Статистика | Метрики за сегодня / 7 дней / 30 дней / всё время |

Ответ на вопрос пользователя: admin переходит в `AdminStates.waiting_reply`, пишет текст, бот отправляет его пользователю через `bot.send_message`. Если отправка не удалась — статус не меняется, admin получает сообщение об ошибке.

## Аналитика

Таблица `analytics_events` собирает события действий пользователей. Логирование встроено в handlers через `repositories/analytics.log_event()`. Ошибки логирования не прерывают основной флоу.

## Деплой

```bash
# Запуск
docker-compose up -d

# Миграции запускаются автоматически при старте контейнера:
# alembic upgrade head && python -m bot
```

Переменные окружения (`.env`):
- `BOT_TOKEN` — токен Telegram бота
- `DATABASE_URL` — postgresql+asyncpg://...
- `ADMIN_TELEGRAM_ID` — Telegram ID администратора

## Ограничения текущей реализации

- Режим polling (не webhook)
- FSM storage — MemoryStorage (сбрасывается при перезапуске)
- Нет Redis (кеширование и FSM для multi-instance)
- Нет Sentry / внешнего мониторинга
- Нет шифрования персональных данных в БД
- Автозапуск парсера не настроен (только вручную через `/sync`)
