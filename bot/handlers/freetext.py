"""
Обработчик свободного текста вне активных форм (Фаза 5.4).

Любой текст, не пойманный другими хендлерами → предложить FAQ или написать вопрос.
Никакого разбора намерений.
"""

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message

from bot.keyboards.faq import freetext_keyboard

router = Router()


@router.message(StateFilter(default_state))
async def freetext_handler(message: Message) -> None:
    await message.answer(
        "Я работаю через кнопки.\n\n"
        "Возможно, ответ есть в разделе «Частые вопросы», "
        "или оставьте вопрос — менеджер ответит в рабочее время.",
        reply_markup=freetext_keyboard(),
    )
