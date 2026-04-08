"""
Обработчики форм сбора заявок (Фазы 3–4).

Флоу для booking:
  lead:booking:{item_id}  →  name  →  phone  →  time  →  confirm  →  submit

Флоу для contact (/contact или кнопка «Связаться»):
  lead:contact  →  name  →  phone  →  confirm  →  submit

Флоу для franchise:
  lead:franchise  →  name  →  phone  →  city  →  confirm  →  submit

Прерывание:
  Любой чужой callback в середине формы → exit_confirm
  /start → сбросить FSM, главное меню
"""

from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from bot.config import settings
from bot.keyboards.admin import AdminLeadsCb
from bot.repositories.analytics import log_event
from bot.keyboards.lead import (
    after_submit_keyboard,
    confirm_keyboard,
    exit_confirm_keyboard,
    phone_request_keyboard,
    step_keyboard,
)
from bot.keyboards.main_menu import main_menu_keyboard
from bot.models.db import LeadType
from bot.repositories.catalog import get_item_by_id
from bot.repositories.leads import create_lead
from bot.services.lead import (
    format_admin_notification,
    format_confirmation,
    format_step_prompt,
    normalize_phone,
)
from bot.states.lead import LeadForm
from bot.utils.message_render import show_text_screen

router = Router()

_FORM_CALLBACKS = {
    "lead:submit", "lead:edit", "lead:continue", "lead:exit", "lead:cancel", "lead:skip",
}

WELCOME_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "Logo.png"

WELCOME_TEXT = (
    "Добро пожаловать в Альтаирику!\n\n"
    "Мы создаём образовательные VR/360° фильмы для школ, планетариев и семей.\n\n"
    "Выберите раздел:"
)


# ---------------------------------------------------------------------------
# Запуск формы — booking (из карточки каталога)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("lead:booking:"))
async def start_booking(callback: CallbackQuery, state: FSMContext, session) -> None:
    item_id = int(callback.data.split(":")[2])
    item = await get_item_by_id(session, item_id)
    await log_event(session, callback.from_user.id, "start_lead_form", entity_type="lead_type", payload_json='{"type":"booking"}')

    screen = await show_text_screen(
        callback,
        format_step_prompt(LeadForm.name),
        reply_markup=step_keyboard(),
        parse_mode="HTML",
    )
    await state.set_data({
        "lead_type": LeadType.booking,
        "catalog_item_id": item_id,
        "item_title": item.title if item else None,
        "form_chat_id": screen.chat.id,
        "form_message_id": screen.message_id,
    })
    await state.set_state(LeadForm.name)
    await callback.answer()


# ---------------------------------------------------------------------------
# Запуск формы — franchise (из раздела франшизы)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "lead:franchise")
async def start_franchise(callback: CallbackQuery, state: FSMContext, session) -> None:
    await log_event(session, callback.from_user.id, "start_lead_form", entity_type="lead_type", payload_json='{"type":"franchise"}')
    screen = await show_text_screen(
        callback,
        format_step_prompt(LeadForm.name, lead_type=LeadType.franchise),
        reply_markup=step_keyboard(),
        parse_mode="HTML",
    )
    await state.set_data({
        "lead_type": LeadType.franchise,
        "form_chat_id": screen.chat.id,
        "form_message_id": screen.message_id,
    })
    await state.set_state(LeadForm.name)
    await callback.answer()


# ---------------------------------------------------------------------------
# Запуск формы — contact (из меню или /contact)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "contact")
@router.message(Command("contact"))
async def start_contact(event, state: FSMContext, session) -> None:
    await log_event(session, event.from_user.id, "start_lead_form", entity_type="lead_type", payload_json='{"type":"contact"}')
    if isinstance(event, CallbackQuery):
        screen = await show_text_screen(
            event,
            format_step_prompt(LeadForm.name, lead_type=LeadType.contact),
            reply_markup=step_keyboard(),
            parse_mode="HTML",
        )
        await state.set_data({
            "lead_type": LeadType.contact,
            "form_chat_id": screen.chat.id,
            "form_message_id": screen.message_id,
        })
        await state.set_state(LeadForm.name)
        await event.answer()
    else:
        sent = await event.answer(
            format_step_prompt(LeadForm.name, lead_type=LeadType.contact),
            reply_markup=step_keyboard(),
            parse_mode="HTML",
        )
        await state.set_data({
            "lead_type": LeadType.contact,
            "form_chat_id": sent.chat.id,
            "form_message_id": sent.message_id,
        })
        await state.set_state(LeadForm.name)


# ---------------------------------------------------------------------------
# Шаг 1 — Имя
# ---------------------------------------------------------------------------

@router.message(StateFilter(LeadForm.name))
async def step_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await _render_current_step(
            message.bot,
            state,
            "Пожалуйста, введите имя минимум из 2 символов.\n\nКак вас зовут?",
        )
        return

    await state.update_data(name=name)
    await _delete_user_message(message)
    await state.set_state(LeadForm.phone)
    await _render_current_step(message.bot, state)


