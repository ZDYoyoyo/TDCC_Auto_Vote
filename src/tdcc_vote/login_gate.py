"""登入狀態判定與開啟登入頁。

為什麼不自動填帳密：集保登入頁掛的是 reCAPTCHA Enterprise v3（隱形、分數制），
自動化瀏覽器分數低、可能被擋；要「穩定通過」只能偽裝指紋或接代解服務，
那是破解平台的反機器人管制，本專案不做。詳見 docs/PLAN.md。

⚠️ 這裡刻意**不做「等待登入完成」的阻塞輪詢**。
先前版本會輪詢最多 10 分鐘，那段時間程式沒在讀鍵盤，使用者按 Enter／q 完全
沒反應，看起來像當掉——實際踩過。現在改成：開好登入頁就把控制權交回使用者，
登入狀態只在每次操作前顯示，不當關卡。
"""

from __future__ import annotations

from playwright.sync_api import Page


def is_logged_in(page: Page, selectors: dict) -> bool:
    """用網址是否進入 /evote/shareholder/ 判斷。

    注意：不能拿「頁面有沒有登出按鈕」當標記——登出表單在未登入的首頁也存在。
    """
    try:
        return selectors["login"]["logged_in_url_contains"] in page.url
    except Exception:
        # 瀏覽器被關掉時 page.url 會丟例外
        return False


def open_login_page(page: Page, selectors: dict) -> None:
    """導到登入頁。不等待、不阻塞。"""
    url = selectors["login"]["url"]
    if is_logged_in(page, selectors):
        print(f"✅ 目前看起來已經是登入狀態：{page.url}")
        return
    print(f"→ 開啟登入頁：{url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"⚠️ 開啟登入頁失敗（你可以自己在瀏覽器輸入網址）：{exc}")
