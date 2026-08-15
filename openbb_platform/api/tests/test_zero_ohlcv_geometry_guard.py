"""Zero/malformed-OHLCV containment: ATR hardening, geometry gate, classify().

Regression cover for the Swedish-fund defect found 2026-08-08. A NAV-only
provider row (`0P...ST` family) arrives as high=low=0.0 with a VALID close.
The true range then collapses to max(0, |0-c|, |0-c|) = c, so ATR converges on
the asset price, `stop = entry - 1.5*ATR` goes NEGATIVE, and a zero low later
satisfies `lo <= stop` and manufactures a first-bar LOSS.

Three containment layers are asserted here:
  A  _atr()        - skips structurally invalid bars, refuses rather than guesses
  B  score_setup() - geometry gate 0 < stop < entry < target before emission
  C  classify()    - a zero/invalid future bar is never read as a barrier touch

Every series is synthetic and deterministic. No network, no ledger access.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.setup_ledger import classify  # noqa: E402
from api.setup_scanner import ATR_PERIOD, _atr, score_setup  # noqa: E402

# Pre-change baselines, captured from the ORIGINAL _atr() before hardening.
# These pin numerical compatibility: hardening must not move a clean result.
CLEAN_120_ATR = 2.155284936293689
CLEAN_60_ATR = 2.0565780390656556
NAV_EQUAL_ATR = 0.19438881698477875


def clean_closes(n=120):
    """Deterministic drifting-with-oscillation close series."""
    return [100.0 * (1.0008 ** i) * (1 + 0.02 * math.sin(i / 9.7)) for i in range(n)]


def clean_ohlc(n=120):
    closes = clean_closes(n)
    return [c * 1.01 for c in closes], [c * 0.99 for c in closes], closes


def trend_series(n=700, drift=0.0008, amp=0.02):
    """Matches the house style in test_setup_scanner.py (clean uptrend)."""
    closes, p = [], 100.0
    for i in range(n):
        p *= (1 + drift)
        closes.append(p * (1 + amp * math.sin(i / 9.7)))
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    return closes, highs, lows


# ── A. _atr() hardening ──────────────────────────────────────────────────────

def test_all_zero_high_low_window_returns_none():
    """1. The exact fund shape: h=l=0 with valid closes must yield no ATR."""
    closes = clean_closes()
    zeros = [0.0] * len(closes)
    assert _atr(zeros, zeros, closes) is None


def test_zero_high_low_no_longer_inflates_atr_to_price():
    """The pre-fix behaviour (ATR ~= price) must not be reproducible."""
    closes = clean_closes()
    zeros = [0.0] * len(closes)
    atr = _atr(zeros, zeros, closes)
    # Refused outright; and had it returned, it must never approach the price.
    assert atr is None or atr < 0.5 * closes[-1]


def test_mixed_malformed_window_below_period_returns_none():
    """2. Fewer than `period` valid observations in the window -> None."""
    highs, lows, closes = clean_ohlc()
    # Corrupt exactly one bar inside the trailing ATR window.
    idx = len(closes) - 3
    highs[idx] = 0.0
    lows[idx] = 0.0
    assert _atr(highs, lows, closes) is None


def test_none_non_numeric_and_non_finite_do_not_crash():
    """3. None / str / NaN / inf are refused, never raised on."""
    highs, lows, closes = clean_ohlc()
    for bad in (None, "n/a", float("nan"), float("inf"), float("-inf"), object()):
        h = list(highs)
        h[len(h) - 2] = bad
        assert _atr(h, lows, closes) is None          # no TypeError escapes
    # A non-numeric PREVIOUS CLOSE is equally refused.
    c = list(closes)
    c[len(c) - 5] = "oops"
    assert _atr(highs, lows, c) is None


def test_boolean_is_not_accepted_as_a_price():
    """float(True) == 1.0 must not silently become a traded price."""
    highs, lows, closes = clean_ohlc()
    h = list(highs)
    h[len(h) - 2] = True
    assert _atr(h, lows, closes) is None


def test_high_below_low_is_rejected():
    """4. An inverted bar is structurally impossible -> refused."""
    highs, lows, closes = clean_ohlc()
    idx = len(closes) - 4
    highs[idx], lows[idx] = lows[idx], highs[idx]     # high < low
    assert _atr(highs, lows, closes) is None


def test_negative_and_zero_previous_close_rejected():
    highs, lows, closes = clean_ohlc()
    c = list(closes)
    c[len(c) - 6] = 0.0
    assert _atr(highs, lows, c) is None
    c[len(c) - 6] = -12.5
    assert _atr(highs, lows, c) is None


def test_clean_atr_matches_pre_change_expected_result():
    """5. Numerical compatibility: clean series are byte-for-byte unchanged."""
    highs, lows, closes = clean_ohlc(120)
    assert _atr(highs, lows, closes) == CLEAN_120_ATR
    assert _atr(highs[:60], lows[:60], closes[:60]) == CLEAN_60_ATR
    # Legitimate NAV shape (o=h=l=c, per DataPoint's documented contract)
    # stays fully supported - only h=l=0 is refused.
    assert _atr(closes, closes, closes) == NAV_EQUAL_ATR
    # Too-short input still returns None, as before.
    assert _atr(highs[:10], lows[:10], closes[:10]) is None


def test_exactly_period_valid_bars_is_sufficient():
    """The gate requires a FULL period, and accepts exactly that."""
    highs, lows, closes = clean_ohlc(ATR_PERIOD + 1)
    assert _atr(highs, lows, closes) is not None


# ── B. geometry gate in score_setup() ────────────────────────────────────────

def test_fund_like_zero_high_low_series_is_refused():
    """6. A fund-shaped series (h=l=0, valid close) emits no setup at all."""
    closes, _, _ = trend_series()
    zeros = [0.0] * len(closes)
    assert score_setup("0PTEST.ST", "Swedish", closes, zeros, zeros,
                       asset_class="fund") is None


def test_xain_shape_regression_fixture_is_refused():
    """7. The cached 0P0000XAIN.ST shape must not reproduce a negative stop.

    Live ledger row 2026-08-06 recorded entry=684.25 / stop=-328.49, i.e. an
    implied ATR of 675.16 against a 684.25 price (98.7%). Reconstructed here
    from the same structure: NAV-scale closes with zeroed high/low."""
    closes = [650.0 * (1.0004 ** i) * (1 + 0.01 * math.sin(i / 11.0))
              for i in range(700)]
    zeros = [0.0] * len(closes)
    result = score_setup("0P0000XAIN.ST", "Swedish", closes, zeros, zeros,
                         asset_class="fund", name="Fund NAV regression")
    assert result is None, "negative-stop geometry must never be emitted"


def test_clean_trending_setup_remains_compatible():
    """8. The hardening must not suppress a valid setup."""
    closes, highs, lows = trend_series()
    result = score_setup("TEST.ST", "Swedish", closes, highs, lows,
                         name="Test AB")
    assert result is not None
    assert result["entry"] > 0


def test_every_emitted_setup_satisfies_strict_level_ordering():
    """9. 0 < stop < entry < target holds for every setup that is emitted."""
    emitted = 0
    for drift, amp, label in ((0.0008, 0.02, "steady"),
                              (0.0015, 0.035, "fast"),
                              (0.0003, 0.010, "slow")):
        closes, highs, lows = trend_series(drift=drift, amp=amp)
        for asset_class in ("equity", "etf", "fund", "crypto"):
            r = score_setup(f"{label}-{asset_class}", "International",
                            closes, highs, lows, asset_class=asset_class)
            if r is None:
                continue
            emitted += 1
            entry, stop, target = r["entry"], r["stop"], r["target"]
            assert all(math.isfinite(v) for v in (entry, stop, target))
            assert 0.0 < stop < entry < target, (label, asset_class,
                                                 entry, stop, target)
    assert emitted > 0, "fixture produced no setups; the assertion was vacuous"


# ── C. classify() barrier hardening ──────────────────────────────────────────

def test_zero_low_future_bar_does_not_classify_loss():
    """10. A zero low is finite but not a price - it must not trigger a stop."""
    entry, stop, target = 100.0, 90.0, 120.0
    outcome, bars = classify(entry, stop, target,
                             fut_highs=[0.0, 0.0, 0.0],
                             fut_lows=[0.0, 0.0, 0.0],
                             horizon=3)
    assert outcome == "EXPIRED"
    assert bars is None


def test_invalid_bar_is_skipped_then_real_bar_still_resolves():
    """A malformed bar delays resolution; it never fabricates or hides one."""
    entry, stop, target = 100.0, 90.0, 120.0
    outcome, bars = classify(entry, stop, target,
                             fut_highs=[0.0, None, "x", 121.0],
                             fut_lows=[0.0, None, "x", 118.0],
                             horizon=4)
    assert outcome == "WIN"
    assert bars == 4


def test_non_numeric_future_bar_does_not_raise():
    entry, stop, target = 100.0, 90.0, 120.0
    for bad in (None, "n/a", float("nan"), float("inf"), object(), True):
        outcome, _ = classify(entry, stop, target,
                              fut_highs=[bad], fut_lows=[bad], horizon=1)
        assert outcome == "EXPIRED"


def test_inverted_future_bar_is_skipped():
    entry, stop, target = 100.0, 90.0, 120.0
    outcome, _ = classify(entry, stop, target,
                          fut_highs=[95.0], fut_lows=[110.0],  # high < low
                          horizon=1)
    assert outcome == "EXPIRED"


def test_genuine_stop_hit_still_classifies_loss():
    """11. Real downside must still register."""
    outcome, bars = classify(100.0, 90.0, 120.0,
                             fut_highs=[101.0, 99.0],
                             fut_lows=[97.0, 89.5],
                             horizon=5)
    assert outcome == "LOSS"
    assert bars == 2


def test_genuine_target_hit_still_classifies_win():
    """12. Real upside must still register."""
    outcome, bars = classify(100.0, 90.0, 120.0,
                             fut_highs=[105.0, 121.0],
                             fut_lows=[99.0, 110.0],
                             horizon=5)
    assert outcome == "WIN"
    assert bars == 2


def test_same_bar_straddle_is_still_ambiguous():
    """The pre-existing AMBIGUOUS rule is untouched by the hardening."""
    outcome, bars = classify(100.0, 90.0, 120.0,
                             fut_highs=[125.0], fut_lows=[85.0], horizon=5)
    assert outcome == "AMBIGUOUS"
    assert bars == 1
