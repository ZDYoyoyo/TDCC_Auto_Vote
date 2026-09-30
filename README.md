# TDCC_Auto_Vote — 集保股東會電子投票輔助工具

把「登入後逐檔點議案、投票、截圖、命名歸檔」這段重複工作自動化。

> **現在進度：P2 已寫完，但從未在真實網站跑過。**
> 邏輯已用「照實抓 DOM 重建的 fixture」驗證通過（17 項檢查），
> 但集保網站上的第一次實跑會發生在你的電腦上。第一次請用「2_預跑不送出」。

---

## 怎麼用（Windows）

### 第一次使用

1. 先裝好 [Python](https://www.python.org/downloads/)（**3.9 以上**，建議 3.12；
   **安裝時要勾「Add python.exe to PATH」**）
2. 雙擊 **`0_安裝環境.bat`**，等它跑完（第一次要下載約 150MB 的瀏覽器，會比較久）

裝不起來時看下面的「常見問題」。

### 每次使用

#### 投票（主要功能）

先雙擊 **`2_預跑不送出.bat`** 試一次。它會跑完整流程但**不會送出任何票**，
讓你確認程式的每一步都對。確認沒問題之後，才用 **`3_執行投票.bat`**。

流程長這樣：

1. 跳出瀏覽器 → **你自己登入** → 回黑色視窗按 Enter
2. 程式列出你持有的股東會清單，標出哪些還能投票
3. 按 Enter 開始，程式逐檔：點進去 → 按「全部贊成(承認)」→ 按「下一步」
4. 到確認頁時**程式停下來**，請你在瀏覽器按【確認投票結果】
   （這一步程式不能代按，理由見下方）
   按完回黑色視窗按 Enter；`s` 跳過這一檔、`q` 結束全部
5. 程式確認完成頁真的寫著「投票已完成」，截圖歸檔，換下一檔
6. 最後印出「成功 X／失敗 Y／跳過 Z」，失敗的逐條列原因

只想投某幾檔：`3_執行投票.bat --only 1101,2330`

產出：

| 位置 | 內容 |
|---|---|
| `evidence/<日期>/` | 截圖，檔名 `<代號>_<日期>_<時間>_<階段>.png` |
| `logs/results/<日期>.jsonl` | 每檔一筆紀錄：當下看到的議案、我方選擇、截圖路徑 |

#### 偵查頁面結構（平台改版時才需要）

雙擊 **`1_偵查頁面結構.bat`**，登入後點到要分析的頁面，回來按 Enter 抓取，
`q` 結束。產出在 `explore/`，把 `structure.md` 給 Claude 用來更新
`config/selectors.yaml`。

### ⚠️ 這些檔案含個資

`explore/` 裡面會有你的**姓名、身分證字號、持股明細**。
已經設定成不會被上傳到 GitHub，但**請不要自己把它貼到公開的地方**。
要給我分析的時候，優先給 `structure.md`（個資比較少），必要時再遮掉敏感欄位。

### 常見問題

**跑 `0_安裝環境.bat` 出現一大串紅字，最後說 `Microsoft Visual C++ 14.0 or greater is required`**

不用去裝那個 Visual C++。原因是 pip 抓了一個沒有現成安裝檔的套件版本，跑去自己編譯。
已經在 `requirements.txt` 擋掉了，**請先用 `git pull` 更新專案，再跑一次 `0_安裝環境.bat`**。

**視窗跳出一堆 `'xxx' is not recognized as an internal or external command`**

舊版的 `.bat` 在錯誤訊息裡寫了中文，被 Windows 命令列拆錯了。同樣更新專案後就沒事。

**用 Microsoft Store 裝的 Python**

可以動，但 Store 版的檔案路徑被系統改寫過，偶爾會出怪問題。
如果遇到說不上來的錯誤，改裝 [python.org](https://www.python.org/downloads/) 的版本。

---

## 為什麼「確認投票結果」要你自己按？

確認頁掛了 **reCAPTCHA Enterprise（隱形、用分數判斷是不是機器人）**。
程式開的瀏覽器分數過不了，會顯示「機器人驗證失敗」。

要讓程式代按，只能偽裝瀏覽器指紋或接驗證碼代解服務——那是破解平台的安全機制，
**本專案不做**（你的股東帳戶風險是你在扛）。

好消息是這個驗證**只在確認頁**。清單頁、議案頁、完成頁都沒有，所以程式能做掉
其他所有步驟，你只要按一下。而且這樣**反而比全程手動更不容易遇到驗證失敗**：
程式幾秒內把前置步驟做完，你一到確認頁馬上按，驗證 token 是新鮮的。

## 為什麼登入也要你自己做？

集保登入頁掛的是 **reCAPTCHA Enterprise v3**（隱形、用分數判斷是不是機器人），
不是那種「看圖片打字」的驗證碼——**沒有東西可以讓程式代填**。
要讓程式自動登入，只能偽裝瀏覽器指紋或接驗證碼代解服務，那是在破解平台的
安全機制，本專案不做（你的股東帳戶風險也是你在扛）。

反正登入只要做一次，真正花時間的是後面逐檔點 N 次——那段才是程式要幫你做的。

詳細的技術分析與後續規劃在 [`docs/PLAN.md`](docs/PLAN.md)。

---

## 給開發者

```bash
pip install -r requirements.txt
python -m playwright install chromium
PYTHONPATH=src python -m tdcc_vote.explore --help
```

| 檔案 | 做什麼 |
|---|---|
| `config/selectors.yaml` | 網站元素定位表。**平台改版原則上只改這一個檔** |
| `src/tdcc_vote/paths.py` | 時間／檔名工具。⚠️ 時區一律 `Asia/Taipei`，不要自己 `datetime.now()` |
| `src/tdcc_vote/browser.py` | 有頭 + 持久化 profile 的瀏覽器啟動（不做任何指紋偽裝） |
| `src/tdcc_vote/login_gate.py` | 開啟登入頁、判定登入狀態（靠網址是否進入 `/evote/shareholder/`）。**不做阻塞等待** |
| `src/tdcc_vote/explore.py` | 偵查工具 |
| `src/tdcc_vote/meetings.py` | 讀清單頁表格，解析 onclick 取代號／動作／會議日期 |
| `src/tdcc_vote/vote.py` | 單檔投票狀態機（停在確認頁等人按） |
| `src/tdcc_vote/evidence.py` | 截圖命名、結果 jsonl（投票當下就寫，不事後重算） |
| `src/tdcc_vote/run_all.py` | 批次驅動與結尾報告 |
| `tests/test_flow_fixture.py` | 對 fixture 跑完整流程。**不代表真實網站可行** |

跑測試：`PYTHONPATH=src python tests/test_flow_fixture.py`

⛔ **定位鐵律：一律用 `onclick` 裡的函式名，不准用 `name` 或 `class`。**
確認頁「確認投票結果」與「取消投票」的 `name` 都是 `button`；
議案頁「下一步」與「取消投票」的 class 都是 `o-button`。
用 name/class 定位會有機會按到「取消投票」，把使用者填好的票整筆丟掉。

⚠️ **`.bat` 檔內容一律只用 ASCII（連 `REM` 註解也是）**。cmd 解析 .bat 用的是系統
預設編碼，即使先 `chcp 65001`，中文字仍可能被拆成看似指令的片段而報錯（已實際踩過）。
要給人看的中文說明，一律由 Python 程式印出。

環境變數 `TDCC_CHROMIUM_PATH` 可指定 Chromium 執行檔（自訂安裝或 CI 用）。
