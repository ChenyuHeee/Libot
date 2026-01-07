from __future__ import annotations

import json
import sys
from pathlib import Path


def _pyinstaller_meipass() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    try:
        return Path(str(meipass))
    except Exception:
        return None


def load_bundled_defaults() -> dict:
    """Load defaults embedded into a PyInstaller bundle.

    For development (non-bundled), returns empty dict.
    """

    root = _pyinstaller_meipass()
    if root is None:
        return {}

    path = root / "libot_bundled.json"
    if not path.exists():
        path = root / "libot_bundled.example.json"
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_bundled_dingtalk_webhook() -> str:
    data = load_bundled_defaults()
    v = data.get("dingtalk_webhook") if isinstance(data, dict) else None
    return str(v).strip() if v else ""
