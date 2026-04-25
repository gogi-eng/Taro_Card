"""Загрузка настроек из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import FrozenSet


def _parse_admin_ids(raw: str | None) -> FrozenSet[int]:
    if not raw:
        return frozenset()
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return frozenset(out)


def _bool_env(key: str, default: bool = False) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: FrozenSet[int]
    payment_details: str
    database_url: str
    use_webhook: bool
    webhook_url: str | None
    webhook_path: str
    webapp_host: str
    webapp_port: int
    log_level: str
    support_username: str | None
    # Авто-проверка USDT TRC20 по TxID (TronScan)
    auto_usdt_verify_trc20: bool
    tron_usdt_receiver: str | None
    trongrid_api_key: str | None
    # Авто-расклад через OpenAI
    auto_reading_ai: bool
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str | None

    @classmethod
    def from_env(cls) -> Settings:
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Задайте BOT_TOKEN в окружении")

        payment = os.environ.get("PAYMENT_DETAILS", "").strip()
        if not payment:
            payment = (
                "USDT TRC20: укажите кошелёк в PAYMENT_DETAILS в .env на сервере."
            )

        db = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db").strip()

        wh = _bool_env("USE_WEBHOOK", False)
        webhook_url = os.environ.get("WEBHOOK_URL", "").strip() or None
        if wh and not webhook_url:
            raise RuntimeError("При USE_WEBHOOK=true нужен WEBHOOK_URL (https://...)")

        auto_usdt = _bool_env("AUTO_USDT_VERIFY_TRC20", False)
        tron_recv = os.environ.get("TRON_USDT_RECEIVER", "").strip() or None
        auto_ai = _bool_env("AUTO_READING_AI", False)
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        openai_base = os.environ.get("OPENAI_BASE_URL", "").strip() or None

        if auto_usdt and not tron_recv:
            raise RuntimeError(
                "При AUTO_USDT_VERIFY_TRC20=true задайте в .env TRON_USDT_RECEIVER= "
                "(TRC20-адрес T..., тот же, что в реквизитах). "
                "Или отключите: AUTO_USDT_VERIFY_TRC20=false"
            )
        if auto_ai and not openai_key:
            raise RuntimeError("При AUTO_READING_AI=true задайте OPENAI_API_KEY.")

        return cls(
            bot_token=token,
            admin_ids=_parse_admin_ids(os.environ.get("ADMIN_IDS")),
            payment_details=payment,
            database_url=db,
            use_webhook=wh,
            webhook_url=webhook_url,
            webhook_path=os.environ.get("WEBHOOK_PATH", "/webhook").strip() or "/webhook",
            webapp_host=os.environ.get("WEBAPP_HOST", "0.0.0.0").strip(),
            webapp_port=int(os.environ.get("WEBAPP_PORT", "8080")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            support_username=os.environ.get("SUPPORT_USERNAME", "").strip() or None,
            auto_usdt_verify_trc20=auto_usdt,
            tron_usdt_receiver=tron_recv,
            trongrid_api_key=os.environ.get("TRONGRID_API_KEY", "").strip() or None,
            auto_reading_ai=auto_ai,
            openai_api_key=openai_key,
            openai_model=openai_model,
            openai_base_url=openai_base,
        )


def require_admins(settings: Settings) -> None:
    if not settings.admin_ids:
        raise RuntimeError("Задайте хотя бы один ADMIN_IDS (Telegram user id админа)")
