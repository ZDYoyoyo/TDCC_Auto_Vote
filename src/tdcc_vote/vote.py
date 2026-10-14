"""單檔投票流程（狀態機）。

流程（網址皆為實抓確認）：
  清單頁 ──點 vote──▶ 議案頁 /001/1_03.html
                        ├─ optionAll(0) 全部贊成(承認)
                        └─ 下一步 checkVote()
                              ▼
                      確認頁 /001/2_01.html   ⚠️ 掛 invisible reCAPTCHA
                        └─「確認投票結果」：程式先自動按一次；
                          被機器人驗證擋下 → 退回請使用者手動按
                              ▼
                      完成頁 /001/6_01.html  處理結果「投票已完成！」
                        └─ #go 確認 ─▶ 回清單

⛔⛔ 定位鐵律：一律用 onclick 裡的函式名，**不准用 name 或 class**。
   確認頁「確認投票結果」與「取消投票」的 name 都是 "button"；
   議案頁「下一步」與「取消投票」的 class 都是 "o-button"。
   用 name/class 定位會有機會按到「取消投票」，把使用者填好的票整筆丟掉。

⛔ 程式永遠不點：取消投票、修改、撤銷。

⚠️ 自動按「確認投票結果」（2026-10-14 使用者明確授權、並切換權限模式後加入）：
   只做**單純的點擊**。不偽裝瀏覽器指紋、不裝 stealth 外掛、不接驗證碼代解——
   機器人檢查照常判斷，它說不行就是不行，程式退回請人手動按，不再往下繞。
   先前使用者在確認頁停留過久才按、遇到「機器人驗證失敗」，可能是 token 過期；
   程式到確認頁幾秒內就按，token 較新鮮，所以值得一試。
"""

from __future__ import annotations

from playwright.sync_api import Page

from . import evidence, nav
from .evidence import VoteRecord
from .meetings import ACTION_VOTE, Meeting

NAV_TIMEOUT = 30_000
SUBMIT_TIMEOUT = 60_000   # 送出後有「憑證簽章中... 請稍候」，給久一點
POLL_MS = 500
# 使用者 2026-09-30 在真站看到的原文。看到就立刻退回手動，不乾等到 SUBMIT_TIMEOUT：
# 等越久，確認頁的驗證 token 越舊，使用者接著手動按反而更容易被擋。
BOT_FAIL_TEXT = "機器人驗證失敗"


class AbortAll(Exception):
    """使用者要求中止整個批次。"""


def _wait_url(page: Page, fragment: str, timeout: int = NAV_TIMEOUT) -> None:
    page.wait_for_url(lambda url: fragment in url, timeout=timeout)


def _back_to_list(page: Page, selectors: dict) -> None:
    """回清單頁。刻意用導頁而不是點「取消投票」——那顆鈕會跳確認框、
    而且語意是放棄，不該由程式代按。

    用 nav.goto 而不是 page.goto：清單頁會自己重導成 ?top=1。"""
    try:
        nav.goto(page, selectors["meetings"]["url"],
                 expect_contains=selectors["meetings"]["url_contains"],
                 timeout=NAV_TIMEOUT)
    except Exception as exc:
        print(f"   ⚠️ 回清單頁失敗：{exc}")


