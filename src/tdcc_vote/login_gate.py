"""登入關卡：程式停在這裡，等使用者本人登入完成。

為什麼不自動填帳密：集保登入頁掛的是 reCAPTCHA Enterprise v3（隱形、分數制），
自動化瀏覽器分數低、可能被擋；要「穩定通過」只能偽裝指紋或接代解服務，
那是破解平台的反機器人管制，本專案不做。詳見 docs/PLAN.md。
"""

from __future__ import annotations

import time

from playwright.sync_api import Page


def is_logged_in(page: Page, selectors: dict) -> bool:
    marker = selectors["login"]["logged_in_url_contains"]
    return marker in page.url


def wait_for_login(
    page: Page,
    selectors: dict,
    timeout_sec: int = 600,
    poll_sec: float = 2.0,
) -> bool:
    """導到登入頁並等待人工登入。回傳是否偵測到已登入。"""
    login_cfg = selectors["login"]

    if is_logged_in(page, selectors):
        print("✅ 偵測到已經是登入狀態（profile 裡的 session 還有效）")
        return True

    print(f"→ 開啟登入頁：{login_cfg['url']}")
    page.goto(login_cfg["url"], wait_until="domcontentloaded")

    print()
    print("=" * 60)
    print("  請在剛跳出來的瀏覽器視窗裡，自己完成登入")
    print("  （輸入身分證字號、密碼，或用憑證登入）")
    print(f"  程式會等你最多 {timeout_sec // 60} 分鐘，登入好就會自動接手")
    print("=" * 60)
    print()

    deadline = time.time() + timeout_sec
    last_note = 0.0
    while time.time() < deadline:
        if is_logged_in(page, selectors):
            print(f"✅ 偵測到登入成功：{page.url}")
            return True
        remain = deadline - time.time()
        if time.time() - last_note >= 30:
            print(f"   ...等待登入中（剩 {int(remain)} 秒）")
            last_note = time.time()
        time.sleep(poll_sec)

    print("⚠️ 等待逾時，沒有偵測到登入成功。")
    return False
