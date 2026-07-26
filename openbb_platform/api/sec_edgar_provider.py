"""
api/sec_edgar_provider.py
==========================
Phase 2 Deliverable C — SEC EDGAR free news/filings provider.

Production-grade alternative to MT Newswires for material events.
Uses the SEC's free public APIs — no key required, no paid subscription.

What it returns:
- 8-K filings: material events (M&A, executive changes, earnings flash)
- 10-Q / 10-K: quarterly/annual reports
- Form 4: insider transactions (executive buys/sells)
- DEF 14A: proxy statements

The endpoint /api/symbol/{ticker}/filings consumes this module.

Rate limit: SEC asks for ≤ 10 req/sec with a descriptive User-Agent.
We use a single Client with persistent connections and per-process CIK cache.

Sources:
- https://www.sec.gov/files/company_tickers.json  (ticker → CIK map)
- https://data.sec.gov/submissions/CIK{cik}.json   (recent filings)

References used in design:
- SEC EDGAR API guide: https://www.sec.gov/edgar/sec-api-documentation
- SEC fair access policy: https://www.sec.gov/os/accessing-edgar-data
"""
from __future__ import annotations
import logging
import os
import re
import threading
import time
from typing import Any, Final, Optional, TypedDict

import httpx

logger = logging.getLogger(__name__)

# SEC EDGAR REQUIRES a descriptive User-Agent or it returns 403.
# Tied to a project email for identification; never hide identity.
_USER_AGENT: Final = "SENTRIQ Research/2.0 javadurant@gmail.com"
_HEADERS: Final = {
    "User-Agent": _USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL_TEMPLATE: Final = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_URL_TEMPLATE: Final = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_doc}"

# Form-type human labels
_FORM_LABELS: Final = {
    "8-K":  "Material Event",
    "10-K": "Annual Report",
    "10-Q": "Quarterly Report",
    "4":    "Insider Trade",
    "13F-HR": "Institutional Holdings",
    "DEF 14A": "Proxy Statement",
    "S-1":  "IPO Registration",
    "SC 13G": "Beneficial Ownership ≥5%",
    "SC 13D": "Activist Ownership",
}

# Per-process CIK cache (ticker → CIK string).
# The full ticker map is ~600KB JSON — load once, hold for the life of the process.
_cik_cache: dict[str, str] = {}
_cik_cache_lock = threading.Lock()
_cik_cache_loaded_at: float = 0.0
_CIK_CACHE_TTL: Final = 86400.0  # 24 hours


class SECFiling(TypedDict, total=False):
    """Normalized SEC filing record returned to the frontend."""
    accession_number:    str
    form_type:           str
    form_label:          str
    filed_date:          str     # YYYY-MM-DD
    period_of_report:    str
    primary_document:    str
    primary_doc_desc:    str
    filing_url:          str
    items:               str     # 8-K items, e.g. "1.01, 2.02"


