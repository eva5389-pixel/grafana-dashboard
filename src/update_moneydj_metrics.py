#!/usr/bin/env python3
"""Resolve verified MoneyDJ fund IDs and calculate NAV-derived risk metrics."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import csv
import json
from pathlib import Path
import urllib.parse
import urllib.request

from update_dashboard import max_drawdown, recovery_days

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://yuantabank.moneydj.com"
MARKETS = ("taiwan", "japan", "korea", "hong_kong", "china", "usa", "india", "asean", "europe", "brazil")


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 fund-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def flatten(node, output):
    if isinstance(node, list):
        for item in node:
            flatten(item, output)
    elif isinstance(node, dict):
        if node.get("sid") and node.get("name"):
            output[node["name"]] = node["sid"]
        for value in node.values():
            if isinstance(value, (list, dict)):
                flatten(value, output)


def fetch_metric(name: str, sid: str, start: date, end: date) -> tuple[str, dict]:
    query = urllib.parse.urlencode({"a": sid, "b": 1, "c": start.isoformat(), "d": end.isoformat()})
    raw = download(f"{BASE}/w/bcd/tBCDNavList.djbcd?{query}").decode("ascii", errors="ignore")
    parts = raw.split()
    if len(parts) < 2:
        raise RuntimeError("invalid MoneyDJ response")
    dates = parts[0].split(",")
    values = [float(value) for value in parts[1].split(",") if value]
    if len(values) < 30 or len(dates) != len(values):
        raise RuntimeError(f"insufficient NAV history ({len(values)})")
    return name, {
        "moneydj_id": sid,
        "observations": len(values),
        "start": dates[0],
        "end": dates[-1],
        "max_drawdown": max_drawdown(values),
        "recovery_days": recovery_days(values),
        "source": f"{BASE}/w/bcd/tBCDNavList.djbcd?a={sid}",
    }


def main() -> int:
    catalog = json.loads(download(f"{BASE}/wData/query/option/djjson/fundlistJson.djjson").decode("big5hkscs"))
    by_name = {}
    flatten(catalog["ResultSet"]["Result"], by_name)
    names = []
    for market in MARKETS:
        with (ROOT / "data" / "categories" / f"{market}.csv").open(encoding="utf-8-sig") as handle:
            names.extend(row["name"] for row in csv.DictReader(handle))
    matched = {name: by_name[name] for name in names if name in by_name}
    end = date.today()
    start = end - timedelta(days=370)
    metrics, errors = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_metric, name, sid, start, end): name for name, sid in matched.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                key, value = future.result()
                metrics[key] = value
            except Exception as exc:
                errors[name] = str(exc)
    payload = {
        "as_of": end.isoformat(),
        "matched": len(matched),
        "updated": len(metrics),
        "unmatched": sorted(set(names) - set(matched)),
        "errors": errors,
        "funds": metrics,
    }
    destination = ROOT / "config" / "moneydj_metrics.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MoneyDJ matched={len(matched)} updated={len(metrics)} unmatched={len(payload['unmatched'])} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
