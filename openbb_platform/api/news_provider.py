"""
api/news_provider.py
=====================
Phase 2 Deliverable A + B — News provider abstraction with Polygon rich-data support.

Returns ticker-specific news headlines for the SENTRIQ symbol page.

Provider strategy:
- Default: yfinance (free, already in venv, no API key required)
- Polygon: activated when POLYGON_API_KEY environment variable is set
           Polygon adds per-ticker sentiment, related tickers, keywords,
           publisher logo, and full descriptions.

The endpoint /api/symbol/{ticker}/news consumes this module.
The frontend NewsTab.tsx + OverviewTab.tsx renders the normalized output.

Normalized output shape (NewsItem):
    {
      "id":           str,                # stable unique id from provider
      "title":        str,                # headline text (HTML stripped)
      "summary":      Optional[str],      # full description (1-3 sentences)
      "published":    str,                # ISO-8601 timestamp (UTC)
      "source":       str,                # publisher display name
      "url":          str,                # link to full story
      "thumbnail":    Optional[str],      # cover image URL
      "tickers":      list[str],          # related tickers mentioned

      # ── Polygon-only enrichments (None/missing for yfinance) ─────────
      "sentiment":            Optional[str],  # positive | negative | neutral
      "sentiment_reasoning":  Optional[str],  # 1-3 sentence rationale
      "keywords":             Optional[list[str]],
      "publisher_logo":       Optional[str],  # publisher logo image URL
      "publisher_favicon":    Optional[str],  # publisher favicon URL
    }
"""
from __future__ import annotations
import html
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Final, Optional, TypedDict

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)

# Tag-strip regex — Gurpreet S. requirement (XSS-safe headlines)
_HTML_TAG_RE: Final = re.compile(r"<[^>]+>")


def _strip_html(text: Optional[str]) -> str:
    """Strip HTML tags and decode entities from provider-supplied text."""
    if not text:
        return ""
    no_tags = _HTML_TAG_RE.sub("", text)
    return html.unescape(no_tags).strip()


def _clamp(n: int, lo: int, hi: int) -> int:
    """Clamp integer to [lo, hi] range. Selivanov's input-safety helper."""
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


# ── Output contract (TypedDict for type safety) ───────────────────────────
class NewsItem(TypedDict, total=False):
    id:                  str
    title:               str
    summary:             str
    published:           str
    source:              str
    url:                 str
    thumbnail:           str
    tickers:             list[str]
    # Polygon enrichments (yfinance leaves these out)
    sentiment:           str    # positive | negative | neutral
    sentiment_reasoning: str
    keywords:            list[str]
    publisher_logo:      str
    publisher_favicon:   str


