"""直接執行 run_all.main()，從登入後一路跑到結尾報告。

為什麼要有這支：2026-10-14 第一次實跑踩到的三個 bug（寫死第一個分頁、
頁面自我重導、表格延遲載入）**全部**出在 run_all 這一層，而當時的測試只測了
它底下的零件，main() 本身從沒被執行過。

只替換兩件事：網址指向 fixture、鍵盤輸入改成預先排好的答案。
⚠️ 一樣只驗證邏輯，不代表真實網站可行。

跑法：PYTHONPATH=src python tests/test_run_all_e2e.py
"""

from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

import tdcc_vote.run_all as ra  # noqa: E402
from tdcc_vote import evidence  # noqa: E402

LOGIN = (ROOT / "tests/fixtures/evote/login/shareholder.html").as_uri()
TMP_ENTRY = (ROOT / "tests/fixtures/evote/shareholder/000/tc_estock_welshas_tmp.html").as_uri()
EMPTY = (ROOT / "tests/fixtures_empty/evote/shareholder/000/tc_estock_welshas.html").as_uri()

failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def run_main(list_url: str, answers: list[str], out: Path,
             extra_args: list[str] | None = None) -> int:
    sel = yaml.safe_load((ROOT / "config/selectors.yaml").read_text(encoding="utf-8"))
    sel["login"]["url"] = LOGIN
    sel["meetings"]["url"] = list_url
    sel["meetings"]["table_wait_ms"] = 3000
    ra.load_selectors = lambda: sel
    # 測試不可污染真實資料：所有產出導到暫存目錄
    ra.EXPLORE_DIR = out / "explore"
    evidence.EVIDENCE_DIR = out / "evidence"
    evidence.RESULTS_DIR = out / "logs"

    queue = list(answers)
    real_input = builtins.input
    builtins.input = lambda prompt="": (print(prompt, end=""), queue.pop(0))[1]
    try:
        return ra.main(["--headless", "--profile", str(out / "profile")] + (extra_args or []))
    finally:
        builtins.input = real_input


def main() -> int:
    if not os.environ.get("TDCC_CHROMIUM_PATH"):
        print("（提示：容器內需設 TDCC_CHROMIUM_PATH；Windows 本機不用）")
    tmp = Path(tempfile.mkdtemp(prefix="tdcc_e2e_"))

    print("\n[A] 正常清單（經 _tmp 入口、資料延遲載入）→ 預跑")
    code = run_main(TMP_ENTRY, ["", ""], tmp / "A")
    check("main() 回傳 0", code == 0, str(code))
    recs = []
    for f in (tmp / "A" / "logs").glob("*.jsonl"):
        recs += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    check("兩檔都有紀錄", len(recs) == 2, str(len(recs)))
    check("兩檔都是 DRY_RUN（沒有送出）", all(r["status"] == "DRY_RUN" for r in recs),
          str([r["status"] for r in recs]))
    check("紀錄裡代號是字串、00878 保留前導零",
          sorted(r["stock_code"] for r in recs) == ["00878", "1101"],
          str([r["stock_code"] for r in recs]))
    check("每檔至少 3 張截圖", all(len(r["screenshots"]) >= 3 for r in recs))

    print("\n[B] 表格讀不到 → 不可以說「沒有可投票的項目」")
    code = run_main(EMPTY, [""], tmp / "B")
    check("main() 回傳非 0（不確定就不能報成功）", code != 0, str(code))
    dumps = list((tmp / "B" / "explore").glob("*/structure.md"))
    check("自動存下頁面供診斷", len(dumps) == 1, str(len(dumps)))
    check("沒有產生任何投票紀錄", not (tmp / "B" / "logs").exists())

    print("\n[D] 真投模式（--confirm）：自動按確認，兩檔都投完、不需要使用者動手")
    # 只排兩個答案（登入後 Enter、開始 Enter）。若程式退回手動而多要輸入，
    # queue 會被 pop 空而丟例外，測試就會失敗——用來證明真的沒有打擾使用者。
    code = run_main(TMP_ENTRY, ["", ""], tmp / "D", ["--confirm"])
    check("main() 回傳 0", code == 0, str(code))
    recs_d = []
    for f in (tmp / "D" / "logs").glob("*.jsonl"):
        recs_d += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    check("兩檔都投成功", [r["status"] for r in recs_d] == ["OK", "OK"],
          str([r["status"] for r in recs_d]))
    check("兩檔都標明是程式自動送出", all(r["submitted_by"] == "auto" for r in recs_d),
          str([r["submitted_by"] for r in recs_d]))
    receipts = sorted(p.name for p in (tmp / "D" / "evidence" / "投票完成").glob("*.png"))
    check("「投票完成」資料夾有兩張，各帶代號", len(receipts) == 2
          and receipts[0].startswith("00878_") and receipts[1].startswith("1101_"),
          str(receipts))

    print("\n[C] 污染檢查")
    for d in ("evidence", "logs", "explore", "profile"):
        check(f"專案的 {d}/ 沒被建立", not (ROOT / d).exists())

    print("\n" + "=" * 56)
    if failures:
        print(f"  ❌ {len(failures)} 項失敗：" + "; ".join(failures))
        return 1
    print("  ✅ 全部通過（僅代表邏輯正確，不代表真實網站可行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
