# TDCC_Auto_Vote — 集保股東會電子投票輔助工具

把「登入後逐檔點議案、投票、截圖、命名歸檔」這段重複工作自動化。

> **現在進度：P0（偵查階段）。還不能投票。**
> 目前只完成一支工具：把登入後的頁面結構抓下來，用來寫真正的投票程式。
> 為什麼要這一步 → 見下方「為什麼不是直接寫好投票」。

---

## 怎麼用（Windows）

### 第一次使用

1. 先裝好 [Python](https://www.python.org/downloads/)（**3.9 以上**，建議 3.12；
   **安裝時要勾「Add python.exe to PATH」**）
2. 雙擊 **`0_安裝環境.bat`**，等它跑完（第一次要下載約 150MB 的瀏覽器，會比較久）

裝不起來時看下面的「常見問題」。

### 每次使用

雙擊 **`1_偵查頁面結構.bat`**，然後：

1. 程式會跳出一個瀏覽器視窗，**你自己在裡面登入**（身分證、密碼，或憑證）
2. 登入好之後，在瀏覽器裡點到你想分析的頁面
   （例如「可投票的股東會清單」、某一檔的「議案頁」）
3. 回到黑色視窗按 **Enter**，它就會把那一頁存下來
4. 重複 2-3 把要分析的頁面都抓一遍
5. 全部抓完，輸入 **q** 再按 Enter 結束

抓下來的東西會放在 `explore/` 資料夾，每一頁一個子資料夾，裡面有：

| 檔案 | 內容 |
|---|---|
| `structure.md` | 這一頁有哪些連結／按鈕／欄位／表格（寫程式要看的就是這份） |
| `page.html` | 頁面原始碼 |
| `screenshot.png` | 整頁截圖 |

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

## 為什麼不是直接寫好投票程式？

因為登入後的頁面**沒登入就看不到**。在沒看過真實頁面之前寫「點哪個按鈕」，
只能用猜的——猜出來的東西會長得很像真的，但跑起來就是找不到元素，
而且錯在哪很難查。所以先抓真實結構，再照著寫。

## 為什麼登入要你自己做？

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
| `src/tdcc_vote/login_gate.py` | 停下來等人工登入，靠網址進入 `/evote/shareholder/` 判定成功 |
| `src/tdcc_vote/explore.py` | 偵查工具 |

⚠️ **`.bat` 檔內容一律只用 ASCII（連 `REM` 註解也是）**。cmd 解析 .bat 用的是系統
預設編碼，即使先 `chcp 65001`，中文字仍可能被拆成看似指令的片段而報錯（已實際踩過）。
要給人看的中文說明，一律由 Python 程式印出。

環境變數 `TDCC_CHROMIUM_PATH` 可指定 Chromium 執行檔（自訂安裝或 CI 用）。
