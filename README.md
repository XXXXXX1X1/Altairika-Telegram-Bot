# Altairika Telegram Bot

Telegram-бот для компании Altairika — выездного VR-кинотеатра для школ и мероприятий. Бот помогает клиентам изучить каталог VR-фильмов, оформить заявку, задать вопрос, узнать об условиях франшизы. Встроен AI-ассистент на базе OpenRouter. Для сотрудников предусмотрена панель администратора.

## Возможности

**Для пользователей**
- Каталог VR-фильмов с фильтрами по возрасту, длительности и предметам
- Карточки фильмов с постером, описанием и кнопкой перехода на сайт
- **AI-ассистент** — свободный текст: подбор фильмов, ответы по компании, франшизе, FAQ, сравнению с конкурентами
- Заявки: бронирование показа, запрос по франшизе, контакт
- Раздел FAQ — вопросы и ответы из базы данных
- Раздел «Франшиза» — питч, условия, поддержка, преимущества, FAQ
- Сравнение с конкурентами

**Для администратора** (команда `/admin`)
- Список заявок с сортировкой по статусу и дате, пагинация
- Карточка заявки, смена статуса (новая → в работе → закрыта)
- Список вопросов пользователей, фильтр непрочитанных
- Ответ пользователю прямо из панели (FSM-форма, редактирование на месте)
- Статистика: пользователи, заявки, вопросы, события — за сегодня / 7 дней / 30 дней / всё время
- Уведомления о новых заявках и вопросах с кнопкой быстрого перехода

## Стек

| Компонент | Версия |
|-----------|--------|
| Python | 3.11+ |
| aiogram | 3.13 |
| SQLAlchemy (async) | 2.0 |
| asyncpg | 0.30 |
| Alembic | 1.14 |
| PostgreSQL | 16 |
| openai SDK | — (для OpenRouter API) |
| Docker / docker-compose | — |

## Структура проекта

```
.
├── bot/
│   ├── handlers/
│   │   ├── start.py        # /start, главное меню
│   │   ├── admin.py        # /admin и панель администратора
│   │   ├── catalog.py      # Каталог фильмов
│   │   ├── lead.py         # FSM-формы заявок
│   │   ├── faq.py          # FAQ
│   │   ├── franchise.py    # Раздел франшизы
│   │   ├── compare.py      # Сравнение с конкурентами
│   │   ├── ai_movie.py     # AI-подбор фильмов (FSM AiPick)
│   │   └── freetext.py     # Точка входа AI-ассистента
│   ├── services/
│   │   ├── catalog.py, lead.py, compare.py, admin.py
│   │   ├── ai_client.py    # Клиент OpenRouter API
│   │   ├── ai_router.py    # Определение intent (эвристики + скоринг)
│   │   ├── ai_decision.py  # LLM-анализ сценария диалога
│   │   ├── ai_branch.py    # Логика продолжения/переключения ветки
│   │   ├── ai_catalog.py   # Поиск и ранжирование фильмов
│   │   ├── ai_memory.py    # Сессионная память (PostgreSQL)
│   │   ├── ai_context.py   # Сборка контекста для LLM
│   │   ├── ai_answer.py    # Полный pipeline: память → контекст → LLM
│   │   └── ai_movie_params.py  # AI-извлечение параметров подбора
│   ├── keyboards/          # Inline-клавиатуры
│   ├── repositories/       # Слой БД
│   ├── states/             # FSM-состояния
│   ├── models/db.py        # SQLAlchemy ORM модели
│   ├── middleware.py       # DbSession и CallbackDebounce middleware
│   ├── config.py           # Настройки из .env (pydantic-settings)
│   └── __main__.py         # Точка входа, регистрация роутеров
├── alembic/
│   └── versions/           # Миграции БД
├── scripts/
│   ├── entrypoint.sh       # Скрипт запуска: миграции → данные → бот
│   ├── run_parser.py       # Ручная синхронизация каталога с сайта
│   ├── seed_faq.py         # Начальные данные FAQ
│   ├── seed_franchise.py   # Контент франшизы с сайта
│   └── seed_compare.py     # Сравнение с конкурентами
├── docs/                   # Основная документация проекта
│   └── work/               # Рабочие и служебные документы
├── .env.example            # Шаблон переменных окружения
├── docker-compose.yml      # Основной compose: db + bot
├── Dockerfile
└── requirements.txt
```

