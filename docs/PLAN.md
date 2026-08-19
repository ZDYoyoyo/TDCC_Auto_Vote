# TDCC_Auto_Vote 實作計畫（草案 v0，待使用者拍板）

> 狀態：**尚未動工**。本檔記錄現地偵查的**已驗證事實**與建議架構。
> 事實區的每一條都附出處，可自行複驗；沒驗證過的一律標 ⚠️未驗證。

---

## 一、現地偵查結果（2026-08-19 實際抓取，非推測）

抓取方式：`curl` 抓靜態 HTML（未登入、未送出任何表單）。

| 項目 | 事實 | 出處 |
|---|---|---|
| 入口 | `https://stockservices.tdcc.com.tw/` → meta refresh → `/evote/index.html` | 抓取 root HTML |
| 股東登入頁 | `/evote/login/shareholder.html` | index.html 內 `href` |
| 登入 POST | `form[name=voteform]` → `/evote/login/shareholderLogin.html` | login 頁 line 699 |
| 帳號欄位 | `input[name=pageIdNo]`（身分證/統編，maxlength 18） | login 頁 |
| 密碼欄位 | `input[name=pageUserPwd]`（maxlength **12**） | login 頁 |
| 防重放 | hidden `_random`（每次載入不同）、`JspUserType=S`、`userType=S` | login 頁 |
| **反機器人** | **reCAPTCHA Enterprise v3（隱形、分數制）**，sitekey `6Lfla...5iBF`，`action:'login'`，token 寫進 hidden `token` 隨登入 POST 送出，每 110 秒刷新 | login 頁 line 1917-1928 |
| 圖形驗證碼 | 存在備用機制 `chgImg()` / `/evote/code_verify.jpg`，搭配 hidden `errorCount`（推測：密碼錯誤達次數才出現，⚠️未驗證） | login 頁 line 1771-1779 |
| 其他登入方式 | 自然人憑證（`twcaForm`）、行動憑證（`phone-ca-handler.js`、`qrid`/`sessionToken`） | login 頁 |
| 裝置指紋 | 載入 `js/device.min.js` | index/login 頁 |
| 技術棧 | JSP + jQuery 3.6.1，**傳統多頁式（非 SPA）**，頁面由伺服器產生 | 資源清單 |
| 投票頁路徑樣式 | `/evote/shareholder/109/emeeting.html`、`/evote/shareholder/110/00.html`、`111/00`、`112/01`、`113/00` 等 | index.html 內 `location.href` |
| 登入後投票流程是否也有 reCAPTCHA | **⚠️未驗證**（需登入後才看得到；目前只確認登入頁有，且 `action` 標記為 `'login'`） | — |

### 這份偵查改變了什麼

原本參考資料假設「驗證碼 = 圖片，程式暫停讓你手動輸入」。**實際不是。**
reCAPTCHA v3 是**隱形分數制**：沒有東西可以讓你「手動輸入」，它在背景根據
瀏覽器指紋、滑鼠軌跡、IP 信譽等打分數。Playwright/Selenium 開的瀏覽器分數
通常偏低，登入可能被擋或被要求額外驗證。

要「穩定通過」它，做法只有偽裝指紋（stealth 外掛）、換住宅代理、接驗證碼代解
服務——**這是在破解金融平台的反機器人管制，本專案不做**（也違反平台條款）。

---

## 二、核心設計決策：半自動（attended），不是全自動

```
┌── 人做（一次） ──────────┐  ┌── 程式做（重複 N 次） ─────────────┐
│ 開瀏覽器 → 輸入帳密       │  │ 逐檔開議案 → 填投票 → 送出 →       │
│ → 過 reCAPTCHA → 登入成功 │→ │ 截圖存證 → 命名歸檔 → 寫結果紀錄   │
└──────────────────────┘  └────────────────────────────────┘
```

**做法**：程式用 Playwright 開一個**有頭 + 持久化 profile** 的瀏覽器
（`launch_persistent_context`），停在登入頁等你**自己登入**；偵測到登入成功後
接手跑批次。持久化 profile 讓瀏覽器指紋穩定、且 session 有機會沿用。

**為什麼這樣而不是全自動**：
1. 登入那一關的反機器人**繞不過去且不該繞**（見上）。
2. 真正的痛點不在登入（一次），在**逐檔點 N 次議案 + 截圖 + 命名歸檔**（N 檔）。
   把後者自動化，省掉 ~90% 的手工，風險與複雜度卻低一個數量級。
3. 全程有人在場 → 送出前可人工攔截，不會半夜自動對你的股東帳戶做不可逆操作。

**被否決的替代方案**：
- ❌ headless 全自動排程（GitHub Actions / cron）：登入過不了，且要把身分證+密碼
  放雲端。
- ❌ 直接打 `/evote/login/shareholderLogin.html` API（跳過瀏覽器）：少了 reCAPTCHA
  token 會被擋，等於要偽造反機器人驗證。
- ❌ 驗證碼代解服務 / stealth 指紋偽裝：破解安全管制，明確不做。

