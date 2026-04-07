"""
Парсер каталога altairika.ru.

Каталог на странице /catalog_full рендерится через Tilda Store:
в HTML нет готовых карточек, а товары подгружаются из Tilda API.

Стратегия:
1. Скачать HTML страницы /catalog_full.
2. Извлечь пары recid/storepart для блоков каталога и их подписи.
3. Запросить /api/getproductslist/ для каждого блока.
4. Нормализовать и объединить позиции по title.
"""

import asyncio
import html
import json
import logging
import re
import ssl
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

CATALOG_URL = "https://altairika.ru/catalog_full"
TIMEOUT_SEC = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_OPTION_RE = re.compile(
    r'<option value="(?P<recid>\d+),\d+">(?P<label>[^<]+)</option>'
)
_STORE_RE = re.compile(
    r"recid:'(?P<recid>\d+)',storepart:'(?P<storepart>\d+)'"
)
PRIMARY_RECID = "1794845301"
PRIMARY_STOREPART = "586011282611"
_EXACT_DURATION_PATTERNS = [
    re.compile(
        r"\d{1,2}\+\s*\|\s*(\d{1,3}\s*мин(?:ут(?:а|ы)?)?\.?)\s*\|\s*(?:180|360)°",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:продолжительность|длительность|хронометраж)[^0-9]{0,40}(\d{1,3}\s*(?:минут(?:а|ы)?|мин\.?))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3}\s*(?:минут(?:а|ы)?|мин\.?))[^а-яa-z]{0,20}(?:фильм|мультфильм|ролик|сеанс)",
        re.IGNORECASE,
    ),
]
_RANGE_DURATION_MARKERS = (
    "до 5",
    "5-10",
    "10-15",
    "15-20",
    "20-25",
    "25-30",
    "более 30",
)


