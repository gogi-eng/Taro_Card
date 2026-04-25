from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def kb_start() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Согласен (18+)", callback_data="menu:agree"),
        InlineKeyboardButton(text="📌 Правила и цены", callback_data="menu:rules"),
    )
    b.row(InlineKeyboardButton(text="🃏 Заказать расклад", callback_data="menu:order"))
    b.row(
        InlineKeyboardButton(text="🆓 Бесплатно: 1 карта", callback_data="menu:free"),
        InlineKeyboardButton(text="📜 Мои 3", callback_data="menu:history"),
    )
    return b.as_markup()


def kb_tiers() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="5 USD — 3 карты", callback_data="tier:5"),
        InlineKeyboardButton(text="10 USD — расширенный", callback_data="tier:10"),
    )
    b.row(InlineKeyboardButton(text="❌ Отменить", callback_data="menu:cancel_flow"))
    return b.as_markup()


def kb_choose_payment(*, has_stars: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💵 USDT / реквизиты", callback_data="pay:meth:usdt"))
    if has_stars:
        b.row(InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data="pay:meth:stars"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel_flow"))
    return b.as_markup()


def kb_after_tier() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💳 Я оплатил(а)", callback_data="pay:done"))
    b.row(InlineKeyboardButton(text="❌ Отменить заказ", callback_data="menu:cancel_flow"))
    return b.as_markup()


def kb_skip_proof() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Пропустить комментарий", callback_data="pay:skip_note"))
    return b.as_markup()


def kb_upsell_after_reading(*, order_id: int, bot_username: str) -> InlineKeyboardMarkup:
    u = (bot_username or "").strip().lstrip("@")
    b = InlineKeyboardBuilder()
    if u:
        b.row(
            InlineKeyboardButton(
                text="💬 Уточнить / второй расклад (скидка в описании ⬇)",
                url=f"https://t.me/{u}?start=clarify{order_id}",
            )
        )
        b.row(
            InlineKeyboardButton(
                text="🃏 Новый платный расклад",
                url=f"https://t.me/{u}?start=order",
            )
        )
    b.row(InlineKeyboardButton(text="🔮 В меню", callback_data="menu:back_start"))
    return b.as_markup()


def kb_back_only() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔮 В меню", callback_data="menu:back_start"))
    return b.as_markup()
