from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot_app.db.base import Base


class OrderStatus(str, enum.Enum):
    awaiting_payment = "awaiting_payment"
    paid_pending_reading = "paid_pending_reading"
    completed = "completed"
    cancelled = "cancelled"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    agreed_terms_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    readings: Mapped[list["ReadingEntry"]] = relationship(back_populates="user")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.telegram_id"))
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    tier_usd: Mapped[int] = mapped_column(Integer)  # 5 or 10
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.awaiting_payment.value)
    payment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    ai_reading_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["UserProfile"] = relationship(back_populates="orders")
    readings: Mapped[list["ReadingEntry"]] = relationship(back_populates="order")


class ReadingEntry(Base):
    __tablename__ = "reading_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.telegram_id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # free_1card | order_ai | order_manual
    kind: Mapped[str] = mapped_column(String(32), index=True)
    order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["UserProfile"] = relationship(back_populates="readings")
    order: Mapped["Order | None"] = relationship(back_populates="readings")
