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


# ── Elliott adapter (direction-aware) ────────────────────────────────────────

def test_elliott_bearish_in_progress_is_conflict():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "IN_PROGRESS",
        "direction": "BEARISH", "current_wave": "Wave 3"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("bearish IMPULSE" in c for c in r["conflicts"])


def test_elliott_bearish_complete_is_support_not_conflict():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "ZIGZAG", "status": "COMPLETE",
        "direction": "BEARISH", "current_wave": "Wave C"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("downside structure exhausted" in s for s in r["supports"])
    assert not any("Elliott" in c for c in r["conflicts"])


def test_elliott_bullish_complete_is_conflict():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "COMPLETE",
        "direction": "BULLISH", "current_wave": "Wave 5"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("upside structure exhausted" in c for c in r["conflicts"])


def test_elliott_bullish_wave3_is_support():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "IN_PROGRESS",
        "direction": "BULLISH", "current_wave": "Wave 3"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("bullish IMPULSE in progress" in s for s in r["supports"])


def test_elliott_wave5_late_stage_is_caution():
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "IN_PROGRESS",
        "direction": "BULLISH", "current_wave": "Wave 5"}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    assert any("late-stage" in c for c in r["conflicts"])


def test_build_technical_context_includes_elliott_when_engine_present():
    """Live adapter test: runs the real computed Elliott engine if importable."""
    import importlib.util
    if importlib.util.find_spec("engine.structure.elliott_wave") is None:
        return  # engine not on path in this environment - adapter degrades to None
    from api.setup_scanner import build_technical_context, _atr
    closes, highs, lows = trend_series(n=400, amp=0.06)
    atr = _atr(highs, lows, closes)
    ctx = build_technical_context(highs, lows, closes, atr, symbol="TEST")
    assert ctx is not None and "harmonics" in ctx
    if "elliott" in ctx:  # engine may honestly return no valid count
        for k in ("structure", "status", "direction", "invalidation"):
            assert k in ctx["elliott"]


# ── Ledger-based timing calibration ──────────────────────────────────────────

def test_calibration_scales_expected_days():
    closes, highs, lows = trend_series()
    plain = score_setup("X", "Swedish", closes, highs, lows)
    calib = {"reliable": True, "speed_factor": 0.5, "n_samples": 100,
             "median_abs_pct_error": 0.4}
    fast = score_setup("X", "Swedish", closes, highs, lows, calibration=calib)
    assert fast["expected_trading_days"] <= plain["expected_trading_days"]
    assert fast["historical_calibration_error"] == 0.4
    assert fast["min_trading_days"] <= fast["expected_trading_days"] <= fast["max_trading_days"]
    assert "ledger calibration" in fast["timing_reasoning"]


def test_unreliable_calibration_is_ignored():
    closes, highs, lows = trend_series()
    calib = {"reliable": False, "speed_factor": 0.5, "n_samples": 2}
    r = score_setup("X", "Swedish", closes, highs, lows, calibration=calib)
    plain = score_setup("X", "Swedish", closes, highs, lows)
    assert r["expected_trading_days"] == plain["expected_trading_days"]
    assert r["historical_calibration_error"] is None


def test_timing_calibration_math(monkeypatch):
    from api import setup_ledger as sl
    fake = [
        {"outcome": "WIN", "bars_to_resolve": 6, "window_days": 24, "grade": "A"},
        {"outcome": "WIN", "bars_to_resolve": 3, "window_days": 18, "grade": "A"},
        {"outcome": "WIN", "bars_to_resolve": 9, "window_days": 18, "grade": "B"},
        {"outcome": "WIN", "bars_to_resolve": 12, "window_days": 24, "grade": "B"},
        {"outcome": "WIN", "bars_to_resolve": 5, "window_days": 20, "grade": "C"},
        {"outcome": "WIN", "bars_to_resolve": 4, "window_days": 16, "grade": "C"},
        {"outcome": "LOSS", "bars_to_resolve": 2, "window_days": 18, "grade": "A"},
        # v3-style record with explicit expected_days
        {"outcome": "WIN", "bars_to_resolve": 10, "expected_days": 10,
         "window_days": 20, "grade": "A"},
    ]
    monkeypatch.setattr(sl, "_read_all", lambda: fake)
    c = sl.timing_calibration()
    assert c["reliable"] is True
    assert c["n_samples"] == 7          # LOSS excluded
    assert 0.5 <= c["speed_factor"] <= 2.0
    assert c["median_abs_pct_error"] is not None
    assert "by_grade" in c and set(c["by_grade"]) == {"A", "B", "C"}


