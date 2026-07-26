# api/tvremix_scanner.py
"""
Conflicted Buy Setup market scanner — market-wide discovery (Priority 3).

Layers (Section 7 architecture, adapted to verified capabilities 2026-07-22):
  1. Universe discovery: tvremix run_screener per market (sweden / america /
     crypto — all three live-verified). UNFILTERED by user decision
     2026-07-22: no min-price/min-volume thresholds are applied because
     thresholds are user-supplied only; every row's price/volume/market-cap
     is exposed so downstream consumers can filter, and coverage is labelled
     "unfiltered_screener".
  2. Sentiment overlay: Bigdata.com licensed chunk sentiment for the top
     candidates of the equity markets (quota-honest: finalists only).
  3. Technicals rating: TradingView Recommend.All arrives IN the screener
     rows — no per-symbol calls needed. Buy-side ratings become Conflicted
     Buy Setup candidates per the project data-architecture spec.
  4. Crypto universe: the TradingView crypto screener (verified live:
     CRYPTO:BTCUSD with Recommend.All). The CoinDesk WebSocket feed remains
     a capability probe only — building a WS market-data client is separate,
     unstarted work and is labelled honestly in the output.

Conviction score (user decision 2026-07-22): TradingView's own computed
Recommend.All rating, linearly mapped from [-1, 1] to [0, 100]. This is a
transparent relabelling of the provider's licensed computed value — NO
invented weights. Bigdata sentiment is context, not scored.

Redistribution gate (TRUTH 3): output is for internal signal generation.
Raw TV price quotes must not be re-served to end users until tvremix
licensing terms are verified.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .bigdata_client import bigdata_search
from .tvremix_client import fetch_tvremix_news, run_screener, tvremix_key_present

logger = logging.getLogger("tvremix-scanner")

_MARKETS = (
    {"market": "sweden", "region": "Swedish",
     "label": "OMX Stockholm + Nordic venues (TradingView 'sweden' screener)"},
    {"market": "america", "region": "International",
     "label": "US listed (TradingView 'america' screener)"},
    {"market": "crypto", "region": "Crypto",
     "label": "Global crypto (TradingView 'crypto' screener)"},
)
# Section 7 contract: news_headlines = top 3. Enrichment is finalists-only
# so a scan costs a bounded, predictable number of external calls.
_NEWS_TOP_N = 3
_BIGDATA_TOP_N = 3
_BIGDATA_RESULT_LIMIT = 5
_HEADLINES_MAX = 3

_TYPE_TO_ASSET = {"stock": "STOCK", "fund": "FUND", "etf": "ETF",
                  "spot": "CRYPTO"}
_EQUITY_MARKETS = ("sweden", "america")


def signal_type_for(recommendation: Optional[str]) -> str:
    """Section 7 Layer-3 mapping, verbatim from the project spec:
    BUY / STRONG_BUY → Conflicted Buy Setup candidate; SELL / STRONG_SELL →
    short/sell candidate; everything else → NEUTRAL watchlist."""
    rec = (recommendation or "").strip().lower()
    if rec in ("buy", "strong buy"):
        return "CONFLICTED_BUY"
    if rec in ("sell", "strong sell"):
        return "SELL"
    return "NEUTRAL"


def conviction_from_rating(rec_all: Any) -> Optional[float]:
    """User decision 2026-07-22: TV Recommend.All in [-1, 1] linearly mapped
    to [0, 100]. Returns None (never a fabricated number) when the provider
    did not supply a rating."""
    if not isinstance(rec_all, (int, float)):
        return None
    v = (float(rec_all) + 1.0) / 2.0 * 100.0
    return round(max(0.0, min(100.0, v)), 1)


def _row_to_setup(row: dict, mkt: dict, now_iso: str) -> Optional[dict]:
    sym = (row.get("symbol") or "").strip()
    if not sym:
        return None
    exchange = sym.split(":", 1)[0] if ":" in sym else "?"
    rtype = (row.get("type") or "").strip().lower()
    if mkt["market"] == "crypto":
        asset_class = "CRYPTO"
    else:
        asset_class = _TYPE_TO_ASSET.get(rtype, rtype.upper() or "UNKNOWN")
    recommendation = row.get("recommendation")
    rec_all = row.get("Recommend.All")
    return {
        # ── Section 7 output contract ──
        "symbol": sym,
        "exchange": exchange,
        "asset_class": asset_class,
        "signal_type": signal_type_for(recommendation),
        "conviction_score": conviction_from_rating(rec_all),
        "data_sources_used": ["TradingView screener via tvremix"],
        "technicals_rating": {
            "recommendation": recommendation,
            "value": rec_all,
            "interval": "1D",
            "source": "TradingView Recommend.All via tvremix",
        },
        "sentiment_score": None,
        "sentiment_note": "not scored (no licensed sentiment retrieved)",
        "news_headlines": None,
        "timestamp_utc": now_iso,
        "source_as_of": f"TradingView screener snapshot {now_iso}",
        # ── honest transparency fields (so consumers can filter/verify) ──
        "name": row.get("description") or row.get("name"),
        "price": row.get("close"),
        "currency": row.get("currency"),
        "volume": row.get("volume"),
        "market_cap": row.get("market_cap_basic") or row.get("market_cap_calc"),
        "rsi": row.get("RSI"),
        "sector": row.get("sector"),
        "days_to_earnings": row.get("days_to_earnings"),
        "conviction_method": ("TV Recommend.All linear map [-1,1]→[0,100] "
                              "(user decision 2026-07-22)"),
    }


def _bigdata_sentiment_overlay(query: str) -> Optional[dict]:
    """Mean licensed best-chunk sentiment across up to _BIGDATA_RESULT_LIMIT
    search results. Arithmetic over licensed values only — never modelled."""
    results = bigdata_search(query, limit=_BIGDATA_RESULT_LIMIT)
    if not results:
        return None
    vals: list[float] = []
    for r in results:
        chunks = [c for c in (r.get("chunks") or []) if isinstance(c, dict)]
        if not chunks:
            continue
        best = max(chunks, key=lambda c: c.get("relevance") or 0.0)
        s = best.get("sentiment")
        if isinstance(s, (int, float)):
            vals.append(float(s))
    if not vals:
        return None
    return {
        "score": round(sum(vals) / len(vals), 3),
        "n_results_scored": len(vals),
        "note": (f"mean licensed Bigdata.com chunk sentiment of {len(vals)} "
                 "search results, scale -1..1"),
    }


def conflicted_buy_scan(limit: int = 50) -> dict:
    """Full market scan across Swedish, International and Crypto universes.
    Returns {"status": "ok", ...} always — per-market failures degrade to an
    honest error entry, never a crash. See module docstring for method."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    if not tvremix_key_present():
        return {"status": "ok", "generated_utc": now_iso, "markets": {},
                "total_setups": 0,
                "error": "TVREMIX_API_KEY not set (or placeholder) — scanner unavailable"}

    markets_out: dict[str, Any] = {}
    total = 0
    # Phase A: ALL screeners first, enrichment after — news/Bigdata calls
    # between screener calls were live-observed (2026-07-22) to burn the
    # per-minute budget and starve the later markets.
    market_rows: dict[str, Optional[list]] = {}
    for mkt in _MARKETS:
        market_rows[mkt["market"]] = run_screener(market=mkt["market"], limit=limit)
    for mkt in _MARKETS:
        rows = market_rows[mkt["market"]]
        if rows is None:
            markets_out[mkt["market"]] = {
                "region": mkt["region"], "label": mkt["label"],
                "scanned": 0, "setups": [],
                "error": "screener unavailable (see /api/ready tvremix_capabilities)",
            }
            continue
        setups = []
        for row in rows:
            if isinstance(row, dict):
                s = _row_to_setup(row, mkt, now_iso)
                if s is not None:
                    setups.append(s)
        # Rank: highest buy conviction first → lowest → sells at the bottom
        # come out naturally because conviction maps sell ratings below 50.
        setups.sort(key=lambda s: (
            -(s["conviction_score"] if s["conviction_score"] is not None else -1.0),
            s["symbol"]))

        # Finalist enrichment — bounded external calls per scan.
        for s in setups[:_NEWS_TOP_N]:
            try:
                nv = fetch_tvremix_news(s["symbol"], limit=_HEADLINES_MAX)
                if nv:
                    s["news_headlines"] = [it["title"] for it in nv["items"][:_HEADLINES_MAX]]
                    s["data_sources_used"].append(nv["source"])
            except Exception as exc:  # noqa: BLE001 - enrichment never breaks a scan
                logger.debug("news enrichment %s: %s", s["symbol"], type(exc).__name__)
        if mkt["market"] in _EQUITY_MARKETS:
            for s in setups[:_BIGDATA_TOP_N]:
                if not s.get("name"):
                    continue
                try:
                    overlay = _bigdata_sentiment_overlay(str(s["name"]))
                    if overlay:
                        s["sentiment_score"] = overlay["score"]
                        s["sentiment_note"] = overlay["note"]
                        s["data_sources_used"].append(
                            "Bigdata.com licensed chunk sentiment")
                except Exception as exc:  # noqa: BLE001
                    logger.debug("bigdata overlay %s: %s",
                                 s["symbol"], type(exc).__name__)

        markets_out[mkt["market"]] = {
            "region": mkt["region"], "label": mkt["label"],
            "scanned": len(setups),
            "coverage_label": "unfiltered_screener",
            "setups": setups,
        }
        total += len(setups)

    return {
        "status": "ok",
        "generated_utc": now_iso,
        "markets": markets_out,
        "total_setups": total,
        "conviction_method": ("TradingView Recommend.All linearly mapped from "
                              "[-1,1] to [0,100] (user decision 2026-07-22); "
                              "no invented weights"),
        "universe_note": ("TradingView screener universes via tvremix, "
                          "UNFILTERED (user decision 2026-07-22) — price/volume "
                          "thresholds are user-supplied only and none were supplied"),
        "crypto_note": ("crypto universe via the TradingView crypto screener; "
                        "the CoinDesk WebSocket feed remains a capability probe "
                        "only (no WS market-data client built yet)"),
        "redistribution_note": ("internal signal generation only — raw TV quote "
                                "redistribution to end users is gated pending "
                                "tvremix licensing verification (TRUTH 3)"),
    }
