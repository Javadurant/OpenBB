# api/tools/backtest_bull_multiregime.py
"""Multi-regime extension of backtest_v33 for the v3.9 BULLISH-STRUCTURE signal.

Reuses backtest_v33's exact look-ahead-safe pipeline (score_setup + setup_ledger
.classify + as-of-sliced regime) but widens history to period="max" and the
window to N_MONDAYS weekly Mondays back from 2026-05-25 — spanning several market
cycles (2021 bull → 2022 bear → 2023-26 recovery/bull) so the FIRED subgroup is
large enough to test the MAE (drawdown) signal for significance.

Writes the SANCTIONED parallel eval file (sentriq_ledger_v33_eval.jsonl) — never
the live ledger. Then splits fired-vs-not and reports hit%, expectancy(R), MAE,
MFE, a bootstrap 95% CI on the MAE difference, Welch t, and a per-regime split.
"""
from __future__ import annotations
import json, math, os, random, sys, time
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("N_MONDAYS", os.getenv("N_MONDAYS", "260"))
import api.tools.backtest_v33 as bt  # noqa: E402

# Per-symbol raw-history disk cache so re-runs never re-hit yfinance (which
# rate-limits under the 24 max-history requests). 1-day TTL.
_RAW_DIR = "/tmp/sentriq_backtest_raw"
_FETCH_BACKOFFS = (0, 10, 30, 60, 90)   # retry schedule on rate-limit


def _fetch_max(sym: str):
    os.makedirs(_RAW_DIR, exist_ok=True)
    safe = "".join(c if (c.isalnum() or c in "-._") else "_" for c in sym)
    fp = os.path.join(_RAW_DIR, f"{safe}_max.json")
    try:
        if os.path.exists(fp) and (time.time() - os.path.getmtime(fp)) < 86400:
            d = json.load(open(fp))
            d["dates"] = [date.fromisoformat(x) for x in d["dates"]]
            print(f"    (cache) {sym}: {len(d['c'])} bars")
            return d
    except Exception:
        pass
    import yfinance as yf
    for backoff in _FETCH_BACKOFFS:
        if backoff:
            time.sleep(backoff)
        try:
            h = yf.Ticker(sym).history(period="max")
            if h is None or len(h) < 400:
                return None
            out = {"dates": [ts.date() for ts in h.index],
                   "c": [float(x) for x in h["Close"]],
                   "h": [float(x) for x in h["High"]],
                   "l": [float(x) for x in h["Low"]],
                   "v": [float(x) for x in h["Volume"]] if "Volume" in h else None}
            try:
                json.dump({**out, "dates": [d.isoformat() for d in out["dates"]]}, open(fp, "w"))
            except Exception:
                pass
            time.sleep(1.5)   # pace between symbols to stay under the rate limit
            return out
        except Exception as e:
            if "RateLimit" in type(e).__name__ or "Too Many" in str(e):
                continue      # transient throttle → retry after backoff
            return None
    return None


def _rr(e):
    d = e["entry"] - e["stop"]
    return (e["target"] - e["entry"]) / d if d > 1e-9 else None


def _grp(rows):
    dec = [e for e in rows if e["outcome"] in ("WIN", "LOSS", "AMBIGUOUS")]
    wins = [e for e in dec if e["outcome"] == "WIN"]
    Rs = [(_rr(e) if e["outcome"] == "WIN" else -1.0) for e in dec if _rr(e) is not None]
    mae = [e["mae_pct"] for e in rows if e.get("mae_pct") is not None]
    mfe = [e["mfe_pct"] for e in rows if e.get("mfe_pct") is not None]
    return {"n": len(rows), "dec": len(dec), "win": len(wins),
            "hit": 100 * len(wins) / len(dec) if dec else None,
            "exp": sum(Rs) / len(Rs) if Rs else None,
            "mae": sum(mae) / len(mae) if mae else None, "mae_arr": mae,
            "mfe": sum(mfe) / len(mfe) if mfe else None}


def _welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return None, None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se < 1e-12:
        return None, None
    t = (ma - mb) / se
    # two-sided p via normal approx (large-n)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, p


