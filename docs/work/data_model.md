# 04. Модель данных

## Общая схема

База данных: PostgreSQL. ORM: SQLAlchemy async. Миграции: Alembic.

### Таблицы

| Таблица | Назначение |
|---------|-----------|
| `categories` | Категории каталога фильмов |
| `catalog_items` | Фильмы каталога |
| `bot_users` | Пользователи бота |
| `leads` | Заявки (запись, франшиза, контакт) |
| `faq_topics` | Темы раздела FAQ |
| `faq_items` | Вопросы и ответы FAQ |
| `user_questions` | Вопросы пользователей оператору |
| `franchise_content` | Контент раздела франшизы |
| `competitors` | Конкуренты для сравнения |
| `comparison_parameters` | Параметры сравнения |
| `comparison_values` | Значения сравнения по конкурентам |
| `analytics_events` | Аналитика действий пользователей |

---

## categories

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| name | varchar(255) | Название категории |
| order | integer | Порядок отображения |
| item_count | integer | Количество активных фильмов |

## catalog_items

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| title | varchar(500) NOT NULL | Название фильма |
| description | text | Полное описание |
| short_description | text | Краткое описание |
| category_id | integer FK | Ссылка на categories.id |
| tags | text | JSON-массив тегов (возраст, длительность, тема, предмет, язык) |
| image_url | varchar(1000) | URL постера |
| price | varchar(500) | Цена (текст, может быть диапазоном) |
| duration | varchar(100) | Длительность (код: d5, d15, d30, d30p) |
| age_rating | varchar(20) | Возрастное ограничение |
| url | varchar(1000) | Ссылка на страницу на сайте |
| is_active | boolean | Активность позиции |
| updated_at | timestamptz | Дата последнего обновления |

Данные поступают из Tilda Store API через parser.

## bot_users

| Поле | Тип | Описание |
|------|-----|---------|
| telegram_user_id | bigint PK | Telegram user ID |
| username | varchar(255) | Telegram username (без @) |
| first_name | varchar(255) NOT NULL | Имя |
| language_code | varchar(10) | Язык Telegram |
| created_at | timestamptz | Первый визит |
| last_seen_at | timestamptz | Последний визит |

## leads

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| telegram_user_id | bigint NOT NULL | Кто оставил заявку |
| name | varchar(255) NOT NULL | Имя пользователя |
| phone | varchar(50) NOT NULL | Телефон (нормализован) |
| lead_type | enum(booking, franchise, contact) NOT NULL | Тип заявки |
| catalog_item_id | integer FK | Фильм (для booking) |
| preferred_time | varchar(255) | Удобное время (для booking) |
| city | varchar(255) | Город (для franchise) |
| status | enum(new, in_progress, done) | Статус обработки |
| created_at | timestamptz | Дата создания |
| updated_at | timestamptz | Дата последнего изменения |

## faq_topics

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| title | varchar(500) NOT NULL | Название темы |
| order | integer | Порядок |
| is_active | boolean | Видимость |

## faq_items

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| topic_id | integer FK NOT NULL | Тема |
| question | varchar(1000) NOT NULL | Текст вопроса |
| answer | text NOT NULL | Текст ответа |
| order | integer | Порядок внутри темы |
| is_active | boolean | Видимость |

## user_questions

Вопросы пользователей, адресованные оператору.

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| telegram_user_id | bigint NOT NULL | Кто задал вопрос |
| username | varchar(255) | Telegram username |
| text | text NOT NULL | Текст вопроса |
| is_answered | boolean | Отвечен ли вопрос |
| created_at | timestamptz | Дата вопроса |
| answered_at | timestamptz | Дата ответа |
| answered_by | bigint | Telegram ID администратора-ответчика |
| answer_text | text | Текст ответа |

## franchise_content

| Поле | Тип | Описание |
|------|-----|---------|
| section | enum(pitch, conditions, support, faq) PK | Раздел |
| content | text NOT NULL | Контент раздела |
| updated_at | timestamptz | Дата обновления |

## competitors, comparison_parameters, comparison_values

Используются для отображения таблицы сравнения с конкурентами.

**competitors:** id, name, website, is_active, updated_at

**comparison_parameters:** id, name, altairika_value, order

**comparison_values:** parameter_id + competitor_id (составной PK), value, rating(good|neutral|bad)

## analytics_events

События пользовательских действий для статистики.

| Поле | Тип | Описание |
|------|-----|---------|
| id | integer PK | — |
| telegram_user_id | bigint | Пользователь (nullable) |
| event_type | varchar(100) NOT NULL | Тип события |
| entity_type | varchar(50) | Тип связанного объекта |
| entity_id | integer | ID связанного объекта |
| payload_json | text | Дополнительный контекст (JSON) |
| created_at | timestamptz | Время события |

Индексы: `event_type`, `created_at`, `telegram_user_id`.

### Используемые event_type

| Событие | Когда записывается |
|---------|-------------------|
| `open_main_menu` | /start, возврат в главное меню |
| `open_catalog` | Открытие каталога |
| `open_catalog_item` | Открытие карточки фильма |
| `start_lead_form` | Запуск формы заявки |
| `submit_lead` | Успешная отправка заявки |
| `ask_question` | Пользователь задал вопрос оператору |
| `click_site_link` | Зарезервировано (переход на сайт) |

---

## Источники данных

| Данные | Источник | Способ загрузки |
|--------|---------|----------------|
| Каталог фильмов | Tilda Store API (altairika.ru/catalog_full) | Парсер + /sync |
| FAQ | Вручную | scripts/seed_faq.py |
| Франшиза | altairika.ru/franchise | scripts/seed_franchise.py |
| Конкуренты | Вручную | scripts/seed_compare.py |
| Заявки / вопросы / аналитика | Генерируются ботом | Автоматически |

---

## Миграции

| Файл | Содержание |
|------|-----------|
| `alembic/versions/0001_initial.py` | Полная начальная схема |
| `alembic/versions/0002_admin.py` | Новые поля user_questions + таблица analytics_events |
