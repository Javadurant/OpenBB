# api/tests/test_v39_bullish_structure.py
"""v3.9 — bullish-structure scoring component. Deterministic, no network.
Locks: completed bullish harmonic PRZ + Elliott continuation + confluence RAISE
conviction (supports-only), and bearish/aged/above-price/completed cases don't."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.setup_scanner import (W_BULL_CONFLUENCE, W_BULL_ELLIOTT, W_BULL_HARMONIC,
                               W_BULL_STRUCT, _bullish_structure)

PRICE, ATR, EXT = 100.0, 5.0, 0.5  # EXT in pullback band (<=1.2)
_TOL = 1e-9


def _h(bullish, d_price, age=10, name="Gartley"):
    return {"name": name, "bullish": bullish, "d_price": d_price, "age_bars": age}


def test_bullish_prz_near_below_price_scores_full_harmonic():
    ctx = {"harmonics": [_h(True, 98.0)]}  # 0.4 ATR below price
    r = _bullish_structure(ctx, PRICE, ATR, extended_atr=2.0)  # not pullback → no confluence
    assert r is not None
    assert abs(r["harmonic_pts"] - W_BULL_HARMONIC) <= _TOL
    assert abs(r["elliott_pts"]) <= _TOL
    assert abs(r["earned"] - W_BULL_HARMONIC) <= _TOL
    assert "conflict" not in r  # supports-only: never emits a conflict


def test_elliott_continuation_scores():
    ctx = {"harmonics": [], "elliott": {"direction": "BULLISH", "status": "IN_PROGRESS",
                                        "current_wave": "wave 3", "structure": "impulse"}}
    r = _bullish_structure(ctx, PRICE, ATR, extended_atr=2.0)
    assert abs(r["elliott_pts"] - W_BULL_ELLIOTT) <= _TOL
    assert abs(r["earned"] - W_BULL_ELLIOTT) <= _TOL


def test_full_confluence_caps_at_eight():
    # harmonic (4) + elliott (3) + pullback-confluence (1) = 8
    ctx = {"harmonics": [_h(True, 99.0)],
           "elliott": {"direction": "BULLISH", "status": "IN_PROGRESS",
                       "current_wave": "3", "structure": "impulse"}}
    r = _bullish_structure(ctx, PRICE, ATR, extended_atr=EXT)  # in pullback band
    assert abs(r["confluence_pts"] - W_BULL_CONFLUENCE) <= _TOL
    assert abs(r["earned"] - W_BULL_STRUCT) <= _TOL  # 4+3+1 = 8 = max


def test_bearish_harmonic_does_not_score():
    assert _bullish_structure({"harmonics": [_h(False, 98.0)]}, PRICE, ATR, 0.5) is None


def test_aged_bullish_harmonic_excluded():
    assert _bullish_structure({"harmonics": [_h(True, 98.0, age=120)]}, PRICE, ATR, 0.5) is None


def test_bullish_prz_above_price_excluded():
    # A bullish D ABOVE price is not buy-side support
    assert _bullish_structure({"harmonics": [_h(True, 103.0)]}, PRICE, ATR, 0.5) is None


def test_far_prz_excluded():
    # 4 ATR below (beyond NEAR_PRZ_ATR=1.5) → not counted
    assert _bullish_structure({"harmonics": [_h(True, 80.0)]}, PRICE, ATR, 0.5) is None


def test_completed_bullish_elliott_not_scored():
    # A COMPLETE bullish count is 'upside exhausted' — a conflict elsewhere, never a bull score
    ctx = {"harmonics": [], "elliott": {"direction": "BULLISH", "status": "COMPLETE",
                                        "current_wave": "5", "structure": "impulse"}}
    assert _bullish_structure(ctx, PRICE, ATR, 0.5) is None


def test_none_context_and_zero_atr_safe():
    assert _bullish_structure(None, PRICE, ATR, 0.5) is None
    assert _bullish_structure({"harmonics": [_h(True, 98.0)]}, PRICE, 0.0, 0.5) is None


def test_single_signal_no_confluence():
    # harmonic only, not in pullback → structural=1 → no confluence bonus
    r = _bullish_structure({"harmonics": [_h(True, 98.0)]}, PRICE, ATR, extended_atr=2.5)
    assert abs(r["confluence_pts"]) <= _TOL
    assert abs(r["earned"] - W_BULL_HARMONIC) <= _TOL
