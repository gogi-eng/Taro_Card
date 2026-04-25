"""Точка входа: `python -m bot_app` из корня проекта (предпочтительно)."""

from __future__ import annotations

import sys
from pathlib import Path

# Если запускают `python путь\bot_app\__main__.py`, пакет `bot_app` не в PYTHONPATH.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot_app.main import main

if __name__ == "__main__":
    main()
