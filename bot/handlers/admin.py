# Панель администратора.
# Доступ: только ADMIN_TELEGRAM_ID, проверка на каждом handler и callback.
# Вход: /admin

from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.keyboards.admin import (
    AdminLeadsCb,
    AdminQCb,
    AdminStatsCb,
    admin_main_keyboard,
    lead_card_keyboard,
    leads_list_with_items_keyboard,
    question_card_keyboard,
    question_reply_cancel_keyboard,
    questions_list_with_items_keyboard,
    stats_keyboard,
)
from bot.models.db import LeadStatus
from bot.repositories.catalog import get_item_by_id
from bot.repositories.admin import (
    get_lead_by_id,
    get_leads_page,
    get_question_by_id,
    get_questions_page,
    get_stats,
    mark_question_answered,
    mark_question_answered_no_text,
    update_lead_status,
)
from bot.services.admin import (
    format_lead_card,
    format_leads_list,
    format_question_card,
    format_questions_list,
    format_stats,
    lead_status_label,
    lead_type_label,
)
from bot.states.admin import AdminStates
from bot.utils.message_render import show_text_screen

router = Router()

_DENY = "Доступ запрещён"

_PERIOD_DELTAS: dict[str, timedelta | None] = {
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_TELEGRAM_ID


def _since(period: str) -> datetime | None:
    delta = _PERIOD_DELTAS.get(period)
    return None if delta is None else datetime.now(timezone.utc) - delta


# ---------------------------------------------------------------------------
# /admin — вход в панель
# ---------------------------------------------------------------------------

@router.message(Command("admin"))
async def cmd_admin(message: Message, session) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(_DENY)
        return

    _, new_leads_total = await get_leads_page(session, only_new=True)
    _, new_questions_total = await get_questions_page(session, only_unanswered=True)

    await message.answer(
        "<b>Панель администратора</b>",
        reply_markup=admin_main_keyboard(
            new_leads=new_leads_total,
            new_questions=new_questions_total,
        ),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Главный экран (callback)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: CallbackQuery, session, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    await state.clear()
    _, new_leads_total = await get_leads_page(session, only_new=True)
    _, new_questions_total = await get_questions_page(session, only_unanswered=True)

    await show_text_screen(
        callback,
        "<b>Панель администратора</b>",
        reply_markup=admin_main_keyboard(
            new_leads=new_leads_total,
            new_questions=new_questions_total,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Заявки — список
# ---------------------------------------------------------------------------

@router.callback_query(AdminLeadsCb.filter(F.action == "list"))
async def admin_leads_list(
    callback: CallbackQuery, callback_data: AdminLeadsCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    only_new = bool(callback_data.only_new)
    page = max(1, callback_data.page)
    leads, total = await get_leads_page(session, only_new=only_new, page=page)

    if total == 0:
        empty_text = "Новых заявок нет." if only_new else "Заявок пока нет."
        await show_text_screen(
            callback,
            empty_text,
            reply_markup=leads_list_with_items_keyboard([], [], page, 0, only_new=callback_data.only_new),
        )
        await callback.answer()
        return

    labels = [
        f"{lead_type_label(l.lead_type)} | {l.name} | {l.phone[:10]} | {lead_status_label(l.status)}"
        for l in leads
    ]
    await show_text_screen(
        callback,
        format_leads_list(leads, page, total),
        reply_markup=leads_list_with_items_keyboard(
            [l.id for l in leads], labels, page, total, only_new=callback_data.only_new,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Заявки — карточка
# ---------------------------------------------------------------------------

@router.callback_query(AdminLeadsCb.filter(F.action == "card"))
async def admin_lead_card(
    callback: CallbackQuery, callback_data: AdminLeadsCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    lead = await get_lead_by_id(session, callback_data.lead_id)
    if lead is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    item = await get_item_by_id(session, lead.catalog_item_id) if lead.catalog_item_id else None

    await show_text_screen(
        callback,
        format_lead_card(lead, item.title if item else None),
        reply_markup=lead_card_keyboard(lead.id, callback_data.page, callback_data.only_new),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Заявки — смена статуса
# ---------------------------------------------------------------------------

@router.callback_query(AdminLeadsCb.filter(F.action.in_(["set_in_progress", "set_done"])))
async def admin_lead_status(
    callback: CallbackQuery, callback_data: AdminLeadsCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    new_status = LeadStatus.in_progress if callback_data.action == "set_in_progress" else LeadStatus.done
    lead = await update_lead_status(session, callback_data.lead_id, new_status)
    if lead is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    item = await get_item_by_id(session, lead.catalog_item_id) if lead.catalog_item_id else None

    await show_text_screen(
        callback,
        format_lead_card(lead, item.title if item else None),
        reply_markup=lead_card_keyboard(lead.id, callback_data.page, callback_data.only_new),
        parse_mode="HTML",
    )
    await callback.answer(f"Статус: {lead_status_label(lead.status)}")


# ---------------------------------------------------------------------------
# Вопросы — список
# ---------------------------------------------------------------------------

@router.callback_query(AdminQCb.filter(F.action == "list"))
async def admin_questions_list(
    callback: CallbackQuery, callback_data: AdminQCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    only_new = bool(callback_data.only_new)
    page = max(1, callback_data.page)
    questions, total = await get_questions_page(session, only_unanswered=only_new, page=page)

    if total == 0:
        empty_text = "Новых вопросов нет." if only_new else "Вопросов пока нет."
        await show_text_screen(
            callback,
            empty_text,
            reply_markup=questions_list_with_items_keyboard(
                [], [], page, 0, only_new=callback_data.only_new,
            ),
        )
        await callback.answer()
        return

    labels = []
    for q in questions:
        user = f"@{q.username}" if q.username else f"ID{q.telegram_user_id}"
        short = q.text[:40].replace("\n", " ")
        if len(q.text) > 40:
            short += "…"
        labels.append(f"{'✓' if q.is_answered else '•'} {user}: {short}")

    await show_text_screen(
        callback,
        format_questions_list(questions, page, total),
        reply_markup=questions_list_with_items_keyboard(
            [q.id for q in questions], labels, page, total, only_new=callback_data.only_new,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Вопросы — карточка
# ---------------------------------------------------------------------------

@router.callback_query(AdminQCb.filter(F.action == "card"))
async def admin_question_card(
    callback: CallbackQuery, callback_data: AdminQCb, session, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    await state.clear()
    question = await get_question_by_id(session, callback_data.q_id)
    if question is None:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    await show_text_screen(
        callback,
        format_question_card(question),
        reply_markup=question_card_keyboard(question.id, callback_data.page, callback_data.only_new),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Вопросы — отметить отвеченным без отправки ответа
# ---------------------------------------------------------------------------

@router.callback_query(AdminQCb.filter(F.action == "mark_done"))
async def admin_question_mark_done(
    callback: CallbackQuery, callback_data: AdminQCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    question = await mark_question_answered_no_text(session, callback_data.q_id, callback.from_user.id)
    if question is None:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    await show_text_screen(
        callback,
        format_question_card(question),
        reply_markup=question_card_keyboard(question.id, callback_data.page, callback_data.only_new),
        parse_mode="HTML",
    )
    await callback.answer("Отмечено как отвеченный.")


# ---------------------------------------------------------------------------
# Вопросы — запуск ввода ответа (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(AdminQCb.filter(F.action == "reply"))
async def admin_question_reply_start(
    callback: CallbackQuery, callback_data: AdminQCb, state: FSMContext
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    # Редактируем текущее сообщение и запоминаем его координаты для дальнейшего редактирования
    sent = await show_text_screen(
        callback,
        "Напишите ответ пользователю:",
        reply_markup=question_reply_cancel_keyboard(
            callback_data.q_id, callback_data.page, callback_data.only_new,
        ),
    )
    await state.set_state(AdminStates.waiting_reply)
    await state.update_data(
        reply_q_id=callback_data.q_id,
        reply_page=callback_data.page,
        reply_only_new=callback_data.only_new,
        form_chat_id=sent.chat.id,
        form_message_id=sent.message_id,
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Вопросы — получение текста ответа и отправка пользователю
# ---------------------------------------------------------------------------

async def _edit_form(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
) -> None:
    """Редактирует сообщение формы на месте, не создавая нового."""
    if not chat_id or not message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass


async def _delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(StateFilter(AdminStates.waiting_reply))
async def admin_question_reply_receive(
    message: Message, state: FSMContext, session, bot: Bot
) -> None:
    if not _is_admin(message.from_user.id):
        return

    # Читаем все данные из FSM до любых state.clear()
    data = await state.get_data()
    q_id: int = data["reply_q_id"]
    page: int = data.get("reply_page", 1)
    only_new: int = data.get("reply_only_new", 0)
    form_chat_id: int = data.get("form_chat_id", 0)
    form_message_id: int = data.get("form_message_id", 0)

    answer_text = (message.text or "").strip()
    if not answer_text:
        # Удаляем пустое сообщение, редактируем форму с подсказкой
        await _delete_message(message)
        await _edit_form(
            bot, form_chat_id, form_message_id,
            "Ответ не может быть пустым.\n\nНапишите текст:",
            reply_markup=question_reply_cancel_keyboard(q_id, page, only_new),
        )
        return

    question = await get_question_by_id(session, q_id)
    if question is None:
        await _delete_message(message)
        await state.clear()
        await _edit_form(bot, form_chat_id, form_message_id, "Вопрос не найден.")
        return

    # Удаляем введённое администратором сообщение
    await _delete_message(message)

    # Отправляем ответ пользователю
    sent_ok = False
    try:
        await bot.send_message(question.telegram_user_id, f"Ответ на ваш вопрос:\n\n{answer_text}")
        sent_ok = True
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    except Exception:
        pass

    if not sent_ok:
        await state.clear()
        await _edit_form(
            bot, form_chat_id, form_message_id,
            "Не удалось отправить ответ пользователю.\n"
            "Статус вопроса не изменён.",
            reply_markup=question_card_keyboard(q_id, page, only_new),
        )
        return

    question = await mark_question_answered(session, q_id, answer_text, message.from_user.id)
    await state.clear()

    # Показываем обновлённую карточку вопроса прямо в том же сообщении
    await _edit_form(
        bot, form_chat_id, form_message_id,
        format_question_card(question) + "\n\n<i>✅ Ответ отправлен</i>",
        reply_markup=question_card_keyboard(q_id, page, only_new),
    )


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

@router.callback_query(AdminStatsCb.filter(F.action == "view"))
async def admin_stats(
    callback: CallbackQuery, callback_data: AdminStatsCb, session
) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer(_DENY, show_alert=True)
        return

    data = await get_stats(session, _since(callback_data.period))
    await show_text_screen(
        callback,
        format_stats(data, callback_data.period),
        reply_markup=stats_keyboard(callback_data.period),
        parse_mode="HTML",
    )
    await callback.answer()
