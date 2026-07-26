# api/backtest_router.py
"""
Cached, async per-symbol backtest endpoint — serves the Edge/Expectancy card.

DECISION PROVENANCE (LLM Council, this session):
  A per-symbol walk-forward is ~15-30s, so it MUST NOT run synchronously inline.
  Locked model: cache-aside + stale-while-revalidate + single-flight async
  background compute + {status:"computing"}/poll, with a nightly pre-warm of the
  active basket via a background loop (mirrors main.py's ledger auto-eval).

  - Single-flight (Selivanov): one compute per (symbol,strategy,tf) in flight;
    concurrent cold requests share it instead of stampeding.
  - Non-blocking (Karpathy): the CPU-bound walk-forward runs in a worker thread
    (asyncio.to_thread) so a 15-30s study never freezes the event loop.
  - Honest freshness (Nilsson): every served result carries computed_at + stale.
  - Honest coverage (Gurpreet/NG): a data miss or thin sample is reported, never
    fabricated; symbol/strategy are validated on input.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from .symbol_backtest import (
    STRATEGIES,
    available_strategies,
    backtest_from_points,
)

logger = logging.getLogger("backtest_router")
router = APIRouter()

# ── cache config ────────────────────────────────────────────────────────────
_CACHE_DIR = Path(os.getenv("SENTRIQ_CACHE_DIR", "/tmp")) / "sentriq_backtest"
_TTL_SEC = int(os.getenv("BACKTEST_TTL_SEC", str(24 * 3600)))   # fresh window
_ETA_SEC = int(os.getenv("BACKTEST_ETA_SEC", "25"))             # advertised compute ETA
_VALID_TF = {"1d"}                                              # daily first (council-locked)

# Single-flight registry: cache_key -> running asyncio.Task. Guarded by a lock so
# concurrent cold requests for the same symbol share one compute.
_inflight: dict[str, "asyncio.Task[None]"] = {}
_inflight_lock = asyncio.Lock()


def _safe(s: str) -> str:
    """Filename-safe token (uppercased)."""
    return re.sub(r"[^A-Z0-9._-]+", "_", (s or "").upper()).strip("_") or "NA"


_CACHE_VERSION = "v2"  # bump to invalidate stale entries (pre per-request lookback)

def _cache_key(symbol: str, strategy: str, timeframe: str) -> str:
    return f"{_CACHE_VERSION}__{_safe(strategy)}__{_safe(timeframe)}__{_safe(symbol)}"


def _cache_path(symbol: str, strategy: str, timeframe: str) -> Path:
    return _CACHE_DIR / f"{_cache_key(symbol, strategy, timeframe)}.json"


def _read_cache(symbol: str, strategy: str, timeframe: str) -> Optional[dict]:
    p = _cache_path(symbol, strategy, timeframe)
    try:
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("backtest cache read failed %s: %s", p.name, exc)
        return None


def _write_cache(symbol: str, strategy: str, timeframe: str, report: dict) -> None:
    p = _cache_path(symbol, strategy, timeframe)
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report), encoding="utf-8")
        os.replace(tmp, p)  # atomic publish
    except OSError as exc:
        logger.warning("backtest cache write failed %s: %s", p.name, exc)


def _age_sec(report: dict) -> Optional[float]:
    ts = report.get("computed_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except ValueError:
        return None


def _is_fresh(report: dict) -> bool:
    age = _age_sec(report)
    return age is not None and age <= _TTL_SEC


async def _compute_and_cache(symbol: str, asset_class: str, strategy: str, timeframe: str) -> None:
    """Fetch the series (async) then run the CPU-bound walk-forward in a worker
    thread so the event loop stays responsive. Persists the result on success."""
    from .data_ingestion import service as _ingest
    from .symbol_backtest import STRATEGY_LOOKBACK_DAYS
    try:
        series = await _ingest.get_series(symbol, asset_class, lookback_days=STRATEGY_LOOKBACK_DAYS.get(strategy))
        if series is None or not getattr(series, "points", None):
            report = {
                "status": "ok", "symbol": symbol.upper(), "asset_class": asset_class,
                "strategy": strategy, "timeframe": timeframe, "available": False,
                "reason": "no_data",
                "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        else:
            report = await asyncio.to_thread(
                backtest_from_points, series.points,
                symbol=symbol, asset_class=asset_class, strategy=strategy,
            )
            report["source"] = getattr(series, "source", "?")
            report["timeframe"] = timeframe
            report["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_cache(symbol, strategy, timeframe, report)
        logger.info("backtest computed %s/%s available=%s",
                    symbol, strategy, report.get("available"))
    except Exception:  # noqa: BLE001 - a failed compute must not kill the task silently-broken
        logger.warning("backtest compute failed for %s/%s", symbol, strategy, exc_info=True)


async def _ensure_compute(symbol: str, asset_class: str, strategy: str, timeframe: str) -> None:
    """Start a single-flight background compute if one isn't already running."""
    key = _cache_key(symbol, strategy, timeframe)
    async with _inflight_lock:
        if key in _inflight and not _inflight[key].done():
            return
        task = asyncio.create_task(_compute_and_cache(symbol, asset_class, strategy, timeframe))
        _inflight[key] = task

        def _cleanup(_t: "asyncio.Task[None]", k: str = key) -> None:
            existing = _inflight.get(k)
            if existing is _t:
                _inflight.pop(k, None)

        task.add_done_callback(_cleanup)


