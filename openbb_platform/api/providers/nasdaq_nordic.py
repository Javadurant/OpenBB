# api/providers/nasdaq_nordic.py
"""
Nasdaq Nordic instrument-list provider.

Resolves a Nordic ticker (e.g. EVO.ST, VOLV-B.ST, KAMBI.ST) to its market
segment ("main" | "first_north" | "other") and ISIN by downloading the
official Nasdaq Nordic shares screener at
https://api.nasdaq.com/api/nordic/screener/shares?category=...&tableonly=true
and caching the merged result on disk for 7 days.

The screener returns one row per listed instrument with fields:
    {symbol, fullName, currency, isin, orderbookId, assetClass, ...}

We index by yfinance-style ticker, derived per currency:
    SEK → ".ST"   (Stockholm)
    DKK → ".CO"   (Copenhagen)
    ISK → ".IC"   (Iceland)
    EUR → not derived (Helsinki/Tallinn/Riga/Vilnius all use EUR; the
           micCode field is empty in the screener feed so we skip these
           rather than guess a suffix).

The transformation `symbol.replace(" ", "-") + suffix` is verified against
the data: e.g. "VOLV B" → "VOLV-B.ST", "ASSA B" → "ASSA-B.ST",
"ALVO SDB" → "ALVO-SDB.ST", "EVO" → "EVO.ST".

NEVER fabricates: if the index has no entry for a ticker — because the
ticker is delisted, very new, or simply outside Nasdaq Nordic — the
function returns ("unknown", None). Network failures are logged via the
module logger and degrade to ("unknown", None); they never raise.

The Nasdaq-managed Nordic markets do NOT include Spotlight Stock Market
(run by Spotlight Group AB). Tickers that trade only on Spotlight will
fall through to ("unknown", None) here.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger("nasdaq_nordic")

API_BASE = "https://api.nasdaq.com/api/nordic"
SCREENER_PATH = "/screener/shares"

# Nasdaq Nordic screener category names (verified against
# nasdaq.com/sv/european-market-activity/shares page config, 2026-05).
CATEGORIES: tuple[str, ...] = ("MAIN_MARKET", "FIRST_NORTH", "OTHERS")
SEGMENT_BY_CATEGORY: dict[str, str] = {
    "MAIN_MARKET": "main",
    "FIRST_NORTH": "first_north",
    "OTHERS":      "other",
}

# Currency → yfinance suffix. EUR is intentionally excluded — see module
# docstring.
CURRENCY_TO_SUFFIX: dict[str, str] = {
    "SEK": ".ST",
    "DKK": ".CO",
    "ISK": ".IC",
}

CACHE_DIR = Path(os.getenv("SENTRIQ_CACHE_DIR", "/tmp"))
CACHE_FILE = CACHE_DIR / "sentriq_nasdaq_nordic.json"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days — instrument lists move slowly

HTTP_TIMEOUT = 15.0
HTTP_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; SENTRIQ/1.0)",
    "Accept": "application/json",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/sv/european-market-activity/shares",
}

# Module-level memory cache. None = not loaded yet; {} = loaded but empty.
_INDEX: dict[str, dict[str, str | None]] | None = None


def _yf_ticker_from(symbol: str, currency: str) -> str | None:
    """Convert Nasdaq Nordic API symbol + currency to a yfinance ticker."""
    suffix = CURRENCY_TO_SUFFIX.get((currency or "").upper())
    if not suffix:
        return None
    base = (symbol or "").strip().replace(" ", "-")
    if not base:
        return None
    return f"{base}{suffix}".upper()


def _fetch_category(category: str) -> list[dict]:
    """GET one screener category. Returns rows, or [] on any failure."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
            r = client.get(
                f"{API_BASE}{SCREENER_PATH}",
                params={"category": category, "tableonly": "true"},
            )
        if r.status_code != 200:
            logger.warning(
                "Nasdaq Nordic %s HTTP %s: %s",
                category, r.status_code, r.text[:200],
            )
            return []
        body = r.json()
        rcode = (body.get("status") or {}).get("rCode")
        if rcode != 200:
            logger.warning("Nasdaq Nordic %s body status: %s", category, body.get("status"))
            return []
        rows = ((body.get("data") or {}).get("instrumentListing") or {}).get("rows") or []
        if not isinstance(rows, list):
            return []
        return rows
    except Exception as e:
        logger.warning("Nasdaq Nordic %s fetch failed: %s", category, e)
        return []


def _build_index() -> dict[str, dict[str, str | None]]:
    """Hit all three categories and build the ticker -> {segment, isin} index."""
    idx: dict[str, dict[str, str | None]] = {}
    for cat in CATEGORIES:
        rows = _fetch_category(cat)
        seg = SEGMENT_BY_CATEGORY[cat]
        for row in rows:
            sym = row.get("symbol")
            ccy = row.get("currency")
            isin = (row.get("isin") or "").strip() or None
            yt = _yf_ticker_from(sym, ccy)
            if not yt:
                continue
            # First write wins; same ticker shouldn't appear in two categories.
            if yt not in idx:
                idx[yt] = {"segment": seg, "isin": isin}
    logger.info("Nasdaq Nordic index built: %d instruments", len(idx))
    return idx


def _read_disk() -> dict[str, dict[str, str | None]] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open() as f:
            blob = json.load(f)
        ts = float(blob.get("fetched_at", 0))
        age = time.time() - ts
        if age > CACHE_TTL_SECONDS:
            logger.info("Nasdaq Nordic disk cache stale (%.1f hours)", age / 3600)
            return None
        instruments = blob.get("instruments")
        if not isinstance(instruments, dict):
            return None
        return instruments
    except Exception as e:
        logger.warning("Nasdaq Nordic disk cache read failed: %s", e)
        return None


def _write_disk(index: dict[str, dict[str, str | None]]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump({"fetched_at": time.time(), "instruments": index}, f)
        tmp.replace(CACHE_FILE)  # atomic on POSIX
    except Exception as e:
        logger.warning("Nasdaq Nordic disk cache write failed: %s", e)


def _load_index() -> dict[str, dict[str, str | None]]:
    """Lazy load: memory → disk → network. Caches all hits in memory."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    disk = _read_disk()
    if disk is not None:
        _INDEX = disk
        return _INDEX
    fresh = _build_index()
    _INDEX = fresh
    if fresh:
        _write_disk(fresh)
    return _INDEX


def lookup_segment(ticker: str) -> tuple[str, str | None]:
    """
    Look up a Nordic ticker's market segment and ISIN.

    Returns:
        (segment, isin) where segment ∈ {"main", "first_north", "other", "unknown"}.
        isin is the 12-char ISIN string or None when the ticker isn't in the index.

    Never raises.
    """
    if not ticker or not isinstance(ticker, str):
        return ("unknown", None)
    try:
        idx = _load_index()
    except Exception as e:
        logger.warning("Nasdaq Nordic index load failed: %s", e)
        return ("unknown", None)
    rec = idx.get(ticker.strip().upper())
    if not rec:
        return ("unknown", None)
    segment = rec.get("segment") or "unknown"
    isin = rec.get("isin") or None
    return (segment, isin)


def force_refresh() -> int:
    """Force a re-download of the screener data. Returns instrument count."""
    global _INDEX
    fresh = _build_index()
    _INDEX = fresh
    if fresh:
        _write_disk(fresh)
    return len(fresh)
