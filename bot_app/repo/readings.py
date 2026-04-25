from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_app.db.models import ReadingEntry

KIND_FREE = "free_1card"
KIND_ORDER_AI = "order_ai"
KIND_ORDER_MANUAL = "order_manual"


async def add_reading_entry(
    session: AsyncSession,
    *,
    user_id: int,
    question: str,
    answer: str,
    kind: str,
    order_id: int | None = None,
) -> ReadingEntry:
    e = ReadingEntry(
        user_id=user_id,
        question=question.strip()[:4000],
        answer=answer.strip()[:12000],
        kind=kind,
        order_id=order_id,
    )
    session.add(e)
    await session.flush()
    return e


async def list_last_readings_for_user(
    session: AsyncSession, user_id: int, limit: int = 3
) -> list[ReadingEntry]:
    r = await session.execute(
        select(ReadingEntry)
        .where(ReadingEntry.user_id == user_id)
        .order_by(desc(ReadingEntry.id))
        .limit(limit)
    )
    return list(r.scalars().all())


def _d_at_utc(ts: datetime | None) -> dt.date | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date()


async def count_free_today_utc(session: AsyncSession, user_id: int) -> int:
    today = datetime.now(timezone.utc).date()
    r = await session.execute(
        select(ReadingEntry)
        .where(ReadingEntry.user_id == user_id, ReadingEntry.kind == KIND_FREE)
        .order_by(ReadingEntry.id.desc())
        .limit(32)
    )
    n = 0
    for row in r.scalars().all():
        d = _d_at_utc(row.created_at)
        if d == today:
            n += 1
    return n


async def can_use_free_today_utc(
    session: AsyncSession, user_id: int, *, per_day: int
) -> bool:
    if per_day <= 0:
        return False
    if await count_free_today_utc(session, user_id) >= per_day:
        return False
    return True


