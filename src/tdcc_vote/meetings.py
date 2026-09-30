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


def read_meetings(page: Page, selectors: dict) -> list[Meeting]:
    """讀清單頁的表格。第 0 列是表頭，跳過。"""
    cfg = selectors["meetings"]
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
