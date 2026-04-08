"""
Наполняет таблицы competitors, comparison_parameters, comparison_values
примерными данными на основе открытых источников.

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/seed_compare.py

При повторном запуске — пропускает уже существующих конкурентов и параметры.
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

from bot.models.db import (  # noqa: E402
    ComparisonParameter,
    ComparisonRating,
    ComparisonValue,
    Competitor,
)

# ---------------------------------------------------------------------------
# Данные конкурентов
# ---------------------------------------------------------------------------

COMPETITORS = [
    {"name": "VR Concept", "website": "vrconcept.ru"},
    {"name": "Vizerra", "website": "vizerra.com"},
]

# ---------------------------------------------------------------------------
# Параметры сравнения
# ---------------------------------------------------------------------------
# Структура: параметр → altairika_value → [(competitor_name, value, rating)]

PARAMETERS = [
    {
        "name": "Лет на рынке",
        "altairika": "14+ лет",
        "order": 1,
        "values": [
            ("VR Concept", "~7 лет", ComparisonRating.neutral),
            ("Vizerra", "~10 лет", ComparisonRating.neutral),
        ],
    },
    {
        "name": "Размер каталога",
        "altairika": "135 на главной странице, 150+ в разделе франшизы",
        "order": 2,
        "values": [
            ("VR Concept", "до 30 сцен", ComparisonRating.bad),
            ("Vizerra", "~20 объектов", ComparisonRating.bad),
        ],
    },
    {
        "name": "Целевая аудитория",
        "altairika": "Школы, планетарии, семьи",
        "order": 3,
        "values": [
            ("VR Concept", "Корпоративный сектор", ComparisonRating.neutral),
            ("Vizerra", "Музеи, туризм", ComparisonRating.neutral),
        ],
    },
    {
        "name": "Мобильный формат",
        "altairika": "Мобильный планетарий 5 м, до 60 зрителей",
        "order": 4,
        "values": [
            ("VR Concept", "Только стационарные инсталляции", ComparisonRating.bad),
            ("Vizerra", "Нет мобильных решений", ComparisonRating.bad),
        ],
    },
    {
        "name": "Франшиза",
        "altairika": "Полный пакет: оборудование + обучение + поддержка",
        "order": 5,
        "values": [
            ("VR Concept", "Франшизы нет", ComparisonRating.bad),
            ("Vizerra", "Лицензионная модель (без оборудования)", ComparisonRating.neutral),
        ],
    },
    {
        "name": "Партнёры",
        "altairika": "12 стран, 3 млн зрителей",
        "order": 6,
        "values": [
            ("VR Concept", "Преимущественно РФ", ComparisonRating.neutral),
            ("Vizerra", "РФ и СНГ", ComparisonRating.neutral),
        ],
    },
    {
        "name": "Поддержка клиентов",
        "altairika": "Персональный менеджер + методические материалы",
        "order": 7,
        "values": [
            ("VR Concept", "Техподдержка по заявкам", ComparisonRating.neutral),
            ("Vizerra", "Онлайн-документация", ComparisonRating.bad),
        ],
    },
]


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        # Конкуренты
        comp_map: dict[str, Competitor] = {}
        for c in COMPETITORS:
            result = await session.execute(
                select(Competitor).where(Competitor.name == c["name"])
            )
            comp = result.scalar_one_or_none()
            if comp is None:
                comp = Competitor(name=c["name"], website=c.get("website"), is_active=True)
                session.add(comp)
                await session.flush()
                print(f"  + Конкурент: {comp.name}")
            else:
                print(f"  ~ Уже есть: {comp.name}")
            comp_map[comp.name] = comp

        # Параметры и значения
        added_params = added_vals = 0
        for p in PARAMETERS:
            result = await session.execute(
                select(ComparisonParameter).where(ComparisonParameter.name == p["name"])
            )
            param = result.scalar_one_or_none()
            if param is None:
                param = ComparisonParameter(
                    name=p["name"],
                    altairika_value=p["altairika"],
                    order=p["order"],
                )
                session.add(param)
                await session.flush()
                added_params += 1

            for comp_name, value, rating in p["values"]:
                comp = comp_map.get(comp_name)
                if not comp:
                    continue
                result = await session.execute(
                    select(ComparisonValue).where(
                        ComparisonValue.parameter_id == param.id,
                        ComparisonValue.competitor_id == comp.id,
                    )
                )
                val = result.scalar_one_or_none()
                if val is None:
                    session.add(ComparisonValue(
                        parameter_id=param.id,
                        competitor_id=comp.id,
                        value=value,
                        rating=rating,
                    ))
                    added_vals += 1

        await session.commit()

    await engine.dispose()
    print(f"\nГотово: параметров добавлено — {added_params}, значений — {added_vals}.")


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL не задан.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(seed(url))
