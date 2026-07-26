# api/tests/test_omnisearch_router.py
"""
Pure-function smoke tests for api.omnisearch_router. No yfinance,
no network — exercises the cache helpers, classify_asset rules, and
news dedup. These are the helpers the routers compose; a regression
here cascades across the whole bridge.
"""
import time

import pytest

from api.omnisearch_router import (
    _CACHE,
    _TTL,
    _TTL_SYMBOLOGY,
    _cache_get,
    _cache_set,
    _dedupe_news,
    _round,
    _safe,
    classify_asset,
    rank_score,
    resolve_venue,
)


# ─── cache helpers ────────────────────────────────────────────────────────
def setup_function(_function) -> None:
    """Reset the module-global cache between tests."""
    _CACHE.clear()


def test_cache_roundtrip() -> None:
    _cache_set("k1", {"a": 1})
    assert _cache_get("k1") == {"a": 1}


def test_cache_get_misses_after_default_ttl() -> None:
    _cache_set("expiring", "value")
    _CACHE["expiring"] = (time.time() - (_TTL + 1), "value")  # backdate
    assert _cache_get("expiring") is None


def test_cache_get_default_ttl_evicts_stale_entries() -> None:
    _CACHE["stale"] = (time.time() - 7200, "v")  # 2h ago, default TTL is 60s
    assert _cache_get("stale") is None
    # The miss must also evict the entry so we don't accumulate dead state.
    assert "stale" not in _CACHE


def test_cache_get_symbology_ttl_keeps_24h_old_entries() -> None:
    """Per-call ttl override must work — used by symbology() to keep
    24h-stable identifiers cached even though default _TTL is 60s."""
    _CACHE["stable"] = (time.time() - 7200, "v")  # 2h ago
    assert _cache_get("stable", ttl=_TTL_SYMBOLOGY) == "v"


# ─── classify_asset ───────────────────────────────────────────────────────
@pytest.mark.parametrize("symbol,yf_type,expected", [
    ("AAPL",       "EQUITY",        "equity"),
    ("SPY",        "ETF",           "etf"),
    ("VFIAX",      "MUTUALFUND",    "fund"),
    ("^GSPC",      "INDEX",         "index"),
    ("BTC-USD",    "CRYPTOCURRENCY","crypto"),
    ("EURUSD=X",   "CURRENCY",      "fx"),
    ("GC=F",       "FUTURE",        "future"),
    ("AAPL241220C00200000", "OPTION","option"),
])
def test_classify_asset_direct_yf_type(symbol: str, yf_type: str, expected: str) -> None:
    assert classify_asset(symbol, yf_type) == expected


@pytest.mark.parametrize("symbol,expected", [
    ("EURUSD=X",  "fx"),
    ("GC=F",      "commodity"),
    ("BTC-USD",   "crypto"),
    ("^GSPC",     "index"),
    ("AAPL",      "equity"),  # default fallback
])
def test_classify_asset_pattern_fallback(symbol: str, expected: str) -> None:
    """When yf_type is missing, the symbol pattern alone classifies."""
    assert classify_asset(symbol, "") == expected


# ─── resolve_venue ────────────────────────────────────────────────────────
def test_resolve_venue_st_equity_returns_sek() -> None:
    v = resolve_venue("EVO.ST", "equity", None)
    assert v["country"] == "SE"
    assert v["currency"] == "SEK"


def test_resolve_venue_bond_us_prefix_returns_us_treasury() -> None:
    v = resolve_venue("US10Y", "bond", None)
    assert v["country"] == "US"
    assert v["currency"] == "USD"
    assert v["tier"] == "sovereign"


def test_resolve_venue_bond_eurozone_prefix_returns_eur() -> None:
    v = resolve_venue("DE10Y", "bond", None)
    assert v["country"] == "DE"
    assert v["currency"] == "EUR"


# ─── _dedupe_news ─────────────────────────────────────────────────────────
def test_dedupe_news_keeps_first_occurrence_by_url() -> None:
    items = [
        {"title": "Apple Q4",  "url": "https://example.com/a", "_ts": 100},
        {"title": "AAPL News", "url": "https://example.com/a", "_ts": 99},   # dup URL
        {"title": "Other",     "url": "https://example.com/b", "_ts": 90},
    ]
    out = _dedupe_news(items)
    assert len(out) == 2
    assert out[0]["title"] == "Apple Q4"   # first occurrence wins
    assert out[1]["url"] == "https://example.com/b"


def test_dedupe_news_falls_back_to_title_when_url_missing() -> None:
    items = [
        {"title": "Same Headline", "url": None, "_ts": 100},
        {"title": "Same Headline", "url": None, "_ts": 90},
    ]
    out = _dedupe_news(items)
    assert len(out) == 1


def test_dedupe_news_drops_entries_with_neither_url_nor_title() -> None:
    items = [
        {"title": "real", "url": "https://x.com/1"},
        {"title": "",     "url": None},
        {"title": None,   "url": None},
    ]
    out = _dedupe_news(items)
    assert len(out) == 1


# ─── _safe / _round ───────────────────────────────────────────────────────
def test_safe_returns_default_for_nan_inf() -> None:
    import math
    assert _safe(math.nan, default=0) == 0
    assert _safe(math.inf, default=0) == 0
    assert _safe(-math.inf, default=0) == 0


def test_round_strips_nan_and_handles_none() -> None:
    assert _round(None) is None
    assert _round(1.23456, 2) == 1.23
    assert _round("not a number") is None


# ─── rank_score (Item 8 boost lives downstream of this) ───────────────────
def test_rank_score_exact_ticker_match_is_top() -> None:
    s_exact = rank_score("AAPL", "AAPL", "Apple Inc.")
    s_partial = rank_score("AAPL", "AAPLY", "Apple Hospitality REIT")
    assert s_exact > s_partial
    assert s_exact >= 1000  # the "exact ticker" boost is +1000


def test_rank_score_empty_query_is_zero() -> None:
    assert rank_score("", "AAPL", "Apple") == 0
