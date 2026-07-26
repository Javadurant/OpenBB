# backtest_run.py
# <- NEW [Backtest/Expectancy Harness] CLI: measure the computed Elliott engine's edge.
#
# USAGE
#   venv/bin/python backtest_run.py                 # offline self-test (synthetic)
#   venv/bin/python backtest_run.py AAPL            # live, daily, 2R target
#   venv/bin/python backtest_run.py AAPL 1d 2.0     # symbol, interval, target_r

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from engine.backtest_signals import backtest_elliott


def _report(title: str, m: dict) -> None:
    print(f"\n===== {title} =====")
    if m.get("note"):
        print(f"  note: {m['note']}")
    print(f"  trades            : {m['trades']}")
    print(f"  win rate          : {m['win_rate']:.1%}")
    print(f"  expectancy (R/trade): {m['expectancy_r']:+.3f}  <- the edge")
    print(f"  total R           : {m['total_r']:+.2f}")
    print(f"  avg win / avg loss: {m['avg_win_r']:+.2f}R / {m['avg_loss_r']:+.2f}R")
    print(f"  profit factor     : {m['profit_factor']}")
    print(f"  max drawdown (R)  : {m['max_drawdown_r']:.2f}")
    print(f"  max losing streak : {m['max_losing_streak']}")
    print(f"  outcomes          : {m['outcomes']}  (target {m['target_r']}R)")
    if m.get("by_setup"):
        print("  by setup:")
        for name, b in sorted(m["by_setup"].items(), key=lambda kv: kv[1]["expectancy_r"], reverse=True):
            print(f"    {name:28s} n={b['trades']:<3d} win={b['win_rate']:.0%} "
                  f"exp={b['expectancy_r']:+.3f}R total={b['total_r']:+.1f}R")
    print(f"  {m['disclaimer']}")


def _synthetic():
    """Two clean impulses + corrections so the harness is exercised offline."""
    pts = [100, 120, 113, 150, 140, 165,   # impulse up + bits
           150, 130, 138, 110, 122, 100]
    seg = 10
    vals = []
    for k in range(len(pts) - 1):
        vals += list(np.linspace(pts[k], pts[k + 1], seg, endpoint=False))
    vals.append(pts[-1])
    a = np.asarray(vals, float)
    labels = [f"d{i}" for i in range(a.size)]
    m = backtest_elliott(a, a, a, labels, target_r=2.0, max_hold=40, warmup=20)
    _report("SYNTHETIC SELF-TEST", m)


def _live(symbol: str, interval: str, target_r: float, mode: str = "all"):
    from datetime import datetime, timedelta
    from openbb import obb
    start = (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")  # ~10y for a real sample
    res = obb.equity.price.historical(symbol, interval=interval, provider="yfinance",
                                      start_date=start)
    df = res.to_df()
    df.columns = [c.lower() for c in df.columns]
    labels = [str(x)[:10] for x in df.index]
    rev = mode in ("all", "rev")
    cont = mode in ("all", "cont")
    m = backtest_elliott(df["high"].to_numpy(float), df["low"].to_numpy(float),
                         df["close"].to_numpy(float), labels, target_r=target_r,
                         enable_reversal=rev, enable_continuation=cont)
    _report(f"{symbol.upper()} {interval} [{mode}] (bars={len(df)})", m)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _synthetic()
    else:
        sym = sys.argv[1]
        interval = sys.argv[2] if len(sys.argv) > 2 else "1d"
        tr = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
        mode = sys.argv[4] if len(sys.argv) > 4 else "all"   # all | cont | rev
        _live(sym, interval, tr, mode)
