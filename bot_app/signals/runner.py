"""Фоновые задачи: закрытие сигналов и ежедневный отчёт в канал."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot

from bot_app.config import Settings
from bot_app.signals.report import build_daily_report_html
from bot_app.signals.resolver import resolve_open_signals

log = logging.getLogger("bot_app.signals.runner")


async def _sleep_until_next_utc_hour(hour: int) -> None:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    sec = max(1.0, (target - now).total_seconds())
    log.info("Следующий отчёт сигналов через %.0f с (UTC %02d:00)", sec, hour)
    await asyncio.sleep(sec)


async def send_long_html(bot: Bot, chat_id: int, html: str) -> None:
    limit = 3800
    if len(html) <= limit:
        await bot.send_message(chat_id, html, parse_mode="HTML")
        return
    buf: list[str] = []
    size = 0
    for line in html.split("\n"):
        if size + len(line) + 1 > limit and buf:
            await bot.send_message(chat_id, "\n".join(buf), parse_mode="HTML")
            buf = []
            size = 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        await bot.send_message(chat_id, "\n".join(buf), parse_mode="HTML")


async def signal_background(bot: Bot, settings: Settings) -> None:
    if not settings.signal_tracker_enabled:
        return
    cid = settings.signal_report_channel_id
    if cid is None:
        log.error("SIGNAL_TRACKER_ENABLED без SIGNAL_REPORT_CHANNEL_ID")
        return

    async with aiohttp.ClientSession() as http:

        async def resolver_loop() -> None:
            while True:
                try:
                    await resolve_open_signals(
                        settings.database_url,
                        http,
                        bybit_category=settings.signal_bybit_category,
                        max_hold_hours=settings.signal_max_hold_hours,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("resolver_loop")
                await asyncio.sleep(settings.signal_resolve_interval_sec)

        async def reporter_loop() -> None:
            await asyncio.sleep(10)
            while True:
                try:
                    await _sleep_until_next_utc_hour(settings.signal_report_hour_utc)
                    html = await build_daily_report_html(
                        settings.database_url,
                        min_signals=settings.signal_min_signals_for_ranking,
                    )
                    await send_long_html(bot, cid, html)
                    log.info("Отчёт по сигналам отправлен в %s", cid)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("reporter_loop")

        try:
            await asyncio.gather(resolver_loop(), reporter_loop())
        except asyncio.CancelledError:
            pass


def start_signal_background(bot: Bot, settings: Settings) -> asyncio.Task[None]:
    return asyncio.create_task(signal_background(bot, settings), name="signal_tracker")
