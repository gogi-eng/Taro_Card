from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import suppress

from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot_app.config import Settings, require_admins
from bot_app.db.session import init_db
from bot_app.handlers import setup_routers


async def _run() -> None:
    # Загружаем .env из корня проекта (рядом с пакетом bot_app), не только из cwd.
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
    load_dotenv()
    settings = Settings.from_env()
    require_admins(settings)

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("bot_app")

    await init_db(settings.database_url)
    log.info("База данных инициализирована.")

    bot = Bot(settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(setup_routers(settings))

    log.info("Запуск long polling…")
    allowed = dp.resolve_used_update_types()
    if "message" not in allowed:
        # Иначе Telegram не присылает сообщения/команды — бот «молчит».
        allowed = sorted({*allowed, "message", "callback_query", "pre_checkout_query"})
        log.warning(
            "В сети allowed_updates не было «message» — расширено до: %s", allowed
        )
    log.info("allowed_updates для getUpdates: %s", allowed)

    if settings.signal_tracker_enabled and "channel_post" not in allowed:
        allowed = sorted({*allowed, "channel_post"})
        log.info("Трекер сигналов: добавлен channel_post → %s", allowed)

    signal_task: asyncio.Task[None] | None = None
    if settings.signal_tracker_enabled:
        from bot_app.signals.runner import start_signal_background

        signal_task = start_signal_background(bot, settings)

    if os.environ.get("LOG_INCOMING_MESSAGES", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):

        @dp.message.outer_middleware()
        async def _log_incoming(handler, event, data):
            if event.text:
                log.info(
                    "Входящее: user=%s chat=%s type=%s text=%r",
                    event.from_user.id if event.from_user else None,
                    event.chat.id,
                    event.chat.type,
                    (event.text or "")[:400],
                )
            return await handler(event, data)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=allowed)
    finally:
        if signal_task:
            signal_task.cancel()
            with suppress(asyncio.CancelledError):
                await signal_task
        await bot.session.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
