"""
Universe Registry tests — provider-backed discovery, honest coverage labels,
and liquidity shortlisting. Network-free: discover_exchange takes a `fetcher`
seam and shortlist takes a `liquidity_fn` seam, both stubbed here.
"""
from __future__ import annotations

import pathlib
import sys
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.universe_registry import (  # noqa: E402
    asset_class_for, discover_exchange, shortlist, to_yf_symbol,
)

# Mirrors the shape EODHD returns (verified live 2026-07-14).
ST_FIXTURE = [
    {"Code": "VOLV-B", "Name": "Volvo B", "Type": "Common Stock", "Currency": "SEK"},
    {"Code": "SKF-B", "Name": "SKF B", "Type": "Common Stock", "Currency": "SEK"},
    {"Code": "XACT-OMXS30", "Name": "XACT OMXS30", "Type": "ETF", "Currency": "SEK"},
    {"Code": "0P0000ULAP", "Name": "Spiltan", "Type": "FUND", "Currency": "SEK"},
    {"Code": "SOMEPREF", "Name": "Pref", "Type": "Preferred Stock", "Currency": "SEK"},
    {"Code": "", "Name": "blank", "Type": "Common Stock", "Currency": "SEK"},
]


def test_asset_class_and_symbol_mapping():
    assert asset_class_for("Common Stock") == "equity"
    assert asset_class_for("ETF") == "etf"
    assert asset_class_for("Mutual Fund") == "fund"
    assert asset_class_for("Preferred Stock") is None
    assert asset_class_for(None) is None
    assert to_yf_symbol("SKF-B", "ST") == "SKF-B.ST"
    assert to_yf_symbol("AAPL", "US") == "AAPL"


def test_discover_normalizes_and_labels_full_exchange():
    res = discover_exchange("ST", fetcher=lambda e: ST_FIXTURE, use_cache=False)
    assert res["coverage_label"] == "full_exchange_market"
    assert res["source_provider"] == "eodhd"
    # Preferred + blank-code rows are dropped; 4 valid instruments remain.
    assert res["discovered"] == 4
    classes = sorted(s["asset_class"] for s in res["symbols"])
    assert classes == ["equity", "equity", "etf", "fund"]
    skf = next(s for s in res["symbols"] if s["provider_symbol"] == "SKF-B")
    assert skf["symbol"] == "SKF-B.ST"       # yfinance suffix applied
    assert skf["region"] == "Swedish"


def test_discover_failure_labels_are_honest():
    def raise_key(_e):
        raise PermissionError("no key")

    def raise_gate(_e):
        raise urllib.error.HTTPError("u", 423, "Locked", None, None)

    def raise_other(_e):
        raise RuntimeError("boom")

    assert discover_exchange("ST", fetcher=raise_key, use_cache=False)["coverage_label"] == "key_missing"
    assert discover_exchange("ST", fetcher=raise_gate, use_cache=False)["coverage_label"] == "plan_gated"
    r = discover_exchange("ST", fetcher=raise_other, use_cache=False)
    assert r["coverage_label"] == "provider_blocked"
    assert r["discovered"] == 0 and r["symbols"] == []


def test_shortlist_prefilters_rank_and_report():
    universe = discover_exchange("ST", fetcher=lambda e: ST_FIXTURE, use_cache=False)["symbols"]
    liq = {
        "VOLV-B.ST": {"last_price": 250.0, "turnover_20d": 9e8, "history_days": 500},
        "SKF-B.ST":  {"last_price": 260.0, "turnover_20d": 5e8, "history_days": 500},
    }
    # VOLV-B (higher turnover) must rank first; SKF-B second. Equities only.
    res = shortlist(universe, "equity", liquidity_fn=lambda s: liq.get(s),
                    limit=10, min_price=1.0, min_history_days=130)
    assert res["discovered"] == 2          # two equities in the exchange list
    assert res["eligible"] == 2
    assert res["scanned"] == 2
    assert res["symbols"][0]["symbol"] == "VOLV-B.ST"

    # Now make SKF-B fail each prefilter and confirm honest exclusion reasons.
    liq2 = {
        "VOLV-B.ST": {"last_price": 250.0, "turnover_20d": 9e8, "history_days": 500},
        "SKF-B.ST":  None,   # no data
    }
    res2 = shortlist(universe, "equity", liquidity_fn=lambda s: liq2.get(s), limit=10)
    assert res2["eligible"] == 1
    assert res2["excluded"].get("no_price_data") == 1

    liq3 = {
        "VOLV-B.ST": {"last_price": 0.2, "turnover_20d": 9e8, "history_days": 500},  # penny
        "SKF-B.ST":  {"last_price": 260.0, "turnover_20d": 5e8, "history_days": 10}, # short
    }
    res3 = shortlist(universe, "equity", liquidity_fn=lambda s: liq3.get(s),
                     limit=10, min_price=1.0, min_history_days=130)
    assert res3["eligible"] == 0
    assert res3["excluded"].get("below_min_price") == 1
    assert res3["excluded"].get("insufficient_history") == 1

    # limit caps the scanned set and reports capped_out honestly.
    res4 = shortlist(universe, "equity", liquidity_fn=lambda s: liq.get(s), limit=1)
    assert res4["scanned"] == 1 and res4["capped_out"] == 1
