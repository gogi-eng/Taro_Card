"""Закрытие открытых сигналов по истории цены (консервативно: в одной свече SL раньше TP)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot_app.db.session import session_scope
from bot_app.db.signal_models import ParsedSignal, ParsedSignalStatus, SignalPost, SignalSource
from bot_app.signals.bybit_klines import fetch_klines

log = logging.getLogger("bot_app.signals.resolver")


def _to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _simulate_long(sl: float, tp: float, candles: list[tuple[int, float, float, float, float]]) -> str | None:
    """Возвращает 'sl' или 'tp' при первом касании; None если нет."""
    for _t, _o, high, low, _c in candles:
        hit_sl = low <= sl
        hit_tp = high >= tp
        if hit_sl and hit_tp:
            return "sl"  # консервативно
        if hit_sl:
            return "sl"
        if hit_tp:
            return "tp"
    return None


def _simulate_short(sl: float, tp: float, candles: list[tuple[int, float, float, float, float]]) -> str | None:
    for _t, _o, high, low, _c in candles:
        hit_sl = high >= sl
        hit_tp = low <= tp
        if hit_sl and hit_tp:
            return "sl"
        if hit_sl:
            return "sl"
        if hit_tp:
            return "tp"
    return None


async def resolve_open_signals(
    database_url: str,
    http: aiohttp.ClientSession,
    *,
    bybit_category: str,
    max_hold_hours: int,
) -> int:
    """
    Обновляет открытые сигналы. Возвращает число изменённых записей.
    """
    now = datetime.now(timezone.utc)
    updated = 0
    async with session_scope(database_url) as session:
        q = await session.execute(
            select(ParsedSignal)
            .where(ParsedSignal.status == ParsedSignalStatus.open.value)
            .options(
                selectinload(ParsedSignal.post).selectinload(SignalPost.source)
            )
        )
        rows: list[ParsedSignal] = list(q.scalars().all())

    for ps in rows:
        if not ps.symbol or not ps.side or ps.entry is None or ps.tp1 is None or ps.sl is None:
            async with session_scope(database_url) as session:
                att = await session.get(ParsedSignal, ps.id)
                if att and att.status == ParsedSignalStatus.open.value:
                    att.status = ParsedSignalStatus.parsing_failed.value
                    att.resolved_at = now
                    att.parse_note = (att.parse_note or "") + "; incomplete"
                    updated += 1
            continue

        post = ps.post
        posted_at = post.posted_at
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        deadline = posted_at + timedelta(hours=max_hold_hours)
        end = min(now, deadline)
        start_ms = _to_ms(posted_at)
        end_ms = _to_ms(end)

        candles = await fetch_klines(
            http, ps.symbol, start_ms, end_ms, category=bybit_category
        )
        first: str | None = None
        if ps.side == "long":
            first = _simulate_long(ps.sl, ps.tp1, candles)
        elif ps.side == "short":
            first = _simulate_short(ps.sl, ps.tp1, candles)

        async with session_scope(database_url) as session:
            att = await session.get(ParsedSignal, ps.id)
            if not att or att.status != ParsedSignalStatus.open.value:
                continue
            if first == "tp":
                att.status = ParsedSignalStatus.tp.value
                att.first_hit = "tp"
                att.resolved_at = now
                updated += 1
            elif first == "sl":
                att.status = ParsedSignalStatus.sl.value
                att.first_hit = "sl"
                att.resolved_at = now
                updated += 1
            elif now >= deadline:
                att.status = ParsedSignalStatus.expired.value
                att.resolved_at = now
                att.parse_note = (att.parse_note or "") + f"; no hit in {max_hold_hours}h"
                updated += 1

    if updated:
        log.info("Сигналов обновлено: %s", updated)
    return updated
