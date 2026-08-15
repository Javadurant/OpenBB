"""evaluate_open_entries() against malformed provider bars — temp ledgers only.

Closes the last untested gap in the 2026-08-08 zero-OHLCV containment: the
hardened `classify()` was proven in isolation, but the full evaluation path that
feeds it — fetch series, slice future bars, classify, persist — was never
exercised against the malformed shapes that caused the defect.

SAFETY MODEL
  * Every write targets a pytest `tmp_path` ledger. The live and eval ledgers are
    never opened for writing; a spy asserts this rather than assuming it, and the
    session conftest guard independently verifies their content hashes.
  * No network, no real market-data service, no token, no SOTD route. The data
    service is a local stub.
  * The five negative-stop rows are reproduced as immutable COPIES of the real
    stored shapes. The real ledger is read-only here and never mutated.

DATA PROVENANCE — READ THIS BEFORE REUSING ANY NUMBER
  The five row shapes are real values copied from the live trust ledger.
  Every OHLCV bar in this file is SYNTHETIC test data, constructed to exercise a
  code path. Synthetic bars are NOT historical market evidence and must never be
  cited as such. Real contemporaneous evidence lives in the provenance archive.
"""
from __future__ import annotations

import builtins
import hashlib
import json
import math
import os
import pathlib
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.setup_ledger import (  # noqa: E402
    _read_all, classify, evaluate_open_entries, usable_bar_count,
)
from api.symbol_backtest import _classify_directional  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIVE_LEDGER = ROOT / "sentriq_ledger.jsonl"
EVAL_LEDGER = ROOT / "sentriq_ledger_v33_eval.jsonl"

# ── Real stored row shapes (copied, never mutated) ───────────────────────────
# The five PENDING rows whose ATR was inflated by high=low=0.0 bars, producing a
# stop below zero. window_days is large for the same reason: the inflated ATR
# widened the time-to-target window. That matters here — a row cannot be declared
# EXPIRED until `horizon` future bars exist, so these cannot expire in any
# realistic window.
NEGATIVE_STOP_ROWS: list[dict] = [
    {"key": "2026-07-30:0P00000L4S.ST:C", "date": "2026-07-30", "symbol": "0P00000L4S.ST",
     "asset_class": "fund", "entry": 330.9, "stop": -18.17, "target": 1029.04,
     "window_days": 478, "expected_days": 146, "outcome": "PENDING", "grade": "C"},
    {"key": "2026-08-03:0P0000ULAP.ST:C", "date": "2026-08-03", "symbol": "0P0000ULAP.ST",
     "asset_class": "fund", "entry": 1014.01, "stop": -147.75, "target": 3337.53,
     "window_days": 336, "expected_days": 134, "outcome": "PENDING", "grade": "C"},
    {"key": "2026-08-04:0P0000XAIN.ST:C", "date": "2026-08-04", "symbol": "0P0000XAIN.ST",
     "asset_class": "fund", "entry": 681.92, "stop": -329.54, "target": 2704.84,
     "window_days": 616, "expected_days": 192, "outcome": "PENDING", "grade": "C"},
    {"key": "2026-08-05:0P0000XAIN.ST:C", "date": "2026-08-05", "symbol": "0P0000XAIN.ST",
     "asset_class": "fund", "entry": 688.78, "stop": -322.73, "target": 2711.8,
     "window_days": 590, "expected_days": 191, "outcome": "PENDING", "grade": "C"},
    {"key": "2026-08-06:0P0000XAIN.ST:C", "date": "2026-08-06", "symbol": "0P0000XAIN.ST",
     "asset_class": "fund", "entry": 684.25, "stop": -328.49, "target": 2709.73,
     "window_days": 582, "expected_days": 190, "outcome": "PENDING", "grade": "C"},
]

# A structurally VALID row, used to prove genuine barrier events still resolve.
# SYNTHETIC TEST DATA — not a real setup.
VALID_ROW: dict = {
    "key": "2026-07-01:SYNTHETIC.TEST:C", "date": "2026-07-01", "symbol": "SYNTHETIC.TEST",
    "asset_class": "equity", "entry": 100.0, "stop": 90.0, "target": 120.0,
    "window_days": 10, "expected_days": 5, "outcome": "PENDING", "grade": "C",
}


