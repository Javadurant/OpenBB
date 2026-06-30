"""
Rule-gated Elliott Wave engine (clean-room, pure stdlib).

Encodes the THREE ABSOLUTE RULES and motive/corrective guidelines from the
user's verified reference ("ELLIOTT WAVE VERIFIED REFERENCE" ->
Frost & Prechter, Elliott Wave Principle, 10th Ed., Ch.2 pp.21-90).

Design posture (matches AUDIT-elliott-harmonic-2026-06-27.md):
  * Rules are LAWS: any violation => count INVALID (unless a diagonal exception applies).
  * Guidelines are probabilities: missing one keeps the count VALID but atypical.
  * Every rejected count logs the exact failed rule.
  * Operates on pivots (bar_index, price) only -- no pandas, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Pivot:
    """A single ZigZag turning point."""
    index: int
    price: float
    time: Optional[str] = None


@dataclass
class ImpulseResult:
    """Classification of a 6-pivot window as an impulse / diagonal / invalid."""
    structure: str                                   # IMPULSE | INVALID (+ diagonals later)
    direction: str = "bullish"                       # bullish | bearish
    invalidation: float = 0.0                        # price that negates the count (W1 origin)
    is_diagonal: bool = False                         # True when overlap is permitted (wedge)
    failed_rules: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    pivots: List[Pivot] = field(default_factory=list)  # the 6 window pivots (W1 start .. W5 end)


@dataclass
class ElliottAnalysis:
    """Result of scanning a full swing series: a ranked set of valid counts."""
    preferred: Optional[ImpulseResult] = None
    alternates: List[ImpulseResult] = field(default_factory=list)
    counts: List[ImpulseResult] = field(default_factory=list)  # all valid, recency-desc


def classify_impulse(pivots: List[Pivot]) -> ImpulseResult:
    """
    Classify 6 pivots (start-W1 .. end-W5) against the three absolute rules.

    RULE_1: Wave 2 never retraces 100%+ of Wave 1 ([PF] p.21).
    RULE_2: Wave 3 never the SHORTEST of W1/W3/W5 measured by LENGTH ([PF] p.21).
    """
    p0, p1, p2, p3, p4, p5 = pivots[:6]
    bullish = p1.price > p0.price
    failed: List[str] = []

    # SHAPE -- the six pivots must alternate like a 5-wave impulse and W3 must
    # extend beyond the W1 extreme. (Truncated W5 is allowed; not required to
    # exceed W3 here.) This gate lets a sliding-window scan reject "wrong-foot"
    # windows that begin on a corrective leg.
    if bullish:
        shape_ok = (
            p0.price < p1.price > p2.price < p3.price > p4.price < p5.price
            and p3.price > p1.price
        )
    else:
        shape_ok = (
            p0.price > p1.price < p2.price > p3.price < p4.price > p5.price
            and p3.price < p1.price
        )
    if not shape_ok:
        failed.append("SHAPE")

    # RULE_1 -- bullish: wave2_low must be strictly above wave1 start (p0).
    #           bearish: wave2_high must be strictly below wave1 start (p0).
    if bullish:
        if p2.price <= p0.price:
            failed.append("RULE_1")
    else:
        if p2.price >= p0.price:
            failed.append("RULE_1")

    # RULE_2 -- measure by LENGTH (price distance), never by endpoint price.
    len_w1 = abs(p1.price - p0.price)
    len_w3 = abs(p3.price - p2.price)
    len_w5 = abs(p5.price - p4.price)
    if len_w3 <= len_w1 and len_w3 <= len_w5:
        failed.append("RULE_2")

    # RULE_3 -- Wave 4 must not enter Wave 1 territory (strict impulse).
    #   bullish: wave4_low (p4) must stay strictly above wave1 end (p1, the W1 high).
    #   bearish: wave4_high (p4) must stay strictly below wave1 end (p1, the W1 low).
    # The diagonal exception (overlap permitted) is handled by classify(), not here.
    if bullish:
        if p4.price <= p1.price:
            failed.append("RULE_3")
    else:
        if p4.price >= p1.price:
            failed.append("RULE_3")

    structure = "INVALID" if failed else "IMPULSE"
    return ImpulseResult(
        structure=structure,
        direction="bullish" if bullish else "bearish",
        invalidation=p0.price,
        failed_rules=failed,
        pivots=list(pivots[:6]),
    )


def classify(pivots: List[Pivot]) -> ImpulseResult:
    """
    Classify a 6-pivot window, applying the diagonal exception to RULE_3.

    A strict impulse whose ONLY violation is RULE_3 (W4/W1 overlap) is re-read as
    a DIAGONAL when the motive waves form a contracting wedge (W1 > W3 > W5 by
    length) -- the configuration in which the reference permits overlap
    ([PF] pp.83-90). Leading vs ending sub-type is positional and is assigned by
    the scan that owns surrounding context, not here.
    """
    base = classify_impulse(pivots)
    if base.structure == "IMPULSE":
        return base

    if base.failed_rules == ["RULE_3"]:
        p0, p1, p2, p3, p4, p5 = pivots[:6]
        len_w1 = abs(p1.price - p0.price)
        len_w3 = abs(p3.price - p2.price)
        len_w5 = abs(p5.price - p4.price)
        if len_w1 > len_w3 > len_w5:                      # converging / contracting wedge
            base.structure = "DIAGONAL"
            base.is_diagonal = True
            base.failed_rules = [r for r in base.failed_rules if r != "RULE_3"]
            base.notes.append("DIAGONAL -- overlap permitted (contracting wedge)")
    return base


def _coerce_pivots(swings) -> List[Pivot]:
    """Accept either Pivot objects or (bar_index, price) tuples from compute_zigzag."""
    out: List[Pivot] = []
    for s in swings:
        if isinstance(s, Pivot):
            out.append(s)
        else:
            idx, price = s[0], s[1]
            out.append(Pivot(int(idx), float(price)))
    return out


def analyze(swings) -> ElliottAnalysis:
    """
    Scan a full swing series for valid Elliott impulse / diagonal counts (E1 fix).

    Slides a 6-pivot window across EVERY position -- so an impulse that completed
    earlier in the series, and Wave 5 itself, are in scope (the legacy detector
    only inspected the last ~4 legs). Returns all valid counts ranked by recency
    (most recent = preferred), with the rest as alternates.
    """
    pivots = _coerce_pivots(swings)
    counts: List[ImpulseResult] = []
    for i in range(len(pivots) - 5):
        window = pivots[i:i + 6]
        result = classify(window)
        if result.structure in ("IMPULSE", "DIAGONAL"):
            counts.append(result)

    # Recency tie-break: latest-completing count first (defensible, transparent;
    # a guideline-fit confidence score can refine this later).
    counts.sort(key=lambda r: r.pivots[-1].index, reverse=True)

    preferred = counts[0] if counts else None
    alternates = counts[1:] if len(counts) > 1 else []
    return ElliottAnalysis(preferred=preferred, alternates=alternates, counts=counts)
