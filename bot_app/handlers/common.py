from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot_app.config import Settings
from bot_app.keyboards import kb_start
from bot_app.texts import RULES_AND_PRICES, WELCOME
from bot_app.utils.notify import esc


def setup(settings: Settings) -> Router:
    router = Router(name="common")

    @router.message(CommandStart())
    async def cmd_start(message: Message, command: CommandObject) -> None:
        arg = (command.args or "").strip()
        if arg.startswith("clarify"):
            await message.answer(
                "Продолжение или уточнение — оформите <b>новый</b> расклад (тот же чат).\n\n"
                f"{esc(settings.upsell_note)}",
                parse_mode="HTML",
                reply_markup=kb_start(),
            )
            return
        if arg == "order":
            await message.answer(
                "Нажмите «🃏 Заказать расклад» ниже — и оформите вопрос.",
                reply_markup=kb_start(),
            )
            return
        await message.answer(WELCOME, reply_markup=kb_start())

    @router.message(Command("help"))
    @router.message(F.text.casefold() == "помощь")
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "Команды:\n"
            "/start — главное меню\n"
            "/help — эта справка\n"
            "/cancel — отменить активный заказ в базе (если «активный заказ», но вы не оформляли — сначала /cancel)\n\n"
            + RULES_AND_PRICES,
            reply_markup=kb_start(),
        )

    return router
