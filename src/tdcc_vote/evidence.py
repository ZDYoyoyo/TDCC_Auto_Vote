"""截圖存證與結果紀錄。

⚠️ point-in-time 原則：投票當下就把「當時看到的議案與我方選擇」寫進紀錄，
不要事後回平台重查再組。事後重查不會報錯，只會靜默給你一份「看起來對」的歷史。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from .paths import PROJECT_ROOT, now, safe_name, stamp, today

EVIDENCE_DIR = PROJECT_ROOT / "evidence"
RESULTS_DIR = PROJECT_ROOT / "logs" / "results"


@dataclass
class VoteRecord:
    """一檔的投票結果。寫入時間點＝投票當下。"""

    stock_code: str          # 一律字串（00878 不可變成 878）
    company: str
    meeting_date: str        # 平台顯示的原文，不自行換算民國／西元
    status: str              # OK / DRY_RUN / FAILED / SKIPPED
    detail: str = ""
    proposals: list[dict[str, str]] = field(default_factory=list)  # 當下看到的議案與選擇
    screenshots: list[str] = field(default_factory=list)
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if not self.recorded_at:
            self.recorded_at = now().isoformat()


def shot(page: Page, stock_code: str, kind: str) -> str:
    """截圖。檔名：<代號>_<日期>_<時間>_<階段>.png，按日期分資料夾。"""
    folder = EVIDENCE_DIR / today()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_name(stock_code)}_{stamp()}_{safe_name(kind)}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:
        print(f"   ⚠️ 截圖失敗（{kind}）：{exc}")
        return ""
    return str(path)


def record(rec: VoteRecord) -> Path:
    """把一筆結果 append 到當天的 jsonl。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{today()}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    return path


def read_table(page: Page, selector: str) -> list[dict[str, Any]]:
    """把一個表格讀成 [{'cells': [...]}, ...]，用於存下當下的議案內容。"""
    try:
        return page.evaluate(
            """(sel) => {
                const t = document.querySelector(sel);
                if (!t) return [];
                return [...t.rows].map(r => ({
                    cells: [...r.cells].map(c => (c.innerText || '').replace(/\\s+/g, ' ').trim())
                }));
            }""",
            selector,
        )
    except Exception:
        return []
