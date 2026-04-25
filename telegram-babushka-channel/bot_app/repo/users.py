from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_app.db.models import UserProfile


async def ensure_user(session: AsyncSession, telegram_id: int) -> UserProfile:
    r = await session.execute(select(UserProfile).where(UserProfile.telegram_id == telegram_id))
    u = r.scalar_one_or_none()
    if u is None:
        u = UserProfile(telegram_id=telegram_id)
        session.add(u)
        await session.flush()
    return u


async def set_agreed_terms(session: AsyncSession, telegram_id: int) -> None:
    u = await ensure_user(session, telegram_id)
    u.agreed_terms_at = datetime.now(timezone.utc)
