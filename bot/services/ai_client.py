"""Клиент для вызова OpenRouter API (совместим с OpenAI SDK)."""
import logging

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


async def call_llm(system_prompt: str, user_message: str) -> str | None:
    """Вызывает модель и возвращает текст ответа или None при ошибке."""
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY не задан")
        return None

    client = _get_client()
    logger.info("LLM вызов: модель=%s prompt_len=%d", settings.AI_MODEL, len(system_prompt))
    try:
        response = await client.chat.completions.create(
            model=settings.AI_MODEL,
            max_tokens=settings.AI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
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
