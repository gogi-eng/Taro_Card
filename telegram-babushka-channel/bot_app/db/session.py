from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot_app.db.base import Base
from bot_app.db import models  # noqa: F401 — регистрация моделей

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_parent_dir_exists(database_url: str) -> None:
    """Создаёт родительский каталог для файла SQLite (относительный и абсолютный путь)."""
    if "sqlite" not in database_url:
        return
    try:
        u = make_url(database_url)
    except Exception:
        return
    if not u.database:
        return
    p = Path(u.database)
    if not p.is_absolute():
        p = Path.cwd() / p
    parent = p.parent
    if parent and parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)


def _ensure_engine(database_url: str):
    global _engine, _session_factory
    if _engine is None:
        _ensure_sqlite_parent_dir_exists(database_url)
        _engine = create_async_engine(database_url, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    _ensure_engine(database_url)
    assert _session_factory is not None
    return _session_factory


def _migrate_sqlite_orders(sync_conn) -> None:
    """Добавляет колонки к существующей таблице orders (SQLite)."""
    from sqlalchemy import inspect, text

    insp = inspect(sync_conn)
    try:
        cols = {c["name"] for c in insp.get_columns("orders")}
    except Exception:
        return
    if "payment_tx_hash" not in cols:
        sync_conn.execute(
            text("ALTER TABLE orders ADD COLUMN payment_tx_hash VARCHAR(128)")
        )
    if "ai_reading_sent" not in cols:
        sync_conn.execute(
            text("ALTER TABLE orders ADD COLUMN ai_reading_sent BOOLEAN NOT NULL DEFAULT 0")
        )


async def init_db(database_url: str) -> None:
    engine = _ensure_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in database_url:
            await conn.run_sync(_migrate_sqlite_orders)


@asynccontextmanager
async def session_scope(
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory(database_url)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
