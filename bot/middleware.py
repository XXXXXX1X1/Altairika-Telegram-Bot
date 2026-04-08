from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class CallbackDebounceMiddleware(BaseMiddleware):
    def __init__(self, window_seconds: float = 1.2) -> None:
        self.window_seconds = window_seconds
        self._seen: dict[tuple[int, int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        if not event.message or not event.data:
            return await handler(event, data)

        now = monotonic()
        expired_keys = [
            key for key, ts in self._seen.items() if now - ts > self.window_seconds
        ]
        for key in expired_keys:
            self._seen.pop(key, None)

        key = (event.from_user.id, event.message.message_id, event.data)
        last_seen = self._seen.get(key)
        if last_seen is not None and now - last_seen < self.window_seconds:
            await event.answer("Кнопка уже обрабатывается.")
            return None

        self._seen[key] = now
        return await handler(event, data)