# ── Abstract provider ─────────────────────────────────────────────────────
class NewsProvider(ABC):
    """Strategy-pattern base class for news providers."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        """Return up to `limit` recent news items for `ticker`."""
        raise NotImplementedError


# ── yfinance provider (default, free) ─────────────────────────────────────
class YFinanceNewsProvider(NewsProvider):
    """
    Default provider. Uses yfinance.Ticker(...).news which returns a list of
    dicts with the modern shape {id, content: {title, summary, pubDate,
    provider: {displayName}, previewUrl, thumbnail: {originalUrl}, ...}}.

    Falls back gracefully when yfinance returns the legacy flat shape.
    No sentiment / keywords / related-tickers — yfinance doesn't provide them.
    """

    name = "yfinance"

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        try:
            tk = yf.Ticker(ticker.upper())
            raw = tk.news or []
        except Exception as e:
            logger.warning("yfinance news fetch failed for %s: %s", ticker, e)
            return []

        out: list[NewsItem] = []
        for item in raw[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                # Modern shape (post-2024): {id, content: {...}}
                if "content" in item and isinstance(item["content"], dict):
                    c = item["content"]
                    title = _strip_html(c.get("title"))
                    if not title:
                        continue
                    norm: NewsItem = {
                        "id":        str(item.get("id") or c.get("id") or title[:60]),
                        "title":     title,
                        "summary":   _strip_html(c.get("summary") or c.get("description")),
                        "published": str(c.get("pubDate") or c.get("displayTime") or ""),
                        "source":    str((c.get("provider") or {}).get("displayName") or "Yahoo Finance"),
                        "url":       str(c.get("previewUrl") or c.get("canonicalUrl", {}).get("url", "")),
                        "tickers":   [ticker.upper()],
                    }
                    thumb = (c.get("thumbnail") or {}).get("originalUrl")
                    if thumb:
                        norm["thumbnail"] = str(thumb)

                # Legacy flat shape
                else:
                    title = _strip_html(item.get("title"))
                    if not title:
                        continue
                    pub_ts = item.get("providerPublishTime")
                    if isinstance(pub_ts, (int, float)):
                        pub_iso = datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat()
                    else:
                        pub_iso = str(pub_ts or "")
                    norm = {
                        "id":        str(item.get("uuid") or title[:60]),
                        "title":     title,
                        "summary":   "",
                        "published": pub_iso,
                        "source":    str(item.get("publisher") or "Yahoo Finance"),
                        "url":       str(item.get("link", "")),
                        "tickers":   [ticker.upper()],
                    }
                    if item.get("thumbnail"):
                        thumb_url = (item["thumbnail"].get("resolutions") or [{}])[0].get("url")
                        if thumb_url:
                            norm["thumbnail"] = str(thumb_url)

                out.append(norm)
            except Exception as e:
                logger.debug("yfinance news item parse error: %s", e)
                continue

        return out


# ── Polygon provider (production-grade, requires API key) ─────────────────
class PolygonNewsProvider(NewsProvider):
    """
    Polygon.io news endpoint — production-grade.

    Activated when POLYGON_API_KEY env var is set. Free tier: 5 calls/min,
    2-year history. Returns rich insights per article:
      - per-ticker sentiment (positive/negative/neutral) + 1-3 sentence reasoning
      - related tickers
      - keywords / topic tags
      - publisher logo + favicon URLs
      - full description (not just truncated summary)

    Docs: https://polygon.io/docs/rest/stocks/news
    """

    name = "polygon"
    BASE_URL: Final = "https://api.polygon.io/v2/reference/news"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.Client(timeout=15.0)

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        ticker_upper = ticker.upper()
        try:
            resp = self._client.get(
                self.BASE_URL,
                params={
                    "ticker": ticker_upper,
                    "limit":  limit,
                    "order":  "desc",
                    "sort":   "published_utc",
                    "apiKey": self._api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("polygon news HTTP %s for %s: %s",
                           e.response.status_code, ticker, e.response.text[:120])
            return []
        except Exception as e:
            logger.warning("polygon news fetch failed for %s: %s", ticker, e)
            return []

        out: list[NewsItem] = []
        for item in (data.get("results") or [])[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                title = _strip_html(item.get("title"))
                if not title:
                    continue

                # ── Extract sentiment for the requested ticker ────────────
                # Polygon returns insights[] with per-ticker sentiment.
                # We pick the one for the requested ticker; ignore others.
                sentiment: Optional[str] = None
                sentiment_reasoning: Optional[str] = None
                insights = item.get("insights") or []
                if isinstance(insights, list):
                    for ins in insights:
                        if not isinstance(ins, dict):
                            continue
                        if str(ins.get("ticker", "")).upper() == ticker_upper:
                            sentiment = str(ins.get("sentiment") or "").lower() or None
                            sentiment_reasoning = _strip_html(ins.get("sentiment_reasoning")) or None
                            break

                norm: NewsItem = {
                    "id":        str(item.get("id") or title[:60]),
                    "title":     title,
                    "summary":   _strip_html(item.get("description")),
                    "published": str(item.get("published_utc") or ""),
                    "source":    str((item.get("publisher") or {}).get("name") or "Polygon"),
                    "url":       str(item.get("article_url", "")),
                    "tickers":   list(item.get("tickers") or [ticker_upper])[:10],  # cap to 10
                }
                if item.get("image_url"):
                    norm["thumbnail"] = str(item["image_url"])
                if item.get("keywords"):
                    norm["keywords"] = [str(k) for k in item["keywords"][:8]]   # cap to 8
                publisher = item.get("publisher") or {}
                if publisher.get("logo_url"):
                    norm["publisher_logo"] = str(publisher["logo_url"])
                if publisher.get("favicon_url"):
                    norm["publisher_favicon"] = str(publisher["favicon_url"])
                if sentiment:
                    norm["sentiment"] = sentiment
                if sentiment_reasoning:
                    norm["sentiment_reasoning"] = sentiment_reasoning

                out.append(norm)
            except Exception as e:
                logger.debug("polygon news item parse error: %s", e)
                continue

        return out



# ── Finnhub provider (free tier 60 req/min, official Python client) ───────
class FinnhubNewsProvider(NewsProvider):
    """
    Finnhub.io company-news endpoint. Activated when FINNHUB_API_KEY is set
    AND Polygon is NOT set. Free tier: 60 calls/min, 30-day window.

    Library: finnhub-python (https://github.com/Finnhub-Stock-API/finnhub-python)
    """

    name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def fetch(self, ticker: str, limit: int) -> list[NewsItem]:
        limit = _clamp(limit, 1, 50)
        try:
            import finnhub  # finnhub-python — official client
            client = finnhub.Client(api_key=self._api_key)
            # Pull last 30 days of company news
            from datetime import date, timedelta
            today = date.today()
            from_d = (today - timedelta(days=30)).isoformat()
            to_d   = today.isoformat()
            raw = client.company_news(ticker.upper(), _from=from_d, to=to_d) or []
        except Exception as e:
            logger.warning("finnhub fetch failed for %s: %s", ticker, e)
            return []

        out: list[NewsItem] = []
        for item in raw[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                title = _strip_html(item.get("headline"))
                if not title:
                    continue
                # Finnhub returns datetime as Unix epoch seconds
                ts_epoch = item.get("datetime") or 0
                if isinstance(ts_epoch, (int, float)) and ts_epoch > 0:
                    from datetime import datetime, timezone
                    pub_iso = datetime.fromtimestamp(int(ts_epoch), tz=timezone.utc).isoformat()
                else:
                    pub_iso = ""
                norm: NewsItem = {
                    "id":        str(item.get("id") or title[:60]),
                    "title":     title,
                    "summary":   _strip_html(item.get("summary")),
                    "published": pub_iso,
                    "source":    str(item.get("source") or "Finnhub"),
                    "url":       str(item.get("url", "")),
                    "tickers":   [ticker.upper()] + (
                        [str(t).upper() for t in (item.get("related") or "").split(",") if t.strip()][:5]
                    ),
                }
                if item.get("image"):
                    norm["thumbnail"] = str(item["image"])
                if item.get("category"):
                    norm["keywords"] = [str(item["category"])]
                out.append(norm)
            except Exception as e:
                logger.debug("finnhub item parse error: %s", e)
                continue

        return out


# ── Provider factory ──────────────────────────────────────────────────────
def get_news_provider() -> NewsProvider:
    """
    Return the active provider based on environment.

    Priority:
        1. Polygon  (when POLYGON_API_KEY env var is set + non-empty)
        2. Finnhub  (when FINNHUB_API_KEY env var is set + non-empty)
        3. yfinance (default — always available)
    """
    polygon_key = os.getenv("POLYGON_API_KEY", "").strip()
    if polygon_key:
        logger.info("Using PolygonNewsProvider (key found, len=%d)", len(polygon_key))
        return PolygonNewsProvider(polygon_key)

    finnhub_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if finnhub_key:
        logger.info("Using FinnhubNewsProvider (key found, len=%d)", len(finnhub_key))
        return FinnhubNewsProvider(finnhub_key)

    return YFinanceNewsProvider()


def active_provider_name() -> str:
    """Diagnostic helper — which provider is currently active."""
    return get_news_provider().name