---

## 三、建議架構

```
TDCC_Auto_Vote/
├── 1_執行投票.bat          # 使用者入口（雙擊即可）
├── 2_預跑不送出.bat        # dry-run 入口
├── config/
│   ├── stocks.yaml         # 要投的股票清單 + 每檔投票決策
│   └── selectors.yaml      # 網站元素定位（平台改版只改這一檔）
├── src/tdcc_vote/
│   ├── browser.py          # Playwright 持久化 context 啟動
│   ├── login_gate.py       # 停下等人工登入，輪詢直到偵測登入成功
│   ├── meetings.py         # 抓「可投票清單」→ 標準化成 dataclass
│   ├── vote.py             # 單檔投票（狀態機：開啟→填選→確認→送出）
│   ├── evidence.py         # 截圖 + 檔名 + 結果 JSONL
│   └── run_all.py          # 批次驅動 + 總結報告
├── tools/explore.py        # 🔧 偵查工具：登入後 dump 頁面結構供填 selectors.yaml
├── evidence/YYYY-MM-DD/    # 截圖（gitignore）
└── logs/results/*.jsonl    # 每檔結果（gitignore）
```

**selectors 外置的理由**：目前**沒有任何登入後頁面的真實 DOM**。現在寫死選擇器
＝憑空捏造「看起來合理」的東西（明文反模式）。所以：
- 選擇器一律放 `config/selectors.yaml`，程式碼只引用 key。
- 先寫 `tools/explore.py`：你登入後它把實際 DOM／候選選擇器 dump 出來，
  用**真實資料**填 yaml。

---

## 四、安全設計（不可退讓）

| 項目 | 做法 |
|---|---|
| **預設不送出** | `--dry-run` 為**預設**：跑完整流程但停在最終確認頁、截圖、不按送出。要加 `--confirm` 才真的投 |
| 憑證 | `.env` + python-dotenv；`.env`、`profile/`、`evidence/`、`logs/` 全部進 `.gitignore` |
| session 檔 | 持久化 profile 內含登入 cookie ＝ 等同帳號憑證，**絕不 commit** |
| 節奏 | 每步 1~3 秒隨機延遲。目的是**不打壞平台、模擬正常人操作速度**，不是偽裝身分 |
| 失敗處理 | 任一步失敗 → 立刻截圖 + 記錄例外 + 該檔標記 FAILED，**繼續下一檔**，最後總結 |
| 結果紀錄 | 投票**當下**就寫入議案內容、我方選擇、截圖路徑、時間戳（point-in-time，事後不重算） |
| 誠實回報 | 結尾印「成功 X / 失敗 Y / 跳過 Z」，失敗逐條列原因。**有跳過就不准說「全部完成」** |

---

## 五、本專案鐵律（草案，P1 驗證後正式寫進 CLAUDE.md）

1. **股票代號一律字串**：`00878` 用 int 會變 `878`。yaml 讀取後強制 `str` 並補零檢查。
2. **時區一律 Asia/Taipei**：容器/伺服器是 UTC，`datetime.now()` 無時區在台灣晚上跑會
   差一天 → 誤判投票截止日。所有日期在**讀取那一層**轉成 `Asia/Taipei` 的 ISO 日期。
3. **股數只讀不算**：平台顯示「股」或「張」在抓取層確定並記錄原文，投票流程用不到
   換算，**不要自己 ×1000 或 ÷1000**。

---

## 六、分階段

| 階段 | 內容 | 需要你配合 |
|---|---|---|
| **P0** | 專案骨架、`.gitignore`、config schema、dry-run 引擎、`tools/explore.py` | 否 |
| **P1** | 你跑一次 explore（手動登入）→ 用真實 DOM 填 `selectors.yaml` → 單檔跑通 dry-run | **要**（一次，約 10 分鐘） |
| **P2** | 批次多檔 + 截圖存證 + 結果報告 + `.bat` 入口 | 驗收 |
| **P3** | 通知（LINE/Telegram）、排程提醒（提醒你去投，不是自動投） | 視需要 |

---

## 七、明確不做

- 不做無人值守全自動登入、不繞 reCAPTCHA、不接驗證碼代解、不做指紋偽裝。
- 不把帳密放 GitHub Actions／任何雲端。
- 不在沒有真實 DOM 前寫死選擇器。
- 不自動處理「代領紀念品平台」的上傳（那是另一家的服務，先產出乾淨的截圖與清單即可）。

---

## 八、待拍板（見對話）

1. 自動化程度：確認採半自動？
2. 投票決策來源：一律贊成／每檔自訂？
3. 平台是否已內建「全部議案一鍵贊成」？若有，本專案範圍可再縮小。
4. 執行環境：Windows 本機？

---

## ⚠️ 服務條款

集保股東 e 服務是官方系統、操作的是你**本人**的股東帳戶。自動化操作是否違反其
使用條款，我沒有查證過，**你應自行確認**。本設計刻意保留「登入由你本人完成、
送出前可攔截」，就是為了讓每一次操作都確實是你本人的意思表示。
