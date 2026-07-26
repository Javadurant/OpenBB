# engine/backtest_signals.py
# <- NEW [Backtest/Expectancy Harness]: walk-forward, NO look-ahead measurement of the
#    computed Elliott engine's signals. Turns "I believe" into measured numbers:
#    win rate, average R, expectancy (R/trade), profit factor, max drawdown (in R).
#
# HONESTY / SCOPE (read before trusting any number this produces):
#   * This measures a MECHANICAL trade model built on the engine's own structure
#     (entry = decision-bar close; stop = the structural extreme; target = a fixed
#     R-multiple). R = risk unit = |entry - stop|. R-multiples are a risk convention,
#     not an invented domain value — no Elliott ratio is fabricated here.
#   * NO LOOK-AHEAD: at decision bar i the engine sees only bars[:i+1]; the trade is
#     simulated strictly on bars after i. Pivot confirmation (min_bars) adds realistic lag.
#   * Past expectancy is NOT a guarantee of future results. This tool exists to size
#     positions and reject negative-edge setups — not to promise profit.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from engine.structure import elliott_wave as ew

logger = logging.getLogger(__name__)

# Trade outcome reasons.
HIT_TARGET = "target"
HIT_STOP = "stop"
TIMEOUT = "timeout"


@dataclass
class Trade:
    """One simulated trade, scored in R-multiples (risk units)."""
    entry_index: int
    entry_label: str
    direction: int          # +1 long, -1 short
    entry_price: float
    stop: float
    target: float
    setup: str              # e.g. "IMPULSE reversal", "ZIGZAG continuation"
    exit_index: int = -1
    exit_price: float = 0.0
    r_multiple: float = 0.0
    outcome: str = ""


def _signal_from_count(p: ew.WaveCount) -> Optional[tuple[int, float, str]]:
    """Map a COMPLETED count to (direction, stop, setup) using the engine's
    canonical classifier (ew.signal_for_count) — single source of truth shared with
    the live API. Returns None when there is no actionable bias."""
    sig = ew.signal_for_count(p)
    if sig["bias"] == "NONE" or sig["stop"] is None:
        return None
    direction = 1 if sig["bias"] == "LONG" else -1
    return direction, float(sig["stop"]), f"{p.count_type.value} {sig['kind']}"


def _simulate(direction: int, entry: float, stop: float, target: float,
              high: np.ndarray, low: np.ndarray, close: np.ndarray,
              start: int, max_hold: int) -> tuple[int, float, str]:
    """Walk bars strictly after `start`; return (exit_index, exit_price, outcome).
    Stop checked before target on the same bar (conservative)."""
    end = min(start + max_hold, len(close) - 1)
    for j in range(start + 1, end + 1):
        if direction > 0:
            if low[j] <= stop:
                return j, stop, HIT_STOP
            if high[j] >= target:
                return j, target, HIT_TARGET
        else:
            if high[j] >= stop:
                return j, stop, HIT_STOP
            if low[j] <= target:
                return j, target, HIT_TARGET
    return end, float(close[end]), TIMEOUT


