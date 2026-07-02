"""
TradingView-convention harmonic pattern detector (clean-room, pure stdlib).

TradingView's Harmonics indicator classifies an XABCD pivot set by its LEG ratios:
    AB/XA, BC/AB, CD/BC, AD/XA           (CD/XC for Cypher — the Carney exception)
Each pattern is a set of windows on those ratios. A window is (lo, hi); a point
target is written (v, v). A ratio matches if it falls within the window widened by
`tol` (relative), which mirrors the small "% Err" TradingView tolerates.

Windows for CYPHER / BUTTERFLY / BAT are taken from the user's SEB-A.ST screenshots
(exact). GARTLEY / CRAB / DEEP_CRAB use standard Carney values and are marked for
verification against the live TradingView Pine source when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Window = Tuple[float, float]

# Per-pattern ratio windows. Only the ratios listed are constrained for that pattern.
HARMONIC_SPECS: Dict[str, Dict[str, Window]] = {
    # --- verified against user screenshots (SEB-A.ST daily) ---
    "CYPHER":    {"AB_XA": (0.382, 0.618), "BC_AB": (1.272, 1.414), "CD_XC": (0.786, 0.786)},
    "BUTTERFLY": {"AB_XA": (0.786, 0.786), "BC_AB": (0.382, 0.886), "CD_BC": (1.618, 2.618),
                  "AD_XA": (1.272, 1.618)},
    "BAT":       {"AB_XA": (0.382, 0.500), "BC_AB": (0.382, 0.886), "CD_BC": (1.618, 2.618),
                  "AD_XA": (0.886, 0.886)},
    # --- standard Carney values; verify against TradingView Pine source ---
    "GARTLEY":   {"AB_XA": (0.618, 0.618), "BC_AB": (0.382, 0.886), "CD_BC": (1.130, 1.618),
                  "AD_XA": (0.786, 0.786)},
    "CRAB":      {"AB_XA": (0.382, 0.618), "BC_AB": (0.382, 0.886), "CD_BC": (2.240, 3.618),
                  "AD_XA": (1.618, 1.618)},
    "DEEP_CRAB": {"AB_XA": (0.886, 0.886), "BC_AB": (0.382, 0.886), "CD_BC": (2.000, 3.618),
                  "AD_XA": (1.618, 1.618)},
}


@dataclass
class HarmonicMatch:
    pattern: str
    direction: str                       # bullish | bearish
    ratios: Dict[str, float]
    deviation: float                     # total out-of-window deviation (0 = perfect)
    pivots: List[Tuple[int, float]] = field(default_factory=list)


def _ratios(x: float, a: float, b: float, c: float, d: float) -> Dict[str, float]:
    xa, ab, bc, cd = abs(a - x), abs(b - a), abs(c - b), abs(d - c)
    xc, ad = abs(c - x), abs(d - a)
    def r(n, dn): return (n / dn) if dn > 1e-12 else 0.0
    return {"AB_XA": r(ab, xa), "BC_AB": r(bc, ab), "CD_BC": r(cd, bc),
            "AD_XA": r(ad, xa), "CD_XC": r(cd, xc)}


def _is_xabcd_shape(x, a, b, c, d) -> Optional[str]:
    """Return 'bullish'/'bearish' if the five pivots alternate like an XABCD, else None."""
    if x < a > b < c > d:
        return "bullish"          # X low, A high, B low, C high, D low
    if x > a < b > c < d:
        return "bearish"
    return None


def _dev(value: float, win: Window, tol: float) -> Optional[float]:
    """0 if inside the tol-widened window; else the relative distance; None if outside."""
    lo, hi = win
    lo_w, hi_w = lo * (1 - tol), hi * (1 + tol)
    if lo_w <= value <= hi_w:
        center = (lo + hi) / 2 or 1.0
        inside = 0.0 if lo <= value <= hi else min(abs(value - lo), abs(value - hi)) / abs(center)
        return inside
    return None


def detect_harmonic(pivots: List[Tuple[int, float]], tol: float = 0.12
                    ) -> Optional[HarmonicMatch]:
    """Classify a 5-pivot (X,A,B,C,D) set, returning the best-fitting pattern or None."""
    if len(pivots) < 5:
        return None
    (xi, x), (ai, a), (bi, b), (ci, c), (di, d) = pivots[:5]
    direction = _is_xabcd_shape(x, a, b, c, d)
    if direction is None:
        return None

    rr = _ratios(x, a, b, c, d)
    best: Optional[HarmonicMatch] = None
    for name, spec in HARMONIC_SPECS.items():
        total = 0.0
        ok = True
        for key, win in spec.items():
            dv = _dev(rr[key], win, tol)
            if dv is None:
                ok = False
                break
            total += dv
        if ok and (best is None or total < best.deviation):
            best = HarmonicMatch(pattern=name, direction=direction,
                                 ratios={k: round(v, 4) for k, v in rr.items()},
                                 deviation=round(total, 4), pivots=list(pivots[:5]))
    return best


_RATIO_ORDER = ("AB_XA", "BC_AB", "CD_BC", "AD_XA", "CD_XC")


def _grade(dev: float) -> str:
    if dev <= 0.0:
        return "PERFECT"
    if dev <= 0.05:
        return "GOOD"
    if dev <= 0.12:
        return "FAIR"
    return "LOOSE"


def pattern_report(m: "HarmonicMatch") -> Dict:
    """Expand a HarmonicMatch into the TradingView info-box payload: pivot labels,
    the Actual/%Err/Theoretical ratio table, a 0-100 score, and entry/stop/targets.

    Targets/stop use standard harmonic Fib projections of the A->D leg (Target 1 =
    0.382, Target 2 = 0.618; stop = 0.236 beyond D). %Err is distance to the nearest
    theoretical bound (0 inside the window). Exact TradingView target/score formulas
    need the Pine source; these are the standard-harmonic equivalents.
    """
    (xi, X), (ai, A), (bi, B), (ci, C), (di, D) = m.pivots[:5]
    spec = HARMONIC_SPECS[m.pattern]

    table: List[Dict] = []
    accs: List[float] = []
    for key in _RATIO_ORDER:
        if key not in spec:
            continue
        lo, hi = spec[key]
        actual = m.ratios[key]
        if lo <= actual <= hi:
            err = 0.0
        else:
            nb = lo if abs(actual - lo) < abs(actual - hi) else hi
            err = (abs(actual - nb) / nb * 100.0) if nb else 0.0
        theo = f"{lo:g}" if abs(lo - hi) < 1e-9 else f"{lo:g} | {hi:g}"
        table.append({"name": key.replace("_", "/"), "actual": round(actual, 3),
                      "pct_err": round(err, 1), "theoretical": theo})
        accs.append(max(0.0, 100.0 - err))

    leg_acc = round(sum(accs) / len(accs), 2) if accs else 0.0
    dirn = 1.0 if m.direction == "bullish" else -1.0
    ad = abs(D - A)
    entry = round(D, 4)
    stop = round(D - dirn * 0.236 * ad, 4)
    t1 = round(D + dirn * 0.382 * ad, 4)
    t2 = round(D + dirn * 0.618 * ad, 4)
    prz_low, prz_high = sorted((entry, stop))

    return {
        "pattern": m.pattern, "direction": m.direction, "found": True,
        "quality": _grade(m.deviation), "deviation": m.deviation,
        "pivot_idx": [xi, ai, bi, ci, di], "pivot_labels": ["X", "A", "B", "C", "D"],
        "pivot_prices": [round(X,4), round(A,4), round(B,4), round(C,4), round(D,4)],
        "ratios": m.ratios, "ratios_table": table,
        "score": leg_acc, "leg_accuracy": leg_acc,
        "d_price": entry, "entry": entry, "stop": stop, "target1": t1, "target2": t2,
        "prz_low": round(prz_low, 4), "prz_high": round(prz_high, 4),
    }


def scan_patterns(highs: Sequence[float], lows: Sequence[float], depth: int = 5,
                  tol: float = 0.12, max_patterns: int = 25) -> List[Dict]:
    """Full harmonic scan: pivot-lookback ZigZag -> slide 5-pivot windows through the
    TradingView-convention classifier -> TradingView info-box reports, recency-first.
    Symbol/timeframe agnostic (works on any OHLC)."""
    from .pivots import pivot_zigzag
    sw = pivot_zigzag(highs, lows, depth)
    out: List[Dict] = []
    for i in range(len(sw) - 4):
        m = detect_harmonic(sw[i:i + 5], tol)
        if m is not None:
            out.append(pattern_report(m))
    out.sort(key=lambda r: r["pivot_idx"][-1], reverse=True)
    return out[:max_patterns]
