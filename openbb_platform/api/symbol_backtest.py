# api/symbol_backtest.py
"""
Per-symbol walk-forward backtest — the engine behind the Edge/Expectancy card.

DECISION PROVENANCE (LLM Council, this session):
  The global TRUST LEDGER (setup_ledger.py) reports edge by GRADE across every
  logged setup. This module answers a different question: "what is THIS symbol's
  own historical edge?" — a walk-forward over the symbol's own price history.

COUNCIL-LOCKED RULES (mirroring setup_ledger's discipline):
  - Reuse, don't reimplement (KARPATHY): the barrier classifier (`classify`) and
    window parser (`_parse_window_days`) come from setup_ledger; the setup
    generator (`score_setup`) comes from setup_scanner. We only orchestrate.
  - Look-ahead-safe (KARPATHY/Gurpreet): at each as-of index i, score using ONLY
    bars[:i+1]; classify on strictly-later bars[i+1:]. No peeking.
  - Independence (NG): NON-OVERLAPPING trades. After a trade resolves, advance the
    cursor past its resolution so adjacent, autocorrelated setups don't inflate the
    effective sample size — the precondition for an honest win-rate CI.
  - Honest statistics (NG/NILSSON): Wilson score interval on win-rate (sane at small
    n); gate on MIN_SAMPLE_FOR_RATE; report per-symbol only — never cherry-pick the
    best symbol of a basket (data-snooping bias). Small n -> rate_reliable = False.
  - Strategy-pluggable (cross-cutting): STRATEGIES registry. `continuation` is live;
    `harmonic_prz` is a drop-in slot feeding the SAME classifier.

Pure core (`walk_forward` / `backtest_from_points`) — float-safe, no I/O. The async
`compute_symbol_backtest` adds the single data fetch via an injected service.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .setup_ledger import (
    MIN_BARS_TO_SCORE,
    MIN_SAMPLE_FOR_RATE,
    _parse_window_days,
    classify,
)
from .setup_scanner import score_setup

logger = logging.getLogger("symbol_backtest")

LOOKBACK_BARS_DEFAULT: int = 756       # ~3 trading years of daily bars
TRADEABLE_GRADES: tuple[str, ...] = ("A", "B")  # headline edge = tradeable subset
WILSON_Z: float = 1.96                 # 95% confidence
_SLICE_CAP: int = 400                  # cap history fed to the generator (perf; SMAs need <=50)
_VALID_ASSET_CLASSES: frozenset[str] = frozenset({"equity", "etf", "fund", "crypto"})
# Evaluation horizon for harmonic-PRZ reversals (a backtest window in trading
# days, NOT a Carney ratio — price levels are 100% engine-sourced). Reversals
# can take longer to resolve than continuation pullbacks.
HARMONIC_HORIZON: str = "30-60 trading days"


def _classify_directional(entry: float, stop: float, target: float, direction: str,
                          fut_highs: list, fut_lows: list, horizon: int) -> tuple[str, Optional[int]]:
    """First-touch barrier, direction-aware. LONG delegates to the single-sourced
    setup_ledger.classify so longs can never diverge from the global ledger. SHORT
    mirrors it: WIN when price falls to target before rising to stop. Float-safe."""
    if direction != "short":
        return classify(entry, stop, target, fut_highs, fut_lows, horizon)
    n = min(len(fut_highs), len(fut_lows), max(1, horizon))
    for i in range(n):
        hi, lo = fut_highs[i], fut_lows[i]
        if hi is None or lo is None or not (math.isfinite(hi) and math.isfinite(lo)):
            continue
        hit_target = lo <= target   # price fell to the (lower) target
        hit_stop = hi >= stop       # price rose to the (higher) stop
        if hit_target and hit_stop:
            return "AMBIGUOUS", i + 1
        if hit_stop:
            return "LOSS", i + 1
        if hit_target:
            return "WIN", i + 1
    return "EXPIRED", None


def _norm_direction(setup: dict) -> str:
    """Map a setup's direction to 'long'/'short'. Trust the geometry first
    (target vs entry), then any explicit field; default long (continuation)."""
    try:
        entry = float(setup.get("entry"))
        target = float(setup.get("target"))
        if target < entry:
            return "short"
        if target > entry:
            return "long"
    except (TypeError, ValueError):
        pass
    d = str(setup.get("direction", "")).lower()
    if d in ("short", "bearish", "sell"):
        return "short"
    return "long"


# ─────────────────────────────────────────────────────────────────────────────
# Strategy registry — each generator returns a SetupResult-shaped dict or None.
# Adding a strategy = register a generator here; the harness is unchanged.
# ─────────────────────────────────────────────────────────────────────────────
def _gen_continuation(symbol: str, region: str, closes: list[float],
                      highs: list[float], lows: list[float],
                      asset_class: str) -> Optional[dict]:
    """Momentum/pullback continuation setup (the existing scanner engine)."""
    return score_setup(symbol, region, closes, highs, lows, asset_class=asset_class)


_HARMONIC_QUALITY_GRADE: dict[str, str] = {"EXCELLENT": "A", "GOOD": "B", "OK": "C"}
_HARMONIC_MIN_BARS: int = 40  # need enough swings for a pattern to form


def _gen_harmonic_prz(symbol: str, region: str, closes: list[float],
                      highs: list[float], lows: list[float],
                      asset_class: str) -> Optional[dict]:
    """Carney harmonic-PRZ reversal setup.

    Levels are 100% ENGINE-SOURCED: compute_prz_confluence() returns
    entry/stop_loss/target_1/rr_ratio computed from Carney ratios (Vol.1/2/3).
    Nothing is invented here — we only map the engine's trade spec into the
    harness shape, and infer direction from the engine's own geometry. Returns
    None when the engine is unavailable, no pattern is found, or the PRZ trade is
    not rr_valid. Heavy (imports the pattern engine + builds a frame per call) —
    walk_forward uses a coarser scan_step for this strategy.
    """
    if len(closes) < _HARMONIC_MIN_BARS:
        return None
    try:
        import pandas as pd  # heavy; only needed for the harmonic engine
        from .symbol_router import _import_engines
    except Exception:  # noqa: BLE001 — engine/deps unavailable -> strategy degrades to None
        return None
    try:
        eng = _import_engines()
        df = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes})
        swings = eng["compute_zigzag"](df["close"])
        harmonics = eng["scan_all_harmonic_patterns"](swings)
        found = [p for p in (harmonics or []) if p.get("found")]
        if not found:
            return None
        ichimoku = eng["compute_ichimoku"](df)
        indicators = eng["compute_all_indicators"](df)
        prz = eng["compute_prz_confluence"](df, swings, harmonics, ichimoku, indicators)
        if not prz or not prz.get("rr_valid") or float(prz.get("entry", 0.0) or 0.0) <= 1e-9:
            return None
        entry = float(prz["entry"])
        stop = float(prz["stop_loss"])
        target = float(prz["target_1"])
        rr = float(prz.get("rr_ratio") or 0.0)
        quality = str(found[0].get("quality", "OK")).upper()
        return {
            "symbol": symbol, "name": symbol, "region": region, "asset_class": asset_class,
            "grade": _HARMONIC_QUALITY_GRADE.get(quality, "C"),
            "entry": round(entry, 4), "stop": round(stop, 4), "target": round(target, 4),
            "reward_risk": rr, "time_window_days": HARMONIC_HORIZON,
            "direction": "bullish" if target > entry else "bearish",
        }
    except Exception as exc:  # noqa: BLE001 — never abort the study on one bar
        logger.debug("harmonic_prz gen failed for %s: %s", symbol, exc)
        return None


STRATEGIES: dict[str, Callable[..., Optional[dict]]] = {
    "continuation": _gen_continuation,
    "harmonic_prz": _gen_harmonic_prz,
}

# Per-strategy cursor advance when no setup fires. Cheap generators scan every bar;
# the harmonic engine is heavy, so it scans coarsely.
STRATEGY_SCAN_STEP: dict[str, int] = {"continuation": 1, "harmonic_prz": 3}

# Per-strategy scan window (trading bars) and fetch horizon (calendar days).
# Continuation fires often -> ~3y window, 1y fetch (unchanged). Harmonic PRZ
# setups are rare, so it needs a wider scan window AND a deeper fetch to resolve
# enough non-overlapping trades. Defaults elsewhere stay 1y so risk/overview
# metrics (e.g. max_drawdown_1y) remain byte-for-byte identical.
STRATEGY_LOOKBACK_BARS: dict[str, int] = {"continuation": LOOKBACK_BARS_DEFAULT, "harmonic_prz": 1260}
STRATEGY_LOOKBACK_DAYS: dict[str, int] = {"continuation": 365, "harmonic_prz": 1825}


def available_strategies() -> list[str]:
    return list(STRATEGIES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────
def wilson_ci(wins: int, n: int, z: float = WILSON_Z) -> tuple[Optional[float], Optional[float]]:
    """Wilson score interval for a binomial proportion, returned as percentages.
    Preferred over the normal approximation: never produces <0% / >100% bounds and
    stays meaningful at small n. Pure function."""
    if n <= 0:
        return (None, None)
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return (round(100.0 * lo, 1), round(100.0 * hi, 1))


def _expectancy_r(wins: int, decided: int, avg_rr: Optional[float]) -> Optional[float]:
    """Expected R-multiple per trade: wr*avg_reward - (1-wr)*1R (risk is 1R by
    definition). Identical formula to setup_ledger.aggregate so the two agree."""
    if decided <= 0 or avg_rr is None:
        return None
    wr = wins / decided
    return round(wr * avg_rr - (1.0 - wr) * 1.0, 3)


def _agg(rs: list[dict]) -> dict[str, Any]:
    wins = sum(1 for r in rs if r["outcome"] == "WIN")
    losses = sum(1 for r in rs if r["outcome"] in ("LOSS", "AMBIGUOUS"))
    expired = sum(1 for r in rs if r["outcome"] == "EXPIRED")
    decided = wins + losses
    rr_vals = [r["reward_risk"] for r in rs
               if isinstance(r.get("reward_risk"), (int, float)) and r["reward_risk"]]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None
    rate = round(100.0 * wins / decided, 1) if decided > 0 else None
    ci_lo, ci_hi = wilson_ci(wins, decided)
    return {
        "trades": len(rs), "wins": wins, "losses": losses, "expired": expired,
        "decided": decided, "win_rate_pct": rate, "win_rate_ci95": [ci_lo, ci_hi],
        "avg_reward_risk": avg_rr, "expectancy_r": _expectancy_r(wins, decided, avg_rr),
        "rate_reliable": decided >= MIN_SAMPLE_FOR_RATE,
    }


def _summarize(trades: list[dict]) -> dict[str, Any]:
    """overall + tradeable(A,B) + per-grade breakdown."""
    return {
        "overall": _agg(trades),
        "tradeable": _agg([t for t in trades if t["grade"] in TRADEABLE_GRADES]),
        "by_grade": {g: _agg([t for t in trades if t["grade"] == g]) for g in ("A", "B", "C")},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward core (pure)
# ─────────────────────────────────────────────────────────────────────────────
def walk_forward(ts: list, highs: list[float], lows: list[float], closes: list[float], *,
                 symbol: str, asset_class: str, strategy: str,
                 lookback_bars: int = LOOKBACK_BARS_DEFAULT,
                 scan_step: int = 1) -> list[dict]:
    """Non-overlapping, look-ahead-safe, direction-aware walk-forward. Returns a
    list of resolved trade records. Never raises on a single-bar generator failure.
    `scan_step` advances the cursor when no setup fires (raise it for expensive
    generators like harmonic_prz that run the full pattern engine per bar)."""
    gen = STRATEGIES.get(strategy)
    if gen is None:
        raise ValueError(f"unknown strategy: {strategy!r}")
    n = len(closes)
    if n < MIN_BARS_TO_SCORE + 5:
        return []
    step = max(1, scan_step)
    region = "Swedish" if symbol.upper().endswith(".ST") else "International"
    start = max(MIN_BARS_TO_SCORE, n - max(1, lookback_bars))
    trades: list[dict] = []
    i = start
    while i < n - 1:
        lo_slice = max(0, i + 1 - _SLICE_CAP)
        c = closes[lo_slice:i + 1]
        h = highs[lo_slice:i + 1]
        l = lows[lo_slice:i + 1]
        try:
            setup = gen(symbol, region, c, h, l, asset_class)
        except Exception as exc:  # noqa: BLE001 — one bad bar must not abort the study
            logger.debug("gen failed @%d %s/%s: %s", i, symbol, strategy, exc)
            setup = None
        if not setup or setup.get("grade") not in ("A", "B", "C"):
            i += step
            continue
        entry, stop, target = setup.get("entry"), setup.get("stop"), setup.get("target")
        if entry is None or stop is None or target is None:
            i += step
            continue
        try:
            entry_f, stop_f, target_f = float(entry), float(stop), float(target)
        except (TypeError, ValueError):
            i += step
            continue
        direction = _norm_direction(setup)
        # Reject degenerate/malformed geometry: stop must sit on the opposite side
        # of entry from the target (long: stop<entry<target; short: target<entry<stop).
        ok_geom = (
            (direction == "long" and stop_f < entry_f < target_f) or
            (direction == "short" and target_f < entry_f < stop_f)
        )
        if not ok_geom:
            i += step
            continue
        horizon = _parse_window_days(setup.get("time_window_days"))
        fut_h, fut_l = highs[i + 1:], lows[i + 1:]
        if not fut_h:
            break
        try:
            outcome, bars = _classify_directional(entry_f, stop_f, target_f, direction,
                                                  fut_h, fut_l, horizon)
        except (ValueError, TypeError) as exc:
            logger.debug("classify failed @%d %s: %s", i, symbol, exc)
            i += step
            continue
        # Honest expiry: not enough subsequent bars to fill the horizon -> stop here
        # rather than scoring half-formed trades at the right edge of history.
        if outcome == "EXPIRED" and len(fut_h) < horizon:
            break
        ts_i = ts[i]
        trades.append({
            "as_of": ts_i.date().isoformat() if hasattr(ts_i, "date") else str(ts_i),
            "grade": setup["grade"], "outcome": outcome, "direction": direction,
            "reward_risk": float(setup.get("reward_risk") or 0.0),
            "bars_to_resolve": bars,
        })
        # Non-overlap: jump past resolution (or the full horizon when expired).
        i += (bars if bars else horizon) + 1
    return trades


_METHODOLOGY: str = (
    "Per-symbol walk-forward: at each historical as-of bar, the strategy is scored "
    "using only data up to that bar (look-ahead-safe), then evaluated on strictly-later "
    "daily bars via a first-touch barrier (WIN if target reached before stop within the "
    "time window; LOSS if stop first; same-bar straddle = not-a-win; EXPIRED otherwise). "
    "Trades are NON-OVERLAPPING — the cursor advances past each trade's resolution — so "
    "win-rate samples are quasi-independent. Win-rate is reported with a 95% Wilson "
    "confidence interval and read alongside expectancy_r (expected R-multiple per trade): "
    "a fixed reward:risk means positive expectancy can coexist with a sub-50% win rate."
)


def backtest_from_points(points: list, *, symbol: str, asset_class: str = "equity",
                         strategy: str = "continuation",
                         lookback_bars: Optional[int] = None) -> dict[str, Any]:
    """Pure entry point: take normalized price points -> backtest report dict."""
    if lookback_bars is None:
        lookback_bars = STRATEGY_LOOKBACK_BARS.get(strategy, LOOKBACK_BARS_DEFAULT)
    ts = [p.ts for p in points]
    highs = [p.high for p in points]
    lows = [p.low for p in points]
    closes = [p.close for p in points]
    trades = walk_forward(ts, highs, lows, closes, symbol=symbol,
                          asset_class=asset_class, strategy=strategy,
                          lookback_bars=lookback_bars,
                          scan_step=STRATEGY_SCAN_STEP.get(strategy, 1))
    summ = _summarize(trades)
    return {
        "status": "ok",
        "symbol": symbol.upper(),
        "asset_class": asset_class,
        "strategy": strategy,
        "timeframe": "1d",
        "bars_analyzed": len(points),
        "lookback_bars": min(lookback_bars, len(points)),
        "available": summ["overall"]["trades"] > 0,
        **summ,
        "methodology": _METHODOLOGY,
        "disclaimer": "Decision-support, not advice. Past results do not predict future performance.",
    }


async def compute_symbol_backtest(service: Any, symbol: str, asset_class: str = "equity", *,
                                  strategy: str = "continuation",
                                  lookback_bars: Optional[int] = None) -> dict[str, Any]:
    """Fetch the symbol's daily series via the injected service, then backtest.
    Honest on a data miss (available=False, never a fabricated edge)."""
    ac = asset_class if asset_class in _VALID_ASSET_CLASSES else "equity"
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy!r}")
    try:
        series = await service.get_series(symbol, ac, lookback_days=STRATEGY_LOOKBACK_DAYS.get(strategy))
    except Exception as exc:  # noqa: BLE001 — a fetch miss is "uncovered", not a crash
        logger.warning("backtest fetch failed for %s: %s", symbol, exc)
        series = None
    if series is None or not getattr(series, "points", None):
        return {
            "status": "ok", "symbol": symbol.upper(), "asset_class": ac,
            "strategy": strategy, "timeframe": "1d", "available": False,
            "reason": "no_data", "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    out = backtest_from_points(series.points, symbol=symbol, asset_class=ac,
                               strategy=strategy, lookback_bars=lookback_bars)
    out["source"] = getattr(series, "source", "?")
    out["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out
