"""
Обработчики «по умолчанию» — в конце цепи роутеров.
Снимает «крутилку» у старых inline-кнопок и уменьшает «Update is not handled» в логах.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot_app.config import Settings
from bot_app.keyboards import kb_start


def setup(_settings: Settings) -> Router:
    router = Router(name="fallback")

    @router.callback_query()
    async def stale_callback(callback: CallbackQuery) -> None:
        # answer обязателен, иначе у кнопки крутится индикатор в клиенте Telegram
        await callback.answer(
            "Кнопка устарела. Нажмите /start",
            show_alert=True,
        )

    @router.message()
    async def unhandled_message(message: Message) -> None:
        # Только личные чаты, не группы
        if message.chat.type != "private":
            return
        if not message.text:
            return
        if message.text.startswith("/"):
            await message.answer("Неизвестная команда. См. /help")
            return
        await message.answer(
            "Не понял запрос. Нажмите /start или /help.",
            reply_markup=kb_start(),
        )

    return router
