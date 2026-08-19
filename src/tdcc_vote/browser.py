"""瀏覽器啟動。

刻意採「有頭 + 持久化 profile」：
- 有頭：登入這一關由使用者本人在畫面上完成（集保登入頁是隱形 reCAPTCHA，
  沒有東西可以讓程式代填，也不該去繞）。
- 持久化 profile：cookie 留著，下次有機會不用重新登入。

⚠️ 這裡不做任何指紋偽裝（不改 User-Agent、不裝 stealth 外掛）。
locale/timezone 設成 zh-TW / Asia/Taipei 是為了讓網頁的日期顯示正確，
那本來就是使用者的真實環境。
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

from .paths import PROJECT_ROOT

DEFAULT_PROFILE = PROJECT_ROOT / "profile"


def launch(
    pw: Playwright,
    profile_dir: Path | None = None,
    channel: str | None = None,
    headless: bool = False,
) -> BrowserContext:
    """開一個持久化的瀏覽器 context。

    channel: 傳 "chrome" 可改用系統已安裝的 Google Chrome；
             預設用 Playwright 自帶的 Chromium。
    headless: 僅供自動化測試用。正常使用一定要有頭，你才看得到、才能登入。
    """
    profile_dir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE
    profile_dir.mkdir(parents=True, exist_ok=True)

    # 少數環境（自訂安裝路徑、CI）Playwright 找不到自帶的 Chromium，
    # 可用環境變數指定執行檔。一般 Windows 使用者不需要設。
    executable_path = os.environ.get("TDCC_CHROMIUM_PATH") or None

    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        channel=channel,
        executable_path=executable_path,
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        no_viewport=not headless,
        args=["--window-size=1440,960"] if not headless else [],
    )
