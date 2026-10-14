"""讀取「可投票股東會清單」。

清單頁：/evote/shareholder/000/tc_estock_welshas.html
表格 #stockInfo 欄位（實抓確認）：
  0 證券代號公司簡稱 / 1 會議日期投票起迄日 / 2 投票狀況 / 3 作業項目 / 4 eGift資格

作業項目那一欄是連結，參數全在 onclick：
  getOverlapMeeting('<證券代號>','<動作>','<會議日期YYYYMMDD>')
  vote=投票 qry=查詢 modify=修改 repael=撤銷（平台自己拼錯，照抄）

⚠️ 鐵律：證券代號一律當**字串**處理。00878 用 int 會變成 878。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from playwright.sync_api import Page

ACTION_VOTE = "vote"


@dataclass
class Meeting:
    stock_code: str                      # 字串，保留前導零
    company: str
    meeting_date: str                    # 平台原文（民國年），不自行換算
    vote_period: str
    status: str                          # 未投票 / 已投票 / 已截止投票
    actions: dict[str, str] = field(default_factory=dict)  # 動作 -> onclick 原文
    raw_cells: list[str] = field(default_factory=list)

    @property
    def can_vote(self) -> bool:
        return ACTION_VOTE in self.actions

    def __str__(self) -> str:
        return f"{self.stock_code} {self.company}｜會議 {self.meeting_date}｜{self.status}"


def _js_rows(page: Page, table_sel: str, link_sel: str) -> list[dict]:
    return page.evaluate(
        """([tableSel, linkSel]) => {
            const t = document.querySelector(tableSel);
            if (!t) return [];
            const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
            return [...t.rows].map(r => ({
                cells: [...r.cells].map(c => clean(c.innerText)),
                links: [...r.querySelectorAll(linkSel)].map(a => ({
                    text: clean(a.innerText),
                    onclick: a.getAttribute('onclick') || '',
                })),
            }));
        }""",
        [table_sel, link_sel],
    )


def list_page_info(page: Page, selectors: dict) -> dict:
    """清單頁的現況，用於診斷「為什麼讀到 0 筆」。"""
    cfg = selectors["meetings"]
    try:
        return page.evaluate(
            """([tableSel, infoSel]) => {
                const t = document.querySelector(tableSel);
                const i = document.querySelector(infoSel);
                return {
                    table_found: !!t,
                    row_count: t ? t.rows.length : 0,
                    page_info: i ? (i.innerText || '').replace(/\\s+/g, ' ').trim() : '',
                };
            }""",
            [cfg["table"], cfg.get("page_info", "#tbDisplayTag")],
        ) | {"url": page.url}
    except Exception as exc:
        return {"table_found": False, "row_count": 0, "page_info": "",
                "url": page.url, "error": str(exc)}


def declared_total(info: dict) -> int | None:
    """從「共計N筆」取出平台自己宣稱的筆數；讀不到回 None。"""
    m = re.search(r"共計\s*(\d+)\s*筆", info.get("page_info", ""))
    return int(m.group(1)) if m else None


def wait_for_rows(page: Page, selectors: dict) -> bool:
    """等表格出現資料列（表頭之外至少一列）。回傳是否等到。

    ⚠️ 為什麼要等：表格資料是頁面載入**之後**才用 JS 填進去的。
    2026-10-14 實跑在頁面骨架一出來就讀，只讀到表頭 → 回報「0 筆」，
    使用者明明有可投票項目。explore 抓得到，是因為人按 Enter 時早就載完了。
    """
    cfg = selectors["meetings"]
    try:
        page.wait_for_function(
            "sel => { const t = document.querySelector(sel); return !!t && t.rows.length > 1; }",
            arg=cfg["table"],
            timeout=int(cfg.get("table_wait_ms", 20000)),
        )
        return True
    except Exception:
        return False


def read_meetings(page: Page, selectors: dict) -> list[Meeting]:
    """讀清單頁的表格。第 0 列是表頭，跳過。

    會先等表格真的有資料（見 wait_for_rows）。呼叫端不必、也不該自己先讀。
    """
    cfg = selectors["meetings"]
    wait_for_rows(page, selectors)
    pattern = re.compile(cfg["action_onclick_re"])
    rows = _js_rows(page, cfg["table"], cfg["action_link"])

    meetings: list[Meeting] = []
    for row in rows[1:]:
        cells = row["cells"]
        if len(cells) < 3:
            continue

        actions: dict[str, str] = {}
        code_from_onclick = ""
        date_from_onclick = ""
        for link in row["links"]:
            m = pattern.search(link["onclick"])
            if not m:
                continue
            code_from_onclick, action, date_from_onclick = m.group(1), m.group(2), m.group(3)
            actions[action] = link["onclick"]

        # 第 0 欄是「代號 公司簡稱」黏在一起（例 "1101 台泥"）。
        # 代號優先取 onclick 裡的（那是平台自己給的權威值），公司名取欄位剩下的部分。
        first = cells[0].split()
        code = str(code_from_onclick or (first[0] if first else ""))
        company = " ".join(first[1:]) if len(first) > 1 else ""

        # 第 1 欄是「會議日期 投票起迄日」兩段
        date_parts = cells[1].split()
        meetings.append(
            Meeting(
                stock_code=code,
                company=company,
                meeting_date=date_parts[0] if date_parts else "",
                vote_period=" ".join(date_parts[1:]),
                status=cells[2] if len(cells) > 2 else "",
                actions=actions,
                raw_cells=cells,
            )
        )
    return meetings


def votable(meetings: list[Meeting]) -> list[Meeting]:
    """只留下真的還能投票的（作業項目有 vote 連結）。

    刻意用「有沒有 vote 連結」而不是「投票狀況欄是不是『未投票』」判斷：
    已截止的檔狀況欄也不是「已投票」，但平台不會給 vote 連結。
    以平台給不給連結為準，比自己解析中文字串可靠。
    """
    return [m for m in meetings if m.can_vote]
