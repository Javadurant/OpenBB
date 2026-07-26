# api/providers/esg.py
"""
ESG ratings provider — INTEGRATION SLOT.

Yahoo Finance no longer reliably exposes ESG scores; production-quality
ESG coverage requires a commercial feed. The three common options:

  - MSCI ESG          (https://www.msci.com/our-solutions/esg-investing)
  - Sustainalytics    (https://www.sustainalytics.com)
  - Refinitiv ESG     (https://www.refinitiv.com/en/sustainable-finance)

Configure with:
    ESG_PROVIDER=msci | sustainalytics | refinitiv
    ESG_API_KEY=<your-key>

Without a configured provider, lookup_esg() returns None and the caller
falls back to yfinance.sustainability (best-effort) and finally to a
provider_required marker. NEVER fabricates an ESG score, percentile,
or controversy level.

The integration shape (env-keyed, single lookup_esg entry point, return
a normalized dict) is in place so a future commit can add a real client
without touching the router.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("esg")

PROVIDER_NAMES: dict[str, str] = {
    "msci":           "MSCI ESG",
    "sustainalytics": "Sustainalytics",
    "refinitiv":      "Refinitiv ESG",
}


def configured_provider() -> str | None:
    """Return the configured provider's display name, or None when unset."""
    p = (os.getenv("ESG_PROVIDER") or "").strip().lower()
    return PROVIDER_NAMES.get(p)


def lookup_esg(symbol: str) -> dict[str, Any] | None:
    """
    Look up ESG metrics for a symbol against the configured provider.

    Returns a dict with normalized keys when the provider has a rating,
    otherwise None. Never raises.

    Normalized response shape (every field optional, all numeric):
        {
            "total":       float | None,   # composite ESG score
            "environment": float | None,
            "social":      float | None,
            "governance":  float | None,
            "controversy": float | None,   # controversy level (0–5 scale)
            "percentile":  float | None,   # peer-group percentile
            "rating":      str   | None,   # letter rating (e.g. "AA", "BBB")
            "as_of":       str   | None,   # ISO date of the rating
        }

    Currently no provider is wired — the function returns None whenever
    ESG_PROVIDER is unset or set to a value with no implementation yet.
    """
    if not symbol or not isinstance(symbol, str):
        return None
    provider = configured_provider()
    if provider is None:
        return None
    logger.info(
        "ESG_PROVIDER=%s configured but no client implementation yet "
        "(symbol=%s) — returning None",
        provider, symbol,
    )
    return None
