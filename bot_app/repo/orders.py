from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_app.db.models import Order, OrderStatus


async def get_active_order_for_user(session: AsyncSession, user_id: int) -> Order | None:
    r = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .where(
            Order.status.in_(
                [
                    OrderStatus.awaiting_payment.value,
                    OrderStatus.paid_pending_reading.value,
                ]
            )
        )
        .order_by(Order.id.desc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def create_order(
    session: AsyncSession,
    *,
    user_id: int,
    username: str | None,
    question: str,
    tier_usd: int,
) -> Order:
    o = Order(
        user_id=user_id,
        username=username,
        question=question.strip(),
        tier_usd=tier_usd,
        status=OrderStatus.awaiting_payment.value,
    )
    session.add(o)
    await session.flush()
    return o


async def mark_order_paid_pending(
    session: AsyncSession, order_id: int, payment_note: str | None
) -> Order | None:
    r = await session.execute(select(Order).where(Order.id == order_id))
    o = r.scalar_one_or_none()
    if o is None:
        return None
    o.status = OrderStatus.paid_pending_reading.value
    o.payment_note = payment_note
    o.updated_at = datetime.now(timezone.utc)
    return o


async def mark_order_paid_trc20(
    session: AsyncSession,
    order_id: int,
    tx_hash: str,
    payment_note: str | None,
) -> Order | None:
    r = await session.execute(select(Order).where(Order.id == order_id))
    o = r.scalar_one_or_none()
    if o is None:
        return None
    o.status = OrderStatus.paid_pending_reading.value
    o.payment_tx_hash = tx_hash
    o.payment_note = payment_note
    o.updated_at = datetime.now(timezone.utc)
    return o


async def payment_tx_hash_exists(session: AsyncSession, tx_hash: str) -> bool:
    r = await session.execute(select(Order.id).where(Order.payment_tx_hash == tx_hash).limit(1))
    return r.scalar_one_or_none() is not None


async def mark_order_completed(
    session: AsyncSession, order_id: int, *, ai_reading_sent: bool = False
) -> Order | None:
    r = await session.execute(select(Order).where(Order.id == order_id))
    o = r.scalar_one_or_none()
    if o is None:
        return None
    o.status = OrderStatus.completed.value
    o.ai_reading_sent = ai_reading_sent
    o.updated_at = datetime.now(timezone.utc)
    return o


async def cancel_all_active_orders_for_user(session: AsyncSession, user_id: int) -> int:
    """Отменяет все заказы пользователя в статусах awaiting_payment и paid_pending_reading."""
    r = await session.execute(
        select(Order).where(
            Order.user_id == user_id,
            Order.status.in_(
                [
                    OrderStatus.awaiting_payment.value,
                    OrderStatus.paid_pending_reading.value,
                ]
            ),
        )
    )
    rows = list(r.scalars().all())
    now = datetime.now(timezone.utc)
    for o in rows:
        o.status = OrderStatus.cancelled.value
        o.updated_at = now
    return len(rows)


async def cancel_order_by_user(session: AsyncSession, order_id: int, user_id: int) -> bool:
    r = await session.execute(select(Order).where(Order.id == order_id, Order.user_id == user_id))
    o = r.scalar_one_or_none()
    if o is None:
        return False
    if o.status in (OrderStatus.completed.value, OrderStatus.cancelled.value):
        return False
    o.status = OrderStatus.cancelled.value
    o.updated_at = datetime.now(timezone.utc)
    return True


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    r = await session.execute(select(Order).where(Order.id == order_id))
    return r.scalar_one_or_none()


async def user_owns_order(order: Order, user_id: int) -> bool:
    return order.user_id == user_id


async def list_pending_orders(session: AsyncSession, limit: int = 20) -> list[Order]:
    r = await session.execute(
        select(Order)
        .where(Order.status == OrderStatus.paid_pending_reading.value)
        .order_by(Order.id.asc())
        .limit(limit)
    )
    return list(r.scalars().all())
