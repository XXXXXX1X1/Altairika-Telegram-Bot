from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.keyboards.admin import AdminQCb
from bot.repositories.analytics import log_event
from bot.keyboards.faq import (
    FaqCb,
    after_question_keyboard,
    answer_keyboard,
    faq_question_cancel_keyboard,
    items_keyboard,
    topics_keyboard,
)
from bot.repositories.faq import (
    get_active_topics,
    get_item_by_id,
    get_items_by_topic,
    get_topic_by_id,
    save_user_question,
)
from bot.states.faq import UserQuestionForm
from bot.utils.message_render import show_text_screen

router = Router()

_NO_TOPICS_TEXT = (
    "Раздел «Частые вопросы» пока пополняется.\n\n"
    "Задайте вопрос напрямую — мы ответим в рабочее время."
)


# ---------------------------------------------------------------------------
# Вход в FAQ (из главного меню)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "faq")
async def faq_entry(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await _show_topics(callback, session)


@router.callback_query(FaqCb.filter(F.action == "topics"))
async def show_topics(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await _show_topics(callback, session)


async def _show_topics(callback: CallbackQuery, session) -> None:
    topics = await get_active_topics(session)
    if not topics:
        await show_text_screen(callback, _NO_TOPICS_TEXT)
        await callback.answer()
        return

    await show_text_screen(
        callback,
        "<b>Частые вопросы</b>\n\nВыберите тему:",
        reply_markup=topics_keyboard(topics),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Список вопросов темы
# ---------------------------------------------------------------------------

@router.callback_query(FaqCb.filter(F.action == "items"))
async def show_items(callback: CallbackQuery, callback_data: FaqCb, session) -> None:
    topic = await get_topic_by_id(session, callback_data.topic_id)
    if not topic:
        await callback.answer("Тема не найдена.", show_alert=True)
        return

    items = await get_items_by_topic(session, topic.id)
    if not items:
        await show_text_screen(
            callback,
            f"<b>{topic.title}</b>\n\nВ этой теме пока нет вопросов.",
            reply_markup=items_keyboard([], topic.id),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    text = f"<b>{topic.title}</b>\n\nВыберите вопрос:"
    await show_text_screen(
        callback,
        text,
        reply_markup=items_keyboard(items, topic.id),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Ответ на вопрос
# ---------------------------------------------------------------------------

@router.callback_query(FaqCb.filter(F.action == "answer"))
async def show_answer(callback: CallbackQuery, callback_data: FaqCb, session) -> None:
    item = await get_item_by_id(session, callback_data.item_id)
    if not item:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    text = f"<b>{item.question}</b>\n\n{item.answer}"
    await show_text_screen(
        callback,
        text,
        reply_markup=answer_keyboard(callback_data.topic_id),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Задать свой вопрос — запуск FSM
# ---------------------------------------------------------------------------

@router.callback_query(FaqCb.filter(F.action == "question"))
async def start_user_question(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserQuestionForm.waiting_text)
    await show_text_screen(
        callback,
        "Напишите ваш вопрос — мы ответим в ближайшее рабочее время.",
        reply_markup=faq_question_cancel_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(UserQuestionForm.waiting_text))
async def receive_user_question(
    message: Message, state: FSMContext, session, bot: Bot
) -> None:
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Пожалуйста, опишите вопрос подробнее:")
        return

    question = await save_user_question(
        session,
        message.from_user.id,
        text,
        username=message.from_user.username,
    )
    await state.clear()
    await log_event(session, message.from_user.id, "ask_question")

    # Уведомление администратору с кнопкой открытия вопроса
    try:
        notification_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Открыть вопрос",
                callback_data=AdminQCb(action="card", only_new=0, page=1, q_id=question.id).pack(),
            )
        ]])
        await bot.send_message(
            settings.ADMIN_TELEGRAM_ID,
            f"❓ Вопрос от пользователя (ID: {message.from_user.id})\n\n{text}",
            reply_markup=notification_keyboard,
        )
    except Exception:
        pass

    await message.answer(
        "Спасибо! Мы ответим вам в ближайшее рабочее время.",
        reply_markup=after_question_keyboard(),
    )
