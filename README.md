# Grafana dashboards

本儲存庫包含全球共同基金策略平台，以及既有的 BitMart 儀表板匯出檔。

## 共同基金 Dashboard

- Grafana 匯入檔：`dashboards/mutual-funds.json`
- 每日排名資料：`data/rankings.csv`
- 分類資料：`data/categories/*.csv`
- 基金與 Benchmark 設定：`config/funds.json`

平台涵蓋台灣、日本、韓國、香港、中國、美國、半導體、光通訊、量子電腦、金融及醫療。排名使用一年報酬、Benchmark 超額報酬、六個月動能、夏普指數與最大回撤，另列回撤恢復天數及研究訊號。

## 安全設定

GitHub Actions Repository Secret 必須命名為 `TWELVE_DATA_API_KEY`。API Key 不得寫入程式碼、Dashboard JSON 或提交紀錄。

## Grafana 匯入

1. 在 Grafana 安裝並新增 [Infinity data source](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)。
2. 匯入 `dashboards/mutual-funds.json`。
3. 在匯入畫面選擇剛建立的 Infinity data source。

資料為每日淨值型資料，不代表盤中即時價格。訊號僅供研究參考，不構成投資建議。
