#!/usr/bin/env python3
"""Build ranked Grafana CSV inputs from interchangeable fund-data providers.

Only instruments with an explicit Twelve Data symbol are fetched. Missing symbols
remain visible as pending rows so the dashboard never substitutes invented data.
"""

from __future__ import annotations

import csv
import importlib
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
NAV_DATA = DATA / "nav"


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


def fetch_local_nav(filename: str) -> list[float]:
    """Read a normalized user-downloaded NAV series from data/nav."""
    path = NAV_DATA / filename
    values = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("nav") not in (None, ""):
                values.append(float(row["nav"]))
    if len(values) < 2:
        raise RuntimeError(f"No usable local NAV history: {filename}")
    return values


def fetch_apify_closes(symbol: str, token: str) -> list[float]:
    """Fetch one year of daily Yahoo Finance history through Apify."""
    endpoint = "https://api.apify.com/v2/acts/canadesk~yahoo-finance/run-sync-get-dataset-items"
    request = urllib.request.Request(
        f"{endpoint}?{urllib.parse.urlencode({'token': token})}",
        data=json.dumps({
            "tickers": [symbol],
            "period": "1y",
            "interval": "1d",
            "process": "gh",
            "storecsv": "no",
            "proxy": {"useApifyProxy": True},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "grafana-fund-dashboard/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)
    records = payload if isinstance(payload, list) else [payload]
    points = next((item.get("data", []) for item in records if item.get("ticker") == symbol), [])
    dated = sorted(
        ((point.get("Date") or point.get("date"), point.get("close")) for point in points),
        key=lambda item: item[0] or "",
    )
    values = [float(close) for _, close in dated if close not in (None, "")]
    if len(values) < 2:
        raise RuntimeError(f"No usable Apify history for {symbol}")
    return values


def fetch_market_closes(symbol: str, twelve_key: str, apify_token: str) -> tuple[list[float], str]:
    errors = []
    if twelve_key:
        try:
            return fetch_closes(symbol, twelve_key), "Twelve Data"
        except Exception as exc:
            errors.append(f"Twelve Data: {type(exc).__name__}")
    if apify_token:
        try:
            return fetch_apify_closes(symbol, apify_token), "Apify/Yahoo"
        except Exception as exc:
            errors.append(f"Apify: {type(exc).__name__}")
    raise RuntimeError("; ".join(errors) or "No market-data credential")


def yahoo_symbol_candidates(identifier: str) -> list[str]:
    """Return stable Yahoo fund symbol variants without duplicate requests."""
    value = identifier.strip()
    if not value:
        return []
    candidates = [value]
    if value.upper().endswith(":FO"):
        candidates.append(value[:-3])
    return list(dict.fromkeys(candidates))


def fetch_yahoo_fund_closes(identifier: str, apify_token: str) -> tuple[list[float], str]:
    """Try Yahoo Taiwan's fund id and its bare Morningstar id via Apify."""
    errors = []
    for candidate in yahoo_symbol_candidates(identifier):
        try:
            return fetch_apify_closes(candidate, apify_token), f"Apify/Yahoo {candidate}"
        except Exception as exc:
            errors.append(f"{candidate}: {type(exc).__name__}")
    raise RuntimeError("; ".join(errors) or "No Yahoo fund id")


def fetch_mstarpy_nav(identifier: str, session=None) -> tuple[list[float], object]:
    """Return Morningstar NAV history through optional MIT-licensed mstarpy.

    The provider is opt-in because current mstarpy versions launch Chrome.  A
    caller-owned session is returned and reused to avoid one browser per fund.
    """
    module = importlib.import_module("mstarpy")
    session = session or module.MorningstarSession()
    fund = module.Funds(identifier, session=session)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=800)
    points = fund.nav(start, end) or []
    dated = sorted(
        ((point.get("date"), point.get("nav")) for point in points),
        key=lambda item: item[0] or "",
    )
    values = [float(nav) for _, nav in dated if nav not in (None, "")]
    if len(values) < 2:
        raise RuntimeError(f"No usable Morningstar NAV for {identifier}")
    return values, session


def quantstats_metrics(values: list[float], risk_free_rate: float) -> dict[str, float | None]:
    """Optionally cross-check Sharpe and drawdown with Apache-2 QuantStats."""
    try:
        qs = importlib.import_module("quantstats")
        pd = importlib.import_module("pandas")
    except ImportError:
        return {}
    series = pd.Series(daily_returns(values))
    result = {
        "sharpe": float(qs.stats.sharpe(series, rf=risk_free_rate, periods=252)),
        "max_drawdown": float(qs.stats.max_drawdown(series)),
    }
    return {key: value for key, value in result.items() if math.isfinite(value)}


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


def score(row: dict) -> float | None:
    """Composite score is published only when every required metric exists."""
    required = ("return_1y", "excess_return_1y", "momentum_6m", "sharpe", "max_drawdown")
    if any(row.get(key) is None for key in required):
        return None
    return (float(row["return_1y"]) + float(row["excess_return_1y"])
            + float(row["momentum_6m"]) + float(row["sharpe"]) / 5
            + float(row["max_drawdown"]) / 2)


def ranking_score(row: dict) -> float:
    def present(key: str, missing: float) -> float:
        value = row.get(key)
        return missing if value is None else float(value)
    values = (present("return_1y", -9), present("excess_return_1y", -9),
              present("momentum_6m", -9), present("sharpe", -9) / 5,
              present("max_drawdown", -1) / 2)
    return sum(values)


def main() -> int:
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    apify_token = os.environ.get("APIFY_API_TOKEN", "")
    allow_pending = os.environ.get("ALLOW_PENDING", "0") == "1"
    if not api_key and not apify_token and not allow_pending:
        print("TWELVE_DATA_API_KEY or APIFY_API_TOKEN is required", file=sys.stderr)
        return 2

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    categories = {item["id"]: item for item in config["categories"]}
    benchmark_cache: dict[str, list[float]] = {}
    mstarpy_session = None
    enable_mstarpy = os.environ.get("ENABLE_MSTARPY", "0") == "1"
    rows: list[dict] = []

    for fund in config["funds"]:
        category = categories[fund["category"]]
        symbol = fund.get("twelve_data_symbol", "").strip()
        yahoo_fund_id = fund.get("yahoo_fund_id", "").strip()
        morningstar_id = fund.get("morningstar_id", "").strip()
        local_nav_file = fund.get("local_nav_file", "").strip()
        row = {**fund, "category_name": category["name"], "benchmark": category["benchmark_symbol"]}
        fund_values = None
        provider = None
        if local_nav_file:
            try:
                fund_values = fetch_local_nav(local_nav_file)
                provider = "Yahoo台灣下載"
            except Exception as exc:
                row["status"] = f"本機淨值錯誤: {type(exc).__name__}"
        if morningstar_id and enable_mstarpy:
            try:
                fund_values, mstarpy_session = fetch_mstarpy_nav(morningstar_id, mstarpy_session)
                provider = "Morningstar/MStarpy"
            except Exception as exc:
                row["status"] = f"Morningstar錯誤: {type(exc).__name__}"
        if fund_values is None and symbol and (api_key or apify_token):
            try:
                fund_values, provider = fetch_market_closes(symbol, api_key, apify_token)
            except Exception as exc:
                row["status"] = f"市場API錯誤: {type(exc).__name__}"
        if fund_values is None and yahoo_fund_id and apify_token:
            try:
                fund_values, provider = fetch_yahoo_fund_closes(yahoo_fund_id, apify_token)
            except Exception as exc:
                row["status"] = f"Yahoo基金錯誤: {type(exc).__name__}"
        if fund_values is not None:
            try:
                fund_length = len(fund_values)
                risk_metrics = quantstats_metrics(fund_values[-252:], config["risk_free_rate"])
                row.update({
                    "return_1y": pct_change(fund_values, min(252, fund_length - 1)),
                    "momentum_6m": pct_change(fund_values, min(126, fund_length - 1)),
                    "sharpe": risk_metrics.get("sharpe", sharpe(fund_values[-252:], config["risk_free_rate"])),
                    "max_drawdown": risk_metrics.get("max_drawdown", max_drawdown(fund_values)),
                    "recovery_days": recovery_days(fund_values),
                    "status": f"已更新（{provider}）",
                })
                benchmark_symbol = category["benchmark_symbol"]
                try:
                    if benchmark_symbol not in benchmark_cache:
                        benchmark_cache[benchmark_symbol], _ = fetch_market_closes(benchmark_symbol, api_key, apify_token)
                    benchmark_values = benchmark_cache[benchmark_symbol]
                    length = min(len(fund_values), len(benchmark_values))
                    benchmark_values = benchmark_values[-length:]
                    row["benchmark_return_1y"] = pct_change(benchmark_values, min(252, length - 1))
                    if row["return_1y"] is not None and row["benchmark_return_1y"] is not None:
                        row["excess_return_1y"] = row["return_1y"] - row["benchmark_return_1y"]
                except Exception:
                    row["status"] = f"已更新（{provider}；Benchmark資料不足）"
            except Exception as exc:  # keep one bad instrument from blocking every category
                row["status"] = f"指標錯誤: {type(exc).__name__}"
        else:
            if fund.get("seed_return_1y") is not None:
                row["return_1y"] = fund["seed_return_1y"]
                row["status"] = "MoneyDJ報酬；其餘待API"
            else:
                row["status"] = "待填Morningstar或市場代碼"
        row["signal"] = signal(row)
        row["score"] = score(row)
        rows.append(row)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    for category_id, category in categories.items():
        if not grouped[category_id]:
            grouped[category_id].append({
                "category": category_id,
                "category_name": category["name"],
                "name": "基金清單建置中",
                "moneydj_id": "",
                "twelve_data_symbol": "",
                "benchmark": category["benchmark_symbol"],
                "signal": "待資料",
                "status": "待建立基金清單",
                "score": None,
            })
    for category_rows in grouped.values():
        category_rows.sort(key=ranking_score, reverse=True)
        for rank, row in enumerate(category_rows[:10], 1):
            row["rank"] = rank

    DATA.mkdir(exist_ok=True)
    CATEGORY_DATA.mkdir(parents=True, exist_ok=True)
    fields = ["rank", "category_name", "name", "moneydj_id", "twelve_data_symbol", "benchmark", "return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "sharpe", "max_drawdown", "recovery_days", "score", "signal", "status"]

    def write_csv(path: Path, selected: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in selected:
                output = {key: item.get(key, "") for key in fields}
                for key in ("return_1y", "benchmark_return_1y", "excess_return_1y", "momentum_6m", "max_drawdown"):
                    output[key] = fmt(item.get(key), percent=True)
                output["sharpe"] = fmt(item.get("sharpe"))
                output["score"] = fmt(item.get("score"))
                writer.writerow(output)

    ranked = [row for key in categories for row in grouped.get(key, [])[:10]]
    write_csv(DATA / "rankings.csv", ranked)
    for category_id in categories:
        write_csv(CATEGORY_DATA / f"{category_id}.csv", grouped.get(category_id, [])[:10])

    metadata = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(ranked),
        "verified_rows": sum(str(r.get("status", "")).startswith("已更新") for r in ranked),
    }
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
