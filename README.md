# Grafana dashboards

本儲存庫包含全球共同基金策略平台，以及既有的 BitMart 儀表板匯出檔。

## 共同基金 Dashboard

- Grafana 匯入檔：`dashboards/mutual-funds.json`
- 每日排名資料：`data/rankings.csv`
- 分類資料：`data/categories/*.csv`
- 基金與 Benchmark 設定：`config/funds.json`

平台涵蓋台灣、日本、韓國、香港、中國、美國、半導體、光通訊、量子電腦、金融及醫療。排名使用一年報酬、Benchmark 超額報酬、六個月動能、夏普指數與最大回撤，另列回撤恢復天數及研究訊號。

## 資料來源原則

- 基富通公開基金總覽用於核對基金名稱、分類及網站公布的績效；其頁面標示基金資料來自 Morningstar。
- Twelve Data 優先用於設定檔中有明確代碼的市場價格與 Benchmark 歷史序列；失敗時以 Apify/Yahoo Finance 備援。
- 設定 `morningstar_id` 的基金可透過 MIT 授權的 MStarpy 取得 Morningstar 公開淨值；此來源為選用功能，失敗時安全降級。
- Sharpe 與最大回撤以 Apache-2.0 授權的 QuantStats 交叉計算；套件不可用時使用本專案內建公式。
- 網站未提供的歷史資料不推測、不補值；儀表板會顯示「待資料」。
- 不使用基富通登入帳戶資料，也不以未公開介面繞過網站限制。

## 安全設定

GitHub Actions Repository Secrets 使用 `TWELVE_DATA_API_KEY` 與 `APIFY_API_TOKEN`。兩者至少設定一個；任何 Token 都不得寫入程式碼、Dashboard JSON 或提交紀錄。

## Grafana 匯入

1. 在 Grafana 安裝並新增 [Infinity data source](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)。
2. 匯入 `dashboards/mutual-funds.json`。
3. 在匯入畫面選擇剛建立的 Infinity data source。

資料為每日淨值型資料，不代表盤中即時價格。訊號僅供研究參考，不構成投資建議。

## 開源元件

- MStarpy（MIT）：基金搜尋與公開淨值介接。
- QuantStats（Apache-2.0）：報酬序列風險指標。
- 本專案不複製第三方資料庫；僅在更新時呼叫已設定的資料來源。
