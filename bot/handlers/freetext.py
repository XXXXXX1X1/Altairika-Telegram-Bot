# Перехват свободного текста вне активных FSM-форм.
# Pipeline: определение intent → сборка контекста → вызов LLM → ответ.
# Для администратора — подсказка /admin.

import logging

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.ai import after_ai_keyboard, ai_fallback_keyboard
from bot.keyboards.faq import freetext_keyboard
from bot.services.ai_answer import generate_answer
from bot.services.ai_router import detect_intent

logger = logging.getLogger(__name__)
router = Router()

_ADMIN_HINT = "Введите /admin для перехода в панель администратора."

_FALLBACK_TEXT = (
    "Не удалось обработать запрос автоматически.\n"
    "Напишите нам напрямую — ответим в рабочее время."
)

# Интенты, которые переводят пользователя в форму без LLM-ответа
_LEAD_INTENTS = {"lead_booking", "lead_franchise"}


@router.message(StateFilter(default_state))
async def freetext_handler(message: Message, session: AsyncSession) -> None:
    # Если AI не настроен — возвращаем старую заглушку
    if not settings.OPENROUTER_API_KEY:
        await message.answer(
            "Я работаю через кнопки.\n\n"
            "Возможно, ответ есть в разделе «Частые вопросы», "
            "или оставьте вопрос — менеджер ответит в рабочее время.",
            reply_markup=freetext_keyboard(),
        )
        return

    user_text = message.text or ""

    # Определяем intent
    intent = detect_intent(user_text)
    logger.info("user=%d intent=%s text=%r", message.from_user.id, intent, user_text[:80])

    # Для явных заявок — не тратим токены, сразу предлагаем форму
    if intent in _LEAD_INTENTS:
        if intent == "lead_booking":
            reply = "Отлично! Нажмите кнопку ниже чтобы оставить заявку на сеанс:"
        else:
            reply = "Хорошо! Нажмите кнопку ниже чтобы оставить заявку на франшизу:"
        await message.answer(reply, reply_markup=after_ai_keyboard(intent))
        return

    # Показываем индикатор загрузки
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Генерируем ответ через LLM
    try:
        answer = await generate_answer(
            db=session,
            telegram_user_id=message.from_user.id,
            user_text=user_text,
            intent=intent,
        )
    except Exception as e:
        logger.exception("Ошибка generate_answer для user=%d: %s", message.from_user.id, e)
        answer = None

    if answer:
        await message.answer(answer, reply_markup=after_ai_keyboard(intent))
    else:
        logger.warning("AI вернул None для user=%d intent=%s", message.from_user.id, intent)
        await message.answer(_FALLBACK_TEXT, reply_markup=ai_fallback_keyboard())
