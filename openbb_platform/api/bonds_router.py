# api/bonds_router.py
"""
Sovereign bond / fixed-income router.

Free official sources only:
  - US Treasuries (1m..30y constant-maturity) → FRED (Federal Reserve
    Bank of St. Louis) DGS series. Requires FRED_API_KEY.
  - Eurozone country yields (10Y benchmark only) → ECB Statistical Data
    Warehouse, IRS "long-term interest rate for convergence" series.
    No key required.

NOT covered:
  - Eurozone tenors other than 10Y per country (no free per-country
    feed at multiple tenors; aggregate Eurozone yield curve at multiple
    tenors does exist via the YC dataset but is not exposed here).
  - Corporate bonds (TRACE delayed via FINRA or paid real-time TRACE).
  - Bond CUSIPs / individual issuances.

NEVER fabricates a yield. Returns 404 / 502 / 500 with diagnostic text
when the upstream source is unreachable or returns no data.
"""
from __future__ import annotations

import csv as csvlib
import logging
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException

# Reuse the omnisearch_router's _CACHE helpers — single shared in-memory
# cache, no new layer (per engineering rule #4).
sys.path.insert(0, str(Path(__file__).parent.parent))
from .omnisearch_router import _TTL_SYMBOLOGY, _cache_get, _cache_set  # noqa: E402

logger = logging.getLogger("bonds")
router = APIRouter(prefix="/api/bonds", tags=["bonds"])

# ─────────────────────────────────────────────────────────────────────────
# US Treasuries via FRED — DGS constant-maturity rates
# ─────────────────────────────────────────────────────────────────────────
US_TREASURY_SERIES: dict[str, str] = {
    "1m":  "DGS1MO",
    "3m":  "DGS3MO",
    "6m":  "DGS6MO",
    "1y":  "DGS1",
    "2y":  "DGS2",
    "5y":  "DGS5",
    "10y": "DGS10",
    "20y": "DGS20",
    "30y": "DGS30",
}

# ─────────────────────────────────────────────────────────────────────────
# Eurozone country sovereign 10Y benchmark via ECB IRS convergence series
# ─────────────────────────────────────────────────────────────────────────
EUROZONE_COUNTRIES: dict[str, str] = {
    "AT": "Austria",     "BE": "Belgium",   "CY": "Cyprus",     "DE": "Germany",
    "EE": "Estonia",     "ES": "Spain",     "FI": "Finland",    "FR": "France",
    "GR": "Greece",      "HR": "Croatia",   "IE": "Ireland",    "IT": "Italy",
    "LT": "Lithuania",   "LU": "Luxembourg","LV": "Latvia",     "MT": "Malta",
    "NL": "Netherlands", "PT": "Portugal",  "SI": "Slovenia",   "SK": "Slovakia",
}

ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
ECB_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; SENTRIQ/1.0)",
    "Accept": "text/csv",
}
ECB_TIMEOUT = 15.0
HISTORY_LIMIT = 60  # months of history (≈5 years)


