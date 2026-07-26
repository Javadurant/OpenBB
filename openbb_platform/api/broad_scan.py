# api/broad_scan.py
"""
Broad market scan — the "946/18k, not a 12-name watchlist" answer (v3.8).

Fixes SENTRIQ's biggest coverage inefficiency: Setup of the Day ranks only the
curated SETUP_UNIVERSE, so "best setup" meant "best of ~12 names", and the
universe_registry.shortlist() liquidity path was never wired because a per-symbol
liquidity probe over 946+ (Swedish) / 18k+ (US) symbols would be minutes of
yfinance round-trips per request.

THE WIRING (efficient by construction):
  1. discover_exchange(exch)   → the full listed universe (946 ST / 18k US),
                                 the honest coverage denominator (yfinance tickers).
  2. run_screener(market)      → ONE call returns the whole market's liquidity
                                 (close × avg-volume = turnover) — NO 946 probes.
  3. shortlist(..., liquidity_fn=dict.get) → rank the discovered universe by that
                                 bulk turnover, take the top-N liquid tranche
                                 (this also drops the sub-0.01-SEK penny junk).
  4. _fetch_and_score(...)      → SENTRIQ's OWN setup_scanner grades the tranche
                                 A / B / C (engine reuse — never re-implemented).

Result: real Grade A (HIGHEST CONVICTION) / Grade B (SOLID ALIGNMENT) surfaced
from the broad market, cached, without the per-request 946-probe bottleneck.

Every external dependency is injectable (discover_fn / screener_fn / score_fn) so
the pipeline is unit-testable with zero network (universe_registry's fetcher-seam
philosophy). No invented domain values — liquidity is the provider's own volume,
grades are the existing scanner's, thresholds are 0 (pure liquidity ranking)
unless the caller supplies them.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .tvremix_client import from_tv_symbol, run_screener
from .universe_registry import discover_exchange, shortlist

logger = logging.getLogger("broad-scan")

# region → (EODHD exchange code, tvremix screener market)
_REGION_MAP = {
    "Swedish": ("ST", "sweden"),
    "International": ("US", "america"),
}
_MAX_WORKERS = 8
_DEFAULT_DEPTH = 100          # symbols actually graded (liquid tranche)
_DEFAULT_SCREEN_PAGE = 300    # screener rows pulled for the bulk liquidity map
# Sentinel so shortlist's history prefilter is a no-op: the real >=60-bar history
# check lives inside _fetch_and_score, which drops thin-history names honestly.
_HISTORY_UNKNOWN = 10_000

_GRADE_RANK = {"A": 0, "B": 1, "C": 2}

# Compact projection of the (huge) SetupResult for a market-wide list payload.
_SLIM_KEYS = (
    "symbol", "name", "region", "asset_class", "grade", "score", "classification",
    "setup_type", "risk_level", "confidence", "last_price", "sector",
    "entry", "stop", "target", "reward_risk", "invalidation",
    "daily_trend", "weekly_trend", "monthly_trend", "rsi_14",
    "strongest_supporting", "strongest_opposing", "market_regime",
    "expected_target_date", "earliest_target_date", "latest_target_date",
    "timing_reliability", "source", "as_of", "proxy", "conflicts",
    "sub_scores", "sub_scores_max",
)


def _turnover(row: dict) -> Optional[float]:
    """Bulk liquidity proxy = price × average daily volume, from one screener row.
    Prefers the 10-day average volume; falls back to the day's volume. None when
    the row lacks the fields (never fabricated)."""
    close = row.get("close")
    vol = row.get("average_volume_10d_calc")
    if not isinstance(vol, (int, float)):
        vol = row.get("volume")
    if not isinstance(close, (int, float)) or not isinstance(vol, (int, float)):
        return None
    if close <= 0 or vol <= 0:
        return None
    return float(close) * float(vol)


def _build_liquidity_map(rows: list) -> dict:
    """tvremix screener rows → {yfinance_symbol: {last_price, turnover_20d,
    history_days}} for the shortlist liquidity_fn. Only rows that map cleanly
    back to a yfinance ticker (main-market equities) are kept."""
    liq: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if (row.get("type") or "").strip().lower() not in ("", "stock"):
            continue  # equities only for the A/B/C equity scan
        yf = from_tv_symbol(row.get("symbol") or "")
        if not yf:
            continue
        t = _turnover(row)
        if t is None:
            continue
        prev = liq.get(yf)
        if prev is None or t > prev["turnover_20d"]:
            liq[yf] = {"last_price": float(row["close"]),
                       "turnover_20d": t, "history_days": _HISTORY_UNKNOWN}
    return liq


def _slim(r: dict) -> dict:
    return {k: r.get(k) for k in _SLIM_KEYS if k in r}


def broad_equity_entries(
    region: str,
    *,
    depth: int = _DEFAULT_DEPTH,
    screen_page: int = _DEFAULT_SCREEN_PAGE,
    discover_fn: Callable[[str], dict] = discover_exchange,
    screener_fn: Callable[..., Optional[list]] = run_screener,
) -> tuple:
    """The candidate-generation half of the broad scan, WITHOUT scoring —
    discover the full exchange universe (946 ST / 18k US), get bulk liquidity
    from ONE screener call, rank by turnover, take the top-`depth` tranche.

    Returns (entries, meta): entries = [(yf_symbol, region, "equity"), …] and
    meta carries the honest funnel counts. Reused by Setup of the Day so its
    equity boxes rank the broad liquid universe instead of the ~12 curated
    names — the fix for "best of 12" vs "best in market"."""
    region = "Swedish" if str(region).lower().startswith("swed") else "International"
    exch, market = _REGION_MAP[region]

    disc = discover_fn(exch) or {}
    symbols = disc.get("symbols") or []
    disc_label = disc.get("coverage_label", "unknown")

    rows = None
    try:
        rows = screener_fn(market=market, limit=screen_page)
    except Exception as exc:  # noqa: BLE001 - degrade, never crash
        logger.warning("broad-entries screener %s failed: %s", market, type(exc).__name__)
    liq_map = _build_liquidity_map(rows or [])

    # If discovery is unavailable (no/expired EODHD key), fall back to the
    # screener-derived symbol set so the scan still runs, labelled honestly.
    if not symbols and liq_map:
        symbols = [{"symbol": s, "asset_class": "equity", "region": region}
                   for s in liq_map]
        disc_label = "screener_derived_universe"

    sl = shortlist(symbols, "equity", liquidity_fn=liq_map.get,
                   limit=depth, min_price=0.0, min_turnover=0.0,
                   min_history_days=0)
    entries = [(s["symbol"], region, "equity") for s in sl["symbols"]]
    meta = {
        "exchange": exch, "market": market, "discovery_label": disc_label,
        "discovered": sl.get("discovered", 0), "screener_liquid": len(liq_map),
        "eligible": sl.get("eligible", 0), "capped_out": sl.get("capped_out", 0),
        "excluded": sl.get("excluded", {}), "shortlisted": len(entries),
    }
    return entries, meta


def broad_scan(
    region: str,
    *,
    score_fn: Callable[..., Optional[dict]],
    regime_map: Optional[dict] = None,
    calibration: Optional[dict] = None,
    depth: int = _DEFAULT_DEPTH,
    screen_page: int = _DEFAULT_SCREEN_PAGE,
    discover_fn: Callable[[str], dict] = discover_exchange,
    screener_fn: Callable[..., Optional[list]] = run_screener,
    max_workers: int = _MAX_WORKERS,
) -> dict:
    """Broad market scan for one region. Returns {"status": "ok", ...} always;
    upstream gaps degrade to honest labels, never a crash.

    score_fn is injected (the real phase2_router._fetch_and_score) and is called
    as score_fn(entry, calibration=, regime_map=, news_enabled=False) — news is
    skipped for breadth (grade reflects technical structure; finalists' news is
    fetched by the symbol page)."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    region = "Swedish" if str(region).lower().startswith("swed") else "International"
    entries, meta = broad_equity_entries(
        region, depth=depth, screen_page=screen_page,
        discover_fn=discover_fn, screener_fn=screener_fn)

    scored: list[dict] = []
    if entries:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(score_fn, e, calibration=calibration,
                                   regime_map=regime_map, news_enabled=False)
                       for e in entries]
            for f in futures:
                try:
                    r = f.result()
                except Exception as exc:  # noqa: BLE001 - one bad symbol never sinks the scan
                    logger.debug("broad-scan score error: %s", type(exc).__name__)
                    r = None
                if r is not None:
                    scored.append(r)

    scored.sort(key=lambda r: (_GRADE_RANK.get(r.get("grade"), 9),
                               -(r.get("score") or 0.0), r.get("symbol") or ""))
    slim = [_slim(r) for r in scored]
    grade_a = [r for r in slim if r.get("grade") == "A"]
    grade_b = [r for r in slim if r.get("grade") == "B"]
    grade_c = [r for r in slim if r.get("grade") == "C"]

    return {
        "status": "ok",
        "region": region,
        "exchange": meta["exchange"],
        "screener_market": meta["market"],
        "generated_utc": now_iso,
        "discovered": meta["discovered"],            # equities in the exchange list
        "discovery_label": meta["discovery_label"],  # full_exchange_market / key_missing / …
        "screener_liquid": meta["screener_liquid"],  # names with bulk liquidity data
        "eligible": meta["eligible"],                # passed the (zero) liquidity prefilters
        "scanned": len(scored),                      # actually graded by setup_scanner
        "capped_out": meta["capped_out"],
        "excluded": meta["excluded"],
        "grade_a_count": len(grade_a),
        "grade_b_count": len(grade_b),
        "grade_a": grade_a,                          # HIGHEST CONVICTION
        "grade_b": grade_b,                          # SOLID ALIGNMENT
        "grade_c": grade_c,
        "coverage_label": (
            f"scanned top {len(scored)} most-liquid of {meta['discovered']} "
            f"discovered {meta['exchange']} equities — liquidity via TradingView "
            f"screener (1 bulk call), grade via SENTRIQ setup_scanner"),
        "method_note": (
            "Grade A = HIGHEST CONVICTION, Grade B = SOLID ALIGNMENT. "
            "News skipped for breadth (finalists' news on the symbol page). "
            "No invented thresholds — pure liquidity ranking."),
    }
