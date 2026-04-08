"""Клиент для вызова OpenRouter API (совместим с OpenAI SDK)."""
import json
import logging
import re

from openai import AsyncOpenAI, APIError, APITimeoutError

from bot.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            timeout=20.0,
        )
    return _client


async def call_llm(
    system_prompt: str,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    *,
    max_tokens: int | None = None,
) -> str | None:
    """Вызывает модель и возвращает текст ответа или None при ошибке."""
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY не задан")
        return None

    client = _get_client()
    logger.info("LLM вызов: модель=%s prompt_len=%d", settings.AI_MODEL, len(system_prompt))
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=settings.AI_MODEL,
            max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            messages=messages,
        )
        text = response.choices[0].message.content or None
        logger.info("LLM ответ получен: %d символов", len(text) if text else 0)
        return text
    except APITimeoutError:
        logger.warning("OpenRouter timeout для модели %s", settings.AI_MODEL)
        return None
    except APIError as e:
        logger.error("OpenRouter API error status=%s body=%s", getattr(e, 'status_code', '?'), str(e)[:300])
        return None
    except Exception as e:
        logger.exception("Неожиданная ошибка при вызове LLM: %s", e)
        return None


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def call_llm_json(
    system_prompt: str,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    *,
    max_tokens: int = 250,
) -> dict | None:
    """Вызывает модель и пытается вернуть JSON-объект."""
    text = await call_llm(
        system_prompt,
        user_message,
        history=history,
        max_tokens=max_tokens,
    )
    if not text:
        return None
    parsed = _extract_json_object(text)
    if parsed is None:
        logger.warning("LLM JSON parse failed: %r", text[:300])
    return parsed