@router.get("/api/symbol/{symbol}/backtest")
async def symbol_backtest(
    symbol: str,
    asset_class: str = Query("equity"),
    strategy: str = Query("continuation"),
    timeframe: str = Query("1d"),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    """Cached per-symbol backtest. Serves cache instantly (with freshness flags);
    on a cold/missing entry, kicks an async background compute and returns
    {status:"computing"} so the client can poll. `refresh=true` forces recompute."""
    symbol = (symbol or "").strip()
    if not symbol or len(symbol) > 24 or not re.match(r"^[A-Za-z0-9.\-=^]+$", symbol):
        raise HTTPException(400, "invalid symbol")
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"unknown strategy '{strategy}'; valid: {available_strategies()}")
    if timeframe not in _VALID_TF:
        raise HTTPException(400, f"unsupported timeframe '{timeframe}'; valid: {sorted(_VALID_TF)}")

    cached = None if refresh else _read_cache(symbol, strategy, timeframe)

    if cached is not None and _is_fresh(cached):
        cached["cached"] = True
        cached["stale"] = False
        return cached

    # Cold or stale (or forced): ensure a background compute is running.
    await _ensure_compute(symbol, asset_class, strategy, timeframe)

    if cached is not None:
        # Stale-while-revalidate: serve the last-good result, flag it, refresh in bg.
        cached["cached"] = True
        cached["stale"] = True
        cached["refreshing"] = True
        return cached

    # Nothing cached yet — tell the client to poll.
    return {
        "status": "computing",
        "symbol": symbol.upper(),
        "strategy": strategy,
        "timeframe": timeframe,
        "cached": False,
        "eta_s": _ETA_SEC,
        "poll_after_s": min(5, _ETA_SEC),
    }


# ── nightly pre-warm of the active basket (watchlist + well-knowns) ──────────
# Reuses the well-known crypto/index/etc. catalogs from omnisearch as the static
# basket. The watchlist is client-owned (localStorage) so it pre-warms lazily on
# first view; this loop keeps the common, always-relevant symbols hot.
_PREWARM_INTERVAL_SEC = int(os.getenv("BACKTEST_PREWARM_INTERVAL_SEC", str(24 * 3600)))
_PREWARM_WARMUP_SEC = int(os.getenv("BACKTEST_PREWARM_WARMUP_SEC", "40"))
_PREWARM_STRATEGY = os.getenv("BACKTEST_PREWARM_STRATEGY", "continuation")


def _default_basket() -> list[tuple[str, str]]:
    """(symbol, asset_class) pairs to keep warm. Equities/ETFs that anchor the app
    plus the well-known crypto basket. Kept small and high-traffic on purpose."""
    basket: list[tuple[str, str]] = [
        ("AAPL", "equity"), ("MSFT", "equity"), ("NVDA", "equity"),
        ("SPY", "etf"), ("QQQ", "etf"),
    ]
    try:
        from .omnisearch_router import WELL_KNOWN_CRYPTO
        basket += [(sym, "crypto") for sym in WELL_KNOWN_CRYPTO]
    except Exception:  # noqa: BLE001 - basket is best-effort
        pass
    return basket


async def prewarm_once(basket: Optional[list[tuple[str, str]]] = None,
                       strategy: str = _PREWARM_STRATEGY, timeframe: str = "1d") -> dict[str, int]:
    """Recompute the basket sequentially (gentle on providers). Returns counts."""
    pairs = basket if basket is not None else _default_basket()
    warmed = failed = 0
    for symbol, ac in pairs:
        try:
            await _compute_and_cache(symbol, ac, strategy, timeframe)
            warmed += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.2)  # be kind to upstream rate limits
    logger.info("backtest pre-warm done: warmed=%d failed=%d", warmed, failed)
    return {"warmed": warmed, "failed": failed}


async def prewarm_loop() -> None:
    """Periodic pre-warm. Disable with BACKTEST_PREWARM=0."""
    await asyncio.sleep(_PREWARM_WARMUP_SEC)
    while True:
        try:
            await prewarm_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never let the loop die
            logger.warning("backtest pre-warm iteration failed", exc_info=True)
        try:
            await asyncio.sleep(_PREWARM_INTERVAL_SEC)
        except asyncio.CancelledError:
            raise
