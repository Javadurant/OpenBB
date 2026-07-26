"""
Universe Registry — provider-backed symbol discovery for Setup of the Day.

Replaces the "is SKF-B best of a 12-name watchlist, or best in the market?"
ambiguity with an honest, provider-verified universe. Discovers the full listed
universe of an exchange from EODHD's exchange-symbol-list endpoint, maps it to
SENTRIQ's asset-class + yfinance-symbol conventions, caches it daily, and stamps
every result with a coverage label from the project taxonomy.

Provider capability (verified live 2026-07-14, secret-safe probe):
  - EODHD exchange-symbol-list/ST : HTTP 200, 983 rows (946 Common Stock / 27 ETF / 10 FUND)
  - EODHD exchange-symbol-list/US : HTTP 200, 51604 rows (18190 stock / 5860 ETF / 5060 mutual)
  - EODHD eod-bulk-last-day       : HTTP 423 (PLAN-GATED) -> no cheap bulk liquidity feed.

Because bulk EOD is plan-gated, shortlisting uses an INJECTED liquidity function
(yfinance turnover at scan time). The registry itself stays provider-light and is
fully unit-testable without network (discover_exchange takes a `fetcher` seam).

Coverage taxonomy (project rule — never imply more than was verified):
  full_provider_market | full_exchange_market | broad_index_universe |
  broad_provider_universe | curated_fallback | small_watchlist_fallback |
  data_limited | provider_blocked | key_missing | plan_gated
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("universe_registry")

# Where daily discovery caches live (JSON per exchange, timestamped + sourced).
CACHE_DIR = Path(os.getenv("SENTRIQ_UNIVERSE_CACHE", "/tmp/sentriq_universe"))
CACHE_TTL_SEC = 24 * 3600  # symbol lists change slowly; refresh daily

# Exchange → yfinance mapping + provenance. Extend as new exchanges are wired.
EXCHANGE_META: dict[str, dict[str, str]] = {
    "ST": {"suffix": ".ST", "region": "Swedish", "country": "Sweden",
           "currency": "SEK", "mic": "XSTO", "name": "Nasdaq Stockholm"},
    "US": {"suffix": "", "region": "International", "country": "United States",
           "currency": "USD", "mic": "XNAS/XNYS", "name": "US listed (NASDAQ/NYSE)"},
}

# EODHD 'Type' → SENTRIQ asset_class. Anything not mapped is intentionally
# skipped for the equity/etf/fund boxes (preferred, warrants, units, notes, index).
_TYPE_TO_CLASS: dict[str, str] = {
    "Common Stock": "equity",
    "ETF": "etf",
    "FUND": "fund",
    "Mutual Fund": "fund",
}


def asset_class_for(eodhd_type: Optional[str]) -> Optional[str]:
    """Map an EODHD instrument Type to our asset_class, or None to skip it."""
    return _TYPE_TO_CLASS.get((eodhd_type or "").strip())


def to_yf_symbol(code: str, exchange: str) -> str:
    """EODHD Code + exchange → yfinance-compatible ticker (ST codes get '.ST')."""
    suffix = EXCHANGE_META.get(exchange, {}).get("suffix", "")
    return f"{code}{suffix}" if suffix else code


def _eodhd_key() -> Optional[str]:
    k = (os.getenv("EODHD_API_KEY") or "").strip().strip('"').strip("'")
    return k or None


def _default_fetcher(exchange: str) -> list[dict[str, Any]]:
    """Real EODHD exchange-symbol-list call. Raises on any non-200 so the caller
    can classify the failure (key_missing / provider_blocked / plan_gated)."""
    key = _eodhd_key()
    if not key:
        raise PermissionError("EODHD_API_KEY not set")
    url = (f"https://eodhd.com/api/exchange-symbol-list/{exchange}"
           f"?api_token={key}&fmt=json")
    req = urllib.request.Request(url, headers={"User-Agent": "sentriq-universe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _classify_failure(exc: Exception) -> str:
    """Map a discovery failure to an honest coverage label."""
    if isinstance(exc, PermissionError):
        return "key_missing"
    code = getattr(exc, "code", None)
    if code in (402, 403, 423):
        return "plan_gated"
    return "provider_blocked"


def _cache_path(exchange: str) -> Path:
    return CACHE_DIR / f"exchange_{exchange}.json"


def _normalize(rows: list[dict[str, Any]], exchange: str) -> list[dict[str, Any]]:
    """EODHD rows → typed registry records (equity/etf/fund only)."""
    meta = EXCHANGE_META.get(exchange, {})
    out: list[dict[str, Any]] = []
    for row in rows:
        ac = asset_class_for(row.get("Type"))
        if ac is None:
            continue
        code = (row.get("Code") or "").strip()
        if not code:
            continue
        out.append({
            "symbol": to_yf_symbol(code, exchange),   # yfinance ticker
            "provider_symbol": code,                   # EODHD code
            "name": row.get("Name") or code,
            "asset_class": ac,
            "asset_subclass": row.get("Type"),
            "exchange": exchange,
            "mic": meta.get("mic"),
            "country": meta.get("country"),
            "region": meta.get("region"),
            "currency": row.get("Currency") or meta.get("currency"),
            "source_provider": "eodhd",
        })
    return out


def discover_exchange(
    exchange: str,
    *,
    fetcher: Optional[Callable[[str], list[dict[str, Any]]]] = None,
    force: bool = False,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Discover the full listed universe of `exchange` from EODHD, cached daily.

    Returns an honest, self-describing result:
      {exchange, source_provider, universe_source, coverage_label,
       discovered, as_of, cached, symbols:[...], error?}

    coverage_label is `full_exchange_market` only when the provider list truly
    returns; on failure it degrades to key_missing / plan_gated / provider_blocked
    with symbols=[] — the label can never overstate what was verified.
    """
    exchange = exchange.upper()
    fetch = fetcher or _default_fetcher
    now = time.time()

    if use_cache and not force:
        cp = _cache_path(exchange)
        try:
            if cp.exists() and (now - cp.stat().st_mtime) < CACHE_TTL_SEC:
                data = json.loads(cp.read_text())
                data["cached"] = True
                return data
        except Exception:  # noqa: BLE001 - a bad cache must never block discovery
            logger.warning("universe cache read failed for %s", exchange, exc_info=True)

    try:
        rows = fetch(exchange)
    except Exception as exc:  # noqa: BLE001 - classify, never crash the scan
        label = _classify_failure(exc)
        logger.warning("universe discovery failed for %s: %s (%s)",
                       exchange, type(exc).__name__, label)
        return {
            "exchange": exchange, "source_provider": "eodhd",
            "universe_source": "provider_exchange_list", "coverage_label": label,
            "discovered": 0, "as_of": None, "cached": False, "symbols": [],
            "error": f"{type(exc).__name__}",
        }

    symbols = _normalize(rows, exchange)
    result = {
        "exchange": exchange, "source_provider": "eodhd",
        "universe_source": "provider_exchange_list",
        "coverage_label": "full_exchange_market" if symbols else "data_limited",
        "discovered": len(symbols),
        "raw_rows": len(rows),
        "as_of": int(now), "cached": False, "symbols": symbols,
    }
    if use_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _cache_path(exchange).write_text(json.dumps(result))
        except Exception:  # noqa: BLE001 - caching is best-effort
            logger.warning("universe cache write failed for %s", exchange, exc_info=True)
    return result