# ── Synthetic offline data service ───────────────────────────────────────────

@dataclass
class _Bar:
    """SYNTHETIC bar. `high`/`low` are deliberately typed loosely so malformed
    provider shapes (None, str, NaN, inf) can be represented faithfully."""
    ts: datetime
    high: object
    low: object


class _Series:
    def __init__(self, points):
        self.points = points


class StubService:
    """Offline stand-in for data_ingestion.service. No network, ever."""

    def __init__(self, bars_by_symbol: dict[str, list[_Bar]]):
        self._bars = bars_by_symbol
        self.calls: list[tuple[str, str]] = []

    async def get_series(self, symbol: str, asset_class: str, *a, **kw):
        self.calls.append((symbol, asset_class))
        bars = self._bars.get(symbol)
        return _Series(bars) if bars is not None else None


def _bars_from(start: str, specs: list[tuple[object, object]]) -> list[_Bar]:
    """Build consecutive daily bars beginning the day AFTER `start`."""
    d0 = date.fromisoformat(start)
    return [_Bar(datetime.combine(d0 + timedelta(days=i + 1),
                                  datetime.min.time(), tzinfo=timezone.utc), hi, lo)
            for i, (hi, lo) in enumerate(specs)]


# The five malformed shapes required by the containment spec. SYNTHETIC.
MALFORMED_SPECS: list[tuple[object, object]] = [
    (0.0, 0.0),                       # high = low = 0  (the observed fund defect)
    (None, None),                     # missing
    ("n/a", "n/a"),                   # non-numeric
    (float("nan"), float("inf")),     # NaN / infinity
    (95.0, 110.0),                    # high < low (inverted)
]


