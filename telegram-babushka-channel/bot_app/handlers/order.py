from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError

from bot_app.config import Settings
from bot_app.db.models import Order
from bot_app.db.session import session_scope
from bot_app.keyboards import kb_after_tier, kb_skip_proof, kb_start, kb_tiers
from bot_app.repo import (
    cancel_all_active_orders_for_user,
    create_order,
    ensure_user,
    get_active_order_for_user,
    get_order_by_id,
    mark_order_completed,
    mark_order_paid_pending,
    mark_order_paid_trc20,
    payment_tx_hash_exists,
    set_agreed_terms,
)
from bot_app.services.reading_ai import generate_tarot_reading
from bot_app.services.tron_usdt import normalize_tx_hash, verify_usdt_trc20_incoming
from bot_app.states import OrderFlow
from bot_app.texts import DISCLAIMER, RULES_AND_PRICES
from bot_app.utils.notify import esc, notify_admins


async def _after_marked_paid(
    settings: Settings,
    bot,
    *,
    user_id: int,
    username: str | None,
    order: Order,
) -> None:
    """После подтверждения оплаты: AI-расклад или уведомление админам для ручной выдачи."""
    if settings.auto_reading_ai and settings.openai_api_key:
        reading, err = await generate_tarot_reading(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            question=order.question,
            tier_usd=order.tier_usd,
        )
        if reading:
            try:
                await bot.send_message(
                    user_id,
                    f"🔮 Ваш расклад (заказ #{order.id}):\n\n{reading}",
                )
            except TelegramForbiddenError:
                await notify_admins(
                    bot,
                    settings,
                    f"⚠️ Заказ <b>#{order.id}</b>: клиент <code>{user_id}</code> заблокировал бота — "
                    "не удалось отправить AI-расклад. /deliver вручную.",
                )
                return
            async with session_scope(settings.database_url) as session:
                await mark_order_completed(session, order.id, ai_reading_sent=True)
            uname = username or "—"
            await notify_admins(
                bot,
                settings,
                f"⚡ Заказ <b>#{order.id}</b> закрыт автоматически (AI). Клиент: "
                f"<code>{user_id}</code> @{esc(uname)}",
            )
            return
        await notify_admins(
            bot,
            settings,
            f"⚠️ Заказ <b>#{order.id}</b> оплачен, AI не смог: {esc(err)}. "
            f"/deliver {order.id}",
        )
        return

    uname = username or "—"
    admin_txt = (
        f"🆕 Оплата отмечена. Заказ <b>#{order.id}</b>\n"
        f"Пользователь: <code>{user_id}</code> @{esc(uname)}\n"
        f"Сумма: {order.tier_usd} USD\n"
        f"Вопрос:\n{esc(order.question)}\n"
    )
    if order.payment_note:
        admin_txt += f"Комментарий / Tx:\n{esc(order.payment_note)}\n"
    admin_txt += f"\n/deliver {order.id} — затем пришлите расклад следующим сообщением"
    await notify_admins(bot, settings, admin_txt)


async def _finalize_payment_callback(
    settings: Settings,
    callback: CallbackQuery,
    state: FSMContext,
    note: str | None,
) -> None:
    if not callback.from_user or not callback.message:
        return
    data = await state.get_data()
    oid = data.get("order_id")
    if not oid:
        await callback.answer()
        return
    async with session_scope(settings.database_url) as session:
        o = await mark_order_paid_pending(session, int(oid), note)
        if not o:
            await callback.answer("Ошибка заказа.", show_alert=True)
            return
        order = o
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"Спасибо! Заказ <b>#{oid}</b> принят в работу.\n\nВаш вопрос:\n{esc(order.question)}",
        parse_mode="HTML",
        reply_markup=kb_start(),
    )
    await _after_marked_paid(
        settings,
        callback.bot,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        order=order,
    )


