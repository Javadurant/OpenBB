"""v3.6 tests: Polygon licensed-sentiment news adapter + advisory-council
source-integrity grounding (scanner levels beat conviction arithmetic)."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.polygon_news import (fetch_polygon_news, parse_polygon_items,  # noqa: E402
                              polygon_key_present)
from api.setup_scanner import news_sentiment  # noqa: E402

POLY_FIXTURE = [
    {"title": "Apple announces record quarter",
     "description": "Revenue climbs.",
     "published_utc": "2026-07-11T14:00:00Z",
     "article_url": "https://example.com/a",
     "publisher": {"name": "Reuters"},
     "insights": [{"ticker": "AAPL", "sentiment": "positive",
                   "sentiment_reasoning": "Strong results."}]},
    {"title": "Analysts cautious on supply chain",
     "description": "",
     "published_utc": "2026-07-10T09:00:00Z",
     "article_url": "https://example.com/b",
     "publisher": {"name": "WSJ"},
     "insights": [{"ticker": "MSFT", "sentiment": "negative",
                   "sentiment_reasoning": "Different ticker - must not apply."}]},
]


def test_polygon_fixture_parses_with_per_ticker_licensed_sentiment(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "POLYKEY-NEVER-SHOWN")
    items = parse_polygon_items(POLY_FIXTURE, "AAPL")
    assert len(items) == 2
    assert items[0]["sentiment"] == "positive"                 # matched ticker
    assert items[0]["sentiment_source"] == "Polygon insights (licensed)"
    assert "sentiment" not in items[1]                          # MSFT insight ignored
    assert "POLYKEY" not in json.dumps(items)                   # secret-safe


def test_licensed_sentiment_beats_lexicon_and_upgrades_confidence():
    licensed = news_sentiment([
        {"title": "no lexicon words here at all", "age_days": 1,
         "sentiment": "positive"}])
    assert licensed["label"] == "positive"                      # scored WITHOUT lexicon hits
    assert licensed["n_licensed"] == 1
    assert licensed["method"] == "licensed per-ticker sentiment"
    assert licensed["confidence"] == "high"
    mixed = news_sentiment([
        {"title": "irrelevant words", "age_days": 1, "sentiment": "negative"},
        {"title": "company beats estimates", "age_days": 1}])
    assert mixed["method"] == "mixed: licensed + lexicon"
    assert mixed["confidence"] == "medium"


def test_polygon_placeholder_or_missing_key_degrades(monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "{polygon_api_key}")
    assert polygon_key_present() is False                       # placeholder detected
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    assert polygon_key_present() is False
    assert fetch_polygon_news("AAPL") is None                   # no crash, no network


def test_trade_ticket_consumes_scanner_levels_first(monkeypatch):
    """COUNCIL-AUDIT: with technical evidence, ticket levels come from the
    Setup Scanner - conviction arithmetic only as labelled fallback."""
    import pandas as pd
    from api import symbol_router as sr
    n = 30
    df = pd.DataFrame({"high": [101.0] * n, "low": [99.0] * n,
                       "close": [100.0] * n, "volume": [1e6] * n})
    monkeypatch.setattr(sr, "_import_engines",
                        lambda: {"_fetch_ohlcv": lambda s, years=1: df})
    tally = {"BUY": 4, "SELL": 3, "HOLD": 3, "avg_score": 60.0}
    tech = {"entry": 257.6, "invalidation": 247.73, "target": 277.34,
            "reward_risk": 2.0}
    t = sr._trade_ticket("SKF-B.ST", 257.6, "BUY", 72, tally, tech=tech)
    assert t["scanner_grounded"] is True
    assert t["stop"] == 247.73 and t["target"] == 277.34
    assert t["expected_rr"] == 2.0                              # NOT 1 + 2*0.72 = 2.44
    assert "Setup Scanner" in t["level_basis"]
    assert "Setup Scanner" in t["stop_reason"]
    # fallback path stays honest and labelled
    t2 = sr._trade_ticket("SKF-B.ST", 100.0, "BUY", 72, tally, tech=None)
    assert t2["scanner_grounded"] is False
    assert t2["expected_rr"] == 2.44                            # conviction arithmetic
    assert "NO scanner evidence" in t2["level_basis"]


def test_council_response_source_integrity_wording():
    """Static check: the chairman endpoint must ship the simulation framing."""
    src = (pathlib.Path(__file__).resolve().parents[1] / "symbol_router.py").read_text()
    assert "simulation_disclaimer" in src
    assert "not a real review or" in src            # per-member basis framing
    assert "did not" in src and "review this security" in src