def _write_ledger(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _read_ledger(path: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def guarded_open(monkeypatch):
    """Fail loudly if anything opens a REAL ledger for writing.

    Hash comparison proves content did not change; this proves intent — a write
    that happened to rewrite identical bytes would still be a policy breach."""
    real_open = builtins.open
    guarded = {os.path.realpath(LIVE_LEDGER), os.path.realpath(EVAL_LEDGER)}
    violations: list[str] = []

    def spy(file, mode="r", *args, **kwargs):
        try:
            target = os.path.realpath(file)
        except TypeError:      # file descriptors etc.
            target = ""
        if any(m in mode for m in ("w", "a", "x", "+")) and target in guarded:
            violations.append(f"{target} opened with mode={mode!r}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    yield violations
    assert not violations, f"REAL LEDGER OPENED FOR WRITING: {violations}"


# ── 1-7. The five real negative-stop shapes ──────────────────────────────────

@pytest.mark.parametrize("row", NEGATIVE_STOP_ROWS, ids=lambda r: r["key"])
async def test_negative_stop_row_is_not_resolved_by_malformed_bars(row, tmp_path, guarded_open):
    """Requirements 2, 4, 5, 6, 7 — per row shape.

    A malformed bar must not resolve the row, and the negative stop must be
    carried through untouched: not clamped to zero, not normalised, not repaired."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(row)])
    svc = StubService({row["symbol"]: _bars_from(row["date"], MALFORMED_SPECS)})

    result = await evaluate_open_entries(svc, path=str(led))

    out = _read_ledger(led)
    assert len(out) == 1
    rec = out[0]
    assert rec["outcome"] == "PENDING", "malformed bars must not resolve a row"
    assert rec.get("bars_to_resolve") is None
    assert rec.get("resolved_on") is None
    assert rec["stop"] == row["stop"] and rec["stop"] < 0, "negative stop was altered"
    assert rec["entry"] == row["entry"] and rec["target"] == row["target"]
    assert result["resolved"] == 0 and result["still_pending"] == 1


@pytest.mark.parametrize("row", NEGATIVE_STOP_ROWS, ids=lambda r: r["key"])
async def test_negative_stop_row_unreachable_barriers_stay_pending(row, tmp_path, guarded_open):
    """Valid bars at realistic prices cannot touch a sub-zero stop or a target
    ~4x entry, so the row must stay PENDING — no barrier event exists."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(row)])
    px = float(row["entry"])
    specs = [(px * 1.01, px * 0.99) for _ in range(12)]   # SYNTHETIC, plausible range
    svc = StubService({row["symbol"]: _bars_from(row["date"], specs)})

    await evaluate_open_entries(svc, path=str(led))

    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "PENDING"
    assert rec["stop"] < 0, "stop must remain negative and uninterpreted"


async def test_all_five_shapes_together_remain_pending(tmp_path, guarded_open):
    """All five in one ledger, mixed malformed feed — none may resolve."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(r) for r in NEGATIVE_STOP_ROWS])
    svc = StubService({r["symbol"]: _bars_from(r["date"], MALFORMED_SPECS)
                       for r in NEGATIVE_STOP_ROWS})

    result = await evaluate_open_entries(svc, path=str(led))

    out = _read_ledger(led)
    assert len(out) == len(NEGATIVE_STOP_ROWS)
    assert {r["outcome"] for r in out} == {"PENDING"}
    assert result["resolved"] == 0
    assert all(r["stop"] < 0 for r in out)


# ── 8-10. Genuine events still resolve ───────────────────────────────────────

async def test_genuine_stop_hit_resolves_loss(tmp_path, guarded_open):
    """Requirement 8 — a real stop event on a valid row still classifies LOSS."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = [(101.0, 97.0), (99.0, 89.5)]        # SYNTHETIC: bar 2 breaches stop 90
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})

    await evaluate_open_entries(svc, path=str(led))

    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "LOSS"
    assert rec["bars_to_resolve"] == 2


async def test_genuine_target_hit_resolves_win(tmp_path, guarded_open):
    """Requirement 9 — a real target event on a valid row still classifies WIN."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = [(105.0, 99.0), (121.0, 110.0)]      # SYNTHETIC: bar 2 reaches target 120
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})

    await evaluate_open_entries(svc, path=str(led))

    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "WIN"
    assert rec["bars_to_resolve"] == 2


async def test_malformed_bars_are_skipped_not_counted_before_a_genuine_event(
        tmp_path, guarded_open):
    """Requirement 10 — malformed bars ahead of a real event must be skipped, and
    must not be mistaken for the event or shift its bar index."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = list(MALFORMED_SPECS) + [(121.0, 118.0)]   # SYNTHETIC: real WIN at bar 6
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})

    await evaluate_open_entries(svc, path=str(led))

    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "WIN"
    assert rec["bars_to_resolve"] == len(specs), (
        "a skipped bar must still consume its position; the resolving bar index "
        "has to reflect real elapsed bars")


async def test_zero_low_never_produces_a_loss_on_a_valid_row(tmp_path, guarded_open):
    """The original defect, end to end: zero lows against a positive stop."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = [(0.0, 0.0)] * 5                     # SYNTHETIC: the fund-feed shape
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})

    await evaluate_open_entries(svc, path=str(led))

    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "PENDING", "zero lows must never manufacture a LOSS"


async def test_missing_series_leaves_row_pending(tmp_path, guarded_open):
    """A provider miss is absence of evidence, never an outcome."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(NEGATIVE_STOP_ROWS[0])])
    svc = StubService({})                        # get_series returns None

    result = await evaluate_open_entries(svc, path=str(led))

    assert _read_ledger(led)[0]["outcome"] == "PENDING"
    assert result["still_pending"] == 1


# ── 11-16. Isolation, immutability, cleanup ──────────────────────────────────

