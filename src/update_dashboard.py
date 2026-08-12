#!/usr/bin/env python3
"""Fetch Twelve Data daily prices and build ranked Grafana CSV inputs.

Only instruments with an explicit Twelve Data symbol are fetched. Missing symbols
remain visible as pending rows so the dashboard never substitutes invented data.
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "funds.json"
DATA = ROOT / "data"
CATEGORY_DATA = DATA / "categories"


def pct_change(values: list[float], periods: int) -> float | None:
    if len(values) <= periods or values[-periods - 1] == 0:
        return None
    return values[-1] / values[-periods - 1] - 1


def daily_returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1]]


def sharpe(values: list[float], risk_free_rate: float) -> float | None:
    returns = daily_returns(values)
    if len(returns) < 30:
        return None
    volatility = statistics.stdev(returns)
    if volatility == 0:
        return None
    return (statistics.mean(returns) * 252 - risk_free_rate) / (volatility * math.sqrt(252))


def max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def recovery_days(values: list[float]) -> int | None:
    if not values:
        return None
    peak_index = 0
    trough_index = 0
    peak = values[0]
    worst = 0.0
    for i, value in enumerate(values):
        if value > peak:
            peak, peak_index = value, i
        drawdown = value / peak - 1
        if drawdown < worst:
            worst, trough_index = drawdown, i
    target = max(values[: trough_index + 1])
    for i in range(trough_index + 1, len(values)):
        if values[i] >= target:
            return i - trough_index
    return None


def api_json(endpoint: str, api_key: str, **params: str | int) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://api.twelvedata.com/{endpoint}?{query}",
        headers={"Authorization": f"apikey {api_key}", "User-Agent": "grafana-fund-dashboard/1.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if payload.get("status") == "error":
                raise RuntimeError(payload.get("message", "Twelve Data error"))
            return payload
        except (urllib.error.URLError, RuntimeError) as exc:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def fetch_closes(symbol: str, api_key: str) -> list[float]:
    payload = api_json("time_series", api_key, symbol=symbol, interval="1day", outputsize=800)
    rows = payload.get("values", [])
    return [float(row["close"]) for row in reversed(rows) if row.get("close")]


def fmt(value: float | int | None, percent: bool = False) -> str:
    if value is None:
        return ""
    return f"{value * 100:.2f}" if percent else f"{value:.3f}"


def signal(row: dict) -> str:
    metrics = [row.get("excess_return_1y"), row.get("momentum_6m"), row.get("sharpe")]
    if any(value is None for value in metrics):
        return "待資料"
    votes = sum((metrics[0] > 0, metrics[1] > 0, metrics[2] > 0))
    return "買進" if votes == 3 else "觀察" if votes == 2 else "賣出"


def score(row: dict) -> float:
    values = (
        row.get("return_1y") or -9,
        row.get("excess_return_1y") or -9,
        row.get("momentum_6m") or -9,
        (row.get("sharpe") or -9) / 5,
        (row.get("max_drawdown") or -1) / 2,
    )
    return sum(values)


def main() -> int:
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    allow_pending = os.environ.get("ALLOW_PENDING", "0") == "1"
    if not api_key and not allow_pending:
        print("TWELVE_DATA_API_KEY is required", file=sys.stderr)
        return 2

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    categories = {item["id"]: item for item in config["categories"]}
    benchmark_cache: dict[str, list[float]] = {}
    rows: list[dict] = []

    for fund in config["funds"]:
        category = categories[fund["category"]]
        symbol = fund.get("twelve_data_symbol", "").strip()
        row = {**fund, "category_name": category["name"], "benchmark": category["benchmark_symbol"]}
        if symbol and api_key:
            try:
                fund_values = fetch_closes(symbol, api_key)
                benchmark_symbol = category["benchmark_symbol"]
                if benchmark_symbol not in benchmark_cache:
                    benchmark_cache[benchmark_symbol] = fetch_closes(benchmark_symbol, api_key)
                benchmark_values = benchmark_cache[benchmark_symbol]
                length = min(len(fund_values), len(benchmark_values))
                fund_values, benchmark_values = fund_values[-length:], benchmark_values[-length:]
                row.update({
                    "return_1y": pct_change(fund_values, min(252, length - 1)),
                    "benchmark_return_1y": pct_change(benchmark_values, min(252, length - 1)),
                    "momentum_6m": pct_change(fund_values, min(126, length - 1)),
                    "sharpe": sharpe(fund_values[-252:], config["risk_free_rate"]),
                    "max_drawdown": max_drawdown(fund_values),
                    "recovery_days": recovery_days(fund_values),
                    "status": "已更新",
                })
                if row["return_1y"] is not None and row["benchmark_return_1y"] is not None:
                    row["excess_return_1y"] = row["return_1y"] - row["benchmark_return_1y"]
            except Exception as exc:  # keep one bad symbol from blocking every category
                row["status"] = f"API錯誤: {type(exc).__name__}"
        else:
            row["status"] = "待填Twelve Data代碼"
        row["signal"] = signal(row)
        row["score"] = score(row)
        rows.append(row)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    for category_rows in grouped.values():
        category_rows.sort(key=score, reverse=True)
        for rank, row in enumerate(category_rows[:10], 1):
            row["rank"] = rank

    DATA.mkdir(exist_ok=True)
    CATEGORY_DATA.mkdir(parents=True, exist_ok=True)
    fields = ["rank", "category_name", "name", "moneydj_id", "twelve_data_symbol", "benchmark", "return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "sharpe", "max_drawdown", "recovery_days", "signal", "status"]

    def write_csv(path: Path, selected: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in selected:
                output = {key: item.get(key, "") for key in fields}
                for key in ("return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "max_drawdown"):
                    output[key] = fmt(item.get(key), percent=True)
                output["sharpe"] = fmt(item.get("sharpe"))
                writer.writerow(output)

    ranked = [row for key in categories for row in grouped.get(key, [])[:10]]
    write_csv(DATA / "rankings.csv", ranked)
    for category_id in categories:
        write_csv(CATEGORY_DATA / f"{category_id}.csv", grouped.get(category_id, [])[:10])

    metadata = {"updated_at": datetime.now(timezone.utc).isoformat(), "rows": len(ranked), "verified_rows": sum(r.get("status") == "已更新" for r in ranked)}
    (DATA / "status.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    today = date.today()
    if os.environ.get("MONTH_END") == "1" or (today + timedelta(days=1)).month != today.month:
        snapshots = DATA / "monthly"
        snapshots.mkdir(exist_ok=True)
        write_csv(snapshots / f"{today:%Y-%m}.csv", ranked)
    print(json.dumps(metadata, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
