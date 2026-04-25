"""История и бесплатные расклады в БД."""

from __future__ import annotations

import pytest

from bot_app.config import Settings
from bot_app.db.session import init_db, session_scope
from bot_app.repo.readings import (
    KIND_FREE,
    KIND_ORDER_AI,
    add_reading_entry,
    can_use_free_today_utc,
    count_free_today_utc,
    list_last_readings_for_user,
)
from bot_app.repo.users import ensure_user


@pytest.mark.asyncio
async def test_reading_entries_and_free_limit(env_minimal, monkeypatch):
    monkeypatch.setenv("PAYMENT_DETAILS", "test wallet")
    s = Settings.from_env()
    await init_db(s.database_url)

    async with session_scope(s.database_url) as session:
        await ensure_user(session, telegram_id=777)
        await add_reading_entry(
            session,
            user_id=777,
            question="Вопрос?",
            answer="Ответ.",
            kind=KIND_FREE,
        )
    async with session_scope(s.database_url) as session:
        n = await count_free_today_utc(session, 777)
        assert n == 1
        ok = await can_use_free_today_utc(session, 777, per_day=1)
        assert ok is False
        ok2 = await can_use_free_today_utc(session, 777, per_day=2)
        assert ok2 is True

    async with session_scope(s.database_url) as session:
        await add_reading_entry(
            session,
            user_id=777,
            question="Платный",
            answer="Текст AI",
            kind=KIND_ORDER_AI,
            order_id=None,
        )
        rows = await list_last_readings_for_user(session, 777, limit=3)
        assert len(rows) == 2