async def test_real_ledgers_are_never_opened_for_writing(tmp_path, guarded_open):
    """Requirements 11-13. The guarded_open fixture asserts on teardown."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(r) for r in NEGATIVE_STOP_ROWS])
    svc = StubService({r["symbol"]: _bars_from(r["date"], MALFORMED_SPECS)
                       for r in NEGATIVE_STOP_ROWS})
    await evaluate_open_entries(svc, path=str(led))
    assert led.exists(), "the temp ledger is the only write target"


async def test_five_real_historical_rows_remain_byte_identical(tmp_path, guarded_open):
    """Requirement 14 — the real rows are untouched by any of this."""
    before_hash = _sha256(LIVE_LEDGER)
    before_rows = [r for r in _read_all()
                   if isinstance(r.get("stop"), (int, float)) and r["stop"] <= 0]
    assert len(before_rows) == 5

    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(r) for r in NEGATIVE_STOP_ROWS])
    svc = StubService({r["symbol"]: _bars_from(r["date"], MALFORMED_SPECS)
                       for r in NEGATIVE_STOP_ROWS})
    await evaluate_open_entries(svc, path=str(led))

    after_rows = [r for r in _read_all()
                  if isinstance(r.get("stop"), (int, float)) and r["stop"] <= 0]
    assert after_rows == before_rows
    assert _sha256(LIVE_LEDGER) == before_hash
    # Each real row still matches the copy this file asserts against.
    by_key = {r["key"]: r for r in after_rows}
    for row in NEGATIVE_STOP_ROWS:
        real = by_key[row["key"]]
        for field in ("entry", "stop", "target", "window_days", "outcome", "grade"):
            assert real[field] == row[field], f"{row['key']}.{field} drifted"


async def test_temp_ledger_is_isolated_and_removable(tmp_path, guarded_open):
    """Requirement 15 — writes stay inside tmp_path, which pytest cleans up."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    svc = StubService({VALID_ROW["symbol"]:
                       _bars_from(VALID_ROW["date"], [(121.0, 118.0)])})
    await evaluate_open_entries(svc, path=str(led))

    produced = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert produced == {led}, f"unexpected artifacts outside the temp ledger: {produced}"
    assert str(tmp_path) not in (str(LIVE_LEDGER), str(EVAL_LEDGER))
    for p in produced:
        p.unlink()
    assert not any(tmp_path.rglob("*"))


def test_refuses_an_explicit_path_that_resolves_to_the_live_ledger():
    """The pre-existing write guard still holds — asserted, not assumed."""
    from api.setup_ledger import _resolve_ledger
    with pytest.raises(ValueError, match="refusing to write"):
        _resolve_ledger(str(LIVE_LEDGER), writing=True)
    assert _resolve_ledger(str(LIVE_LEDGER), writing=False)  # reads stay allowed


# ═════════════════════════════════════════════════════════════════════════════
# Expiry must be decided on USABLE bars, and the short side must not fabricate
# outcomes from malformed bars. Requirements 1-25.
#
# DATA PROVENANCE: every bar below is SYNTHETIC. Only the five negative-stop row
# SHAPES are real values copied from the live ledger.
# ═════════════════════════════════════════════════════════════════════════════

VALID_NO_TOUCH = (101.0, 99.0)      # long: inside both barriers
GENUINE_TARGET = (121.0, 118.0)     # long: breaches target 120
GENUINE_STOP = (99.0, 89.5)         # long: breaches stop 90
STRADDLE = (125.0, 85.0)            # long: same bar hits both

# SHORT geometry: target 80 < entry 100 < stop 110
S_ENTRY, S_STOP, S_TARGET = 100.0, 110.0, 80.0
S_TARGET_HIT = (85.0, 79.0)
S_STOP_HIT = (111.0, 105.0)
S_STRADDLE = (115.0, 75.0)
S_NO_TOUCH = (105.0, 95.0)


def _hl(specs):
    return [h for h, _ in specs], [l for _, l in specs]


# ── usable_bar_count primitive ───────────────────────────────────────────────

def test_usable_bar_count_rejects_every_invalid_shape():
    for bad in (None, "n/a", float("nan"), float("inf"), float("-inf"),
                object(), True, False, -5.0, 0.0):
        assert usable_bar_count([bad], [bad], 1) == 0


