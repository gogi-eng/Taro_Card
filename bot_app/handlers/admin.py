from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot_app.config import Settings
from bot_app.db.models import OrderStatus
from bot_app.db.session import session_scope
from bot_app.filters import IsAdmin
from bot_app.keyboards import kb_upsell_after_reading
from bot_app.repo import (
    cancel_order_by_user,
    get_order_by_id,
    list_pending_orders,
    mark_order_completed,
)
from bot_app.repo.readings import KIND_ORDER_MANUAL, add_reading_entry
from bot_app.states import AdminDelivery
from bot_app.utils.notify import esc, notify_admins


def setup(settings: Settings) -> Router:
    router = Router(name="admin")
    is_admin = IsAdmin(settings)

    @router.message(is_admin, Command("orders"))
    async def cmd_orders(message: Message) -> None:
        async with session_scope(settings.database_url) as session:
            rows = await list_pending_orders(session, limit=30)
        if not rows:
            await message.answer("Нет заказов в статусе «оплата отмечена — ждём расклад».")
            return
        chunks: list[str] = []
        for o in rows:
            q = o.question.replace("\n", " ")[:120]
            chunks.append(
                f"#{o.id} | {o.tier_usd} USD | uid={o.user_id} | {esc(q)}"
            )
        text = "Очередь:\n" + "\n".join(chunks)
        if len(text) > 3500:
            text = text[:3500] + "…"
        await message.answer(text, parse_mode="HTML")

    @router.message(is_admin, Command("order"))
    async def cmd_order(message: Message, command: CommandObject) -> None:
        args = (command.args or "").strip().split()
        if not args:
            await message.answer("Использование: /order &lt;номер&gt;", parse_mode="HTML")
            return
        try:
            oid = int(args[0])
        except ValueError:
            await message.answer("Номер заказа — целое число.")
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, oid)
        if not o:
            await message.answer(f"Заказ #{oid} не найден.")
            return
        note = esc(o.payment_note) if o.payment_note else "—"
        tx_line = esc(o.payment_tx_hash) if o.payment_tx_hash else "—"
        txt = (
            f"Заказ <b>#{o.id}</b>\n"
            f"Статус: <code>{esc(o.status)}</code>\n"
            f"Клиент: <code>{o.user_id}</code> @{esc(o.username or '—')}\n"
            f"Сумма: {o.tier_usd} USD\n"
            f"TxID (TRC20): <code>{tx_line}</code>\n"
            f"AI-расклад отправлен: {'да' if o.ai_reading_sent else 'нет'}\n"
            f"Вопрос:\n{esc(o.question)}\n"
            f"Комментарий к оплате:\n{note}\n"
            f"\n/deliver {o.id} — следующим сообщением отправить расклад\n"
            f"/cancel_order {o.id} — отменить заказ"
        )
        await message.answer(txt, parse_mode="HTML")

    @router.message(is_admin, Command("deliver"))
    async def cmd_deliver(message: Message, command: CommandObject, state: FSMContext) -> None:
        args = (command.args or "").strip().split()
        if not args:
            await message.answer("Использование: /deliver &lt;номер_заказа&gt;", parse_mode="HTML")
            return
        try:
            oid = int(args[0])
        except ValueError:
            await message.answer("Номер заказа — целое число.")
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, oid)
        if not o:
            await message.answer(f"Заказ #{oid} не найден.")
            return
        if o.status != OrderStatus.paid_pending_reading.value:
            await message.answer(
                f"Заказ #{oid} не в очереди на расклад (статус: {o.status})."
            )
            return
        await state.set_state(AdminDelivery.waiting_reading)
        await state.update_data(deliver_order_id=oid)
        await message.answer(
            f"Заказ <b>#{oid}</b>. Сама команда расклад не отправляет — "
            f"<b>следующим сообщением</b> пришлите текст или медиа (фото, документ, голос): "
            f"бот перешлёт его клиенту как есть.\n"
            f"В группах с темами — ответьте в <b>этой же теме</b>, где видно это сообщение.\n"
            f"/cancel_delivery — выйти без отправки.",
            parse_mode="HTML",
        )

    @router.message(is_admin, Command("cancel_delivery"), StateFilter(AdminDelivery.waiting_reading))
    async def cmd_cancel_delivery(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Режим отправки расклада отменён.")

    @router.message(is_admin, StateFilter(AdminDelivery.waiting_reading))
    async def admin_sends_reading(message: Message, state: FSMContext) -> None:
        if message.text and message.text.startswith("/"):
            await message.answer(
                "Сейчас ожидается расклад <b>одним сообщением</b> (не команда). "
                "Чтобы выйти из режима: /cancel_delivery",
                parse_mode="HTML",
            )
            return
        data = await state.get_data()
        oid = data.get("deliver_order_id")
        if not oid:
            await state.clear()
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, int(oid))
        if not o:
            await state.clear()
            await message.answer("Заказ не найден.")
            return
        uid = o.user_id
        try:
            await message.copy_to(uid)
        except TelegramForbiddenError:
            await message.answer(
                f"Не удалось отправить: пользователь <code>{uid}</code> заблокировал бота.",
                parse_mode="HTML",
            )
            await notify_admins(
                message.bot,
                settings,
                f"⚠️ Не доставлен расклад по заказу #{oid}: пользователь {uid} заблокировал бота.",
            )
            await state.clear()
            return
        if message.text:
            answer_txt = (message.text or "")[:10000]
        elif message.caption:
            answer_txt = (message.caption or "")[:10000]
        else:
            answer_txt = "Расклад отправлен (см. выше: медиа или вложение)."
        async with session_scope(settings.database_url) as session:
            await add_reading_entry(
                session,
                user_id=uid,
                question=o.question,
                answer=answer_txt,
                kind=KIND_ORDER_MANUAL,
                order_id=int(oid),
            )
            await mark_order_completed(session, int(oid), ai_reading_sent=False)
        me = await message.bot.get_me()
        bname = (settings.bot_username or (me.username or "")).lstrip("@")
        try:
            await message.bot.send_message(
                uid,
                f"💡 {settings.upsell_note}",
                reply_markup=kb_upsell_after_reading(
                    order_id=int(oid),
                    bot_username=bname,
                ),
            )
        except TelegramForbiddenError:
            pass
        await state.clear()
        await message.answer(f"Готово. Расклад по заказу #{oid} отправлен клиенту.")

    @router.message(is_admin, Command("cancel_order"))
    async def cmd_cancel_order_admin(message: Message, command: CommandObject) -> None:
        args = (command.args or "").strip().split()
        if not args:
            await message.answer("Использование: /cancel_order &lt;номер&gt;", parse_mode="HTML")
            return
        try:
            oid = int(args[0])
        except ValueError:
            await message.answer("Номер заказа — целое число.")
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, oid)
            if not o:
                await message.answer(f"Заказ #{oid} не найден.")
                return
            uid = o.user_id
            ok = await cancel_order_by_user(session, oid, uid)
        if not ok:
            await message.answer("Нельзя отменить (уже завершён или отменён).")
            return
        await message.answer(f"Заказ #{oid} отменён. Сообщите клиенту при необходимости.")
        try:
            await message.bot.send_message(
                uid,
                f"Ваш заказ #{oid} отменён администратором. Если это ошибка — напишите в поддержку.",
            )
        except TelegramForbiddenError:
            pass

    return router
