from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError

from bot_app.config import Settings
from bot_app.db.session import session_scope
from bot_app.keyboards import (
    kb_after_tier,
    kb_choose_payment,
    kb_skip_proof,
    kb_start,
    kb_tiers,
)
from bot_app.repo import (
    cancel_all_active_orders_for_user,
    create_order,
    ensure_user,
    get_active_order_for_user,
    get_order_by_id,
    mark_order_paid_pending,
    mark_order_paid_trc20,
    payment_tx_hash_exists,
    set_agreed_terms,
)
from bot_app.services.fulfillment import route_after_paid
from bot_app.services.stars_payment import send_stars_invoice
from bot_app.services.tron_usdt import normalize_tx_hash, verify_usdt_trc20_incoming
from bot_app.states import OrderFlow
from bot_app.texts import DISCLAIMER, RULES_AND_PRICES
from bot_app.utils.callbacks import ack_callback
from bot_app.utils.notify import esc, notify_admins


async def _finalize_payment_callback(
    settings: Settings,
    callback: CallbackQuery,
    state: FSMContext,
    note: str | None,
) -> None:
    if not callback.from_user or not callback.message:
        return
    await ack_callback(callback)
    data = await state.get_data()
    oid = data.get("order_id")
    if not oid:
        return
    async with session_scope(settings.database_url) as session:
        o = await mark_order_paid_pending(session, int(oid), note)
        if not o:
            await callback.message.answer("Ошибка заказа. Начните с /start.")
            return
        order = o
    await state.clear()
    await callback.message.answer(
        f"Спасибо! Заказ <b>#{oid}</b> принят в работу.\n\nВаш вопрос:\n{esc(order.question)}",
        parse_mode="HTML",
        reply_markup=kb_start(),
    )
    await route_after_paid(
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
    await route_after_paid(
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
        await ack_callback(callback)
        if not callback.from_user or not callback.message:
            return
        async with session_scope(settings.database_url) as session:
            await set_agreed_terms(session, callback.from_user.id)
        await callback.message.answer(
            "Спасибо. Условия приняты. Можете нажать «Заказать расклад».",
            reply_markup=kb_start(),
        )

    @router.callback_query(F.data == "menu:rules")
    async def cb_rules(callback: CallbackQuery) -> None:
        await ack_callback(callback)
        if not callback.message:
            return
        await callback.message.answer(
            DISCLAIMER + "\n\n" + RULES_AND_PRICES, reply_markup=kb_start()
        )

    @router.callback_query(F.data == "menu:order")
    async def cb_order_start(callback: CallbackQuery, state: FSMContext) -> None:
        await ack_callback(callback)
        if not callback.from_user or not callback.message:
            return
        async with session_scope(settings.database_url) as session:
            u = await ensure_user(session, callback.from_user.id)
            if not u.agreed_terms_at:
                await callback.message.answer(
                    "Сначала нажмите кнопку «Согласен (18+)».",
                    reply_markup=kb_start(),
                )
                return
            active = await get_active_order_for_user(session, callback.from_user.id)
            if active:
                await callback.message.answer(
                    "У вас уже есть <b>активный</b> заказ в базе. Отправьте /cancel — отменит его, "
                    "и можно снова заказать. Если вы уже оплатили, а расклада нет — напишите администратору.",
                    parse_mode="HTML",
                    reply_markup=kb_start(),
                )
                return
        # сброс сценария «бесплатная карта» и прочих данных FSM
        await state.clear()
        await state.set_state(OrderFlow.entering_question)
        await state.update_data(username=callback.from_user.username)
        await callback.message.answer(
            "Опишите одним сообщением тему и <b>один</b> основной вопрос для расклада.\n"
            "По возможности не спрашивайте о третьих лицах без их согласия.",
            parse_mode="HTML",
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
        await ack_callback(callback)
        if not callback.from_user or not callback.message:
            return
        raw = (callback.data or "").split(":", 1)[-1]
        try:
            tier = int(raw)
        except ValueError:
            return
        if tier not in (5, 10):
            return
        data = await state.get_data()
        q = data.get("question")
        if not q:
            await callback.message.answer(
                "Сначала введите вопрос <b>одним текстовым сообщением</b>.",
                parse_mode="HTML",
            )
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
        if settings.stars_payments:
            await state.set_state(OrderFlow.choosing_payment)
            await callback.message.answer(
                f"Заказ <b>#{oid}</b> создан: <b>{tier} USD</b>.\n\n"
                "Выберите способ оплаты (Stars удобнее, если USDT путает).",
                parse_mode="HTML",
                reply_markup=kb_choose_payment(has_stars=True),
            )
            return
        await state.set_state(OrderFlow.awaiting_payment_confirm)
        pay = settings.payment_details.strip()
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

    @router.callback_query(StateFilter(OrderFlow.choosing_payment), F.data == "pay:meth:usdt")
    async def cb_pay_usdt(callback: CallbackQuery, state: FSMContext) -> None:
        await ack_callback(callback)
        if not callback.from_user or not callback.message:
            return
        data = await state.get_data()
        oid = data.get("order_id")
        if not oid:
            await callback.message.answer("Сессия устарела. Отправьте /start.", reply_markup=kb_start())
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, int(oid))
        if not o or o.user_id != callback.from_user.id:
            await callback.message.answer("Заказ не найден. /start", reply_markup=kb_start())
            return
        await state.set_state(OrderFlow.awaiting_payment_confirm)
        pay = settings.payment_details.strip()
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
            f"Заказ <b>#{oid}</b> — {o.tier_usd} USD.\n\n"
            f"💳 Реквизиты:\n<pre>{esc(pay)}</pre>" + extra,
            parse_mode="HTML",
            reply_markup=kb_after_tier(),
        )

    @router.callback_query(StateFilter(OrderFlow.choosing_payment), F.data == "pay:meth:stars")
    async def cb_pay_stars(callback: CallbackQuery, state: FSMContext) -> None:
        await ack_callback(callback)
        if not settings.stars_payments or not callback.from_user or not callback.message:
            await callback.message.answer("Stars не включены в настройке бота.", reply_markup=kb_start())
            return
        data = await state.get_data()
        oid = data.get("order_id")
        if not oid:
            await callback.message.answer("Сессия устарела. Отправьте /start.", reply_markup=kb_start())
            return
        async with session_scope(settings.database_url) as session:
            o = await get_order_by_id(session, int(oid))
        if not o or o.user_id != callback.from_user.id:
            await callback.message.answer("Заказ не найден. /start", reply_markup=kb_start())
            return
        await send_stars_invoice(
            callback.message,
            order=o,
            user_telegram_id=callback.from_user.id,
            settings=settings,
        )
        await state.clear()
        await callback.message.answer("Откройте счёт выше и оплатите в Stars ⭐", reply_markup=kb_start())

    @router.callback_query(StateFilter(OrderFlow.awaiting_payment_confirm), F.data == "pay:done")
    async def cb_paid(callback: CallbackQuery, state: FSMContext) -> None:
        await ack_callback(callback)
        if not callback.message:
            return
        data = await state.get_data()
        oid = data.get("order_id")
        if not oid:
            await callback.message.answer("Заказ не найден. Начните с /start.", reply_markup=kb_start())
            return
        if settings.auto_usdt_verify_trc20:
            await state.set_state(OrderFlow.waiting_tron_tx_hash)
            await callback.message.answer(
                "Отправьте <b>TxID</b> перевода USDT (TRC20) на наш кошелёк из реквизитов — "
                "ровно <b>64</b> hex-символа (скопируйте из кошелька или TronScan).",
                parse_mode="HTML",
            )
            return
        await state.set_state(OrderFlow.waiting_payment_proof)
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
        await route_after_paid(
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
        await ack_callback(callback, text="Отменено.")
        await state.clear()
        n = 0
        if callback.from_user:
            async with session_scope(settings.database_url) as session:
                n = await cancel_all_active_orders_for_user(session, callback.from_user.id)
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
