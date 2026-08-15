"""Priority 4: explicit ledger `path=` redirection + loud live-write refusal.

TEST-ONLY. Verifies that setup_ledger can target an approved PARALLEL ledger
explicitly, and that an explicit WRITE path resolving to the live ledger raises
loudly instead of silently corrupting production data.

SAFETY DESIGN — why no test ever names the real live ledger in a write call:
  Every write-refusal test monkeypatches BOTH `_LEDGER_PATH` and
  `LIVE_LEDGER_PATH` onto temp files first. If the refusal logic were broken,
  a test that passed the REAL live path would append to the production trust
  ledger - the exact catastrophe this guard exists to prevent. Detecting that
  after the fact (via the conftest checksum guard) is not good enough, so the
  real ledger is never a write argument here. Reads are likewise temp-only.

All records below are synthetic plumbing fixtures in throwaway temp files. They
assert WHICH file was touched, never a trading conclusion, and no test reads or
writes the real live or eval ledger.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api import setup_ledger as sl  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fake_live(tmp_path, monkeypatch):
    """Redirect the module's notion of "live" onto a temp file.

    Both constants are patched together so _resolve_ledger's identity check
    (`resolved == realpath(LIVE_LEDGER_PATH)`) stays self-consistent."""
    live = tmp_path / "fake_live_ledger.jsonl"
    live.write_text("", encoding="utf-8")
    monkeypatch.setattr(sl, "_LEDGER_PATH", str(live))
    monkeypatch.setattr(sl, "LIVE_LEDGER_PATH", str(live))
    return live


@pytest.fixture
def parallel(tmp_path):
    """An approved parallel ledger - a distinct file from `fake_live`."""
    return tmp_path / "parallel_eval_ledger.jsonl"


def _setup(symbol="TEST.ST", grade="A", as_of="2026-01-05"):
    """Minimal SetupResult-shaped dict accepted by log_setup."""
    return {"symbol": symbol, "grade": grade, "entry": 100.0, "stop": 95.0,
            "target": 110.0, "reward_risk": 2.0, "as_of": as_of,
            "time_window_days": "10-20 trading days", "score": 70.0,
            "region": "Swedish", "asset_class": "equity", "source": "test"}


def _record(outcome="WIN", grade="A", bars=6, expected=8, symbol="TEST.ST",
            date="2026-01-05"):
    """A resolved ledger row, as _read_all would parse it."""
    return {"key": sl.make_key(date, symbol, grade), "date": date,
            "symbol": symbol, "grade": grade, "outcome": outcome,
            "entry": 100.0, "stop": 95.0, "target": 110.0, "reward_risk": 2.0,
            "window_days": 16, "expected_days": expected,
            "bars_to_resolve": bars}


def _write_rows(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# path=None preserves live behaviour
# ─────────────────────────────────────────────────────────────────────────────
def test_log_setup_path_none_targets_the_live_ledger(fake_live, parallel):
    assert sl.log_setup(_setup()) is True
    rows = [json.loads(x) for x in fake_live.read_text().splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TEST.ST"
    assert rows[0]["outcome"] == "PENDING"
    assert not parallel.exists()          # nothing leaked to the parallel file


def test_log_setup_path_none_still_idempotent(fake_live):
    assert sl.log_setup(_setup()) is True
    assert sl.log_setup(_setup()) is False        # duplicate key
    assert len(fake_live.read_text().splitlines()) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Loud refusal on explicit live-ledger WRITES
# ─────────────────────────────────────────────────────────────────────────────
def test_log_setup_explicit_live_path_raises_loudly(fake_live):
    before = fake_live.read_text()
    with pytest.raises(ValueError, match="refusing to write"):
        sl.log_setup(_setup(), path=str(fake_live))
    assert fake_live.read_text() == before        # refusal happened BEFORE any write


def test_log_setup_refusal_is_not_swallowed_into_false(fake_live):
    """The historical contract says log_setup never raises on DATA problems.
    A misdirected TARGET is different and must escape the try/except."""
    with pytest.raises(ValueError):
        sl.log_setup(_setup(), path=str(fake_live))
    # ...while a genuine data problem still degrades to False, unchanged.
    assert sl.log_setup({"symbol": None, "grade": "A"}) is False


def test_log_setup_refuses_live_path_via_symlink_and_dotdot(fake_live, tmp_path):
    """realpath() normalisation: an alias for the live ledger is still live."""
    indirect = tmp_path / "sub" / ".." / fake_live.name
    with pytest.raises(ValueError, match="refusing to write"):
        sl.log_setup(_setup(), path=str(indirect))
    link = tmp_path / "alias_ledger.jsonl"
    link.symlink_to(fake_live)
    with pytest.raises(ValueError, match="refusing to write"):
        sl.log_setup(_setup(), path=str(link))


def test_rewrite_explicit_live_path_raises(fake_live):
    before = fake_live.read_text()
    with pytest.raises(ValueError, match="refusing to write"):
        sl._rewrite([_record()], str(fake_live))
    assert fake_live.read_text() == before


# ─────────────────────────────────────────────────────────────────────────────
# Explicit parallel WRITES are allowed and isolated
# ─────────────────────────────────────────────────────────────────────────────
def test_log_setup_parallel_path_writes_only_there(fake_live, parallel):
    assert sl.log_setup(_setup(), path=str(parallel)) is True
    rows = [json.loads(x) for x in parallel.read_text().splitlines() if x.strip()]
    assert len(rows) == 1 and rows[0]["symbol"] == "TEST.ST"
    assert fake_live.read_text() == ""            # live untouched


def test_log_setup_parallel_idempotency_is_per_file(fake_live, parallel):
    """A key present in the parallel file must not block the live file."""
    assert sl.log_setup(_setup(), path=str(parallel)) is True
    assert sl.log_setup(_setup(), path=str(parallel)) is False   # dup in parallel
    assert sl.log_setup(_setup()) is True                        # live is independent
    assert len(fake_live.read_text().splitlines()) == 1


def test_rewrite_parallel_path_writes_only_there(fake_live, parallel):
    _write_rows(parallel, [_record(outcome="PENDING")])
    sl._rewrite([_record(outcome="WIN")], str(parallel))
    rows = [json.loads(x) for x in parallel.read_text().splitlines() if x.strip()]
    assert len(rows) == 1 and rows[0]["outcome"] == "WIN"
    assert fake_live.read_text() == ""
    assert not (parallel.parent / (parallel.name + ".tmp")).exists()  # tmp cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Explicit READS
# ─────────────────────────────────────────────────────────────────────────────
def test_aggregate_reads_explicit_path(fake_live, parallel):
    _write_rows(parallel, [_record(outcome="WIN"), _record(outcome="LOSS", date="2026-01-06")])
    out = sl.aggregate(path=str(parallel))
    assert out["total_logged"] == 2
    assert out["total_resolved"] == 2
    assert out["by_grade"]["A"]["wins"] == 1
    assert out["by_grade"]["A"]["losses"] == 1
    # live (empty) must report nothing - proves the read was redirected
    assert sl.aggregate()["total_logged"] == 0


def test_timing_calibration_reads_explicit_path(fake_live, parallel):
    _write_rows(parallel, [_record(outcome="WIN", bars=6, expected=8)])
    out = sl.timing_calibration(path=str(parallel))
    assert out["n_samples"] == 1
    assert out["reliable"] is False        # below MIN_SAMPLE_FOR_RATE, stated honestly
    assert sl.timing_calibration()["n_samples"] == 0


def test_read_all_allows_explicit_live_path(fake_live):
    """Reads may target live explicitly - only writes are refused."""
    _write_rows(fake_live, [_record()])
    assert len(sl._read_all(str(fake_live))) == 1


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_open_entries: one resolved target for read AND rewrite
# ─────────────────────────────────────────────────────────────────────────────
class _Point:
    def __init__(self, ts, high, low):
        self.ts, self.high, self.low = ts, high, low


class _Series:
    source = "test"

    def __init__(self, points):
        self.points = points


class _Service:
    """Offline stand-in for the ingestion service. No network."""

    def __init__(self, points):
        self._points = points
        self.calls = 0

    async def get_series(self, symbol, asset_class, **kwargs):
        self.calls += 1
        return _Series(self._points)


def _future_points(n=10, high=115.0, low=99.0):
    base = datetime(2026, 1, 6, tzinfo=timezone.utc)
    return [_Point(base + timedelta(days=i), high, low) for i in range(n)]


async def test_evaluate_open_entries_uses_one_parallel_target(fake_live, parallel):
    _write_rows(parallel, [_record(outcome="PENDING", bars=None, expected=8)])
    _write_rows(fake_live, [_record(outcome="PENDING", bars=None, expected=8)])
    live_before = fake_live.read_text()

    res = await sl.evaluate_open_entries(_Service(_future_points()), path=str(parallel))

    assert res["resolved"] == 1
    rows = [json.loads(x) for x in parallel.read_text().splitlines() if x.strip()]
    assert rows[0]["outcome"] == "WIN"          # target 110 touched by high 115
    assert fake_live.read_text() == live_before  # live never read-modify-written


async def test_evaluate_open_entries_refuses_explicit_live_path(fake_live):
    _write_rows(fake_live, [_record(outcome="PENDING", bars=None)])
    before = fake_live.read_text()
    svc = _Service(_future_points())
    with pytest.raises(ValueError, match="refusing to write"):
        await sl.evaluate_open_entries(svc, path=str(fake_live))
    assert fake_live.read_text() == before
    assert svc.calls == 0                        # refused before any fetch


# ─────────────────────────────────────────────────────────────────────────────
# backfill_seed: fail fast, before any fetch work
# ─────────────────────────────────────────────────────────────────────────────
class _ExplodingService:
    """Any fetch attempt is a test failure - seeding must refuse first."""

    async def get_series(self, *a, **k):  # pragma: no cover - must never run
        raise AssertionError("backfill_seed fetched before validating the write path")


async def test_backfill_seed_refuses_live_path_before_fetch(fake_live):
    before = fake_live.read_text()
    with pytest.raises(ValueError, match="refusing to write"):
        await sl.backfill_seed(_ExplodingService(), [("TEST.ST", "Swedish", "equity")],
                               ["2026-01-05"], path=str(fake_live))
    assert fake_live.read_text() == before


# ─────────────────────────────────────────────────────────────────────────────
# Public identity constant
# ─────────────────────────────────────────────────────────────────────────────
def test_live_ledger_path_constant_points_at_the_real_live_ledger():
    """Unpatched, the public alias must name the production ledger so tools can
    assert their own output path differs from it."""
    assert pathlib.Path(sl.LIVE_LEDGER_PATH).name == "sentriq_ledger.jsonl"
    assert sl.LIVE_LEDGER_PATH == sl._LEDGER_PATH
