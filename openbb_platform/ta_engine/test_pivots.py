"""
Tests for the TradingView-style pivot-lookback ZigZag.

TradingView harmonic indicators detect swings with ta.pivothigh(depth)/pivotlow(depth):
a bar is a pivot high if its high is the maximum within `depth` bars on each side
(pivot low symmetric on lows). This is far finer than a percentage ZigZag and is the
pivot method our harmonic detectors must consume to reach parity with the chart.
"""
from ta_engine.pivots import pivot_zigzag


def test_pivot_zigzag_finds_confirmed_alternating_pivots():
    # depth=2: a pivot needs 2 higher/lower bars on BOTH sides (so bars within 2 of an
    # end can't be confirmed). Series has a high at idx2 (12), a low at idx5 (9), a
    # high at idx7 (13).
    series = [10, 11, 12, 11, 10, 9, 10, 13, 12, 11, 10]
    swings = pivot_zigzag(series, series, depth=2)
    assert [i for i, _ in swings] == [2, 5, 7]
    assert [round(p, 2) for _, p in swings] == [12.0, 9.0, 13.0]


def test_pivot_zigzag_collapses_consecutive_same_direction_pivots():
    # Two rising highs with no intervening low: keep only the more extreme high.
    # highs peak at idx2 (12) then idx6 (15); the dip at idx4 (11) is not low enough
    # to register as a pivot low within depth=2 -> two consecutive highs -> keep idx6.
    series = [10, 11, 12, 11, 12, 14, 15, 14, 13, 12, 11]
    swings = pivot_zigzag(series, series, depth=2)
    # only alternating extremes survive; the final swing is the dominant high (idx6=15)
    assert swings[-1][0] == 6
    assert round(swings[-1][1], 2) == 15.0
    # no two consecutive pivots share direction (strictly alternating by price)
    prices = [p for _, p in swings]
    for a, b in zip(prices, prices[1:]):
        assert a != b
