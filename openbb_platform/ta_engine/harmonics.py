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
