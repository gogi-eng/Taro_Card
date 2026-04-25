"""Общие фикстуры: тестовая БД и переменные окружения."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def env_minimal(monkeypatch, tmp_path):
    """Минимальный env для Settings (без реальных секретов)."""
    db = tmp_path / "test.db"
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST-TOKEN")
    monkeypatch.setenv("ADMIN_IDS", "999001")
    monkeypatch.setenv("PAYMENT_DETAILS", "USDT test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("AUTO_USDT_VERIFY_TRC20", "false")
    monkeypatch.setenv("AUTO_READING_AI", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRON_USDT_RECEIVER", raising=False)