def test_timing_calibration_insufficient_data(monkeypatch):
    from api import setup_ledger as sl
    monkeypatch.setattr(sl, "_read_all", lambda: [
        {"outcome": "WIN", "bars_to_resolve": 6, "window_days": 24, "grade": "A"}])
    c = sl.timing_calibration()
    assert c["reliable"] is False
    assert c["speed_factor"] == 1.0


def test_ledger_logs_expected_days(tmp_path, monkeypatch):
    from api import setup_ledger as sl
    monkeypatch.setattr(sl, "_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    ok = sl.log_setup({
        "symbol": "TEST.ST", "grade": "B", "entry": 100.0, "stop": 95.0,
        "target": 110.0, "time_window_days": "5-20 trading days",
        "expected_trading_days": 10, "as_of": "2026-07-08"})
    assert ok
    rec = sl._read_all()[0]
    assert rec["expected_days"] == 10
    assert rec["window_days"] == 20


# ── Corporate-event gap risk (earnings / ex-dividend inside the window) ──────

def test_earnings_inside_window_flags_penalises_and_caps_reliability():
    from datetime import date, timedelta
    closes, highs, lows = trend_series()
    as_of = date(2026, 7, 8)
    ev = {"next_earnings_date": (as_of + timedelta(days=5)).isoformat()}
    r = score_setup("X", "Swedish", closes, highs, lows, as_of=as_of, event_context=ev)
    plain = score_setup("X", "Swedish", closes, highs, lows, as_of=as_of)
    assert r["events"]["earnings_in_window"] is True
    assert any("earnings report" in c for c in r["conflicts"])
    assert r["score"] < plain["score"]                      # conflict penalty applied
    assert r["timing_reliability"] != "high"                # never high across earnings
    assert "earnings inside the window" in r["timing_reasoning"]
    assert r["risk_level"] in ("Elevated", "High", "Moderate-High")


def test_earnings_far_outside_window_is_not_flagged():
    from datetime import date, timedelta
    closes, highs, lows = trend_series()
    as_of = date(2026, 7, 8)
    ev = {"next_earnings_date": (as_of + timedelta(days=400)).isoformat()}
    r = score_setup("X", "Swedish", closes, highs, lows, as_of=as_of, event_context=ev)
    plain = score_setup("X", "Swedish", closes, highs, lows, as_of=as_of)
    assert r["events"]["earnings_in_window"] is False
    assert not any("earnings report" in c for c in r["conflicts"])
    assert r["score"] == plain["score"]
    assert r["timing_reliability"] == plain["timing_reliability"]


def test_large_ex_dividend_inside_window_is_conflict():
    from datetime import date, timedelta
    from api.setup_scanner import _atr
    closes, highs, lows = trend_series()
    as_of = date(2026, 7, 8)
    atr = _atr(highs, lows, closes)
    ev = {"next_ex_dividend_date": (as_of + timedelta(days=4)).isoformat(),
          "dividend_amount": 1.0 * atr}           # a full ATR of mechanical drop
    r = score_setup("SWED-A.ST", "Swedish", closes, highs, lows,
                    as_of=as_of, event_context=ev)
    assert r["events"]["ex_dividend_in_window"] is True
    assert r["events"]["dividend_atr_ratio"] >= 0.5
    assert any("ex-dividend" in c for c in r["conflicts"])


def test_small_ex_dividend_is_informational_not_conflict():
    from datetime import date, timedelta
    from api.setup_scanner import _atr
    closes, highs, lows = trend_series()
    as_of = date(2026, 7, 8)
    atr = _atr(highs, lows, closes)
    ev = {"next_ex_dividend_date": (as_of + timedelta(days=4)).isoformat(),
          "dividend_amount": 0.05 * atr}          # tiny dividend: flag, don't punish
    r = score_setup("X", "Swedish", closes, highs, lows, as_of=as_of, event_context=ev)
    assert r["events"]["ex_dividend_in_window"] is True
    assert not any("ex-dividend" in c for c in r["conflicts"])


