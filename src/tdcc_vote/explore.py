"""偵查工具：把登入後的真實頁面結構 dump 出來。

為什麼需要這支：登入後的頁面（可投票清單、議案頁）沒有登入就看不到，
所以現在沒有任何真實 DOM。在真實 DOM 之前寫死選擇器＝憑空捏造，
所以第一步是先把真東西抓下來，再據以填 config/selectors.yaml。

用法（Windows 雙擊 1_偵查頁面結構.bat 即可）：
  1. 程式開瀏覽器並停在登入頁 → 你自己登入
  2. 你在瀏覽器裡點到想分析的頁面（例：可投票股東會清單、某一檔的議案頁）
  3. 回到這個黑色視窗按 Enter → 它把當前頁面存下來
  4. 重複 2-3，全部抓完輸入 q 結束

程式不會自己等、也不會自己動；提示一出現就可以按 Enter。

⚠️ 產出的檔案含你的姓名、身分證、持股明細等個資，存在 explore/ 底下，
   已加入 .gitignore。不要外傳、不要貼到公開的地方。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from .browser import DEFAULT_PROFILE, launch
from .config import load_selectors
from .login_gate import is_logged_in, open_login_page
from .paths import PROJECT_ROOT, safe_name, stamp

DEFAULT_OUT = PROJECT_ROOT / "explore"

# 在頁面裡跑，收集所有可能拿來當選擇器的元素
_COLLECT_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().slice(0, 100);
  const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
  const sel = (el) => {
    if (el.id) return '#' + esc(el.id);
    const nm = el.getAttribute('name');
    if (nm) return el.tagName.toLowerCase() + '[name="' + nm + '"]';
    const cn = (typeof el.className === 'string') ? el.className.trim() : '';
    const cls = cn ? '.' + cn.split(/\s+/).slice(0, 2).map(esc).join('.') : '';
    return el.tagName.toLowerCase() + cls;
  };
  const vis = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const take = (arr, n) => arr.slice(0, n);
  const counts = {};
  const keep = (key, arr, n) => { counts[key] = arr.length; return take(arr, n); };

  const links = keep('links', [...document.querySelectorAll('a[href]')]
    .filter(vis)
    .map(a => ({ text: clean(a.innerText), href: a.getAttribute('href'), sel: sel(a) }))
    .filter(x => x.text || x.href), 300);

  const buttons = keep('buttons', [...document.querySelectorAll(
      'button, input[type=button], input[type=submit], [role=button], a[onclick]')]
    .filter(vis)
    .map(b => ({
      text: clean(b.innerText || b.value || b.getAttribute('aria-label')),
      sel: sel(b),
      onclick: clean(b.getAttribute('onclick')),
    })), 200);

  const fields = keep('fields', [...document.querySelectorAll('input, textarea')]
    .filter(el => el.type !== 'hidden')
    .map(el => ({
      type: el.type || el.tagName.toLowerCase(),
      name: el.getAttribute('name') || '',
      id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      value: (el.type === 'radio' || el.type === 'checkbox') ? (el.value || '') : '',
      checked: !!el.checked,
      sel: sel(el),
      visible: vis(el),
    })), 400);

  const selects = keep('selects', [...document.querySelectorAll('select')].map(s => ({
    name: s.getAttribute('name') || '', id: s.id || '', sel: sel(s),
    options: take([...s.options].map(o => clean(o.text) + ' [' + o.value + ']'), 30),
  })), 60);

  const tables = keep('tables', [...document.querySelectorAll('table')].map((t, i) => {
    const rows = [...t.rows];
    return {
      index: i,
      sel: sel(t),
      row_count: rows.length,
      headers: rows.length ? take([...rows[0].cells].map(c => clean(c.innerText)), 15) : [],
      sample_row: rows.length > 1 ? take([...rows[1].cells].map(c => clean(c.innerText)), 15) : [],
    };
  }), 40);

  return {
    url: location.href,
    title: document.title,
    links, buttons, fields, selects, tables, counts,
  };
}
"""


