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

from tdcc_vote import evidence, nav  # noqa: E402
from tdcc_vote.login_gate import is_logged_in, pick_page  # noqa: E402
from tdcc_vote.meetings import (  # noqa: E402
    declared_total, list_page_info, read_meetings, votable, wait_for_rows)
from tdcc_vote.vote import vote_one  # noqa: E402

# ⚠ 測試不可污染真實資料：截圖與紀錄導到暫存目錄，
#   不要寫進專案的 evidence/ 與 logs/（那是使用者真實的存證）。
_TMP = pathlib.Path(tempfile.mkdtemp(prefix='tdcc_fixture_'))
evidence.EVIDENCE_DIR = _TMP / 'evidence'
evidence.RESULTS_DIR = _TMP / 'logs'

FIXTURES = ROOT / "tests" / "fixtures"
LIST_URL = (FIXTURES / "evote/shareholder/000/tc_estock_welshas.html").as_uri()
LOGIN_URL = (FIXTURES / "evote/login/shareholder.html").as_uri()
TMP_URL = (FIXTURES / "evote/shareholder/000/tc_estock_welshas_tmp.html").as_uri()

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def main() -> int:
    sel = yaml.safe_load((ROOT / "config/selectors.yaml").read_text(encoding="utf-8"))
    sel["meetings"]["url"] = TMP_URL           # 指向 fixture：走網站選單入口 _tmp
    sel["meetings"]["url_contains"] = "tc_estock_welshas"

    with sync_playwright() as pw:
        import os
        browser = pw.chromium.launch(
            headless=True,
            executable_path=os.environ.get("TDCC_CHROMIUM_PATH") or None,
        )
        page = browser.new_page()
        nav.goto(page, TMP_URL, expect_contains="tc_estock_welshas")

        print("\n[1] 讀清單與解析（經 _tmp 入口，表格資料延遲 1.5 秒才出現）")
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
        nav.goto(page, LIST_URL, expect_contains="tc_estock_welshas")
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
        check("紀錄標明是使用者手動送出", rec2.submitted_by == "manual", rec2.submitted_by)
        receipt = Path(rec2.receipt) if rec2.receipt else None
        check("完成截圖存在「投票完成」資料夾",
              bool(receipt) and receipt.exists() and receipt.parent == evidence.receipt_dir(),
              str(receipt.relative_to(_TMP)) if receipt else "沒有產生")
        check("完成截圖檔名含代號與公司名",
              bool(receipt) and receipt.name.startswith("00878_國泰永續高股息_"),
              receipt.name if receipt else "-")
        check("預跑的那一檔沒有完成截圖", rec.receipt == "", rec.receipt or "（無，正確）")
        others = [p.name for p in evidence.receipt_dir().glob("*.png")]
        check("「投票完成」資料夾只有真的投完的那一張", len(others) == 1, str(others))

        print("\n[6] 多分頁：登入後平台另開頁，不可寫死第一個分頁")
        # 重現實際 bug：pages[0] 停在登入頁，使用者其實在另一個分頁
        ctx2 = browser.new_context()
        tab_login = ctx2.new_page()
        tab_login.goto(LOGIN_URL, wait_until="domcontentloaded")
        tab_list = ctx2.new_page()
        nav.goto(tab_list, LIST_URL + "?top=1", expect_contains="tc_estock_welshas")

        check("第一個分頁確實是登入頁（未登入）", not is_logged_in(tab_login, sel),
              tab_login.url.rsplit("/", 1)[-1])
        picked = pick_page(ctx2, sel)
        check("pick_page 挑到已登入的那個分頁，不是 pages[0]",
              picked.url == tab_list.url, picked.url.rsplit("/", 1)[-1])
        check("挑到的分頁判定為已登入", is_logged_in(picked, sel))
        ctx2.close()

        print("\n[7] 真站會自我重導成 ?top=1：nav.goto 要撐住，但不能吞掉真錯誤")
        ctx3 = browser.new_context()
        t4 = ctx3.new_page()
        ok = True
        try:
            nav.goto(t4, LIST_URL, expect_contains="tc_estock_welshas")
        except Exception as exc:
            ok = False
            print(f"      nav.goto 失敗：{exc}")
        check("nav.goto 導到會自我重導的頁面仍成功", ok)
        check("最後落在 ?top=1 的頁面", "top=1" in t4.url, t4.url.rsplit("/", 1)[-1])
        check("到站後表格讀得到", len(read_meetings(t4, sel)) == 3)
        ctx3.close()

        # ⚠️ 誠實說明：fixture 的 location.replace 發生得太早，Playwright 會把它
        #    算進同一次導航，所以**沒有重現**使用者遇到的那個競態例外。
        #    因此改成直接測 nav.goto 的契約：用假的 page 物件餵進真實的錯誤訊息。
        print("      （以下用假 page 物件直接測 nav.goto 的處理邏輯）")

        REAL_ERR = ('Page.goto: Navigation to "https://x/000/tc_estock_welshas.html" '
                    'is interrupted by another navigation to '
                    '"https://x/000/tc_estock_welshas.html?top=1"')

        class FakePage:
            def __init__(self, err, final_url):
                self._err, self.url = err, final_url
            def goto(self, *a, **k):
                if self._err:
                    raise RuntimeError(self._err)
            def wait_for_load_state(self, *a, **k):
                pass
            def wait_for_url(self, pred, **k):
                if not pred(self.url):
                    raise RuntimeError("timeout")

        # (a) 遇到自我重導的例外，但最後在正確頁面 → 應視為成功
        swallowed = True
        try:
            nav.goto(FakePage(REAL_ERR, "https://x/000/tc_estock_welshas.html?top=1"),
                     "https://x/", expect_contains="tc_estock_welshas")
        except Exception as exc:
            swallowed = False
            print(f"      不該丟卻丟了：{exc}")
        check("自我重導例外 + 落在正確頁面 → 當成成功", swallowed)

        # (b) 不是自我重導的錯誤 → 必須原封不動丟出去，不可被吞掉
        passed_through = False
        try:
            nav.goto(FakePage("net::ERR_CONNECTION_RESET", "https://x/"),
                     "https://x/", expect_contains="tc_estock_welshas")
        except Exception as exc:
            passed_through = "ERR_CONNECTION_RESET" in str(exc)
        check("真正的連線錯誤不會被吞掉", passed_through)

        # (c) 容忍了例外，但最後落在錯的頁面（例如被踢回登入頁）→ 必須報錯
        reported = False
        try:
            nav.goto(FakePage(REAL_ERR, "https://x/evote/login/shareholder.html"),
                     "https://x/", expect_contains="tc_estock_welshas")
        except RuntimeError as exc:
            reported = "不在預期的頁面" in str(exc)
        check("容忍重導但落在錯頁面 → 仍然報錯", reported)

        print("\n[8] 表格延遲載入：不等就讀會讀到 0 筆（2026-10-14 實際踩過）")
        ctx4 = browser.new_context()
        t5 = ctx4.new_page()
        nav.goto(t5, LIST_URL, expect_contains="tc_estock_welshas")
        early = list_page_info(t5, sel)
        check("重現確認：剛導完時表格只有表頭（若失敗代表 fixture 沒重現，本組無意義）",
              early["row_count"] <= 1, f"row_count={early['row_count']}")
        check("剛導完時平台筆數還是 0（所以不能拿它當「真的沒有」的依據）",
              declared_total(early) == 0, early["page_info"])
        check("wait_for_rows 等得到資料", wait_for_rows(t5, sel))
        late = list_page_info(t5, sel)
        check("等完之後平台顯示 3 筆", declared_total(late) == 3, late["page_info"])
        check("等完之後讀得到 3 筆", len(read_meetings(t5, sel)) == 3)

        print("\n[9] 讀不到表格時的診斷資訊")
        t6 = ctx4.new_page()
        nav.goto(t6, LOGIN_URL)
        miss = list_page_info(t6, sel)
        check("沒有表格時 table_found=False", miss["table_found"] is False)
        check("沒有表格時 declared_total 回 None（不可誤判成 0 筆）",
              declared_total(miss) is None)
        ctx4.close()

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
