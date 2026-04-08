# Перехват свободного текста вне активных FSM-форм.
# Никакого разбора намерений — только предложение FAQ или вопрос оператору.
# Для администратора — подсказка /admin (актуально после перезапуска бота).

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message

from bot.config import settings
from bot.keyboards.faq import freetext_keyboard

router = Router()

_ADMIN_HINT = "Введите /admin для перехода в панель администратора."

_USER_HINT = (
    "Я работаю через кнопки.\n\n"
    "Возможно, ответ есть в разделе «Частые вопросы», "
    "или оставьте вопрос — менеджер ответит в рабочее время."
)


@router.message(StateFilter(default_state))
async def freetext_handler(message: Message) -> None:
    # Администратор мог потерять FSM-состояние после перезапуска бота
    if message.from_user.id == settings.ADMIN_TELEGRAM_ID:
        await message.answer(_ADMIN_HINT)
        return

    await message.answer(_USER_HINT, reply_markup=freetext_keyboard())
