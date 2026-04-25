"""Выдача расклада после оплаты, история, картинки, апселл."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import FSInputFile, InputMediaPhoto

from bot_app.config import Settings
from bot_app.db.models import Order
from bot_app.db.session import session_scope
from bot_app.keyboards import kb_upsell_after_reading
from bot_app.repo import mark_order_completed
from bot_app.repo.readings import (
    KIND_ORDER_AI,
    add_reading_entry,
)
from bot_app.services.card_images import SpreadKind, ensure_placeholder_card_pack, resolve_card_image_paths
from bot_app.services.reading_ai import generate_tarot_reading
from bot_app.utils.notify import esc, notify_admins

if TYPE_CHECKING:
    pass

log = logging.getLogger("bot_app.fulfillment")


async def _send_spread_photos(
    bot: Bot, chat_id: int, kind: SpreadKind, settings: Settings
) -> None:
    custom = settings.cards_images_dir
    paths = resolve_card_image_paths(kind, custom_dir=custom)
    if not paths and not custom:
        ensure_placeholder_card_pack()
        paths = resolve_card_image_paths(kind, custom_dir=None)
    if not paths:
        return
    if len(paths) == 1:
        await bot.send_photo(chat_id, FSInputFile(paths[0]))
        return
    media = [InputMediaPhoto(media=FSInputFile(p)) for p in paths[:10]]
    if media:
        await bot.send_media_group(chat_id, media=media)


async def deliver_paid_order_ai(
    settings: Settings,
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    order: Order,
) -> None:
    """AI-расклад после подтверждённой оплаты; заказ закрывается при успехе."""
    if not settings.openai_api_key:
        await notify_admins(
            bot,
            settings,
            f"⚠️ Заказ <b>#{order.id}</b> оплачен, но нет OPENAI_API_KEY. /deliver {order.id}",
        )
        return
    reading, err = await generate_tarot_reading(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        question=order.question,
        tier_usd=order.tier_usd,
    )
    if not reading:
        await notify_admins(
            bot,
            settings,
            f"⚠️ Заказ <b>#{order.id}</b> оплачен, AI не смог: {esc(err)}. /deliver {order.id}",
        )
        return
    sk = SpreadKind.tier5 if order.tier_usd <= 5 else SpreadKind.tier10
    try:
        await _send_spread_photos(bot, user_id, sk, settings)
    except Exception as e:
        log.warning("Фото карт не отправлены: %s", e)
    try:
        me = await bot.get_me()
        bname = (settings.bot_username or (me.username or "")).lstrip("@")
        body = f"🔮 Ваш расклад (заказ #{order.id}):\n\n{reading}\n\n💡 {settings.upsell_note}"
        await bot.send_message(
            user_id,
            body,
            reply_markup=kb_upsell_after_reading(
                order_id=order.id,
                bot_username=bname,
            ),
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
        await add_reading_entry(
            session,
            user_id=user_id,
            question=order.question,
            answer=reading,
            kind=KIND_ORDER_AI,
            order_id=order.id,
        )
    await notify_admins(
        bot,
        settings,
        f"⚡ Заказ <b>#{order.id}</b> закрыт автоматически (AI). Клиент: "
        f"<code>{user_id}</code> @{esc(username or '—')}",
    )


async def deliver_paid_order_manual_queue(
    settings: Settings,
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    order: Order,
) -> None:
    """Оплата отмечена, AI выключен — в очередь админам."""
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


async def route_after_paid(
    settings: Settings,
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    order: Order,
) -> None:
    if settings.auto_reading_ai and settings.openai_api_key:
        await deliver_paid_order_ai(settings, bot, user_id=user_id, username=username, order=order)
        return
    await deliver_paid_order_manual_queue(
        settings, bot, user_id=user_id, username=username, order=order
    )


