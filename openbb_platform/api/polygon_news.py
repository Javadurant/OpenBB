"""Polygon.io news adapter (v3.6) — the project's first LICENSED sentiment feed.

Live capability probe 2026-07-12: POLYGON_API_KEY is real (not a placeholder)
and /v2/reference/news returns items WITH per-ticker `insights[].sentiment`
("positive|negative|neutral") and `sentiment_reasoning`. This upgrades the
scanner's news component from lexicon-only (model-derived, low confidence) to
licensed sentiment for symbols Polygon covers (US names; .ST tickers degrade
to the Avanza/yfinance lexicon route).

Contract mirrors fmp_news.py: secret-safe (key never in output/logs/errors),
hard timeout, item cap, None on any failure, provenance in the source string.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("polygon_news")

_TIMEOUT_S = 8
_MAX_ITEMS = 10
_URL = "https://api.polygon.io/v2/reference/news"
_CAPS: dict = {}


def polygon_key_present() -> bool:
    v = os.getenv("POLYGON_API_KEY", "").strip()
    return bool(v) and v != "PASTE" and not (v.startswith("{") and v.endswith("}"))


def parse_polygon_items(results: list, ticker: str,
                        now: Optional[datetime] = None) -> list[dict]:
    """Normalize Polygon news rows to the scanner's news-item shape, carrying
    the LICENSED per-ticker sentiment when insights match the symbol."""
    now = now or datetime.now(timezone.utc)
    items: list[dict] = []
    for row in results or []:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "").strip()
        if not title:
            continue
        age_days = None
        try:
            ts = row.get("published_utc")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                age_days = max(0, (now - dt).days)
        except (ValueError, TypeError):
            pass
        senti, reasoning = None, None
        for ins in row.get("insights") or []:
            if isinstance(ins, dict) and ins.get("ticker", "").upper() == ticker.upper():
                senti = ins.get("sentiment")
                reasoning = (ins.get("sentiment_reasoning") or "")[:200]
                break
        item = {
            "title": title[:160],
            "summary": (row.get("description") or "")[:240],
            "age_days": age_days,
            "url": (row.get("article_url") or "")[:300],
            "publisher": ((row.get("publisher") or {}).get("name") or "")[:60],
        }
        if senti in ("positive", "negative", "neutral"):
            item["sentiment"] = senti                     # LICENSED, per-ticker
            item["sentiment_source"] = "Polygon insights (licensed)"
            if reasoning:
                item["sentiment_reasoning"] = reasoning
        items.append(item)
    return items[:_MAX_ITEMS]


def fetch_polygon_news(symbol: str, limit: int = _MAX_ITEMS) -> Optional[dict]:
    """News for one symbol with licensed sentiment, or None (missing key,
    non-US coverage gap, network failure). Key never logged or echoed."""
    if not polygon_key_present():
        return None
    key = os.getenv("POLYGON_API_KEY", "").strip()
    try:
        qs = urllib.parse.urlencode(
            {"ticker": symbol, "limit": min(limit, _MAX_ITEMS), "apiKey": key})
        req = urllib.request.Request(f"{_URL}?{qs}",
                                     headers={"User-Agent": "sentriq-scanner"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        items = parse_polygon_items(raw.get("results", []), symbol)
        if not items:
            return None
        licensed = sum(1 for i in items if "sentiment" in i)
        return {
            "items": items,
            "source": (f"Polygon news ({licensed}/{len(items)} items with "
                       "licensed per-ticker sentiment)"),
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - never stall or crash a scan
        logger.debug("polygon news %s failed: %s", symbol, type(exc).__name__)
        return None


def polygon_capabilities(force: bool = False) -> dict:
    """Cached capability status for /api/ready (booleans + category only)."""
    global _CAPS
    if _CAPS and not force:
        return _CAPS
    caps = {"polygon_key_present": polygon_key_present(),
            "polygon_news_available": False, "polygon_gate_reason": None}
    if not caps["polygon_key_present"]:
        caps["polygon_gate_reason"] = "POLYGON_API_KEY missing or placeholder"
    else:
        r = fetch_polygon_news("AAPL", limit=1)
        caps["polygon_news_available"] = r is not None
        if r is None:
            caps["polygon_gate_reason"] = "probe returned no items (plan/coverage)"
    _CAPS = caps
    return caps