def test_usable_bar_count_is_bounded_by_horizon():
    specs = list(MALFORMED_SPECS) + [VALID_NO_TOUCH] * 3
    h, l = _hl(specs)
    assert usable_bar_count(h, l, len(specs)) == 3
    assert usable_bar_count(h, l, 2) == 0
    assert usable_bar_count(h, l, 6) == 1


# ── 1-9. Expiry correction ───────────────────────────────────────────────────

async def test_1_all_malformed_at_or_beyond_horizon_stays_pending(tmp_path, guarded_open):
    led = tmp_path / "temp_ledger.jsonl"
    row = dict(VALID_ROW, window_days=3)
    _write_ledger(led, [row])
    svc = StubService({row["symbol"]: _bars_from(row["date"], MALFORMED_SPECS)})
    result = await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "PENDING"
    assert rec.get("resolved_on") is None
    assert result["resolved"] == 0


async def test_2_valid_no_touch_below_horizon_stays_pending(tmp_path, guarded_open):
    led = tmp_path / "temp_ledger.jsonl"
    row = dict(VALID_ROW, window_days=3)
    _write_ledger(led, [row])
    svc = StubService({row["symbol"]: _bars_from(row["date"], [VALID_NO_TOUCH] * 2)})
    await evaluate_open_entries(svc, path=str(led))
    assert _read_ledger(led)[0]["outcome"] == "PENDING"


async def test_3_valid_no_touch_at_horizon_expires(tmp_path, guarded_open):
    """Genuine expiry must survive - the fix must not make rows immortal."""
    led = tmp_path / "temp_ledger.jsonl"
    row = dict(VALID_ROW, window_days=3)
    _write_ledger(led, [row])
    svc = StubService({row["symbol"]: _bars_from(row["date"], [VALID_NO_TOUCH] * 3)})
    result = await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "EXPIRED"
    assert rec["bars_to_resolve"] is None
    assert rec["resolved_on"] is not None
    assert result["resolved"] == 1


async def test_4_mixed_below_usable_horizon_stays_pending(tmp_path, guarded_open):
    """Fetched count clears the horizon; usable count does not."""
    led = tmp_path / "temp_ledger.jsonl"
    row = dict(VALID_ROW, window_days=5)
    _write_ledger(led, [row])
    specs = list(MALFORMED_SPECS[:2]) + [VALID_NO_TOUCH] * 3
    svc = StubService({row["symbol"]: _bars_from(row["date"], specs)})
    await evaluate_open_entries(svc, path=str(led))
    assert _read_ledger(led)[0]["outcome"] == "PENDING"


async def test_5_mixed_at_usable_horizon_no_event_expires(tmp_path, guarded_open):
    """Horizon window fully usable, malformed bars only AFTER it."""
    led = tmp_path / "temp_ledger.jsonl"
    row = dict(VALID_ROW, window_days=3)
    _write_ledger(led, [row])
    specs = [VALID_NO_TOUCH] * 3 + list(MALFORMED_SPECS)
    svc = StubService({row["symbol"]: _bars_from(row["date"], specs)})
    await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "EXPIRED"
    assert rec["resolved_on"] is not None


async def test_6_malformed_then_genuine_target_wins(tmp_path, guarded_open):
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = list(MALFORMED_SPECS) + [GENUINE_TARGET]
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})
    await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "WIN"
    assert rec["bars_to_resolve"] == len(specs)


async def test_7_malformed_then_genuine_stop_loses(tmp_path, guarded_open):
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(VALID_ROW)])
    specs = list(MALFORMED_SPECS) + [GENUINE_STOP]
    svc = StubService({VALID_ROW["symbol"]: _bars_from(VALID_ROW["date"], specs)})
    await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "LOSS"
    assert rec["bars_to_resolve"] == len(specs)


def test_8_long_ambiguous_ordering_unchanged():
    assert classify(100.0, 90.0, 120.0, [STRADDLE[0]], [STRADDLE[1]], 5) == ("AMBIGUOUS", 1)
    h, l = _hl(list(MALFORMED_SPECS) + [STRADDLE])
    assert classify(100.0, 90.0, 120.0, h, l, 10) == ("AMBIGUOUS", 6)


