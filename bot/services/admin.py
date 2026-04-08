# Форматирование данных для панели администратора.

import math
from datetime import datetime

from bot.models.db import Lead, LeadStatus, LeadType, UserQuestion
from bot.repositories.admin import LEADS_PER_PAGE, QUESTIONS_PER_PAGE

_LEAD_TYPE_LABELS = {
    LeadType.booking: "Запись",
    LeadType.franchise: "Франшиза",
    LeadType.contact: "Контакт",
}

_LEAD_STATUS_LABELS = {
    LeadStatus.new: "Новая",
    LeadStatus.in_progress: "В работе",
    LeadStatus.done: "Закрыта",
}

_PERIOD_LABELS = {
    "today": "Сегодня",
    "7d": "7 дней",
    "30d": "30 дней",
    "all": "Всё время",
}


def lead_type_label(lt: LeadType) -> str:
    return _LEAD_TYPE_LABELS.get(lt, str(lt))


def lead_status_label(ls: LeadStatus) -> str:
    return _LEAD_STATUS_LABELS.get(ls, str(ls))


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone() if dt.tzinfo else dt
    return local.strftime("%d.%m.%Y %H:%M")


def _user_display(q: UserQuestion) -> str:
    return f"@{q.username}" if q.username else f"ID {q.telegram_user_id}"


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------

def format_leads_list(leads: list[Lead], page: int, total: int) -> str:
    pages = max(1, math.ceil(total / LEADS_PER_PAGE))
    start = (page - 1) * LEADS_PER_PAGE + 1
    lines = [f"<b>Заявки</b>  (стр. {page}/{pages}, всего {total})\n"]
    for i, lead in enumerate(leads, start=start):
        typ = lead_type_label(lead.lead_type)
        status = lead_status_label(lead.status)
        lines.append(f"{i}. {typ} | {lead.name} | {lead.phone} | {_fmt_dt(lead.created_at)} | {status}")
    return "\n".join(lines)


def format_lead_card(lead: Lead) -> str:
    parts = [
        f"<b>Заявка #{lead.id}</b>",
        f"Тип: {lead_type_label(lead.lead_type)}",
        f"Имя: {lead.name}",
        f"Телефон: {lead.phone}",
    ]
    if lead.lead_type == LeadType.booking and lead.catalog_item_id:
        parts.append(f"ID фильма: {lead.catalog_item_id}")
    if lead.city:
        parts.append(f"Город: {lead.city}")
    if lead.preferred_time:
        parts.append(f"Удобное время: {lead.preferred_time}")
    parts.append(f"Создана: {_fmt_dt(lead.created_at)}")
    parts.append(f"Статус: {lead_status_label(lead.status)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Вопросы
# ---------------------------------------------------------------------------

def format_questions_list(questions: list[UserQuestion], page: int, total: int) -> str:
    pages = max(1, math.ceil(total / QUESTIONS_PER_PAGE))
    start = (page - 1) * QUESTIONS_PER_PAGE + 1
    lines = [f"<b>Вопросы</b>  (стр. {page}/{pages}, всего {total})\n"]
    for i, q in enumerate(questions, start=start):
        status = "Отвечен" if q.is_answered else "Новый"
        short = q.text[:50].replace("\n", " ")
        if len(q.text) > 50:
            short += "…"
        lines.append(f"{i}. {_user_display(q)} | {short} | {_fmt_dt(q.created_at)} | {status}")
    return "\n".join(lines)


def format_question_card(q: UserQuestion) -> str:
    parts = [
        f"<b>Вопрос #{q.id}</b>",
        f"Пользователь: {_user_display(q)}",
        f"Дата: {_fmt_dt(q.created_at)}",
        f"Статус: {'Отвечен' if q.is_answered else 'Новый'}",
        "",
        "<b>Текст вопроса:</b>",
        q.text,
    ]
    if q.is_answered and q.answer_text:
        parts += ["", "<b>Ответ:</b>", q.answer_text]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

def format_stats(data: dict, period: str) -> str:
    label = _PERIOD_LABELS.get(period, period)
    lines = [
        f"<b>Статистика — {label}</b>",
        "",
        "<b>Пользователи</b>",
        f"Всего: {data['total_users']}",
        f"За период: {data['users_period']}",
        "",
        "<b>Заявки</b>",
        f"Всего: {data['total_leads']}",
        f"За период: {data['leads_period']}",
        f"  Запись: {data['leads_booking']}",
        f"  Франшиза: {data['leads_franchise']}",
        f"  Контакт: {data['leads_contact']}",
        "",
        "<b>Вопросы</b>",
        f"Всего: {data['total_questions']}",
        f"За период: {data['questions_period']}",
        "",
        "<b>Действия (за период)</b>",
        f"Открытий каталога: {data['open_catalog']}",
        f"Открытий карточек: {data['open_catalog_item']}",
        f"Переходов на сайт: {data['click_site_link']}",
        f"Запусков формы: {data['start_lead_form']}",
        f"Отправлено заявок: {data['submit_lead']}",
    ]
    return "\n".join(lines)
