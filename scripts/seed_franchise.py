"""
Подтягивает разделы франшизы с altairika.ru/franchise и сохраняет в БД.

Использование:
    python3 scripts/seed_franchise.py
"""

import asyncio
import html
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from bot.models.db import FranchiseContent, FranchiseSection  # noqa: E402

SOURCE_URL = "https://altairika.ru/franchise"


def _normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    value = value.replace("﻿", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _html_to_text(fragment: str) -> str:
    fragment = fragment.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    fragment = re.sub(r"</li>\s*", "\n", fragment)
    fragment = re.sub(r"<li[^>]*>\s*", "• ", fragment)
    fragment = re.sub(r"</?(ul|ol)[^>]*>", "", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    lines = [_normalize_text(line) for line in fragment.splitlines()]
    return "\n".join(line for line in lines if line)


def _normalize_html(html_text: str) -> str:
    normalized = html.unescape(html_text)
    normalized = normalized.replace("\xa0", " ").replace("﻿", "")
    return normalized


def _extract_title_text_pair(html_text: str, title: str) -> tuple[str, str] | None:
    normalized = _normalize_html(html_text)
    pattern = re.compile(
        rf">{re.escape(title)}</h3>.*?"
        r"field='tn_text_[^']+'>(.*?)</div>",
        flags=re.S,
    )
    match = pattern.search(normalized)
    if not match:
        return None
    description = _html_to_text(match.group(1))
    if not description:
        return None
    return title, description


def _extract_metric_value(html_text: str, label: str) -> str | None:
    normalized = _normalize_html(html_text)
    text = _html_to_text(normalized)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if label not in lines:
        return None
    index = lines.index(label)
    window_start = max(0, index - 3)
    candidates = lines[window_start:index]
    for value in reversed(candidates):
        if any(char.isdigit() for char in value):
            return value
    return None


def build_conditions_content(html_text: str) -> str:
    text = _html_to_text(_normalize_html(html_text))
    payback = _extract_metric_value(html_text, "Средний срок окупаемости") or "12-18 мес."
    fee = _extract_metric_value(html_text, "средний размер паушального взноса") or "900 тыс. ₽"

    income_match = re.search(r"доход от\s*([0-9 ]+)\s*₽", text, flags=re.I)
    income = f"от {income_match.group(1).strip()} ₽" if income_match else "от 300 000 ₽"

    content = [
        "<b>💼 Условия и инвестиции</b>",
        "",
        "Франшиза рассчитана на мобильный формат без обязательного отдельного помещения на старте.",
        "",
        "<b>📊 Ключевые ориентиры по странице Altairika</b>",
        f"• Средний срок окупаемости: {html.escape(payback)}",
        f"• Средний ежемесячный доход: {html.escape(income)}",
        f"• Средний размер паушального взноса: {html.escape(fee)}",
        "",
        "<b>🏙️ Для малых городов</b>",
        "• Подходит для городов с населением от 100 000 до 250 000 человек",
        "• Потенциальный средний доход: до 150 000 ₽ в месяц",
        "• Ориентир по паушальному взносу: 850 000 ₽",
        "",
        "<b>🚀 Как выглядит запуск</b>",
        "1. Получаете презентацию и обсуждаете формат работы под ваш город.",
        "2. Проходите обучение и готовите оборудование к старту.",
        "3. Заключаете договор, оплачиваете паушальный взнос и запускаете показы.",
        "",
        "<b>✅ Что важно на старте</b>",
        "• Эксклюзив на территорию: вы становитесь единственным представителем в своём регионе",
        "• Можно стартовать без дополнительных затрат на интернет-рекламу",
        "• Оборудование можно получить через Altairika в формате «под ключ»",
    ]
    return "\n".join(content)


def build_support_content(html_text: str) -> str:
    sections = [
        (
            "Поддержка",
            "🛠️",
            _extract_title_text_pair(html_text, "Поддержка"),
            "Помощь на старте и в ежедневной работе: сопровождение партнёра, ответы на вопросы, "
            "подключение к внутренним чатам и поддержка без внутренней конкуренции в вашем регионе.",
        ),
        (
            "Аналитика",
            "📈",
            _extract_title_text_pair(html_text, "Аналитика"),
            "Инструменты для контроля показов и бизнеса: статистика, понятные показатели и возможность "
            "видеть, как развивается проект и где усиливать результат.",
        ),
        (
            "Продвижение",
            "📣",
            _extract_title_text_pair(html_text, "Продвижение"),
            "Готовые материалы для запуска и продаж: маркетинговая упаковка, сайт, рекомендации по "
            "продвижению и инструменты, которые помогают быстрее выходить на клиентов.",
        ),
        (
            "Обучение и развитие",
            "🎓",
            _extract_title_text_pair(html_text, "Обучение и развитие"),
            "Обучение работе с продуктом и росту бизнеса: база знаний, академия, встречи с экспертами "
            "и практические материалы для уверенного запуска.",
        ),
    ]

    content = [
        "<b>📦 Что входит в пакет</b>",
        "",
        "Франшиза Altairika включает не только контент и оборудование, но и полный набор инструментов для запуска и роста.",
    ]

    for title, icon, extracted, fallback in sections:
        description = extracted[1] if extracted else fallback
        content.append("")
        content.append(f"<b>{icon} {html.escape(title)}</b>")
        content.append(html.escape(description))

    return "\n".join(content)


def extract_franchise_faq(html_text: str) -> list[tuple[str, str]]:
    block_match = re.search(
        r'<a name="faq"[^>]*>.*?<div id="rec1728552271".*?</div>\s*<script>t_onReady\(function\(\) \{t_onFuncLoad\(\'t668_init\'',
        html_text,
        flags=re.S,
    )
    if not block_match:
        raise RuntimeError("Не удалось найти FAQ-блок франшизы на странице.")

    block = block_match.group(0)
    questions = re.findall(
        r'field="li_title__[^"]+"[^>]*>\s*<span[^>]*>(.*?)</span>',
        block,
        flags=re.S,
    )
    answers = re.findall(
        r'field="li_descr__[^"]+"[^>]*>(.*?)</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>',
        block,
        flags=re.S,
    )

    if not questions or not answers or len(questions) != len(answers):
        raise RuntimeError("Не удалось корректно извлечь вопросы и ответы по франшизе.")

    items: list[tuple[str, str]] = []
    for question_html, answer_html in zip(questions, answers, strict=True):
        question = _html_to_text(question_html)
        answer = _html_to_text(answer_html)
        if question and answer:
            items.append((question, answer))
    return items


def build_faq_content(items: list[tuple[str, str]]) -> str:
    parts = ["<b>❓ Частые вопросы по франшизе</b>"]
    for index, (question, answer) in enumerate(items, start=1):
        parts.append(f"<b>{index}. {html.escape(question)}</b>\n{html.escape(answer)}")
    return "\n\n".join(parts)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8", errors="ignore")


async def seed(database_url: str) -> None:
    html_text = fetch_html(SOURCE_URL)
    faq_items = extract_franchise_faq(html_text)
    sections = {
        FranchiseSection.conditions: build_conditions_content(html_text),
        FranchiseSection.support: build_support_content(html_text),
        FranchiseSection.faq: build_faq_content(faq_items),
    }

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        actions: dict[FranchiseSection, str] = {}
        for section, content in sections.items():
            result = await session.execute(
                select(FranchiseContent).where(FranchiseContent.section == section)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = FranchiseContent(section=section, content=content)
                session.add(row)
                actions[section] = "создан"
            else:
                row.content = content
                actions[section] = "обновлён"

        await session.commit()

    await engine.dispose()
    print(
        "Разделы франшизы обновлены: "
        f"conditions={actions[FranchiseSection.conditions]}, "
        f"support={actions[FranchiseSection.support]}, "
        f"faq={actions[FranchiseSection.faq]} ({len(faq_items)} вопросов)."
    )


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL не задан.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(seed(url))
