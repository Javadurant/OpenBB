"""
Golden-master parity tests for the harmonic Cypher detector.

These exercise the REAL committed detector (pages.ai_trading_agent.detect_cypher),
not a copy, against a TradingView reference case (golden/cypher_btc_tradingfinder.json).

NOTE ON PARITY SCOPE: pivot PRICES in the golden file are screenshot-approximate
until exact values are exported from a live TradingView chart (MCP
data_get_pine_labels) or pasted by the user. The RATIO WINDOWS are exact, taken
from the TradingFinder HP.XABCD call, so ratio-level parity is fully testable now.
"""
import os
import sys

HERE = os.path.dirname(__file__)
OPENBB_PLATFORM = os.path.dirname(HERE)
if OPENBB_PLATFORM not in sys.path:
    sys.path.insert(0, OPENBB_PLATFORM)

from pages.ai_trading_agent import detect_cypher          # the real committed engine
from ta_engine.parity import load_case, ratio_within_window


def _xabc_swings(case):
    p = case["pivots"]
    return [(p[k]["bar_index"], p[k]["price"]) for k in ("x", "a", "b", "c")]


def test_committed_cypher_matches_golden_pattern_and_direction():
    case = load_case("cypher_btc_tradingfinder.json")
    res = detect_cypher(_xabc_swings(case))
    assert res["found"] is True
    assert res["pattern"] == "CYPHER"
    assert res["direction"] == case["direction"]


def test_committed_cypher_ratios_within_tradingfinder_windows():
    case = load_case("cypher_btc_tradingfinder.json")
    res = detect_cypher(_xabc_swings(case))
    w = case["ratio_windows_tradingfinder"]
    assert ratio_within_window(res["ratios"]["AB_XA"], w["B_of_XA"])
    assert ratio_within_window(res["ratios"]["XC_XA"], w["C_of_XA"])


def test_parity_divergence_carney_vs_tradingfinder_c_window():
    # DOCUMENTED DIVERGENCE: a Cypher that TradingFinder draws (C/XA = 1.18, inside
    # its 1.13-1.414 window) is REJECTED by the committed detector (Carney 1.272-
    # 1.414). This test pins the current behavior and makes the gap reviewable.
    X, A = 63825.0, 64310.0
    XA = A - X
    B = A - 0.465 * XA
    C = X + 1.18 * XA                       # TradingFinder-valid, Carney-invalid
    res = detect_cypher([(0, X), (1, A), (2, B), (3, C)])
    assert res["found"] is False
    assert res["ratios"]["XC_XA"] < 1.272   # confirms it sits in the divergence zone
