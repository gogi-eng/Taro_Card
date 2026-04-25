"""Мок aiohttp — проверка verify_usdt_trc20_incoming без сети."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_app.services.tron_usdt import USDT_TRC20_CONTRACT, verify_usdt_trc20_incoming


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_verify_usdt_success_mocked_http():
    receiver = "TTvB9g2dtoWHb3GLduAzbqTtPXBLNs5hr4"
    payload = {
        "trc20TransferInfo": [
            {
                "to_address": receiver,
                "contract_address": USDT_TRC20_CONTRACT,
                "amount_str": "5000000",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=payload)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_AsyncCM(mock_resp))

    mock_client_cm = _AsyncCM(mock_session)

    with patch("bot_app.services.tron_usdt.aiohttp.ClientSession", return_value=mock_client_cm):
        ok, err = await verify_usdt_trc20_incoming(
            tx_hash="a" * 64,
            receiver_base58=receiver,
            min_usdt=5.0,
            trongrid_api_key=None,
        )

    assert ok is True
    assert err == ""


@pytest.mark.asyncio
async def test_verify_usdt_wrong_amount_mocked():
    receiver = "TTvB9g2dtoWHb3GLduAzbqTtPXBLNs5hr4"
    payload = {
        "trc20TransferInfo": [
            {
                "to_address": receiver,
                "contract_address": USDT_TRC20_CONTRACT,
                "amount_str": "1000000",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=payload)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_AsyncCM(mock_resp))
    mock_client_cm = _AsyncCM(mock_session)

    with patch("bot_app.services.tron_usdt.aiohttp.ClientSession", return_value=mock_client_cm):
        ok, err = await verify_usdt_trc20_incoming(
            tx_hash="c" * 64,
            receiver_base58=receiver,
            min_usdt=5.0,
            trongrid_api_key=None,
        )

    assert ok is False
    assert "Нет входящего" in err or "меньше" in err
