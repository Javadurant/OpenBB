# engine/structure/elliott_wave.py
# <- NEW [Elliott Wave Engine]: deterministic 5-3 wave detection + preferred/alternate ranking
#
# DOMAIN SOURCE (dual-verified, nothing invented):
#   [PF]  Frost, A.J. & Prechter, R.R. — Elliott Wave Principle: Key to Market
#         Behavior (10th Ed.), New Classics Library. ISBN 978-0-932750-75-4.
#         Loaded by user as ELLIOTT_WAVE_VERIFIED_REFERENCE.docx.
#   [EWI] Elliott Wave International — Waveopedia
#         https://www.elliottwave.com/waveopedia/  (Home + Impulse entries)
#
# The two mandated principles, implemented literally:
#   P1 WAVE PRINCIPLE DISCIPLINE  -> the three absolute rules are HARD gates.
#      A count violating any rule is discarded ([EWI]: "a rule should never be
#      disregarded"). No relaxation, ever.
#   P2 LOGICAL VALIDATION          -> always emit a PREFERRED count and >=1
#      ALTERNATE count, ranked by the number of GUIDELINES satisfied
#      ([EWI]: "preferred = satisfies the largest number of guidelines").
#
# Every numeric constant below is sourced. No magic numbers. No float ==.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# SOURCED CONSTANTS  (UPPER_SNAKE_CASE, module level)
# ════════════════════════════════════════════════════════════════════════════

# Pivot confirmation window. [PF] IDENTIFICATION_PROTOCOL Step 2:
# "Use N-bar confirmation on both sides (minimum 5 bars each side)."
MIN_PIVOT_BARS: int = 5

# Ratio comparison tolerance for price-swing (Elliott) ratios.
# [PF] FIBONACCI_RATIO_TABLE.FLOAT_COMPARISON_RULE.wave_retracement_tolerance.
WAVE_RATIO_TOLERANCE: float = 0.020

# --- Impulse guideline ratios (probabilistic; used only for SCORING, never as gates) ---
# [PF] FIBONACCI_RATIO_TABLE.IMPULSE_WAVES
W2_RETRACE_OF_W1: tuple[float, ...] = (0.618, 0.500, 0.382)          # [PF] p.28
W3_EXTENSION_OF_W1: tuple[float, ...] = (1.618, 2.618, 4.236, 1.000, 2.000)  # [PF] pp.29-33
W4_RETRACE_OF_W3: tuple[float, ...] = (0.382, 0.236, 0.500)          # [PF] pp.34-37
W5_EQUALS_W1: float = 1.000                                          # [PF] pp.38-42
W5_FIB_OF_W1_W3: float = 0.618                                       # [PF] pp.38-42
W5_EXTENSION: float = 1.618                                          # [PF] pp.38-42

# --- Corrective guideline ratios ---
# [PF] FIBONACCI_RATIO_TABLE.CORRECTIVE_WAVES
ZIGZAG_B_RETRACE_RANGE: tuple[float, float] = (0.382, 0.790)         # [PF] p.52 (upper=0.790)
ZIGZAG_C_VS_A: tuple[float, ...] = (1.000, 1.618, 0.618)             # [PF] p.53
FLAT_REG_B_RETRACE_RANGE: tuple[float, float] = (0.850, 1.000)       # [PF] p.55
FLAT_REG_C_VS_A_RANGE: tuple[float, float] = (1.000, 1.050)          # [PF] p.55
FLAT_EXP_B_RETRACE: tuple[float, ...] = (1.236, 1.382)               # [PF] pp.56-58
FLAT_EXP_C_VS_A: tuple[float, ...] = (1.618, 1.272, 1.000)           # [PF] pp.56-58


# ════════════════════════════════════════════════════════════════════════════
# TYPED RESULT CONTRACTS
# ════════════════════════════════════════════════════════════════════════════

