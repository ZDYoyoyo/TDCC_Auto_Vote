"""對 fixture 頁面跑完整投票流程。

⚠️ 這只驗證「解析與定位邏輯」，**不代表在真實集保網站上可行**。
   fixture 是照實抓的 DOM 重建的（含兩個撞名陷阱），
   用途是：容器連不上集保網站，這是唯一能回歸測試選擇器邏輯的方法。

跑法：PYTHONPATH=src python tests/test_flow_fixture.py
"""

from __future__ import annotations

import pathlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import tempfile  # noqa: E402

import yaml  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from tdcc_vote import evidence  # noqa: E402
from tdcc_vote.meetings import read_meetings, votable  # noqa: E402
from tdcc_vote.vote import vote_one  # noqa: E402

# ⚠ 測試不可污染真實資料：截圖與紀錄導到暫存目錄，
#   不要寫進專案的 evidence/ 與 logs/（那是使用者真實的存證）。
_TMP = pathlib.Path(tempfile.mkdtemp(prefix='tdcc_fixture_'))
evidence.EVIDENCE_DIR = _TMP / 'evidence'
evidence.RESULTS_DIR = _TMP / 'logs'

FIXTURES = ROOT / "tests" / "fixtures"
LIST_URL = (FIXTURES / "evote/shareholder/000/tc_estock_welshas.html").as_uri()

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def main() -> int:
    sel = yaml.safe_load((ROOT / "config/selectors.yaml").read_text(encoding="utf-8"))
    sel["meetings"]["url"] = LIST_URL          # 指向 fixture
    sel["meetings"]["url_contains"] = "tc_estock_welshas"

    with sync_playwright() as pw:
        import os
        browser = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("TDCC_CHROMIUM_PATH") or None,
        )
        page = browser.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded")

        print("\n[1] 讀清單與解析")
        ms = read_meetings(page, sel)
        check("讀到 3 筆", len(ms) == 3, f"實際 {len(ms)}")
        by_code = {m.stock_code: m for m in ms}
        check("代號保留前導零（00878 沒變成 878）", "00878" in by_code, str(sorted(by_code)))
        check("代號是字串", all(isinstance(m.stock_code, str) for m in ms))
        check("公司名切出來", by_code.get("1101") and by_code["1101"].company == "台泥",
              by_code["1101"].company if "1101" in by_code else "-")
        check("會議日期只取第一段", by_code.get("1101") and by_code["1101"].meeting_date == "115/10/13",
              by_code["1101"].meeting_date if "1101" in by_code else "-")

        print("\n[2] 篩出可投票（以平台給不給 vote 連結為準）")
        v = votable(ms)
        check("只有 2 筆可投票", len(v) == 2, ", ".join(m.stock_code for m in v))
        check("已投票的 1909 被排除", all(m.stock_code != "1909" for m in v))
        check("1909 的 modify/repael 有被讀到但不會用",
              set(by_code["1909"].actions) == {"qry", "modify", "repael"},
              str(sorted(by_code["1909"].actions)))

        print("\n[3] 預跑（--dry-run 預設）：應停在確認頁、不送出")
        rec = vote_one(page, sel, by_code["1101"], confirm=False)
        check("狀態 DRY_RUN", rec.status == "DRY_RUN", rec.status + " / " + rec.detail)
        check("有抓到確認頁的議案內容（point-in-time）", len(rec.proposals) >= 2,
              f"{len(rec.proposals)} 列")
        check("截圖有產生", len(rec.screenshots) >= 3, f"{len(rec.screenshots)} 張")
        check("預跑後回到清單頁", "tc_estock_welshas" in page.url, page.url.rsplit("/", 1)[-1])

        print("\n[4] ⛔ 撞名陷阱：確認沒有按到「取消投票」或「修改」")
        # fixture 的災難路徑會改 document.title，這裡驗證它從沒被觸發
        check("全程沒觸發取消／修改", "災難" not in page.title() and "錯誤" not in page.title(),
              page.title())

        print("\n[5] 真投票路徑（confirm=True，fixture 自動代替使用者按確認）")
        page.goto(LIST_URL, wait_until="domcontentloaded")
        ms2 = read_meetings(page, sel)
        target = {m.stock_code: m for m in ms2}["00878"]
        # 用 monkeypatch 模擬使用者「按完確認、回來按 Enter」
        import tdcc_vote.vote as vote_mod
        calls = {"n": 0}

        def fake_ask() -> str:
            calls["n"] += 1
            # 模擬使用者真的在瀏覽器按了「確認投票結果」
            page.click(sel["confirm"]["submit_button"])
            page.wait_for_url(lambda u: "6_01" in u, timeout=10000)
            return ""

        vote_mod._ask_confirmed = fake_ask
        rec2 = vote_one(page, sel, target, confirm=True)
        check("狀態 OK", rec2.status == "OK", rec2.status + " / " + rec2.detail)
        check("完成頁驗到「投票已完成」", "投票已完成" in rec2.detail, rec2.detail[:60])
        check("有等使用者按確認（沒有程式自己按送出）", calls["n"] == 1, f"{calls['n']} 次")
        check("完成後回到清單頁", "tc_estock_welshas" in page.url, page.url.rsplit("/", 1)[-1])
        check("這一輪也沒觸發取消／修改", "災難" not in page.title(), page.title())

        browser.close()

    print("\n" + "=" * 56)
    if failures:
        print(f"  ❌ {len(failures)} 項失敗：" + "; ".join(failures))
        return 1
    print("  ✅ 全部通過（僅代表邏輯正確，不代表真實網站可行）")
    print(f"  （測試產出在 {_TMP}，未寫入專案的 evidence/ 與 logs/）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
