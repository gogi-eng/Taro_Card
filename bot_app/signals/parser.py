"""Разбор типичных формулировок сигналов в Telegram (LONG/SHORT, Entry, TP, SL)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Биржевой тикер для Bybit linear (суффикс USDT)
_SYMBOL_WORD = r"[A-Z]{2,15}"
_PAIR_RE = re.compile(rf"\b({_SYMBOL_WORD})\s*/?\s*USDT\b|\b({_SYMBOL_WORD})USDT\b", re.I)

_ENTRY_RE = re.compile(
    r"(?:ENTRY|ВХОД|Вход|E\s*[:\.\s])\s*[:\.]?\s*(\d+(?:\.\d+)?)",
    re.I,
)
# Первый TP / TP1 / цели
_TP_RE = re.compile(
    r"(?:TP|ТП|T\.?\s*P\.?|TARGET|ЦЕЛЬ)\s*(?:1|I|①)?\s*[:\.]?\s*(\d+(?:\.\d+)?)",
    re.I,
)
_SL_RE = re.compile(
    r"(?:SL|СТОП|STOP|S\s*&?\s*L)\s*[:\.]?\s*(\d+(?:\.\d+)?)",
    re.I,
)


@dataclass(frozen=True)
class ParsedParts:
    symbol: str | None  # например BTCUSDT
    side: str | None  # long | short
    entry: float | None
    tp1: float | None
    sl: float | None
    note: str | None


def _normalize_symbol(raw: str) -> str:
    s = raw.upper().replace(" ", "")
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


def _detect_side(text: str) -> str | None:
    t = text.upper()
    long_hits = (" LONG", "ЛОНГ", " BUY", "ПОКУП", "LONG ", "SHORT")
    # осторожно: SHORT содержится в LONG? no
    if re.search(r"\b(LONG|ЛОНГ|BUY|ПОКУПК)\b", t) and not re.search(
        r"\b(SHORT|ШОРТ|SELL|ПРОДАЖ)\b", t
    ):
        return "long"
    if re.search(r"\b(SHORT|ШОРТ|SELL|ПРОДАЖ)\b", t):
        return "short"
    return None


def parse_signal_text(text: str) -> ParsedParts:
    text = (text or "").strip()
    if len(text) < 4:
        return ParsedParts(None, None, None, None, None, "пусто")

    symbol: str | None = None
    m = _PAIR_RE.search(text)
    if m:
        base = (m.group(1) or m.group(2) or "").upper()
        if base:
            symbol = _normalize_symbol(base)

    side = _detect_side(text)

    entry: float | None = None
    em = _ENTRY_RE.search(text)
    if em:
        try:
            entry = float(em.group(1))
        except ValueError:
            pass

    tp1: float | None = None
    for tm in _TP_RE.finditer(text):
        try:
            tp1 = float(tm.group(1))
            break
        except ValueError:
            continue

    sl: float | None = None
    sm = _SL_RE.search(text)
    if sm:
        try:
            sl = float(sm.group(1))
        except ValueError:
            pass

    note: str | None = None
    if not symbol:
        note = "нет пары USDT"
    elif not side:
        note = "нет LONG/SHORT"
    elif entry is None or tp1 is None or sl is None:
        note = "не хватает entry/tp/sl"
    else:
        if side == "long" and not (sl < entry < tp1):
            note = "long: ожидалось SL<Entry<TP"
        elif side == "short" and not (tp1 < entry < sl):
            note = "short: ожидалось TP<Entry<SL"

    ok = note is None
    return ParsedParts(symbol, side, entry, tp1, sl, None if ok else note)