def test_garbage_event_dates_degrade_silently():
    closes, highs, lows = trend_series()
    ev = {"next_earnings_date": "not-a-date", "next_ex_dividend_date": None,
          "dividend_amount": float("nan")}
    r = score_setup("X", "Swedish", closes, highs, lows, event_context=ev)
    assert r is not None
    assert r["events"]["earnings_in_window"] is False
    assert r["events"]["ex_dividend_in_window"] is False


# ── v3.1: compliance matrix, Fib time tools, copper/silver, SKF regression ───

def test_compliance_matrix_present_and_honest():
    closes, highs, lows = trend_series()
    r = score_setup("X", "Swedish", closes, highs, lows)
    c = r["compliance"]
    # consulted components report True with real data
    for k in ("trend_daily_weekly_monthly", "daily_rsi", "monthly_rsi", "ma100",
              "ichimoku_state", "ichimoku_time_numbers", "macd", "bollinger",
              "atr", "fib_time_zones", "fib_circles",
              "tax_note_excluded_from_score"):
        assert c[k] is True, f"compliance[{k}] should be True"
    # components whose data was NOT provided must report honest False
    for k in ("volume", "fundamentals_in_score", "news_in_score",
              "market_regime_filter"):
        assert c[k] is False, f"compliance[{k}] must be honest False"
    # v3.2 structural components report whether they actually computed
    for k in ("andrews_pitchfork", "support_resistance_levels",
              "fib_price_clusters", "liquidity_screen"):
        assert k in c
    # context-dependent flags reflect what was passed
    assert c["harmonics_consulted"] is False
    r2 = score_setup("X", "Swedish", closes, highs, lows,
                     technical_context={"harmonics": []})
    assert r2["compliance"]["harmonics_consulted"] is True


def test_trend_based_fib_time_projection_math():
    from api.setup_scanner import _tbft_candidates
    # pivots A@0, B@20 (leg = 20 bars), C@40; today = bar 48
    piv = [(0, 100.0), (20, 120.0), (40, 105.0)]
    cands = dict(_tbft_candidates(piv, 48))
    assert cands[0.618] == 40 + round(0.618 * 20) - 48          # ~4 days ahead
    assert cands[1.0] == 12
    assert cands[1.618] == 40 + round(1.618 * 20) - 48          # ~24 days ahead
    # projections already in the past are dropped
    assert all(d > 0 for d in cands.values())
    assert _tbft_candidates(piv[:2], 48) == []                  # needs 3 pivots


def test_fib_circle_projection_math():
    from api.setup_scanner import _fib_circle_candidates
    # target 5 ATR above the pivot, pivot 20 bars ago
    cands = dict(_fib_circle_candidates(20, 5.0))
    for radius, d_ahead in cands.items():
        expected = round((radius ** 2 - 25) ** 0.5) - 20
        assert d_ahead == expected and d_ahead > 0
    # radius smaller than the price distance can never be reached
    assert 21 not in dict(_fib_circle_candidates(20, 25.0))


def test_timing_tools_checked_reported():
    closes, highs, lows = trend_series()
    r = score_setup("X", "Swedish", closes, highs, lows)
    tools = r["timing_tools_checked"]
    assert tools["fib_time_zones"] is True
    assert tools["fib_circles"] is True
    assert tools["ichimoku_time_numbers"] is True
    assert "trend_based_fib_time" in tools


def test_universe_has_copper_and_silver_with_proxy_labels():
    from api.phase2_router import SETUP_UNIVERSE, _PROXY_META
    for region in ("Swedish", "International"):
        for ac in ("copper", "silver"):
            syms = [s for s, r, a in SETUP_UNIVERSE if r == region and a == ac]
            assert syms, f"no {region} {ac} instruments in universe"
            for s in syms:
                assert s in _PROXY_META, f"{s} lacks an honest proxy label"


def test_chikou_and_flat_tenkan_surface_as_supports():
    closes, highs, lows = trend_series()
    r = score_setup("X", "Swedish", closes, highs, lows)
    ichi = r["debug"]["ichimoku"]
    if ichi and ichi["chikou_free"]:
        assert any("Chikou" in s for s in r["supports"])


