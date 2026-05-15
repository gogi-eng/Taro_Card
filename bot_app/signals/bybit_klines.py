"""Публичные свечи Bybit v5 (linear / spot) без API-ключа."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

log = logging.getLogger("bot_app.signals.bybit")


BYBIT_REST = "https://api.bybit.com"


async def fetch_klines(
    session: aiohttp.ClientSession,
    symbol: str,
    start_ms: int,
    end_ms: int,
    category: str = "linear",
    interval: str = "5",
    limit: int = 1000,
) -> list[tuple[int, float, float, float, float]]:
    """
    Возвращает список (open_time_ms, open, high, low, close) по возрастанию времени.
    """
    sym = symbol.upper()
    out: list[tuple[int, float, float, float, float]] = []
    cur = start_ms
    # Bybit разбивает диапазон — идём окнами
    while cur <= end_ms and len(out) < 50000:
        params: dict[str, Any] = {
            "category": category,
            "symbol": sym,
            "interval": interval,
            "start": cur,
            "end": end_ms,
            "limit": min(limit, 1000),
        }
        url = f"{BYBIT_REST}/v5/market/kline"
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("Bybit kline %s: HTTP %s %s", sym, resp.status, body[:200])
                    break
                data = await resp.json()
        except aiohttp.ClientError as e:
            log.warning("Bybit kline network: %s", e)
            break
        lst = ((data or {}).get("result") or {}).get("list") or []
        if not lst:
            break
        # list item: [start, open, high, low, close, volume, turnover]
        batch: list[tuple[int, float, float, float, float]] = []
        for row in lst:
            try:
                t0 = int(row[0])
                o, h, low, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                batch.append((t0, o, h, low, c))
            except (IndexError, ValueError, TypeError):
                continue
        batch.sort(key=lambda x: x[0])
        if not batch:
            break
        out.extend(batch)
        # следующее окно — после последней свечи
        last_t = batch[-1][0]
        step = _interval_ms(interval)
        cur = last_t + step
        if last_t >= end_ms:
            break
    # дедуп по времени
    seen: set[int] = set()
    deduped: list[tuple[int, float, float, float, float]] = []
    for row in sorted(out, key=lambda x: x[0]):
        if row[0] in seen:
            continue
        seen.add(row[0])
        deduped.append(row)
    return deduped


def _interval_ms(interval: str) -> int:
    v = interval.strip().lower()
    if v.endswith("h"):
        return int(v[:-1] or "1") * 3600_000
    if v.endswith("d"):
        return int(v[:-1] or "1") * 86400_000
    return int(v or "5") * 60_000
