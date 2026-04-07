from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.compare import compare_keyboard
from bot.repositories.compare import get_active_competitors, get_parameters_with_values
from bot.services.compare import format_comparison
from bot.utils.message_render import show_text_screen

router = Router()


@router.callback_query(F.data == "franchise:market")
async def show_comparison(callback: CallbackQuery, session) -> None:
    competitors = await get_active_competitors(session)
    parameters = await get_parameters_with_values(session)

    text = format_comparison(parameters, competitors)

    await show_text_screen(
        callback,
        text,
        reply_markup=compare_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