@dataclass
class ParsedItem:
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    image_url: str | None = None
    price: str | None = None
    duration: str | None = None
    age_rating: str | None = None
    url: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(
        request,
        timeout=TIMEOUT_SEC,
        context=ssl._create_unverified_context(),
    ) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_store_blocks(page_html: str) -> list[tuple[str, str, str | None]]:
    categories_by_recid = {
        match.group("recid"): re.sub(r"\s*\(всего \d+\)\s*$", "", match.group("label")).strip()
        for match in _OPTION_RE.finditer(page_html)
    }

    blocks: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str]] = set()

    for match in _STORE_RE.finditer(page_html):
        recid = match.group("recid")
        storepart = match.group("storepart")
        key = (recid, storepart)
        if key in seen:
            continue
        seen.add(key)
        blocks.append((recid, storepart, categories_by_recid.get(recid)))

    return blocks


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = html.unescape(value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() or None


def _extract_first_image(product: dict) -> str | None:
    editions = product.get("editions") or []
    if editions:
        image = editions[0].get("img")
        if image:
            return image

    gallery_raw = product.get("gallery")
    if not gallery_raw:
        return None

    try:
        gallery = json.loads(gallery_raw)
    except json.JSONDecodeError:
        return None

    if not gallery:
        return None

    return gallery[0].get("img")


def _extract_characteristic_values(product: dict, title: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for item in product.get("characteristics") or []:
        if item.get("title") != title:
            continue
        value = _clean_text(item.get("value"))
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)

    return values


def _join_values(values: list[str]) -> str | None:
    if not values:
        return None
    return ", ".join(values)


def _normalize_exact_duration(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _clean_text(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    if any(marker in lowered for marker in _RANGE_DURATION_MARKERS):
        return None
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("мин.", "минут")
    normalized = re.sub(r"\bмин\b", "минут", normalized)
    return normalized


def _should_lookup_precise_duration(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _RANGE_DURATION_MARKERS)


def _extract_precise_duration_from_page_html(page_html: str) -> str | None:
    text = html.unescape(page_html)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    for pattern in _EXACT_DURATION_PATTERNS:
        match = pattern.search(text)
        if match:
            duration = _normalize_exact_duration(match.group(1))
            if duration:
                return duration
    return None


async def _try_fetch_precise_duration(url: str | None) -> str | None:
    if not url or url == CATALOG_URL:
        return None
    try:
        page_html = await asyncio.to_thread(_fetch_text, url)
    except Exception:
        logger.debug("Парсер: не удалось открыть страницу фильма для точной длительности: %s", url)
        return None
    return _extract_precise_duration_from_page_html(page_html)


def _extract_tags(product: dict) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    tag_titles = ("тема", "тематика", "предмет", "направление", "жанр")

    for item in product.get("characteristics") or []:
        title = (item.get("title") or "").strip().lower()
        if not any(marker in title for marker in tag_titles):
            continue

        raw_value = _clean_text(item.get("value"))
        if not raw_value:
            continue

        for part in re.split(r"[,/;\n]+", raw_value):
            value = part.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            tags.append(value)

    return tags


def _normalize_age_rating(values: list[str]) -> str | None:
    if not values:
        return None

    order = [
        ("Любой", "0+"),
        ("Детский сад", "5+"),
        ("Начальная школа", "7+"),
        ("Средняя школа", "12+"),
        ("Старшая школа", "16+"),
        ("Взрослые", "18+"),
    ]
    present = set(values)

    for label, rating in order:
        if label in present:
            return rating

    return values[0][:20]


async def _fetch_products_for_block(recid: str, storepart: str) -> tuple[int, list[dict]]:
    products: list[dict] = []
    slice_num = 1
    total = 0

    while True:
        api_url = (
            "https://store.tildaapi.com/api/getproductslist/"
            f"?recid={recid}&storepartuid={storepart}&slice={slice_num}"
        )
        payload = await asyncio.to_thread(_fetch_text, api_url)
        data = json.loads(payload)
        total = int(data.get("total") or total or 0)
        chunk = data.get("products") or []
        products.extend(chunk)

        nextslice = data.get("nextslice")
        if not nextslice or not chunk:
            break
        slice_num = int(nextslice)

    return total, products


async def parse_catalog() -> list[ParsedItem]:
    """
    Парсит каталог altairika.ru/catalog_full.
    Возвращает список ParsedItem.
    При ошибке логирует и возвращает пустой список.
    """
    items: list[ParsedItem] = []
    products_by_title: dict[str, ParsedItem] = {}

    try:
        logger.info("Парсер: открываю %s", CATALOG_URL)
        page_html = await asyncio.to_thread(_fetch_text, CATALOG_URL)
        store_blocks = _extract_store_blocks(page_html)

        if not store_blocks:
            logger.warning("Парсер: не удалось извлечь блоки каталога со страницы")
            return []

        logger.info("Парсер: найдено %d стартовых блоков каталога", len(store_blocks))
        primary_category = next(
            (category for recid, _, category in store_blocks if recid == PRIMARY_RECID),
            None,
        )
        primary_total, primary_products = await _fetch_products_for_block(
            PRIMARY_RECID,
            PRIMARY_STOREPART,
        )
        logger.info(
            "Парсер: выбран основной каталог recid=%s storepart=%s total=%d",
            PRIMARY_RECID, PRIMARY_STOREPART, primary_total,
        )

        category_name = primary_category or "Каталог"
        for product in primary_products:
            title = _clean_text(product.get("title"))
            if not title:
                continue

            image_url = _extract_first_image(product)
            age_values = _extract_characteristic_values(product, "Возраст")
            duration_values = _extract_characteristic_values(product, "Продолжительность")
            item_url = _clean_text(product.get("url")) or CATALOG_URL
            duration = _join_values(duration_values)
            if _should_lookup_precise_duration(duration):
                precise_duration = await _try_fetch_precise_duration(item_url)
                if precise_duration:
                    duration = precise_duration

            products_by_title[title] = ParsedItem(
                title=title,
                description=_clean_text(product.get("text")) or _clean_text(product.get("descr")),
                category=category_name,
                tags=_extract_tags(product) or None,
                image_url=image_url,
                price=_clean_text(product.get("price")),
                duration=duration,
                age_rating=_normalize_age_rating(age_values),
                url=item_url,
                raw=product,
            )

    except Exception as exc:
        logger.exception("Парсер: ошибка при парсинге: %s", exc)

    items = list(products_by_title.values())
    logger.info("Парсер: успешно извлечено %d позиций", len(items))
    return items
