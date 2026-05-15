"""Модели для учёта торговых сигналов из Telegram / внешних источников."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot_app.db.base import Base


class SignalPlatform(str, enum.Enum):
    telegram = "telegram"
    tiktok = "tiktok"
    manual = "manual"


class ParsedSignalStatus(str, enum.Enum):
    open = "open"
    tp = "tp"
    sl = "sl"
    expired = "expired"
    parsing_failed = "parsing_failed"


class SignalSource(Base):
    """Канал / аккаунт, откуда приходят сигналы."""

    __tablename__ = "signal_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    posts: Mapped[list["SignalPost"]] = relationship(back_populates="source")


class SignalPost(Base):
    """Сырой пост (сообщение), из которого парсится сигнал."""

    __tablename__ = "signal_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("signal_sources.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Для Telegram: id чата и сообщения (уникальность)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped["SignalSource"] = relationship(back_populates="posts")
    parsed: Mapped[list["ParsedSignal"]] = relationship(back_populates="post")


class ParsedSignal(Base):
    """
    Один торговый сигнал после разбора текста.
    Результат: TP1 до SL — выигрыш; SL раньше — проигрыш; ничего за max_hold — expired.
    """

    __tablename__ = "parsed_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("signal_posts.id"), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)  # long | short
    entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp1: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ParsedSignalStatus.open.value, index=True
    )
    first_hit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # tp | sl
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    parse_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    post: Mapped["SignalPost"] = relationship(back_populates="parsed")
