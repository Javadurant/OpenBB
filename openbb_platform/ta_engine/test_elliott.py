"""
Tests for the rule-gated Elliott Wave engine.

Every rule assertion is sourced to the user's verified reference:
  "ELLIOTT WAVE VERIFIED REFERENCE" -> Frost & Prechter, Elliott Wave Principle (10th Ed.)
Rule citations [PF] Ch.2 p.21 are reproduced in elliott.py docstrings.

Pivots model the 6 turning points of a 5-wave impulse:
  p0 = start of Wave 1, p1 = end W1, p2 = end W2, p3 = end W3, p4 = end W4, p5 = end W5.
"""
from ta_engine.elliott import Pivot, classify_impulse, classify, analyze


def test_rule1_violation_wave2_full_retrace_is_invalid():
    # Bullish impulse. Wave1 = 100 -> 120. Wave2 retraces all the way to 100
    # (== Wave1 start) => 100% retracement => RULE_1 violation ([PF] p.21).
    pivots = [
        Pivot(0, 100.0),  # start W1
        Pivot(1, 120.0),  # end W1
        Pivot(2, 100.0),  # end W2  -- 100% retrace of W1 -> INVALID
        Pivot(3, 150.0),  # end W3
        Pivot(4, 135.0),  # end W4
        Pivot(5, 175.0),  # end W5
    ]
    result = classify_impulse(pivots)
    assert result.structure == "INVALID"
    assert "RULE_1" in result.failed_rules


def test_rule2_violation_wave3_is_shortest_by_length_is_invalid():
    # Lengths: W1=40, W3=35, W5=58 -> W3 is the shortest motive wave => RULE_2.
    # Rule 1 ok (110 > 100). Rule 3 ok (W4 low 142 > W1 high 140).
    # Per reference: measure by LENGTH (price distance), not endpoint price.
    pivots = [
        Pivot(0, 100.0),  # start W1
        Pivot(1, 140.0),  # end W1   len 40
        Pivot(2, 110.0),  # end W2
        Pivot(3, 145.0),  # end W3   len 35  (shortest)
        Pivot(4, 142.0),  # end W4
        Pivot(5, 200.0),  # end W5   len 58
    ]
    result = classify_impulse(pivots)
    assert result.structure == "INVALID"
    assert "RULE_2" in result.failed_rules


def test_rule3_violation_wave4_overlaps_wave1_is_invalid():
    # Bullish. W4 low (125) enters W1 territory (W1 high 130) => RULE_3 ([PF] p.21).
    # Rule 1 ok (112 > 100). Rule 2 ok (W1=30, W3=63, W5=60 -> W3 not shortest).
    pivots = [
        Pivot(0, 100.0),  # start W1
        Pivot(1, 130.0),  # end W1   len 30
        Pivot(2, 112.0),  # end W2
        Pivot(3, 175.0),  # end W3   len 63
        Pivot(4, 125.0),  # end W4   overlaps W1 high (130)
        Pivot(5, 185.0),  # end W5   len 60
    ]
    result = classify_impulse(pivots)
    assert result.structure == "INVALID"
    assert "RULE_3" in result.failed_rules


def test_valid_textbook_bullish_impulse_passes_all_rules():
    # Clean impulse: every rule satisfied, no overlap, W3 longest.
    pivots = [
        Pivot(0, 100.0),  # start W1
        Pivot(1, 120.0),  # end W1   len 20
        Pivot(2, 110.0),  # end W2   (50% retrace)
        Pivot(3, 160.0),  # end W3   len 50  (longest)
        Pivot(4, 140.0),  # end W4   (no overlap: 140 > 120)
        Pivot(5, 180.0),  # end W5   len 40
    ]
    result = classify_impulse(pivots)
    assert result.structure == "IMPULSE"
    assert result.failed_rules == []
    assert result.direction == "bullish"


def test_valid_textbook_bearish_impulse_passes_all_rules():
    # Mirror of the bullish case (prices descending).
    pivots = [
        Pivot(0, 200.0),  # start W1
        Pivot(1, 180.0),  # end W1   len 20
        Pivot(2, 190.0),  # end W2
        Pivot(3, 140.0),  # end W3   len 50 (longest)
        Pivot(4, 160.0),  # end W4   (no overlap: 160 < 180)
        Pivot(5, 120.0),  # end W5   len 40
    ]
    result = classify_impulse(pivots)
    assert result.structure == "IMPULSE"
    assert result.failed_rules == []
    assert result.direction == "bearish"


def test_valid_impulse_reports_invalidation_at_wave1_origin():
    # E4: every count carries an invalidation price. For a 5-wave impulse the
    # structural invalidation is the Wave 1 origin (p0): a full retrace through
    # it negates the count (direct consequence of RULE_1).
    pivots = [
        Pivot(0, 100.0), Pivot(1, 120.0), Pivot(2, 110.0),
        Pivot(3, 160.0), Pivot(4, 140.0), Pivot(5, 180.0),
    ]
    result = classify_impulse(pivots)
    assert result.invalidation == 100.0


