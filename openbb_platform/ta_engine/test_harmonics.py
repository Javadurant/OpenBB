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