def _try_auto_submit(page: Page, selectors: dict) -> tuple[bool, list[str]]:
    """自動按「確認投票結果」一次並等完成頁。回傳（是否成功, 期間跳出的對話框文字）。

    對話框處理：
    - alert（只有「確定」）→ 按確定，記下文字（例如「機器人驗證失敗」）。
    - confirm／prompt（有「取消」）→ **一律取消**並記下文字。
      不知道它在問什麼之前，不替使用者回答「是」。取消只會讓這次沒送出、
      退回手動，最壞是多按一下，不會投錯。
    """
    confirm_cfg = selectors["confirm"]
    done_cfg = selectors["done"]
    messages: list[str] = []

    def on_dialog(dialog) -> None:
        messages.append(f"[{dialog.type}] {dialog.message}")
        try:
            if dialog.type == "alert":
                dialog.accept()
            else:
                dialog.dismiss()
        except Exception:
            pass

    def bot_failed() -> bool:
        # 不確定真站是用 alert 還是頁面上的文字顯示，兩種都看
        if any(BOT_FAIL_TEXT in m for m in messages):
            return True
        try:
            return page.get_by_text(BOT_FAIL_TEXT).count() > 0
        except Exception:   # 導頁中，執行環境可能剛好被換掉
            return False

    page.on("dialog", on_dialog)
    try:
        page.click(confirm_cfg["submit_button"], timeout=NAV_TIMEOUT)
        print(f"     （等待完成頁，最多 {SUBMIT_TIMEOUT // 1000} 秒…）")
        waited = 0
        while waited < SUBMIT_TIMEOUT:
            if done_cfg["url_contains"] in page.url:
                return True, messages
            if bot_failed():
                if not any(BOT_FAIL_TEXT in m for m in messages):
                    messages.append(f"[頁面文字] {BOT_FAIL_TEXT}")
                return False, messages
            page.wait_for_timeout(POLL_MS)
            waited += POLL_MS
        return False, messages
    except Exception:
        return False, messages
    finally:
        try:
            page.remove_listener("dialog", on_dialog)
        except Exception:
            pass


