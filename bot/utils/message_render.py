from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup


async def show_text_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) :
    try:
        return await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramBadRequest:
        pass

    sent = await callback.message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    return sent


async def show_photo_screen(
    callback: CallbackQuery,
    photo: str | FSInputFile,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) :
    sent = await callback.message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    return sent


async def show_local_photo_screen(
    callback: CallbackQuery,
    photo_path: str | Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
):
    return await show_photo_screen(
        callback,
        photo=FSInputFile(str(photo_path)),
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
