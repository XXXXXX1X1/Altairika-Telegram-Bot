from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.franchise import (
    FranchiseAdvantageCb,
    FranchiseFaqCb,
    franchise_advantage_detail_keyboard,
    franchise_advantages_keyboard,
    franchise_faq_answer_keyboard,
    franchise_faq_items_keyboard,
    franchise_main_keyboard,
    franchise_section_keyboard,
)
from bot.models.db import FranchiseSection
from bot.repositories.franchise import get_franchise_content, parse_franchise_faq
from bot.utils.message_render import show_local_photo_screen, show_text_screen

router = Router()

FRANCHISE_IMAGE_PATH = Path(__file__).resolve().parents[2] / "photo" / "fr.png"

_NO_CONTENT = (
    "Информация по этому разделу скоро появится.\n\n"
    "Оставьте заявку — мы расскажем подробнее."
)

_ADVANTAGE_TEXTS = {
    "why": (
        "<b>🏆 Почему выбирают Altairika</b>\n\n"
        "Altairika сочетает выездной формат, образовательный продукт, собственные технологии "
        "и масштабную сеть партнёров.\n\n"
        "<b>Что выделяет нас</b>\n"
        "• выездная модель без обязательного помещения на старте\n"
        "• продукт на стыке образования, технологий и детских услуг\n"
        "• собственное ПО и операционная инфраструктура\n"
        "• масштабируемая франшизная сеть\n"
        "• не один аттракцион, а целая образовательная платформа\n\n"
        "Это не просто VR-шоу, а понятный мобильный бизнес с сильной упаковкой для школ."
    ),
    "content": (
        "<b>🎬 Контент и языки</b>\n\n"
        "<b>Сильные стороны каталога</b>\n"
        "• 150+ фильмов в библиотеке\n"
        "• 22 языка озвучки\n"
        "• программы для детей от 4+ лет\n"
        "• широкий тематический охват для повторных продаж школам\n\n"
        "<b>Почему это важно партнёру</b>\n"
        "• больше причин вернуться в ту же школу повторно\n"
        "• проще собирать программы под разный возраст\n"
        "• выше LTV учреждения\n"
        "• ниже риск, что контент быстро надоест"
    ),
    "tech": (
        "<b>💻 ПО и технологии</b>\n\n"
        "Altairika работает не только на контенте, но и на собственной технологической базе.\n\n"
        "<b>Что есть внутри продукта</b>\n"
        "• собственное ПО Space Touch VR\n"
        "• сервис статистики и аналитики\n"
        "• синхронные показы до 60 устройств\n"
        "• работа по локальной сети без постоянного интернета\n"
        "• российский реестр ПО\n\n"
        "<b>Практический эффект</b>\n"
        "• легче контролировать выездные показы\n"
        "• проще масштабировать команду\n"
        "• меньше зависимость от технического хаоса на площадке"
    ),
    "schools": (
        "<b>🏫 Продажи в школы</b>\n\n"
        "Altairika упакована не как просто развлечение, а как решение для учреждений.\n\n"
        "<b>Что важно для школ</b>\n"
        "• сильный акцент на школьный B2B/B2G-канал\n"
        "• понятная подача для директоров, завучей и администраций\n"
        "• подходит под задачи цифровой образовательной среды\n"
        "• есть сценарий синхронного показа для целого класса\n"
        "• упоминается совместимость с закупками по 44-ФЗ и 223-ФЗ\n\n"
        "<b>Что это даёт партнёру</b>\n"
        "• легче входить в переговоры со школами\n"
        "• проще продавать продукт как полезную образовательную услугу\n"
        "• выше шанс на долгий цикл сотрудничества"
    ),
    "start": (
        "<b>🚀 Лёгкий старт и экономика</b>\n\n"
        "Модель запуска построена так, чтобы быстрее выйти на первые продажи и не перегружать старт лишними расходами.\n\n"
        "<b>Чем это выгодно</b>\n"
        "• ниже входной барьер, чем у VR-арен и стационарных центров\n"
        "• аренда не съедает маржу на старте\n"
        "• можно быстрее выйти на первые продажи\n"
        "• проще занять локальную нишу в своём городе\n\n"
        "<b>Плюс к этому</b>\n"
        "• модель уже масштабирована на десятки регионов и стран\n"
        "• сеть партнёров и школ доказывает, что формат повторяемый\n"
        "• у франчайзи есть не один продукт, а экосистема для дальнейшего роста"
    ),
}