def _ask_confirmed() -> str:
    """等使用者在瀏覽器按下「確認投票結果」（自動按被擋、或關閉自動按時才會用到）。

    ⚠️ 刻意用 input() 等使用者講「我按完了」，而不是輪詢網頁等它自己變。
    先前 explore 用輪詢等登入，結果程式 10 分鐘不讀鍵盤、看起來像當掉。
    使用者主導的等待不會有那個問題——他知道自己要按 Enter。
    """
    print()
    print("   " + "▂" * 52)
    print("   👉 請在瀏覽器按【確認投票結果】")
    print("      按完之後回來這裡按 Enter；s=跳過這一檔；q=結束全部")
    print("   " + "▂" * 52)
    try:
        return input("   > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "q"


def vote_one(
    page: Page,
    selectors: dict,
    meeting: Meeting,
    confirm: bool = False,
    auto_submit: bool = True,
) -> VoteRecord:
    """投一檔。

    confirm=False（預設）：跑到確認頁就停，不送出。
    confirm=True：送出。auto_submit=True 先自動按一次，被擋才請使用者手動按；
                  auto_submit=False 直接請使用者手動按。
    """
    code = meeting.stock_code
    rec = VoteRecord(
        stock_code=code,
        company=meeting.company,
        meeting_date=meeting.meeting_date,
        status="FAILED",
    )
    vote_cfg = selectors["vote"]
    confirm_cfg = selectors["confirm"]
    done_cfg = selectors["done"]

    def snap(kind: str) -> None:
        path = evidence.shot(page, code, kind)
        if path:
            rec.screenshots.append(path)

    try:
        onclick = meeting.actions.get(ACTION_VOTE)
        if not onclick:
            rec.status = "SKIPPED"
            rec.detail = "這一檔沒有投票連結（已投票或已截止）"
            return rec

        # ① 清單頁 → 議案頁。用完整 onclick 做精確比對，不會點錯列。
        print(f"   → 進入議案頁")
        page.click(f'a[onclick="{onclick}"]', timeout=NAV_TIMEOUT)
        _wait_url(page, vote_cfg["url_contains"])
        snap("1_議案頁")

        # ② 全部贊成（平台自己的按鈕；上下各一顆，取第一顆）
        print("   → 按「全部贊成(承認)」")
        page.locator(vote_cfg["select_all_agree"]).first.click(timeout=NAV_TIMEOUT)
        snap("2_已選全部贊成")

        # ③ 下一步 → 確認頁
        print("   → 按「下一步」")
        page.click(vote_cfg["next_button"], timeout=NAV_TIMEOUT)
        _wait_url(page, confirm_cfg["url_contains"])

        # ④ 在確認頁把「當下看到的議案與我方選擇」存下來（point-in-time）
        rec.proposals = [
            {"cells": " | ".join(r["cells"])}
            for r in evidence.read_table(page, confirm_cfg["summary_table"])
        ]
        snap("3_確認頁")

        if not confirm:
            rec.status = "DRY_RUN"
            rec.detail = "已填好並停在確認頁，未送出（預設行為；要真的投票請加 --confirm）"
            print("   ⏸ 停在確認頁，沒有送出（預設不送出）")
            _back_to_list(page, selectors)
            return rec

        # ⑤ 送出：先自動按一次，被擋才退回手動
        need_manual = True
        auto_note = ""   # 自動送出失敗的原因；投成功也要保留，真站診斷要靠它
        if auto_submit:
            print("   → 自動按「確認投票結果」")
            ok, dialogs = _try_auto_submit(page, selectors)
            for msg in dialogs:
                print(f"     （網頁訊息：{msg}）")
            if ok:
                rec.submitted_by = "auto"
                need_manual = False
            else:
                snap("x_自動送出被擋")
                note = "；".join(dialogs) or f"時間內沒到完成頁（目前在 {page.url}）"
                auto_note = f"自動送出未成功：{note}"
                rec.detail = auto_note
                print("   ⚠️ 自動送出沒有成功，改請你手動按。")
                print("      若畫面顯示「機器人驗證失敗」，請重新整理該頁後再按一次。")

        while need_manual:
            answer = _ask_confirmed()
            if answer == "q":
                rec.status = "SKIPPED"
                rec.detail = "使用者中止整個批次"
                _back_to_list(page, selectors)
                raise AbortAll
            if answer == "s":
                rec.status = "SKIPPED"
                rec.detail = "使用者跳過這一檔（未送出）"
                _back_to_list(page, selectors)
                return rec

            if done_cfg["url_contains"] in page.url:
                rec.submitted_by = "manual"
                break

            # 還沒到完成頁：可能沒按、或被機器人驗證擋下來
            snap("x_確認後未完成")
            print(f"   ⚠️ 還沒偵測到完成頁（目前在 {page.url}）")
            print("      若畫面顯示「機器人驗證失敗」，請重新整理該頁再試一次；")
            print("      或輸入 s 跳過這一檔。")

        # ⑥ 驗證完成頁真的寫著成功，不是「跑完了」就算成功
        rows = evidence.read_table(page, done_cfg["result_table"])
        text = " ".join(" ".join(r["cells"]) for r in rows)

        if done_cfg["success_text"] in text:
            rec.status = "OK"
            how = "程式自動送出" if rec.submitted_by == "auto" else "你手動送出"
            rec.detail = f"{how}｜{text.strip()[:200]}" + (f"｜{auto_note}" if auto_note else "")
            # 投完票的證明另放「投票完成」資料夾，方便一次找齊上傳給代領平台
            rec.receipt = evidence.receipt_shot(page, code, meeting.company)
            if rec.receipt:
                rec.screenshots.append(rec.receipt)
            print(f"   ✅ 投票已完成（{how}）")
            if rec.receipt:
                print(f"      完成截圖：{rec.receipt}")
        else:
            snap("x_完成頁無成功字樣")   # 失敗的不放進「投票完成」，留在過程資料夾
            rec.status = "FAILED"
            rec.detail = f"到了完成頁但找不到「{done_cfg['success_text']}」：{text.strip()[:200]}"
            print(f"   ❌ {rec.detail}")

        # ⑦ 按完成頁的「確認」回清單
        try:
            page.click(done_cfg["ack_button"], timeout=NAV_TIMEOUT)
            _wait_url(page, selectors["meetings"]["url_contains"])
        except Exception as exc:
            print(f"   ⚠️ 按完成頁「確認」失敗，直接回清單：{exc}")
            _back_to_list(page, selectors)
        return rec

    except AbortAll:
        raise
    except Exception as exc:
        rec.status = "FAILED"
        rec.detail = f"{type(exc).__name__}: {exc}".replace("\n", " ")[:300]
        print(f"   ❌ 失敗：{rec.detail}")
        snap("x_失敗")
        _back_to_list(page, selectors)
        return rec
