#!/usr/bin/env python3
"""Build dashboard rankings from the verified XLSM snapshot export."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from update_dashboard import (
    CATEGORY_DATA, CONFIG, DATA, fetch_local_nav, fmt, max_drawdown,
    pct_change, recovery_days, sharpe, signal,
)


BENCHMARK_KEYWORDS = {
    "taiwan": "EWT.US", "japan": "EWJ.US", "korea": "EWY.US",
    "hong_kong": "EWH.US", "usa": "SPY.US", "finance": "XLF.US",
    "healthcare": "IBB.US",
}


def eligible(item: dict[str, str]) -> bool:
    """Reject rows that the source workbook mapped to the wrong market bucket."""
    category, region = item.get("category", ""), item.get("region", "")
    expected_region = {
        "taiwan": {"台灣"}, "japan": {"日本"}, "korea": {"韓國"},
        "hong_kong": {"香港"}, "china": {"中國", "大中華"}, "usa": {"美國"},
    }
    if category in expected_region and region not in expected_region[category]:
        return False
    if category in expected_region:
        return item.get("target", "") in {"股票型", "中小型股", "REIT", "資訊科技股", "必需性消費股", "公共事業股"}
    return True


def family_key(name: str) -> str:
    """Collapse currency/share-class variants without merging different strategies."""
    value = re.sub(r"（[^）]*）|\([^)]*\)", "", name)
    value = re.sub(r"基金之配息來源.*$|本基金之配息來源.*$", "", value)
    if "基金" in value:
        value = value[: value.rfind("基金") + 2]
    value = re.sub(r"[-－/]?(?:A|B|C|D|E|F|I|N|R|S|T|X|Y|Z|AM|AT|IT|I2|A2|T2|T3)?(?:類?股|級別)?(?:美元|歐元|日圓|日元|台幣|人民幣|澳幣|南非幣|新幣|英鎊|加幣|紐幣)?(?:避險|累積|配息|月配|年配|穩定月收|固定月配)*型?$", "", value, flags=re.I)
    return re.sub(r"[\s　\-－_/]", "", value).lower()


def number(value: str) -> float | None:
    try:
        return float(value) / 100
    except (TypeError, ValueError):
        return None


def main() -> int:
    source = DATA / "workbook_funds.csv"
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    categories = {item["id"]: item for item in config["categories"]}
    raw = list(csv.DictReader(source.open(encoding="utf-8-sig")))
    benchmarks = {}
    for row in raw:
        keyword = BENCHMARK_KEYWORDS.get(row["category"])
        if row.get("target") == "市場指數" and keyword and keyword.lower() in row.get("name", "").lower():
            benchmarks[row["category"]] = number(row.get("return_1y"))
    grouped = defaultdict(list)
    for item in raw:
        category = item["category"]
        if category not in categories or item.get("target") == "市場指數" or not eligible(item):
            continue
        return_1y = number(item.get("return_1y"))
        momentum = number(item.get("momentum_6m"))
        try:
            sharpe_value = float(item["sharpe"])
        except (TypeError, ValueError):
            sharpe_value = None
        benchmark_return = benchmarks.get(category)
        row = {
            "category": category, "category_name": categories[category]["name"],
            "name": item["name"], "moneydj_id": item.get("fund_code", ""),
            "twelve_data_symbol": "", "benchmark": categories[category]["benchmark_symbol"],
            "return_1y": return_1y, "benchmark_return_1y": benchmark_return,
            "excess_return_1y": return_1y - benchmark_return if return_1y is not None and benchmark_return is not None else None,
            "momentum_6m": momentum, "sharpe": sharpe_value, "max_drawdown": None,
            "recovery_days": None, "score": None,
            "status": f"已驗證（活動績效表 {item.get('as_of_date','')}；回撤/恢復期資料不足）",
        }
        if all(row.get(key) is not None for key in ("return_1y", "excess_return_1y", "momentum_6m", "sharpe")):
            row["score"] = (row["return_1y"] + row["excess_return_1y"]
                            + row["momentum_6m"] + row["sharpe"] / 5)
        row["signal"] = signal(row)
        grouped[category].append(row)
    for fund in config["funds"]:
        local_file = fund.get("local_nav_file", "").strip()
        if not local_file:
            continue
        values = fetch_local_nav(local_file)
        category = fund["category"]
        local_row = {
            "category": category, "category_name": categories[category]["name"],
            "name": fund["name"], "moneydj_id": fund.get("yahoo_fund_id", ""),
            "twelve_data_symbol": fund.get("twelve_data_symbol", ""),
            "benchmark": categories[category]["benchmark_symbol"],
            "return_1y": pct_change(values, min(252, len(values) - 1)),
            "benchmark_return_1y": None, "excess_return_1y": None,
            "momentum_6m": pct_change(values, min(126, len(values) - 1)),
            "sharpe": sharpe(values[-252:], config["risk_free_rate"]),
            "max_drawdown": max_drawdown(values), "recovery_days": recovery_days(values),
            "score": None, "signal": "待資料",
            "status": "已更新（Yahoo台灣下載；Benchmark資料不足）",
        }
        match = next((row for row in grouped[category]
                      if family_key(row["name"]) == family_key(fund["name"])), None)
        if match is None:
            grouped[category].append(local_row)
            continue
        match.update({key: local_row[key] for key in (
            "moneydj_id", "return_1y", "momentum_6m", "sharpe",
            "max_drawdown", "recovery_days",
        )})
        if match.get("benchmark_return_1y") is not None:
            match["excess_return_1y"] = match["return_1y"] - match["benchmark_return_1y"]
        if all(match.get(key) is not None for key in (
                "return_1y", "excess_return_1y", "momentum_6m", "sharpe")):
            match["score"] = (match["return_1y"] + match["excess_return_1y"]
                              + match["momentum_6m"] + match["sharpe"] / 5
                              + match["max_drawdown"] / 2)
        match["signal"] = signal(match)
        match["status"] = "已更新（Yahoo台灣下載 + 活動績效表 Benchmark）"
    fields = ["rank", "category_name", "name", "moneydj_id", "twelve_data_symbol", "benchmark",
              "return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "sharpe",
              "max_drawdown", "recovery_days", "score", "signal", "status"]
    ranked = []
    CATEGORY_DATA.mkdir(parents=True, exist_ok=True)
    for category, meta in categories.items():
        rows = grouped.get(category, [])
        rows.sort(key=lambda r: (r["score"] is not None, r["score"] or -999), reverse=True)
        deduped, seen = [], set()
        for row in rows:
            key = family_key(row["name"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        rows = deduped
        if not rows:
            rows = [{"category_name": meta["name"], "name": "此來源目前無可驗證基金", "benchmark": meta["benchmark_symbol"],
                     "signal": "待資料", "status": "活動績效表無對應資料"}]
        output = []
        for rank, row in enumerate(rows[:10], 1):
            formatted = {key: row.get(key, "") for key in fields}
            formatted["rank"] = rank
            for key in ("return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "max_drawdown"):
                formatted[key] = fmt(row.get(key), percent=True)
            formatted["sharpe"] = fmt(row.get("sharpe"))
            formatted["score"] = fmt(row.get("score"))
            output.append(formatted)
        ranked.extend(output)
        with (CATEGORY_DATA / f"{category}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader(); writer.writerows(output)
    with (DATA / "rankings.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(ranked)
    verified = sum(str(row.get("status", "")).startswith(("已驗證", "已更新")) for row in ranked)
    (DATA / "status.json").write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(), "rows": len(ranked),
        "verified_rows": verified, "source_rows": len(raw),
        "source": "1150806Fund Performance活動更新版.xlsm",
        "limitations": "活動績效表為快照；無逐日序列的基金最大回撤與恢復期留空",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(ranked)} dashboard rows; {verified} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
