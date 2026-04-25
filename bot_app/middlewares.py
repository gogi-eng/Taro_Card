from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot_app.config import Settings


class SettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings, database_url: str) -> None:
        self.settings = settings
        self.database_url = database_url

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["settings"] = self.settings
        data["database_url"] = self.database_url
        return await handler(event, data)