@pytest.mark.parametrize("row", NEGATIVE_STOP_ROWS, ids=lambda r: r["key"])
async def test_9_negative_stop_rows_unchanged_and_pending(row, tmp_path, guarded_open):
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(row)])
    svc = StubService({row["symbol"]: _bars_from(row["date"], MALFORMED_SPECS)})
    await evaluate_open_entries(svc, path=str(led))
    rec = _read_ledger(led)[0]
    assert rec["outcome"] == "PENDING"
    assert rec["stop"] == row["stop"] < 0, "negative stop was reinterpreted"
    assert rec["entry"] == row["entry"] and rec["target"] == row["target"]


# ── 10-17. Short-side correction ─────────────────────────────────────────────

def test_10_zero_low_short_bar_does_not_win():
    """THE DEFECT: `lo <= target` fired unconditionally on a zero low, so an
    empty bar fabricated a short WIN."""
    outcome, bars = _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                          [0.0], [0.0], 5)
    assert outcome != "WIN", "a zero-low bar fabricated a short WIN"
    assert (outcome, bars) == ("EXPIRED", None)


def test_11_zero_high_short_bar_does_not_fabricate_loss():
    outcome, _ = _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                       [0.0], [95.0], 5)
    assert outcome not in ("LOSS", "WIN")


def test_12_short_malformed_bars_are_skipped_safely():
    for bad in (None, "n/a", float("nan"), float("inf"), float("-inf"),
                object(), True, False, -1.0, 0.0):
        outcome, _ = _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                           [bad], [bad], 1)
        assert outcome == "EXPIRED"


def test_13_short_inverted_bar_is_skipped():
    outcome, _ = _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                       [95.0], [110.0], 1)   # high < low
    assert outcome == "EXPIRED"


def test_14_genuine_short_target_still_wins():
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 [S_TARGET_HIT[0]], [S_TARGET_HIT[1]], 5) == ("WIN", 1)


def test_15_genuine_short_stop_still_loses():
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 [S_STOP_HIT[0]], [S_STOP_HIT[1]], 5) == ("LOSS", 1)


def test_16_short_same_bar_straddle_unchanged():
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 [S_STRADDLE[0]], [S_STRADDLE[1]], 5) == ("AMBIGUOUS", 1)


def test_17_clean_short_series_is_compatible():
    h, l = _hl([S_NO_TOUCH] * 4)
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 h, l, 4) == ("EXPIRED", None)
    h, l = _hl(list(MALFORMED_SPECS) + [S_TARGET_HIT])
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 h, l, 10) == ("WIN", 6)


def test_17b_long_delegation_is_bit_identical():
    """The long side must be untouched by the short-side change."""
    for specs in ([GENUINE_TARGET], [GENUINE_STOP], [STRADDLE],
                  [VALID_NO_TOUCH], list(MALFORMED_SPECS)):
        h, l = _hl(specs)
        assert (_classify_directional(100.0, 90.0, 120.0, "long", h, l, 10)
                == classify(100.0, 90.0, 120.0, h, l, 10))


# ── 18-25. Isolation and compatibility ───────────────────────────────────────

async def test_18_19_temp_ledger_is_the_only_write_target(tmp_path, guarded_open):
    """guarded_open asserts on teardown that neither real ledger was opened for
    writing; hashes prove content, the spy proves intent."""
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(r) for r in NEGATIVE_STOP_ROWS])
    svc = StubService({r["symbol"]: _bars_from(r["date"], MALFORMED_SPECS)
                       for r in NEGATIVE_STOP_ROWS})
    await evaluate_open_entries(svc, path=str(led))
    produced = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert produced == {led}


