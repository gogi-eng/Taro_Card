from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from bot_app.config import Settings


class IsAdmin(Filter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        uid = event.from_user.id if event.from_user else None
        return uid is not None and uid in self.settings.admin_ids