# ---------------------------------------------------------------------------
# Главная страница франшизы
# ---------------------------------------------------------------------------

@router.callback_query(F.data.in_({"franchise", "franchise:main"}))
async def franchise_main(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.pitch)
    text = content.content if content else (
        "<b>Франшиза Альтаирика</b>\n\n"
        "Станьте партнёром и откройте собственный центр виртуальной реальности.\n"
        "Более 14 лет на рынке, 3 млн зрителей, партнёры в 12 странах."
    )
    await show_local_photo_screen(
        callback,
        FRANCHISE_IMAGE_PATH,
        text,
        reply_markup=franchise_main_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Условия и инвестиции
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "franchise:conditions")
async def franchise_conditions(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.conditions)
    text = content.content if content else _NO_CONTENT
    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_section_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Поддержка и обучение
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "franchise:support")
async def franchise_support(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.support)
    text = content.content if content else _NO_CONTENT
    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_section_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Наши преимущества
# ---------------------------------------------------------------------------

@router.callback_query(F.data.in_({"franchise:advantages", "franchise:market"}))
async def franchise_advantages(callback: CallbackQuery) -> None:
    await show_text_screen(
        callback,
        "<b>🏆 Наши преимущества</b>\n\n"
        "Ключевые сильные стороны франшизы Altairika.\n\n"
        "Выберите раздел:",
        reply_markup=franchise_advantages_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(FranchiseAdvantageCb.filter())
async def franchise_advantage_detail(
    callback: CallbackQuery,
    callback_data: FranchiseAdvantageCb,
) -> None:
    text = _ADVANTAGE_TEXTS.get(callback_data.section)
    if not text:
        await callback.answer("Раздел не найден.", show_alert=True)
        return

    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_advantage_detail_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Подраздел: Частые вопросы
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "franchise:faq")
async def franchise_faq(callback: CallbackQuery, session) -> None:
    content = await get_franchise_content(session, FranchiseSection.faq)
    if not content:
        await show_text_screen(
            callback,
            _NO_CONTENT,
            reply_markup=franchise_section_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    items = parse_franchise_faq(content.content)
    if not items:
        await show_text_screen(
            callback,
            _NO_CONTENT,
            reply_markup=franchise_section_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await show_text_screen(
        callback,
        "<b>Частые вопросы по франшизе</b>\n\nВыберите вопрос:",
        reply_markup=franchise_faq_items_keyboard([(item.id, item.question) for item in items]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(FranchiseFaqCb.filter(F.action == "list"))
async def franchise_faq_list(callback: CallbackQuery, session) -> None:
    await franchise_faq(callback, session)


@router.callback_query(FranchiseFaqCb.filter(F.action == "answer"))
async def franchise_faq_answer(
    callback: CallbackQuery,
    callback_data: FranchiseFaqCb,
    session,
) -> None:
    content = await get_franchise_content(session, FranchiseSection.faq)
    if not content:
        await callback.answer("FAQ не найден.", show_alert=True)
        return

    items = parse_franchise_faq(content.content)
    item = next((item for item in items if item.id == callback_data.item_id), None)
    if not item:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return

    text = f"<b>{item.question}</b>\n\n{item.answer}"
    await show_text_screen(
        callback,
        text,
        reply_markup=franchise_faq_answer_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