def _md_section(title: str, lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "_（無）_"
    return f"\n## {title}\n\n{body}\n"


def _heading(name: str, shown: int, total: int) -> str:
    """數量標題。有截斷就明講，不要讓人以為看到的就是全部。"""
    if total > shown:
        return f"{name}（顯示 {shown} / 共 {total}，⚠️已截斷）"
    return f"{name}（{total}）"


def _render_markdown(info: dict, frames: list[dict]) -> str:
    counts = info.get("counts", {})
    out = [f"# 頁面結構：{info['title']}", "", f"- 網址：`{info['url']}`"]

    out.append(_md_section(
        _heading("連結", len(info["links"]), counts.get("links", len(info["links"]))),
        [f"- `{x['sel']}` → {x['text'] or '(無文字)'} — `{x['href']}`" for x in info["links"]],
    ))
    out.append(_md_section(
        _heading("按鈕", len(info["buttons"]), counts.get("buttons", len(info["buttons"]))),
        [f"- `{x['sel']}` → {x['text'] or '(無文字)'}"
         + (f" — onclick: `{x['onclick']}`" if x["onclick"] else "")
         for x in info["buttons"]],
    ))
    out.append(_md_section(
        _heading("輸入欄位／選項", len(info["fields"]), counts.get("fields", len(info["fields"]))),
        [f"- `{x['sel']}` type={x['type']} name={x['name'] or '-'}"
         + (f" value={x['value']}" if x["value"] else "")
         + (" ✔已勾選" if x["checked"] else "")
         + ("" if x["visible"] else " (隱藏)")
         + (f" placeholder={x['placeholder']}" if x["placeholder"] else "")
         for x in info["fields"]],
    ))
    out.append(_md_section(
        _heading("下拉選單", len(info["selects"]), counts.get("selects", len(info["selects"]))),
        [f"- `{x['sel']}` name={x['name'] or '-'}\n  - " + "\n  - ".join(x["options"])
         for x in info["selects"]],
    ))
    out.append(_md_section(
        _heading("表格", len(info["tables"]), counts.get("tables", len(info["tables"]))),
        [f"- `{x['sel']}` 共 {x['row_count']} 列\n"
         f"  - 表頭：{x['headers']}\n"
         f"  - 範例列：{x['sample_row']}"
         for x in info["tables"]],
    ))
    out.append(_md_section(
        f"Frames（{len(frames)}）",
        [f"- `{f['name'] or '(無名)'}` → `{f['url']}`" for f in frames],
    ))
    return "\n".join(out)


def dump(page: Page, out_root: Path, seq: int) -> Path:
    """把當前頁面存成一個資料夾：HTML + 截圖 + 結構摘要。"""
    info = page.evaluate(_COLLECT_JS)
    frames = [{"name": f.name, "url": f.url} for f in page.frames]

    folder = out_root / f"{stamp()}_{seq:02d}_{safe_name(info['title'])}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "page.html").write_text(page.content(), encoding="utf-8")
    (folder / "structure.md").write_text(_render_markdown(info, frames), encoding="utf-8")
    page.screenshot(path=str(folder / "screenshot.png"), full_page=True)

    # 多個 frame 時，每個 frame 的 HTML 也各存一份（JSP 網站常用 frame 包投票區）
    if len(page.frames) > 1:
        fdir = folder / "frames"
        fdir.mkdir(exist_ok=True)
        for i, fr in enumerate(page.frames):
            try:
                (fdir / f"{i:02d}_{safe_name(fr.name or 'frame')}.html").write_text(
                    fr.content(), encoding="utf-8"
                )
            except Exception as exc:  # frame 可能已消失或跨網域
                (fdir / f"{i:02d}_ERROR.txt").write_text(str(exc), encoding="utf-8")

    print(f"   已存到：{folder}")
    print(f"   連結 {len(info['links'])} / 按鈕 {len(info['buttons'])} / "
          f"欄位 {len(info['fields'])} / 表格 {len(info['tables'])} / frame {len(frames)}")
    return folder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="集保投票頁面結構偵查工具")
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="瀏覽器 profile 目錄")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="輸出目錄")
    ap.add_argument("--channel", default=None, help='用系統瀏覽器，例：--channel chrome')
    ap.add_argument("--headless", action="store_true", help="無視窗模式（僅供測試，正常使用不要開）")
    args = ap.parse_args(argv)

    selectors = load_selectors()
    args.out.mkdir(parents=True, exist_ok=True)

    print("⚠️ 提醒：這支程式會把頁面原始碼與截圖存下來，內容含你的姓名／身分證／持股。")
    print(f"   存放位置：{args.out}（已在 .gitignore，不會被 commit）。請勿外傳。")
    print()

    with sync_playwright() as pw:
        ctx = launch(pw, profile_dir=args.profile, channel=args.channel, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            open_login_page(page, selectors)

            print()
            print("─" * 60)
            print(" 接下來都由你控制，程式不會自己動：")
            print("   1. 在瀏覽器裡登入")
            print("   2. 點到想分析的頁面")
            print("   3. 回到這個視窗按 Enter → 抓取那一頁")
            print("   4. 重複 2-3；全部抓完輸入 q 再按 Enter 結束")
            print("─" * 60)

            seq = 0
            while True:
                state = "已登入" if is_logged_in(page, selectors) else "還沒登入"
                try:
                    cmd = input(f"\n[{state}] 按 Enter 抓取目前頁面（q=結束）> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if cmd in {"q", "quit", "exit"}:
                    break
                try:
                    dump(page, args.out, seq + 1)
                    seq += 1
                except Exception as exc:
                    print(f"❌ 抓取失敗：{exc}")
                    if "closed" in str(exc).lower():
                        print("   瀏覽器好像被關掉了，結束。")
                        break

            print(f"\n完成，共抓取 {seq} 個頁面。")
            print(f"請把 {args.out} 裡的 structure.md 交給我，用來填 config/selectors.yaml。")
        finally:
            ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
