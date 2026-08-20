"""Funnel observability: shortlisted/dropped counters + visible scoring failures.

Pins the defect this replaces: a shortlisted entry that raised was logged at
DEBUG while the service runs at INFO, and one that returned None was not logged
at all — so `eligible - capped_out` never reconciled with `scanned` and no
caller could see which names had vanished.

Every assertion also guards the property that matters far more than the
counters: exposing the losses must not move a single candidate, score, grade,
conflict, rank or winner.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.broad_scan import broad_scan  # noqa: E402

_NAMES = ["VOLV_B", "SKF_B", "ERIC_B", "SAND", "ATCO_A", "HM_B"]
SYMS = [f"{n.replace('_', '-')}.ST" for n in _NAMES]

_DISC = {"coverage_label": "full_exchange_market",
         "symbols": [{"symbol": s, "asset_class": "equity"} for s in SYMS]}
_SCREEN = [{"symbol": f"OMXSTO:{n}", "type": "stock", "close": 100.0,
            "average_volume_10d_calc": 5_000_000 - i * 100_000}
           for i, n in enumerate(_NAMES)]


def _score_fn(behaviour: dict):
    """behaviour[symbol] -> 'A'|'B'|'C' to grade, 'raise', or 'none'."""
    def score(entry, calibration=None, regime_map=None, news_enabled=True):
        sym = entry[0]
        b = behaviour.get(sym, "C")
        if b == "raise":
            raise RuntimeError("simulated scorer failure")
        if b == "none":
            return None
        return {"symbol": sym, "region": entry[1], "asset_class": entry[2],
                "grade": b, "score": 90.0 - SYMS.index(sym),
                "conflicts": [] if b == "A" else ["some conflict"],
                "classification": "x", "last_price": 1.0}
    return score


def _run(behaviour: dict) -> dict:
    return broad_scan("Swedish", score_fn=_score_fn(behaviour),
                      discover_fn=lambda e: _DISC,
                      screener_fn=lambda market, limit=300: _SCREEN, depth=10)


def _reconciles(r: dict) -> bool:
    return r["shortlisted"] - sum(r["dropped"].values()) == r["scanned"]


# ── counters ────────────────────────────────────────────────────────────────
def test_shortlisted_is_exposed():
    assert _run({})["shortlisted"] == len(SYMS)


def test_clean_run_reports_zero_drops_and_reconciles():
    r = _run({})
    assert r["dropped"] == {"score_error": 0, "no_result": 0}
    assert r["scanned"] == len(SYMS)
    assert _reconciles(r)


def test_score_error_is_counted_and_not_double_counted():
    r = _run({SYMS[0]: "raise", SYMS[1]: "raise"})
    assert r["dropped"]["score_error"] == 2
    assert r["dropped"]["no_result"] == 0, "a raise must not also count as no_result"
    assert _reconciles(r)


def test_no_result_is_counted_separately():
    r = _run({SYMS[0]: "none", SYMS[1]: "none", SYMS[2]: "none"})
    assert r["dropped"] == {"score_error": 0, "no_result": 3}
    assert _reconciles(r)


def test_mixed_drops_reconcile_exactly():
    r = _run({SYMS[0]: "raise", SYMS[1]: "none", SYMS[2]: "none"})
    assert r["dropped"] == {"score_error": 1, "no_result": 2}
    assert r["scanned"] == 3
    assert _reconciles(r)


def test_scoring_failure_is_visible_at_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _run({SYMS[0]: "raise"})
    assert any(rec.levelno >= logging.WARNING and "broad-scan score error" in rec.getMessage()
               for rec in caplog.records), "swallowed failure must surface at the service log level"


# ── the invariant: selection is untouched ───────────────────────────────────
_FIXTURE = {SYMS[0]: "A", SYMS[1]: "B", SYMS[2]: "C",
            SYMS[3]: "C", SYMS[4]: "B", SYMS[5]: "A"}


def test_fixed_fixture_produces_identical_grades_scores_and_order():
    r = _run(_FIXTURE)
    assert [x["symbol"] for x in r["grade_a"]] == [SYMS[0], SYMS[5]]
    assert [x["symbol"] for x in r["grade_b"]] == [SYMS[1], SYMS[4]]
    assert [x["symbol"] for x in r["grade_c"]] == [SYMS[2], SYMS[3]]
    assert r["grade_a_count"] == 2 and r["grade_b_count"] == 2
    assert [x["score"] for x in r["grade_a"]] == [90.0, 85.0]
    assert r["grade_a"][0]["conflicts"] == []


def test_winner_unchanged_when_another_candidate_drops():
    base = _run(_FIXTURE)
    dropped = _run({**_FIXTURE, SYMS[3]: "none"})   # drop a Grade C
    assert base["grade_a"][0]["symbol"] == dropped["grade_a"][0]["symbol"]
    assert base["grade_a"][0]["score"] == dropped["grade_a"][0]["score"]
    assert base["grade_a"][0]["conflicts"] == dropped["grade_a"][0]["conflicts"]
    assert dropped["dropped"]["no_result"] == 1


def test_grade_first_ordering_preserved():
    r = _run(_FIXTURE)
    order = [x["grade"] for x in r["grade_a"] + r["grade_b"] + r["grade_c"]]
    assert order == sorted(order), "grade-first ordering must hold"


def test_no_ledger_write():
    root = Path(__file__).resolve().parents[2]
    snap = {p: p.stat().st_size for p in root.glob("sentriq_ledger*.jsonl")}
    assert snap, "ledger fixtures must exist for this guard to mean anything"
    _run(_FIXTURE)
    assert {p: p.stat().st_size for p in root.glob("sentriq_ledger*.jsonl")} == snap