def backtest_elliott(high: Sequence[float], low: Sequence[float], close: Sequence[float],
                     labels: Sequence[str], *, target_r: float = 2.0,
                     max_hold: int = 60, warmup: int = 60,
                     min_bars: int = ew.MIN_PIVOT_BARS,
                     min_risk_frac: float = 0.005,
                     enable_reversal: bool = True,
                     enable_continuation: bool = True) -> dict:
    """Walk-forward backtest of the computed Elliott engine. One position at a time.

    Args:
        target_r:   reward target as a multiple of risk R (default 2.0 = 2R).
        max_hold:   max bars to hold before marking to market.
        warmup:     bars required before the first decision (engine needs structure).
        min_risk_frac: skip degenerate setups whose risk < this fraction of entry price.
    """
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    cl = np.asarray(close, dtype=float)
    n = len(cl)
    trades: list[Trade] = []
    if n < warmup + 10:
        return _summary(trades, target_r, note="insufficient history")

    i = warmup
    last_signal_pivot = -1
    while i < n - 1:
        res = ew.analyze(h[:i + 1], lo[:i + 1], cl[:i + 1], list(labels[:i + 1]),
                         symbol="BT", timeframe="bt", as_of=str(labels[i]),
                         min_bars=min_bars)
        p = res.preferred
        if p is None:
            i += 1
            continue
        term_idx = p.legs[-1].end_index
        # Fire only on a FRESH completion whose terminal pivot is recent (just confirmed).
        fresh = (term_idx != last_signal_pivot) and (i - term_idx <= min_bars + 1)
        sig = _signal_from_count(p) if fresh else None
        if sig is None:
            i += 1
            continue
        direction, stop, setup = sig
        # Strategy filter: the backtest shows IMPULSE-reversal (fading trends) is a
        # net loser while corrective-CONTINUATION (trading with the trend after a
        # correction) carries the edge. Toggle families to trade only the edge.
        is_reversal = "reversal" in setup
        if (is_reversal and not enable_reversal) or (not is_reversal and not enable_continuation):
            last_signal_pivot = term_idx
            i += 1
            continue
        entry = float(cl[i])
        risk = abs(entry - stop)
        if risk < min_risk_frac * abs(entry) or risk <= 0:   # degenerate / no room
            last_signal_pivot = term_idx
            i += 1
            continue
        target = entry + direction * target_r * risk
        # Stop must sit on the correct side of entry for the trade to make sense.
        if (direction > 0 and stop >= entry) or (direction < 0 and stop <= entry):
            last_signal_pivot = term_idx
            i += 1
            continue
        ex_i, ex_p, outcome = _simulate(direction, entry, stop, target, h, lo, cl, i, max_hold)
        r = direction * (ex_p - entry) / risk
        trades.append(Trade(i, str(labels[i]), direction, entry, stop, target, setup,
                            ex_i, ex_p, round(r, 4), outcome))
        last_signal_pivot = term_idx
        i = ex_i + 1   # flat until the trade closes (no overlapping positions)

    return _summary(trades, target_r)


def _summary(trades: list[Trade], target_r: float, note: str = "") -> dict:
    """Compute expectancy metrics from the trade list. All returns in R-multiples."""
    n = len(trades)
    rs = [t.r_multiple for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = (len(wins) / n) if n else 0.0
    expectancy = (sum(rs) / n) if n else 0.0      # average R per trade = the edge
    profit_factor = (gross_win / gross_loss) if gross_loss > np.finfo(float).eps else (
        float("inf") if gross_win > 0 else 0.0)

    # Equity curve in R + max drawdown (R) and worst losing streak.
    equity, peak, max_dd, streak, worst_streak = 0.0, 0.0, 0.0, 0, 0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        streak = streak + 1 if r <= 0 else 0
        worst_streak = max(worst_streak, streak)

    by_outcome = {k: sum(1 for t in trades if t.outcome == k)
                  for k in (HIT_TARGET, HIT_STOP, TIMEOUT)}

    # Per-setup expectancy — shows WHICH signal family carries the edge.
    by_setup: dict[str, dict] = {}
    for t in trades:
        b = by_setup.setdefault(t.setup, {"trades": 0, "total_r": 0.0, "wins": 0})
        b["trades"] += 1
        b["total_r"] += t.r_multiple
        b["wins"] += 1 if t.r_multiple > 0 else 0
    for b in by_setup.values():
        b["expectancy_r"] = round(b["total_r"] / b["trades"], 4) if b["trades"] else 0.0
        b["win_rate"] = round(b["wins"] / b["trades"], 4) if b["trades"] else 0.0
        b["total_r"] = round(b["total_r"], 4)

    return {
        "trades": n,
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(expectancy, 4),        # >0 = positive edge per trade
        "total_r": round(sum(rs), 4),
        "avg_win_r": round((sum(wins) / len(wins)) if wins else 0.0, 4),
        "avg_loss_r": round((sum(losses) / len(losses)) if losses else 0.0, 4),
        "profit_factor": (round(profit_factor, 4) if np.isfinite(profit_factor) else None),
        "max_drawdown_r": round(max_dd, 4),
        "max_losing_streak": worst_streak,
        "target_r": target_r,
        "outcomes": by_outcome,
        "by_setup": by_setup,
        "note": note,
        "disclaimer": ("Mechanical backtest of the computed Elliott model. No look-ahead. "
                       "Past expectancy is not a guarantee of future results."),
        "trade_log": [t.__dict__ for t in trades],
    }
