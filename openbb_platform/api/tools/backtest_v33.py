"""v3.3 trust-ledger re-seed + component-effect backtest (look-ahead-safe).

The live ledger's calibration (n=134, speed 0.75) was seeded with the retired
v2 engine. This tool seeds a PARALLEL evaluation file with the v3.3 engine and
measures which components actually correlate with outcomes.

LOOK-AHEAD SAFETY:
  - every score uses ONLY bars <= as_of (sliced once-fetched series);
  - market regime / sector RS computed from SLICED index/ETF series;
  - news, earnings calendar, fundamentals and ledger calibration are EXCLUDED
    (they cannot be reconstructed as-of-date without leakage) - honestly noted;
  - outcomes evaluated on strictly-later bars via setup_ledger.classify
    (same first-touch WIN/LOSS/AMBIGUOUS/EXPIRED contract as the live ledger).

NEVER touches sentriq_ledger.jsonl. Output: sentriq_ledger_v33_eval.jsonl.

Run (reproducible):
  cd openbb_platform && venv/bin/python -m api.tools.backtest_v33
Optional: N_MONDAYS env var (default 21, Mondays backwards from 2026-05-25).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from api.setup_scanner import score_setup, build_technical_context, _atr  # noqa: E402
from api.setup_ledger import classify  # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "sentriq_ledger_v33_eval.jsonl")

SWE = ["VOLV-B.ST", "ERIC-B.ST", "HM-B.ST", "INVE-B.ST", "ATCO-A.ST", "SAND.ST",
       "SEB-A.ST", "EVO.ST", "ABB.ST", "ASSA-B.ST", "SWED-A.ST", "SKF-B.ST"]
INTL = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "AVGO", "JPM", "V",
        "COST", "NFLX", "AMD"]
RETURN_HORIZONS = (1, 3, 5, 9, 18, 24, 30)


def _mondays(n: int, last: date) -> list[date]:
    d = last
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return [d - timedelta(weeks=i) for i in range(n)][::-1]


def _fetch(sym: str):
    import yfinance as yf
    h = yf.Ticker(sym).history(period="3y")
    if h is None or len(h) < 300:
        return None
    return {
        "dates": [ts.date() for ts in h.index],
        "c": [float(x) for x in h["Close"]],
        "h": [float(x) for x in h["High"]],
        "l": [float(x) for x in h["Low"]],
        "v": [float(x) for x in h["Volume"]] if "Volume" in h else None,
    }


def _regime_at(idx_series, cut: int):
    c = idx_series["c"][: cut + 1]
    if len(c) < 200:
        return None
    ma200 = sum(c[-200:]) / 200
    return {"index": idx_series["sym"], "close": round(c[-1], 2),
            "ma200": round(ma200, 2), "risk_on": c[-1] > ma200}


def main() -> None:
    n_mondays = int(os.getenv("N_MONDAYS", "21"))
    mondays = _mondays(n_mondays, date(2026, 5, 25))
    print(f"seeding {len(mondays)} Mondays {mondays[0]} .. {mondays[-1]}")

    cache: dict = {}
    for sym in SWE + INTL + ["^OMX", "^GSPC"]:
        cache[sym] = _fetch(sym)
        if cache[sym]:
            cache[sym]["sym"] = sym
        print(f"  fetched {sym}: {len(cache[sym]['c']) if cache[sym] else 0} bars")

    entries: list[dict] = []
    for sym in SWE + INTL:
        s = cache.get(sym)
        if not s:
            continue
        region = "Swedish" if sym.endswith(".ST") else "International"
        idx = cache["^OMX" if region == "Swedish" else "^GSPC"]
        for as_of in mondays:
            cut = max((i for i, d in enumerate(s["dates"]) if d <= as_of), default=-1)
            if cut < 300:
                continue
            closes, highs, lows = s["c"][: cut + 1], s["h"][: cut + 1], s["l"][: cut + 1]
            vols = s["v"][: cut + 1] if s["v"] else None
            atr = _atr(highs, lows, closes)
            ctx = build_technical_context(highs, lows, closes, atr, symbol=sym) if atr else None
            icut = max((i for i, d in enumerate(idx["dates"]) if d <= as_of), default=-1) if idx else -1
            regime = _regime_at(idx, icut) if idx and icut >= 200 else None
            r = score_setup(sym, region, closes, highs, lows,
                            as_of=s["dates"][cut], technical_context=ctx,
                            volumes=vols, market_regime=regime)
            if not r:
                continue
            fut_h, fut_l = s["h"][cut + 1:], s["l"][cut + 1:]
            fut_c = s["c"][cut + 1:]
            horizon = int(r["max_trading_days"])
            outcome, bars = classify(r["entry"], r["stop"], r["target"],
                                     fut_h, fut_l, horizon)
            if outcome == "EXPIRED" and len(fut_h) < horizon:
                continue  # not enough future bars to judge honestly
            win_h = min(horizon, len(fut_h))
            mae = (min(fut_l[:win_h]) / r["entry"] - 1) * 100 if win_h else None
            mfe = (max(fut_h[:win_h]) / r["entry"] - 1) * 100 if win_h else None
            rets = {f"r{n}": round((fut_c[n - 1] / r["entry"] - 1) * 100, 2)
                    for n in RETURN_HORIZONS if len(fut_c) >= n}
            ell_support = any("Elliott" in x for x in r.get("supports", []))
            ell_conflict = any("Elliott" in x for x in r.get("conflicts", []))
            entries.append({
                "symbol": sym, "region": region, "as_of": s["dates"][cut].isoformat(),
                "grade": r["grade"], "classification": r["classification"],
                "score": r["score"], "risk_level": r["risk_level"],
                "n_conflicts": len(r.get("conflicts", [])),
                "sub_scores": r["sub_scores"], "penalties": r["penalties"],
                "regime_risk_on": bool(regime and regime.get("risk_on")),
                "volume_confirmed": bool(r["sub_scores"].get("volume", 0) >= 3.0),
                "sr_clean": bool(r["sub_scores"].get("support_resistance", 0) >= 4.0),
                "fib_cluster": bool(r["sub_scores"].get("fib_price", 0) >= 2.0),
                "pitchfork_up": bool(r["sub_scores"].get("pitchfork", 0) >= 3.0),
                "elliott_support": ell_support, "elliott_conflict": ell_conflict,
                "entry": r["entry"], "stop": r["stop"], "target": r["target"],
                "expected_days": r["expected_trading_days"], "horizon": horizon,
                "outcome": outcome, "bars_to_resolve": bars,
                "mae_pct": round(mae, 2) if mae is not None else None,
                "mfe_pct": round(mfe, 2) if mfe is not None else None,
                **rets,
            })
        print(f"  scored {sym}: cumulative entries={len(entries)}")

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    print(f"\nwrote {len(entries)} entries -> {OUT_PATH}")
    report(entries)


def _bucket(entries, key_fn, label):
    from collections import defaultdict
    groups = defaultdict(list)
    for e in entries:
        groups[key_fn(e)].append(e)
    rows = []
    for k in sorted(groups, key=str):
        g = groups[k]
        wins = sum(1 for e in g if e["outcome"] == "WIN")
        losses = sum(1 for e in g if e["outcome"] in ("LOSS", "AMBIGUOUS"))
        dec = wins + losses
        hr = 100 * wins / dec if dec else None
        speed = sorted(e["bars_to_resolve"] / max(1, e["expected_days"])
                       for e in g if e["outcome"] == "WIN" and e["bars_to_resolve"])
        med_speed = speed[len(speed) // 2] if speed else None
        mfe = [e["mfe_pct"] for e in g if e.get("mfe_pct") is not None]
        mae = [e["mae_pct"] for e in g if e.get("mae_pct") is not None]
        rows.append((k, len(g), dec, hr, med_speed,
                     sum(mfe) / len(mfe) if mfe else None,
                     sum(mae) / len(mae) if mae else None))
    print(f"\n== {label} ==")
    print(f"{'bucket':28} {'n':>4} {'dec':>4} {'hit%':>6} {'speed':>6} {'MFE%':>6} {'MAE%':>6}")
    for k, n, dec, hr, sp, mfe, mae in rows:
        hr_s = f"{hr:6.1f}" if hr is not None else "   n/a"
        sp_s = f"{sp:6.2f}" if sp is not None else "   n/a"
        mfe_s = f"{mfe:6.2f}" if mfe is not None else "   n/a"
        mae_s = f"{mae:6.2f}" if mae is not None else "   n/a"
        print(f"{str(k)[:28]:28} {n:>4} {dec:>4} {hr_s} {sp_s} {mfe_s} {mae_s}")
    return rows


def report(entries: list[dict]) -> None:
    print(f"\n=========== v3.3 COMPONENT-EFFECT REPORT (n={len(entries)}) ===========")
    _bucket(entries, lambda e: e["grade"], "grade")
    _bucket(entries, lambda e: e["classification"], "classification")
    _bucket(entries, lambda e: min(e["n_conflicts"], 3), "conflict count (3=3+)")
    _bucket(entries, lambda e: e["regime_risk_on"], "market regime risk-on")
    _bucket(entries, lambda e: e["volume_confirmed"], "volume confirmed (>=3/4)")
    _bucket(entries, lambda e: e["sr_clean"], "S/R clean (4/4)")
    _bucket(entries, lambda e: e["fib_cluster"], "fib price cluster (>=2/3)")
    _bucket(entries, lambda e: e["pitchfork_up"], "pitchfork full (3/3)")
    _bucket(entries, lambda e: e["elliott_support"], "Elliott supportive")
    _bucket(entries, lambda e: e["elliott_conflict"], "Elliott conflicting")
    _bucket(entries, lambda e: e["region"], "region")
    wins = [e for e in entries if e["outcome"] == "WIN" and e["bars_to_resolve"]]
    if wins:
        ratios = sorted(e["bars_to_resolve"] / max(1, e["expected_days"]) for e in wins)
        errs = sorted(abs(e["bars_to_resolve"] - e["expected_days"]) / max(1, e["expected_days"])
                      for e in wins)
        print(f"\n== v3.3 timing calibration (WIN-only, n={len(wins)}) ==")
        print(f"median actual/expected speed: {ratios[len(ratios)//2]:.2f}")
        print(f"median abs pct timing error:  {errs[len(errs)//2]:.2f}")


if __name__ == "__main__":
    main()