async def test_20_historical_rows_remain_byte_identical(tmp_path, guarded_open):
    before_hash = _sha256(LIVE_LEDGER)
    before = [r for r in _read_all()
              if isinstance(r.get("stop"), (int, float)) and r["stop"] <= 0]
    led = tmp_path / "temp_ledger.jsonl"
    _write_ledger(led, [dict(r) for r in NEGATIVE_STOP_ROWS])
    svc = StubService({r["symbol"]: _bars_from(r["date"], MALFORMED_SPECS)
                       for r in NEGATIVE_STOP_ROWS})
    await evaluate_open_entries(svc, path=str(led))
    after = [r for r in _read_all()
             if isinstance(r.get("stop"), (int, float)) and r["stop"] <= 0]
    assert after == before and len(after) == 5
    assert _sha256(LIVE_LEDGER) == before_hash


def test_21_no_network_access_occurs(monkeypatch):
    """The stub service is the only data source; nothing here opens a socket."""
    import socket

    def deny(*a, **kw):
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", deny)
    assert _classify_directional(S_ENTRY, S_STOP, S_TARGET, "short",
                                 [S_TARGET_HIT[0]], [S_TARGET_HIT[1]], 5) == ("WIN", 1)


def test_22_no_production_evaluation_or_backtest_runs():
    """Static self-check over this module's AST: every awaited
    evaluate_open_entries() call must bind an explicit `path`, so no test in
    this file can silently evaluate the REAL ledger.

    AST, not text matching. A line scan reads its own source and cannot tell a
    real call from a mention of one inside a string literal, a comment or the
    checker itself - it flags its own predicate and fails."""
    import ast
    import inspect

    module = inspect.getmodule(test_22_no_production_evaluation_or_backtest_runs)
    tree = ast.parse(inspect.getsource(module))

    def _callee(call: ast.Call):
        func = call.func
        if isinstance(func, ast.Name):
            return func.id
        return getattr(func, "attr", None)

    awaited = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if _callee(call) != "evaluate_open_entries":
            continue
        awaited += 1
        assert "path" in {kw.arg for kw in call.keywords}, (
            f"line {node.lineno}: awaited evaluate_open_entries() without an "
            f"explicit path= - it would target the LIVE ledger")
    assert awaited > 0, "no awaited evaluation calls found - the guard is vacuous"

    called = {_callee(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "compute_symbol_backtest" not in called, (
        "the production backtest entry point must never run from this module")

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("backtest_v33" in m for m in imported), (
        "the out-of-scope backtest CLI must never be imported here")


def test_23_classify_caller_contract_is_unchanged():
    """classify() must still return a 2-tuple; all three call sites unpack two."""
    result = classify(100.0, 90.0, 120.0, [121.0], [118.0], 5)
    assert isinstance(result, tuple) and len(result) == 2
    outcome, bars = result
    assert outcome in ("WIN", "LOSS", "AMBIGUOUS", "EXPIRED")
    assert bars is None or isinstance(bars, int)


def test_24_no_ledger_payload_field_was_added_or_removed():
    """aggregate()/timing_calibration() shapes are untouched by this package."""
    from api.setup_ledger import aggregate, timing_calibration
    agg = aggregate()
    for field in ("status", "total_logged", "total_resolved", "by_grade",
                  "date_range", "last_evaluated", "methodology", "disclaimer"):
        assert field in agg
    for stat in agg["by_grade"].values():
        for field in ("logged", "wins", "losses", "expired", "pending", "decided",
                      "win_rate_pct", "avg_reward_risk", "expectancy_r", "rate_reliable"):
            assert field in stat
    assert "speed_factor" in timing_calibration()


def test_25_clean_series_baseline_is_identical():
    """On clean data usable == fetched, so every gate behaves as before."""
    clean = [VALID_NO_TOUCH] * 10
    h, l = _hl(clean)
    assert usable_bar_count(h, l, 10) == len(h) == 10
    assert classify(100.0, 90.0, 120.0, h, l, 10) == ("EXPIRED", None)
    h, l = _hl([VALID_NO_TOUCH] * 3 + [GENUINE_TARGET])
    assert classify(100.0, 90.0, 120.0, h, l, 10) == ("WIN", 4)
    assert usable_bar_count(h, l, 10) == 4
