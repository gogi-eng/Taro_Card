from __future__ import annotations

import html

from aiogram import Bot

from bot_app.config import Settings


async def notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for aid in settings.admin_ids:
        try:
            await bot.send_message(aid, text, parse_mode="HTML")
        except Exception:
            continue


def esc(s: str) -> str:
    return html.escape(s, quote=False)
