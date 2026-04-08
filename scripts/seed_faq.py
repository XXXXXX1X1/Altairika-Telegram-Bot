"""
Наполняет общий FAQ актуальными вопросами Altairika.

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/seed_faq.py
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
        "title": "О сеансах",
        "order": 1,
        "items": [
            {
                "question": "Как проходит сеанс виртуальной реальности?",
                "answer": (
                    "Сеанс проходит в четыре этапа: подготовка площадки, инструктаж, синхронный просмотр фильма "
                    "в VR-очках и короткий блиц-урок после просмотра. После фильма дети обсуждают увиденное "
                    "и отвечают на вопросы по теме."
                ),
                "order": 1,
            },
            {
                "question": "Сколько зрителей могут смотреть фильм одновременно?",
                "answer": (
                    "Altairika проводит синхронные показы до 60 зрителей одновременно. "
                    "Это удобно для школьных классов, групп в лагере и детских мероприятий."
                ),
                "order": 2,
            },
            {
                "question": "Где можно провести сеанс?",
                "answer": (
                    "Для сеанса не нужны особые условия. Его можно провести в школе, детском саду, "
                    "летнем лагере, музее, на празднике или дома. Оператор привозит с собой всё необходимое оборудование."
                ),
                "order": 3,
            },
            {
                "question": "Что нужно подготовить для показа?",
                "answer": (
                    "Нужна просторная проветриваемая площадка со стульями или креслами для зрителей. "
                    "Остальное привозит оператор: VR-очки, планшет для управления, Wi-Fi роутер и аудиосистему."
                ),
                "order": 4,
            },
            {
                "question": "Безопасен ли VR-сеанс для детей?",
                "answer": (
                    "Сеанс виртуальной реальности безопасен и не вредит зрению. "
                    "Очки дезинфицируются перед каждым показом, а операторы проходят обучение по работе с оборудованием и детьми."
                ),
                "order": 5,
            },
        ],
    },
    {
        "title": "Для школ и родителей",
        "order": 2,
        "items": [
            {
                "question": "Подходит ли Altairika для школ?",
                "answer": (
                    "Да. Для учителей предусмотрен готовый учебный модуль "
                    "длительностью до 30 минут можно провести прямо в классе. К фильмам подготовлены методические рекомендации "
                    "и тесты для проверки знаний."
                ),
                "order": 1,
            },
            {
                "question": "Чем такие фильмы полезны ребёнку?",
                "answer": (
                    "VR-формат делает обучение более наглядным и вовлекающим. "
                    "Ребёнок не просто слушает, а буквально погружается в тему: космос, природу, историю, географию и науку."
                ),
                "order": 2,
            },
            {
                "question": "Можно ли пригласить Altairika на день рождения или семейное событие?",
                "answer": (
                    "Да. Это необычный сюрприз или подарок, "
                    "который можно провести не выходя из дома или на семейном мероприятии."
                ),
                "order": 3,
            },
            {
                "question": "С какого возраста подходят фильмы?",
                "answer": (
                    "Возрастной вход начинается от 4+. "
                    "У каждого фильма в каталоге также есть свой возрастной рейтинг, поэтому программу можно подобрать под конкретную аудиторию."
                ),
                "order": 4,
            },
        ],
    },
    {
        "title": "Запись и организация",
        "order": 3,
        "items": [
            {
                "question": "Как организовать показ?",
                "answer": (
                    "Оставьте заявку, после чего с вами согласуют дату, время и условия проведения сеанса. "
                    "Перед мероприятием вы получите дополнительные материалы, а в день показа партнёр привезёт оборудование и подготовит его к работе."
                ),
                "order": 1,
            },
            {
                "question": "Сколько времени занимает подготовка оборудования?",
                "answer": (
                    "Настройка оборудования занимает не более 20 минут, "
                    "после чего сеанс можно начинать."
                ),
                "order": 2,
            },
            {
                "question": "Как выбрать фильм?",
                "answer": (
                    "Фильмы можно посмотреть в каталоге и выбрать по возрасту, длительности и теме. "
                    "В карточке каждого фильма указаны описание, возраст, длительность и другая полезная информация."
                ),
                "order": 3,
            },
            {
                "question": "Как с вами связаться для уточнения деталей?",
                "answer": (
                    "Оставьте заявку через кнопку «Связаться с нами» или через форму записи в каталоге. "
                    "После этого менеджер свяжется с вами и поможет подобрать подходящий формат."
                ),
                "order": 4,
            },
        ],
    },
]


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        added_topics = 0
        updated_topics = 0
        added_items = 0
        updated_items = 0
        disabled_items = 0

        topic_titles = {topic["title"] for topic in FAQ_DATA}

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
                topic.order = topic_data["order"]
                topic.is_active = True
                updated_topics += 1
                print(f"  ~ Тема обновлена: {topic.title}")

            expected_questions = {item["question"] for item in topic_data["items"]}

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
                else:
                    item.answer = item_data["answer"]
                    item.order = item_data["order"]
                    item.is_active = True
                    updated_items += 1

            result = await session.execute(
                select(FaqItem).where(FaqItem.topic_id == topic.id)
            )
            existing_items = list(result.scalars())
            for item in existing_items:
                if item.question not in expected_questions and item.is_active:
                    item.is_active = False
                    disabled_items += 1

        result = await session.execute(select(FaqTopic))
        for topic in list(result.scalars()):
            if topic.title not in topic_titles:
                topic.is_active = False

        await session.commit()

    await engine.dispose()
    print(
        "\nГотово: "
        f"тем добавлено — {added_topics}, "
        f"тем обновлено — {updated_topics}, "
        f"вопросов добавлено — {added_items}, "
        f"вопросов обновлено — {updated_items}, "
        f"вопросов отключено — {disabled_items}."
    )


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL не задан.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(seed(url))
