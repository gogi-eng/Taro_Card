"""Build a looping GIF from the base Tarot illustration (candle flicker + subtle zoom)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    print("Install Pillow: pip install pillow", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "assets" / "grandmother-tarot-base.png"
    out = root / "assets" / "grandmother-tarot-animated.gif"
    if not src.is_file():
        print(f"Missing: {src}", file=sys.stderr)
        sys.exit(1)

    im = Image.open(src).convert("RGBA")
    w, h = im.size
    frames: list[Image.Image] = []
    durations: list[int] = []

    # 12 frames: smooth loop — warm pulse (candle) + very subtle zoom breathing
    n = 12
    for i in range(n):
        t = i / n
        # brightness wave ~ candle (0.94 .. 1.06)
        phase = math.sin(t * 2 * math.pi) * 0.06 + 1.0
        layer = ImageEnhance.Brightness(im).enhance(phase)
        layer = ImageEnhance.Color(layer).enhance(0.98 + 0.04 * math.sin(t * 2 * math.pi + 0.5))
        # subtle zoom: scale 1.0 .. 1.02
        scale = 1.0 + 0.02 * (0.5 - 0.5 * math.cos(t * 2 * math.pi))
        nw = int(w * scale)
        nh = int(h * scale)
        zoomed = layer.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - w) // 2
        top = (nh - h) // 2
        cropped = zoomed.crop((left, top, left + w, top + h))
        frames.append(cropped.convert("P", palette=Image.ADAPTIVE, colors=256))
        durations.append(90)  # ms per frame (~11 fps)

    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {out} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
