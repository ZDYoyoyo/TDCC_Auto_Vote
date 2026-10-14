"""查詢截圖：全部投完之後，回清單逐檔點「查詢」，把已投票結果頁拍下來。

為什麼另外一個階段（使用者 2026-10-14 實測後要求）：
  完成頁只寫「投票完成」，上面的按鈕會回首頁；要交給代領平台的是清單上點
  「查詢」之後的已投票結果頁（/002/01.html，列出議案與「贊成」）。
  使用者要的流程是：先把票全部投完，再回清單一檔一檔點查詢截圖。

⛔ 只點 qry。同一列還可能有 modify（改票）與 repael（撤銷），絕不可點。
   跟投票時一樣，用完整 onclick 字串精確比對，不會點錯列、也不會點錯動作。
"""

from __future__ import annotations

from playwright.sync_api import Page

from . import evidence
from .evidence import VoteRecord
from .meetings import ACTION_QUERY, Meeting
from .vote import NAV_TIMEOUT, _back_to_list


def capture_receipt(page: Page, selectors: dict, meeting: Meeting) -> VoteRecord:
    """點這一檔的「查詢」，拍下已投票結果頁存到「投票完成」資料夾，再回清單。"""
    code = meeting.stock_code
    rec = VoteRecord(
        stock_code=code,
        company=meeting.company,
        meeting_date=meeting.meeting_date,
        status="RECEIPT_FAILED",
    )
    rcfg = selectors["receipt"]

    onclick = meeting.actions.get(ACTION_QUERY)
    if not onclick:
        rec.detail = "這一檔沒有「查詢」連結"
        print(f"   ❌ {rec.detail}")
        return rec

    try:
        print("   → 點「查詢」")
        page.click(f'a[onclick="{onclick}"]', timeout=NAV_TIMEOUT)
        page.wait_for_url(lambda u: rcfg["url_contains"] in u, timeout=NAV_TIMEOUT)

        # 等結果表格真的有內容再拍，免得拍到還沒載完的空白頁
        page.wait_for_selector(rcfg["summary_table"], timeout=NAV_TIMEOUT)
        rows = evidence.read_table(page, rcfg["summary_table"])
        rec.proposals = [{"cells": " | ".join(r["cells"])} for r in rows]
        if not rows:
            path = evidence.shot(page, code, "x_查詢頁沒有內容")
            if path:
                rec.screenshots.append(path)
            rec.detail = "查詢頁的結果表格是空的，沒有存進「投票完成」"
            print(f"   ❌ {rec.detail}")
            return rec

        rec.receipt = evidence.receipt_shot(page, code, meeting.company)
        if rec.receipt:
            rec.screenshots.append(rec.receipt)
            rec.status = "RECEIPT"
            rec.detail = f"查詢頁截圖完成（結果表格 {len(rows)} 列）"
            print(f"   📸 {rec.receipt}")
        else:
            rec.detail = "查詢頁截圖失敗"
        return rec

    except Exception as exc:
        rec.detail = f"{type(exc).__name__}: {exc}".replace("\n", " ")[:300]
        print(f"   ❌ 查詢截圖失敗：{rec.detail}")
        path = evidence.shot(page, code, "x_查詢失敗")
        if path:
            rec.screenshots.append(path)
        return rec

    finally:
        _back_to_list(page, selectors)
