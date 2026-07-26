"""
api/polygon_ohlcv_provider.py
==============================
Phase 2 Deliverable B (continued) — Polygon OHLCV backup for yfinance.

When yfinance fails (rate limit, network, ticker missing) OR when the user
explicitly requests production-grade data, this module pulls daily aggregates
from Polygon /v2/aggs.

Activated when POLYGON_API_KEY env var is set. Falls back to yfinance silently.

Functions:
    fetch_polygon_ohlcv(ticker, days=120)  → DataFrame[date, open, high, low, close, volume]
    fetch_polygon_prev_close(ticker)        → dict{close, volume, vwap, change_pct}
    polygon_available()                     → bool
"""
from __future__ import annotations
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Final, Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_BASE_URL: Final = "https://api.polygon.io"


def polygon_available() -> bool:
    """Return True iff POLYGON_API_KEY env var is set and non-empty."""
    return bool(os.getenv("POLYGON_API_KEY", "").strip())


def _api_key() -> str:
    key = os.getenv("POLYGON_API_KEY", "").strip()
    if not key:
        raise RuntimeError("POLYGON_API_KEY not set")
    return key


def fetch_polygon_ohlcv(ticker: str, days: int = 120) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV bars from Polygon for the last `days` calendar days.

    Returns a DataFrame indexed by date with columns:
        open, high, low, close, volume, vwap, trades

    Returns None on failure (caller should fall back to yfinance).
    """
    if not polygon_available():
        return None

    ticker = ticker.upper().strip()
    if not ticker:
        return None

    days = max(1, min(days, 730))   # Polygon free tier is 2-year history
    end   = date.today()
    start = end - timedelta(days=days)

    url = f"{_BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"adjusted": "true", "sort": "asc", "apiKey": _api_key()})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("polygon OHLCV HTTP %s for %s: %s",
                       e.response.status_code, ticker, e.response.text[:120])
        return None
    except Exception as e:
        logger.warning("polygon OHLCV fetch failed for %s: %s", ticker, e)
        return None

    results = data.get("results") or []
    if not results:
        return None

    # Polygon aggregates: t=ms epoch, o,h,l,c=OHLC, v=volume, vw=vwap, n=trades
    rows = []
    for r in results:
        try:
            ts_ms = int(r.get("t") or 0)
            if ts_ms <= 0:
                continue
            rows.append({
                "date":   datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date(),
                "open":   float(r.get("o") or 0),
                "high":   float(r.get("h") or 0),
                "low":    float(r.get("l") or 0),
                "close":  float(r.get("c") or 0),
                "volume": int(r.get("v") or 0),
                "vwap":   float(r.get("vw") or 0),
                "trades": int(r.get("n") or 0),
            })
        except (TypeError, ValueError) as e:
            logger.debug("polygon OHLCV row parse error: %s", e)
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows).set_index("date").sort_index()
    return df


def fetch_polygon_prev_close(ticker: str) -> Optional[dict[str, Any]]:
    """
    Fetch the previous trading day's close + volume + VWAP from Polygon.
    Lighter-weight call than fetch_polygon_ohlcv when only the last bar is needed.

    Returns:
        { close, volume, vwap, open, high, low, change_pct, trades, ts_ms }
        or None on failure.
    """
    if not polygon_available():
        return None

    ticker = ticker.upper().strip()
    if not ticker:
        return None

    url = f"{_BASE_URL}/v2/aggs/ticker/{ticker}/prev"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params={"adjusted": "true", "apiKey": _api_key()})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("polygon prev HTTP %s for %s", e.response.status_code, ticker)
        return None
    except Exception as e:
        logger.warning("polygon prev fetch failed for %s: %s", ticker, e)
        return None

    results = data.get("results") or []
    if not results:
        return None

    bar = results[0]
    try:
        open_  = float(bar.get("o") or 0)
        close_ = float(bar.get("c") or 0)
        return {
            "ticker":     ticker,
            "open":       open_,
            "high":       float(bar.get("h") or 0),
            "low":        float(bar.get("l") or 0),
            "close":      close_,
            "volume":     int(bar.get("v") or 0),
            "vwap":       float(bar.get("vw") or 0),
            "trades":     int(bar.get("n") or 0),
            "ts_ms":      int(bar.get("t") or 0),
            "change_pct": (close_ - open_) / open_ * 100 if open_ > 0 else 0.0,
        }
    except (TypeError, ValueError) as e:
        logger.warning("polygon prev parse error for %s: %s", ticker, e)
        return None


def fetch_ohlcv_with_fallback(ticker: str, days: int = 120) -> tuple[Optional[pd.DataFrame], str]:
    """
    Convenience: try Polygon first (if key set), fall back to yfinance.

    Returns:
        (df, provider_name) where provider_name in {'polygon', 'yfinance', 'none'}
    """
    if polygon_available():
        df = fetch_polygon_ohlcv(ticker, days)
        if df is not None and len(df) > 0:
            return df, "polygon"

    # yfinance fallback
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker.upper())
        hist = tk.history(period=f"{days}d", auto_adjust=True)
        if hist is None or len(hist) == 0:
            return None, "none"
        # Standardize column names
        hist = hist.rename(columns={
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })
        # Convert index to date type
        hist.index = pd.to_datetime(hist.index).date
        hist.index.name = "date"
        return hist[["open", "high", "low", "close", "volume"]], "yfinance"
    except Exception as e:
        logger.warning("yfinance OHLCV fallback failed for %s: %s", ticker, e)
        return None, "none"
