"""Intraday bars importer (v3.5) — converts the sub-60m limitation into a
user-provided export path.

Live sub-60m bars have NO configured source (yfinance floor is 60m, FMP
intraday is plan-gated). This importer accepts TradingView/FMP/other CSV or
JSON exports so the timing refiner can use finer bars whenever the user
supplies them. Daily/60m fallbacks stay explicit and honest.

Create a template:
  venv/bin/python -m api.tools.import_intraday --template my_export.json
Import CSV (columns: time,open,high,low,close[,volume]):
  venv/bin/python -m api.tools.import_intraday --import-csv skf_15m.csv \
      --symbol SKF-B.ST --timeframe 15m --timezone Europe/Stockholm --source tradingview_export
Import JSON (template shape):
  venv/bin/python -m api.tools.import_intraday --import-json my_export.json

Imported series land in intraday_reference/<SYMBOL>-<TF>.json. Consumption:
api.setup_scanner.refine_target_time_intraday accepts any bar arrays -
load_intraday_reference() below returns (highs, lows, closes, bars_per_day).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

REF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "intraday_reference")
VALID_TF = {"1m": 390, "5m": 78, "15m": 26, "30m": 13, "60m": 7}   # US bars/day
VALID_TF_ST = {"1m": 510, "5m": 102, "15m": 34, "30m": 17, "60m": 8.5}
MIN_BARS = 30

TEMPLATE = {
    "symbol": "SKF-B.ST", "exchange": "OMXSTO", "timeframe": "15m",
    "timezone": "Europe/Stockholm", "source": "tradingview_export",
    "capture_method": "csv_export | manual_copy",
    "bars": [{"time": "2026-07-11T09:00", "open": 0, "high": 0, "low": 0,
              "close": 0, "volume": 0}],
}


def validate_series(data: dict) -> list[str]:
    errors = []
    for k in ("symbol", "timeframe", "timezone", "source"):
        if not data.get(k):
            errors.append(f"missing field: {k}")
    if data.get("timeframe") not in VALID_TF:
        errors.append(f"timeframe must be one of {sorted(VALID_TF)}")
    bars = data.get("bars") or []
    if len(bars) < MIN_BARS:
        errors.append(f"needs >= {MIN_BARS} bars (got {len(bars)})")
    times = [b.get("time") for b in bars]
    if any(not t for t in times):
        errors.append("every bar needs a time")
    elif times != sorted(times):
        errors.append("bar times must be ascending")
    for i, b in enumerate(bars):
        try:
            o, h, l, c = (float(b["open"]), float(b["high"]),
                          float(b["low"]), float(b["close"]))
            if not (l <= o <= h and l <= c <= h) or l <= 0:
                errors.append(f"bar {i}: OHLC sanity failed")
                break
        except (KeyError, TypeError, ValueError):
            errors.append(f"bar {i}: non-numeric OHLC")
            break
    return errors


def save_series(data: dict) -> str:
    os.makedirs(REF_DIR, exist_ok=True)
    path = os.path.join(REF_DIR, f"{data['symbol']}-{data['timeframe']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def load_intraday_reference(symbol: str, timeframe: str | None = None):
    """(highs, lows, closes, bars_per_day) for the refiner, or None.
    Picks the finest available timeframe when none is specified."""
    if not os.path.isdir(REF_DIR):
        return None
    order = ["1m", "5m", "15m", "30m", "60m"]
    tfs = [timeframe] if timeframe else order
    for tf in tfs:
        path = os.path.join(REF_DIR, f"{symbol}-{tf}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        bars = data.get("bars") or []
        if len(bars) < MIN_BARS:
            continue
        per_day = (VALID_TF_ST if symbol.upper().endswith(".ST") else VALID_TF)[tf]
        return ([float(b["high"]) for b in bars],
                [float(b["low"]) for b in bars],
                [float(b["close"]) for b in bars],
                per_day)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--template")
    p.add_argument("--import-json")
    p.add_argument("--import-csv")
    p.add_argument("--symbol")
    p.add_argument("--timeframe")
    p.add_argument("--timezone", default="Europe/Stockholm")
    p.add_argument("--source", default="csv_export")
    a = p.parse_args()
    if a.template:
        with open(a.template, "w", encoding="utf-8") as fh:
            json.dump(TEMPLATE, fh, indent=2)
        print(f"template written: {a.template}")
        return 0
    if a.import_csv:
        if not a.symbol or not a.timeframe:
            p.error("--import-csv needs --symbol and --timeframe")
        with open(a.import_csv, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        data = {"symbol": a.symbol, "timeframe": a.timeframe,
                "timezone": a.timezone, "source": a.source,
                "capture_method": "csv_export",
                "bars": [{k: r.get(k) or r.get(k.capitalize()) for k in
                          ("time", "open", "high", "low", "close", "volume")}
                         for r in rows]}
    elif a.import_json:
        with open(a.import_json, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        p.error("use --template, --import-csv or --import-json")
        return 2
    errors = validate_series(data)
    if errors:
        print("INVALID:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    path = save_series(data)
    print(f"imported {len(data['bars'])} bars -> {path}")
    print("Consumed by refine_target_time_intraday via load_intraday_reference().")
    return 0


if __name__ == "__main__":
    sys.exit(main())
