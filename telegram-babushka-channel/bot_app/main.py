from __future__ import annotations

import asyncio
import logging
import sys

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
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
