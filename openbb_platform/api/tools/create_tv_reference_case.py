"""TradingView values-parity case creator/validator (v3.4).

CDP automation has failed three times (tv_launch spawns, port 9222 never
responds), so THIS is the primary parity route: create a template, fill it
from TradingView's Indicator Values panel by hand, validate, run parity.

Create a template:
  venv/bin/python -m api.tools.create_tv_reference_case --symbol SKF-B.ST --timeframe 1D
Validate a filled case:
  venv/bin/python -m api.tools.create_tv_reference_case --validate api/tests/tv_reference/SKF-B.ST-1D.json
Then run parity:
  venv/bin/python -m pytest api/tests/test_tv_parity.py -q

Manual capture steps (TradingView Desktop):
  1. Open the SAME symbol + timeframe (e.g. OMXSTO:SKF_B, 1D).
  2. Add the indicators you want to compare (RSI, Ichimoku, MACD, BB).
  3. Enable the Data Window / Indicator Values panel.
  4. Hover the LAST CLOSED bar; note bar date and each value.
  5. Export or copy enough OHLCV bars (>= 80, same bars TV displays).
  6. Fill this template's ohlcv arrays + tv_values; save; validate; run parity.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tests", "tv_reference")
REQUIRED_META = ("symbol", "exchange", "timeframe", "timezone", "as_of")
KNOWN_VALUES = ("rsi_14", "macd", "macd_signal", "macd_histogram",
                "macd_hist_positive", "tenkan", "kijun", "senkou_a", "senkou_b",
                "chikou", "bollinger_upper", "bollinger_middle", "bollinger_lower",
                "atr", "ma20", "ma50", "ma100", "ma200")
MIN_BARS = 80


def template(symbol: str, timeframe: str) -> dict:
    return {
        "source": "TradingView",
        "capture_method": "manual_copy",
        "symbol": symbol,
        "exchange": "",
        "timeframe": timeframe,
        "timezone": "",
        "session": "",
        "as_of": "",
        "bar_time": "",
        "indicator_settings": {"rsi": 14, "ichimoku": "9/26/52", "macd": "12/26/9",
                               "bollinger": "20/2"},
        "ohlcv": {"closes": [], "highs": [], "lows": []},
        "tv_values": {k: None for k in KNOWN_VALUES},
        "patterns": [], "elliott_counts": [], "fib_levels": [], "fib_time": [],
        "tolerances": {"rsi_14": 1.5, "tenkan_pct": 0.2, "kijun_pct": 0.2},
        "notes": "Fill ohlcv with the SAME bars TradingView displays (oldest first, "
                 ">= 80 bars) and tv_values from the Indicator Values panel at the "
                 "last closed bar. Delete tv_values keys you did not capture.",
    }


def validate(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        case = json.load(fh)
    errors: list[str] = []
    for k in REQUIRED_META:
        if not case.get(k):
            errors.append(f"missing metadata: {k}")
    o = case.get("ohlcv") or {}
    n = len(o.get("closes") or [])
    if n < MIN_BARS:
        errors.append(f"ohlcv.closes has {n} bars (< {MIN_BARS} needed for Ichimoku/RSI windows)")
    if len(o.get("highs") or []) != n or len(o.get("lows") or []) != n:
        errors.append("ohlcv arrays must be equal length")
    tv = {k: v for k, v in (case.get("tv_values") or {}).items() if v is not None}
    if not tv:
        errors.append("tv_values has no captured values - fill at least one")
    unknown = [k for k in tv if k not in KNOWN_VALUES]
    if unknown:
        errors.append(f"unknown tv_values keys: {unknown}")
    if errors:
        print(f"INVALID: {path}")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print(f"VALID: {path} ({n} bars, {len(tv)} captured values: {sorted(tv)})")
    print("Next: venv/bin/python -m pytest api/tests/test_tv_parity.py -q")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol")
    p.add_argument("--timeframe", default="1D")
    p.add_argument("--out")
    p.add_argument("--validate")
    p.add_argument("--list-fields", action="store_true")
    p.add_argument("--instructions", action="store_true")
    a = p.parse_args()
    if a.list_fields:
        print("required metadata:", ", ".join(REQUIRED_META))
        print("accepted tv_values:", ", ".join(KNOWN_VALUES))
        print(f"ohlcv: closes/highs/lows arrays, equal length, >= {MIN_BARS} bars")
        return 0
    if a.instructions:
        print(
            "TradingView values-parity: exact steps (no coding needed)\n"
            "1. TradingView Desktop -> open the symbol + timeframe (e.g. OMXSTO:SKF_B, 1D).\n"
            "2. Add indicators to compare: Relative Strength Index, Ichimoku Cloud,\n"
            "   MACD, Bollinger Bands.\n"
            "3. Right-click chart -> enable the Data Window (Indicator Values).\n"
            "4. Hover the LAST CLOSED bar; write down the bar date and each value.\n"
            "5. Export/copy >= 80 OHLCV bars for the SAME chart (TradingView:\n"
            "   chart menu -> Export chart data, or copy from the data window).\n"
            "6. Create the template:\n"
            "   venv/bin/python -m api.tools.create_tv_reference_case --symbol SKF-B.ST --timeframe 1D\n"
            "7. Edit the printed JSON file: fill ohlcv arrays + tv_values;\n"
            "   delete tv_values keys you did not capture.\n"
            "8. Validate:\n"
            "   venv/bin/python -m api.tools.create_tv_reference_case --validate api/tests/tv_reference/SKF-B.ST-1D.json\n"
            "9. Run parity:\n"
            "   venv/bin/python -m pytest api/tests/test_tv_parity.py -q")
        return 0
    if a.validate:
        return validate(a.validate)
    if not a.symbol:
        p.error("--symbol required (or use --validate FILE)")
    os.makedirs(REF_DIR, exist_ok=True)
    name = a.out or f"{a.symbol.replace('/', '_')}-{a.timeframe}.json"
    path = os.path.join(REF_DIR, name)
    if os.path.exists(path):
        print(f"refusing to overwrite existing case: {path}")
        return 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(template(a.symbol, a.timeframe), fh, indent=2)
    print(f"template written: {path}")
    print("Fill it per the module docstring, then validate:")
    print(f"  venv/bin/python -m api.tools.create_tv_reference_case --validate '{path}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
