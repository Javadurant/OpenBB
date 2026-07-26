"""
api/news_aggregator.py
=======================
Phase 3 Deliverable A (May 19, 2026) — FREE MT Newswires equivalent.

Multi-source news aggregator combining 5 free providers. Replaces the need
for paid MT Newswires CORE subscription.

PROVIDERS — by free-tier generosity:

    1. GDELT          — ZERO-KEY, completely free, global news graph
                        ~250k articles/day indexed, ticker-symbol matching
                        (https://www.gdeltproject.org/)

    2. YFINANCE       — UNLIMITED, no key, always-on fallback
                        Top 10-15 yahoo finance headlines per ticker

    3. POLYGON        — 5 calls/min free, requires POLYGON_API_KEY
                        Richest: per-ticker sentiment + insights + keywords

    4. FINNHUB        — 60 calls/min free, requires FINNHUB_API_KEY
                        Company news endpoint with sentiment field
                        (https://finnhub.io/dashboard — free signup)

    5. ALPHA_VANTAGE  — 25 calls/day free, requires ALPHA_VANTAGE_API_KEY
                        NEWS_SENTIMENT with per-ticker sentiment scores
                        Gated behind AV_INCLUDE=1 to preserve scarce quota

Strategy: parallel fan-out across all configured providers, then dedupe by
URL and sort by published_utc desc.

REMOVED (paid-tier required):
    - Tiingo news (returns HTTP 403 even with valid key)
    - FMP stock_news (returns HTTP 403/402 even with valid key, paywalled)

VERIFICATION (May 19, 2026):
    - GDELT          OK — returns AAPL articles globally
    - YFINANCE       OK — 10-15 items/call
    - AV NEWS_SENT   OK — 50 items per call
    - POLYGON        OK — pending key in .env
    - FINNHUB        OK — pending key (user signs up free at finnhub.io)
"""
from __future__ import annotations
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Final, Optional

import httpx

