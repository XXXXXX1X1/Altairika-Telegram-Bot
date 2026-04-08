from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class FranchiseFaqCb(CallbackData, prefix="frfaq"):
    action: str
    item_id: int = 0


class FranchiseAdvantageCb(CallbackData, prefix="fradv"):
    section: str


def _compact_faq_question(question: str) -> str:
    replacements = {
        "Какое оборудование необходимо?": "Какое нужно оборудование?",
        "Что входит в паушальный взнос?": "Что входит в паушальный взнос?",
        "Могу ли я через вас купить оборудование?": "Можно купить оборудование через вас?",
        "Подходит ли франшиза для малых городов?": "Подходит для малых городов?",
        "Где и с кем я смогу работать?": "Где и с кем работать?",
        "Какие ещё бизнес-продукты у вас есть?": "Какие ещё продукты у вас есть?",
    }
    return replacements.get(question, question)


def franchise_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💼 Условия и инвестиции", callback_data="franchise:conditions")
    builder.button(text="📦 Что входит в пакет", callback_data="franchise:support")
    builder.button(text="🏆 Наши преимущества", callback_data="franchise:advantages")
    builder.button(text="❓ Частые вопросы", callback_data="franchise:faq")
    builder.button(text="📝 Оставить заявку", callback_data="lead:franchise")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def franchise_section_keyboard(show_market: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Оставить заявку", callback_data="lead:franchise")
    builder.button(text="⬅️ Назад", callback_data="franchise:main")
    builder.adjust(2)
    return builder.as_markup()


def franchise_faq_items_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item_id, question in items:
        button_text = _compact_faq_question(question)
        builder.button(
            text=button_text,
            callback_data=FranchiseFaqCb(action="answer", item_id=item_id).pack(),
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="franchise:main"))
    return builder.as_markup()


def franchise_faq_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к вопросам",
                    callback_data=FranchiseFaqCb(action="list").pack(),
                ),
                InlineKeyboardButton(
                    text="📝 Оставить заявку",
                    callback_data="lead:franchise",
                ),
            ],
        ]
    )


def franchise_advantages_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏆 Почему выбирают Altairika",
        callback_data=FranchiseAdvantageCb(section="why").pack(),
    )
    builder.button(
        text="🎬 Контент и языки",
        callback_data=FranchiseAdvantageCb(section="content").pack(),
    )
    builder.button(
        text="💻 ПО и технологии",
        callback_data=FranchiseAdvantageCb(section="tech").pack(),
    )
    builder.button(
        text="🏫 Продажи в школы",
        callback_data=FranchiseAdvantageCb(section="schools").pack(),
    )
    builder.button(
        text="🚀 Лёгкий старт",
        callback_data=FranchiseAdvantageCb(section="start").pack(),
    )
    builder.button(text="⬅️ Назад", callback_data="franchise:main")
    builder.adjust(1)
    return builder.as_markup()


def franchise_advantage_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к преимуществам",
                    callback_data="franchise:advantages",
                ),
                InlineKeyboardButton(
                    text="📝 Оставить заявку",
                    callback_data="lead:franchise",
                ),
            ],
        ]
    )