def shortlist(
    symbols: list[dict[str, Any]],
    asset_class: str,
    *,
    liquidity_fn: Callable[[str], Optional[dict[str, Any]]],
    limit: int = 40,
    min_price: float = 1.0,
    min_turnover: float = 0.0,
    min_history_days: int = 130,
) -> dict[str, Any]:
    """Reduce a discovered universe to a scannable, liquidity-ranked shortlist.

    Because bulk EOD is plan-gated, `liquidity_fn(symbol)` supplies price/turnover/
    history per symbol (yfinance at scan time; a stub in tests). Returns honest
    funnel counts + per-reason exclusions so the API can show discovered → eligible
    → scanned → excluded, and WHY names dropped.
    """
    pool = [s for s in symbols if s.get("asset_class") == asset_class]
    excluded: dict[str, int] = {}
    eligible: list[dict[str, Any]] = []

    def drop(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for s in pool:
        liq = None
        try:
            liq = liquidity_fn(s["symbol"])
        except Exception:  # noqa: BLE001 - a bad symbol must not sink the batch
            drop("provider_error")
            continue
        if not liq:
            drop("no_price_data")
            continue
        price = liq.get("last_price")
        turnover = liq.get("turnover_20d") or 0.0
        hist = liq.get("history_days") or 0
        if price is None or price < min_price:
            drop("below_min_price")
            continue
        if hist < min_history_days:
            drop("insufficient_history")
            continue
        if turnover < min_turnover:
            drop("below_min_liquidity")
            continue
        eligible.append({**s, "last_price": price, "turnover_20d": turnover,
                         "history_days": hist})

    eligible.sort(key=lambda r: r.get("turnover_20d") or 0.0, reverse=True)
    selected = eligible[:limit]
    return {
        "asset_class": asset_class,
        "discovered": len(pool),          # symbols of this class in the exchange list
        "eligible": len(eligible),        # passed price/liquidity/history prefilters
        "scanned": len(selected),         # top-N sent to the setup engine
        "capped_out": max(len(eligible) - len(selected), 0),
        "excluded": excluded,             # reason → count (transparency mandate)
        "symbols": selected,
    }
