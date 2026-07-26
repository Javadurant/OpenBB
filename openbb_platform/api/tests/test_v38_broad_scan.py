# api/tests/test_v38_broad_scan.py
"""v3.8 smoke tests: broad market scan pipeline + tvremix reverse symbol map.
Zero network — injected discover/screener/score stubs (universe_registry
fetcher-seam philosophy)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.broad_scan import _build_liquidity_map, _turnover, broad_scan
from api.tvremix_client import from_tv_symbol


def test_from_tv_symbol_inverse():
    assert from_tv_symbol("OMXSTO:VOLV_B") == "VOLV-B.ST"
    assert from_tv_symbol("OMXSTO:SKF_B") == "SKF-B.ST"
    assert from_tv_symbol("NASDAQ:AAPL") == "AAPL"
    assert from_tv_symbol("NYSE:JPM") == "JPM"
    assert from_tv_symbol("AMEX:UUP") == "UUP"
    # Unmappable venues are dropped, never guessed:
    assert from_tv_symbol("NGM:SERV") is None
    assert from_tv_symbol("CRYPTO:BTCUSD") is None
    assert from_tv_symbol("AAPL") is None      # bare ticker, no exchange
    assert from_tv_symbol("") is None


def test_turnover_prefers_avg_volume():
    assert _turnover({"close": 100.0, "average_volume_10d_calc": 1000,
                      "volume": 5}) == 100_000.0
    assert _turnover({"close": 100.0, "volume": 2000}) == 200_000.0  # fallback
    assert _turnover({"close": 0.0, "volume": 2000}) is None          # no fabrication
    assert _turnover({"volume": 2000}) is None                        # missing price
    assert _turnover({"close": 10.0}) is None                         # missing volume


def test_liquidity_map_filters_and_maps():
    rows = [
        {"symbol": "OMXSTO:VOLV_B", "type": "stock", "close": 347.8,
         "average_volume_10d_calc": 2_000_000},
        {"symbol": "NGM:SERV", "type": "stock", "close": 0.007,
         "average_volume_10d_calc": 170_000_000},   # unmappable venue -> dropped
        {"symbol": "OMXSTO:XACT_BULL", "type": "fund", "close": 10.0,
         "volume": 1000},                            # non-equity type -> dropped
    ]
    liq = _build_liquidity_map(rows)
    assert set(liq) == {"VOLV-B.ST"}
    assert liq["VOLV-B.ST"]["turnover_20d"] == 347.8 * 2_000_000


def test_broad_scan_ranks_by_grade_then_liquidity():
    disc = {"coverage_label": "full_exchange_market", "symbols": [
        {"symbol": "VOLV-B.ST", "asset_class": "equity"},
        {"symbol": "SKF-B.ST", "asset_class": "equity"},
        {"symbol": "PENNY.ST", "asset_class": "equity"},
    ]}
    screen = [
        {"symbol": "OMXSTO:VOLV_B", "type": "stock", "close": 347.8,
         "average_volume_10d_calc": 2_000_000},   # turnover ~695M
        {"symbol": "OMXSTO:SKF_B", "type": "stock", "close": 230.0,
         "average_volume_10d_calc": 1_500_000},   # turnover ~345M
        {"symbol": "OMXSTO:PENNY", "type": "stock", "close": 0.007,
         "average_volume_10d_calc": 170_000_000}, # turnover ~1.2M (penny)
    ]
    grades = {"VOLV-B.ST": "A", "SKF-B.ST": "B", "PENNY.ST": "C"}
    captured = {}

    def score(entry, calibration=None, regime_map=None, news_enabled=True):
        sym, region, ac = entry
        captured[sym] = news_enabled
        return {"symbol": sym, "region": region, "asset_class": ac,
                "grade": grades[sym], "score": {"A": 88, "B": 74, "C": 40}[grades[sym]],
                "classification": "x", "last_price": 1.0}

    out = broad_scan("Swedish", score_fn=score,
                     discover_fn=lambda e: disc,
                     screener_fn=lambda market, limit=300: screen, depth=10)
    assert out["status"] == "ok"
    assert out["scanned"] == 3
    assert out["grade_a_count"] == 1 and out["grade_b_count"] == 1
    assert [r["symbol"] for r in out["grade_a"]] == ["VOLV-B.ST"]
    assert [r["symbol"] for r in out["grade_b"]] == ["SKF-B.ST"]
    # News MUST be skipped for the broad breadth scan:
    assert all(v is False for v in captured.values())
    assert "946" not in out["coverage_label"] or "discovered" in out["coverage_label"]


def test_broad_scan_screener_derived_fallback_when_discovery_empty():
    # EODHD key missing -> discovery empty -> fall back to screener universe, labelled.
    screen = [{"symbol": "OMXSTO:VOLV_B", "type": "stock", "close": 347.8,
               "average_volume_10d_calc": 2_000_000}]

    def score(entry, calibration=None, regime_map=None, news_enabled=True):
        return {"symbol": entry[0], "region": entry[1], "asset_class": entry[2],
                "grade": "B", "score": 70.0}

    out = broad_scan("Swedish", score_fn=score,
                     discover_fn=lambda e: {"coverage_label": "key_missing", "symbols": []},
                     screener_fn=lambda market, limit=300: screen, depth=10)
    assert out["status"] == "ok"
    assert out["discovery_label"] == "screener_derived_universe"
    assert out["scanned"] == 1


def test_broad_scan_survives_screener_failure():
    def boom(market, limit=300):
        raise RuntimeError("screener down")

    out = broad_scan("International", score_fn=lambda *a, **k: None,
                     discover_fn=lambda e: {"coverage_label": "full_exchange_market",
                                            "symbols": []},
                     screener_fn=boom, depth=10)
    assert out["status"] == "ok"      # never crashes
    assert out["scanned"] == 0