---

## Быстрый старт (Docker)

### 1. Клонировать репозиторий

```bash
git clone https://github.com/XXXXXX1X1/Altairika-Telegram-Bot.git
cd Altairika-Telegram-Bot
```

### 2. Создать файл `.env`

```bash
cp .env.example .env
```

Заполнить обязательные переменные:

```env
BOT_TOKEN=1234567890:AABBCCDDEEFFaabbccddeeff   # Токен от @BotFather
DATABASE_URL=postgresql+asyncpg://bot:secret@localhost:5432/altairika
ADMIN_TELEGRAM_ID=123456789                       # Ваш Telegram user ID
POSTGRES_DB=altairika
POSTGRES_USER=bot
POSTGRES_PASSWORD=secret

# AI-ассистент (опционально — без ключа бот работает без AI)
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=google/gemini-2.0-flash-001
```

> Узнать свой `ADMIN_TELEGRAM_ID` можно через [@userinfobot](https://t.me/userinfobot).

---

### Режим 1 — Базовый (без парсера каталога)

Поднимает базу данных и бот. Каталог фильмов нужно заполнить вручную после старта.

```bash
docker compose up --build -d
```

**Что происходит автоматически:**

| Шаг | Что делается |
|-----|-------------|
| 1 | Поднимается PostgreSQL 16, ожидается готовность базы |
| 2 | Применяются все миграции Alembic (`alembic upgrade head`) |
| 3 | Заполняется FAQ (статические данные) |
| 4 | Заполняется раздел «Сравнение с конкурентами» |
| 5 | Синхронизируется контент франшизы с `altairika.ru` (если сайт доступен) |
| 6 | Запускается бот |

После старта заполнить каталог:

```bash
docker compose exec bot python scripts/run_parser.py
```

---

### Режим 2 — С парсером каталога (автоматически)

Поднимает базу, бот и однократно запускает парсер каталога с `altairika.ru`.

```bash
docker compose --profile with-parser up --build -d
```

Сервис `catalog_sync` запустится параллельно с ботом, выполнит миграции и синхронизирует каталог, затем завершится. При повторных запусках `docker compose up` без профиля `with-parser` парсер не запускается.

> Если `altairika.ru` недоступен — парсер завершится с ошибкой, но бот продолжит работу.

---

### Проверить логи

```bash
docker compose logs -f bot
```

Ожидаемый вывод при успешном старте:

```
=====================================================
  Altairika Bot — подготовка к запуску
=====================================================

[1/4] Применяем миграции базы данных...
      Миграции применены.

[2/4] Заполняем FAQ...
[3/4] Заполняем сравнение с конкурентами...
[4/4] Синхронизируем контент франшизы с altairika.ru...

=====================================================
  Запускаем бота...
=====================================================

INFO:bot:Bot started (polling)
```

### Остановить

```bash
docker compose down          # остановить контейнеры
docker compose down -v       # + удалить volume с данными БД
```

---

## Локальный запуск (без Docker)

### Требования

- Python 3.11+
- PostgreSQL 16 (запущен и доступен)

### Установка

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Настройка `.env`

```env
BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/altairika
ADMIN_TELEGRAM_ID=...
OPENROUTER_API_KEY=sk-or-...   # опционально
```

### Первый запуск (выполнить один раз)

```bash
alembic upgrade head              # Создать таблицы
python3 scripts/seed_faq.py       # FAQ
python3 scripts/seed_compare.py   # Сравнение с конкурентами
python3 scripts/seed_franchise.py # Контент франшизы (нужен интернет)
python3 scripts/run_parser.py     # Каталог фильмов (нужен интернет)
```

### Запуск бота

```bash
python3 -m bot
```

---

## AI-ассистент

Бот поддерживает свободный текст через AI. Если `OPENROUTER_API_KEY` не задан — бот работает только по кнопкам (заглушка для свободного текста).

### Поддерживаемые сценарии

| Сценарий | Пример запроса |
|----------|---------------|
| Подбор фильма | «Подберите фильм для 3 класса про космос» |
| Информация о фильме | «Расскажи про фильм Динозавры» |
| О компании | «Что такое Альтаирика?», «Как проходит сеанс?» |
| Франшиза | «Сколько стоит франшиза?», «Какая окупаемость?» |
| Сравнение | «Чем вы лучше VR Concept?» |
| FAQ | «Безопасен ли VR для детей?» |
| Заявка | «Хочу записаться» → переход в FSM-форму |

### Переменные AI

| Переменная | По умолчанию | Описание |
|------------|-------------|---------|
| `OPENROUTER_API_KEY` | — | Ключ OpenRouter (обязателен для AI) |
| `AI_MODEL` | `google/gemini-2.0-flash-001` | Модель через OpenRouter |
| `AI_MAX_TOKENS` | `600` | Максимум токенов в ответе |
| `AI_SESSION_TTL_MINUTES` | `30` | TTL сессии диалога (мин.) |

Подробнее: `docs/work/09_ai_assistant.md`

---

## Панель администратора

Доступ: команда `/admin`. Бот проверяет `ADMIN_TELEGRAM_ID` на каждом запросе.

| Раздел | Описание |
|--------|----------|
| Заявки | Список всех/новых заявок, карточка, смена статуса |
| Вопросы | Список всех/неотвеченных, FSM-форма ответа, отметить отвеченным |
| Статистика | 13 метрик за 4 периода: сегодня / 7 дней / 30 дней / всё время |

---

## Обновление данных

```bash
# Синхронизировать каталог фильмов с сайта
docker compose exec bot python3 scripts/run_parser.py

# Обновить контент франшизы
docker compose exec bot python3 scripts/seed_franchise.py

# Только просмотреть каталог без записи в БД
docker compose exec bot python3 scripts/run_parser.py --dry-run
```

---

## Миграции

```bash
# Применить все миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Создать новую миграцию
alembic revision --autogenerate -m "описание"
```

Файлы миграций: `alembic/versions/`

| Файл | Содержание |
|------|-----------|
| `0001_initial.py` | Все базовые таблицы |
| `0002_admin.py` | Поля ответов, `analytics_events` |
| `0003_ai_sessions.py` | Таблица `ai_sessions` для AI-памяти |

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|:---:|---------|
| `BOT_TOKEN` | да | Токен Telegram-бота от @BotFather |
| `DATABASE_URL` | да | Строка подключения к PostgreSQL (asyncpg) |
| `ADMIN_TELEGRAM_ID` | да | Telegram user ID администратора |
| `POSTGRES_DB` | да (Docker) | Имя базы данных |
| `POSTGRES_USER` | да (Docker) | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | да (Docker) | Пароль PostgreSQL |
| `OPENROUTER_API_KEY` | нет | Ключ OpenRouter для AI-ассистента |
| `AI_MODEL` | нет | Модель LLM (по умолчанию `google/gemini-2.0-flash-001`) |
| `AI_MAX_TOKENS` | нет | Лимит токенов ответа (по умолчанию `600`) |
| `AI_SESSION_TTL_MINUTES` | нет | TTL сессии диалога (по умолчанию `30`) |

---

## Разработка

### Порядок регистрации роутеров

Порядок `dp.include_router()` в `__main__.py` имеет значение:

1. `start_router` — команда `/start`
2. `admin_router` — команда `/admin` и панель
3. `lead_router`, `faq_router` — FSM-формы (приоритет перед остальными)
4. `catalog_router`, `franchise_router`, `compare_router`
5. `ai_movie_router` — перехватывает сообщения в состоянии `AiPick`
6. `freetext_router` — последним, catch-all для свободного текста

### Навигация

Вся навигация реализована через редактирование существующего сообщения (`edit_message_text` / `edit_message_caption`). Новое сообщение создаётся только:
- при ответе на команду `/start`
- при карточке с фото в AI-подборе
- при входе в FSM-форму
