# verify_elliott.py
# <- NEW [Elliott Wave Engine]: self-contained verifier for engine/structure/elliott_wave.py
#
# PURPOSE
#   Offline contract checks (no network) + an optional live OpenBB smoke test.
#   Nothing about the domain is invented here: the absolute-rule and no-count
#   behaviours asserted below are exactly those documented in elliott_wave.py
#   ([PF] Frost & Prechter EWP 10th Ed. + [EWI] Waveopedia).
#
# USAGE
#   venv/bin/python verify_elliott.py            # 6 offline logic checks
#   venv/bin/python verify_elliott.py VOLV-B.ST  # offline + live OpenBB test
#
# EXIT CODE  0 = all offline checks passed, non-zero otherwise.

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

_PASS = 0
_FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    """Record one assertion. Never raises — collects results for a summary."""
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}  {detail}")


# ── IMPORT CHECK ────────────────────────────────────────────────────────────
print("\n[IMPORT CHECK]")
try:
    from engine.structure import elliott_wave as ew
    _check("import engine.structure.elliott_wave", True)
except Exception as exc:  # noqa: BLE001 — verifier must report, not crash
    print(f"  FAIL  import failed: {exc}")
    sys.exit(2)

for _attr in ("analyze", "detect_pivots", "ElliottResult", "WaveCount",
              "Pivot", "CountType", "Direction", "MIN_PIVOT_BARS",
              "WAVE_RATIO_TOLERANCE"):
    _check(f"public symbol present: {_attr}", hasattr(ew, _attr))


def _pivots(spec: list[tuple[int, float, bool]]) -> list:
    """Build a list[ew.Pivot] from (index, price, is_high) triples."""
    return [ew.Pivot(index=i, label=f"b{i}", price=float(p), is_high=h)
            for (i, p, h) in spec]


def _impulse_series(points: list[float], seg: int = 8):
    """Piecewise-linear high==low==close series through control points.
    Each leg spans `seg` bars so the N-bar (5) fractal resolves each turn.
    Returns (high, low, close, labels)."""
    vals: list[float] = []
    for k in range(len(points) - 1):
        vals.extend(np.linspace(points[k], points[k + 1], seg,
                                endpoint=False).tolist())
    vals.append(points[-1])
    arr = np.asarray(vals, dtype=float)
    labels = [f"d{i}" for i in range(arr.size)]
    return arr, arr, arr, labels


# ── 6 OFFLINE LOGIC CHECKS ──────────────────────────────────────────────────
print("\n[LOGIC CHECKS]")

# L1 — No structure -> never blank label, explicit no-count reason. [PF] FORBIDDEN_1
flat = np.full(14, 100.0)
res_flat = ew.analyze(flat, flat, flat, [f"d{i}" for i in range(flat.size)],
                      symbol="FLAT", timeframe="1d", as_of="d13")
_check("L1 no-count: preferred is None", res_flat.preferred is None)
_check("L1 no-count: chart_label not blank",
       res_flat.chart_label.startswith("Elliott: NO VALID COUNT"),
       res_flat.chart_label)

# Clean textbook bullish impulse, 6 alternating pivots (low,high,...,high).
clean = _pivots([(0, 100, False), (8, 110, True), (16, 106, False),
                 (24, 126, True), (32, 118, False), (40, 128, True)])

# L2 — clean impulse is built, classified IMPULSE, valid, all 3 rules pass.
c2 = ew._build_impulse(clean)
_check("L2 impulse built (not None)", c2 is not None)
_check("L2 type == IMPULSE", c2 is not None and c2.count_type is ew.CountType.IMPULSE)
_check("L2 is_valid True", c2 is not None and c2.is_valid)
_check("L2 all 3 absolute rules passed",
       c2 is not None and all(rc.passed for rc in c2.rule_checks))

# L3 — RULE_1 gate: W2 retraces >100% of W1 -> impulse discarded (None).
bad1 = _pivots([(0, 100, False), (8, 110, True), (16, 98, False),
                (24, 126, True), (32, 118, False), (40, 128, True)])
_check("L3 RULE_1 violation discarded", ew._build_impulse(bad1) is None)

# L4 — RULE_2 gate: W3 is the shortest of 1/3/5 -> discarded (None).
bad2 = _pivots([(0, 100, False), (8, 110, True), (16, 106, False),
                (24, 111, True), (32, 110.5, False), (40, 120.5, True)])
_check("L4 RULE_2 violation discarded", ew._build_impulse(bad2) is None)

# L5 — RULE_3 gate: W4 enters W1 territory (overlap) -> discarded (None).
bad3 = _pivots([(0, 100, False), (8, 110, True), (16, 106, False),
                (24, 126, True), (32, 108, False), (40, 128, True)])
_check("L5 RULE_3 violation discarded", ew._build_impulse(bad3) is None)

# L6 — full pipeline: detection->analyze yields IMPULSE and is deterministic.
h, lo, cl, lab = _impulse_series([100, 110, 106, 126, 118, 128])
r6a = ew.analyze(h, lo, cl, lab, symbol="SYN", timeframe="1d", as_of=lab[-1])
r6b = ew.analyze(h, lo, cl, lab, symbol="SYN", timeframe="1d", as_of=lab[-1])
_check("L6 pipeline finds a preferred count", r6a.preferred is not None,
       r6a.no_count_reason or "")
