"""FMP stock-news adapter (v3.4) — bounded, provenance-rich, secret-safe.

/api/ready confirmed FMP_API_KEY exists in the server env (booleans only).
This adapter turns that into a real news source for the Setup Scanner's
lexicon-sentiment component. Design contract:

  - read-only public market-data endpoint (stock_news), never account data;
  - the API key is read from the environment at call time and NEVER appears
    in returned data, logs, exceptions, or reprs (asserted by tests);
  - hard timeout + item cap: a slow/failed FMP call can never stall a scan;
  - missing key / any failure degrades to None (caller falls back to yfinance);
  - items match the scanner's news_context shape: {title, summary, age_days, url}.
  - provenance: source string names FMP; per-item timestamps preserved.

Known coverage limit (verified 2026-07-10 via the FMP MCP): Nordic `.ST`
tickers return empty - Swedish names keep using yfinance/Avanza-Placera routes.

PLAN GATE (verified live 2026-07-11, key redacted): with the server's current
FMP key, /stable/news/stock returns HTTP 402 Payment Required and
/api/v3/stock_news returns HTTP 403 Forbidden - FMP news requires a higher
FMP plan. The adapter is fixture-tested and degrades to None (yfinance
fallback) until the plan is upgraded; no code change will be needed then.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("fmp_news")

_FMP_TIMEOUT_S = 8
_FMP_MAX_ITEMS = 10
_FMP_URL = "https://financialmodelingprep.com/api/v3/stock_news"


def fmp_key_present() -> bool:
    """Boolean only - the value is never returned or logged."""
    return bool(os.getenv("FMP_API_KEY", "").strip())


def parse_fmp_items(raw: list, now: Optional[datetime] = None) -> list[dict]:
    """Normalize FMP stock_news rows to the scanner's news-item shape.
    Pure + fixture-testable. Rows: {title, text, publishedDate, url, site}."""
    now = now or datetime.now(timezone.utc)
    items: list[dict] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or "").strip()
        if not title:
            continue
        age_days = None
        ts = row.get("publishedDate")
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = max(0, (now - dt).days)
        except (ValueError, TypeError):
            pass
        items.append({
            "title": title[:160],
            "summary": (row.get("text") or "")[:240],
            "age_days": age_days,
            "url": (row.get("url") or "")[:300],
            "publisher": (row.get("site") or "")[:60],
        })
    return items[:_FMP_MAX_ITEMS]


def fetch_fmp_news(symbol: str, limit: int = _FMP_MAX_ITEMS) -> Optional[dict]:
    """Fetch news for one symbol. Returns the scanner news_context dict or
    None (missing key, non-US coverage gap, network failure, bad payload).
    The key is passed as a query param to FMP only - never logged/echoed."""
    key = os.getenv("FMP_API_KEY", "").strip()
    if not key:
        return None
    try:
        qs = urllib.parse.urlencode(
            {"tickers": symbol, "limit": min(limit, _FMP_MAX_ITEMS), "apikey": key})
        req = urllib.request.Request(f"{_FMP_URL}?{qs}",
                                     headers={"User-Agent": "sentriq-scanner"})
        with urllib.request.urlopen(req, timeout=_FMP_TIMEOUT_S) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        items = parse_fmp_items(raw if isinstance(raw, list) else [])
        if not items:
            return None
        return {
            "items": items,
            "source": "FMP stock_news + lexicon sentiment (model-derived)",
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - never stall or crash a scan
        logger.debug("fmp news %s failed: %s", symbol, type(exc).__name__)
        return None
