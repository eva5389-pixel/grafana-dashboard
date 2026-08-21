#!/usr/bin/env python3
"""Generate a standalone market benchmark valuation/risk dashboard."""

import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "dashboards" / "market-benchmarks.json"

MARKETS = [
    ("台灣", "EWT", "-33.20"),
    ("日本", "EWJ", "29.10"),
    ("韓國", "EWY", "-28.62"),
    ("香港", "EWH", "12.33"),
    ("中國", "MCHI", ""),
    ("美國", "SPY", "22.52"),
    ("印度", "INDA", ""),
    ("東協", "ASEA", ""),
    ("歐洲", "VGK", ""),
    ("巴西", "EWZ", ""),
]


def csv_data() -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["market", "benchmark", "return_1y", "pe_ratio", "volatility_1y", "risk_level", "status"])
    for market, benchmark, annual_return in MARKETS:
        writer.writerow([
            market,
            benchmark,
            annual_return or "待串接",
            "待串接",
            "待串接",
            "待資料",
            "報酬率沿用既有資料" if annual_return else "等待市場指數資料源",
        ])
    return buffer.getvalue()


def main() -> int:
    dashboard = {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            {
                "id": 1,
                "type": "text",
                "title": "市場 Benchmark 評價與風險說明",
                "gridPos": {"h": 5, "w": 24, "x": 0, "y": 0},
                "options": {
                    "mode": "markdown",
                    "content": (
                        "## 各市場 Benchmark 評價與風險模板\n"
                        "- **一年報酬率**：近一年含息價格報酬。\n"
                        "- **本益比**：Benchmark 追蹤指數或 ETF 投資組合本益比。\n"
                        "- **年化標準差**：以近一年日報酬率計算，乘以 √252 年化。\n"
                        "- **風險分級**：低風險 `<15%`；中風險 `15%–25%`；高風險 `>25%`。\n\n"
                        "> 「待串接」代表尚未取得同一基準日、同一口徑的可靠資料，不以基金指標代替。"
                    ),
                },
            },
            {
                "id": 2,
                "type": "table",
                "title": "全球市場 Benchmark｜報酬、估值與風險",
                "gridPos": {"h": 16, "w": 24, "x": 0, "y": 5},
                "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "${datasource}"},
                "targets": [{
                    "refId": "A",
                    "type": "csv",
                    "source": "inline",
                    "format": "table",
                    "data": csv_data(),
                    "parser": "backend",
                }],
                "transformations": [{
                    "id": "organize",
                    "options": {
                        "indexByName": {
                            "market": 0, "benchmark": 1, "return_1y": 2, "pe_ratio": 3,
                            "volatility_1y": 4, "risk_level": 5, "status": 6,
                        },
                        "renameByName": {
                            "market": "市場", "benchmark": "Benchmark", "return_1y": "一年報酬率%",
                            "pe_ratio": "本益比(倍)", "volatility_1y": "年化標準差%",
                            "risk_level": "風險分級", "status": "資料狀態",
                        },
                    },
                }],
                "fieldConfig": {
                    "defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "市場"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
                        {"matcher": {"id": "byName", "options": "風險分級"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}}]},
                    ],
                },
                "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
            },
        ],
        "refresh": "1d",
        "schemaVersion": 41,
        "tags": ["基金", "Benchmark", "風險", "本益比"],
        "templating": {"list": [{
            "name": "datasource", "label": "Infinity 資料源", "type": "datasource",
            "query": "yesoreyeram-infinity-datasource", "current": {}, "refresh": 1,
        }]},
        "time": {"from": "now-1y", "to": "now"},
        "timezone": "browser",
        "title": "全球市場 Benchmark｜報酬估值風險",
        "uid": "global-market-benchmark-risk",
        "version": 1,
    }
    DESTINATION.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(DESTINATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
