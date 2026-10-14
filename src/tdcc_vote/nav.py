"""導頁工具。

⚠️ 為什麼需要這一層：集保的頁面會**自己再重導一次**。
實測（使用者 2026-10-14 回報）：
  goto https://.../000/tc_estock_welshas.html
  → Page.goto: Navigation to "...tc_estock_welshas.html" is interrupted by
    another navigation to "...tc_estock_welshas.html?top=1"

那個 ?top=1 應該是頁面自己的「跳脫框架」腳本加的。Playwright 的 goto 只要
發現自己發起的導航被另一個導航打斷就丟例外，**即使最後其實到了正確的頁面**。
所以不能直接用 page.goto，要容忍這種自我重導、再用「最後落在哪裡」來判斷成敗。
"""

from __future__ import annotations

from playwright.sync_api import Page

_INTERRUPTED = "interrupted by another navigation"
DEFAULT_TIMEOUT = 60_000
SETTLE_TIMEOUT = 20_000


def goto(
    page: Page,
    url: str,
    expect_contains: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    """導到 url，容忍頁面自我重導。

    expect_contains：導完之後網址必須含這段，否則視為失敗（丟 RuntimeError）。
    用「最後落在哪裡」判斷，比相信 goto 有沒有丟例外可靠。
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as exc:
        if _INTERRUPTED not in str(exc):
            raise
        # 被頁面自己的重導打斷，不是真的失敗。等它安定下來。
        try:
            page.wait_for_load_state("domcontentloaded", timeout=SETTLE_TIMEOUT)
        except Exception:
            pass

    if not expect_contains:
        return

    if expect_contains in page.url:
        return
    # 重導可能還在飛，再等一下網址變成預期的樣子
    try:
        page.wait_for_url(lambda u: expect_contains in u, timeout=SETTLE_TIMEOUT)
    except Exception:
        raise RuntimeError(
            f"導頁後不在預期的頁面：預期網址含「{expect_contains}」，實際是 {page.url}"
        ) from None
