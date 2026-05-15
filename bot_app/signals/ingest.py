"""Сохранение поста и распарсенного сигнала."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from bot_app.db.session import session_scope
from bot_app.db.signal_models import (
    ParsedSignal,
    ParsedSignalStatus,
    SignalPost,
    SignalSource,
)
from bot_app.signals.parser import parse_signal_text


async def ingest_channel_message(
    database_url: str,
    *,
    platform: str,
    external_id: str,
    display_name: str,
    raw_text: str,
    posted_at: datetime,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
) -> tuple[int, str]:
    """
    Возвращает (parsed_signal_id или post id placeholder, статус текстом).
    """
    async with session_scope(database_url) as session:
        if telegram_chat_id is not None and telegram_message_id is not None:
            dup = await session.execute(
                select(SignalPost).where(
                    SignalPost.telegram_chat_id == telegram_chat_id,
                    SignalPost.telegram_message_id == telegram_message_id,
                )
            )
            if dup.scalar_one_or_none():
                return (-1, "duplicate")

        src_q = await session.execute(
            select(SignalSource).where(
                SignalSource.platform == platform,
                SignalSource.external_id == external_id,
            )
        )
        src = src_q.scalar_one_or_none()
        if not src:
            src = SignalSource(
                platform=platform,
                external_id=external_id,
                display_name=display_name[:255],
            )
            session.add(src)
            await session.flush()
        else:
            src.display_name = display_name[:255]

        post = SignalPost(
            source_id=src.id,
            raw_text=raw_text[:12000],
            posted_at=posted_at,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        session.add(post)
        await session.flush()

        parsed_fields = parse_signal_text(raw_text)
        ps = ParsedSignal(
            post_id=post.id,
            symbol=parsed_fields.symbol,
            side=parsed_fields.side,
            entry=parsed_fields.entry,
            tp1=parsed_fields.tp1,
            sl=parsed_fields.sl,
            status=(
                ParsedSignalStatus.open.value
                if parsed_fields.note is None
                else ParsedSignalStatus.parsing_failed.value
            ),
            parse_note=parsed_fields.note,
        )
        session.add(ps)
        await session.flush()
        return (
            ps.id,
            "open" if parsed_fields.note is None else f"failed: {parsed_fields.note}",
        )
