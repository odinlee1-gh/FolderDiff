# FileDiff

比較兩個目錄的差異，並輸出 HTML 報表。

更新日期：2026-11-09

## 內容

- `folderdiff_cli.py`：CLI / GUI 混合版，支援直接指定目錄或用 UI 選擇目錄
- `folderdiff_ui.py`：獨立 UI 版，直接選目錄後會用瀏覽器開啟 HTML 報表
- `requirements.txt`：目前僅需 Python 內建模組，實際上無額外依賴
- `.gitignore`：排除 `.venv/`、`__pycache__/` 與產生的報表（`dir_diff_*.html`、`*.csv`，內含本機路徑）

## 使用方式

### 1) CLI / GUI 混合版

```bash
python folderdiff_cli.py
```

如果未傳入目錄參數，就會開啟資料夾選擇視窗。

也可以直接指定：

```bash
python folderdiff_cli.py "D:\A" "E:\B"
python folderdiff_cli.py "D:\A" "E:\B" --hash
python folderdiff_cli.py "D:\A" "E:\B" --csv diff.csv
python folderdiff_cli.py "D:\A" "E:\B" --ignore .git __pycache__ .DS_Store Thumbs.db
python folderdiff_cli.py "D:\A" "E:\B" --outdir reports
python folderdiff_cli.py "D:\A" "E:\B" --no-html
```

### 2) 獨立 UI 版

```bash
python folderdiff_ui.py
```

開啟視窗後：

1. 在「目錄 A」「目錄 B」按「瀏覽…」選擇資料夾（也可直接貼上路徑，可用「⇅ 交換 A / B」對調）
2. 選擇比對方式：
   - 檔案大小＋修改時間（快速，預設）
   - SHA-256 內容雜湊（準確，檔案多時較慢）
3. 視需要調整「忽略名稱」（以空白分隔）
4. 按「開始比對」或 Enter

比對在背景執行，視窗不會卡住，並顯示進度。完成後視窗會顯示「只在 A／只在 B／不一致」的數量與耗時，並自動用預設瀏覽器開啟 HTML 報表。

其他按鈕：

- 「重新開啟報表」：再次開啟最近一次的報表
- 「開啟報表資料夾」：開啟報表所在資料夾
- 「清除」：清空目錄 A、B 與上次結果

若目錄未選、不存在，或 A、B 為同一資料夾，會跳出提示。

## 功能

- 比較兩個目錄內檔案差異
- 顯示只在 A / 只在 B 的檔案
- 顯示兩邊都存在但內容或時間不同的檔案
- 支援忽略檔名或資料夾名稱
- 可選擇以大小 + 修改時間比較，或以 SHA-256 內容比較
- 可輸出 CSV
- 可輸出 HTML 報表
- HTML 內容會顯示目錄層級、搜尋篩選與差異資訊
- 以 `~` 開頭的暫存檔會自動忽略

### HTML 報表（UI 版）

- 支援淺色／深色模式（跟隨系統設定）
- 點擊上方數量卡片可跳到對應區塊
- 篩選列固定在頂端：按 `/` 開始搜尋、`Esc` 清除；各區塊顯示「符合數 / 總數」
- 檔案大小以 B / KB / MB / GB 顯示，滑鼠移上可看精確 bytes
- 不一致區塊以底色標示較新的修改時間，並以 A / B 標記較新的一方
- SHA-256 模式下無法讀取的檔案會標示為「無法讀取」，不會中斷比對

## 產出

```text
dir_diff_YYYYMMDD_HHMMSS.html      # folderdiff_cli.py：輸出到目前工作目錄（或 --outdir 指定的資料夾）
dir_diff_ui_YYYYMMDD_HHMMSS.html   # folderdiff_ui.py：輸出到程式所在資料夾
```

## 建立 venv

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python folderdiff_ui.py
```

## 注意事項

- 若目錄不存在，程式會直接提示錯誤
- HTML 報表會自動透過預設瀏覽器開啟
- UI 版視窗圖示（原始 logo 補成正方形）以 base64 內嵌在 `folderdiff_ui.py` 的 `ICON_PNGS_B64`（64/48/32/16 px PNG），單一檔案即可執行；要更換圖示，將新的 PNG 轉成 base64 取代該常數即可
- UI 版與 `folderdiff_cli.py` 的報表樣式各自獨立，上述「HTML 報表（UI 版）」功能僅適用於 `folderdiff_ui.py`
- 目前 `requirements.txt` 不含第三方套件，僅為環境說明檔

## 版本更新紀錄（Changelog）

- 目前版本為第一版，尚無更新紀錄。