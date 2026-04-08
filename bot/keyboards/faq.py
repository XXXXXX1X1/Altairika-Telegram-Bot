from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models.db import FaqItem, FaqTopic


class FaqCb(CallbackData, prefix="faq"):
    action: str       # topics | items | answer | question
    topic_id: int = 0
    item_id: int = 0


def topics_keyboard(topics: list[FaqTopic]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for topic in topics:
        builder.button(
            text=f"📚 {topic.title}",
            callback_data=FaqCb(action="items", topic_id=topic.id),
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


def items_keyboard(items: list[FaqItem], topic_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(
            text=f"❔ {item.question[:60]}{'…' if len(item.question) > 60 else ''}",
            callback_data=FaqCb(action="answer", topic_id=topic_id, item_id=item.id),
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад к темам",
        callback_data=FaqCb(action="topics").pack(),
    ))
    return builder.as_markup()


def answer_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⬅️ Назад к вопросам",
                callback_data=FaqCb(action="items", topic_id=topic_id).pack(),
            ),
            InlineKeyboardButton(
                text="✍️ Задать свой вопрос",
                callback_data=FaqCb(action="question").pack(),
            ),
        ],
    ])


def after_question_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
        ],
    ])


def freetext_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq"),
            InlineKeyboardButton(text="✍️ Написать вопрос", callback_data=FaqCb(action="question").pack()),
        ],
    ])


def faq_question_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="faq")]
        ]
    )