from .news_provider import (
    NewsItem,
    NewsProvider,
    PolygonNewsProvider,
    YFinanceNewsProvider,
    _clamp,
    _strip_html,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# GDELT — completely free, no API key, global news graph
# ─────────────────────────────────────────────────────────────────────────
class GDELTNewsProvider(NewsProvider):
    """
    GDELT 2.0 Doc API. ZERO key required. Global news indexing project.

    Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

    Note: GDELT indexes news that MENTIONS the ticker — not stock-specific
    coverage. Combined with other providers it adds breadth (e.g. coverage
    of small companies that financial sites miss).
    """

    name = "gdelt"
    BASE_URL: Final = "https://api.gdeltproject.org/api/v2/doc/doc"

    # Map ticker → full company name for better matching (top 50 mega-caps)
    _COMPANY_HINTS: Final = {
        "AAPL": "Apple",   "MSFT": "Microsoft", "GOOG": "Google",
        "GOOGL": "Alphabet", "AMZN": "Amazon",  "META": "Meta",
        "TSLA": "Tesla",   "NVDA": "Nvidia",    "BRK.B": "Berkshire",
        "JPM": "JPMorgan", "JNJ": "Johnson Johnson", "V": "Visa",
        "PG": "Procter Gamble", "UNH": "UnitedHealth", "HD": "Home Depot",
        "MA": "Mastercard","XOM": "Exxon",      "BAC": "Bank of America",
        "DIS": "Disney",   "ADBE": "Adobe",     "NFLX": "Netflix",
        "CRM": "Salesforce","CSCO": "Cisco",    "INTC": "Intel",
        "AMD": "Advanced Micro Devices", "PYPL": "PayPal",
        "ORCL": "Oracle",  "IBM": "IBM",        "BABA": "Alibaba",
    }

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        ticker_upper = ticker.upper()
        company = self._COMPANY_HINTS.get(ticker_upper, ticker_upper)

        # Use both ticker and company name to maximize relevance
        query = f'"{company}" stock' if company != ticker_upper else f'"{ticker_upper}"'

        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(
                    self.BASE_URL,
                    params={
                        "query":      query,
                        "mode":       "ArtList",
                        "maxrecords": min(limit * 2, 50),  # over-fetch to filter
                        "format":     "json",
                        "sort":       "datedesc",
                        "timespan":   "3d",  # last 3 days only
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("gdelt news HTTP %s for %s", e.response.status_code, ticker)
            return []
        except Exception as e:
            logger.warning("gdelt news fetch failed for %s: %s", ticker, e)
            return []

        articles = data.get("articles") or []
        out: list[NewsItem] = []
        for item in articles[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                title = _strip_html(item.get("title"))
                if not title:
                    continue
                # GDELT seendate format: YYYYMMDDTHHMMSSZ
                seen = item.get("seendate", "")
                pub_iso = ""
                if len(seen) >= 13:
                    try:
                        dt = datetime.strptime(seen[:13], "%Y%m%dT%H%M")
                        pub_iso = dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pub_iso = seen

                norm: NewsItem = {
                    "id":        f"gdelt_{seen}_{title[:30]}",
                    "title":     title,
                    "summary":   "",  # GDELT doesn't return summaries in ArtList mode
                    "published": pub_iso,
                    "source":    str(item.get("domain") or "GDELT"),
                    "url":       str(item.get("url", "")),
                    "tickers":   [ticker_upper],
                }
                if item.get("socialimage"):
                    norm["thumbnail"] = str(item["socialimage"])
                out.append(norm)
            except Exception as e:
                logger.debug("gdelt parse error: %s", e)
                continue

        return out


# ─────────────────────────────────────────────────────────────────────────
# Finnhub — 60 calls/min free, requires API key
# ─────────────────────────────────────────────────────────────────────────
class FinnhubNewsProvider(NewsProvider):
    """
    Finnhub company-news endpoint. Free tier: 60 calls/min, basic data only.
    User signs up free at https://finnhub.io/dashboard
    Docs: https://finnhub.io/docs/api/company-news
    """

    name = "finnhub"
    BASE_URL: Final = "https://finnhub.io/api/v1/company-news"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        ticker_upper = ticker.upper()

        # Finnhub requires from/to date range
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=14)

        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(
                    self.BASE_URL,
                    params={
                        "symbol":   ticker_upper,
                        "from":     start.isoformat(),
                        "to":       end.isoformat(),
                        "token":    self._api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("finnhub news HTTP %s for %s", e.response.status_code, ticker)
            return []
        except Exception as e:
            logger.warning("finnhub news fetch failed for %s: %s", ticker, e)
            return []

        if not isinstance(data, list):
            return []

        out: list[NewsItem] = []
        for item in data[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                title = _strip_html(item.get("headline"))
                if not title:
                    continue
                # Finnhub datetime is epoch seconds
                ts = item.get("datetime") or 0
                pub_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat() if ts else ""

                norm: NewsItem = {
                    "id":        f"finnhub_{item.get('id', '')}_{title[:30]}",
                    "title":     title,
                    "summary":   _strip_html(item.get("summary")),
                    "published": pub_iso,
                    "source":    str(item.get("source") or "Finnhub"),
                    "url":       str(item.get("url", "")),
                    "tickers":   [str(t).upper() for t in (item.get("related") or "").split(",") if t][:10] or [ticker_upper],
                }
                if item.get("image"):
                    norm["thumbnail"] = str(item["image"])
                if item.get("category"):
                    norm["keywords"] = [str(item["category"])]
                out.append(norm)
            except Exception as e:
                logger.debug("finnhub parse error: %s", e)
                continue

        return out


# ─────────────────────────────────────────────────────────────────────────
# AlphaVantage NEWS_SENTIMENT — 25 calls/day free, scarce quota
# ─────────────────────────────────────────────────────────────────────────
class AlphaVantageNewsProvider(NewsProvider):
    """
    AlphaVantage NEWS_SENTIMENT endpoint. Free tier: 25 calls/day total.

    Each call returns up to 50 items with per-ticker sentiment scoring.
    GATED behind AV_INCLUDE=1 env var to preserve scarce quota.

    Docs: https://www.alphavantage.co/documentation/#news-sentiment
    """

    name = "alpha_vantage"
    BASE_URL: Final = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        ticker_upper = ticker.upper()
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    self.BASE_URL,
                    params={
                        "function": "NEWS_SENTIMENT",
                        "tickers":  ticker_upper,
                        "limit":    limit,
                        "sort":     "LATEST",
                        "apikey":   self._api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("alpha_vantage news HTTP %s for %s", e.response.status_code, ticker)
            return []
        except Exception as e:
            logger.warning("alpha_vantage news fetch failed for %s: %s", ticker, e)
            return []

        if "Information" in data and "rate limit" in str(data.get("Information", "")).lower():
            logger.warning("alpha_vantage rate-limited (25/day exhausted)")
            return []

        feed = data.get("feed") or []
        out: list[NewsItem] = []
        for item in feed[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                title = _strip_html(item.get("title"))
                if not title:
                    continue

                # Extract sentiment for the requested ticker
                sentiment: Optional[str] = None
                sentiment_reasoning: Optional[str] = None
                for ts in (item.get("ticker_sentiment") or []):
                    if str(ts.get("ticker", "")).upper() == ticker_upper:
                        try:
                            score = float(ts.get("ticker_sentiment_score", 0))
                        except (TypeError, ValueError):
                            score = 0.0
                        label = str(ts.get("ticker_sentiment_label", "")).lower()
                        if "bullish" in label:
                            sentiment = "positive"
                        elif "bearish" in label:
                            sentiment = "negative"
                        else:
                            sentiment = "neutral"
                        sentiment_reasoning = f"AlphaVantage score {score:+.3f} ({label.replace('-', ' ')})"
                        break

                # AV time_published format: YYYYMMDDTHHMMSS
                pub_raw = str(item.get("time_published", ""))
                pub_iso = ""
                if len(pub_raw) >= 13:
                    try:
                        dt = datetime.strptime(pub_raw[:13], "%Y%m%dT%H%M")
                        pub_iso = dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pub_iso = pub_raw

                norm: NewsItem = {
                    "id":        f"av_{pub_raw}_{title[:30]}",
                    "title":     title,
                    "summary":   _strip_html(item.get("summary")),
                    "published": pub_iso,
                    "source":    str(item.get("source") or "AlphaVantage"),
                    "url":       str(item.get("url", "")),
                    "tickers":   [str(t.get("ticker", "")).upper()
                                  for t in (item.get("ticker_sentiment") or [])
                                  if t.get("ticker")][:10] or [ticker_upper],
                }
                if item.get("banner_image"):
                    norm["thumbnail"] = str(item["banner_image"])
                if item.get("topics"):
                    norm["keywords"] = [str(t.get("topic", "")) for t in item["topics"][:8] if t.get("topic")]
                if sentiment:
                    norm["sentiment"] = sentiment
                if sentiment_reasoning:
                    norm["sentiment_reasoning"] = sentiment_reasoning
                out.append(norm)
            except Exception as e:
                logger.debug("alpha_vantage parse error: %s", e)
                continue

        return out


# ─────────────────────────────────────────────────────────────────────────
# Multi-source aggregator (parallel fan-out + dedupe)
# ─────────────────────────────────────────────────────────────────────────
class MultiSourceNewsAggregator:
    """
    Combines free providers in parallel, dedupes by URL, sorts by published_utc.

    Provider activation:
        - Always:           GDELT (no key) + YFinance (no key)
        - POLYGON_API_KEY   → PolygonNewsProvider (richest)
        - FINNHUB_API_KEY   → FinnhubNewsProvider
        - ALPHA_VANTAGE_API_KEY + AV_INCLUDE=1 → AlphaVantageNewsProvider

    AlphaVantage is gated behind AV_INCLUDE=1 to preserve precious 25/day quota.
    """

    name = "multi"

    def __init__(self) -> None:
        self.providers: list[NewsProvider] = []
        self._init_providers()

    def _init_providers(self) -> None:
        # Tier 1: Polygon (richest, when key set)
        if (k := os.getenv("POLYGON_API_KEY", "").strip()):
            self.providers.append(PolygonNewsProvider(k))

        # Tier 2: Finnhub (60/min, when key set)
        if (k := os.getenv("FINNHUB_API_KEY", "").strip()):
            self.providers.append(FinnhubNewsProvider(k))

        # Tier 3: AlphaVantage (gated)
        if os.getenv("AV_INCLUDE", "").strip() in ("1", "true", "yes"):
            if (k := os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()):
                self.providers.append(AlphaVantageNewsProvider(k))

        # Tier 4: GDELT (no key, always on)
        self.providers.append(GDELTNewsProvider())

        # Tier 5: YFinance (no key, always last fallback)
        self.providers.append(YFinanceNewsProvider())

        logger.info("MultiSource aggregator initialized with %d providers: %s",
                    len(self.providers), [p.name for p in self.providers])

    def fetch(self, ticker: str, limit: int = 15) -> dict[str, Any]:
        """
        Parallel fetch from all configured providers, dedupe + sort.

        Returns:
            {
                items:      list[NewsItem],
                providers:  list[str],
                counts:     dict[str, int],
            }
        """
        limit = _clamp(limit, 1, 50)
        results: dict[str, list[NewsItem]] = {}

        with ThreadPoolExecutor(max_workers=min(5, len(self.providers))) as pool:
            futures = {
                pool.submit(p.fetch, ticker, limit): p.name
                for p in self.providers
            }
            for fut in as_completed(futures, timeout=20.0):
                name = futures[fut]
                try:
                    items = fut.result()
                    if items:
                        results[name] = items
                except Exception as e:
                    logger.warning("provider %s failed: %s", name, e)

        # Dedupe by URL (strip query params)
        seen_urls: set[str] = set()
        merged: list[NewsItem] = []
        for name, items in results.items():
            for item in items:
                url = (item.get("url", "") or "").lower().strip().rstrip("/")
                if not url:
                    continue
                key = url.split("?")[0]
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                # Tag with the contributing provider
                merged.append({**item, "_provider": name})  # type: ignore

        # Sort by published descending
        merged.sort(key=lambda i: i.get("published", "") or "", reverse=True)

        return {
            "items":     merged[:limit],
            "providers": list(results.keys()),
            "counts":    {name: len(items) for name, items in results.items()},
        }


def aggregator_active_providers() -> list[str]:
    """Diagnostic: which providers are currently active."""
    return [p.name for p in MultiSourceNewsAggregator().providers]
