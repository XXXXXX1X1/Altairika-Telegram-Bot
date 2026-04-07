import re
from html import escape

from bot.models.db import LeadType

# Минимальная/максимальная длина номера (только цифры)
_PHONE_MIN = 10
_PHONE_MAX = 15
_PHONE_RE = re.compile(r"^\+?[\d\s\-().]{7,20}$")


def normalize_phone(raw: str) -> str | None:
    """
    Нормализует номер телефона.
    Возвращает строку вида +79991234567 или None если невалидный.
    """
    if not _PHONE_RE.match(raw.strip()):
        return None
    digits = re.sub(r"\D", "", raw)
    if not (_PHONE_MIN <= len(digits) <= _PHONE_MAX):
        return None
    # Приводим российские номера: 8XXXXXXXXXX → +7XXXXXXXXXX
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return f"+{digits}" if not raw.strip().startswith("+") else f"+{digits}"


LEAD_TYPE_LABELS = {
    LeadType.booking: "Запись на сеанс",
    LeadType.franchise: "Заявка на франшизу",
    LeadType.contact: "Контакт",
}


def format_step_prompt(state, lead_type: LeadType | None = None) -> str:
    state_name = getattr(state, "state", state)
    if state_name.endswith("name"):
        if lead_type == LeadType.franchise:
            return (
                "Оставьте заявку на франшизу, и мы свяжемся с вами в течение одного рабочего дня.\n\n"
                "<b>Как вас зовут?</b>"
            )
        if lead_type == LeadType.contact:
            return "Оставьте контакт, и мы перезвоним вам.\n\n<b>Как вас зовут?</b>"
        return "<b>Как вас зовут?</b>\n\nНапишите ваше имя:"
    if state_name.endswith("phone"):
        return "<b>Ваш номер телефона?</b>\n\nВведите номер в формате +79991234567."
    if state_name.endswith("time"):
        return (
            "<b>Удобное время для сеанса?</b>\n\n"
            "Укажите пожелание или нажмите «Пропустить»."
        )
    if state_name.endswith("city"):
        return "<b>Ваш город или регион?</b>"
    return ""


def format_confirmation(data: dict) -> str:
    """Текст шага подтверждения."""
    lead_type = data["lead_type"]
    lines = [
        "<b>Проверьте данные:</b>",
        "",
        f"Тип: {LEAD_TYPE_LABELS.get(lead_type, lead_type)}",
        f"Имя: {escape(data['name'])}",
        f"Телефон: {escape(data['phone'])}",
    ]
    if data.get("item_title"):
        lines.append(f"Позиция: {escape(data['item_title'])}")
    if data.get("preferred_time"):
        lines.append(f"Удобное время: {escape(data['preferred_time'])}")
    if data.get("city"):
        lines.append(f"Город: {escape(data['city'])}")

    lines += [
        "",
        "<i>Нажимая «Отправить», вы соглашаетесь на обработку персональных данных.</i>",
    ]
    return "\n".join(lines)


def format_admin_notification(data: dict) -> str:
    """Уведомление администратору о новой заявке."""
    lead_type = data["lead_type"]
    label = LEAD_TYPE_LABELS.get(lead_type, str(lead_type))

    is_franchise = lead_type == LeadType.franchise
    prefix = "🆕 ФРАНШИЗА" if is_franchise else "🆕 Новая заявка"

    lines = [
        f"{prefix} — {label}",
        "",
        f"Имя: {data['name']}",
        f"Телефон: {data['phone']}",
    ]
    if data.get("item_title"):
        lines.append(f"Позиция: {data['item_title']}")
    if data.get("preferred_time"):
        lines.append(f"Время: {data['preferred_time']}")
    if data.get("city"):
        lines.append(f"Город: {data['city']}")
    if data.get("telegram_user_id"):
        lines.append(f"Telegram ID: {data['telegram_user_id']}")

    return "\n".join(lines)
