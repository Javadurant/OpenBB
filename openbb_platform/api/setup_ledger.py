"""
api/setup_ledger.py
===================
Setup Scanner TRUST LEDGER — an honest, look-ahead-safe track record.

DECISION PROVENANCE (LLM Council, May 23 2026):
  Log every scored setup, then score it against subsequent price action using a
  strict first-touch barrier method, and publish the aggregate hit-rate WITH
  sample size + methodology. Decision-support, never advice; past != future.

COUNCIL-LOCKED RULES:
  - Hit-definition (KARPATHY): on subsequent DAILY bars after as_of,
      WIN  = a bar's high >= target BEFORE any bar's low <= stop
      LOSS = a bar's low  <= stop   first
      AMBIGUOUS = same bar straddles both (high>=target AND low<=stop) -> NOT a win
      EXPIRED  = neither triggers by the window horizon
  - Look-ahead-safe seeding (KARPATHY/Gurpreet): score as-of a PAST date using
      ONLY bars up to that date; evaluate on strictly-later bars. No peeking.
  - Idempotency (SELIVANOV): one record per "date:symbol:grade".
  - Presentation (NILSSON/Gurpreet): always expose n; small n -> "insufficient
      data"; report A/B/C separately; never annualize.

Pure classification function; float-safe (>=/<= only, no ==). Append-only JSONL.
"""
from __future__ import annotations

import asyncio  # <- NEW [autoeval]: serialize evaluation
import json
import logging
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any, Final, Optional, TypedDict

logger = logging.getLogger("setup_ledger")

_LEDGER_PATH: Final = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sentriq_ledger.jsonl")
MIN_SAMPLE_FOR_RATE: Final = 5      # below this, report "insufficient data"
MIN_BARS_TO_SCORE:   Final = 60     # need history depth before an as_of to score
DEFAULT_WINDOW_DAYS: Final = 18     # fallback horizon if a window can't be parsed
_WRITE_LOCK: Final = threading.Lock()  # guards append + rewrite against concurrent scan workers
_EVAL_LOCK: Final = asyncio.Lock()      # <- NEW [autoeval]: serialize evaluate (bg loop + manual endpoint)
_LAST_EVAL_TS: Optional[str] = None      # <- NEW [autoeval]: last evaluation time (UTC ISO), surfaced in aggregate()


class LedgerEntry(TypedDict, total=False):
    key:          str
    date:         str          # as_of (YYYY-MM-DD) the setup was generated for
    symbol:       str
    name:         str
    region:       str
    asset_class:  str
    grade:        str
    score:        float
    entry:        float
    stop:         float
    target:       float
    reward_risk:  float
    window_days:  int
    expected_days: Optional[int]   # v3: base-case trading days (v2 records lack it)
    source:       str
    outcome:      str          # PENDING | WIN | LOSS | EXPIRED | AMBIGUOUS
    resolved_on:  Optional[str]
    bars_to_resolve: Optional[int]
    logged_at:    str


def _parse_window_days(window: Any) -> int:
    """Extract the upper-bound horizon (trading days) from a window value/string."""
    if isinstance(window, (int, float)) and math.isfinite(window):
        return max(1, int(window))
    if isinstance(window, str):
        nums = [int(s) for s in window.replace("-", " ").split() if s.isdigit()]
        if nums:
            return max(nums)
    return DEFAULT_WINDOW_DAYS


def make_key(date_iso: str, symbol: str, grade: str) -> str:
    return f"{date_iso}:{symbol}:{grade}"


