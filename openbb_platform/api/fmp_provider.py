"""
api/fmp_provider.py
====================
Phase 2 Deliverable E — FMP migration to new /stable/ endpoints.

FMP retired all /api/v3/ endpoints on Aug 31, 2025 for accounts created
after that date. The new "stable" tier (https://financialmodelingprep.com/stable/)
provides a free quota covering fundamentals, valuation, and analyst signals.

Free-tier endpoints verified live May 19, 2026 with user's key:
  ✓ /stable/quote                  — real-time quote
  ✓ /stable/profile                — company profile, exchange, beta, employees, dividends
  ✓ /stable/key-metrics-ttm        — P/E, P/B, EV/EBITDA, ROE, debt/equity (TTM)
  ✓ /stable/ratios-ttm             — current ratio, gross margin, operating margin, etc.
  ✓ /stable/income-statement       — quarterly and annual income statements
  ✓ /stable/grades                 — analyst rating changes (Buy/Sell/Hold) — 1760 items
  ✓ /stable/ratings-snapshot       — composite analyst rating + score
  ✓ /stable/historical-price-eod   — historical OHLCV (light or full)
  ✓ /stable/earnings               — past + upcoming earnings dates with EPS
  ✓ /stable/dividends              — dividend history with payment dates

Restricted on free tier (HTTP 402):
  ✗ /stable/institutional-ownership/latest
  ✗ /stable/news/stock
  ✗ /stable/news/forex
  → These are covered by yfinance + SEC EDGAR + Polygon (free alternatives)

The endpoint /api/symbol/{ticker}/fmp consumes this module.

Source:  https://site.financialmodelingprep.com/developer/docs (post-2025 spec)
Skill:   /mnt/project/methodology_Statistical_Arbitrage_and_Pair_Trading_Methodology.md
"""
from __future__ import annotations
import logging
import os
from typing import Any, Final, Optional, TypedDict

import httpx

logger = logging.getLogger(__name__)

_BASE_URL: Final = "https://financialmodelingprep.com/stable"
_TIMEOUT_SEC: Final = 15.0


class FMPQuote(TypedDict, total=False):
    symbol:        str
    name:          str
    price:         float
    changesPercentage: float
    dayLow:        float
    dayHigh:       float
    yearHigh:      float
    yearLow:       float
    marketCap:     float
    volume:        int
    avgVolume:     int
    pe:            float
    eps:           float
    timestamp:     int


class FMPRatingSnapshot(TypedDict, total=False):
    symbol:         str
    rating:         str          # A+, A, B+, etc.
    overallScore:   int          # 1-5
    discountedCashFlowScore: int
    returnOnEquityScore:     int
    returnOnAssetsScore:     int
    debtToEquityScore:       int
    priceToEarningsScore:    int
    priceToBookScore:        int


def fmp_available() -> bool:
    """True iff FMP_API_KEY is set and non-empty in the environment."""
    return bool(os.getenv("FMP_API_KEY", "").strip())


def _http_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Internal: GET a FMP stable endpoint. Returns parsed JSON or None on error."""
    key = os.getenv("FMP_API_KEY", "").strip()
    if not key:
        return None

    full_params = dict(params or {})
    full_params["apikey"] = key

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC, follow_redirects=True) as client:
            r = client.get(f"{_BASE_URL}{path}", params=full_params)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status in (402, 403):
            logger.info("FMP /stable%s restricted on free tier (HTTP %d)", path, status)
        else:
            logger.warning("FMP /stable%s HTTP %d", path, status)
        return None
    except Exception as e:
        logger.warning("FMP /stable%s fetch failed: %s", path, e)
        return None


def fetch_quote(ticker: str) -> Optional[FMPQuote]:
    """Real-time quote with P/E, EPS, day range, year range, market cap."""
    data = _http_get("/quote", {"symbol": ticker.upper()})
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def fetch_profile(ticker: str) -> Optional[dict[str, Any]]:
    """Company profile: exchange, sector, industry, employees, IPO date, description."""
    data = _http_get("/profile", {"symbol": ticker.upper()})
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def fetch_key_metrics_ttm(ticker: str) -> Optional[dict[str, Any]]:
    """Trailing-12-month key metrics: P/E, P/B, ROE, ROA, debt/equity, current ratio, etc."""
    data = _http_get("/key-metrics-ttm", {"symbol": ticker.upper()})
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def fetch_ratios_ttm(ticker: str) -> Optional[dict[str, Any]]:
    """Trailing-12-month financial ratios: margins, returns, liquidity, leverage."""
    data = _http_get("/ratios-ttm", {"symbol": ticker.upper()})
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def fetch_ratings_snapshot(ticker: str) -> Optional[FMPRatingSnapshot]:
    """Composite analyst rating snapshot with per-component scores."""
    data = _http_get("/ratings-snapshot", {"symbol": ticker.upper()})
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def fetch_grades_recent(ticker: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Recent analyst rating changes (last N): firm, from-grade, to-grade, date."""
    data = _http_get("/grades", {"symbol": ticker.upper()})
    if not isinstance(data, list):
        return []
    return data[:limit]


def fetch_earnings(ticker: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Past + upcoming earnings dates with EPS estimates and actuals."""
    data = _http_get("/earnings", {"symbol": ticker.upper(), "limit": limit})
    if not isinstance(data, list):
        return []
    return data[:limit]


def fetch_dividends(ticker: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Recent dividend history with payment dates and amounts."""
    data = _http_get("/dividends", {"symbol": ticker.upper(), "limit": limit})
    if not isinstance(data, list):
        return []
    return data[:limit]


def fetch_insider_trades(ticker: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """
    Recent insider transactions via Form 4 (alternative path; SEC EDGAR is primary).
    Some FMP free-tier accounts can access this, others get HTTP 402.
    """
    data = _http_get("/insider-trading", {"symbol": ticker.upper(), "limit": limit})
    if not isinstance(data, list):
        return []
    return data[:limit]


def fetch_aggregate(ticker: str) -> dict[str, Any]:
    """
    One-shot aggregate fetch for the /api/symbol/{ticker}/fmp endpoint.

    Returns a dict with all working free-tier endpoints in parallel-friendly shape.
    Endpoints that fail (key missing, ticker unknown, restricted) return null cleanly.
    """
    if not fmp_available():
        return {
            "status":          "unavailable",
            "reason":          "FMP_API_KEY not set",
            "quote":           None,
            "profile":         None,
            "key_metrics":     None,
            "ratios":          None,
            "rating":          None,
            "recent_grades":   [],
            "earnings":        [],
            "dividends":       [],
        }

    sym = ticker.upper().strip()
    return {
        "status":          "ok",
        "symbol":          sym,
        "provider":        "fmp-stable",
        "quote":           fetch_quote(sym),
        "profile":         fetch_profile(sym),
        "key_metrics":     fetch_key_metrics_ttm(sym),
        "ratios":          fetch_ratios_ttm(sym),
        "rating":          fetch_ratings_snapshot(sym),
        "recent_grades":   fetch_grades_recent(sym, limit=6),
        "earnings":        fetch_earnings(sym, limit=5),
        "dividends":       fetch_dividends(sym, limit=5),
    }
