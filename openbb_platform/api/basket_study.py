# api/basket_study.py
"""
Basket study — run the per-symbol backtest across a basket of symbols to FIRM UP
the numbers, then report honestly.

DECISION PROVENANCE (LLM Council, this session — NG's amendment):
  Scanning a basket and surfacing the single best symbol inflates apparent edge
  (data-snooping; White's Reality Check; Lopez de Prado). So this harness:
    - reports EVERY symbol's edge with its own Wilson CI (no cherry-picking),
    - publishes a POOLED estimate (more trades -> tighter CI) for the strategy as
      a whole, clearly labelled as a strategy-level figure, and
    - gates each row on sample sufficiency (rate_reliable).
  Pooling is exact for win-rate from per-symbol aggregates (sum wins / sum
  decided); pooled avg R:R is decided-weighted; pooled expectancy uses both.

Pure `pool_reports` (testable, no I/O) + async `run_basket_study` (fetches via the
injected service). `python -m api.basket_study` runs it on the default basket.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .symbol_backtest import (
    _expectancy_r,
    compute_symbol_backtest,
    wilson_ci,
)

logger = logging.getLogger("basket_study")


def pool_reports(reports: list[dict], subset: str = "tradeable") -> dict[str, Any]:
    """Pool a list of per-symbol backtest reports into per-symbol rows + a pooled
    strategy-level estimate. Pure function. `subset` is 'tradeable' | 'overall'."""
    rows: list[dict] = []
    pooled_wins = pooled_losses = pooled_decided = pooled_setups = 0
    rr_weighted = 0.0
    rr_weight = 0
    covered = 0
    for rep in reports:
        sym = rep.get("symbol", "?")
        if not rep.get("available"):
            rows.append({"symbol": sym, "available": False, "reason": rep.get("reason")})
            continue
        block = rep.get(subset) or rep.get("overall") or {}
        decided = int(block.get("decided") or 0)
        wins = int(block.get("wins") or 0)
        losses = int(block.get("losses") or 0)
        trades = int(block.get("trades") or 0)
        rows.append({
            "symbol": sym, "available": True,
            "win_rate_pct": block.get("win_rate_pct"),
            "win_rate_ci95": block.get("win_rate_ci95"),
            "expectancy_r": block.get("expectancy_r"),
            "avg_reward_risk": block.get("avg_reward_risk"),
            "decided": decided, "trades": trades,
            "rate_reliable": bool(block.get("rate_reliable")),
        })
        covered += 1
        pooled_wins += wins
        pooled_losses += losses
        pooled_decided += decided
        pooled_setups += trades
        arr = block.get("avg_reward_risk")
        if isinstance(arr, (int, float)) and arr and decided > 0:
            rr_weighted += arr * decided
            rr_weight += decided
    pooled_avg_rr = round(rr_weighted / rr_weight, 2) if rr_weight else None
    pooled_rate = round(100.0 * pooled_wins / pooled_decided, 1) if pooled_decided > 0 else None
    ci_lo, ci_hi = wilson_ci(pooled_wins, pooled_decided)
    pooled = {
        "symbols_covered": covered,
        "wins": pooled_wins, "losses": pooled_losses, "decided": pooled_decided,
        "setups": pooled_setups,
        "win_rate_pct": pooled_rate, "win_rate_ci95": [ci_lo, ci_hi],
        "avg_reward_risk": pooled_avg_rr,
        "expectancy_r": _expectancy_r(pooled_wins, pooled_decided, pooled_avg_rr),
        "rate_reliable": pooled_decided >= 30,  # pooled bar is higher than per-symbol
    }
    # Honest ranking: by expectancy, but ONLY among reliable rows (no cherry-picking
    # a thin-sample outlier to the top).
    ranked = sorted(
        [r for r in rows if r.get("available") and r.get("rate_reliable") and r.get("expectancy_r") is not None],
        key=lambda r: r["expectancy_r"], reverse=True,
    )
    return {
        "status": "ok",
        "subset": subset,
        "per_symbol": rows,
        "ranked_reliable": ranked,
        "pooled": pooled,
        "disclaimer": (
            "Per-symbol figures carry their own confidence interval; the pooled figure "
            "is a strategy-level estimate across the basket, not a tradeable single-symbol "
            "edge. Decision-support, not advice. Past results do not predict the future."
        ),
    }


async def run_basket_study(service: Any, basket: list[tuple[str, str]],
                           strategy: str = "continuation", subset: str = "tradeable",
                           ) -> dict[str, Any]:
    """Backtest each (symbol, asset_class) in the basket and pool the results.
    Sequential — gentle on upstream providers."""
    reports: list[dict] = []
    for symbol, ac in basket:
        try:
            rep = await compute_symbol_backtest(service, symbol, ac, strategy=strategy)
        except Exception as exc:  # noqa: BLE001 — one symbol must not abort the basket
            logger.warning("basket study: %s failed: %s", symbol, exc)
            rep = {"symbol": symbol.upper(), "available": False, "reason": "error"}
        reports.append(rep)
        await asyncio.sleep(0.2)
    out = pool_reports(reports, subset=subset)
    out["strategy"] = strategy
    out["basket_size"] = len(basket)
    return out


def _print_table(study: dict) -> None:
    p = study["pooled"]
    print(f"\nBASKET STUDY — strategy={study.get('strategy')} subset={study.get('subset')} "
          f"({p['symbols_covered']}/{study.get('basket_size')} covered)\n")
    print(f"{'SYMBOL':<10}{'WIN%':>7}{'CI95':>14}{'EXP(R)':>9}{'RR':>6}{'N':>6}{'REL':>5}")
    for r in study["per_symbol"]:
        if not r.get("available"):
            print(f"{r['symbol']:<10}{'—':>7}{'(uncovered)':>14}")
            continue
        ci = r.get("win_rate_ci95") or [None, None]
        cistr = f"{ci[0]}-{ci[1]}" if ci[0] is not None else "—"
        print(f"{r['symbol']:<10}{(r.get('win_rate_pct') if r.get('win_rate_pct') is not None else '—')!s:>7}"
              f"{cistr:>14}{(r.get('expectancy_r') if r.get('expectancy_r') is not None else '—')!s:>9}"
              f"{(r.get('avg_reward_risk') if r.get('avg_reward_risk') is not None else '—')!s:>6}"
              f"{r.get('decided', 0):>6}{('Y' if r.get('rate_reliable') else 'n'):>5}")
    print(f"\nPOOLED: win%={p['win_rate_pct']} CI95={p['win_rate_ci95']} "
          f"exp={p['expectancy_r']}R decided={p['decided']} reliable={p['rate_reliable']}")
    print(study["disclaimer"], "\n")


def _main() -> None:
    """CLI: `python -m api.basket_study [strategy]`. Uses the default basket and
    the live data ingestion service (run inside the venv)."""
    import sys
    strategy = sys.argv[1] if len(sys.argv) > 1 else "continuation"
    from .backtest_router import _default_basket
    from .data_ingestion import service as _ingest
    study = asyncio.run(run_basket_study(_ingest, _default_basket(), strategy=strategy))
    _print_table(study)


if __name__ == "__main__":
    _main()