@router.get("/treasuries/{tenor}")
def get_treasury_yield(tenor: str) -> dict[str, Any]:
    """
    US Treasury constant-maturity yield from FRED.

    Tenor ∈ {1m, 3m, 6m, 1y, 2y, 5y, 10y, 20y, 30y}. Returns latest
    yield_pct + recent history (oldest first), the FRED series id, and
    the as-of date. NEVER fabricates: missing FRED observations
    (value = ".") are skipped; if all are missing, returns
    available=false.
    """
    t = tenor.lower()
    series_id = US_TREASURY_SERIES.get(t)
    if not series_id:
        raise HTTPException(
            400,
            f"Tenor {tenor!r} not supported. Valid: {sorted(US_TREASURY_SERIES.keys())}",
        )
    cache_key = f"bonds:us:{t}"
    cached = _cache_get(cache_key, ttl=_TTL_SYMBOLOGY)
    if cached is not None:
        return cached
    try:
        from data_clients import fred_get
        data = fred_get(
            "series/observations",
            series_id=series_id,
            sort_order="desc",
            limit=HISTORY_LIMIT,
        )
        obs = data.get("observations", []) if isinstance(data, dict) else []
        history: list[dict[str, Any]] = []
        for o in obs:
            val = o.get("value")
            if val is None or val == ".":
                continue
            try:
                history.append({"date": o.get("date"), "yield_pct": float(val)})
            except (TypeError, ValueError):
                continue
        history.reverse()  # oldest first
        latest = history[-1] if history else None
        out: dict[str, Any] = {
            "status":     "ok",
            "country":    "US",
            "tenor":      t,
            "yield_pct":  latest["yield_pct"] if latest else None,
            "as_of":      latest["date"]      if latest else None,
            "history":    history,
            "source":     "FRED",
            "series_id":  series_id,
            "available":  latest is not None,
        }
        _cache_set(cache_key, out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("FRED treasury %s", tenor)
        raise HTTPException(500, f"FRED error: {e}")


@router.get("/eurozone/{country}/{tenor}")
def get_eurozone_yield(country: str, tenor: str) -> dict[str, Any]:
    """
    Eurozone country sovereign yield from ECB long-term interest rate
    for convergence series (monthly, 10-year benchmark only).

    Country ∈ AT/BE/CY/DE/EE/ES/FI/FR/GR/HR/IE/IT/LT/LU/LV/MT/NL/PT/SI/SK.
    Tenor must be "10y" — ECB does not publish other tenors per country
    in this series.
    """
    c = (country or "").upper()
    t = (tenor or "").lower()
    if c not in EUROZONE_COUNTRIES:
        raise HTTPException(
            400,
            f"Country {country!r} not supported. Valid: {sorted(EUROZONE_COUNTRIES.keys())}",
        )
    if t != "10y":
        raise HTTPException(
            400,
            f"Tenor {tenor!r} not supported. ECB convergence series only "
            "publishes 10y per Eurozone country. Other tenors require a paid "
            "feed (Bloomberg / Refinitiv).",
        )

    series_id = f"IRS.M.{c}.L.L40.CI.0000.EUR.N.Z"
    cache_key = f"bonds:eu:{c}:{t}"
    cached = _cache_get(cache_key, ttl=_TTL_SYMBOLOGY)
    if cached is not None:
        return cached

    url = f"{ECB_BASE}/IRS/M.{c}.L.L40.CI.0000.EUR.N.Z"
    try:
        with httpx.Client(timeout=ECB_TIMEOUT, headers=ECB_HEADERS) as client:
            r = client.get(url, params={"lastNObservations": str(HISTORY_LIMIT)})
        if r.status_code != 200:
            logger.warning("ECB %s HTTP %s: %s", series_id, r.status_code, r.text[:200])
            raise HTTPException(502, f"ECB returned HTTP {r.status_code}")
        rows = list(csvlib.reader(StringIO(r.text)))
        if not rows or len(rows) < 2:
            raise HTTPException(404, f"ECB returned no data for {c} {t}")
        header = rows[0]
        try:
            tp_idx = header.index("TIME_PERIOD")
            ov_idx = header.index("OBS_VALUE")
        except ValueError:
            raise HTTPException(502, "ECB response shape unexpected (header changed?)")
        history: list[dict[str, Any]] = []
        for row in rows[1:]:
            if len(row) <= max(tp_idx, ov_idx):
                continue
            try:
                history.append({"date": row[tp_idx], "yield_pct": float(row[ov_idx])})
            except (TypeError, ValueError):
                continue
        if not history:
            raise HTTPException(404, f"No usable observations for {c} {t}")
        latest = history[-1]
        out: dict[str, Any] = {
            "status":       "ok",
            "country":      c,
            "country_name": EUROZONE_COUNTRIES[c],
            "tenor":        t,
            "yield_pct":    latest["yield_pct"],
            "as_of":        latest["date"],
            "history":      history,
            "source":       "ECB",
            "series_id":    series_id,
            "available":    True,
        }
        _cache_set(cache_key, out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ECB eurozone %s %s", c, t)
        raise HTTPException(500, f"ECB error: {e}")


@router.get("/coverage")
def coverage() -> dict[str, Any]:
    """List supported (country, tenor) pairs so frontends can drive a picker."""
    return {
        "status": "ok",
        "us_treasuries": sorted(US_TREASURY_SERIES.keys(),
                                key=lambda x: (x[-1], int(x[:-1]) if x[:-1].isdigit() else 0)),
        "eurozone_countries": EUROZONE_COUNTRIES,
        "eurozone_tenors": ["10y"],
        "notes": [
            "Corporate bonds and bond CUSIPs require a paid feed (TRACE / Bloomberg).",
            "Eurozone tenors other than 10Y per country require a paid feed.",
        ],
    }
