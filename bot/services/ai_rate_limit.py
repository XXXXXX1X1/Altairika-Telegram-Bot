"""Rate limiting для AI-запросов. Скользящее окно, in-memory."""
import logging
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Лимиты
_AI_RATE_LIMIT = 50          # запросов
_AI_RATE_WINDOW = 300        # секунд (5 минут)
_CLEANUP_EVERY = 1000        # чистить словарь каждые N вызовов

_user_requests: dict[int, deque[datetime]] = {}
_call_count = 0


def check_ai_rate_limit(user_id: int) -> bool:
    """
    Возвращает True если запрос разрешён, False если лимит исчерпан.
    Скользящее окно: не более _AI_RATE_LIMIT запросов за _AI_RATE_WINDOW секунд.
    """
    global _call_count
    _call_count += 1

    now = datetime.now()
    window_start = now - timedelta(seconds=_AI_RATE_WINDOW)

    if user_id not in _user_requests:
        _user_requests[user_id] = deque()

    dq = _user_requests[user_id]

    # Убираем устаревшие метки из начала очереди
    while dq and dq[0] < window_start:
        dq.popleft()

    if len(dq) >= _AI_RATE_LIMIT:
        logger.warning("AI rate limit: user=%d, requests=%d за %ds", user_id, len(dq), _AI_RATE_WINDOW)
        return False

    dq.append(now)

    # Периодически чистим пустые записи чтобы словарь не рос вечно
    if _call_count % _CLEANUP_EVERY == 0:
        _cleanup_stale_users(window_start)

    return True


def get_remaining(user_id: int) -> int:
    """Возвращает сколько запросов осталось в текущем окне."""
    if user_id not in _user_requests:
        return _AI_RATE_LIMIT
    window_start = datetime.now() - timedelta(seconds=_AI_RATE_WINDOW)
    dq = _user_requests[user_id]
    active = sum(1 for ts in dq if ts >= window_start)
    return max(0, _AI_RATE_LIMIT - active)


def _cleanup_stale_users(window_start: datetime) -> None:
    """Удаляет из словаря пользователей без активности в текущем окне."""
    stale = [uid for uid, dq in _user_requests.items() if not dq or dq[-1] < window_start]
    for uid in stale:
        del _user_requests[uid]
    if stale:
        logger.debug("AI rate limit: очищено %d устаревших записей", len(stale))
