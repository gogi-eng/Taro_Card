"""Мониторинг каналов Telegram и ручная подача текстов сигналов."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.filters import Command, Filter
from aiogram.types import Message

from bot_app.config import Settings
from bot_app.db.signal_models import SignalPlatform
from bot_app.filters import IsAdmin
from bot_app.signals.ingest import ingest_channel_message
from bot_app.signals.report import build_daily_report_html
from bot_app.signals.runner import send_long_html

log = logging.getLogger("bot_app.handlers.signals_tracker")


class MonitoredChannelIds(Filter):
    """Пропускает channel_post только из указанных chat_id."""

    __slots__ = ("ids",)

    def __init__(self, ids: frozenset[int]) -> None:
        self.ids = ids

    async def __call__(self, message: Message) -> bool:
        return message.chat.id in self.ids


def setup(settings: Settings) -> Router:
    router = Router(name="signals_tracker")

    if not settings.signal_tracker_enabled:
        return router

    log.info(
        "Трекер сигналов включён: отчёт UTC %02d:00 → канал %s",
        settings.signal_report_hour_utc,
        settings.signal_report_channel_id,
    )
    ids = settings.signal_telegram_chat_ids
    if not ids:
        log.warning(
            "SIGNAL_TELEGRAM_CHAT_IDS пуст — посты каналов не собираются автоматически. "
            "Используйте /signals_manual или задайте id каналов в .env."
        )
    if ids:

        @router.channel_post(MonitoredChannelIds(ids))
        async def on_channel_post(message: Message) -> None:
            raw = message.text or message.caption or ""
            if not raw.strip():
                return
            chat = message.chat
            title = (chat.title or chat.username or str(chat.id))[:250]
            posted_at = message.date
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)

            pid, status = await ingest_channel_message(
                settings.database_url,
                platform=SignalPlatform.telegram.value,
                external_id=str(chat.id),
                display_name=title,
                raw_text=raw,
                posted_at=posted_at,
                telegram_chat_id=chat.id,
                telegram_message_id=message.message_id,
            )
            if pid == -1:
                return
            log.info(
                "Сигнал из канала %s msg=%s → ps=%s (%s)",
                chat.id,
                message.message_id,
                pid,
                status,
            )

    is_admin = IsAdmin(settings)

    @router.message(is_admin, Command("signals_manual"))
    async def cmd_signals_manual(message: Message) -> None:
        """Ответьте командой на сообщение с текстом сигнала или добавьте текст в ту же строку."""
        lines = (message.text or "").split(maxsplit=1)
        raw = lines[1].strip() if len(lines) > 1 else ""
        if message.reply_to_message:
            raw = (
                message.reply_to_message.text
                or message.reply_to_message.caption
                or ""
            ).strip()
        if not raw:
            await message.answer(
                "Использование: ответьте на пост сигнала командой /signals_manual "
                "или /signals_manual текст…"
            )
            return
        title = "manual:" + str(message.from_user.id if message.from_user else "unknown")
        posted_at = datetime.now(timezone.utc)
        pid, status = await ingest_channel_message(
            settings.database_url,
            platform=SignalPlatform.manual.value,
            external_id=title,
            display_name=f"manual @{message.from_user.username or message.from_user.id}",
            raw_text=raw,
            posted_at=posted_at,
        )
        await message.answer(f"Записано parsed_signal #{pid}: {status}")

    @router.message(is_admin, Command("signals_note"))
    async def cmd_signals_note(message: Message) -> None:
        await message.answer(
            "<b>TikTok</b>: автоматического сбора нет. Экспортируйте тексты во внешний файл "
            "и дублируйте вручную через <code>/signals_manual</code> или настройте свой "
            "скрипт импорта в БД.\n"
            "<b>Telegram</b>: добавьте бота админом канала и задайте "
            "<code>SIGNAL_TELEGRAM_CHAT_IDS</code>.",
            parse_mode="HTML",
        )

    @router.message(is_admin, Command("signals_report_now"))
    async def cmd_signals_report_now(message: Message, bot: Bot) -> None:
        html = await build_daily_report_html(
            settings.database_url,
            min_signals=settings.signal_min_signals_for_ranking,
        )
        await send_long_html(bot, message.chat.id, html)

    return router