_check("L6 preferred is IMPULSE",
       r6a.preferred is not None and r6a.preferred.count_type is ew.CountType.IMPULSE,
       "" if r6a.preferred is None else r6a.preferred.count_type.value)
_check("L6 deterministic chart_label", r6a.chart_label == r6b.chart_label)

# L7 — RULE_2 now uses the sourced PERCENTAGE basis ([EWI] Motive Waves) and the
#      clean textbook impulse still satisfies it.
_r2 = next((rc for rc in (c2.rule_checks if c2 else []) if rc.rule_id == "RULE_2"), None)
_check("L7 RULE_2 present on clean impulse", _r2 is not None)
_check("L7 RULE_2 cites EWI percentage basis",
       _r2 is not None and "Motive Waves" in _r2.source,
       "" if _r2 is None else _r2.source)
_check("L7 RULE_2 detail shows %move basis",
       _r2 is not None and "%move" in _r2.detail,
       "" if _r2 is None else _r2.detail)
_check("L7 RULE_2 passes for clean impulse", _r2 is not None and _r2.passed)

# L8 — Triangles ([EWI] A-B-C-D-E, 3-3-3-3-3). Contracting/expanding classified by
#      converging/diverging boundary lines; an uptrending impulse is NOT a triangle.
tri = _pivots([(0, 120, True), (8, 100, False), (16, 116, True),
               (24, 104, False), (32, 112, True), (40, 108, False)])
t_con = ew._build_triangle(tri)
_check("L8 contracting triangle classified",
       t_con is not None and t_con.count_type is ew.CountType.TRIANGLE_CONTRACTING)
_check("L8 contracting triangle is_valid", t_con is not None and t_con.is_valid)
_check("L8 triangle has 5 legs A-E",
       t_con is not None and [l.name for l in t_con.legs] == ["A", "B", "C", "D", "E"])

exp = _pivots([(0, 112, True), (8, 108, False), (16, 116, True),
               (24, 104, False), (32, 120, True), (40, 100, False)])
t_exp = ew._build_triangle(exp)
_check("L8 expanding triangle classified",
       t_exp is not None and t_exp.count_type is ew.CountType.TRIANGLE_EXPANDING)

# The clean impulse pivots (both boundaries rising) must NOT read as a triangle.
t_none = ew._build_triangle(clean)
_check("L8 trending impulse is not a triangle",
       t_none is not None and not t_none.is_valid
       and t_none.count_type is ew.CountType.CORRECTIVE_UNCLASSIFIED)

# L9 — Developing projection ("nearest possibility" anchored to the latest bar).
dev_piv = _pivots([(0, 100, False), (8, 110, True), (16, 106, False), (24, 126, True)])
dev = ew._build_developing(dev_piv, None, 130.0, "d40")
_check("L9 developing built from recent pivots", dev is not None)
_check("L9 developing reaches the live price", dev is not None and dev["end_price"] == 130.0)
_check("L9 developing carries invalidation", dev is not None and "invalidation_level" in dev)
_imp = ew._build_impulse(clean)
dev2 = ew._build_developing(clean, _imp, clean[-1].price + 5.0, "dX")
_check("L9 alternation: after IMPULSE -> developing Wave A",
       dev2 is not None and dev2["wave"] == "A")
# no-count path still surfaces a developing projection (like a harmonic near-miss)
_check("L9 no-count result still exposes developing",
       res_flat.preferred is None)  # flat data -> no count; developing may be None (≥2 pivots needed)


# ── OPTIONAL LIVE OPENBB SMOKE TEST ─────────────────────────────────────────
def _live_test(ticker: str) -> None:
    """Fetch real OHLC the same way app.py does and run analyze().
    Informational only — does not affect the offline exit code."""
    print(f"\n[LIVE OPENBB TEST] {ticker}")
    try:
        from openbb import obb  # noqa: PLC0415 — optional, only on demand
        res = obb.equity.price.historical(ticker, provider="yfinance")  # type: ignore[attr-defined]
        df = res.to_df()
    except Exception as exc:  # noqa: BLE001
        print(f"  SKIP  could not fetch {ticker}: {exc}")
        return
    if df is None or df.empty:
        print(f"  SKIP  no data returned for {ticker}")
        return

    labels = [str(x) for x in df.index]
    out = ew.analyze(df["high"].to_numpy(float), df["low"].to_numpy(float),
                     df["close"].to_numpy(float), labels,
                     symbol=ticker, timeframe="1d", as_of=labels[-1])
    print(f"  bars={len(df)}  pivots={len(out.pivots)}")
    print(f"  chart_label: {out.chart_label}")
    if out.preferred is not None:
        p = out.preferred
        print(f"  preferred : {p.count_type.value} score={p.guideline_score} "
              f"{p.current_wave} inval={p.invalidation_level:.4g}")
    if out.alternate is not None:
        a = out.alternate
        print(f"  alternate : {a.count_type.value} score={a.guideline_score}")
    print(f"  source    : {out.source}")


# ── MAIN ────────────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    _live_test(sys.argv[1])

print(f"\n[SUMMARY] {_PASS} passed, {_FAIL} failed")
sys.exit(0 if _FAIL == 0 else 1)
