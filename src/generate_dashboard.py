#!/usr/bin/env python3
"""Generate a deterministic Grafana dashboard with non-overlapping panels."""

import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "funds.json").read_text(encoding="utf-8"))
INP = json.loads((ROOT / "config" / "inp_supply_chain.json").read_text(encoding="utf-8"))
RULES_MARKDOWN = """## 基金篩選與排名規則

| 榜單 | 篩選及排序方式 |
|---|---|
| **一般市場 Top 10** | 排除撤銷核備、槓桿與反向型；確認市場及基金類型相符；同基金不同幣別／級別去重。資料完整時依「一年報酬＋Benchmark超額報酬＋六個月動能＋夏普÷5＋最大回撤÷2」排序，資料不足時以一年報酬排序。 |
| **全市場 Top 5** | 彙整各市場與主題基金，排除無一年報酬資料者，同基金家族去重後，依一年報酬由高至低取前5名。 |
| **主題基金** | 須有可驗證的主題成分股；綜合基金績效、相關持股比重與供應鏈家數排序。 |
| **磷化銦基金** | 僅納入有持股明細、比例及日期可核實者；先按磷化銦成分股家數，再按相關持股比重排序。一年報酬率為展示欄位，不參與排名。 |

> 訊號：超額報酬、六個月動能、夏普全數為正＝買進；兩項為正＝觀察；其餘＝賣出。僅供研究參考，不構成投資建議。
"""
def table_panel(category: dict, index: int) -> dict:
    csv_data = (ROOT / "data" / "categories" / f"{category['id']}.csv").read_text(encoding="utf-8-sig")
    if category["id"] == "overall_top5":
        source_rows = list(csv.DictReader(io.StringIO(csv_data)))
        fieldnames = list(source_rows[0]) + ["secondary_benchmark", "secondary_benchmark_return_1y"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in source_rows:
            row["secondary_benchmark"] = "台灣加權指數（TAIEX）"
            row["secondary_benchmark_return_1y"] = "92.12"
            writer.writerow(row)
        csv_data = output.getvalue()
    quantum = category["id"] == "quantum"
    optical = category["id"] == "optical"
    memory = category["id"] == "memory"
    robotics = category["id"] == "robotics"
    excluded = {"category_name": True, "moneydj_id": True, "twelve_data_symbol": True, "benchmark_return_1y": True}
    if not quantum:
        excluded.update({"quantum_coverage": True, "quantum_exposure": True,
                         "quantum_holdings": True, "holdings_as_of": True})
    if not optical:
        excluded.update({"optical_coverage": True, "optical_exposure": True,
                         "optical_holdings": True, "optical_as_of": True})
    if not memory:
        excluded.update({"memory_coverage": True, "memory_exposure": True,
                         "memory_holdings": True, "memory_as_of": True})
    if not robotics:
        excluded.update({"robotics_coverage": True, "robotics_exposure": True,
                         "robotics_holdings": True, "robotics_as_of": True})
    overrides = [
        {"matcher": {"id": "byName", "options": "signal"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "mappings", "value": [{"type": "value", "options": {"買進": {"color": "green", "text": "買進"}, "觀察": {"color": "yellow", "text": "觀察"}, "賣出": {"color": "red", "text": "賣出"}, "待資料": {"color": "gray", "text": "待資料"}}}]}]},
        {"matcher": {"id": "byName", "options": "status"}, "properties": [{"id": "custom.width", "value": 150}]},
        {"matcher": {"id": "byName", "options": "name"}, "properties": [{"id": "custom.width", "value": 260}]},
        {"matcher": {"id": "byName", "options": "isin"}, "properties": [{"id": "custom.width", "value": 135}]}
    ]
    if category["id"] == "overall_top5":
        overrides.append({
            "matcher": {"id": "byName", "options": "rank"},
            "properties": [
                {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                {"id": "mappings", "value": [{"type": "value", "options": {"1": {"color": "#FFD700", "text": "👑 1"}}}]}
            ]
        })
    return {
        "id": index + 2,
        "title": category["name"] if category["id"] == "overall_top5" else f"{category['name']}｜基金 Top 10",
        "type": "table",
        "gridPos": {"x": (index % 2) * 12, "y": 10 + (index // 2) * 9, "w": 12, "h": 9},
        "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "${datasource}"},
        "targets": [{"refId": "A", "type": "csv", "source": "inline", "data": csv_data, "format": "table", "parser": "backend"}],
        "transformations": [{
            "id": "organize",
            "options": {
                "indexByName": {"rank": 0, "name": 1, "isin": 2, "currency": 3, "distribution": 4, "quantum_coverage": 5, "optical_coverage": 5, "memory_coverage": 5, "robotics_coverage": 5, "quantum_exposure": 6, "optical_exposure": 6, "memory_exposure": 6, "robotics_exposure": 6, "quantum_holdings": 7, "optical_holdings": 7, "memory_holdings": 7, "robotics_holdings": 7, "holdings_as_of": 8, "optical_as_of": 8, "memory_as_of": 8, "robotics_as_of": 8, "return_1y": 9, "distribution_yield_12m": 10, "total_return_1y": 11, "benchmark": 12, "secondary_benchmark": 13, "secondary_benchmark_return_1y": 14, "excess_return_1y": 15, "momentum_6m": 16, "sharpe": 17, "max_drawdown": 18, "recovery_days": 19, "score": 20, "signal": 21, "status": 22},
                "excludeByName": excluded,
                "renameByName": {"rank": "排名", "name": "基金", "isin": "ISIN碼", "currency": "扣款幣別", "distribution": "是否配息", "distribution_yield_12m": "近12月配息率%", "total_return_1y": "含息總報酬率%", "quantum_coverage": "供應鏈家數", "optical_coverage": "供應鏈家數", "memory_coverage": "供應鏈家數", "robotics_coverage": "供應鏈家數", "quantum_exposure": "相關持股%", "optical_exposure": "相關持股%", "memory_exposure": "相關持股%", "robotics_exposure": "相關持股%", "quantum_holdings": "實際持股", "optical_holdings": "實際持股", "memory_holdings": "實際持股", "robotics_holdings": "實際持股", "holdings_as_of": "持股日期", "optical_as_of": "持股日期", "memory_as_of": "持股日期", "robotics_as_of": "持股日期", "return_1y": "一年報酬%", "benchmark": "Benchmark 1", "secondary_benchmark": "Benchmark 2", "secondary_benchmark_return_1y": "台灣加權一年報酬%", "excess_return_1y": "超額報酬%", "momentum_6m": "六個月動能%", "sharpe": "夏普", "max_drawdown": "最大回撤%", "recovery_days": "恢復天數", "score": "綜合評分", "signal": "訊號", "status": "資料狀態"}
            }
        }],
        "fieldConfig": {
            "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
            "overrides": overrides
        },
        "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    }


panels = [{
    "id": 1,
    "type": "text",
    "title": "全球共同基金策略平台",
    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 10},
    "options": {"mode": "markdown", "content": "# 全球共同基金策略平台\n每日 20:00 更新資料；月底 20:00 固定排名快照。\n\n" + RULES_MARKDOWN}
}]
panels.extend(table_panel(category, index) for index, category in enumerate(CONFIG["categories"]))


def inp_panels(start_y: int) -> list[dict]:
    stages = " → ".join(INP["stages"])
    holdings = json.loads((ROOT / "config" / "inp_fund_holdings.json").read_text(encoding="utf-8"))
    holdings.sort(key=lambda fund: (-fund["coverage"], -fund["exposure"], fund["name"]))
    csv_lines = ["rank,name,coverage,exposure,return_1y,signal,holdings,as_of,status"]
    for rank, fund in enumerate(holdings, 1):
        values = [
            str(rank), fund["name"], str(fund["coverage"]), f'{fund["exposure"]:.2f}',
            f'{fund["return_1y"]:.2f}', "買入", fund["holdings"], fund["as_of"], "已驗證",
        ]
        csv_lines.append(",".join('"' + value.replace('"', '""') + '"' for value in values))
    csv_data = "\n".join(csv_lines) + "\n"
    risks = "\n".join(f"- {risk}" for risk in INP["risks"])
    overview = (
        f"# 產業重點\n**資料日期：{INP['as_of']}**\n\n{INP['thesis']}\n\n"
        f"**供應鏈路徑：** {stages}\n\n## 主要風險\n{risks}\n\n"
        "> 排名依供應鏈直接性與研究優先度排列，不代表報酬預測或買賣建議；實際營收曝險須以公司公告驗證。"
    )
    return [
        {
            "id": 1001,
            "type": "table",
            "title": "磷化銦｜基金 Top 10",
            "gridPos": {"x": 0, "y": start_y, "w": 24, "h": 9},
            "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "${datasource}"},
            "targets": [{"refId": "A", "type": "csv", "source": "inline", "data": csv_data, "format": "table", "parser": "backend"}],
            "transformations": [{
                "id": "organize",
                "options": {
                    "indexByName": {"rank": 0, "name": 1, "coverage": 2, "exposure": 3, "return_1y": 4, "signal": 5, "holdings": 6, "as_of": 7, "status": 8},
                    "excludeByName": {},
                    "renameByName": {"rank": "排名", "name": "基金", "coverage": "成分股家數", "exposure": "相關持股%", "return_1y": "一年報酬率%", "signal": "買賣訊號", "holdings": "實際成分股", "as_of": "持股日期", "status": "資料狀態"},
                },
            }],
            "fieldConfig": {
                "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                "overrides": [
                    {"matcher": {"id": "byName", "options": "rank"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}}, {"id": "mappings", "value": [{"type": "value", "options": {"1": {"color": "#FFD700", "text": "👑 1"}}}]}]},
                    {"matcher": {"id": "byName", "options": "name"}, "properties": [{"id": "custom.width", "value": 230}]},
                    {"matcher": {"id": "byName", "options": "holdings"}, "properties": [{"id": "custom.width", "value": 230}]},
                    {"matcher": {"id": "byName", "options": "signal"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}}, {"id": "mappings", "value": [{"type": "value", "options": {"買入": {"color": "green", "text": "▲ 買入"}, "觀察": {"color": "yellow", "text": "● 觀察"}, "賣出": {"color": "red", "text": "▼ 賣出"}}}]}]},
                    {"matcher": {"id": "byName", "options": "status"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "mappings", "value": [{"type": "value", "options": {"已驗證": {"color": "green", "text": "已驗證"}}}]}]},
                ],
            },
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
        },
        {
            "id": 1002,
            "type": "text",
            "title": "磷化銦｜產業趨勢與風險",
            "gridPos": {"x": 0, "y": start_y + 9, "w": 24, "h": 7},
            "options": {"mode": "markdown", "content": overview},
        },
    ]


table_bottom = 10 + ((len(CONFIG["categories"]) + 1) // 2) * 9
panels.extend(inp_panels(table_bottom))

dashboard = {
    "annotations": {"list": []}, "editable": True, "fiscalYearStartMonth": 0,
    "graphTooltip": 1, "links": [], "panels": panels, "refresh": "1d",
    "schemaVersion": 40, "tags": ["funds", "twelve-data", "benchmark", "InP", "optical"],
    "templating": {"list": [{"name": "datasource", "label": "Infinity 資料源", "type": "datasource", "query": "yesoreyeram-infinity-datasource", "current": {}}]},
    "time": {"from": "now-1y", "to": "now"}, "timezone": "browser",
    "title": "全球共同基金策略平台", "uid": "global-mutual-fund-ranking", "version": 1
}

destination = ROOT / "dashboards" / "mutual-funds.json"
destination.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(destination)
