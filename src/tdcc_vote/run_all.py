"""批次投票主程式。

兩個階段（使用者 2026-10-14 實測後要求）：
  階段 1 投票：逐檔 點進去 → 全部贊成 → 下一步 → 你按「確認投票結果」→ 回清單 → 下一檔
  階段 2 截圖：全部投完後，回清單逐檔點「查詢」，拍已投票結果頁存進「投票完成」
              （完成頁只寫「投票完成」，不是要交給代領平台的畫面）

  確認頁有隱形機器人驗證；2026-10-14 實測程式自動按會被擋，所以預設由你按。
  --auto-submit 可讓程式先試著按一次，被擋再交給你。

--receipts-only：不投票，只對清單上「已投票」的檔補拍查詢截圖。

⚠️ 預設是 --dry-run（跑完整流程但停在確認頁不送出）。要真的投票才加 --confirm。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import evidence, nav
from .browser import DEFAULT_PROFILE, launch
from .config import load_selectors
from .login_gate import list_tabs, open_login_page, pick_page
from .explore import DEFAULT_OUT as EXPLORE_DIR, dump
from .evidence import VoteRecord
from .meetings import (Meeting, declared_total, list_page_info, read_meetings, votable,
                       voted)
from .receipts import capture_receipt
from .vote import AbortAll, vote_one


def _print_list(meetings: list[Meeting]) -> None:
    print(f"\n   清單共 {len(meetings)} 筆：")
    for m in meetings:
        mark = "✅可投票" if m.can_vote else "—"
        print(f"     {mark}  {m}")


def _capture_receipts(page, selectors: dict, codes: list[str]) -> list[VoteRecord]:
    """階段 2：回清單，逐檔點「查詢」拍已投票結果頁。每拍一檔就寫一筆紀錄。"""
    print("\n" + "─" * 60)
    print(f"  階段 2：查詢截圖（{len(codes)} 檔）")
    print("─" * 60)
    nav.goto(page, selectors["meetings"]["url"],
             expect_contains=selectors["meetings"]["url_contains"])
    # 重新讀清單：投完票之後各列的連結會變（vote 不見、多出 qry/modify/repael）
    by_code = {m.stock_code: m for m in read_meetings(page, selectors)}

    results: list[VoteRecord] = []
    for i, code in enumerate(codes, 1):
        m = by_code.get(code)
        if m is None:
            rec = VoteRecord(stock_code=code, company="", meeting_date="",
                             status="RECEIPT_FAILED", detail="重新讀清單時找不到這一檔")
            print(f"\n[{i}/{len(codes)}] {code} — ❌ {rec.detail}")
        else:
            print(f"\n[{i}/{len(codes)}] {m}")
            rec = capture_receipt(page, selectors, m)
        results.append(rec)
        evidence.record(rec)
    return results


def _summary(records: list) -> int:
    """結尾報告。有跳過或失敗就不准說「全部完成」。"""
    ok = [r for r in records if r.status == "OK"]
    dry = [r for r in records if r.status == "DRY_RUN"]
    failed = [r for r in records if r.status == "FAILED"]
    skipped = [r for r in records if r.status == "SKIPPED"]
    shot_ok = [r for r in records if r.status == "RECEIPT"]
    shot_failed = [r for r in records if r.status == "RECEIPT_FAILED"]

    print("\n" + "=" * 60)
    if ok or dry or failed or skipped:
        print(f"  成功投票 {len(ok)}　預跑未送出 {len(dry)}　失敗 {len(failed)}　跳過 {len(skipped)}")
    if shot_ok or shot_failed:
        print(f"  查詢截圖 成功 {len(shot_ok)}　失敗 {len(shot_failed)}")
    print("=" * 60)
    for label, group in (("❌ 投票失敗", failed), ("⏭ 跳過", skipped),
                         ("❌ 截圖失敗", shot_failed)):
        for r in group:
            print(f"  {label}：{r.stock_code} {r.company} — {r.detail}")
    if failed:
        print("\n  ⚠️ 有投票失敗的項目，請自己上平台確認那幾檔的投票狀況。")
    if shot_failed:
        print("\n  ⚠️ 有截圖失敗的項目（票已經投了）。可以之後用「4_補查詢截圖.bat」補拍，")
        print("     或自己上網站點「查詢」截圖。")
    if dry:
        print("\n  ℹ️ 這次是預跑，票**沒有真的送出**。要真的投票請加 --confirm。")
    return 1 if (failed or shot_failed) else 0


def _ask_start(prompt_list: str) -> bool:
    """列出要處理的檔，等使用者按 Enter。回傳是否開始。"""
    print(prompt_list)
    print("按 Enter 開始（q=離開）")
    try:
        return input("> ").strip().lower() != "q"
    except (EOFError, KeyboardInterrupt):
        return False


def _run_receipts_only(page, selectors: dict, meetings: list[Meeting], only: set[str],
                       records: list) -> int | None:
    """只補查詢截圖。回傳 None＝有做事（往下印總結）；int＝提早結束的回傳碼。"""
    done = voted(meetings, selectors["meetings"].get("voted_status_text", "已投票"))
    if only:
        done = [m for m in done if m.stock_code in only]
    if not done:
        print("\n清單上沒有「已投票」且有「查詢」連結的檔。")
        return 0
    if not _ask_start(f"\n要補拍 {len(done)} 檔：" +
                      "、".join(f"{m.stock_code} {m.company}" for m in done)):
        return 0
    records += _capture_receipts(page, selectors, [m.stock_code for m in done])
    return None


def _run_voting(page, selectors: dict, meetings: list[Meeting], only: set[str],
                records: list, args) -> int | None:
    """階段 1 投票，投完接階段 2 查詢截圖。回傳 None＝有做事；int＝提早結束的回傳碼。"""
    targets = votable(meetings)
    if only:
        targets = [m for m in targets if m.stock_code in only]
    if not targets:
        print("\n沒有可投票的項目（清單裡沒有任何檔給出投票連結）。")
        return 0
    if not _ask_start(f"\n要處理 {len(targets)} 檔：" +
                      "、".join(f"{m.stock_code} {m.company}" for m in targets)):
        return 0

    print("\n" + "─" * 60)
    print(f"  階段 1：投票（{len(targets)} 檔）")
    print("─" * 60)
    aborted = False
    for i, m in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {m}")
        try:
            rec = vote_one(page, selectors, m, confirm=args.confirm,
                           auto_submit=args.auto_submit)
        except AbortAll:
            print("   已中止批次。")
            aborted = True
            break
        records.append(rec)
        evidence.record(rec)

    voted_codes = [r.stock_code for r in records if r.status == "OK"]
    if voted_codes and aborted:
        # 使用者按 q 是要停，尊重他；已投的票之後可以補拍
        print("\n  你中止了批次，所以沒有進行查詢截圖。")
        print("  已投的票可以之後用「4_補查詢截圖.bat」補拍。")
    elif voted_codes:
        records += _capture_receipts(page, selectors, voted_codes)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="集保電子投票批次輔助（半自動）")
    ap.add_argument("--confirm", action="store_true",
                    help="真的投票。不加這個就是預跑，停在確認頁不送出")
    ap.add_argument("--auto-submit", action="store_true",
                    help="讓程式先試著自動按「確認投票結果」（2026-10-14 實測會被機器人驗證擋下）")
    ap.add_argument("--receipts-only", action="store_true",
                    help="不投票，只對清單上「已投票」的檔補拍查詢截圖")
    ap.add_argument("--only", default="",
                    help="只處理這些證券代號，逗號分隔，例：--only 1101,2330")
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    ap.add_argument("--channel", default=None, help='用系統瀏覽器，例：--channel chrome')
    ap.add_argument("--headless", action="store_true", help="無視窗（僅測試用）")
    args = ap.parse_args(argv)

    selectors = load_selectors()
    only = {c.strip() for c in args.only.split(",") if c.strip()}

    print("=" * 60)
    if args.receipts_only:
        print("  模式：只補查詢截圖（不投票）")
        print("  對清單上「已投票」的檔逐一點「查詢」截圖，存進「投票完成」資料夾。")
    elif args.confirm:
        print("  模式：⚠️ 真的投票（--confirm）")
        print("  全部投完後，會自動回清單逐檔點「查詢」截圖。")
        if args.auto_submit:
            print("  程式會先試著自動按「確認投票結果」；若被機器人驗證擋下，")
            print("  會停下來請你手動按。")
        else:
            print("  每一檔填好後會停下來，由你在瀏覽器按「確認投票結果」。")
    else:
        print("  模式：預跑（不會送出任何票）")
        print("  會跑完整流程並停在確認頁截圖，但不送出。要真投票請加 --confirm。")
    print("=" * 60)

    records: list = []
    with sync_playwright() as pw:
        ctx = launch(pw, profile_dir=args.profile, channel=args.channel,
                     headless=args.headless)
        page = pick_page(ctx, selectors)
        try:
            open_login_page(page, selectors)
            print("\n請在**程式剛剛開的那個瀏覽器視窗**裡登入，"
                  "登好之後回來這裡按 Enter（q=離開）")
            try:
                if input("> ").strip().lower() == "q":
                    return 0
            except (EOFError, KeyboardInterrupt):
                return 0

            # ⚠️ 登入後平台會另開頁（網址帶 ?top=1），所以要重新挑一次分頁，
            #    不能繼續用原本那個 page 物件。實際踩過。
            page = pick_page(ctx, selectors)

            # 不靠網址猜有沒有登入，直接去清單頁看能不能到。
            # 能到就是有登入；被踢回登入頁就是沒有。
            # ⚠️ 用 nav.goto 而不是 page.goto：這一頁會自己重導成 ?top=1，
            #    page.goto 會丟「interrupted by another navigation」。實際踩過。
            print(f"→ 前往清單頁：{selectors['meetings']['url']}")
            try:
                nav.goto(page, selectors["meetings"]["url"],
                         expect_contains=selectors["meetings"]["url_contains"])
            except Exception as exc:
                print(f"⚠️ 開清單頁失敗：{exc}")
                print(f"   程式目前看到的網址：{page.url}")
                print("   程式開的所有分頁：")
                for u in list_tabs(ctx):
                    print(f"     - {u}")
                return 1

            if "/login/" in page.url or "/evote/shareholder/" not in page.url:
                print("\n⚠️ 到不了清單頁，看起來這個瀏覽器還沒登入。")
                print(f"   程式目前看到的網址：{page.url}")
                print("   程式開的所有分頁：")
                for u in list_tabs(ctx):
                    print(f"     - {u}")
                print("\n   最常見的原因：你是在**自己平常用的瀏覽器**登入的。")
                print("   請在程式剛剛跳出來的那個視窗裡登入，再重跑一次。")
                return 1

            meetings = read_meetings(page, selectors)
            info = list_page_info(page, selectors)
            total = declared_total(info)
            _print_list(meetings)

            # ⚠️ 讀到 0 筆不可以直接說「沒有可投票的項目」。
            #    2026-10-14 實跑就是這樣：程式說沒有，使用者明明有。
            #    假的「沒事」比報錯更危險——使用者會以為不用投了。
            if not meetings:
                # ⚠️ 平台的「共計0筆」也不能當成「真的沒有」的證據：
                #    頁面載入中時它會先顯示 0 筆，資料進來後才變成真的數字
                #    （fixture 測試第 8 組有重現）。所以一律當成「不確定」處理。
                print("\n" + "!" * 60)
                print("  ⚠️ 讀不到清單，但這**不代表**你沒有可投票的項目。")
                if total == 0:
                    print("     平台顯示 0 筆。可能真的沒有，也可能是頁面資料還沒載完。")
                print(f"     網址：{info.get('url')}")
                print(f"     找到表格：{'是' if info.get('table_found') else '否'}"
                      f"　表格列數：{info.get('row_count')}"
                      f"　平台顯示：{info.get('page_info') or '(讀不到)'}")
                print("!" * 60)
                try:
                    folder = dump(page, EXPLORE_DIR, 1)
                    print(f"\n  已把這一頁存下來：{folder}")
                    print("  請把裡面的 structure.md 交給 Claude 診斷。")
                except Exception as exc:
                    print(f"\n  （存頁面失敗：{exc}）")
                print("  在修好之前，請先到網站上手動投票，不要被這個工具卡住截止日。")
                return 1

            if total is not None and total > len(meetings):
                print(f"\n  ⚠️ 平台說共 {total} 筆，只讀到 {len(meetings)} 筆。"
                      "可能有分頁，程式還不會翻頁——只會處理讀到的這些。")
                print("     其餘的請自己上網站確認。")

            if args.receipts_only:
                early = _run_receipts_only(page, selectors, meetings, only, records)
            else:
                early = _run_voting(page, selectors, meetings, only, records, args)
            if early is not None:
                return early
        finally:
            # 使用者第一次實跑時，看到瀏覽器突然關掉不確定是否正常。先講。
            print("\n（程式結束，瀏覽器會自動關閉。結果以下方總結與截圖為準。）")
            ctx.close()

    path = evidence.RESULTS_DIR / f"{evidence.today()}.jsonl"
    code = _summary(records)
    if records:
        if any(r.status == "RECEIPT" for r in records):
            print(f"\n  查詢截圖（交給代領平台用）：{evidence.receipt_dir()}")
        print(f"  過程截圖：{evidence.EVIDENCE_DIR / evidence.today()}")
        print(f"  紀錄：{path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