def test_skf_regression_pullback_not_reversal():
    """SKF-B.ST audit case (2026-07-08): 3/3 timeframes up, pullback zone,
    monthly RSI ~70 (NOT oversold), earnings inside window. The engine must
    classify as continuation/pullback - never an oversold Reversal - keep the
    earnings conflict visible, and stay fully reproducible."""
    from datetime import date, timedelta
    closes, highs, lows = trend_series()          # sustained uptrend fixture
    as_of = date(2026, 7, 8)
    ev = {"next_earnings_date": (as_of + timedelta(days=9)).isoformat()}
    ctx = {"harmonics": [], "elliott": {
        "structure": "TRIANGLE_BARRIER", "status": "COMPLETE",
        "direction": "BEARISH", "current_wave": "Wave E"}}
    r1 = score_setup("SKF-B.ST", "Swedish", closes, highs, lows,
                     name="AB SKF (publ)", as_of=as_of,
                     technical_context=ctx, event_context=ev)
    r2 = score_setup("SKF-B.ST", "Swedish", closes, highs, lows,
                     name="AB SKF (publ)", as_of=as_of,
                     technical_context=ctx, event_context=ev)
    assert r1 == r2                                # reproducible from same data
    assert r1["classification"] != "Reversal Buy Setup"
    assert r1["monthly_rsi"] is None or r1["monthly_rsi"] > MONTHLY_RSI_OVERSOLD
    assert r1["events"]["earnings_in_window"] is True
    assert r1["timing_reliability"] != "high"
    assert any("downside structure exhausted" in s for s in r1["supports"])
    assert r1["risk_level"] in ("Elevated", "High", "Moderate-High")
    # full transparency: sub-scores + penalties + compliance always present
    assert r1["sub_scores"] and r1["penalties"] and r1["compliance"]


# ── v3.2: regime, volume, S/R, fib price, pitchfork, calendars, liquidity ────

def test_add_trading_days_skips_swedish_holidays():
    from datetime import date
    from api.setup_scanner import _add_trading_days, SWEDISH_HOLIDAYS
    # Good Friday 2026-04-03 and Easter Monday 2026-04-06 are skipped
    assert _add_trading_days(date(2026, 4, 1), 2, SWEDISH_HOLIDAYS) == date(2026, 4, 7)
    # crypto: plain calendar days, weekends included
    assert _add_trading_days(date(2026, 4, 1), 2, calendar_days=True) == date(2026, 4, 3)


def test_crypto_windows_use_calendar_days():
    from datetime import date, timedelta
    closes, highs, lows = trend_series()
    as_of = date(2026, 7, 10)   # a Friday
    r = score_setup("BTC-USD", "International", closes, highs, lows,
                    asset_class="crypto", as_of=as_of)
    exp = r["expected_trading_days"]
    assert r["base_case_target_date"] == (as_of + timedelta(days=exp)).isoformat()
    assert "24/7" in r["expected_target_time"]


def test_volume_state_math():
    from api.setup_scanner import _volume_state, W_VOLUME
    flat = [1000.0] * 30
    burst = flat[:-1] + [1600.0]                      # 1.6x the 20d average
    assert _volume_state(burst, breakout=True)["earned"] == W_VOLUME
    assert _volume_state([0.0] * 30, breakout=False) is None   # no data = None
    assert _volume_state(flat[:10], breakout=False) is None    # too short
    quiet = flat[:-1] + [500.0]
    assert _volume_state(quiet, breakout=False)["earned"] == 0.0


def test_support_resistance_math():
    from api.setup_scanner import _support_resistance, W_SR
    piv = [(0, 90.0), (10, 110.0), (20, 95.0), (30, 108.0)]
    # price 100, atr 2: support 95 (2.5 ATR below), resistance 108 (4 ATR above)
    sr = _support_resistance(piv, 100.0, 2.0, target=106.0)
    assert sr["support"] == 95.0 and sr["resistance"] == 108.0
    assert sr["earned"] == W_SR          # support near + clean air to target
    # resistance 1 ATR overhead, before target -> conflict, half score
    sr2 = _support_resistance(piv, 106.5, 2.0, target=112.0)
    assert sr2["conflict"] is not None and "resistance" in sr2["conflict"]


def test_fib_price_levels_math():
    from api.setup_scanner import _fib_price_levels
    piv = [(0, 100.0), (20, 120.0)]                  # up-leg 100 -> 120
    f = _fib_price_levels(piv, 115.0, 2.0, target=125.4)
    assert f["retracements"][0.5] == 110.0
    assert f["extensions"][1.272] == 125.44
    assert any("1.272" in n for n in f["notes"])     # target clusters with ext
    assert f["earned"] >= 2.0


