# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Статус проекта

Проект находится в рабочем состоянии: реализован Telegram-бот на `aiogram`, настроены PostgreSQL и Alembic, есть ручной парсер каталога и сиды для FAQ/сравнения. Актуальная документация лежит в `docs/`.

## Документация

Перед любой работой с кодом читай основную документацию в `docs/`:

- `docs/01_product_brief.md` — цели, персоны, скоуп
- `docs/02_user_scenarios.md` — пользовательские флоу (источник истины для UX-логики)
- `docs/03_ux_design.md` — устройство всех экранов, правила навигации, тон бота
- `docs/04_architecture.md` — стек, компоненты, структура модулей, AI-флоу
- `docs/05_roadmap.md` — дорожная карта по фазам, статус реализации

Рабочая и служебная документация в `docs/work/`:

- `docs/work/data_model.md` — все сущности БД с полями
- `docs/work/ai_assistant.md` — AI-ассистент: реализация, модули, сценарии, трейс диалога
- `docs/work/ai_service.md` — конфигурация AI: промпты, модели, формат контекста
- `docs/work/code_review.md` — результаты код-ревью
- `docs/work/architecture_review.md` — профессиональный ревью архитектуры
- `docs/work/workflow.md` — workflow разработки с Claude Code
- `docs/work/company_knowledge.md` — **[СЛУЖЕБНЫЙ]** база знаний компании (читается ботом)
- `docs/work/market_research.md` — **[СЛУЖЕБНЫЙ]** исследование конкурентов (читается ботом)

## Стек и ключевые решения

- **Python 3.11+**, **aiogram 3.x** (async, FSM, текущий режим запуска: polling)
- **PostgreSQL** + **SQLAlchemy (async)** + **Alembic** для миграций
- **Docker + docker-compose** (бот + PostgreSQL)
- **AI-ассистент** через OpenRouter (intent routing + генерация ответов); свободный текст → AI pipeline
- Каталог загружается автопарсером через Tilda Store API со страницы `https://altairika.ru/catalog_full`.

## Структура модулей (планируемая)

```
bot/
├── handlers/       # CommandHandler, CallbackQueryHandler, MessageHandler
├── services/       # Бизнес-логика: catalog, leads, franchise, faq, compare
├── repositories/   # Слой БД: catalog, leads, faq, users
├── keyboards/      # Inline-клавиатуры
├── states/         # FSM-состояния форм
├── models/         # Pydantic / dataclass модели
└── config.py       # Загрузка из .env
```

## Ключевые UX-правила (обязательно соблюдать)

1. **Навигация через редактирование сообщения** (`edit_message_text` / `edit_message_caption`), не через отправку нового — кроме двух случаев: карточка с изображением и диалоговая форма (FSM).
2. **Карточка с `image_url`** → `sendPhoto` с caption. Если caption > 1024 символов — усечь + кнопка «Читать подробнее».
3. **Форма сбора контакта** всегда имеет шаг подтверждения перед сохранением.
4. **Свободный текст** вне активной формы → предложить FAQ или «написать вопрос оператору». Никакого разбора намерений.
5. **Пустые поля** карточки не отображаются (нет «Цена: не указана»).

## Соглашения по документации

В `docs/` используются маркеры:
- `[Решение]` — проектное решение, принятое по умолчанию
- `[Гипотеза]` — требует проверки до или после запуска
- `[Требует данных]` — нельзя финализировать без данных с сайта / от заказчика
- `[Ядро]` — обязательная часть
- `[Улучшение]` — желательно, но не блокирует запуск
