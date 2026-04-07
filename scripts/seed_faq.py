"""
Наполняет таблицы faq_topics и faq_items тестовыми данными.

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/seed_faq.py

Запускать только один раз на чистой БД — при повторном запуске
проверяет наличие тем и пропускает уже существующие.
"""

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from bot.models.db import FaqItem, FaqTopic  # noqa: E402

FAQ_DATA = [
    {
        "title": "О сеансах и записи",
        "order": 1,
        "items": [
            {
                "question": "Как записаться на сеанс?",
                "answer": (
                    "Выберите фильм в каталоге и нажмите «Записаться». "
                    "Укажите имя и телефон — менеджер свяжется с вами для подтверждения времени."
                ),
                "order": 1,
            },
            {
                "question": "Сколько длится сеанс?",
                "answer": (
                    "Длительность зависит от выбранного фильма — от 10 до 35 минут. "
                    "Продолжительность указана в карточке каждого фильма."
                ),
                "order": 2,
            },
            {
                "question": "Можно ли записаться группой?",
                "answer": (
                    "Да. Мобильный VR-комплекс вмещает до 60 зрителей одновременно. "
                    "Для групповых заявок свяжитесь с нами через кнопку «Связаться»."
                ),
                "order": 3,
            },
            {
                "question": "С какого возраста можно смотреть VR-фильмы?",
                "answer": (
                    "Большинство фильмов подходят с 7 лет. "
                    "Возрастной рейтинг указан в карточке каждого фильма."
                ),
                "order": 4,
            },
        ],
    },
    {
        "title": "Цены и оплата",
        "order": 2,
        "items": [
            {
                "question": "Как формируется цена?",
                "answer": (
                    "Цена зависит от выбранного фильма и модели использования: "
                    "пакет показов (от 1 до 99+) или лицензия (1 год, 2 года, 5 лет, бессрочно). "
                    "Подробные цены указаны в карточке фильма."
                ),
                "order": 1,
            },
            {
                "question": "Есть ли скидки для школ?",
                "answer": (
                    "Да, для образовательных учреждений предусмотрены специальные условия. "
                    "Свяжитесь с нами — подберём оптимальный пакет."
                ),
                "order": 2,
            },
            {
                "question": "Какие способы оплаты доступны?",
                "answer": (
                    "Принимаем оплату по безналичному расчёту для юридических лиц "
                    "и банковской картой для физических лиц. "
                    "Менеджер уточнит детали при подтверждении заявки."
                ),
                "order": 3,
            },
        ],
    },
    {
        "title": "О франшизе",
        "order": 3,
        "items": [
            {
                "question": "Что входит в пакет франшизы?",
                "answer": (
                    "Оборудование, доступ к каталогу из 68+ фильмов, обучение персонала, "
                    "маркетинговые материалы и постоянная поддержка франчайзера. "
                    "Подробнее — в разделе «Франшиза»."
                ),
                "order": 1,
            },
            {
                "question": "Нужен ли опыт в образовании или технологиях?",
                "answer": (
                    "Нет. Мы обучаем с нуля: работа с оборудованием, "
                    "организация сеансов, привлечение клиентов."
                ),
                "order": 2,
            },
            {
                "question": "Как долго рассматривается заявка на франшизу?",
                "answer": (
                    "Мы связываемся с кандидатом в течение одного рабочего дня "
                    "после получения заявки."
                ),
                "order": 3,
            },
        ],
    },
]


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        added_topics = 0
        added_items = 0

        for topic_data in FAQ_DATA:
            result = await session.execute(
                select(FaqTopic).where(FaqTopic.title == topic_data["title"])
            )
            topic = result.scalar_one_or_none()

            if topic is None:
                topic = FaqTopic(
                    title=topic_data["title"],
                    order=topic_data["order"],
                    is_active=True,
                )
                session.add(topic)
                await session.flush()
                added_topics += 1
                print(f"  + Тема: {topic.title}")
            else:
                print(f"  ~ Тема уже есть: {topic.title}")

            for item_data in topic_data["items"]:
                result = await session.execute(
                    select(FaqItem).where(
                        FaqItem.topic_id == topic.id,
                        FaqItem.question == item_data["question"],
                    )
                )
                item = result.scalar_one_or_none()
                if item is None:
                    session.add(FaqItem(
                        topic_id=topic.id,
                        question=item_data["question"],
                        answer=item_data["answer"],
                        order=item_data["order"],
                        is_active=True,
                    ))
                    added_items += 1

        await session.commit()

    await engine.dispose()
    print(f"\nГотово: добавлено тем — {added_topics}, вопросов — {added_items}.")


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL не задан.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(seed(url))
