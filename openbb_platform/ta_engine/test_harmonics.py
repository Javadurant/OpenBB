"""
TradingView-convention harmonic detector tests.

TradingView's Harmonics scores LEG ratios: AB/XA, BC/AB, CD/BC, AD/XA (CD/XC for
Cypher). The acceptance cases below are built from the EXACT ratios in the user's
SEB-A.ST screenshots, so passing them means our classifier agrees with the chart.

Pivots are (X, A, B, C, D). Bullish: X low, A high, B low, C high, D low.
Bearish: mirror.
"""
from ta_engine.harmonics import detect_harmonic


def _prices_bull_cypher():
    # Screenshot: Bullish Cypher AB/XA 0.552, BC/AB 1.275, CD/XC 0.828.
    X = 100.0
    A = 120.0                       # XA = 20
    B = A - 0.552 * (A - X)         # AB/XA = 0.552 -> B = 108.96
    C = B + 1.275 * (A - B)         # BC/AB = 1.275 -> C = 123.04 (extends past A)
    XC = abs(C - X)
    D = C - 0.828 * XC              # CD/XC = 0.828 -> D = 103.96 (a low)
    return [(0, X), (2, A), (4, B), (6, C), (8, D)]


def _prices_bear_butterfly():
    # Screenshot: Bearish Butterfly AB/XA 0.847, BC/AB 0.930, CD/BC 1.686, AD/XA 1.386.
    X = 200.0
    A = 180.0                       # XA = 20
    B = A + 0.847 * (X - A)         # 196.94 (high)
    C = B - 0.930 * (B - A)         # 181.19 (low)
    D = C + 1.686 * (B - C)         # 207.75 (high)
    return [(0, X), (2, A), (4, B), (6, C), (8, D)]


def test_bullish_cypher_from_screenshot_ratios():
    m = detect_harmonic(_prices_bull_cypher())
    assert m is not None
    assert m.pattern == "CYPHER"
    assert m.direction == "bullish"


def test_bearish_butterfly_from_screenshot_ratios():
    m = detect_harmonic(_prices_bear_butterfly())
    assert m is not None
    assert m.pattern == "BUTTERFLY"
    assert m.direction == "bearish"


def test_random_pivots_are_not_a_pattern():
    # No harmonic geometry -> no classification.
    m = detect_harmonic([(0, 100.0), (2, 101.0), (4, 100.5), (6, 130.0), (8, 60.0)])
    assert m is None


def test_butterfly_ratios_do_not_misclassify_as_bat():
    # Butterfly AB/XA ~0.786 must NOT be read as a Bat (AB/XA 0.382-0.5).
    m = detect_harmonic(_prices_bear_butterfly())
    assert m.pattern != "BAT"


def test_pattern_report_has_tradingview_box_fields():
    from ta_engine.harmonics import detect_harmonic, pattern_report
    rep = pattern_report(detect_harmonic(_prices_bull_cypher()))
    assert rep["pattern"] == "CYPHER"
    assert rep["direction"] == "bullish"
    assert rep["pivot_labels"] == ["X", "A", "B", "C", "D"]
    assert len(rep["pivot_idx"]) == 5
    # TradingView info-box: ratios table with theoretical windows + a 0-100 score
    assert any(r["name"] == "AB/XA" for r in rep["ratios_table"])
    assert all({"name", "actual", "pct_err", "theoretical"} <= set(r) for r in rep["ratios_table"])
    assert 0 <= rep["score"] <= 100
    # bullish: targets above entry, stop below entry
    assert rep["target1"] > rep["entry"] > rep["stop"]


def test_scan_patterns_returns_reports_sorted_recent_first():
    from ta_engine.harmonics import scan_patterns
    # Build a series with a clean bullish Cypher near the end via explicit pivots is
    # fiddly; instead assert the API shape + recency ordering on any finds.
    import math
    # a gently oscillating series (may or may not contain patterns) — shape check only
    series = [100 + 8 * math.sin(i / 3.0) + i * 0.05 for i in range(120)]
    out = scan_patterns(series, series, depth=3)
    assert isinstance(out, list)
    idxs = [r["pivot_idx"][-1] for r in out]
    assert idxs == sorted(idxs, reverse=True)   # recency-desc
    for r in out:
        assert r["found"] is True and len(r["pivot_idx"]) == 5


def test_detect_forming_bat_from_tradingview_pivots():
    # TradingView Bearish Bat X-A-B-C (D projected). Exact pivots pulled from the chart.
    from ta_engine.harmonics import detect_forming
    m = detect_forming([(0, 190.9), (2, 180.35), (4, 186.0), (6, 181.5)])
    assert m is not None
    assert m.pattern == "BAT"          # priority order picks Bat over Crab for AB/XA~0.536
    assert m.direction == "bearish"
    assert len(m.pivots) == 5          # projected D appended
    assert m.pivots[4][1] > 186        # bearish D projected above C
