"""Пути к PNG карт/раскладов (опционально). При отсутствии файлов визуал пропускается."""

from __future__ import annotations

import logging
import os
import re
import textwrap
from enum import Enum
from io import BytesIO
from pathlib import Path

log = logging.getLogger("bot_app.cards")


class SpreadKind(str, Enum):
    free_one = "free_one"
    tier5 = "tier5"
    tier10 = "tier10"


def _default_pack_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "cards"


def _find_ttf() -> str | None:
    win = os.environ.get("WINDIR", r"C:\Windows")
    for p in [
        os.path.join(win, "Fonts", "segoeui.ttf"),
        os.path.join(win, "Fonts", "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        if p and os.path.isfile(p):
            return p
    return None


def render_free_card_image_bytes(
    title: str,
    *,
    subtitle: str = "Старшая аркана",
    line2: str = "бесплатный мини-расклад",
) -> bytes | None:
    """
    Картинка с крупной подписью — чтобы «карта» визуально читалась, а не пустой прямоугольник.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    t = re.sub(r"\s+", " ", (title or "").strip()) or "Карта"
    w, h = 520, 780
    im = Image.new("RGB", (w, h), (42, 24, 52))
    d = ImageDraw.Draw(im)
    d.rectangle((18, 18, w - 18, h - 18), outline=(220, 195, 150), width=4)
    font_path = _find_ttf()
    if font_path:
        try:
            f_big = ImageFont.truetype(font_path, 40)
            f_sm = ImageFont.truetype(font_path, 25)
        except OSError:
            f_big = f_sm = ImageFont.load_default()
    else:
        f_big = f_sm = ImageFont.load_default()
    # короткие строки — кириллица, ~10–12 символов в строке
    lines = textwrap.wrap(t, width=12) or [t]
    y = 110
    for part in lines[:4]:
        d.text(
            (w // 2, y),
            part,
            fill=(255, 245, 220),
            font=f_big,
            anchor="mm",
        )
        y += 50
    d.text(
        (w // 2, h // 2 + 30), subtitle, fill=(210, 200, 180), font=f_sm, anchor="mm"
    )
    d.text(
        (w // 2, h // 2 + 80), line2, fill=(180, 170, 160), font=f_sm, anchor="mm"
    )
    d.text(
        (w // 2, h - 90),
        "символ для размышления",
        fill=(150, 140, 130),
        font=f_sm,
        anchor="mm",
    )
    buf = BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def resolve_card_image_paths(
    kind: SpreadKind, *, custom_dir: str | None
) -> list[Path]:
    """
    Возвращает существующие PNG для отправки. Имена по умолчанию:
    free.png | three1.png, three2.png, three3.png | extended.png
    """
    base = Path(custom_dir).expanduser() if custom_dir else _default_pack_dir()
    if not base.is_dir():
        return []
    if kind == SpreadKind.free_one:
        names = ("free.png",)
    elif kind == SpreadKind.tier5:
        names = ("three1.png", "three2.png", "three3.png")
    else:
        names = ("extended.png", "extended2.png")
    out: list[Path] = []
    for n in names:
        p = base / n
        if p.is_file():
            out.append(p)
    return out


def ensure_placeholder_card_pack(target: Path | None = None) -> bool:
    """
    Создаёт простые цветные PNG (Pillow), если каталога нет. Возвращает True при успехе.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.info("Pillow не установлен — картинки карт пропущены. pip install pillow")
        return False
    base = target or _default_pack_dir()
    base.mkdir(parents=True, exist_ok=True)
    palette = {
        "free.png": (80, 40, 90),
        "three1.png": (50, 70, 90),
        "three2.png": (90, 60, 50),
        "three3.png": (40, 80, 60),
        "extended.png": (70, 50, 80),
        "extended2.png": (60, 60, 50),
    }
    for name, rgb in palette.items():
        p = base / name
        if p.exists():
            continue
        im = Image.new("RGB", (400, 600), rgb)
        d = ImageDraw.Draw(im)
        d.rectangle((20, 20, 380, 580), outline=(220, 200, 180), width=3)
        d.text((50, 280), "TAROT", fill=(220, 210, 200))
        im.save(p, format="PNG")
    return True
