"""Точечные проверки разбора сигналов (без Telegram)."""

from bot_app.signals.parser import parse_signal_text


def test_parse_long_btcusdt_ok():
    text = """
    BTCUSDT LONG
    Entry: 95000
    TP: 97000
    SL: 94000
    """
    p = parse_signal_text(text)
    assert p.symbol == "BTCUSDT"
    assert p.side == "long"
    assert p.entry == 95000.0
    assert p.tp1 == 97000.0
    assert p.sl == 94000.0
    assert p.note is None


def test_parse_short_eth():
    text = "ETH/USDT SHORT Entry 3400 TP 3300 SL 3500"
    p = parse_signal_text(text)
    assert p.symbol == "ETHUSDT"
    assert p.side == "short"
    assert p.note is None


def test_parse_invalid_levels_long():
    text = "BTC LONG entry 100 tp 90 sl 95"  # tp ниже entry для лонга
    p = parse_signal_text(text)
    assert p.note is not None


def test_resolver_long_sl_before_tp():
    from bot_app.signals.resolver import _simulate_long

    candles = [(0, 0, 101.0, 99.5, 100.5)]  # только TP
    assert _simulate_long(sl=99.0, tp=101.0, candles=candles) == "tp"

    candles2 = [(0, 0, 101.0, 98.0, 100)]  # и SL и TP в одной свече → sl
    assert _simulate_long(sl=99.0, tp=101.0, candles=candles2) == "sl"
