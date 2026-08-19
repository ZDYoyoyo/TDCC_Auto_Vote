"""時間與路徑工具。

⚠️ 時區鐵律：本專案所有時間**一律 Asia/Taipei**。
容器／伺服器預設是 UTC，`datetime.now()` 不帶時區在台灣晚上 8 點之後跑，
日期會少一天 → 會誤判股東會投票截止日。所以只在這一層取時間，其他地方一律
呼叫這裡的函式，不要自己 `datetime.now()`。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def now() -> datetime:
    """台北時間的現在。"""
    return datetime.now(TAIPEI)


def stamp() -> str:
    """檔名用時間戳，例：20260819_154210"""
    return now().strftime("%Y%m%d_%H%M%S")


def today() -> str:
    """台北日期，例：2026-08-19"""
    return now().strftime("%Y-%m-%d")


# Windows 檔名禁用字元 + 命令列會出事的字元（&, %, !, ^）
_UNSAFE = re.compile(r'[\\/:*?"<>|&%!^\s]+')


def safe_name(text: str, max_len: int = 40) -> str:
    """把任意文字變成能當檔名的字串。"""
    cleaned = _UNSAFE.sub("_", (text or "").strip())
    cleaned = cleaned.strip("_")
    return (cleaned[:max_len] or "untitled")