def test_pitchfork_math_and_staleness():
    from api.setup_scanner import _pitchfork_state, W_PITCHFORK
    piv = [(0, 100.0), (20, 120.0), (40, 110.0)]
    # median line: from P0 through midpoint(30, 115) -> slope 0.5/bar
    pf = _pitchfork_state(piv, price=140.0, atr=2.0, last_idx=60)
    assert pf["stale"] is False and pf["rising"] is True
    assert pf["median"] == 130.0                     # 100 + 0.5 * 60
    assert pf["earned"] == W_PITCHFORK               # above rising median
    stale = _pitchfork_state([(0, 100.0), (20, 120.0), (40, 110.0)],
                             price=140.0, atr=2.0, last_idx=300)
    assert stale["stale"] is True and "earned" not in stale


def test_fundamentals_earned_supports_only():
    from api.setup_scanner import _fundamentals_earned, W_FUND
    full, notes = _fundamentals_earned({"revenue_growth": 0.08, "earnings_growth": 0.1,
                                        "roe": 0.22, "pe_trailing": 15.0})
    assert full == W_FUND and len(notes) == 4
    none_, notes2 = _fundamentals_earned({"revenue_growth": -0.05, "pe_trailing": 80.0})
    assert none_ == 0.0


def test_market_regime_risk_off_penalises_and_caps():
    closes, highs, lows = trend_series()
    on = score_setup("X", "Swedish", closes, highs, lows,
                     market_regime={"index": "^OMX", "risk_on": True})
    off = score_setup("X", "Swedish", closes, highs, lows,
                      market_regime={"index": "^OMX", "risk_on": False})
    assert off["score"] < on["score"]
    assert any("risk-off" in c for c in off["conflicts"])
    assert off["compliance"]["market_regime_filter"] is True
    assert off["grade"] != "A"                       # A-grade cap in a risk-off tape


def test_dynamic_normalization_ignores_missing_components():
    closes, highs, lows = trend_series()
    no_vol = score_setup("X", "Swedish", closes, highs, lows, volumes=None)
    zero_vol = score_setup("X", "Swedish", closes, highs, lows, volumes=[0.0] * len(closes))
    assert no_vol["score"] == zero_vol["score"]      # all-zero volume = not provided
    assert "volume" not in no_vol["sub_scores_max"]
    assert no_vol["compliance"]["volume"] is False


def test_liquidity_penalty_for_thin_turnover():
    closes, highs, lows = trend_series()
    thin = [10.0] * len(closes)                      # ~2k turnover: very thin
    r = score_setup("THIN.ST", "Swedish", closes, highs, lows, volumes=thin)
    assert r["penalties"]["liquidity_penalty"] > 0
    assert r["liquidity_turnover_20d"] is not None
    deep = [1_000_000.0] * len(closes)
    r2 = score_setup("DEEP.ST", "Swedish", closes, highs, lows, volumes=deep)
    assert r2["penalties"]["liquidity_penalty"] == 0.0


# ── v3.3: news sentiment, sector RS, spread, FX, OBV/PRZ, Elliott alternates,
#          intraday refinement ───────────────────────────────────────────────

def _news(items):
    return {"items": items, "source": "test", "as_of": "2026-07-09"}


def test_news_lexicon_positive_negative_stale():
    from api.setup_scanner import news_sentiment
    pos = news_sentiment([{"title": "Company beats estimates, raises guidance",
                           "age_days": 2}])
    assert pos["label"] == "positive" and pos["method"] == "lexicon (model-derived)"
    neg = news_sentiment([{"title": "Profit warning and layoffs announced",
                           "age_days": 3}])
    assert neg["label"] == "negative"
    stale = news_sentiment([{"title": "Company beats estimates", "age_days": 40}])
    assert stale["n_scored"] == 0                       # stale news ignored
    none_ = news_sentiment([{"title": "Quarterly report published", "age_days": 2}])
    assert none_["n_scored"] == 0                       # no lexicon hits = unscored


def test_news_score_moves_final_score_bounded():
    closes, highs, lows = trend_series()
    base = score_setup("X", "Swedish", closes, highs, lows)
    up = score_setup("X", "Swedish", closes, highs, lows, news_context=_news(
        [{"title": "record growth, contract wins, guidance raised", "age_days": 1}]))
    down = score_setup("X", "Swedish", closes, highs, lows, news_context=_news(
        [{"title": "fraud probe, lawsuit, profit warning", "age_days": 1}]))
    assert up["score"] > down["score"]
    assert any("negative" in c for c in down["conflicts"])
    assert abs(up["score"] - base["score"]) < 5          # bounded: news never dominates
    assert base["compliance"]["news_in_score"] is False
    assert up["compliance"]["news_in_score"] is True
    assert up["compliance"]["news_sentiment_licensed"] is False   # honest


