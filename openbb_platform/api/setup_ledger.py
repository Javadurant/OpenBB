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
import re
import threading
from functools import lru_cache
from datetime import datetime, timezone
from typing import Any, Final, Optional, TypedDict

logger = logging.getLogger("setup_ledger")

_LEDGER_PATH: Final = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sentriq_ledger.jsonl")
LIVE_LEDGER_PATH: Final = _LEDGER_PATH   # public: for identity checks by tools/tests
MIN_SAMPLE_FOR_RATE: Final = 5      # below this, report "insufficient data"
MIN_BARS_TO_SCORE:   Final = 60     # need history depth before an as_of to score
DEFAULT_WINDOW_DAYS: Final = 18     # fallback horizon if a window can't be parsed

# ── Calibration eligibility (ADDITIVE - v3) ─────────────────────────────────
# A row can be present in the ledger (immutable audit history) and still be
# unfit to inform PERFORMANCE statistics. Two disjoint, evidence-based reasons;
# neither mutates, deletes or re-outcomes anything.
#
#  (1) STRUCTURAL - the stored geometry is impossible for a long setup. Derived
#      from the row itself: no external data, no threshold.
#  (2) PROVENANCE - the stored OUTCOME was produced by a structurally invalid
#      provider bar. Enumerated explicitly in the tracked manifest, each key
#      bound to an archived evidence file + sha256, never inferred from a
#      stop-distance threshold - no such threshold is defensible.
#
# CONTRACT (v3): every pre-existing field keeps its ALL-RECORD meaning, byte for
# byte. Eligibility is exposed ONLY through new, explicitly named *_eligible
# fields. Consumers opt in; nothing they already read changes underneath them.
#
# The manifest is DATA, not code, so its evidence hashes can be verified by a
# test. It loads from TRACKED source - never /tmp, never the untracked local
# audit archive: runtime must not depend on a local artifact.
_POLICY_PATH: Final = os.path.join(
    os.path.dirname(__file__), "policy", "calibration_eligibility_v1.json")

_STRUCTURAL_REASON: Final = "impossible_geometry"
_PROVENANCE_REASON: Final = "false_resolution_malformed_bar"
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


