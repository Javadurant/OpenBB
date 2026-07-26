# api/providers/funds_library.py
"""
Mutual fund / UCITS data provider — INTEGRATION SLOT.

The European fund landscape uses ISIN as the primary identifier. yfinance
covers many UCITS but with significant gaps — newer share classes,
institutional accumulation tranches, sector funds, and most non-USD-listed
shares often return nothing.

Production-quality UCITS coverage requires a paid feed. The common options:
  - FundsLibrary       (https://www.fundslibrary.co.uk)   — UK-strong
  - FE fundinfo        (https://www.fefundinfo.com)       — broader EU
  - Morningstar Direct (https://www.morningstar.com/products/direct)

Configure with:
    FUNDS_PROVIDER=fundslibrary | fefundinfo | morningstar
    FUNDS_API_KEY=...

Without a configured provider, lookup_fund_by_isin() returns None and the
caller marks `provider_required` on the response. NEVER fabricates NAV,
returns, expense ratios, or AUM. NEVER scrapes Morningstar — that's a
legal grey area called out in the handoff and explicitly out of scope.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("funds_library")

PROVIDER_NAMES: dict[str, str] = {
    "fundslibrary": "FundsLibrary",
    "fefundinfo":   "FE fundinfo",
    "morningstar":  "Morningstar Direct",
}


def configured_provider() -> str | None:
    """Return the configured provider's display name, or None when unset."""
    p = (os.getenv("FUNDS_PROVIDER") or "").strip().lower()
    return PROVIDER_NAMES.get(p)


def _valid_isin(isin: str) -> bool:
    if not isinstance(isin, str):
        return False
    s = isin.strip().upper()
    return len(s) == 12 and s.isalnum()


def lookup_fund_by_isin(isin: str) -> dict[str, Any] | None:
    """
    Look up a UCITS fund by ISIN against the configured provider.

    Returns a dict with normalized fund fields when the provider has the
    fund, otherwise None. Never raises.

    Currently no provider is wired — the function returns None whenever
    FUNDS_PROVIDER is unset or set to a value with no implementation yet.
    The integration shape (env-keyed, per-provider) is in place so a
    future commit can add a real client without touching the router.
    """
    if not _valid_isin(isin):
        return None
    provider = configured_provider()
    if provider is None:
        return None
    logger.info(
        "FUNDS_PROVIDER=%s configured but no client implementation yet "
        "(ISIN=%s) — returning None",
        provider, isin,
    )
    return None
