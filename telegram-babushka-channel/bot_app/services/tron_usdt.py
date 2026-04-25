"""Проверка входящего USDT TRC20 по хешу транзакции (Tron mainnet, TronScan API)."""

from __future__ import annotations

import re
from typing import Any

import aiohttp

USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONSCAN_TX_INFO = "https://apilist.tronscanapi.com/api/transaction-info"


def normalize_tx_hash(raw: str) -> str | None:
    s = raw.strip().lower().removeprefix("0x")
    if re.fullmatch(r"[0-9a-f]{64}", s):
        return s
    return None


def _base58_eq(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def _to_sun(amount_raw: str) -> int | None:
    """USDT TRC20: 6 знаков; в API часто целое число sun или строка с точкой."""
    s = str(amount_raw).strip().replace(",", ".")
    if not s:
        return None
    if "." in s:
        try:
            whole, frac = s.split(".", 1)
            frac = (frac + "000000")[:6]
            return int(whole) * 1_000_000 + int(frac.ljust(6, "0")[:6])
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        return None


async def verify_usdt_trc20_incoming(
    *,
    tx_hash: str,
    receiver_base58: str,
    min_usdt: float,
    trongrid_api_key: str | None = None,
) -> tuple[bool, str]:
    """
    Проверяет входящий USDT TRC20 на кошелёк receiver_base58 >= min_usdt.
    Использует публичный TronScan API (при сбое — сообщение об ошибке).
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if trongrid_api_key:
        headers["TRON-PRO-API-KEY"] = trongrid_api_key

    timeout = aiohttp.ClientTimeout(total=35)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(
                TRONSCAN_TX_INFO,
                params={"hash": tx_hash},
            ) as resp:
                if resp.status != 200:
                    return False, f"TronScan: HTTP {resp.status}. Проверьте хеш на tronscan.org."
                data: Any = await resp.json()
    except aiohttp.ClientError as e:
        return False, f"Сеть: {e!s}. Повторите позже."

    if data.get("contractRet") == "REVERT" or data.get("result") == "FAILED":
        return False, "Транзакция в сети помечена как неуспешная."

    transfers = data.get("trc20TransferInfo") or data.get("trc20_transfer_info") or []
    if isinstance(transfers, dict):
        transfers = [transfers]
    min_sun = int(round(min_usdt * 1_000_000))

    for t in transfers:
        if not isinstance(t, dict):
            continue
        to_addr = t.get("to_address") or t.get("toAddress") or ""
        contract = t.get("contract_address") or t.get("contractAddress") or ""
        if not _base58_eq(contract, USDT_TRC20_CONTRACT):
            continue
        if not _base58_eq(to_addr, receiver_base58):
            continue
        amt_raw = t.get("amount_str") or t.get("amount") or t.get("quant") or "0"
        sun = _to_sun(str(amt_raw))
        if sun is None:
            continue
        if sun >= min_sun:
            return True, ""

    return (
        False,
        "Нет входящего USDT TRC20 на ваш кошелёк из PAYMENT_DETAILS или сумма меньше заказа. "
        "Проверьте сеть TRC20 и адрес получателя.",
    )
