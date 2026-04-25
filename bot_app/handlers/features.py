from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, Message

from bot_app.config import Settings
from bot_app.db.session import session_scope
from bot_app.keyboards import kb_back_only, kb_start
from bot_app.repo.readings import (
    KIND_FREE,
    add_reading_entry,
    can_use_free_today_utc,
    count_free_today_utc,
    list_last_readings_for_user,
)
from bot_app.repo.users import ensure_user
from bot_app.services.card_images import (
    SpreadKind,
    ensure_placeholder_card_pack,
    render_free_card_image_bytes,
    resolve_card_image_paths,
)
from bot_app.services.reading_ai import esc_html, generate_free_one_card_reading
from bot_app.states import FreeOneCard
from bot_app.texts import WELCOME
from bot_app.utils.notify import esc

log = logging.getLogger("bot_app.features")

_KIND_RU = {
    "free_1card": "Бесплатно (1 карта)",
    "order_ai": "Платно (авто-расклад)",
    "order_manual": "Платно (вручную)",
}


def setup(settings: Settings) -> Router:
    router = Router(name="features")

    @router.callback_query(F.data == "menu:back_start")
    async def cb_back(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await callback.message.answer(WELCOME, reply_markup=kb_start())

    @router.callback_query(F.data == "menu:free")
    async def cb_free(callback: CallbackQuery, state: FSMContext) -> None:
        if not settings.enable_free_one_card:
            await callback.answer("Сейчас отключено владельцем бота.", show_alert=True)
            return
        if not callback.from_user:
            return
        async with session_scope(settings.database_url) as session:
            u = await ensure_user(session, callback.from_user.id)
            if not u.agreed_terms_at:
                await callback.answer("Сначала нажмите «Согласен (18+)».", show_alert=True)
                return
            if not await can_use_free_today_utc(
                session, callback.from_user.id, per_day=settings.free_cards_per_day
            ):
                n = await count_free_today_utc(session, callback.from_user.id)
                await callback.answer(
                    f"Лимит на сегодня: {n}/{settings.free_cards_per_day}. "
                    "Попробуйте завтра или оформите платный расклад.",
                    show_alert=True,
                )
                return
        await state.set_state(FreeOneCard.enter_question)
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "🆓 **Бесплатно: одна карта** (коротко). Напишите **один** вопрос одним сообщением (до 500 знаков).",
                parse_mode="Markdown",
                reply_markup=kb_back_only(),
            )

    @router.message(StateFilter(FreeOneCard.enter_question), F.text)
    async def free_got_text(message: Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        text = (message.text or "").strip()
        if len(text) < 3:
            await message.answer("Напишите вопрос чуть подробнее, одной фразой.")
            return
        if len(text) > 500:
            await message.answer("Слишком длинно. Сократите для бесплатного шага.")
            return
        async with session_scope(settings.database_url) as session:
            if not await can_use_free_today_utc(
                session, message.from_user.id, per_day=settings.free_cards_per_day
            ):
                await message.answer(
                    "Похоже, лимит на сегодня уже исчерпан. /start", reply_markup=kb_start()
                )
                await state.clear()
                return
        # Ключ нейросети для бесплатки: берём из .env, даже если AUTO_READING_AI=false
        okey = settings.openai_api_key
        reading, gen_err, card_title = await generate_free_one_card_reading(
            api_key=okey,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            question=text,
        )
        if gen_err and not reading:
            await message.answer(
                f"Сбой: {gen_err} Попробуйте позже. /start", reply_markup=kb_start()
            )
            await state.clear()
            return
        if gen_err and reading:
            log.warning("Бесплатный расклад: %s (показан запасной текст)", gen_err)
        if not reading:
            await message.answer("Не вышло сгенерировать. /start", reply_markup=kb_start())
            await state.clear()
            return
        sent_photo = False
        png = render_free_card_image_bytes(
            (card_title or "Карта дня").strip() or "Карта дня"
        )
        if png:
            try:
                await message.answer_photo(
                    BufferedInputFile(png, filename="karta.png"),
                )
                sent_photo = True
            except Exception as e:
                log.warning("Не удалось отправить сгенерированную карту: %s", e)
        if not sent_photo:
            custom = settings.cards_images_dir
            paths = resolve_card_image_paths(SpreadKind.free_one, custom_dir=custom)
            if not paths and not custom:
                ensure_placeholder_card_pack()
                paths = resolve_card_image_paths(SpreadKind.free_one, custom_dir=None)
            if paths:
                try:
                    await message.answer_photo(FSInputFile(paths[0]))
                except Exception:
                    pass
        plain_db = re.sub(r"<br\s*/?>", " ", reading, flags=re.I)
        plain_db = re.sub(r"<[^>]+>", " ", plain_db)
        plain_db = re.sub(r"\s+", " ", plain_db).strip()
        await message.answer(
            f"{reading}\n\n"
            f"—\n{esc_html(settings.upsell_note)}\n\n"
            f"Полный расклад: кнопка «🃏 Заказать расклад» в /start",
            parse_mode="HTML",
            reply_markup=kb_start(),
        )
        async with session_scope(settings.database_url) as session:
            await add_reading_entry(
                session,
                user_id=message.from_user.id,
                question=text,
                answer=plain_db[:12000],
                kind=KIND_FREE,
            )
        await state.clear()

    @router.message(StateFilter(FreeOneCard.enter_question), ~F.text)
    async def free_not_text(_message: Message) -> None:
        await _message.answer("Нужен текст (одно сообщение с вопросом).")

    @router.callback_query(F.data == "menu:history")
    async def cb_history(callback: CallbackQuery) -> None:
        if not callback.from_user or not callback.message:
            return
        async with session_scope(settings.database_url) as session:
            rows = await list_last_readings_for_user(
                session, callback.from_user.id, limit=3
            )
        if not rows:
            await callback.answer("Пока нет записей в истории.", show_alert=True)
            return
        parts: list[str] = []
        for r in rows:
            kind_ru = _KIND_RU.get(r.kind, r.kind)
            q = esc((r.question or "")[:300])
            a_full = (r.answer or "")
            a = esc(a_full[:700])
            suffix = "…" if len(a_full) > 700 else ""
            parts.append(
                f"<b>{esc(kind_ru)}</b>\n"
                f"Вопрос: {q}\n"
                f"Ответ: {a}{suffix}"
            )
        body = "📜 Последние 3 (от нового к старому):\n\n" + "\n\n".join(parts)
        if len(body) > 4000:
            body = body[:4000] + "…"
        await callback.answer()
        await callback.message.answer(body, parse_mode="HTML", reply_markup=kb_start())

    return router