def _boot_ci(a, b, iters=5000):
    if len(a) < 5 or len(b) < 5:
        return None, None
    rng = random.Random(42)
    diffs = []
    for _ in range(iters):
        sa = [a[rng.randrange(len(a))] for _ in range(len(a))]
        sb = [b[rng.randrange(len(b))] for _ in range(len(b))]
        diffs.append(sum(sa) / len(sa) - sum(sb) / len(sb))
    diffs.sort()
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters)]


def main():
    bt._fetch = _fetch_max            # widen history to cover multiple regimes
    bt.main()                          # writes sentriq_ledger_v33_eval.jsonl + prints v33 report
    rows = [json.loads(l) for l in open(bt.OUT_PATH) if l.strip()]
    fired = [e for e in rows if isinstance(e.get("sub_scores"), dict) and "bullish_structure" in e["sub_scores"]]
    notf = [e for e in rows if not (isinstance(e.get("sub_scores"), dict) and "bullish_structure" in e["sub_scores"])]
    print("\n" + "=" * 68)
    print(f"BULLISH-STRUCTURE MULTI-REGIME ANALYSIS  (N_MONDAYS={os.getenv('N_MONDAYS')})")
    print("=" * 68)
    print(f"total entries: {len(rows)} | FIRED: {len(fired)} | not fired: {len(notf)}")
    hdr = f'{"group":<24}{"n":>6}{"dec":>6}{"hit%":>8}{"exp(R)":>9}{"MAE%":>9}{"MFE%":>8}'
    print("\n" + hdr); print("-" * len(hdr))
    for lbl, g in [("ALL", rows), ("bullish_structure FIRED", fired), ("NOT fired", notf)]:
        m = _grp(g)
        hs = f"{m['hit']:6.1f}%" if m['hit'] is not None else "   n/a"
        es = f"{m['exp']:+7.3f}" if m['exp'] is not None else "    n/a"
        print(f"{lbl:<24}{m['n']:>6}{m['dec']:>6}{hs:>8}{es:>9}{m['mae']:>9.2f}{m['mfe']:>8.2f}")
    gf, gn = _grp(fired), _grp(notf)
    print("\n-- MAE (drawdown) significance: FIRED vs NOT --")
    if gf["mae"] is not None and gn["mae"] is not None:
        diff = gf["mae"] - gn["mae"]
        t, p = _welch(gf["mae_arr"], gn["mae_arr"])
        lo, hi = _boot_ci(gf["mae_arr"], gn["mae_arr"])
        pooled_sd = math.sqrt((sum((x-gf['mae'])**2 for x in gf['mae_arr'])+sum((x-gn['mae'])**2 for x in gn['mae_arr']))/max(1,(len(gf['mae_arr'])+len(gn['mae_arr'])-2)))
        d = diff / pooled_sd if pooled_sd > 1e-9 else 0.0
        print(f"  mean MAE fired={gf['mae']:.2f}%  not={gn['mae']:.2f}%  diff={diff:+.2f}% (less negative = shallower drawdown)")
        if lo is not None:
            print(f"  bootstrap 95% CI of diff: [{lo:+.2f}%, {hi:+.2f}%]  ({'excludes 0 → significant' if (lo>0 or hi<0) else 'includes 0 → NOT significant'})")
        if t is not None:
            print(f"  Welch t={t:+.2f}  p={p:.4f}  Cohen d={d:+.3f}")
    # per-regime split
    print("\n-- per market regime (as-of risk_on) --")
    for reg in (True, False):
        f = [e for e in fired if e.get("regime_risk_on") == reg]
        n = [e for e in notf if e.get("regime_risk_on") == reg]
        mf, mn = _grp(f), _grp(n)
        tag = "risk-ON" if reg else "risk-OFF"
        hf = f"{mf['hit']:.1f}%" if mf['hit'] is not None else "n/a"
        hn = f"{mn['hit']:.1f}%" if mn['hit'] is not None else "n/a"
        maef = f"{mf['mae']:.2f}" if mf['mae'] is not None else "n/a"
        maen = f"{mn['mae']:.2f}" if mn['mae'] is not None else "n/a"
        print(f"  {tag:<8} fired n={mf['n']:>4} hit={hf:>6} MAE={maef:>6}  |  not n={mn['n']:>5} hit={hn:>6} MAE={maen:>6}")


if __name__ == "__main__":
    main()
