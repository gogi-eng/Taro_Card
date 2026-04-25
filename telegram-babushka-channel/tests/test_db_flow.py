"""Интеграция репозитория заказов (SQLite файл)."""

from __future__ import annotations

import pytest

from bot_app.config import Settings
from bot_app.db.models import OrderStatus
from bot_app.db.session import init_db, session_scope
from bot_app.repo import (
    create_order,
    ensure_user,
    get_order_by_id,
    mark_order_completed,
    mark_order_paid_pending,
    mark_order_paid_trc20,
    payment_tx_hash_exists,
)


@pytest.mark.asyncio
async def test_order_lifecycle(env_minimal, monkeypatch):
    monkeypatch.setenv("PAYMENT_DETAILS", "test wallet")
    s = Settings.from_env()
    await init_db(s.database_url)

    async with session_scope(s.database_url) as session:
        await ensure_user(session, telegram_id=777)
        o = await create_order(
            session,
            user_id=777,
            username="u",
            question="Что со мной будет?",
            tier_usd=5,
        )
        oid = o.id

    async with session_scope(s.database_url) as session:
        o2 = await mark_order_paid_pending(session, oid, "manual note")
        assert o2 is not None
        assert o2.status == OrderStatus.paid_pending_reading.value

    async with session_scope(s.database_url) as session:
        o3 = await mark_order_completed(session, oid, ai_reading_sent=True)
        assert o3 is not None
        assert o3.status == OrderStatus.completed.value
        assert o3.ai_reading_sent is True

    async with session_scope(s.database_url) as session:
        o4 = await get_order_by_id(session, oid)
        assert o4 is not None
        assert o4.payment_note == "manual note"


@pytest.mark.asyncio
async def test_trc20_tx_unique_flow(env_minimal, monkeypatch):
    monkeypatch.setenv("PAYMENT_DETAILS", "w")
    s = Settings.from_env()
    await init_db(s.database_url)

    tx = "f" * 64

    async with session_scope(s.database_url) as session:
        await ensure_user(session, 888)
        o = await create_order(
            session,
            user_id=888,
            username=None,
            question="Вопрос?",
            tier_usd=10,
        )
        oid = o.id

    async with session_scope(s.database_url) as session:
        await mark_order_paid_trc20(session, oid, tx, f"trc20:{tx}")

    async with session_scope(s.database_url) as session:
        assert await payment_tx_hash_exists(session, tx) is True
