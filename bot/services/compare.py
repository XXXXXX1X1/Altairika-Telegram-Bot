from datetime import date

from bot.models.db import ComparisonParameter, ComparisonRating, Competitor

_RATING_ICON = {
    ComparisonRating.good: "✅",
    ComparisonRating.neutral: "⚠️",
    ComparisonRating.bad: "❌",
}


def format_comparison(
    parameters: list[ComparisonParameter],
    competitors: list[Competitor],
    updated_on: date | None = None,
) -> str:
    if not parameters or not competitors:
        return (
            "Данные для сравнения пока не добавлены.\n\n"
            "Оставьте заявку — мы расскажем о наших преимуществах лично."
        )

    # Индекс конкурентов по id для быстрого поиска
    comp_index = {c.id: c for c in competitors}

    lines = ["<b>Альтаирика vs рынок</b>\n"]

    for param in parameters:
        lines.append(f"<b>{param.name}</b>")
        lines.append(f"  ✅ Альтаирика: {param.altairika_value}")

        # Значения по конкурентам
        values_by_comp = {v.competitor_id: v for v in param.values}
        for comp in competitors:
            val = values_by_comp.get(comp.id)
            if val:
                icon = _RATING_ICON.get(val.rating, "•")
                lines.append(f"  {icon} {comp.name}: {val.value}")

        lines.append("")  # пустая строка между параметрами

    # Сноска с датой
    date_str = updated_on.strftime("%d.%m.%Y") if updated_on else date.today().strftime("%d.%m.%Y")
    lines.append(f"<i>Данные по открытым источникам, актуальны на {date_str}</i>")

    return "\n".join(lines)
