from bot_app.services.tron_usdt import USDT_TRC20_CONTRACT, normalize_tx_hash


def test_normalize_tx_hash_valid():
    h = "a" * 64
    assert normalize_tx_hash(h) == h
    assert normalize_tx_hash("0x" + h) == h


def test_normalize_tx_hash_invalid():
    assert normalize_tx_hash("short") is None
    assert normalize_tx_hash("g" * 64) is None


def test_usdt_contract_constant():
    assert USDT_TRC20_CONTRACT.startswith("T")