def _read_all() -> list[dict]:
    if not os.path.exists(_LEDGER_PATH):
        return []
    out: list[dict] = []
    try:
        with open(_LEDGER_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as exc:
        logger.warning("ledger read failed: %s", exc)
    return out


def _existing_keys() -> set[str]:
    return {r.get("key", "") for r in _read_all()}


def log_setup(setup: dict, *, date_iso: Optional[str] = None) -> bool:
    """Append a setup snapshot to the ledger (idempotent per date:symbol:grade).
    Returns True if written, False if a duplicate/invalid. Never raises."""
    try:
        symbol = setup.get("symbol")
        grade = setup.get("grade")
        entry = setup.get("entry")
        stop = setup.get("stop")
        target = setup.get("target")
        if not symbol or not grade or entry is None or stop is None or target is None:
            return False
        as_of = date_iso or setup.get("as_of") or datetime.now(timezone.utc).date().isoformat()
        key = make_key(as_of, symbol, grade)
        if key in _existing_keys():
            return False
        rec: LedgerEntry = LedgerEntry(
            key=key, date=as_of, symbol=symbol, name=setup.get("name", symbol),
            region=setup.get("region", "?"), asset_class=setup.get("asset_class", "?"),
            grade=grade, score=float(setup.get("score", 0.0)),
            entry=float(entry), stop=float(stop), target=float(target),
            reward_risk=float(setup.get("reward_risk", 0.0) or 0.0),
            window_days=_parse_window_days(setup.get("time_window_days")),
            expected_days=(int(setup["expected_trading_days"])
                           if isinstance(setup.get("expected_trading_days"), (int, float))
                           else None),
            source=setup.get("source", "?"),
            outcome="PENDING", resolved_on=None, bars_to_resolve=None,
            logged_at=datetime.now(timezone.utc).isoformat(),
        )
        with _WRITE_LOCK:
            if make_key(as_of, symbol, grade) in _existing_keys():
                return False  # re-check under lock (TOCTOU guard)
            with open(_LEDGER_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        return True
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("log_setup failed: %s", exc)
        return False


def classify(entry: float, stop: float, target: float,
             fut_highs: list, fut_lows: list, horizon: int) -> tuple[str, Optional[int]]:
    """First-touch barrier classification on subsequent daily bars.
    Returns (outcome, bars_to_resolve). Float-safe: only >= / <= comparisons."""
    n = min(len(fut_highs), len(fut_lows), max(1, horizon))
    for i in range(n):
        hi = fut_highs[i]
        lo = fut_lows[i]
        if hi is None or lo is None or not (math.isfinite(hi) and math.isfinite(lo)):
            continue
        hit_target = hi >= target
        hit_stop = lo <= stop
        if hit_target and hit_stop:
            return "AMBIGUOUS", i + 1      # same bar straddles -> not a win (KARPATHY)
        if hit_stop:
            return "LOSS", i + 1
        if hit_target:
            return "WIN", i + 1
    return "EXPIRED", None


def _rewrite(records: list[dict]) -> None:
    tmp = _LEDGER_PATH + ".tmp"
    with _WRITE_LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        os.replace(tmp, _LEDGER_PATH)


def aggregate() -> dict[str, Any]:
    """Honest aggregate: win-rate by grade with sample size + methodology."""
    records = _read_all()
    resolved = [r for r in records if r.get("outcome") in ("WIN", "LOSS", "AMBIGUOUS")]
    by_grade: dict[str, dict[str, Any]] = {}
    for g in ("A", "B", "C"):
        rs = [r for r in records if r.get("grade") == g]
        wins = sum(1 for r in rs if r.get("outcome") == "WIN")
        losses = sum(1 for r in rs if r.get("outcome") in ("LOSS", "AMBIGUOUS"))
        pending = sum(1 for r in rs if r.get("outcome") == "PENDING")
        expired = sum(1 for r in rs if r.get("outcome") == "EXPIRED")
        decided = wins + losses
        rate = round(100.0 * wins / decided, 1) if decided > 0 else None
        rr_vals = [r.get("reward_risk") for r in rs
                   if isinstance(r.get("reward_risk"), (int, float)) and r.get("reward_risk")]
        avg_rr = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None
        # Expectancy in R: win% * avg_reward - loss% * 1 (risk is 1R by definition).
        expectancy = None
        if decided > 0 and avg_rr is not None:
            wr = wins / decided
            expectancy = round(wr * avg_rr - (1.0 - wr) * 1.0, 3)
        by_grade[g] = {
            "logged": len(rs), "wins": wins, "losses": losses,
            "expired": expired, "pending": pending, "decided": decided,
            "win_rate_pct": rate,
            "avg_reward_risk": avg_rr,
            "expectancy_r": expectancy,
            "rate_reliable": decided >= MIN_SAMPLE_FOR_RATE,
        }
    dates = sorted(r.get("date", "") for r in records if r.get("date"))
    return {
        "status": "ok",
        "total_logged": len(records),
        "total_resolved": len(resolved),
        "last_evaluated": _LAST_EVAL_TS,  # <- NEW [autoeval]: null until first eval this process
        "by_grade": by_grade,
        "date_range": {"from": dates[0], "to": dates[-1]} if dates else None,
        "methodology": (
            "First-touch barrier on daily bars after the setup date: WIN if target "
            "is reached before stop within the time window; LOSS if stop first; "
            "same-bar straddle counts as not-a-win; EXPIRED if neither. "
            "Look-ahead-safe (setups scored using only data up to their date). "
            "Each setup targets a fixed reward:risk, so win rate must be read with "
            "expectancy_r (expected R-multiple per setup): positive expectancy can "
            "coexist with a sub-50% win rate."
        ),
        "disclaimer": "Decision-support, not advice. Past results do not predict future performance.",
    }


def timing_calibration() -> dict[str, Any]:
    """Historical time-to-target calibration from resolved WIN entries.

    For every WIN with a recorded bars_to_resolve, compare against the
    predicted base case: v3 records carry expected_days explicitly; v2
    records only stored the window upper bound, and v2 windows were
    "base..2*base", so expected is approximated as window_days / 2.

    Returns speed_factor = median(actual / expected), clamped to [0.5, 2.0],
    plus a median absolute percentage error. WIN-only by construction: this
    measures HOW FAST targets are reached when they ARE reached - it does not
    (and must not) restate the hit rate, which lives in aggregate().
    Per-grade splits are included when each grade clears MIN_SAMPLE_FOR_RATE.
    """
    records = _read_all()

    def _samples(rs: list[dict]) -> list[tuple[float, float]]:
        out = []
        for r in rs:
            if r.get("outcome") != "WIN":
                continue
            bars = r.get("bars_to_resolve")
            exp = r.get("expected_days") or (r.get("window_days") or 0) / 2.0
            if not bars or not exp or exp <= 0:
                continue
            out.append((bars / exp, abs(bars - exp) / exp))
        return out

    def _stats(samples: list[tuple[float, float]]) -> dict[str, Any]:
        n = len(samples)
        if n < MIN_SAMPLE_FOR_RATE:
            return {"n_samples": n, "reliable": False, "speed_factor": 1.0,
                    "median_abs_pct_error": None,
                    "note": "insufficient resolved WIN samples for calibration"}
        ratios = sorted(s[0] for s in samples)
        errs = sorted(s[1] for s in samples)
        med = ratios[n // 2]
        return {"n_samples": n, "reliable": True,
                "speed_factor": round(max(0.5, min(2.0, med)), 2),
                "median_actual_over_expected": round(med, 2),
                "median_abs_pct_error": round(errs[n // 2], 2)}

    overall = _stats(_samples(records))
    overall["by_grade"] = {
        g: _stats(_samples([r for r in records if r.get("grade") == g]))
        for g in ("A", "B", "C")}
    overall["methodology"] = (
        "WIN-only calibration on first-touch resolutions: speed_factor is the "
        "median of actual-bars-to-target over predicted-base-case days. It "
        "rescales future base-case estimates; it says nothing about hit rate.")
    return overall


# ---------------------------------------------------------------------------
# Evaluator + look-ahead-safe cold-start seeder (LLM Council, May 23 2026)
# ---------------------------------------------------------------------------
async def evaluate_open_entries(service: Any) -> dict[str, int]:  # <- NEW [autoeval]: serialized public entry
    """Serialize evaluation via _EVAL_LOCK so the background auto-evaluator and a
    manual ?evaluate=true call never interleave their read-modify-write of the
    ledger; records the last-eval timestamp for the aggregate report."""
    global _LAST_EVAL_TS
    async with _EVAL_LOCK:
        result = await _evaluate_open_entries_impl(service)
    _LAST_EVAL_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


async def _evaluate_open_entries_impl(service: Any) -> dict[str, int]:
    """Resolve PENDING ledger entries against subsequent DAILY bars.

    Look-ahead-safe: only bars strictly AFTER the setup date are considered.
    An entry stays PENDING until a barrier is touched OR the full window
    horizon of bars has elapsed - so a live setup logged today is never
    prematurely marked EXPIRED. Never raises per entry. Persists once."""
    from datetime import date as _date
    records = _read_all()
    if not records:
        return {"evaluated": 0, "resolved": 0, "still_pending": 0}
    resolved_count = 0
    still_pending = 0
    series_cache: dict[tuple[str, str], Any] = {}
    for rec in records:
        if rec.get("outcome") != "PENDING":
            continue
        symbol = rec.get("symbol")
        asset_class = rec.get("asset_class", "equity")
        try:
            setup_date = _date.fromisoformat(str(rec.get("date", "")))
        except ValueError:
            continue
        ck = (symbol, asset_class)
        if ck not in series_cache:
            try:
                series_cache[ck] = await service.get_series(symbol, asset_class)
            except Exception as exc:  # noqa: BLE001 - graceful: a miss leaves it PENDING
                logger.warning("evaluate: fetch failed for %s: %s", symbol, exc)
                series_cache[ck] = None
        series = series_cache[ck]
        if series is None or not getattr(series, "points", None):
            still_pending += 1
            continue
        future = [p for p in series.points if p.ts.date() > setup_date]
        if not future:
            still_pending += 1
            continue
        fut_highs = [p.high for p in future]
        fut_lows = [p.low for p in future]
        try:
            horizon = int(rec.get("window_days") or DEFAULT_WINDOW_DAYS)
            outcome, bars = classify(
                float(rec["entry"]), float(rec["stop"]), float(rec["target"]),
                fut_highs, fut_lows, horizon,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("evaluate: classify failed for %s: %s", symbol, exc)
            still_pending += 1
            continue
        if outcome == "EXPIRED" and len(future) < horizon:
            # Not enough subsequent bars yet to declare expiry - stay honest.
            still_pending += 1
            continue
        rec["outcome"] = outcome
        rec["bars_to_resolve"] = bars
        rec["resolved_on"] = datetime.now(timezone.utc).date().isoformat()
        resolved_count += 1
    _rewrite(records)
    return {"evaluated": len(records), "resolved": resolved_count, "still_pending": still_pending}


async def backfill_seed(service: Any, universe: list[tuple[str, str, str]],
                        as_of_dates: list[str]) -> dict[str, int]:
    """Look-ahead-safe cold-start seeding.

    For each (symbol, region, asset_class) and each PAST as_of date, score the
    setup using ONLY bars up to that date (sliced series), then log it PENDING.
    Resolution against later bars is performed separately by
    evaluate_open_entries (single classification path). Never raises per item."""
    from datetime import date as _date
    from .setup_scanner import score_setup
    logged = 0
    skipped = 0
    for symbol, region, asset_class in universe:
        try:
            series = await service.get_series(symbol, asset_class)
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed: fetch failed for %s: %s", symbol, exc)
            skipped += 1
            continue
        if series is None or not getattr(series, "points", None):
            skipped += 1
            continue
        pts = series.points
        for as_of in as_of_dates:
            try:
                cutoff = _date.fromisoformat(as_of)
            except ValueError:
                continue
            upto = [i for i, p in enumerate(pts) if p.ts.date() <= cutoff]
            if not upto:
                continue
            idx = upto[-1]
            if idx + 1 < MIN_BARS_TO_SCORE:
                skipped += 1
                continue
            closes = [p.close for p in pts[: idx + 1]]
            highs = [p.high for p in pts[: idx + 1]]
            lows = [p.low for p in pts[: idx + 1]]
            try:
                setup = score_setup(symbol, region, closes, highs, lows, asset_class=asset_class)
            except Exception as exc:  # noqa: BLE001
                logger.warning("seed: score failed for %s @ %s: %s", symbol, as_of, exc)
                continue
            if not setup:
                continue
            rec = dict(setup)
            rec["source"] = getattr(series, "source", "?")
            if log_setup(rec, date_iso=as_of):
                logged += 1
    return {"logged": logged, "skipped": skipped}
