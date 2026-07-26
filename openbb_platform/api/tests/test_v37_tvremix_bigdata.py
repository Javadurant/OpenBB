# api/tests/test_v37_tvremix_bigdata.py
"""v3.7 smoke tests: tvremix MCP client, Bigdata search adapter, and the
Conflicted Buy Setup scanner mappers. Zero network — live-captured fixtures
(2026-07-22) + monkeypatched env only (pytest-smoke idiom)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.bigdata_client import (bigdata_search, fetch_bigdata_news,
                                parse_bigdata_items)
from api.tvremix_client import (fetch_tvremix_news, parse_tvremix_news_items,
                                to_tv_symbol, tvremix_key_present)
from api.tvremix_scanner import (_row_to_setup, conviction_from_rating,
                                 signal_type_for)

_NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
_TOL = 1e-9

# Live-captured tvremix get_news shape (OMXSTO:VOLV_B, 2026-07-22).
TVR_HEADLINES = [
    {"id": "DJN_DN20260721001662:0",
     "title": ("Volvo's Cyclical Recovery Supports Higher Second-Half "
               "Volumes — Market Talk"),
     "published": "2026-07-21T08:48:00Z",
     "provider": "Dow Jones Newswires", "urgency": 2,
     "link": "https://www.tradingview.com/news/DJN_DN20260721001662:0/"},
    {"title": "No published date item"},
]

# Live-captured Bigdata /v1/search shape (query "Volvo truck orders", 2026-07-22).
BIGDATA_RESULTS = [
    {"id": "E7193709FB23C35F623FD6A2B7ED4CEA",
     "headline": ("BofA Updates Estimate for Volvo Group After Q2 Order Beat; "
                  "Buy Rating Kept"),
     "timestamp": "2026-07-22T07:45:50",
     "source": {"id": "CF4113", "name": "MT Newswires - EMEA", "rank": "RANK_1"},
     "chunks": [{"cnum": 1, "text": "BofA Global Research adjusted its earnings "
                 "forecasts for AB Volvo after stronger-than-expected orders.",
                 "relevance": 0.55, "sentiment": 0.79}]},
    {"headline": "Neutral piece", "timestamp": "2026-07-20T00:00:00",
     "source": {"name": "X"},
     "chunks": [{"text": "t", "relevance": 0.1, "sentiment": 0.05}]},
    {"headline": "Negative piece", "timestamp": "2026-07-10T00:00:00",
     "source": {"name": "Y"},
     "chunks": [{"text": "t", "relevance": 0.9, "sentiment": -0.61}]},
]


def test_to_tv_symbol_mappings():
    assert to_tv_symbol("VOLV-B.ST") == "OMXSTO:VOLV_B"
    assert to_tv_symbol("INVE-B.ST") == "OMXSTO:INVE_B"
    assert to_tv_symbol("OMXSTO:VOLV_B") == "OMXSTO:VOLV_B"
    assert to_tv_symbol("AAPL") is None      # bare US tickers unverified
    assert to_tv_symbol("BTC-USD") is None   # crypto mapping unverified
    assert to_tv_symbol("") is None


def test_parse_tvremix_news_items_shape():
    items = parse_tvremix_news_items(TVR_HEADLINES, now=_NOW)
    assert len(items) == 2
    it = items[0]
    assert it["title"].startswith("Volvo's Cyclical Recovery")
    assert it["age_days"] == 1
    assert it["publisher"] == "Dow Jones Newswires"
    assert it["url"].startswith("https://www.tradingview.com/news/")
    assert items[1]["age_days"] is None  # honest: unknown age, not 0


def test_tvremix_key_placeholder_rejected(monkeypatch):
    monkeypatch.setenv("TVREMIX_API_KEY", "{TVREMIX_API_KEY}")
    assert tvremix_key_present() is False
    assert fetch_tvremix_news("VOLV-B.ST") is None  # degrades, zero network
    monkeypatch.delenv("TVREMIX_API_KEY")
    assert tvremix_key_present() is False


def test_parse_bigdata_items_licensed_sentiment():
    items = parse_bigdata_items(BIGDATA_RESULTS, now=_NOW)
    assert len(items) == 3
    assert items[0]["sentiment"] == "positive"
    assert items[0]["sentiment_source"] == "Bigdata.com chunk sentiment (licensed)"
    assert items[0]["publisher"] == "MT Newswires - EMEA"
    assert items[0]["age_days"] == 0
    assert len(items[0]["summary"]) <= 240
    assert items[1]["sentiment"] == "neutral"    # |0.05| within ±0.2 band
    assert items[2]["sentiment"] == "negative"   # -0.61 below -0.2
    assert items[2]["age_days"] == 12


def test_bigdata_secret_safety(monkeypatch):
    monkeypatch.setenv("BIGDATA_API_KEY", "SENTINEL-NEVER-SHOWN")
    items = parse_bigdata_items(BIGDATA_RESULTS, now=_NOW)
    assert "SENTINEL-NEVER-SHOWN" not in json.dumps(items)


def test_bigdata_placeholder_no_network(monkeypatch):
    monkeypatch.setenv("BIGDATA_API_KEY", "{BIGDATA_API_KEY}")
    assert bigdata_search("Volvo") is None
    assert fetch_bigdata_news("Volvo") is None


def test_signal_type_mapping():
    # Section 7 Layer-3 mapping, verbatim from the project spec.
    assert signal_type_for("Strong Buy") == "CONFLICTED_BUY"
    assert signal_type_for("Buy") == "CONFLICTED_BUY"
    assert signal_type_for("Sell") == "SELL"
    assert signal_type_for("Strong Sell") == "SELL"
    assert signal_type_for("Neutral") == "NEUTRAL"
    assert signal_type_for(None) == "NEUTRAL"


def test_conviction_mapping_tolerance():
    # User decision 2026-07-22: linear [-1,1] → [0,100]. No float ==.
    assert conviction_from_rating(None) is None
    assert conviction_from_rating("not a number") is None
    assert abs(conviction_from_rating(1.0) - 100.0) <= _TOL
    assert abs(conviction_from_rating(-1.0) - 0.0) <= _TOL
    assert abs(conviction_from_rating(0.0) - 50.0) <= _TOL
    assert abs(conviction_from_rating(0.6030303) - 80.2) <= _TOL  # 1dp rounding


def test_row_to_setup_contract():
    row = {"symbol": "OMXSTO:VOLV_B", "description": "Volvo AB Class B",
           "type": "stock", "close": 347.8, "currency": "SEK",
           "volume": 2159825, "market_cap_basic": 690577344971,
           "RSI": 67.1, "sector": "Producer Manufacturing",
           "Recommend.All": 0.603, "recommendation": "Strong Buy",
           "days_to_earnings": 35}
    mkt = {"market": "sweden", "region": "Swedish", "label": "x"}
    s = _row_to_setup(row, mkt, "2026-07-22T12:00:00+00:00")
    for k in ("symbol", "exchange", "asset_class", "signal_type",
              "conviction_score", "data_sources_used", "technicals_rating",
              "sentiment_score", "news_headlines", "timestamp_utc",
              "source_as_of"):
        assert k in s, f"Section 7 contract key missing: {k}"
    assert s["exchange"] == "OMXSTO"
    assert s["asset_class"] == "STOCK"
    assert s["signal_type"] == "CONFLICTED_BUY"
    assert s["sentiment_score"] is None          # honest until licensed data
    assert s["news_headlines"] is None           # enrichment is finalists-only
    crypto = _row_to_setup({"symbol": "CRYPTO:BTCUSD", "type": "spot",
                            "recommendation": "Buy", "Recommend.All": 0.2},
                           {"market": "crypto", "region": "Crypto", "label": "x"},
                           "t")
    assert crypto["asset_class"] == "CRYPTO"
    assert _row_to_setup({"type": "stock"}, mkt, "t") is None  # no symbol → None
