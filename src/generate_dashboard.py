#!/usr/bin/env python3
"""Generate a deterministic Grafana dashboard with non-overlapping panels."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "funds.json").read_text(encoding="utf-8"))
BASE = "https://raw.githubusercontent.com/eva5389-pixel/grafana-dashboard/main/data/categories"


def table_panel(category: dict, index: int) -> dict:
    return {
        "id": index + 2,
        "title": f"{category['name']}｜基金 Top 10",
        "type": "table",
        "gridPos": {"x": (index % 2) * 12, "y": 5 + (index // 2) * 9, "w": 12, "h": 9},
        "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "${datasource}"},
        "targets": [{"refId": "A", "type": "csv", "source": "url", "url": f"{BASE}/{category['id']}.csv", "format": "table", "parser": "backend"}],
        "fieldConfig": {
            "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
            "overrides": [
                {"matcher": {"id": "byName", "options": "signal"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}, {"id": "mappings", "value": [{"type": "value", "options": {"買進": {"color": "green", "text": "買進"}, "觀察": {"color": "yellow", "text": "觀察"}, "賣出": {"color": "red", "text": "賣出"}, "待資料": {"color": "gray", "text": "待資料"}}}]}]},
                {"matcher": {"id": "byName", "options": "status"}, "properties": [{"id": "custom.width", "value": 150}]},
                {"matcher": {"id": "byName", "options": "name"}, "properties": [{"id": "custom.width", "value": 260}]}
            ]
        },
        "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    }


panels = [{
    "id": 1,
    "type": "text",
    "title": "全球共同基金策略平台",
    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 5},
    "options": {"mode": "markdown", "content": "# 全球共同基金策略平台\n每日 20:00 更新資料；月底 20:00 固定排名快照。\n\n評分依據：一年報酬、Benchmark 超額報酬、六個月動能、夏普指數、最大回撤。訊號僅供研究參考，不構成投資建議。"}
}]
panels.extend(table_panel(category, index) for index, category in enumerate(CONFIG["categories"]))

dashboard = {
    "annotations": {"list": []}, "editable": True, "fiscalYearStartMonth": 0,
    "graphTooltip": 1, "links": [], "panels": panels, "refresh": "1d",
    "schemaVersion": 40, "tags": ["funds", "twelve-data", "benchmark"],
    "templating": {"list": [{"name": "datasource", "label": "Infinity 資料源", "type": "datasource", "query": "yesoreyeram-infinity-datasource", "current": {}}]},
    "time": {"from": "now-1y", "to": "now"}, "timezone": "browser",
    "title": "全球共同基金策略平台", "uid": "global-mutual-fund-ranking", "version": 1
}

destination = ROOT / "dashboards" / "mutual-funds.json"
destination.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(destination)
