# 12. Профессиональный ревью архитектуры и кода

> Независимый взгляд. Без скидок на MVP и «потом доделаем».

---

## Общая оценка

**Уровень: крепкий средний+.** Для проекта «бот для малого бизнеса» — выше среднего. Для production-системы с ростом — есть серьёзные долги. Ниже — конкретика.

---

## Что сделано хорошо

### Архитектурный слой

**Чёткое разделение handlers / services / repositories.** Это главное. Handlers только оркестрируют — не лезут в SQL, не форматируют сами. Services содержат бизнес-логику. Repositories — чистый слой БД. Это редкость в Telegram-ботах, где обычно всё смешано в одном файле.

**AI-слой изолирован правильно.** Семь отдельных модулей (`ai_client`, `ai_router`, `ai_decision`, `ai_branch`, `ai_catalog`, `ai_memory`, `ai_context`, `ai_answer`, `ai_movie_params`) с чёткой ответственностью. Новый разработчик разберётся без расшифровки.

**Intent routing — грамотное решение.** Двухуровневая система (LLM с confidence threshold + эвристики как fallback) — это зрелый подход. Не «всё через LLM» и не «всё через if/else». Экономит деньги и работает предсказуемо.

**Dual-model подход** (дешёвая ROUTING_MODEL + качественная AI_MODEL) — правильная оптимизация стоимости. Служебные JSON-вызовы не требуют GPT-4-уровня.

**Fallback без падений.** `call_llm()` возвращает `None` при любой ошибке, никогда не бросает исключение наружу. `generate_answer()` обёрнут в try/except в handler. UX не ломается при недоступности API.

**Контекстная минимальность.** Каждый intent получает только нужные данные — не весь каталог, не весь FAQ. Это и дешевле, и точнее, и снижает галлюцинации.

**Парсер каталога — нормальное решение.** Используют официальный Tilda Store API, а не скрейпинг DOM. Семафор на 8 параллельных запросов при enrich. Обработка пагинации.

**Alembic для миграций** — без вопросов. Откат работает. Версии именованы.

---

## Что вызывает вопросы

### Критично для production

**1. MemoryStorage для FSM.**

```python
dp = Dispatcher(storage=MemoryStorage())
```

При перезапуске бота все активные FSM-сессии (формы заявок, подбор фильмов) теряются. Пользователь в середине формы получает «сломанный» диалог. Для production — Redis или PostgreSQL storage. Это не «потом» — это реальная потеря лидов.

**2. Один администратор жёстко в env.**

```python
ADMIN_TELEGRAM_ID=123456789
```

Нет таблицы администраторов, нет ролей. Добавить второго сотрудника — нельзя без деплоя. Для любого реального бизнеса это ограничение проявится через месяц.

**3. Нет auto-expiry AI-сессий.**

`expires_at` в таблице `ai_sessions` заполняется, но никогда не проверяется и не очищается. Таблица будет расти бесконечно. Для тысячи пользователей — несущественно, для десятков тысяч — проблема. Нужен либо cron-job, либо проверка при `load_state`.

**4. Кеш `company_knowledge` — невалидируемый.**

```python
_knowledge_cache: str | None = None
```

Файл `docs/work/10_company_knowledge.md` загружается один раз. Для обновления контента нужен перезапуск всего бота. Нет команды `/reload_knowledge` для администратора. Неудобно в эксплуатации.

### Архитектурные замечания

**5. `ai_movie.py` — самый тяжёлый файл (768 строк).**

Там и FSM-логика, и UI-рендеринг карточек, и управление снапшотами, и вычисление заголовков. Функция `run_ai_pick_flow()` — 150 строк. Это уже God Function. При следующем изменении логики подбора придётся распутывать.

Как правильнее: отдельный `AiPickService` для бизнес-логики, handler только для Telegram-специфики.

**6. Дублирование логики определения параметров.**

`extract_params()` в `ai_catalog.py` и `extract_movie_params()` в `ai_movie_params.py` делают схожее — извлекают параметры из текста. Второй — AI-версия первого. Но в коде они вызываются в разных местах, иногда оба сразу, потом результаты объединяются. Это запутывает.

Лучше один entry point: `ai_movie_params.py` вызывает `ai_catalog.extract_params()` как fallback внутри себя — что уже так и сделано. Но снаружи это неочевидно: в `ai_movie.py` дёргают оба напрямую.

**7. `decide_next_intent()` vs `analyze_dialog_scenario()` — неясный приоритет.**

В `freetext.py`:
```python
decision = await analyze_dialog_scenario(user_text, ai_state)
if not decision or decision.get("confidence", 0.0) < 0.45:
    decision = decide_next_intent(user_text, ai_state)
```

В `ai_movie.py`:
```python
decision = await analyze_dialog_scenario(user_text, decision_state)
if not decision or decision.get("confidence", 0.0) < 0.45:
    decision = decide_next_intent(user_text, decision_state)
```

