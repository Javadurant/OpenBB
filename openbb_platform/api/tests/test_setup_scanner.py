"""Tests for the Setup Scanner v3 engine (Investor AB / INVE-B.ST regression).

Covers: mandatory v3 output fields, timing-window ordering, tax-note isolation
from scoring, data-quality penalties, harmonic/Elliott conflict penalties,
stale-signal handling, classification honesty, gold/oil universe presence with
proxy labelling, Ichimoku timing constants, and banned overconfident wording.
No network: all series are synthetic.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.setup_scanner import (  # noqa: E402
    CLASSIFICATIONS, KIJUN_TIME_NUMBERS, SPECIAL_TIME_NUMBERS,
    TENKAN_TIME_NUMBERS, score_setup, zigzag_pivots, _classify,
    MONTHLY_RSI_OVERSOLD, PULLBACK_ATR_MULT,
)

BANNED_WORDS = ("guaranteed", "risk-free", "cannot fail", "must buy", "100%")


def trend_series(n=700, drift=0.0008, amp=0.02):
    closes, p = [], 100.0
    for i in range(n):
        p *= (1 + drift)
        closes.append(p * (1 + amp * math.sin(i / 9.7)))
    highs = [c * 1.008 for c in closes]
    lows = [c * 0.992 for c in closes]
    return closes, highs, lows


def test_v3_fields_present_and_ordered():
    closes, highs, lows = trend_series()
    r = score_setup("TEST.ST", "Swedish", closes, highs, lows, name="Test AB")
    assert r is not None
    for field in ("classification", "setup_type", "confidence", "risk_level",
                  "invalidation", "sub_scores", "penalties", "conflicts",
                  "supports", "strongest_supporting", "strongest_opposing",
                  "expected_target_date", "expected_target_time",
                  "earliest_target_date", "base_case_target_date",
                  "latest_target_date", "min_trading_days",
                  "expected_trading_days", "max_trading_days",
                  "timing_confidence", "timing_reliability", "timing_reasoning",
                  "timing_confluence_sources", "data_quality", "debug",
                  "time_window_days", "grade", "entry", "stop", "target"):
        assert field in r, f"missing v3 field: {field}"
    assert r["min_trading_days"] <= r["expected_trading_days"] <= r["max_trading_days"]
    assert r["earliest_target_date"] <= r["base_case_target_date"] <= r["latest_target_date"]
    assert r["classification"] in CLASSIFICATIONS
    assert r["invalidation"] == r["stop"]
    assert "market close" in r["expected_target_time"]  # daily data: EOD estimate only


def test_tax_note_never_affects_score():
    closes, highs, lows = trend_series()
    r0 = score_setup("A", "International", closes, highs, lows, dividend_yield=0.0)
    r5 = score_setup("A", "International", closes, highs, lows, dividend_yield=5.0)
    assert r0["score"] == r5["score"]
    assert r0["grade"] == r5["grade"]
    assert r0["classification"] == r5["classification"]
    assert r0["isk_kf_note"] != r5["isk_kf_note"]  # note DOES change - display only


def test_short_history_is_data_limited():
    closes, highs, lows = trend_series(n=200)
    r = score_setup("THIN.ST", "Swedish", closes, highs, lows)
    assert r is not None
    assert r["data_quality"]["monthly_rsi_available"] is False
    assert r["penalties"]["data_quality_penalty"] > 0


def test_bearish_harmonic_near_price_penalises():
    closes, highs, lows = trend_series()
    price = closes[-1]
    ctx = {"harmonics": [{"name": "BUTTERFLY", "bullish": False,
                          "d_price": price * 0.995, "age_bars": 5}]}
    plain = score_setup("X", "Swedish", closes, highs, lows)
    penal = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert penal["score"] < plain["score"]
    assert any("BUTTERFLY" in c for c in penal["conflicts"])
    assert penal["technical_context_used"] is True


def test_bullish_prz_far_below_is_not_support():
    closes, highs, lows = trend_series()
    price = closes[-1]
    ctx = {"harmonics": [{"name": "GARTLEY", "bullish": True,
                          "d_price": price * 0.80, "age_bars": 10}]}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert not any("GARTLEY" in s for s in r["supports"])
    assert r["penalties"]["stale_signal_penalty"] > 0  # counted stale/irrelevant


def test_elliott_complete_is_a_conflict():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {"structure": "ZIGZAG", "status": "COMPLETE"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("Elliott" in c and "COMPLETE" in c for c in r["conflicts"])


def test_daily_rsi_585_is_not_treated_as_oversold():
    """The Investor AB case: daily RSI ~58.5 must not create a reversal label."""
    closes, highs, lows = trend_series()
    r = score_setup("INVE-B.ST", "Swedish", closes, highs, lows)
    assert r["classification"] != "Reversal Buy Setup" or (
        r["monthly_rsi"] is not None and r["monthly_rsi"] <= MONTHLY_RSI_OVERSOLD)


def test_classify_oversold_reversal_branch():
    cls, typ, risk = _classify(
        aligned=1, extended_atr=0.5, monthly_rsi=28.0, long_term_up=True,
        above_ma100=True, n_conflicts=0, data_limited=False, grade="B",
        breakout=False, ichi=None, boll=None)
    assert cls == "Reversal Buy Setup"
    assert "Oversold" in typ


def test_classify_conflicted_branch():
    cls, typ, risk = _classify(
        aligned=3, extended_atr=0.5, monthly_rsi=50.0, long_term_up=True,
        above_ma100=True, n_conflicts=4, data_limited=False, grade="B",
        breakout=False, ichi=None, boll=None)
    assert cls == "Conflicted Buy Setup"
    assert risk == "High"


def test_no_banned_wording():
    closes, highs, lows = trend_series()
    r = score_setup("X", "Swedish", closes, highs, lows)
    text = (r["why"] + r["strongest_supporting"] + r["strongest_opposing"]).lower()
    for w in BANNED_WORDS:
        assert w not in text, f"banned word in copy: {w}"


def test_zigzag_alternates():
    n = 300
    closes = [100 + 10 * math.sin(i / 12.0) for i in range(n)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    piv = zigzag_pivots(highs, lows, atr=1.0)
    assert len(piv) >= 4
    assert all(piv[i][0] < piv[i + 1][0] for i in range(len(piv) - 1))


def test_ichimoku_time_numbers_configured():
    assert 9 in TENKAN_TIME_NUMBERS and 405 in TENKAN_TIME_NUMBERS
    assert 26 in KIJUN_TIME_NUMBERS and 545 in KIJUN_TIME_NUMBERS
    assert SPECIAL_TIME_NUMBERS == (35, 52, 442)
    assert 26 * 17 == 442


def test_universe_has_gold_and_oil_with_proxy_labels():
    from api.phase2_router import SETUP_UNIVERSE, _PROXY_META
    for region in ("Swedish", "International"):
        for ac in ("gold", "oil"):
            syms = [s for s, r, a in SETUP_UNIVERSE if r == region and a == ac]
            assert syms, f"no {region} {ac} instruments in universe"
            for s in syms:
                assert s in _PROXY_META, f"{s} lacks an honest proxy label"


def test_pullback_scores_higher_than_extended():
    closes, highs, lows = trend_series()
    base = score_setup("X", "Swedish", closes, highs, lows)
    # push last close far above the 20d mean -> extended, entry_zone must drop
    ext_closes = closes[:-1] + [closes[-1] * 1.25]
    ext_highs = highs[:-1] + [ext_closes[-1] * 1.008]
    ext_lows = lows[:-1] + [ext_closes[-1] * 0.992]
    ext = score_setup("X", "Swedish", ext_closes, ext_highs, ext_lows)
    assert ext["sub_scores"]["entry_zone"] <= base["sub_scores"]["entry_zone"]
