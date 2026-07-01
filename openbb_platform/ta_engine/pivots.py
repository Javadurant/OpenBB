"""
TradingView-style pivot-lookback ZigZag.

Replicates ta.pivothigh(depth) / ta.pivotlow(depth): a bar is a confirmed pivot
high when its high strictly exceeds the `depth` highs to its left and is >= the
`depth` highs to its right (pivot low symmetric on lows). Consecutive same-
direction pivots are collapsed to the more extreme one, yielding a strictly
alternating swing series — the pivot method TradingView harmonic indicators
consume. This is far finer than a percentage ZigZag, which is why the percentage
ZigZag misses the patterns the chart draws.

Returns List[(bar_index, price)] — a drop-in for scan_all_harmonic_patterns,
which already slides its pattern windows over every swing.
"""
from typing import List, Sequence, Tuple


def pivot_zigzag(highs: Sequence[float], lows: Sequence[float], depth: int = 5
                 ) -> List[Tuple[int, float]]:
    n = len(highs)
    if n == 0 or depth < 1 or len(lows) != n:
        return []

    raw: List[Tuple[int, float, bool]] = []          # (index, price, is_high)
    for i in range(depth, n - depth):
        hi, lo = highs[i], lows[i]
        left_h, right_h = highs[i - depth:i], highs[i + 1:i + depth + 1]
        left_l, right_l = lows[i - depth:i], lows[i + 1:i + depth + 1]
        is_ph = all(hi > x for x in left_h) and all(hi >= x for x in right_h)
        is_pl = all(lo < x for x in left_l) and all(lo <= x for x in right_l)
        if is_ph and not is_pl:
            raw.append((i, float(hi), True))
        elif is_pl and not is_ph:
            raw.append((i, float(lo), False))
        # both/neither -> ambiguous, skip

    # Collapse consecutive same-direction pivots, keeping the more extreme.
    out: List[Tuple[int, float, bool]] = []
    for idx, price, is_high in raw:
        if out and out[-1][2] == is_high:
            keep_new = (is_high and price > out[-1][1]) or (not is_high and price < out[-1][1])
            if keep_new:
                out[-1] = (idx, price, is_high)
        else:
            out.append((idx, price, is_high))

    return [(i, p) for i, p, _ in out]