class Direction(str, Enum):
    """Dominant direction of the structure under analysis."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class CountType(str, Enum):
    """Classification of a wave count."""
    IMPULSE = "IMPULSE"
    ZIGZAG = "ZIGZAG"
    FLAT_REGULAR = "FLAT_REGULAR"
    FLAT_EXPANDED = "FLAT_EXPANDED"
    TRIANGLE_CONTRACTING = "TRIANGLE_CONTRACTING"   # <- NEW [Triangles]: [EWI] 3-3-3-3-3
    TRIANGLE_BARRIER = "TRIANGLE_BARRIER"           # <- NEW [Triangles]
    TRIANGLE_EXPANDING = "TRIANGLE_EXPANDING"       # <- NEW [Triangles]
    CORRECTIVE_UNCLASSIFIED = "CORRECTIVE_UNCLASSIFIED"


class WaveStatus(str, Enum):
    """Lifecycle of the most recent labelled wave. [PF] PROTOCOL Step 7."""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    COMPLETING = "COMPLETING"


@dataclass(frozen=True)
class Pivot:
    """A confirmed swing high or swing low."""
    index: int
    label: str          # date/bar label (string) for chart annotation
    price: float
    is_high: bool


@dataclass(frozen=True)
class WaveLeg:
    """One labelled leg of a count. Length is ALWAYS abs(price distance)."""
    name: str           # "1","2","3","4","5" or "A","B","C"
    start_index: int
    end_index: int
    start_price: float
    end_price: float

    @property
    def length(self) -> float:
        """[PF] RULE_2: wave length = abs(end_price - start_price)."""
        return abs(self.end_price - self.start_price)


@dataclass(frozen=True)
class RuleCheck:
    """Result of one absolute-rule gate (P1)."""
    rule_id: str        # "RULE_1" | "RULE_2" | "RULE_3"
    passed: bool
    detail: str
    source: str


@dataclass
class WaveCount:
    """A single fully-validated interpretation."""
    count_type: CountType
    direction: Direction
    legs: list[WaveLeg]
    rule_checks: list[RuleCheck]
    guideline_score: int                # P2 ranking key: #guidelines satisfied
    guideline_matches: list[str]
    atypical_notes: list[str]
    ratios: dict[str, float]
    current_wave: str                   # e.g. "Wave 3" / "Wave C"
    status: WaveStatus
    invalidation_level: float           # make-or-break price [EWI]
    invalidation_reason: str
    targets: dict[str, float]

    @property
    def is_valid(self) -> bool:
        """Validity by count type.

        IMPULSE: valid iff every absolute rule passed (P1).
        CORRECTIVE: valid only if it classified into a sourced form
        (zigzag / flat / expanded flat) AND satisfied >=1 guideline.
        CORRECTIVE_UNCLASSIFIED is NEVER valid ([PF] FORBIDDEN_1 — do not
        surface a forced/ambiguous correction as a confident count).
        """
        if self.count_type is CountType.IMPULSE:  # <- FIXED [Gate test]
            return all(rc.passed for rc in self.rule_checks)
        if self.count_type is CountType.CORRECTIVE_UNCLASSIFIED:
            return False
        return self.guideline_score >= 1


@dataclass
class ElliottResult:
    """Top-level engine output. Consumed by API + chart annotation layer."""
    symbol: str
    timeframe: str
    as_of: str
    source: str
    pivots: list[Pivot]
    preferred: Optional[WaveCount]
    alternate: Optional[WaveCount]
    no_count_reason: Optional[str]      # [PF] FORBIDDEN_1: never force; explain instead
    developing: Optional[dict] = None   # <- NEW: in-progress / nearest projection to the last bar
                                        # (the Elliott analog of a harmonic near-miss)

    @property
    def chart_label(self) -> str:
        """One-line label for under the harmonic PRZ. Never blank."""
        if self.preferred is None:
            if self.developing:
                d = self.developing
                inv = d.get("invalidation_level")
                inv_s = f"{inv:.4g}" if isinstance(inv, (int, float)) else "n/a"
                return (f"Elliott: developing {d.get('label', 'wave')} "
                        f"({d.get('direction', '')}) · nearest possibility · "
                        f"invalidation {inv_s}")
            return f"Elliott: NO VALID COUNT — {self.no_count_reason}"
        p = self.preferred
        base = (f"Elliott: {p.count_type.value} · {p.current_wave} "
                f"({p.status.value}) · invalidation {p.invalidation_level:.4g}")
        if self.developing:
            base += f" · developing {self.developing.get('label', '')}"
        return base


# ════════════════════════════════════════════════════════════════════════════
# NUMERIC HELPERS  (no float ==, safe division)
# ════════════════════════════════════════════════════════════════════════════

def _ratio(numerator: float, denominator: float) -> float:
    """Safe ratio. Returns inf when denominator is ~0 (degenerate leg)."""
    if abs(denominator) <= np.finfo(float).eps:
        return float("inf")
    return numerator / denominator


def _matches(value: float, target: float, tol: float = WAVE_RATIO_TOLERANCE) -> bool:
    """[PF] FLOAT_COMPARISON_RULE: abs(value - target) <= tolerance. Never ==."""
    return abs(value - target) <= tol


def _matches_any(value: float, targets: Sequence[float],
                 tol: float = WAVE_RATIO_TOLERANCE) -> bool:
    """True if value is within tolerance of any sourced target ratio."""
    return any(_matches(value, t, tol) for t in targets)


def _in_range(value: float, lo: float, hi: float,
              tol: float = WAVE_RATIO_TOLERANCE) -> bool:
    """Inclusive range check with tolerance padding on both ends."""
    return (lo - tol) <= value <= (hi + tol)


# ════════════════════════════════════════════════════════════════════════════
# PIVOT DETECTION  ([PF] PROTOCOL Step 2 — N-bar fractal, full swing extremes)
# ════════════════════════════════════════════════════════════════════════════

def detect_pivots(high: np.ndarray, low: np.ndarray, labels: Sequence[str],
                  min_bars: int = MIN_PIVOT_BARS,
                  min_swing_pct: Optional[float] = None) -> list[Pivot]:
    """Identify confirmed swing highs/lows using N-bar fractal confirmation.

    A bar i is a swing HIGH iff its high is strictly greater than every high
    within +/- ``min_bars``. Swing LOW is the symmetric condition on lows.
    Uses full swing extremes (highs/lows), never close-to-close. [PF] FORBIDDEN_6.

    The raw pivots are then collapsed into a strictly alternating high/low
    sequence (consecutive same-type pivots resolved to the more extreme one),
    which is the input shape required by all counting routines.
    """
    n = len(high)
    if n != len(low) or n != len(labels):
        raise ValueError("high, low and labels must be the same length")
    if n < (2 * min_bars + 1):
        return []

    raw: list[Pivot] = []
    for i in range(min_bars, n - min_bars):
        window = slice(i - min_bars, i + min_bars + 1)
        # Swing high: bar i is the maximum high of its +/- min_bars window.
        # Swing low: bar i is the minimum low of its window. Ties between
        # adjacent equal extrema are resolved by _collapse_alternating().
        if high[i] >= float(np.max(high[window])):  # <- FIXED [Gate test]: window-extremum
            raw.append(Pivot(index=i, label=str(labels[i]),
                             price=float(high[i]), is_high=True))
        elif low[i] <= float(np.min(low[window])):  # <- FIXED [Gate test]: window-extremum
            raw.append(Pivot(index=i, label=str(labels[i]),
                             price=float(low[i]), is_high=False))

    pivots = _collapse_alternating(raw)
    pivots = _anchor_boundaries(pivots, high, low, labels, n)  # range-anchoring
    return pivots


def _anchor_boundaries(pivots: list[Pivot], high: np.ndarray, low: np.ndarray,
                       labels: Sequence[str], n: int) -> list[Pivot]:
    """Seed pivots at the first and last bar so a structure that begins or ends
    at the visible-range edge is still countable.

    METHODOLOGY NOTE (stated, not silent): the endpoints of the analysed range
    are treated as natural swing boundaries, typed opposite to their nearest
    confirmed interior pivot. This is a deliberate range-anchoring choice; it
    does not alter any rule or ratio.
    """
    if not pivots:
        return pivots
    out = list(pivots)
    first = out[0]
    if first.index > 0:
        start_is_high = not first.is_high
        out.insert(0, Pivot(index=0, label=str(labels[0]),
                            price=float(high[0] if start_is_high else low[0]),
                            is_high=start_is_high))
    last = out[-1]
    if last.index < n - 1:
        end_is_high = not last.is_high
        out.append(Pivot(index=n - 1, label=str(labels[n - 1]),
                         price=float(high[n - 1] if end_is_high else low[n - 1]),
                         is_high=end_is_high))
    return _collapse_alternating(out)


def _filter_significance(pivots: list[Pivot],
                         min_swing_pct: Optional[float]) -> list[Pivot]:
    """Drop pivots whose swing from the previously retained pivot is smaller
    than ``min_swing_pct`` (fraction of price), then restore alternation.

    Default behaviour (min_swing_pct is None) applies NO filter. The threshold
    value is a domain decision and is NEVER invented here — it must be supplied
    by the caller.
    """
    if min_swing_pct is None or len(pivots) < 2:
        return pivots
    kept: list[Pivot] = [pivots[0]]
    for piv in pivots[1:]:
        ref = kept[-1]
        move = _ratio(abs(piv.price - ref.price), abs(ref.price))
        if move < min_swing_pct:
            continue
        kept.append(piv)
    return _collapse_alternating(kept)


def _collapse_alternating(raw: list[Pivot]) -> list[Pivot]:
    """Force a strict high/low/high/low sequence, keeping the more extreme of
    any consecutive same-type run."""
    out: list[Pivot] = []
    for piv in raw:
        if not out:
            out.append(piv)
            continue
        last = out[-1]
        if last.is_high is piv.is_high:  # bool identity, not float compare
            if piv.is_high and piv.price > last.price:
                out[-1] = piv
            elif (not piv.is_high) and piv.price < last.price:
                out[-1] = piv
            # else: keep existing more-extreme pivot
        else:
            out.append(piv)
    return out


# ════════════════════════════════════════════════════════════════════════════
# ABSOLUTE RULES  (P1 — hard gates, [PF] PART 1, [EWI] Impulse)
# ════════════════════════════════════════════════════════════════════════════

def _check_rules(w1: WaveLeg, w2: WaveLeg, w3: WaveLeg, w4: WaveLeg, w5: WaveLeg,
                 direction: Direction) -> list[RuleCheck]:
    """Apply the three absolute impulse rules. Length-based, strict, no ==."""
    checks: list[RuleCheck] = []

    # RULE 1 — Wave 2 never retraces 100%+ of Wave 1. [PF] p.21
    w2_retrace = _ratio(w2.length, w1.length)
    r1 = w2_retrace < 1.000
    checks.append(RuleCheck(
        "RULE_1", r1,
        f"W2 retrace of W1 = {w2_retrace:.3f} (must be < 1.000)",
        "[PF] Ch.2 p.21"))

    # RULE 2 — Wave 3 is never the shortest of 1,3,5. [EWI] Motive Waves states the
    # canonical measure is PERCENTAGE movement: "As long as wave 3 undergoes a
    # greater percentage movement than either wave 1 or 5, this rule is satisfied."
    # [PF] adds it "almost always holds on an arithmetic basis as well." Gate is the
    # sourced percentage basis; arithmetic lengths are retained in the detail.
    # <- FIXED [RULE_2 percentage basis]: per [EWI] Motive Waves (human-approved).
    w1_pct = _ratio(w1.length, abs(w1.start_price))
    w3_pct = _ratio(w3.length, abs(w3.start_price))
    w5_pct = _ratio(w5.length, abs(w5.start_price))
    r2 = w3_pct > min(w1_pct, w5_pct)
    checks.append(RuleCheck(
        "RULE_2", r2,
        f"%move W1={w1_pct:.4f} W3={w3_pct:.4f} W5={w5_pct:.4f} "
        f"(W3 not shortest by % move); arith W1={w1.length:.4g} "
        f"W3={w3.length:.4g} W5={w5.length:.4g}",
        "[EWI] Motive Waves (percentage basis) / [PF] Ch.2 p.21"))

    # RULE 3 — Wave 4 never enters Wave 1 territory (no overlap). [PF] p.21 / [EWI]
    if direction is Direction.BULLISH:
        r3 = w4.end_price > w1.end_price
        detail = f"W4 low {w4.end_price:.4g} must be > W1 high {w1.end_price:.4g}"
    else:
        r3 = w4.end_price < w1.end_price
        detail = f"W4 high {w4.end_price:.4g} must be < W1 low {w1.end_price:.4g}"
    checks.append(RuleCheck(
        "RULE_3", r3, detail + " (diagonal exception NOT auto-applied)",
        "[PF] Ch.2 p.21 / [EWI] Impulse"))

    return checks


# ════════════════════════════════════════════════════════════════════════════
# GUIDELINE SCORING  (P2 ranking — count satisfied guidelines)
# ════════════════════════════════════════════════════════════════════════════

def _score_impulse(w1: WaveLeg, w2: WaveLeg, w3: WaveLeg, w4: WaveLeg,
                   w5: WaveLeg) -> tuple[int, list[str], list[str], dict[str, float]]:
    """Count how many impulse GUIDELINES this valid count satisfies.

    Each satisfied guideline contributes +1. This integer is the P2 ranking
    key. Only sourced ratios are scored — nothing invented.
    """
    score = 0
    matches: list[str] = []
    atypical: list[str] = []
    ratios: dict[str, float] = {}

    r_w2 = _ratio(w2.length, w1.length)
    ratios["w2_retrace_of_w1"] = r_w2
    if _matches_any(r_w2, W2_RETRACE_OF_W1):
        score += 1
        matches.append(f"W2 retrace {r_w2:.3f} matches guideline")
    else:
        atypical.append(f"W2 retrace {r_w2:.3f} atypical")

    r_w3 = _ratio(w3.length, w1.length)
    ratios["w3_extension_of_w1"] = r_w3
    if _matches_any(r_w3, W3_EXTENSION_OF_W1):
        score += 1
        matches.append(f"W3 extension {r_w3:.3f} matches guideline")
    else:
        atypical.append(f"W3 extension {r_w3:.3f} atypical")

    # Guideline: W3 usually the longest of 1,3,5 ([PF] WAVE_3_GUIDELINES).
    if w3.length >= w1.length and w3.length >= w5.length:
        score += 1
        matches.append("W3 is the longest impulse wave")

    r_w4 = _ratio(w4.length, w3.length)
    ratios["w4_retrace_of_w3"] = r_w4
    if _matches_any(r_w4, W4_RETRACE_OF_W3):
        score += 1
        matches.append(f"W4 retrace {r_w4:.3f} matches guideline")
    else:
        atypical.append(f"W4 retrace {r_w4:.3f} atypical")

    # W5 relationships ([PF] WAVE_5_GUIDELINES): equality / fib of W1-W3 / extension
    r_w5_w1 = _ratio(w5.length, w1.length)
    ratios["w5_vs_w1"] = r_w5_w1
    net_1_to_3 = abs(w3.end_price - w1.start_price)
    r_w5_net = _ratio(w5.length, net_1_to_3)
    ratios["w5_vs_w1w3_net"] = r_w5_net
    if (_matches(r_w5_w1, W5_EQUALS_W1) or _matches(r_w5_w1, W5_EXTENSION)
            or _matches(r_w5_net, W5_FIB_OF_W1_W3)):
        score += 1
        matches.append(f"W5 relationship {r_w5_w1:.3f}xW1 matches guideline")
    else:
        atypical.append(f"W5 relationship {r_w5_w1:.3f}xW1 atypical")

    return score, matches, atypical, ratios


# ════════════════════════════════════════════════════════════════════════════
# COUNT BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def _legs_from_pivots(pivots: list[Pivot], names: Sequence[str]) -> list[WaveLeg]:
    """Build consecutive legs from N+1 pivots and N names."""
    legs: list[WaveLeg] = []
    for k, name in enumerate(names):
        a, b = pivots[k], pivots[k + 1]
        legs.append(WaveLeg(name, a.index, b.index, a.price, b.price))
    return legs


def _build_impulse(six: list[Pivot]) -> Optional[WaveCount]:
    """Attempt a 5-wave impulse from 6 alternating pivots. Returns a valid
    WaveCount or None if any absolute rule fails (P1 discard)."""
    direction = Direction.BULLISH if not six[0].is_high else Direction.BEARISH
    w1, w2, w3, w4, w5 = _legs_from_pivots(six, ("1", "2", "3", "4", "5"))

    checks = _check_rules(w1, w2, w3, w4, w5, direction)
    if not all(c.passed for c in checks):
        return None  # P1: violating count is discarded entirely

    score, matches, atypical, ratios = _score_impulse(w1, w2, w3, w4, w5)

    # Targets ([PF] INTERPRETATION_TEMPLATES) and make-or-break level ([EWI]).
    targets: dict[str, float] = {}
    if direction is Direction.BULLISH:
        targets["w5_equality"] = w4.end_price + w1.length
        invalidation = w4.end_price        # break of W4 questions the count
    else:
        targets["w5_equality"] = w4.end_price - w1.length
        invalidation = w4.end_price

    return WaveCount(
        count_type=CountType.IMPULSE, direction=direction,
        legs=[w1, w2, w3, w4, w5], rule_checks=checks,
        guideline_score=score, guideline_matches=matches, atypical_notes=atypical,
        ratios=ratios, current_wave="Wave 5", status=WaveStatus.COMPLETE,
        invalidation_level=invalidation,
        invalidation_reason="Break of Wave 4 extreme questions the impulse",
        targets=targets)


def _build_corrective(four: list[Pivot]) -> Optional[WaveCount]:
    """Attempt an A-B-C corrective from 4 alternating pivots. Classifies as
    zigzag / regular flat / expanded flat using sourced ratios; otherwise
    returns CORRECTIVE_UNCLASSIFIED (never forced, [PF] FORBIDDEN_1)."""
    direction = Direction.BEARISH if four[0].is_high else Direction.BULLISH
    a, b, c = _legs_from_pivots(four, ("A", "B", "C"))

    b_retrace = _ratio(b.length, a.length)
    c_vs_a = _ratio(c.length, a.length)
    ratios = {"b_retrace_of_a": b_retrace, "c_vs_a": c_vs_a}
    score = 0
    matches: list[str] = []
    atypical: list[str] = []

    if _in_range(b_retrace, *ZIGZAG_B_RETRACE_RANGE):
        ctype = CountType.ZIGZAG
        score += 1
        matches.append(f"B retrace {b_retrace:.3f} within zigzag range")
        if _matches_any(c_vs_a, ZIGZAG_C_VS_A):
            score += 1
            matches.append(f"C vs A {c_vs_a:.3f} matches zigzag guideline")
        else:
            atypical.append(f"C vs A {c_vs_a:.3f} atypical for zigzag")
    elif _in_range(b_retrace, *FLAT_REG_B_RETRACE_RANGE):
        ctype = CountType.FLAT_REGULAR
        score += 1
        matches.append(f"B retrace {b_retrace:.3f} within regular-flat range")
        if _in_range(c_vs_a, *FLAT_REG_C_VS_A_RANGE):
            score += 1
            matches.append(f"C vs A {c_vs_a:.3f} matches regular flat")
    elif _matches_any(b_retrace, FLAT_EXP_B_RETRACE):
        ctype = CountType.FLAT_EXPANDED
        score += 1
        matches.append(f"B retrace {b_retrace:.3f} matches expanded flat")
        if _matches_any(c_vs_a, FLAT_EXP_C_VS_A):
            score += 1
            matches.append(f"C vs A {c_vs_a:.3f} matches expanded flat")
    else:
        ctype = CountType.CORRECTIVE_UNCLASSIFIED
        atypical.append(
            f"B retrace {b_retrace:.3f} fits neither zigzag/flat/expanded-flat")

    invalidation = four[0].price  # break of correction origin
    return WaveCount(
        count_type=ctype, direction=direction, legs=[a, b, c],
        rule_checks=[], guideline_score=score, guideline_matches=matches,
        atypical_notes=atypical, ratios=ratios, current_wave="Wave C",
        status=WaveStatus.COMPLETE, invalidation_level=invalidation,
        invalidation_reason="Break of correction origin re-opens the count",
        targets={})


def _build_triangle(six: list[Pivot]) -> Optional[WaveCount]:
    """Attempt an A-B-C-D-E triangle from 6 alternating pivots (five overlapping
    legs, 3-3-3-3-3). [EWI] Triangles: a triangle is delineated by connecting the
    termination points of waves A & C and B & D — the two boundary lines. It is
    classified by how those lines behave:

      contracting — both lines converge (highs fall, lows rise);
      expanding   — both lines diverge (highs rise, lows fall);
      barrier     — one boundary line is horizontal while the other moves.

    Returns CORRECTIVE_UNCLASSIFIED when the six pivots do not form any of these
    (never forced, [PF] FORBIDDEN_1). All structural — no invented ratios; the
    only tolerance reused is WAVE_RATIO_TOLERANCE for the 'horizontal' test.
    """
    direction = Direction.BEARISH if six[0].is_high else Direction.BULLISH
    a, b, c, d, e = _legs_from_pivots(six, ("A", "B", "C", "D", "E"))

    # The two boundary lines = the three highs and the three lows of the window.
    if six[0].is_high:
        highs = [six[0].price, six[2].price, six[4].price]
        lows = [six[1].price, six[3].price, six[5].price]
    else:
        lows = [six[0].price, six[2].price, six[4].price]
        highs = [six[1].price, six[3].price, six[5].price]

    def _desc(x: list[float]) -> bool:
        return x[0] > x[1] > x[2]

    def _asc(x: list[float]) -> bool:
        return x[0] < x[1] < x[2]

    def _flat(x: list[float]) -> bool:
        scale = max(abs(v) for v in x) or 1.0
        return (max(x) - min(x)) / scale <= WAVE_RATIO_TOLERANCE

    highs_desc, highs_asc, highs_flat = _desc(highs), _asc(highs), _flat(highs)
    lows_desc, lows_asc, lows_flat = _desc(lows), _asc(lows), _flat(lows)

    score = 0
    matches: list[str] = []
    atypical: list[str] = []

    if highs_desc and lows_asc:
        ctype = CountType.TRIANGLE_CONTRACTING
        score += 1
        matches.append("Boundaries converge (highs fall, lows rise) — contracting")
    elif highs_asc and lows_desc:
        ctype = CountType.TRIANGLE_EXPANDING
        score += 1
        matches.append("Boundaries diverge (highs rise, lows fall) — expanding")
    elif lows_asc and highs_flat:
        ctype = CountType.TRIANGLE_BARRIER
        score += 1
        matches.append("Flat upper boundary, rising lows — ascending barrier")
    elif highs_desc and lows_flat:
        ctype = CountType.TRIANGLE_BARRIER
        score += 1
        matches.append("Flat lower boundary, falling highs — descending barrier")
    else:
        ctype = CountType.CORRECTIVE_UNCLASSIFIED
        atypical.append("Boundary lines neither converge, diverge, nor form a barrier")

    # Guideline: a clean contracting triangle shrinks each successive subwave. [EWI] Fig.1
    if (ctype is CountType.TRIANGLE_CONTRACTING
            and a.length > c.length > e.length and b.length > d.length):
        score += 1
        matches.append("Each successive subwave smaller (clean contraction)")

    # Running triangle: wave B exceeds the start of wave A. [EWI] Fig.2
    if ctype is not CountType.CORRECTIVE_UNCLASSIFIED:
        running = (b.end_price > a.start_price if direction is Direction.BEARISH
                   else b.end_price < a.start_price)
        if running:
            matches.append("Wave B exceeds start of wave A — running triangle")

    ratios = {"a_len": a.length, "b_len": b.length, "c_len": c.length,
              "d_len": d.length, "e_len": e.length}
    widest = max(a.length, b.length, c.length, d.length, e.length)
    return WaveCount(
        count_type=ctype, direction=direction, legs=[a, b, c, d, e],
        rule_checks=[], guideline_score=score, guideline_matches=matches,
        atypical_notes=atypical, ratios=ratios, current_wave="Wave E",
        status=WaveStatus.COMPLETE, invalidation_level=six[0].price,
        invalidation_reason="Break of triangle origin re-opens the count",
        targets={"thrust_distance": widest})  # [EWI]: thrust ~ widest part of triangle


def _apply_live_status(count: WaveCount, last_price: float) -> None:
    """Mark the terminal wave IN_PROGRESS/COMPLETING if the latest bar has not
    yet confirmed a reversal beyond the final pivot. Sets the current-wave label
    that the chart shows under the harmonic PRZ ([PF] PROTOCOL Step 7)."""
    final = count.legs[-1]
    moved_beyond = (
        last_price > final.end_price if count.direction is Direction.BULLISH
        else last_price < final.end_price)
    if moved_beyond:
        count.status = WaveStatus.IN_PROGRESS
        count.current_wave = f"Wave {final.name}"


def _build_developing(pivots: list[Pivot], base: Optional[WaveCount],
                      last_price: float, last_label: str) -> Optional[dict]:
    """Project the IN-PROGRESS ('developing') wave to the latest bar — the Elliott
    analog of a harmonic near-miss. This is NOT a confirmed count: it labels the
    current swing by motive/corrective ALTERNATION from the most recent confirmed
    structure ([EWI]: a five is followed by a three and vice-versa) and reports the
    make-or-break level. It is always flagged 'developing' so the UI can show it
    dashed and low-confidence — never as a settled signal ([PF] FORBIDDEN_1).

    The leg runs from the last confirmed pivot to 'now' (live price), so something
    is always drawn on the most recent candles even when no complete count exists.
    """
    if len(pivots) < 2:
        return None
    start = pivots[-2]            # last confirmed pivot before the live bar
    end_price = float(last_price)
    # No developing wave without an actual swing away from the last pivot.
    if abs(end_price - start.price) <= np.finfo(float).eps:
        return None
    direction = "BULLISH" if end_price >= start.price else "BEARISH"

    # Alternation: what most likely follows the base count's final wave.
    label, wave = "developing swing", "?"
    if base is not None:
        ct = base.count_type
        if ct is CountType.IMPULSE:
            label, wave = "Wave A", "A"            # five complete -> correction starts
        elif ct in (CountType.ZIGZAG, CountType.FLAT_REGULAR, CountType.FLAT_EXPANDED):
            label, wave = "Wave 1", "1"            # correction complete -> impulse starts
        elif ct in (CountType.TRIANGLE_CONTRACTING, CountType.TRIANGLE_BARRIER,
                    CountType.TRIANGLE_EXPANDING):
            label, wave = "post-triangle thrust", "T"

    return {
        "label": label, "wave": wave, "status": "IN_PROGRESS", "direction": direction,
        "start_label": start.label, "start_price": start.price,
        "end_label": str(last_label), "end_price": end_price,
        "invalidation_level": start.price,   # break of the swing origin re-opens it
        "confidence": "developing",
        "note": ("Developing / unconfirmed: the current swing labelled by "
                 "motive-corrective alternation from the latest confirmed "
                 "structure. A new confirmed pivot is needed to settle it."),
    }


def signal_for_count(count: Optional[WaveCount]) -> dict:
    """Map a COMPLETED count to a trade signal, gated by the measured edge.

    POLICY (from the walk-forward backtest — engine/backtest_signals.py; see
    CLAUDE.md 'Backtest finding'): corrective CONTINUATION trades (trade WITH the
    trend after a correction completes) showed positive expectancy; IMPULSE-
    reversal (fading a finished trend) did not. So continuation -> tradeable;
    reversal -> informational only. This is a backtest-derived policy, NOT an
    [EWI] rule, and NOT financial advice — risk is defined by the stop.
    """
    none = {"bias": "NONE", "kind": "none", "tradeable": False,
            "stop": None, "rationale": "No completed count."}
    if count is None:
        return none
    terminal = count.legs[-1].end_price
    net = count.legs[-1].end_price - count.legs[0].start_price

    if count.count_type is CountType.IMPULSE:
        return {"bias": "SHORT" if net > 0 else "LONG", "kind": "reversal",
                "tradeable": False, "stop": terminal,
                "rationale": ("Fading a completed impulse — informational only "
                              "(negative backtest edge).")}

    corrective = {CountType.ZIGZAG, CountType.FLAT_REGULAR, CountType.FLAT_EXPANDED,
                  CountType.TRIANGLE_CONTRACTING, CountType.TRIANGLE_BARRIER,
                  CountType.TRIANGLE_EXPANDING}
    if count.count_type in corrective:
        return {"bias": "LONG" if net < 0 else "SHORT", "kind": "continuation",
                "tradeable": True, "stop": terminal,
                "rationale": ("Trend resumption after a completed correction "
                              "(positive backtest edge).")}
    return {**none, "stop": terminal, "rationale": "Unclassified correction."}


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def analyze(high: Sequence[float], low: Sequence[float], close: Sequence[float],
            labels: Sequence[str], *, symbol: str, timeframe: str, as_of: str,
            min_bars: int = MIN_PIVOT_BARS,
            min_swing_pct: Optional[float] = None) -> ElliottResult:
    """Run the full Elliott Wave analysis.

    Produces a PREFERRED and an ALTERNATE count ranked by guideline score (P2),
    every count gated by the three absolute rules (P1). If no valid count
    exists, ``no_count_reason`` is populated and ``chart_label`` reports why
    ([PF] FORBIDDEN_1 — never force a count).

    Args:
        high, low, close: OHLC arrays of equal length (e.g. from OBBject.to_df()).
        labels: per-bar date/label strings for chart annotation.
        symbol, timeframe, as_of: provenance, surfaced on the chart + Ask layer.
        min_bars: pivot confirmation window (default sourced = 5).
    """
    source = "[PF] Frost & Prechter EWP 10th Ed. + [EWI] Waveopedia"
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    cl = np.asarray(close, dtype=float)

    try:
        pivots = detect_pivots(h, lo, labels, min_bars=min_bars)
        pivots = _filter_significance(pivots, min_swing_pct)
    except ValueError as exc:
        logger.error("Pivot detection failed for %s: %s", symbol, exc)
        return ElliottResult(symbol, timeframe, as_of, source, [], None, None,
                             f"input error: {exc}")

    if len(pivots) < 4:
        reason = (f"only {len(pivots)} confirmed pivots at {min_bars}-bar "
                  f"sensitivity — insufficient structure for any count")
        logger.info("No count for %s: %s", symbol, reason)
        dev = _build_developing(pivots, None, float(cl[-1]), labels[-1])
        return ElliottResult(symbol, timeframe, as_of, source, pivots, None,
                             None, reason, developing=dev)

    candidates: list[WaveCount] = []

    # Impulse attempts over the most recent 6-pivot windows.
    for end in range(len(pivots), 5, -1):
        window = pivots[end - 6:end]
        if len(window) == 6:
            count = _build_impulse(window)
            if count is not None:
                _apply_live_status(count, float(cl[-1]))
                candidates.append(count)

    # Corrective attempts over the most recent 4-pivot windows.
    for end in range(len(pivots), 3, -1):
        window = pivots[end - 4:end]
        if len(window) == 4:
            count = _build_corrective(window)
            if count is not None:
                _apply_live_status(count, float(cl[-1]))
                candidates.append(count)

    # Triangle attempts (A-B-C-D-E) over the most recent 6-pivot windows. [EWI] Triangles
    for end in range(len(pivots), 5, -1):
        window = pivots[end - 6:end]
        if len(window) == 6:
            count = _build_triangle(window)
            if count is not None:
                _apply_live_status(count, float(cl[-1]))
                candidates.append(count)

    valid = [c for c in candidates if c.is_valid]
    if not valid:
        reason = ("no interpretation satisfied all three absolute rules "
                  "(W2<100%, W3 not shortest, W4 no overlap)")
        logger.info("No valid count for %s: %s", symbol, reason)
        dev = _build_developing(pivots, None, float(cl[-1]), labels[-1])
        return ElliottResult(symbol, timeframe, as_of, source, pivots, None,
                             None, reason, developing=dev)

    # RANKING (product policy, user-mandated): the preferred count must describe the
    # MOST RECENT structure so waves render on the latest candles. Primary key =
    # recency (terminal pivot index); ties broken by [EWI] guideline score, then
    # impulse. The highest-guideline historical count remains available as ALTERNATE.
    valid.sort(key=lambda c: (c.legs[-1].end_index,
                              c.guideline_score,
                              c.count_type is CountType.IMPULSE), reverse=True)
    preferred = valid[0]
    # Alternate = the best DIFFERENT count by guideline score (the textbook read).
    others = [c for c in valid[1:]]
    others.sort(key=lambda c: (c.guideline_score, c.legs[-1].end_index), reverse=True)
    alternate = others[0] if others else None

    # Developing projection only when price has moved beyond the preferred count's
    # final pivot — i.e. there is still-unlabelled action on the most recent candles.
    dev = None
    if pivots and preferred.legs[-1].end_index < pivots[-1].index:
        dev = _build_developing(pivots, preferred, float(cl[-1]), labels[-1])
    return ElliottResult(symbol, timeframe, as_of, source, pivots,
                         preferred, alternate, None, developing=dev)