def test_sector_relative_strength_component():
    from api.setup_scanner import _sector_component, W_SECTOR
    lead = _sector_component({"proxy": "XLI", "rel_1m": 0.02, "rel_3m": 0.04, "rel_6m": 0.01})
    assert lead["earned"] == W_SECTOR and lead["label"] == "sector leader"
    lag = _sector_component({"proxy": "XLI", "rel_1m": -0.02, "rel_3m": -0.04, "rel_6m": -0.01})
    assert lag["earned"] == 0.0 and lag["label"] == "sector laggard"
    assert _sector_component(None) is None
    assert _sector_component({"proxy": "XLI"}) is None   # no windows = not counted


def test_sector_laggard_penalises_leader_rewards():
    closes, highs, lows = trend_series()
    lead = score_setup("X", "Swedish", closes, highs, lows, sector_context={
        "proxy": "XLI", "rel_1m": 0.02, "rel_3m": 0.04, "rel_6m": 0.01})
    lag = score_setup("X", "Swedish", closes, highs, lows, sector_context={
        "proxy": "XLI", "rel_1m": -0.02, "rel_3m": -0.04, "rel_6m": -0.01})
    assert lead["score"] > lag["score"]
    assert any("lagging sector" in c for c in lag["conflicts"])


def test_spread_model_real_quote_and_proxy():
    from api.setup_scanner import _spread_model
    real = _spread_model(100.0, 2.0, 50e6, "equity", False, bid=99.95, ask=100.05)
    assert real["spread_model_type"] == "quote"
    assert abs(real["spread_pct"] - 0.1) < 0.01
    proxy = _spread_model(100.0, 2.0, 500_000, "equity", True)
    assert proxy["spread_model_type"] == "proxy"
    assert proxy["spread_pct"] > real["spread_pct"]      # thin proxy wider than liquid quote
    assert _spread_model(100.0, 2.0, None, "equity", False) is None


def test_wide_spread_penalises():
    from api.setup_scanner import _spread_model
    closes, highs, lows = trend_series()
    thin = [200.0] * len(closes)                          # tiny turnover -> wide proxy spread
    r = score_setup("THIN.ST", "Swedish", closes, highs, lows, volumes=thin)
    assert r["spread"] is not None
    if r["spread"]["wide"]:
        assert r["penalties"].get("spread_penalty", 0) > 0
        assert any("spread" in c for c in r["conflicts"])


def test_fx_high_volatility_penalises_and_low_does_not():
    closes, highs, lows = trend_series()
    hot = score_setup("COPA.L", "Swedish", closes, highs, lows, fx_context={
        "pair": "USDSEK", "rate": 9.5, "vol_ann_pct": 12.0})
    calm = score_setup("COPA.L", "Swedish", closes, highs, lows, fx_context={
        "pair": "USDSEK", "rate": 9.5, "vol_ann_pct": 5.0})
    assert hot["penalties"].get("fx_risk_penalty", 0) > 0
    assert calm["penalties"].get("fx_risk_penalty", 0) == 0
    assert hot["fx"]["pair"] == "USDSEK"
    none_ = score_setup("X.ST", "Swedish", closes, highs, lows)
    assert none_["fx"] is None and none_["compliance"]["fx_context"] is False


def test_obv_rising_supports_falling_conflicts():
    from api.setup_scanner import _obv_state
    n = 100
    closes = [100 + i * 0.5 for i in range(n)]
    up_vols = [1000.0 + i * 10 for i in range(n)]
    obv_up = _obv_state(closes, up_vols)
    assert obv_up["rising"] is True                       # all up-days: OBV climbs
    # price up but volume concentrated on down bars -> craft alternating series
    closes2 = []
    for i in range(n):
        closes2.append(100 + i * 0.1 + (0.8 if i % 2 == 0 else 0.0))
    vols2 = [5000.0 if closes2[i] < closes2[i - 1] else 100.0 for i in range(n)]
    obv_dn = _obv_state(closes2, vols2)
    assert obv_dn["rising"] is False
    assert _obv_state(closes, None) is None
    assert _obv_state(closes, [0.0] * n) is None


