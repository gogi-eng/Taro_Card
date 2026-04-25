from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from bot_app.config import Settings
from bot_app.db.models import OrderStatus
from bot_app.db.session import session_scope
from bot_app.repo import get_order_by_id, mark_order_paid_pending
from bot_app.services.fulfillment import route_after_paid
from bot_app.services.stars_payment import parse_stars_order_payload
from bot_app.keyboards import kb_start


def setup(settings: Settings) -> Router:
    router = Router(name="stars")

    @router.pre_checkout_query()
    async def pre_checkout(q: PreCheckoutQuery) -> None:
        if not settings.stars_payments:
            await q.answer(ok=False, error_message="Оплата Stars отключена владельцем бота.")
            return
        if (q.currency or "") != "XTR":
            await q.answer(ok=False, error_message="Нужен платёж в Stars (XTR).")
            return
        p = parse_stars_order_payload(q.invoice_payload)
        if not p:
            await q.answer(ok=False, error_message="Счёт устарел. /start")
            return
        oid, uid = p
        if not q.from_user or q.from_user.id != uid:
            await q.answer(ok=False, error_message="Счёт привязан к другому пользователю.")
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, oid)
        if not o or o.user_id != uid or o.status != OrderStatus.awaiting_payment.value:
            await q.answer(
                ok=False, error_message="Заказ не найден или уже оплачен. /start"
            )
            return
        exp = settings.stars_tier5 if o.tier_usd <= 5 else settings.stars_tier10
        if int(q.total_amount) != int(exp):
            await q.answer(
                ok=False, error_message="Сумма отличается. Переоформите заказ: /start"
            )
            return
        await q.answer(ok=True)

    @router.message(F.successful_payment)
    async def successful_payment(message: Message) -> None:
        if not message.successful_payment or not message.from_user:
            return
        pay = message.successful_payment
        if pay.currency != "XTR":
            return
        p = parse_stars_order_payload(pay.invoice_payload)
        if not p:
            return
        oid, uid = p
        if message.from_user.id != uid:
            return
        note = f"stars:{pay.telegram_payment_charge_id or 'xtr'}"
        async with session_scope(settings.database_url) as session:
            o = await mark_order_paid_pending(session, oid, note)
            if not o:
                await message.answer(
                    "Не удалось привязать оплату к заказу. Напишите админу с номером заказа.",
                    reply_markup=kb_start(),
                )
                return
            order = o
        await message.answer(
            f"Оплата Stars по заказу <b>#{oid}</b> получена, готовим расклад…",
            parse_mode="HTML",
        )
        await route_after_paid(
            settings,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            order=order,
        )

    return router
