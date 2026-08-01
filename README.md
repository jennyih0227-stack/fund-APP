# 誠毅淨值日報 PWA

熊誠毅｜誠毅傳承 每日基金淨值 App。手機可加到主畫面、離線可看最後一次資料，淨值由 GitHub Actions 每日自動抓取更新。

## 架構

```
GitHub Actions（每日排程）
   └─ scripts/fetch_nav.py  抓凱基 MoneyDJ + Yahoo + TWSE
        └─ 產生 data.json，commit 回 repo
             └─ GitHub Pages 提供 index.html + data.json
                  └─ PWA 前端讀 data.json（同源，無 CORS）
```

前端純靜態，不需要伺服器；爬蟲只在 GitHub 雲端排程時執行。

## 檔案結構

| 檔案 | 用途 |
|------|------|
| `index.html` | PWA 主頁（前端全部邏輯） |
| `data.json` | 淨值資料（Actions 自動覆蓋，首次為範例） |
| `funds_config.json` | 基金清單設定（沿用原 LINE Bot 格式） |
| `manifest.webmanifest` | PWA 設定（App 名稱、圖示） |
| `sw.js` | Service Worker（快取、離線） |
| `icons/` | App 圖示 |
| `scripts/fetch_nav.py` | 抓值腳本（Actions 執行） |
| `.github/workflows/update-nav.yml` | 每日排程 |

## 部署步驟（GitHub 網頁操作，不用指令）

1. **建立 repo**：到 GitHub 建一個新 repo，例如 `fund`（可設 Public）。
2. **上傳檔案**：把本資料夾所有內容拖曳上傳（含 `.github` 資料夾與 `scripts`、`icons`）。
   - ⚠️ GitHub 網頁拖曳有時會漏掉 `.github` 這種點開頭資料夾；若漏了，可個別建立 `.github/workflows/update-nav.yml`。
3. **開啟 Pages**：repo → Settings → Pages → Source 選 `Deploy from a branch` → 分支 `main`、資料夾 `/ (root)` → Save。
4. **開啟 Actions 寫入權限**：repo → Settings → Actions → General → 最下方 Workflow permissions → 選 `Read and write permissions` → Save。（讓排程能 commit `data.json`）
5. **首次手動抓值**：repo → Actions → 左側「更新基金淨值」→ 右側 `Run workflow` → 綠色按鈕。跑完後 `data.json` 會被更新成真實淨值。
6. **打開 App**：網址為 `https://<你的帳號>.github.io/fund/`
   - iPhone Safari 開啟 → 分享鈕 → 加入主畫面。

## 自動更新時間

`.github/workflows/update-nav.yml` 內已設兩個排程（台灣時間）：
- 週一至週五 **15:30**（台股收盤後）
- 週一至週五 **22:00**（美股與基金淨值到齊）

要改時間，編輯該檔的 `cron`（用 UTC，台灣 = UTC+8）。

## 新增／修改基金

編輯 `funds_config.json`，格式與原 LINE Bot 相同：

```json
"fund": {
  "基金名稱": { "fund_id": "TFxx", "url": "https://kgilife.moneydj.com/...", "type": "fund" }
}
```

分類：`etf`（台股/指數）、`us_etf`（美股）、`fund`（全委）、`investment_fund`（投資型保單）、`exchange_rate`（匯率）。改完 commit，下次排程即生效，或手動 Run workflow。

## 更新 App 內容後

若改了 `index.html` 或 `sw.js`，請把 `sw.js` 最上方的 `VERSION = 'v1'` 改成 `'v2'`（以此類推），使已安裝的 App 更新快取。

## 注意

- 資料每日更新，僅供參考，不構成投資建議。
- 凱基 MoneyDJ 偶爾改網址或格式，若某檔顯示「—」代表當次抓取失敗，多為來源端問題，隔日排程會再試。