async def _finalize_payment_message(
    settings: Settings,
    message: Message,
    state: FSMContext,
    note: str | None,
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    oid = data.get("order_id")
    if not oid:
        await state.clear()
        return
    async with session_scope(settings.database_url) as session:
        o = await mark_order_paid_pending(session, int(oid), note)
        if not o:
            await message.answer("Заказ не найден.")
            await state.clear()
            return
        order = o
    await state.clear()
    await message.answer(
        f"Спасибо! Заказ #{oid} принят в работу.",
        reply_markup=kb_start(),
    )
    await _after_marked_paid(
        settings,
        message.bot,
        user_id=message.from_user.id,
        username=message.from_user.username,
        order=order,
    )


def setup(settings: Settings) -> Router:
    router = Router(name="order")

    @router.callback_query(F.data == "menu:agree")
    async def cb_agree(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        async with session_scope(settings.database_url) as session:
            await set_agreed_terms(session, callback.from_user.id)
        await callback.answer()
        await callback.message.answer(
            "Спасибо. Условия приняты. Можете нажать «Заказать расклад».",
            reply_markup=kb_start(),
        )

    @router.callback_query(F.data == "menu:rules")
    async def cb_rules(callback: CallbackQuery) -> None:
        await callback.answer()
        await callback.message.answer(
            DISCLAIMER + "\n\n" + RULES_AND_PRICES, reply_markup=kb_start()
        )

    @router.callback_query(F.data == "menu:order")
    async def cb_order_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            return
        async with session_scope(settings.database_url) as session:
            u = await ensure_user(session, callback.from_user.id)
            if not u.agreed_terms_at:
                await callback.answer("Сначала нажмите «Согласен (18+)».", show_alert=True)
                return
            active = await get_active_order_for_user(session, callback.from_user.id)
            if active:
                await callback.answer(
                    "У вас уже есть активный заказ в базе. Нажмите /cancel — отменит его и "
                    "можно заказать снова. Если оплатили, но расклада нет — напишите админу.",
                    show_alert=True,
                )
                return
        await state.set_state(OrderFlow.entering_question)
        await state.update_data(username=callback.from_user.username)
        await callback.answer()
        await callback.message.answer(
            "Опишите одним сообщением тему и **один** основной вопрос для расклада.\n"
            "По возможности не спрашивайте о третьих лицах без их согласия.",
            parse_mode="Markdown",
        )

    @router.message(OrderFlow.entering_question, F.text)
    async def got_question(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if len(text) < 5:
            await message.answer("Слишком коротко. Раскройте вопрос чуть подробнее.")
            return
        if len(text) > 3500:
            await message.answer("Слишком длинно. Сократите до одного сообщения.")
            return
        await state.update_data(question=text)
        await message.answer("Выберите формат:", reply_markup=kb_tiers())

    @router.callback_query(StateFilter(OrderFlow.entering_question), F.data.startswith("tier:"))
    async def cb_tier(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.message:
            return
        raw = (callback.data or "").split(":", 1)[-1]
        try:
            tier = int(raw)
        except ValueError:
            await callback.answer()
            return
        if tier not in (5, 10):
            await callback.answer()
            return
        data = await state.get_data()
        q = data.get("question")
        if not q:
            await callback.answer("Сначала введите вопрос текстом.", show_alert=True)
            return
        async with session_scope(settings.database_url) as session:
            await ensure_user(session, callback.from_user.id)
            o = await create_order(
                session,
                user_id=callback.from_user.id,
                username=callback.from_user.username,
                question=q,
                tier_usd=tier,
            )
            oid = o.id
        await state.update_data(order_id=oid)
        await state.set_state(OrderFlow.awaiting_payment_confirm)
        pay = settings.payment_details.strip()
        await callback.answer()
        extra = ""
        if settings.auto_usdt_verify_trc20:
            extra = (
                "\n\nПосле оплаты нажмите «Я оплатил(а)» и пришлите <b>TxID</b> транзакции USDT TRC20 "
                "(64 hex-символа)."
            )
        else:
            extra = (
                "\n\nПосле оплаты нажмите «Я оплатил(а)» и при желании пришлите комментарий "
                "(хеш, скрин)."
            )
        await callback.message.answer(
            f"Заказ <b>#{oid}</b> создан: <b>{tier} USD</b>.\n\n"
            f"💳 Реквизиты оплаты:\n<pre>{esc(pay)}</pre>"
            f"{extra}",
            parse_mode="HTML",
            reply_markup=kb_after_tier(),
        )

    @router.callback_query(StateFilter(OrderFlow.awaiting_payment_confirm), F.data == "pay:done")
    async def cb_paid(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        oid = data.get("order_id")
        if not oid:
            await callback.answer("Заказ не найден. Начните с /start.", show_alert=True)
            return
        if settings.auto_usdt_verify_trc20:
            await state.set_state(OrderFlow.waiting_tron_tx_hash)
            await callback.answer()
            await callback.message.answer(
                "Отправьте **TxID** перевода USDT (TRC20) на наш кошелёк из реквизитов — "
                "ровно **64 hex-символа** (скопируйте из кошелька или TronScan).",
                parse_mode="Markdown",
            )
            return
        await state.set_state(OrderFlow.waiting_payment_proof)
        await callback.answer()
        await callback.message.answer(
            "Пришлите текстом комментарий к оплате или фото чека. "
            "Или нажмите «Пропустить комментарий».",
            reply_markup=kb_skip_proof(),
        )

    @router.message(OrderFlow.waiting_tron_tx_hash, F.text)
    async def got_tron_tx(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        data = await state.get_data()
        oid = data.get("order_id")
        if not oid:
            await state.clear()
            return
        tx = normalize_tx_hash(message.text or "")
        if not tx:
            await message.answer(
                "Нужен корректный TxID: 64 символа 0–9 и a–f (без 0x). "
                "Скопируйте из TronScan или кошелька."
            )
            return
        recv = settings.tron_usdt_receiver
        if not recv:
            await message.answer("Ошибка конфигурации кошелька. Обратитесь к администратору.")
            return
        async with session_scope(settings.database_url) as session:
            ord_row = await get_order_by_id(session, int(oid))
            if not ord_row or ord_row.user_id != message.from_user.id:
                await message.answer("Заказ не найден.")
                await state.clear()
                return
            tier = ord_row.tier_usd

        ok, err = await verify_usdt_trc20_incoming(
            tx_hash=tx,
            receiver_base58=recv,
            min_usdt=float(tier),
            trongrid_api_key=settings.trongrid_api_key,
        )
        if not ok:
            await message.answer(f"Не удалось подтвердить оплату: {err}")
            return

        try:
            async with session_scope(settings.database_url) as session:
                if await payment_tx_hash_exists(session, tx):
                    await message.answer("Этот TxID уже использован в другом заказе.")
                    return
                o = await mark_order_paid_trc20(session, int(oid), tx, f"trc20:{tx}")
                if not o:
                    await message.answer("Заказ не найден.")
                    await state.clear()
                    return
                order = o
        except IntegrityError:
            await message.answer("Этот TxID уже зарегистрирован.")
            return

        await state.clear()
        await message.answer(
            f"Оплата подтверждена по сети. Заказ <b>#{oid}</b>.\n\nВаш вопрос:\n{esc(order.question)}",
            parse_mode="HTML",
            reply_markup=kb_start(),
        )
        await _after_marked_paid(
            settings,
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            order=order,
        )

    @router.callback_query(StateFilter(OrderFlow.waiting_payment_proof), F.data == "pay:skip_note")
    async def cb_skip_note(callback: CallbackQuery, state: FSMContext) -> None:
        await _finalize_payment_callback(settings, callback, state, None)

    @router.message(OrderFlow.waiting_payment_proof, F.text)
    async def proof_text(message: Message, state: FSMContext) -> None:
        note = (message.text or "").strip()[:2000]
        await _finalize_payment_message(settings, message, state, note)

    @router.message(OrderFlow.waiting_payment_proof, F.photo)
    async def proof_photo(message: Message, state: FSMContext) -> None:
        fid = message.photo[-1].file_id if message.photo else ""
        cap = (message.caption or "").strip()[:500]
        note = f"photo:{fid}" + (f" | {cap}" if cap else "")
        await _finalize_payment_message(settings, message, state, note)

    @router.callback_query(F.data == "menu:cancel_flow")
    async def cb_cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        n = 0
        if callback.from_user:
            async with session_scope(settings.database_url) as session:
                n = await cancel_all_active_orders_for_user(session, callback.from_user.id)
        await callback.answer("Отменено.")
        if callback.message:
            msg = (
                f"Оформление отменено (активных заказов снято: {n})."
                if n
                else "Оформление отменено."
            )
            await callback.message.answer(msg, reply_markup=kb_start())

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        if not message.from_user:
            return
        async with session_scope(settings.database_url) as session:
            n = await cancel_all_active_orders_for_user(session, message.from_user.id)
        if n:
            await message.answer(
                f"Отменено активных заказов в базе: {n}. Можно снова нажать «Заказать расклад».",
                reply_markup=kb_start(),
            )
        else:
            await message.answer(
                "Активных заказов не было (сессия сброшена). Нажмите «Заказать расклад», если нужно.",
                reply_markup=kb_start(),
            )

    return router