def test_prz_touch_volume_confirmation_and_rejection():
    from api.setup_scanner import _prz_touch_volume
    n = 60
    highs = [101.0] * n
    lows = [99.0] * n
    vols = [1000.0] * (n - 1) + [1800.0]                  # 1.8x on the touch bar
    bull = [{"name": "GARTLEY", "bullish": True, "d_price": 100.0, "age_bars": 3}]
    c = _prz_touch_volume(bull, highs, lows, vols, atr=1.0)
    assert c["confirmed"] is True and c["rejection"] is False
    bear = [{"name": "BUTTERFLY", "bullish": False, "d_price": 100.0, "age_bars": 3}]
    r = _prz_touch_volume(bear, highs, lows, vols, atr=1.0)
    assert r["rejection"] is True
    assert _prz_touch_volume(bull, highs, lows, None, 1.0) is None


def test_elliott_alternate_contradiction_is_informational_not_scored():
    """v3.4 demotion (backtest-evidenced, n=504): the alternate-contradiction
    fired in 83% of entries and saturated 'Conflicted Buy Setup'. It must now
    be VISIBLE (uncertainty_flags) but never scored, counted, or classifying."""
    closes, highs, lows = trend_series()
    ctx = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "IN_PROGRESS", "direction": "BULLISH",
        "current_wave": "Wave 3", "guideline_score": 5,
        "alternate": {"structure": "ZIGZAG", "status": "IN_PROGRESS",
                      "direction": "BEARISH", "current_wave": "Wave C",
                      "invalidation": 90.0, "guideline_score": 2}}}
    r = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx)
    plain = score_setup("X", "Swedish", closes, highs, lows,
                        technical_context={"harmonics": [],
                                           "elliott": {k: v for k, v in ctx["elliott"].items()
                                                       if k != "alternate"}})
    assert r["elliott_preferred"]["structure"] == "IMPULSE"
    assert r["elliott_alternates"] and r["elliott_alternates"][0]["structure"] == "ZIGZAG"
    # visible but NOT a conflict, NOT scored, NOT classification-changing
    assert any("alternate count" in f for f in r["uncertainty_flags"])
    assert not any("alternate count" in c for c in r["conflicts"])
    assert r["score"] == plain["score"]
    assert r["classification"] == plain["classification"]
    assert r["classification"] != "Conflicted Buy Setup"
    assert r["compliance"]["elliott_alternates"] is True
    # a hard BEARISH PREFERRED count still penalizes strongly (unchanged rule)
    bear = {"harmonics": [], "elliott": {
        "structure": "IMPULSE", "status": "IN_PROGRESS",
        "direction": "BEARISH", "current_wave": "Wave 3"}}
    rb = score_setup("X", "Swedish", closes, highs, lows, technical_context=bear)
    assert any("bearish IMPULSE" in c for c in rb["conflicts"])
    assert rb["score"] < plain["score"]
    # agreeing alternate: no flag at all
    ctx2 = {"harmonics": [], "elliott": dict(ctx["elliott"],
            alternate=dict(ctx["elliott"]["alternate"], direction="BULLISH"))}
    r2 = score_setup("X", "Swedish", closes, highs, lows, technical_context=ctx2)
    assert r2["uncertainty_flags"] == []


def test_intraday_refiner_math_and_fallbacks():
    import math as _m
    from api.setup_scanner import refine_target_time_intraday
    ic = [100 + 0.1 * i + 0.5 * _m.sin(i / 3) for i in range(300)]
    ih = [c + 0.3 for c in ic]
    il = [c - 0.3 for c in ic]
    r = refine_target_time_intraday("2026-07-21", 6.0, ih, il, ic, 8.5, "Europe/Stockholm")
    assert r["intraday_available"] is True
    assert "2026-07-21" in r["expected_target_datetime"]
    assert "intraday estimate" in r["expected_target_datetime"]
    assert r["target_time_basis"].startswith("intraday")
    short = refine_target_time_intraday("2026-07-21", 6.0, ih[:10], il[:10], ic[:10], 8.5)
    assert short["intraday_available"] is False and "insufficient" in short["fallback_reason"]
    flat = refine_target_time_intraday("2026-07-21", 6.0, [100.0] * 60, [100.0] * 60,
                                       [100.0] * 60, 8.5)
    assert flat["intraday_available"] is False and "flat" in flat["fallback_reason"]
