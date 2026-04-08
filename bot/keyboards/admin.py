# Клавиатуры и CallbackData для панели администратора.

import math

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.repositories.admin import LEADS_PER_PAGE, QUESTIONS_PER_PAGE


class AdminLeadsCb(CallbackData, prefix="adml"):
    action: str
    only_new: int = 0   # 0 — все, 1 — только новые/необработанные
    page: int = 1
    lead_id: int = 0


class AdminQCb(CallbackData, prefix="admq"):
    action: str
    only_new: int = 0   # 0 — все, 1 — только неотвеченные
    page: int = 1
    q_id: int = 0


class AdminStatsCb(CallbackData, prefix="admst"):
    action: str
    period: str = "today"


# ---------------------------------------------------------------------------
# Главный экран
# ---------------------------------------------------------------------------

def admin_main_keyboard(new_leads: int = 0, new_questions: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    new_l = f"Новые заявки ({new_leads})" if new_leads else "Новые заявки"
    new_q = f"Новые вопросы ({new_questions})" if new_questions else "Новые вопросы"
    builder.row(
        InlineKeyboardButton(
            text=new_l,
            callback_data=AdminLeadsCb(action="list", only_new=1, page=1).pack(),
        ),
        InlineKeyboardButton(
            text="Все заявки",
            callback_data=AdminLeadsCb(action="list", only_new=0, page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=new_q,
            callback_data=AdminQCb(action="list", only_new=1, page=1).pack(),
        ),
        InlineKeyboardButton(
            text="Все вопросы",
            callback_data=AdminQCb(action="list", only_new=0, page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="Статистика",
            callback_data=AdminStatsCb(action="view", period="today").pack(),
        )
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------------------

def _pagination_row(page: int, total: int, per_page: int, cb_prev: str, cb_next: str) -> list[InlineKeyboardButton]:
    pages = max(1, math.ceil(total / per_page))
    prev_btn = (
        InlineKeyboardButton(text="←", callback_data=cb_prev)
        if page > 1
        else InlineKeyboardButton(text=" ", callback_data="noop")
    )
    counter_btn = InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop")
    next_btn = (
        InlineKeyboardButton(text="→", callback_data=cb_next)
        if page < pages
        else InlineKeyboardButton(text=" ", callback_data="noop")
    )
    return [prev_btn, counter_btn, next_btn]


def leads_list_with_items_keyboard(
    lead_ids: list[int],
    lead_labels: list[str],
    page: int,
    total: int,
    *,
    only_new: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lead_id, label in zip(lead_ids, lead_labels):
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=AdminLeadsCb(action="card", only_new=only_new, page=page, lead_id=lead_id).pack(),
        ))
    builder.row(*_pagination_row(
        page, total, LEADS_PER_PAGE,
        cb_prev=AdminLeadsCb(action="list", only_new=only_new, page=page - 1).pack(),
        cb_next=AdminLeadsCb(action="list", only_new=only_new, page=page + 1).pack(),
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"))
    return builder.as_markup()


def lead_card_keyboard(lead_id: int, page: int, only_new: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="В работу",
            callback_data=AdminLeadsCb(action="set_in_progress", only_new=only_new, page=page, lead_id=lead_id).pack(),
        ),
        InlineKeyboardButton(
            text="Закрыть",
            callback_data=AdminLeadsCb(action="set_done", only_new=only_new, page=page, lead_id=lead_id).pack(),
        ),
    )
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к списку",
        callback_data=AdminLeadsCb(action="list", only_new=only_new, page=page).pack(),
    ))
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Вопросы
# ---------------------------------------------------------------------------

def questions_list_with_items_keyboard(
    q_ids: list[int],
    q_labels: list[str],
    page: int,
    total: int,
    *,
    only_new: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for q_id, label in zip(q_ids, q_labels):
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=AdminQCb(action="card", only_new=only_new, page=page, q_id=q_id).pack(),
        ))
    builder.row(*_pagination_row(
        page, total, QUESTIONS_PER_PAGE,
        cb_prev=AdminQCb(action="list", only_new=only_new, page=page - 1).pack(),
        cb_next=AdminQCb(action="list", only_new=only_new, page=page + 1).pack(),
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"))
    return builder.as_markup()


def question_card_keyboard(q_id: int, page: int, only_new: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Ответить",
            callback_data=AdminQCb(action="reply", only_new=only_new, page=page, q_id=q_id).pack(),
        ),
        InlineKeyboardButton(
            text="Отметить отвеченным",
            callback_data=AdminQCb(action="mark_done", only_new=only_new, page=page, q_id=q_id).pack(),
        ),
    )
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к списку",
        callback_data=AdminQCb(action="list", only_new=only_new, page=page).pack(),
    ))
    return builder.as_markup()


def question_reply_cancel_keyboard(q_id: int, page: int, only_new: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Отмена",
            callback_data=AdminQCb(action="card", only_new=only_new, page=page, q_id=q_id).pack(),
        )
    ]])


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

_PERIODS = [
    ("today", "Сегодня"),
    ("7d", "7 дней"),
    ("30d", "30 дней"),
    ("all", "Всё время"),
]


def stats_keyboard(current_period: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in _PERIODS:
        text = f"✓ {label}" if code == current_period else label
        builder.button(text=text, callback_data=AdminStatsCb(action="view", period=code).pack())
    builder.adjust(4)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"))
    return builder.as_markup()