def _http_get(url: str, *, timeout: float = 15.0) -> Optional[dict[str, Any]]:
    """Internal: GET an SEC JSON endpoint, returning parsed JSON or None."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers=_HEADERS)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.warning("SEC EDGAR HTTP %s for %s", e.response.status_code, url[:80])
        return None
    except Exception as e:
        logger.warning("SEC EDGAR fetch failed %s: %s", url[:80], e)
        return None


def _load_cik_map() -> dict[str, str]:
    """Load the full ticker → CIK map, caching results in-process."""
    global _cik_cache_loaded_at
    with _cik_cache_lock:
        # Honor cache if fresh
        now = time.time()
        if _cik_cache and (now - _cik_cache_loaded_at) < _CIK_CACHE_TTL:
            return _cik_cache

        data = _http_get(_TICKERS_URL, timeout=30.0)
        if not isinstance(data, dict):
            return _cik_cache  # return whatever's already there

        # JSON structure: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        new_map: dict[str, str] = {}
        for _, entry in data.items():
            if not isinstance(entry, dict):
                continue
            t = str(entry.get("ticker", "")).upper().strip()
            c = str(entry.get("cik_str", "")).strip()
            if t and c:
                new_map[t] = c.zfill(10)

        _cik_cache.clear()
        _cik_cache.update(new_map)
        _cik_cache_loaded_at = now
        logger.info("Loaded %d ticker→CIK mappings from SEC EDGAR", len(new_map))
        return _cik_cache


def lookup_cik(ticker: str) -> Optional[str]:
    """Return the 10-digit CIK for a ticker symbol, or None if not found."""
    if not ticker:
        return None
    ticker_upper = ticker.upper().strip()
    cik_map = _load_cik_map()
    return cik_map.get(ticker_upper)


def fetch_recent_filings(
    ticker: str,
    *,
    form_types: Optional[list[str]] = None,
    limit: int = 15,
) -> list[SECFiling]:
    """
    Fetch most recent SEC filings for a ticker.

    Args:
        ticker: Stock symbol (e.g. 'AAPL')
        form_types: Filter by form type (default: 8-K, 10-K, 10-Q, 4, 13F-HR)
        limit: Maximum filings to return (default 15, max 50)

    Returns:
        Normalized SECFiling records, newest first.
        Empty list if ticker not found or SEC unreachable.
    """
    if form_types is None:
        form_types = ["8-K", "10-K", "10-Q", "4", "13F-HR", "DEF 14A", "SC 13G", "SC 13D"]
    limit = max(1, min(int(limit), 50))

    cik = lookup_cik(ticker)
    if cik is None:
        logger.info("SEC EDGAR: no CIK for ticker %s", ticker)
        return []

    sub_url = _SUBMISSIONS_URL_TEMPLATE.format(cik=cik)
    data = _http_get(sub_url)
    if not data:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms     = recent.get("form", [])
    dates     = recent.get("filingDate", [])
    reports   = recent.get("reportDate", [])
    descs     = recent.get("primaryDocDescription", [])
    accs      = recent.get("accessionNumber", [])
    docs      = recent.get("primaryDocument", [])
    items_arr = recent.get("items", [])

    cik_int = int(cik)
    out: list[SECFiling] = []
    seen = 0
    for i in range(min(len(forms), 100)):  # SEC returns up to ~1000; scan first 100
        if forms[i] not in form_types:
            continue
        acc = accs[i] if i < len(accs) else ""
        acc_no_dashes = acc.replace("-", "")
        primary_doc = docs[i] if i < len(docs) else ""
        if not (acc_no_dashes and primary_doc):
            continue

        rec: SECFiling = {
            "accession_number": acc,
            "form_type":        forms[i],
            "form_label":       _FORM_LABELS.get(forms[i], forms[i]),
            "filed_date":       dates[i] if i < len(dates) else "",
            "period_of_report": reports[i] if i < len(reports) else "",
            "primary_document": primary_doc,
            "primary_doc_desc": descs[i] if i < len(descs) else forms[i],
            "filing_url":       _FILING_URL_TEMPLATE.format(
                cik_int=cik_int, acc_no_dashes=acc_no_dashes, primary_doc=primary_doc
            ),
        }
        # 8-K items list (e.g. "1.01, 2.02, 9.01")
        if i < len(items_arr) and items_arr[i]:
            rec["items"] = str(items_arr[i])

        out.append(rec)
        seen += 1
        if seen >= limit:
            break

    return out


def fetch_insider_transactions(ticker: str, *, limit: int = 20) -> list[SECFiling]:
    """Form 4 only — insider buys/sells. Heavily used for trader analytics."""
    return fetch_recent_filings(ticker, form_types=["4"], limit=limit)


def fetch_material_events(ticker: str, *, limit: int = 10) -> list[SECFiling]:
    """8-K only — material events (M&A, executive changes, earnings flash)."""
    return fetch_recent_filings(ticker, form_types=["8-K"], limit=limit)