# ---------------------------------------------------------------------------
# Шаг 2 — Телефон (текст или Telegram Contact)
# ---------------------------------------------------------------------------

@router.message(StateFilter(LeadForm.phone), F.contact)
async def step_phone_contact(message: Message, state: FSMContext) -> None:
    phone = f"+{message.contact.phone_number.lstrip('+')}"
    await _phone_received(message, state, phone)


@router.message(StateFilter(LeadForm.phone))
async def step_phone_text(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if not phone:
        await _render_current_step(
            message.bot,
            state,
            "Похоже, это не номер телефона. Попробуйте ещё раз.\n\nВведите номер телефона:",
        )
        return

    await _phone_received(message, state, phone)


async def _phone_received(message: Message, state: FSMContext, phone: str) -> None:
    data = await state.get_data()
    await _delete_phone_helper(message.bot, state)
    await state.update_data(phone=phone)
    await _delete_user_message(message)
    lead_type = data.get("lead_type")

    if lead_type == LeadType.booking:
        await state.set_state(LeadForm.time)
        await _render_current_step(message.bot, state)
    elif lead_type == LeadType.franchise:
        await state.set_state(LeadForm.city)
        await _render_current_step(message.bot, state)
    else:
        await _show_confirm(message.bot, state)


# ---------------------------------------------------------------------------
# Шаг 3 — Время (только для booking)
# ---------------------------------------------------------------------------

@router.message(StateFilter(LeadForm.time))
async def step_time(message: Message, state: FSMContext) -> None:
    if message.text != "Пропустить":
        await state.update_data(preferred_time=(message.text or "").strip() or None)

    await _delete_user_message(message)
    await _show_confirm(message.bot, state)


# ---------------------------------------------------------------------------
# Шаг 3б — Город (только для franchise)
# ---------------------------------------------------------------------------

@router.message(StateFilter(LeadForm.city))
async def step_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await _render_current_step(
            message.bot,
            state,
            "Пожалуйста, укажите город или регион.\n\nВаш город или регион?",
        )
        return

    await state.update_data(city=city)
    await _delete_user_message(message)
    await _show_confirm(message.bot, state)


# ---------------------------------------------------------------------------
# Шаг 4 — Подтверждение
# ---------------------------------------------------------------------------

async def _show_confirm(bot: Bot, state: FSMContext) -> None:
    await _delete_phone_helper(bot, state)
    data = await state.get_data()
    await state.set_state(LeadForm.confirm)
    await _edit_form_message(
        bot,
        state,
        format_confirmation(data),
        reply_markup=confirm_keyboard(),
    )


@router.callback_query(StateFilter(LeadForm.confirm), F.data == "lead:edit")
async def step_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Вернуться к шагу имени, сохранив введённые данные."""
    await state.set_state(LeadForm.name)
    await _edit_form_message(
        callback.bot,
        state,
        format_step_prompt(LeadForm.name, lead_type=(await state.get_data()).get("lead_type")),
        reply_markup=step_keyboard(),
    )
    await callback.answer()


@router.callback_query(StateFilter(LeadForm.confirm), F.data == "lead:cancel")
async def step_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_main_menu(callback.bot, state)
    await callback.answer()


@router.callback_query(StateFilter(LeadForm), F.data == "lead:cancel")
async def cancel_form(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_main_menu(callback.bot, state)
    await callback.answer()


@router.callback_query(StateFilter(LeadForm.time), F.data == "lead:skip")
async def step_skip_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(preferred_time=None)
    await _show_confirm(callback.bot, state)
    await callback.answer()


# ---------------------------------------------------------------------------
# Шаг 5 — Отправка
# ---------------------------------------------------------------------------

@router.callback_query(StateFilter(LeadForm.confirm), F.data == "lead:submit")
async def step_submit(callback: CallbackQuery, state: FSMContext, session, bot: Bot) -> None:
    data = await state.get_data()

    # Защита от двойного нажатия
    if data.get("submitting"):
        await callback.answer("Заявка уже отправляется…", show_alert=False)
        return
    await state.update_data(submitting=True)

    lead_type: LeadType = data["lead_type"]

    lead = await create_lead(
        session=session,
        telegram_user_id=callback.from_user.id,
        name=data["name"],
        phone=data["phone"],
        lead_type=lead_type,
        catalog_item_id=data.get("catalog_item_id"),
        preferred_time=data.get("preferred_time"),
        city=data.get("city"),
    )
    await log_event(session, callback.from_user.id, "submit_lead", entity_type="lead", entity_id=lead.id)

    await _delete_phone_helper(bot, state)
    await state.clear()

    # Уведомление администратору с кнопкой открытия заявки
    notification_data = dict(data)
    notification_data["telegram_user_id"] = callback.from_user.id
    notification_data["lead_type"] = lead_type
    try:
        notification_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Открыть заявку",
                callback_data=AdminLeadsCb(action="card", only_new=0, page=1, lead_id=lead.id).pack(),
            )
        ]])
        await bot.send_message(
            settings.ADMIN_TELEGRAM_ID,
            format_admin_notification(notification_data),
            reply_markup=notification_keyboard,
        )
    except Exception:
        pass  # Не блокируем пользователя при ошибке уведомления

    has_catalog = lead_type == LeadType.booking
    await callback.message.edit_text(
        "Заявка принята!\n\nМы свяжемся с вами в ближайшее рабочее время.",
        reply_markup=after_submit_keyboard(has_catalog),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Прерывание формы — /start сбрасывает FSM
# ---------------------------------------------------------------------------

@router.message(StateFilter(LeadForm), Command("start"))
async def interrupt_start(message: Message, state: FSMContext) -> None:
    await _show_main_menu(message.bot, state)


# ---------------------------------------------------------------------------
# Прерывание формы — любой посторонний callback во время формы
# ---------------------------------------------------------------------------

@router.callback_query(StateFilter(LeadForm))
async def interrupt_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data in _FORM_CALLBACKS:
        # Это наши кнопки — пропускаем (не должны сюда попасть, но на всякий случай)
        await callback.answer()
        return

    await state.set_state(LeadForm.exit_confirm)
    await state.update_data(_pending_callback=callback.data)

    await _edit_form_message(
        callback.bot,
        state,
        "Вы заполняете заявку. Продолжить или выйти?",
        reply_markup=exit_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(StateFilter(LeadForm.exit_confirm), F.data == "lead:continue")
async def exit_continue(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    # Восстанавливаем предыдущее состояние (шаг подтверждения или текущий)
    # Проще всего — вернуть на confirm если данные уже есть, иначе на name
    lead_type = data.get("lead_type")
    if data.get("phone") and (lead_type != LeadType.franchise or data.get("city")):
        await state.set_state(LeadForm.confirm)
        await _edit_form_message(
            callback.bot,
            state,
            format_confirmation(data),
            reply_markup=confirm_keyboard(),
        )
    elif data.get("phone") and lead_type == LeadType.franchise:
        await state.set_state(LeadForm.city)
        await _render_current_step(callback.bot, state)
    elif data.get("name"):
        await state.set_state(LeadForm.phone)
        await _render_current_step(callback.bot, state)
    else:
        await state.set_state(LeadForm.name)
        await _render_current_step(callback.bot, state)
    await callback.answer()


@router.callback_query(StateFilter(LeadForm.exit_confirm), F.data == "lead:exit")
async def exit_form(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_main_menu(callback.bot, state)
    await callback.answer()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

async def _edit_form_message(
    bot: Bot,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> None:
    data = await state.get_data()
    chat_id = data.get("form_chat_id")
    message_id = data.get("form_message_id")
    if not chat_id or not message_id:
        return
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def _render_current_step(bot: Bot, state: FSMContext, override_text: str | None = None) -> None:
    data = await state.get_data()
    current_state = await state.get_state()
    if current_state == LeadForm.name.state:
        text = override_text or format_step_prompt(LeadForm.name, lead_type=data.get("lead_type"))
        keyboard = step_keyboard()
        await _delete_phone_helper(bot, state)
    elif current_state == LeadForm.phone.state:
        text = override_text or format_step_prompt(LeadForm.phone)
        keyboard = step_keyboard()
    elif current_state == LeadForm.time.state:
        text = override_text or format_step_prompt(LeadForm.time)
        keyboard = step_keyboard(allow_skip=True)
        await _delete_phone_helper(bot, state)
    elif current_state == LeadForm.city.state:
        text = override_text or format_step_prompt(LeadForm.city)
        keyboard = step_keyboard()
        await _delete_phone_helper(bot, state)
    else:
        return

    await _edit_form_message(bot, state, text, reply_markup=keyboard)
    if current_state == LeadForm.phone.state:
        await _ensure_phone_helper(bot, state)


async def _show_main_menu(bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    await _delete_phone_helper(bot, state)
    await state.clear()
    chat_id = data.get("form_chat_id")
    message_id = data.get("form_message_id")
    if chat_id and message_id:
        await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(str(WELCOME_IMAGE_PATH)),
            caption=WELCOME_TEXT,
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML",
        )
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            pass


async def _ensure_phone_helper(bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("phone_helper_message_id"):
        return

    chat_id = data.get("form_chat_id")
    if not chat_id:
        return

    sent = await bot.send_message(
        chat_id=chat_id,
        text="Нажмите кнопку ниже, чтобы Telegram сам отправил ваш номер. Можно и ввести его вручную.",
        reply_markup=phone_request_keyboard(),
    )
    await state.update_data(phone_helper_message_id=sent.message_id)


async def _delete_phone_helper(bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("form_chat_id")
    message_id = data.get("phone_helper_message_id")
    if not chat_id or not message_id:
        return

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass
    try:
        cleanup = await bot.send_message(
            chat_id=chat_id,
            text="Скрываю клавиатуру…",
            reply_markup=ReplyKeyboardRemove(),
        )
        await bot.delete_message(chat_id=chat_id, message_id=cleanup.message_id)
    except TelegramBadRequest:
        pass
    await state.update_data(phone_helper_message_id=None)


async def _delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
