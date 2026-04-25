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
    return b.as_markup()


def kb_tiers() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="5 USD — 3 карты", callback_data="tier:5"),
        InlineKeyboardButton(text="10 USD — расширенный", callback_data="tier:10"),
    )
    b.row(InlineKeyboardButton(text="❌ Отменить", callback_data="menu:cancel_flow"))
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
