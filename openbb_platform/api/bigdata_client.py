"""api/bigdata_client.py — Bigdata.com capability probe.

Endpoint confirmed directly by the user (bigdata.com's own quickstart
snippet, 2026-07-18): POST /v1/search, X-API-KEY header. Note: Bigdata's
subscription was previously PAUSED independent of key validity -- a 401/403
here can mean either a bad key or an inactive subscription; this probe
cannot tell those apart, only that "not working" is true, which is still
strictly more informative than "key is a non-empty string."
Key is read at call time and never logged, returned, or included in any
exception text.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("bigdata")

_CAPS_CACHE: dict = {}
_SEARCH_URL = "https://api.bigdata.com/v1/search"
_SEARCH_TIMEOUT_S = 10
_MAX_NEWS_ITEMS = 8
# Label boundaries REUSE the scanner's established news_sentiment convention
# (score > 0.2 → positive, < -0.2 → negative) — an existing platform value,
# not a new invention. Bigdata chunk sentiment is on the -1..1 scale.
_SENT_POS_T = 0.2
_SENT_NEG_T = -0.2


def bigdata_key_present() -> bool:
    return bool(os.getenv("BIGDATA_API_KEY", "").strip())


def bigdata_capabilities(force: bool = False) -> dict:
    """Probe a minimal search query to confirm the key + subscription both
    actually work. Booleans + HTTP reason only, never the key."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    key = os.getenv("BIGDATA_API_KEY", "").strip()
    if not key:
        _CAPS_CACHE = {"bigdata_key_present": False, "bigdata_working": False,
                       "bigdata_reason": "BIGDATA_API_KEY not set"}
        return _CAPS_CACHE
    try:
        body = json.dumps({"query": {"text": "test"}}).encode()
        req = urllib.request.Request(
            "https://api.bigdata.com/v1/search", data=body, method="POST",
            headers={"X-API-KEY": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            json.loads(resp.read().decode("utf-8"))
        _CAPS_CACHE = {"bigdata_key_present": True, "bigdata_working": True,
                       "bigdata_reason": None}
    except urllib.error.HTTPError as e:
        reason = f"HTTP {e.code}"
        if e.code in (401, 403):
            reason += " (bad key OR paused subscription -- check billing too)"
        _CAPS_CACHE = {"bigdata_key_present": True, "bigdata_working": False,
                       "bigdata_reason": reason}
    except Exception as exc:  # noqa: BLE001
        _CAPS_CACHE = {"bigdata_key_present": True, "bigdata_working": False,
                       "bigdata_reason": type(exc).__name__}
    return _CAPS_CACHE


# ── v3.7: real search + scanner news adapter (Priority 2 wiring) ───────────
# Live-verified 2026-07-22: POST /v1/search {"query": {"text": ...}} returns
# {"results": [{id, headline, timestamp, source {name, rank, tier},
#   chunks [{cnum, text, relevance, sentiment, detections}]}]}
# with LICENSED numeric per-chunk sentiment on the -1..1 scale.

def _usable_key() -> str:
    """Placeholder-aware key access for the data path (polygon idiom).
    Does not alter the original bigdata_key_present() contract."""
    v = os.getenv("BIGDATA_API_KEY", "").strip()
    if not v or v == "PASTE" or (v.startswith("{") and v.endswith("}")):
        return ""
    return v


def bigdata_search(query: str, limit: int = _MAX_NEWS_ITEMS) -> Optional[list]:
    """Raw search results list, or None on ANY failure (key missing, HTTP,
    network, parse). Consumes real API quota. Never raises, never logs the
    key — failures reduce to HTTP code / exception class name."""
    key = _usable_key()
    if not key or not query:
        return None
    try:
        body = json.dumps({"query": {"text": query}}).encode()
        req = urllib.request.Request(
            _SEARCH_URL, data=body, method="POST",
            headers={"X-API-KEY": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results")
        if not isinstance(results, list):
            return None
        return results[:limit]
    except urllib.error.HTTPError as e:
        logger.debug("bigdata search failed: HTTP %s", e.code)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("bigdata search failed: %s", type(exc).__name__)
        return None


def parse_bigdata_items(results: list, now: Optional[datetime] = None) -> list:
    """Pure normalizer: Bigdata results → scanner news-item shape
    {title, summary, age_days, publisher, sentiment, sentiment_source,
    sentiment_reasoning}. The licensed numeric chunk sentiment (best-relevance
    chunk) maps to positive/negative/neutral via the scanner's own ±0.2
    convention, which flips news_sentiment() into licensed mode.
    Fixture-testable, no network."""
    now = now or datetime.now(timezone.utc)
    items: list[dict] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        title = (r.get("headline") or "").strip()
        if not title:
            continue
        item: dict[str, Any] = {"title": title[:160]}
        chunks = [c for c in (r.get("chunks") or []) if isinstance(c, dict)]
        if chunks:
            best = max(chunks, key=lambda c: c.get("relevance") or 0.0)
            text = (best.get("text") or "").strip()
            if text:
                item["summary"] = text[:240]
            sent = best.get("sentiment")
            if isinstance(sent, (int, float)):
                if sent > _SENT_POS_T:
                    label = "positive"
                elif sent < _SENT_NEG_T:
                    label = "negative"
                else:
                    label = "neutral"
                item["sentiment"] = label
                item["sentiment_source"] = "Bigdata.com chunk sentiment (licensed)"
                item["sentiment_reasoning"] = (
                    f"licensed chunk sentiment {sent:+.2f} on -1..1 scale "
                    f"(relevance {best.get('relevance') or 0.0:.2f})")[:200]
        ts = r.get("timestamp")
        if isinstance(ts, str) and ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                item["age_days"] = max(0, (now - dt).days)
            except ValueError:
                item["age_days"] = None
        src = r.get("source") or {}
        if isinstance(src, dict) and src.get("name"):
            item["publisher"] = str(src["name"])[:60]
        items.append(item)
        if len(items) >= _MAX_NEWS_ITEMS:
            break
    return items


def fetch_bigdata_news(query: str, limit: int = _MAX_NEWS_ITEMS) -> Optional[dict]:
    """Scanner news-chain entry: {"items", "source", "as_of"} or None.
    Query should be a company NAME (live-verified: 'Volvo truck orders'
    returned premium MT Newswires content) — bare tickers match poorly."""
    results = bigdata_search(query, limit=limit)
    if not results:
        return None
    items = parse_bigdata_items(results)
    if not items:
        return None
    licensed = sum(1 for it in items if "sentiment" in it)
    return {
        "items": items,
        "source": (f"Bigdata.com search ({licensed}/{len(items)} items with "
                   "licensed chunk sentiment)"),
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }
