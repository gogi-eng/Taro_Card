"""Оплата в Telegram Stars (XTR) за заказ: счёт, разбор payload."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiogram.types import LabeledPrice, Message

if TYPE_CHECKING:
    from bot_app.config import Settings
    from bot_app.db.models import Order

_PAYLOAD_RE = re.compile(r"^b(\d+)u(\d+)$")


def parse_stars_order_payload(raw: str) -> tuple[int, int] | None:
    m = _PAYLOAD_RE.match((raw or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


async def send_stars_invoice(
    where: Message,
    *,
    order: "Order",
    user_telegram_id: int,
    settings: "Settings",
) -> None:
    if not settings.stars_payments:
        return
    amt = settings.stars_tier5 if order.tier_usd <= 5 else settings.stars_tier10
    pl = f"b{order.id}u{user_telegram_id}"
    if len(pl.encode("utf-8")) > 128:
        raise ValueError("invoice payload too long")
    await where.answer_invoice(
        title="Расклад Таро",
        description=f"Заказ #{order.id} ({order.tier_usd} USD). Оплата в Stars ⭐",
        payload=pl,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Расклад", amount=amt)],
    )
