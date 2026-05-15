"""Агрегация статистики и HTML-текст отчёта для канала."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot_app.db.session import session_scope
from bot_app.db.signal_models import (
    ParsedSignal,
    ParsedSignalStatus,
    SignalPost,
    SignalSource,
)


@dataclass
class ChannelAgg:
    source_id: int
    display_name: str
    platform: str
    wins: int
    losses: int
    expired: int
    open_cnt: int
    failed: int
    resolved_24h_wins: int
    resolved_24h_losses: int

    @property
    def resolved(self) -> int:
        return self.wins + self.losses

    @property
    def wr(self) -> float | None:
        if self.wins + self.losses == 0:
            return None
        return 100.0 * self.wins / (self.wins + self.losses)

    @property
    def wr24(self) -> float | None:
        if self.resolved_24h_wins + self.resolved_24h_losses == 0:
            return None
        return (
            100.0
            * self.resolved_24h_wins
            / (self.resolved_24h_wins + self.resolved_24h_losses)
        )


async def _load_signals(database_url: str) -> list[ParsedSignal]:
    async with session_scope(database_url) as session:
        q = await session.execute(
            select(ParsedSignal).options(
                selectinload(ParsedSignal.post).selectinload(SignalPost.source)
            )
        )
        return list(q.scalars().all())


def _aggregate(rows: list[ParsedSignal], cutoff_24h: datetime) -> dict[int, ChannelAgg]:
    buckets: dict[int, ChannelAgg] = {}

    def ensure(src: SignalSource) -> ChannelAgg:
        if src.id not in buckets:
            buckets[src.id] = ChannelAgg(
                source_id=src.id,
                display_name=src.display_name,
                platform=src.platform,
                wins=0,
                losses=0,
                expired=0,
                open_cnt=0,
                failed=0,
                resolved_24h_wins=0,
                resolved_24h_losses=0,
            )
        return buckets[src.id]

    for ps in rows:
        src = ps.post.source
        agg = ensure(src)
        st = ps.status
        ra = ps.resolved_at
        if ra and ra.tzinfo is None:
            ra = ra.replace(tzinfo=timezone.utc)

        if st == ParsedSignalStatus.tp.value:
            agg.wins += 1
            if ra and ra >= cutoff_24h:
                agg.resolved_24h_wins += 1
        elif st == ParsedSignalStatus.sl.value:
            agg.losses += 1
            if ra and ra >= cutoff_24h:
                agg.resolved_24h_losses += 1
        elif st == ParsedSignalStatus.expired.value:
            agg.expired += 1
        elif st == ParsedSignalStatus.open.value:
            agg.open_cnt += 1
        elif st == ParsedSignalStatus.parsing_failed.value:
            agg.failed += 1

    return buckets


async def build_daily_report_html(
    database_url: str,
    *,
    min_signals: int,
    report_generated_at: datetime | None = None,
) -> str:
    """
    Полный текст поста (HTML). Таблицы моноширинные через &lt;pre&gt;.
    """
    now = report_generated_at or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    rows = await _load_signals(database_url)
    total_posts = len({ps.post_id for ps in rows})
    buckets = _aggregate(rows, cutoff)

    eligible = [
        b
        for b in buckets.values()
        if (b.wins + b.losses) >= min_signals
    ]
    best_all = sorted(
        eligible,
        key=lambda a: (a.wr or 0, a.wins - a.losses, a.resolved),
        reverse=True,
    )[:10]
    worst_all = sorted(
        eligible,
        key=lambda a: (a.wr or 100, a.wins - a.losses, a.resolved),
    )[:10]

    eligible24 = [
        b
        for b in buckets.values()
        if (b.resolved_24h_wins + b.resolved_24h_losses) >= min_signals
    ]
    best24 = sorted(
        eligible24,
        key=lambda a: (a.wr24 or 0, a.resolved_24h_wins - a.resolved_24h_losses),
        reverse=True,
    )[:10]
    worst24 = sorted(
        eligible24,
        key=lambda a: (a.wr24 or 100, a.resolved_24h_wins - a.resolved_24h_losses),
    )[:10]

    champ = None
    if eligible:
        champ = sorted(
            eligible,
            key=lambda a: (a.wr or 0, a.wins - a.losses, a.resolved),
            reverse=True,
        )[0]

    lines: list[str] = []
    lines.append("<b>📊 Отчёт по торговым сигналам</b>")
    lines.append(f"<i>Сгенерировано (UTC): {now.strftime('%Y-%m-%d %H:%M')}</i>")
    lines.append("")
    lines.append("<b>Как считается</b>")
    lines.append(
        "• Источники: посты из подключённых <b>Telegram-каналов</b> (бот — администратор), "
        "плюс ручной ввод админом; TikTok — только через заготовку импорта (API TikTok здесь не используется)."
    )
    lines.append(
        "• Из текста извлекаются пара USDT, LONG/SHORT, Entry, первый TP и SL (эвристики, без ИИ)."
    )
    lines.append(
        "• Исполнение: после времени поста берутся свечи <b>Bybit</b> (публичный API), интервал 5m. "
        "Если в одной свече затронуты и TP, и SL — считаем, что сработал <b>SL первым</b> (консервативно)."
    )
    lines.append(
        "• Если за период <code>SIGNAL_MAX_HOLD_HOURS</code> ни TP, ни SL не достигнуты — статус «истёк» "
        "(не входит в винрейт)."
    )
    lines.append(
        f"• В рейтинг попадают каналы с ≥<code>{min_signals}</code> завершёнными сделками "
        "(TP или SL)."
    )
    lines.append("")
    if champ:
        lines.append(
            f"🏆 <b>Лучший источник за всё время (по данным БД):</b> "
            f"{_esc(champ.display_name)} — WR {champ.wr:.1f}% при W/L {champ.wins}/{champ.losses}"
        )
    else:
        lines.append(
            "🏆 Лучший источник: пока недостаточно данных "
            f"(нужно ≥{min_signals} завершённых TP/SL по каналу)."
        )
    lines.append("")
    lines.append(f"<i>В базе: {len(buckets)} источников, {total_posts} постов с попыткой разбора.</i>")
    lines.append("")

    def table_block(title: str, lst: list[ChannelAgg], worst: bool = False) -> None:
        lines.append(f"<b>{title}</b>")
        if not lst:
            lines.append("<pre>нет данных</pre>")
            lines.append("")
            return
        show = lst[:10]
        col = "Худшие" if worst else "Лучшие"
        lines.append(
            f"<pre>{col:8} | Канал              | WR%   | W | L | Истёк | Откр. | WR 24ч\n"
            f"{'-' * 72}</pre>"
        )
        for i, b in enumerate(show, 1):
            wr = f"{b.wr:.1f}" if b.wr is not None else " — "
            wr24 = f"{b.wr24:.1f}" if b.wr24 is not None else " — "
            name = _esc(b.display_name)[:18]
            lines.append(
                f"<pre>{i:2} | {name:18} | {wr:5} | {b.wins:2} | {b.losses:2} | "
                f"{b.expired:5} | {b.open_cnt:5} | {wr24:6}</pre>"
            )
        lines.append("")

    table_block("Топ-10 каналов (всё время)", best_all, worst=False)
    table_block("10 наихудших каналов (всё время)", worst_all, worst=True)
    table_block("Топ-10 за последние сутки (по закрытым TP/SL)", best24, worst=False)
    table_block("10 наихудших за последние сутки", worst24, worst=True)

    lines.append(
        "<i>Прошлые дни не пересчитываются — накопление идёт в SQLite; "
        "суточные колонки — только сигналы, у которых дата закрытия попала в последние 24 ч UTC.</i>"
    )
    return "\n".join(lines)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
