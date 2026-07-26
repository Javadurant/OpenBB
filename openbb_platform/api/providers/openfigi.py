"""
OpenFIGI provider — ISIN → FIGI resolution.

Free public API at https://api.openfigi.com/v3/mapping
Rate limit: 25 req/min unauth, 250 req/min with key.
Set OPENFIGI_API_KEY env var if you have one.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib import (
    error as urlerror,
    request as urlrequest,
)

logger = logging.getLogger("openfigi")
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_KEY = os.getenv("OPENFIGI_API_KEY", "").strip() or None

# 24h TTL cache — FIGIs do not change.
_CACHE: dict[str, Any] = {}
_TTL_24H = 24 * 60 * 60

def _cache_get(k: str) -> Any:
    item = _CACHE.get(k)
    if not item: return None
    ts, v = item
    if time.time() - ts > _TTL_24H:
        _CACHE.pop(k, None); return None
    return v

def _cache_set(k: str, v: Any) -> None:
    _CACHE[k] = (time.time(), v)

def isin_to_figi(isin: str, exch_code: str | None = None) -> dict[str, Any]:
    """Resolve an ISIN to its primary FIGI. Returns dict with figi/error.

    OpenFIGI returns an array of FIGIs (one per venue). We pick the
    one matching the requested exchange when provided, else the first
    composite FIGI (the cross-venue identifier).
    """
    if not isin or len(isin) < 10:
        return {"figi": None, "error": "invalid_isin"}

    cache_key = f"figi:{isin}:{exch_code or '*'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    body: list[dict[str, str]] = [{"idType": "ID_ISIN", "idValue": isin}]
    if exch_code:
        body[0]["exchCode"] = exch_code

    headers = {"Content-Type": "application/json"}
    if OPENFIGI_KEY:
        headers["X-OPENFIGI-APIKEY"] = OPENFIGI_KEY

    try:
        req = urlrequest.Request(
            OPENFIGI_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:
        body_txt = ""
        try: body_txt = e.read().decode("utf-8")[:200]
        except Exception: pass
        out = {"figi": None, "error": f"http_{e.code}", "detail": body_txt}
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        return {"figi": None, "error": "request_failed", "detail": str(e)[:200]}

    if not payload or not isinstance(payload, list):
        return {"figi": None, "error": "empty_response"}

    item0 = payload[0]
    if "error" in item0:
        out = {"figi": None, "error": item0["error"]}
        _cache_set(cache_key, out)
        return out

    matches = item0.get("data") or []
    if not matches:
        out = {"figi": None, "error": "no_match"}
        _cache_set(cache_key, out)
        return out

    # Prefer composite FIGI (cross-venue) — pick first match
    primary = matches[0]
    out = {
        "figi":            primary.get("figi"),
        "composite_figi":  primary.get("compositeFIGI"),
        "share_class_figi":primary.get("shareClassFIGI"),
        "ticker":          primary.get("ticker"),
        "exch_code":       primary.get("exchCode"),
        "security_type":   primary.get("securityType"),
        "market_sector":   primary.get("marketSector"),
        "name":            primary.get("name"),
        "all_matches":     len(matches),
    }
    _cache_set(cache_key, out)
    return out


def isin_to_figi_sync(isin: str, exch_code: str | None = None) -> str | None:
    """Sync wrapper used by older router code paths. Returns just the FIGI string."""
    result = isin_to_figi(isin, exch_code)
    return result.get("figi")
