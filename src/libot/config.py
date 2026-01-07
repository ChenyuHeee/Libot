from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibotConfig:
    base_url: str = "https://booking.lib.zju.edu.cn"
    # 原样保存浏览器里的 Cookie 请求头内容（例如："a=b; c=d"）
    cookie: str | None = None


def default_config_dir() -> Path:
    # macOS: ~/Library/Application Support/libot
    home = Path.home()
    return home / "Library" / "Application Support" / "libot"


def default_config_path() -> Path:
    return default_config_dir() / "config.json"


def load_config(path: Path | None = None) -> LibotConfig:
    path = path or default_config_path()
    if not path.exists():
        return LibotConfig()

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    base_url = str(data.get("base_url") or LibotConfig.base_url)
    cookie = data.get("cookie")
    if cookie is not None:
        cookie = str(cookie)
    return LibotConfig(base_url=base_url, cookie=cookie)


def save_config(config: LibotConfig, path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"base_url": config.base_url, "cookie": config.cookie}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)
    return path
