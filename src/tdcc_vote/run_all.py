"""批次投票主程式。

分工（因為確認頁掛了隱形機器人驗證，程式不能代按送出）：
  程式：讀清單 → 篩出可投票 → 逐檔點進去 → 全部贊成 → 下一步 → 截圖歸檔
  你  ：在確認頁按一下「確認投票結果」

⚠️ 預設是 --dry-run（跑完整流程但停在確認頁不送出）。要真的投票才加 --confirm。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import evidence
from .browser import DEFAULT_PROFILE, launch
from .config import load_selectors
from .login_gate import list_tabs, open_login_page, pick_page
from .meetings import Meeting, read_meetings, votable
from .vote import AbortAll, vote_one


def _print_list(meetings: list[Meeting]) -> None:
    print(f"\n   清單共 {len(meetings)} 筆：")
    for m in meetings:
        mark = "✅可投票" if m.can_vote else "—"
        print(f"     {mark}  {m}")


def _summary(records: list) -> int:
    """結尾報告。有跳過或失敗就不准說「全部完成」。"""
    ok = [r for r in records if r.status == "OK"]
    dry = [r for r in records if r.status == "DRY_RUN"]
    failed = [r for r in records if r.status == "FAILED"]
    skipped = [r for r in records if r.status == "SKIPPED"]

    print("\n" + "=" * 60)
    print(f"  成功投票 {len(ok)}　預跑未送出 {len(dry)}　失敗 {len(failed)}　跳過 {len(skipped)}")
    print("=" * 60)
    for label, group in (("❌ 失敗", failed), ("⏭ 跳過", skipped)):
        for r in group:
            print(f"  {label}：{r.stock_code} {r.company} — {r.detail}")
    if failed:
        print("\n  ⚠️ 有失敗的項目，請自己上平台確認那幾檔的投票狀況。")
    if dry:
        print("\n  ℹ️ 這次是預跑，票**沒有真的送出**。要真的投票請加 --confirm。")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="集保電子投票批次輔助（半自動）")
    ap.add_argument("--confirm", action="store_true",
                    help="真的投票。不加這個就是預跑，停在確認頁不送出")
    ap.add_argument("--only", default="",
                    help="只處理這些證券代號，逗號分隔，例：--only 1101,2330")
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    ap.add_argument("--channel", default=None, help='用系統瀏覽器，例：--channel chrome')
    ap.add_argument("--headless", action="store_true", help="無視窗（僅測試用）")
    args = ap.parse_args(argv)

    selectors = load_selectors()
    only = {c.strip() for c in args.only.split(",") if c.strip()}

    print("=" * 60)
    if args.confirm:
        print("  模式：⚠️ 真的投票（--confirm）")
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
            print(f"→ 前往清單頁：{selectors['meetings']['url']}")
            try:
                page.goto(selectors["meetings"]["url"], wait_until="domcontentloaded",
                          timeout=60000)
            except Exception as exc:
                print(f"⚠️ 開清單頁失敗：{exc}")
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
            _print_list(meetings)

            targets = votable(meetings)
            if only:
                targets = [m for m in targets if m.stock_code in only]
            if not targets:
                print("\n沒有可投票的項目（清單裡沒有任何檔給出投票連結）。")
                return 0

            print(f"\n要處理 {len(targets)} 檔：" +
                  "、".join(f"{m.stock_code} {m.company}" for m in targets))
            print("按 Enter 開始（q=離開）")
            try:
                if input("> ").strip().lower() == "q":
                    return 0
            except (EOFError, KeyboardInterrupt):
                return 0

            for i, m in enumerate(targets, 1):
                print(f"\n[{i}/{len(targets)}] {m}")
                try:
                    rec = vote_one(page, selectors, m, confirm=args.confirm)
                except AbortAll:
                    print("   已中止批次。")
                    break
                records.append(rec)
                evidence.record(rec)
        finally:
            ctx.close()

    path = evidence.RESULTS_DIR / f"{evidence.today()}.jsonl"
    code = _summary(records)
    if records:
        print(f"\n  截圖：{evidence.EVIDENCE_DIR / evidence.today()}")
        print(f"  紀錄：{path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