Дублирование паттерна в двух местах. Это должна быть одна функция `get_intent_decision()` с этой логикой внутри.

**8. Смешение двух форматов state.**

В `ai_sessions.state_json` ключ хранится и как `_active_intent` (с underscore) и как `active_intent` (без). В `ai_branch.py`:

```python
current_intent = state.get("_active_intent") or state.get("active_intent")
```

Это защитный код от inconsistency внутри самого проекта. Технический долг — нужно выбрать один формат и мигрировать.

**9. Нет обработки одновременных запросов одного пользователя.**

Пользователь быстро нажимает кнопку два раза → два параллельных запроса к `ai_sessions` → race condition при `save_session`. В SQLAlchemy без транзакции с SELECT FOR UPDATE второй запрос перезапишет первый. `CallbackDebounceMiddleware` помогает с кнопками (1.2 сек), но не защищает полностью.

### Качество кода

**10. Magic numbers и magic strings без констант.**

По коду разбросаны:
```python
if len(caption) > 1024:          # ai_movie.py:395
if len(caption) > 1024:          # ai_movie.py:421
if score >= 0.82:                 # ai_catalog.py:195
if score >= 0.38:                 # ai_catalog.py:230
confidence < 0.45                 # freetext.py + ai_movie.py
```

Эти числа — важные пороги. Сейчас изменить один надо в трёх местах. Должны быть именованными константами: `TELEGRAM_CAPTION_LIMIT = 1024`, `TITLE_MATCH_CONFIDENT_SCORE = 0.82` и т.д.

**11. Логирование без структуры.**

```python
logger.info("LLM вызов: модель=%s prompt_len=%d", settings.AI_MODEL, len(system_prompt))
logger.info("user=%d intent=%s action=%s text=%r", message.from_user.id, intent, action, user_text[:80])
```

Это хорошо — логи есть. Но нет request_id для трассировки цепочки вызовов одного запроса через 4 разных модуля. В продакшене непросто понять: «этот LLM-вызов — от какого пользователя и какого сообщения?»

**12. `bot/utils/message_render.py` — правильная утилита.**

`show_text_screen()` и `show_photo_screen()` — хорошая абстракция над edit/send. Убирает дублирование попытки edit + fallback на send. Редко видно в telegram-ботах — плюс.

**13. `CallbackDebounceMiddleware` — нестандартное, но полезное решение.**

Защита от двойных нажатий на уровне middleware — правильное место. Реализация через middleware вместо флагов в handler'ах — грамотно.

---

## Что отсутствует для production

| Что | Почему важно |
|-----|-------------|
| Redis для FSM storage | Перезапуск без потери форм |
| Webhook вместо polling | Меньше latency, меньше нагрузки на Telegram |
| Healthcheck endpoint | Для мониторинга и Docker health |
| Structured logging (JSON) | Для Grafana/Loki/CloudWatch |
| Sentry или аналог | Алерты на ошибки в реальном времени |
| Ротация логов | Сейчас stdout без ограничений |
| Rate limiting пользователей | Нет защиты от спама в AI |
| AI-аналитика (какие intents, ошибки) | Нельзя улучшить то, что не измеряешь |
| Multi-admin поддержка | Неизбежно понадобится |
| Auto-expiry сессий | Рост таблицы ai_sessions |

---

## Итоговая оценка по категориям

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| Архитектура | 7/10 | Слои разделены, AI-модули изолированы, но fat handler в ai_movie.py |
| Качество AI-решения | 8/10 | Dual-model, confidence fallback, минимальный контекст — всё правильно |
| Устойчивость | 5/10 | MemoryStorage, нет rate limiting, нет мониторинга |
| Код-стиль | 7/10 | Читаемый, но magic numbers и дублирование паттернов |
| Масштабируемость | 5/10 | Один admin, нет Redis, polling режим |
| Документация | 9/10 | Редко видно такое качество в pet/small projects |

**Средняя: 6.8/10** — добротный проект для MVP и первого запуска. Для серьёзной эксплуатации нужен следующий цикл работы.

---

## Приоритет исправлений

### Горящее (до первого реального трафика)

1. **Redis/PG storage для FSM** — иначе будете терять заявки
2. **Rate limiting AI-запросов** — один спамер сожжёт весь бюджет OpenRouter

### Важное (в ближайший спринт)

3. **Auto-expiry ai_sessions** — простой cron или проверка в `load_state`
4. **Multi-admin** — хотя бы таблица `admins` с одним полем
5. **Рефакторинг `ai_movie.py`** — выделить `AiPickService`

### Технический долг (можно отложить)

6. Именованные константы для порогов
7. Единый формат `active_intent` vs `_active_intent`
8. `get_intent_decision()` вместо дублирования паттерна
9. Request ID для трассировки в логах
10. Кеш базы знаний с инвалидацией