@lru_cache(maxsize=1)
def _calibration_policy() -> dict[str, Any]:
    """Load the eligibility manifest once.

    FAIL-SAFE AND ALL-OR-NOTHING. Any problem - missing file, unreadable, bad
    JSON, wrong shape, duplicate key, malformed sha256, missing field - logs an
    error and returns an EMPTY policy, so every row stays ELIGIBLE and the
    *_eligible fields simply equal their all-record counterparts. Entries are
    staged and committed only after the WHOLE manifest validates, so one bad
    record can never partially apply. Failing closed onto an unverified
    exclusion set would silently shrink a published track record.

    Tests must call _calibration_policy.cache_clear() after touching the file."""
    try:
        with open(_POLICY_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
        version = doc["policy_version"]
        entries = doc["provenance_rule"]["keys"]
        if not isinstance(version, str) or not version:
            raise ValueError("policy_version must be a non-empty string")
        if not isinstance(entries, list):
            raise ValueError("provenance_rule.keys must be a list")
        staged: dict[str, dict[str, Any]] = {}
        for e in entries:
            key = e["key"]
            if key in staged:
                raise ValueError(f"duplicate key in manifest: {key}")
            if e["reason"] != _PROVENANCE_REASON:
                raise ValueError(f"{key}: unexpected reason {e['reason']!r}")
            if not _SHA256_RE.match(str(e["evidence_sha256"])):
                raise ValueError(f"{key}: malformed evidence_sha256")
            for field in ("classification", "evidence_file", "audit_date"):
                if not str(e.get(field, "")).strip():
                    raise ValueError(f"{key}: missing {field}")
            staged[key] = e
        return {"policy_version": version, "keys": staged}   # committed only here
    except Exception:  # noqa: BLE001 - fail OPEN, never closed, never partial
        logger.error("calibration eligibility policy unusable at %s - treating "
                     "every row as eligible", _POLICY_PATH, exc_info=True)
        return {"policy_version": None, "keys": {}}


def _geometry_sound(rec: dict) -> bool:
    """True when the stored levels are a possible long setup: all finite and
    0 < stop < entry < target. Mirrors the scanner emission gate, so a row
    today's scanner would refuse cannot inform performance statistics."""
    try:
        entry = float(rec["entry"])
        stop = float(rec["stop"])
        target = float(rec["target"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(v) for v in (entry, stop, target)):
        return False
    return 0.0 < stop < entry < target


def calibration_ineligible_reason(rec: dict) -> Optional[str]:
    """Why this row must not inform performance statistics, or None if it may.
    Pure: never mutates the record."""
    if not _geometry_sound(rec):
        return _STRUCTURAL_REASON
    if rec.get("key") in _calibration_policy()["keys"]:
        return _PROVENANCE_REASON
    return None


def partition_eligibility(records: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Split into (eligible, [(record, reason), ...]) in ONE pass.

    Deliberately NOT keyed by rec['key']: a dict keyed that way would silently
    collapse - and over-exclude - if two rows ever shared a key."""
    eligible: list[dict] = []
    ineligible: list[tuple[dict, str]] = []
    for rec in records:
        reason = calibration_ineligible_reason(rec)
        (ineligible.append((rec, reason)) if reason else eligible.append(rec))
    return eligible, ineligible


def _eligibility_meta(ineligible: list[tuple[dict, str]]) -> dict[str, Any]:
    """Exclusion disclosure attached to every payload that reports *_eligible
    figures. An exclusion the caller cannot see is indistinguishable from a bug."""
    by_reason: dict[str, int] = {}
    for _rec, reason in ineligible:
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {
        "eligibility_policy_version": _calibration_policy()["policy_version"],
        "excluded_ineligible": len(ineligible),
        "excluded_by_reason": dict(sorted(by_reason.items())),
    }


def _outcome_stats(rs: list[dict]) -> dict[str, Any]:
    """Win/loss/expiry counts, win rate and expectancy for one row set.
    Arithmetic is identical to the pre-v3 inline computation."""
    wins = sum(1 for r in rs if r.get("outcome") == "WIN")
    losses = sum(1 for r in rs if r.get("outcome") in ("LOSS", "AMBIGUOUS"))
    pending = sum(1 for r in rs if r.get("outcome") == "PENDING")
    expired = sum(1 for r in rs if r.get("outcome") == "EXPIRED")
    decided = wins + losses
    rate = round(100.0 * wins / decided, 1) if decided > 0 else None
    rr_vals = [r.get("reward_risk") for r in rs
               if isinstance(r.get("reward_risk"), (int, float)) and r.get("reward_risk")]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None
    expectancy = None
    if decided > 0 and avg_rr is not None:
        wr = wins / decided
        expectancy = round(wr * avg_rr - (1.0 - wr) * 1.0, 3)
    return {"logged": len(rs), "wins": wins, "losses": losses, "expired": expired,
            "pending": pending, "decided": decided, "win_rate_pct": rate,
            "avg_reward_risk": avg_rr, "expectancy_r": expectancy}

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


def _resolve_ledger(path: Optional[str], *, writing: bool) -> str:
    """Resolve a ledger path, refusing accidental LIVE-ledger writes.

    path=None keeps the historical behaviour exactly: the live ledger. An
    EXPLICIT path that resolves to the live ledger while WRITING is always a
    mistake - the caller asked for a parallel file (backtest, recalibration,
    eval) and would silently corrupt the production trust ledger instead.
    Reads may target the live ledger explicitly; that is harmless."""
    if path is None:
        return _LEDGER_PATH
    resolved = os.path.realpath(path)
    if writing and resolved == os.path.realpath(LIVE_LEDGER_PATH):
        raise ValueError(
            "refusing to write: explicit ledger path resolves to the LIVE "
            f"ledger ({LIVE_LEDGER_PATH}). Pass a distinct parallel file, or "
            "omit path= to write the live ledger deliberately.")
    return resolved


def _read_all(path: Optional[str] = None) -> list[dict]:
    target = _resolve_ledger(path, writing=False)
    if not os.path.exists(target):
        return []
    out: list[dict] = []
    try:
        with open(target, "r", encoding="utf-8") as fh:
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


def _existing_keys(path: Optional[str] = None) -> set[str]:
    return {r.get("key", "") for r in _read_all(path)}


def log_setup(setup: dict, *, date_iso: Optional[str] = None,
              path: Optional[str] = None) -> bool:
    """Append a setup snapshot to the ledger (idempotent per date:symbol:grade).
    Returns True if written, False if a duplicate/invalid.

    Never raises on DATA problems (the historical contract). The ONE exception
    is a misdirected write TARGET: _resolve_ledger is called OUTSIDE the try so
    an explicit path resolving to the LIVE ledger raises loudly instead of being
    swallowed into a silent False. A caller that asked for a parallel file and
    got the production ledger must fail, not quietly no-op.
    path=None -> live ledger (unchanged)."""
    ledger_path = _resolve_ledger(path, writing=True)  # loud: deliberately outside the try
    try:                                              # NB: `target` below is the PRICE target
        symbol = setup.get("symbol")
        grade = setup.get("grade")
        entry = setup.get("entry")
        stop = setup.get("stop")
        target = setup.get("target")
        if not symbol or not grade or entry is None or stop is None or target is None:
            return False
        as_of = date_iso or setup.get("as_of") or datetime.now(timezone.utc).date().isoformat()
        key = make_key(as_of, symbol, grade)
        if key in _existing_keys(ledger_path):
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
            if make_key(as_of, symbol, grade) in _existing_keys(ledger_path):
                return False  # re-check under lock (TOCTOU guard)
            with open(ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        return True
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("log_setup failed: %s", exc)
        return False


def _usable_price(value: Any) -> Optional[float]:
    """Coerce one OHLCV field to a usable price, or report it unusable.

    Mirrors setup_scanner._usable_price deliberately: setup_scanner imports
    this module, so importing it back at module level would create a cycle.
    Returns None for missing, boolean (float(True) would silently become 1.0),
    non-numeric, NaN/infinity or non-positive values. Never raises."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0.0:
        return None
    return f


def _usable_bar(hi_raw: Any, lo_raw: Any) -> Optional[tuple[float, float]]:
    """Return (high, low) when the bar is structurally usable, else None.

    THE single definition of "usable bar" for barrier testing. classify(),
    usable_bar_count() and symbol_backtest's short path all call this, so they
    cannot disagree about which bars count - a counter that drifted from the
    classifier would reintroduce this defect one level up. Rejects missing,
    boolean, non-numeric, NaN/infinity and non-positive prices (via
    _usable_price) plus inverted bars. Nothing is substituted or repaired."""
    hi = _usable_price(hi_raw)
    lo = _usable_price(lo_raw)
    if hi is None or lo is None or hi < lo:
        return None
    return hi, lo


def usable_bar_count(fut_highs: list, fut_lows: list, horizon: int) -> int:
    """How many of the first `horizon` future bars are structurally usable.

    Callers need this to tell "the horizon passed without a touch" apart from
    "no usable bar was ever seen". Both make classify() return EXPIRED; only the
    first is an outcome. Bounded at `horizon` exactly as classify() bounds its
    scan, so the two always inspect the same window."""
    n = min(len(fut_highs), len(fut_lows), max(1, horizon))
    return sum(1 for i in range(n)
               if _usable_bar(fut_highs[i], fut_lows[i]) is not None)


def classify(entry: float, stop: float, target: float,
             fut_highs: list, fut_lows: list, horizon: int) -> tuple[str, Optional[int]]:
    """First-touch barrier classification on subsequent daily bars.
    Returns (outcome, bars_to_resolve). Float-safe: only >= / <= comparisons.

    Structurally invalid future bars are SKIPPED, not interpreted. A zero low
    is finite, so a bare isfinite() check would let high=low=0.0 (seen from
    NAV-only providers) satisfy `lo <= stop` and manufacture a first-bar LOSS
    against a setup that never actually traded there. Absence of a usable bar
    is absence of evidence, never evidence of a touch."""
    n = min(len(fut_highs), len(fut_lows), max(1, horizon))
    for i in range(n):
        bar = _usable_bar(fut_highs[i], fut_lows[i])
        if bar is None:
            continue
        hi, lo = bar
        hit_target = hi >= target
        hit_stop = lo <= stop
        if hit_target and hit_stop:
            return "AMBIGUOUS", i + 1      # same bar straddles -> not a win (KARPATHY)
        if hit_stop:
            return "LOSS", i + 1
        if hit_target:
            return "WIN", i + 1
    return "EXPIRED", None


def _rewrite(records: list[dict], path: Optional[str] = None) -> None:
    target = _resolve_ledger(path, writing=True)
    tmp = target + ".tmp"
    with _WRITE_LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        os.replace(tmp, target)


def aggregate(path: Optional[str] = None) -> dict[str, Any]:
    """Honest aggregate: win-rate by grade with sample size + methodology.
    path=None -> live ledger (unchanged); explicit reads are allowed."""
    records = _read_all() if path is None else _read_all(path)
    resolved = [r for r in records if r.get("outcome") in ("WIN", "LOSS", "AMBIGUOUS")]
    # v3: eligibility is REPORTED ALONGSIDE, never substituted. `records` stays
    # the all-record population for every pre-existing field.
    eligible, ineligible = partition_eligibility(records)
    resolved_eligible = [r for r in eligible
                         if r.get("outcome") in ("WIN", "LOSS", "AMBIGUOUS")]
    excluded_by_grade: dict[str, int] = {}
    for rec, _reason in ineligible:
        gr = rec.get("grade")
        if gr:
            excluded_by_grade[gr] = excluded_by_grade.get(gr, 0) + 1
    by_grade: dict[str, dict[str, Any]] = {}
    for g in ("A", "B", "C"):
        rs = [r for r in records if r.get("grade") == g]
        all_stats = _outcome_stats(rs)
        eligible_stats = _outcome_stats([r for r in eligible if r.get("grade") == g])
        decided = all_stats["decided"]
        by_grade[g] = {
            # ── ALL-RECORD audit statistics: meaning UNCHANGED from pre-v3 ──
            "logged": all_stats["logged"], "wins": all_stats["wins"],
            "losses": all_stats["losses"], "expired": all_stats["expired"],
            "pending": all_stats["pending"], "decided": decided,
            "win_rate_pct": all_stats["win_rate_pct"],
            "avg_reward_risk": all_stats["avg_reward_risk"],
            "expectancy_r": all_stats["expectancy_r"],
            "rate_reliable": decided >= MIN_SAMPLE_FOR_RATE,
            # ── ELIGIBILITY-ADJUSTED performance statistics: NEW, opt-in ──
            "logged_eligible": eligible_stats["logged"],
            "wins_eligible": eligible_stats["wins"],
            "losses_eligible": eligible_stats["losses"],
            "expired_eligible": eligible_stats["expired"],
            "pending_eligible": eligible_stats["pending"],
            "decided_eligible": eligible_stats["decided"],
            "win_rate_pct_eligible": eligible_stats["win_rate_pct"],
            "expectancy_r_eligible": eligible_stats["expectancy_r"],
            "rate_reliable_eligible": eligible_stats["decided"] >= MIN_SAMPLE_FOR_RATE,
            "excluded": excluded_by_grade.get(g, 0),
        }
    dates = sorted(r.get("date", "") for r in records if r.get("date"))
    return {
        "status": "ok",
        "total_logged": len(records),                 # ALL rows - meaning UNCHANGED
        "total_resolved": len(resolved),              # ALL rows - meaning UNCHANGED
        "total_eligible": len(eligible),
        "total_resolved_eligible": len(resolved_eligible),
        **_eligibility_meta(ineligible),
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
            "coexist with a sub-50% win rate. EVERY field above reports the "
            "ALL-RECORD population and is unchanged. The parallel *_eligible "
            "fields additionally report performance over rows that remain "
            "CALIBRATION-ELIGIBLE: rows whose stored geometry is impossible, or "
            "whose outcome was produced by a structurally invalid provider bar, "
            "are withheld there and counted in excluded_by_reason. Excluded rows "
            "stay in the ledger as immutable audit history; nothing is deleted, "
            "rewritten or re-outcomed."
        ),
        "disclaimer": "Decision-support, not advice. Past results do not predict future performance.",
    }


def timing_calibration(path: Optional[str] = None) -> dict[str, Any]:
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
    path=None -> live ledger (unchanged); explicit reads are allowed.
    """
    records = _read_all() if path is None else _read_all(path)

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
    # v3: calibration metrics are computed over the FULL record set exactly as
    # before - bit-identical. The eligibility policy is DISCLOSED here so the
    # same metadata travels with both payloads, but it does not filter: no WIN
    # is currently excluded, so filtering would be a no-op that only risked
    # perturbing a published constant.
    _eligible_unused, _ineligible = partition_eligibility(records)
    overall.update(_eligibility_meta(_ineligible))
    overall["methodology"] = (
        "WIN-only calibration on first-touch resolutions: speed_factor is the "
        "median of actual-bars-to-target over predicted-base-case days. It "
        "rescales future base-case estimates; it says nothing about hit rate. "
        "Metrics here cover ALL records and are unchanged by the eligibility "
        "policy; excluded_by_reason is reported for transparency only.")
    return overall


# ---------------------------------------------------------------------------
# Evaluator + look-ahead-safe cold-start seeder (LLM Council, May 23 2026)
# ---------------------------------------------------------------------------
async def evaluate_open_entries(service: Any, *, path: Optional[str] = None) -> dict[str, int]:  # <- NEW [autoeval]: serialized public entry
    """Serialize evaluation via _EVAL_LOCK so the background auto-evaluator and a
    manual ?evaluate=true call never interleave their read-modify-write of the
    ledger; records the last-eval timestamp for the aggregate report."""
    global _LAST_EVAL_TS
    async with _EVAL_LOCK:
        result = await _evaluate_open_entries_impl(service, path=path)
    _LAST_EVAL_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


async def _evaluate_open_entries_impl(service: Any, *, path: Optional[str] = None) -> dict[str, int]:
    """Resolve PENDING ledger entries against subsequent DAILY bars.

    Look-ahead-safe: only bars strictly AFTER the setup date are considered.
    An entry stays PENDING until a barrier is touched OR the full window
    horizon of bars has elapsed - so a live setup logged today is never
    prematurely marked EXPIRED. Never raises per entry. Persists once."""
    from datetime import date as _date
    target = _resolve_ledger(path, writing=True)   # resolve ONCE: read and
    records = _read_all(target)                    # rewrite must never diverge
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
        if (outcome == "EXPIRED"
                and usable_bar_count(fut_highs, fut_lows, horizon) < horizon):
            # Not enough USABLE subsequent bars to declare expiry - stay honest.
            # len(future) counted bars the PROVIDER RETURNED, including ones
            # classify() refused to read; expiring on those asserts an outcome
            # from evidence we never had.
            still_pending += 1
            continue
        rec["outcome"] = outcome
        rec["bars_to_resolve"] = bars
        rec["resolved_on"] = datetime.now(timezone.utc).date().isoformat()
        resolved_count += 1
    _rewrite(records, target)
    return {"evaluated": len(records), "resolved": resolved_count, "still_pending": still_pending}


async def backfill_seed(service: Any, universe: list[tuple[str, str, str]],
                        as_of_dates: list[str], *,
                        path: Optional[str] = None) -> dict[str, int]:
    """Look-ahead-safe cold-start seeding.

    For each (symbol, region, asset_class) and each PAST as_of date, score the
    setup using ONLY bars up to that date (sliced series), then log it PENDING.
    Resolution against later bars is performed separately by
    evaluate_open_entries (single classification path). Never raises per item."""
    from datetime import date as _date
    from .setup_scanner import score_setup
    _resolve_ledger(path, writing=True)   # fail fast BEFORE any fetch work
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
            if log_setup(rec, date_iso=as_of, path=path):
                logged += 1
    return {"logged": logged, "skipped": skipped}