def test_overlap_with_contracting_wedge_is_diagonal_not_invalid():
    # E3: W4 overlaps W1 (140 <= 150) -> strict impulse RULE_3 violation, BUT the
    # motive waves contract (W1=50 > W3=45 > W5=35): a converging wedge. Per the
    # reference, overlap is PERMITTED in a diagonal. classify() must rescue it.
    pivots = [
        Pivot(0, 100.0),  # start W1
        Pivot(1, 150.0),  # end W1   len 50
        Pivot(2, 115.0),  # end W2
        Pivot(3, 160.0),  # end W3   len 45
        Pivot(4, 140.0),  # end W4   overlaps W1 high (150)
        Pivot(5, 175.0),  # end W5   len 35
    ]
    result = classify(pivots)
    assert result.is_diagonal is True
    assert result.structure == "DIAGONAL"
    # Overlap is permitted in diagonals -> RULE_3 must NOT remain a fatal failure.
    assert "RULE_3" not in result.failed_rules


def test_overlap_without_wedge_stays_invalid():
    # Overlap but NOT contracting (W3 is the longest, expansion) -> no diagonal
    # rescue; remains INVALID with RULE_3 logged.
    pivots = [
        Pivot(0, 100.0),
        Pivot(1, 130.0),  # W1 len 30
        Pivot(2, 112.0),
        Pivot(3, 175.0),  # W3 len 63 (longest -> not a contracting wedge)
        Pivot(4, 125.0),  # overlaps W1 high (130)
        Pivot(5, 185.0),  # W5 len 60
    ]
    result = classify(pivots)
    assert result.is_diagonal is False
    assert result.structure == "INVALID"
    assert "RULE_3" in result.failed_rules


def test_classify_passes_through_clean_impulse():
    pivots = [
        Pivot(0, 100.0), Pivot(1, 120.0), Pivot(2, 110.0),
        Pivot(3, 160.0), Pivot(4, 140.0), Pivot(5, 180.0),
    ]
    result = classify(pivots)
    assert result.structure == "IMPULSE"
    assert result.is_diagonal is False


def test_monotonic_pivots_are_not_an_impulse():
    # A strictly rising staircase has no corrective waves -> not an impulse shape.
    pivots = [Pivot(i, 100.0 + i * 10) for i in range(6)]  # 100,110,...,150
    result = classify_impulse(pivots)
    assert result.structure == "INVALID"
    assert "SHAPE" in result.failed_rules


def test_wave3_must_exceed_wave1_extreme():
    # Bullish: W3 fails to make a new high above W1 end -> not an impulse shape.
    pivots = [
        Pivot(0, 100.0), Pivot(1, 130.0), Pivot(2, 115.0),
        Pivot(3, 125.0),  # W3 high 125 < W1 high 130 -> SHAPE fail
        Pivot(4, 118.0), Pivot(5, 140.0),
    ]
    result = classify_impulse(pivots)
    assert "SHAPE" in result.failed_rules


def test_analyze_finds_impulse_in_longer_swing_series():
    # E1: a 5-wave impulse occupies pivots 2..7 of an 8-pivot series; the legacy
    # last-4-legs window would miss it. analyze() scans every window and finds it.
    swings = [
        (0, 90.0), (1, 95.0),                 # leading noise (corrective legs)
        (2, 100.0),                            # start W1
        (3, 120.0), (4, 110.0),
        (5, 160.0), (6, 140.0), (7, 180.0),    # ... end W5
    ]
    analysis = analyze(swings)
    assert analysis.preferred is not None
    assert analysis.preferred.structure == "IMPULSE"
    assert analysis.preferred.pivots[0].index == 2
    assert analysis.preferred.pivots[-1].index == 7


def test_analyze_returns_empty_when_no_valid_count():
    # Pure descending staircase: no valid impulse window anywhere.
    swings = [(i, 100.0 - i) for i in range(8)]
    analysis = analyze(swings)
    assert analysis.preferred is None
    assert analysis.counts == []


def test_analyze_prefers_most_recent_of_multiple_counts():
    # Two clean impulses back-to-back; the later one is preferred, the earlier is
    # surfaced as an alternate (recency tie-break).
    swings = [
        (0, 100.0), (1, 120.0), (2, 110.0), (3, 160.0), (4, 140.0), (5, 180.0),
        (6, 150.0), (7, 200.0), (8, 175.0), (9, 260.0), (10, 230.0), (11, 300.0),
    ]
    analysis = analyze(swings)
    assert analysis.preferred is not None
    assert analysis.preferred.pivots[-1].index == 11
    assert len(analysis.alternates) >= 1
    assert analysis.alternates[0].pivots[-1].index < 11
