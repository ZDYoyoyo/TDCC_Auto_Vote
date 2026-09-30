"""單檔投票流程（狀態機）。

流程（網址皆為實抓確認）：
  清單頁 ──點 vote──▶ 議案頁 /001/1_03.html
                        ├─ optionAll(0) 全部贊成(承認)
                        └─ 下一步 checkVote()
                              ▼
                      確認頁 /001/2_01.html   ⛔ 掛 invisible reCAPTCHA
                        └─「確認投票結果」由**使用者本人**按
                              ▼
                      完成頁 /001/6_01.html  處理結果「投票已完成！」
                        └─ #go 確認 ─▶ 回清單

⛔⛔ 定位鐵律：一律用 onclick 裡的函式名，**不准用 name 或 class**。
   確認頁「確認投票結果」與「取消投票」的 name 都是 "button"；
   議案頁「下一步」與「取消投票」的 class 都是 "o-button"。
   用 name/class 定位會有機會按到「取消投票」，把使用者填好的票整筆丟掉。

⛔ 程式永遠不點：確認投票結果（reCAPTCHA 擋自動化）、取消投票、修改、撤銷。
"""

from __future__ import annotations

from playwright.sync_api import Page

from . import evidence
from .evidence import VoteRecord
from .meetings import ACTION_VOTE, Meeting

NAV_TIMEOUT = 30_000


class AbortAll(Exception):
    """使用者要求中止整個批次。"""


def _wait_url(page: Page, fragment: str, timeout: int = NAV_TIMEOUT) -> None:
    page.wait_for_url(lambda url: fragment in url, timeout=timeout)


def _back_to_list(page: Page, selectors: dict) -> None:
    """回清單頁。刻意用 goto 而不是點「取消投票」——那顆鈕會跳確認框、
    而且語意是放棄，不該由程式代按。"""
    try:
        page.goto(selectors["meetings"]["url"], wait_until="domcontentloaded",
                  timeout=NAV_TIMEOUT)
    except Exception as exc:
        print(f"   ⚠️ 回清單頁失敗：{exc}")


def _ask_confirmed() -> str:
    """等使用者在瀏覽器按下「確認投票結果」。

    ⚠️ 刻意用 input() 等使用者講「我按完了」，而不是輪詢網頁等它自己變。
    先前 explore 用輪詢等登入，結果程式 10 分鐘不讀鍵盤、看起來像當掉。
    使用者主導的等待不會有那個問題——他知道自己要按 Enter。
    """
    print()
    print("   " + "▂" * 52)
    print("   👉 請在瀏覽器按【確認投票結果】")
    print("      （這一步程式不能代按：那一頁掛了隱形機器人驗證）")
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
) -> VoteRecord:
    """投一檔。confirm=False（預設）時跑到確認頁就停，不送出。"""
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

        # ⑤ 送出那一下由使用者本人按
        while True:
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
                break

            # 還沒到完成頁：可能沒按、或被機器人驗證擋下來
            snap("x_確認後未完成")
            print(f"   ⚠️ 還沒偵測到完成頁（目前在 {page.url}）")
            print("      若畫面顯示「機器人驗證失敗」，請重新整理該頁再試一次；")
            print("      或輸入 s 跳過這一檔。")

        # ⑥ 驗證完成頁真的寫著成功，不是「跑完了」就算成功
        rows = evidence.read_table(page, done_cfg["result_table"])
        text = " ".join(" ".join(r["cells"]) for r in rows)
        snap("4_完成頁")

        if done_cfg["success_text"] in text:
            rec.status = "OK"
            rec.detail = text.strip()[:200]
            print("   ✅ 投票已完成")
        else:
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
