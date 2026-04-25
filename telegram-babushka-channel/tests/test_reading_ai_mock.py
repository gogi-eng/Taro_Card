"""Мок OpenAI для generate_tarot_reading."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_app.services.reading_ai import generate_tarot_reading


@pytest.mark.asyncio
async def test_generate_tarot_reading_mock():
    fake_message = MagicMock()
    fake_message.content = "Тестовый расклад: карты говорят о спокойствии."

    fake_choice = MagicMock()
    fake_choice.message = fake_message

    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]

    mock_create = AsyncMock(return_value=fake_resp)

    with patch("bot_app.services.reading_ai.AsyncOpenAI") as m_client:
        m_inst = MagicMock()
        m_inst.chat.completions.create = mock_create
        m_client.return_value = m_inst

        text, err = await generate_tarot_reading(
            api_key="sk-test",
            model="gpt-4o-mini",
            base_url=None,
            question="Судьба?",
            tier_usd=5,
        )

    assert err == ""
    assert "Тестовый расклад" in (text or "")
    mock_create.assert_awaited_once()
