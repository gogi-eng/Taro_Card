"""Быстрый ответ на callback — иначе Telegram: «query is too old»."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

log = logging.getLogger("bot_app.callbacks")


async def ack_callback(
    callback: CallbackQuery,
    *,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    """
    Сразу снимает «часики» у кнопки. Вызывать первой строкой в каждом callback.
    Просроченный query гасим тихо. Опционально text/show_alert — одно и то же, что
    у :meth:`aiogram.types.CallbackQuery.answer`.
    """
    try:
        if text is not None or show_alert:
            await callback.answer(text=text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramBadRequest as e:
        m = (e.message or str(e) or "").lower()
        if "query is too old" in m or "response timeout" in m or "invalid" in m:
            log.warning("Callback answer просрочен/невалиден: %s", e)
            return
        raise
