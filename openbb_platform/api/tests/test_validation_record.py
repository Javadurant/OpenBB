"""validation-record-v1: schema, look-ahead guards, append-only behaviour, size.

Entirely offline. Every write goes to a pytest tmp_path; no test here touches a
production ledger, opens a socket, or activates recording.

The point of this module is not that the dataclass holds the right keys. It is
that the two ways evidence gets corrupted are impossible: an outcome leaking
into a scan record, and a record silently reading as "rule satisfied" when the
rule was simply never observed.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.validation_record import (  # noqa: E402
    OPTIONAL_FIELDS,
    SCHEMA_VERSION,
    ValidationRecord,
    append_validation_record,
    compute_missing,
)

_SCAN_TS = "2026-08-20T16:14:35+00:00"


def _rec(**over) -> ValidationRecord:
    base = dict(
        schema_version=SCHEMA_VERSION, rule_set_version="setup_scanner-v3.9-gradeA",
        record_kind="scan", key="2026-08-20:STOR-B.ST:B",
        symbol="STOR-B.ST", resolved_instrument="STOR-B.ST", region="Swedish",
        asset_class="equity", sector="Industrials", is_proxy=False,
        data_provider="yfinance", scan_timestamp_utc=_SCAN_TS,
        market_as_of="2026-08-20", data_freshness="cached", bars_available=1003,
        grade="B", score=82.4, score_denominator=125.0,
        setup_classification="Pullback Buy Setup",
        entry=10.78, stop=10.27, target=11.8, reward_risk=2.0,
        atr_14=0.34, extended_atr=0.62, rsi_14=58.7, weekly_rsi=66.8, monthly_rsi=49.7,
        daily_trend="up", weekly_trend="up", monthly_trend="up",
        timeframes_aligned=3, ma100_state=True,
        conflict_ids=["macd_hist_falling_in_uptrend"],
        conflict_severity_provisional={"macd_hist_falling_in_uptrend": "SCORE_PENALTY"},
        conflict_evidence_source={"macd_hist_falling_in_uptrend": "_comp/macd"},
        integrity_label="VALID", integrity_hard_blocks=[],
        market_regime_index="^OMX", market_regime_risk_on=True,
        missing_fields=[], data_completeness_pct=100.0,
    )
    base.update(over)
    return ValidationRecord(**base)


# 1-2 ── schema versioning ───────────────────────────────────────────────────
def test_valid_schema_version_is_accepted(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec())
    assert json.loads(p.read_text())["schema_version"] == SCHEMA_VERSION


def test_invalid_schema_version_is_rejected(tmp_path):
    p = tmp_path / "v.jsonl"
    with pytest.raises(ValueError, match="schema mismatch"):
        append_validation_record(str(p), _rec(schema_version="validation-record-v0"))
    assert not p.exists(), "a rejected record must not create the file"


# 3 ── deterministic serialisation ──────────────────────────────────────────
def test_serialisation_is_deterministic(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    append_validation_record(str(a), _rec())
    append_validation_record(str(b), _rec())
    assert a.read_bytes() == b.read_bytes()
    keys = list(json.loads(a.read_text()).keys())
    assert keys == sorted(keys), "keys must be sorted so diffs are stable"


# 4-5 ── field validation ───────────────────────────────────────────────────
def test_required_fields_are_mandatory():
    with pytest.raises(TypeError):
        ValidationRecord(schema_version=SCHEMA_VERSION)  # type: ignore[call-arg]


def test_optional_fields_default_and_record_is_frozen():
    r = _rec()
    assert r.outcome is None and r.mae_r is None and r.mfe_r is None
    with pytest.raises(FrozenInstanceError):
        r.grade = "A"  # type: ignore[misc]


# 6-7 ── missing evidence stays missing ─────────────────────────────────────
def test_missing_fields_are_named_not_defaulted():
    raw = {f: None for f in OPTIONAL_FIELDS}
    raw["rsi_14"] = 58.7
    missing, pct = compute_missing(raw)
    assert "extended_atr" in missing and "rsi_14" not in missing
    assert pct == pytest.approx(100.0 / len(OPTIONAL_FIELDS), abs=0.1)


def test_unobserved_rule_never_reads_as_satisfied(tmp_path):
    """ma100_state=None means 'not observed'. It must never serialise as False."""
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec(ma100_state=None, missing_fields=["ma100_state"]))
    row = json.loads(p.read_text())
    assert row["ma100_state"] is None, "not-observed must not collapse to False"
    assert row["ma100_state"] is not False
    assert "ma100_state" in row["missing_fields"]


# 8-10 ── look-ahead guards ─────────────────────────────────────────────────
def test_scan_record_rejects_outcome_data(tmp_path):
    p = tmp_path / "v.jsonl"
    with pytest.raises(ValueError, match="look-ahead guard"):
        append_validation_record(str(p), _rec(record_kind="scan", outcome="WIN"))
    assert not p.exists()


def test_outcome_record_requires_timestamp(tmp_path):
    p = tmp_path / "v.jsonl"
    with pytest.raises(ValueError, match="outcome_recorded_at_utc"):
        append_validation_record(str(p), _rec(record_kind="outcome", outcome="WIN",
                                              outcome_recorded_at_utc=None))


def test_outcome_before_scan_is_rejected_as_look_ahead(tmp_path):
    p = tmp_path / "v.jsonl"
    with pytest.raises(ValueError, match="precedes scan_timestamp_utc"):
        append_validation_record(str(p), _rec(
            record_kind="outcome", outcome="WIN",
            outcome_recorded_at_utc="2026-08-19T00:00:00+00:00"))
    assert not p.exists()


def test_outcome_after_scan_is_accepted(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec(
        record_kind="outcome", outcome="WIN", bars_to_resolve=6,
        outcome_recorded_at_utc="2026-08-28T16:00:00+00:00"))
    assert json.loads(p.read_text())["outcome"] == "WIN"


# 11-13 ── provenance preserved verbatim ────────────────────────────────────
def test_conflict_identifiers_and_sources_preserved(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec())
    row = json.loads(p.read_text())
    assert row["conflict_ids"] == ["macd_hist_falling_in_uptrend"]
    assert row["conflict_severity_provisional"]["macd_hist_falling_in_uptrend"] == "SCORE_PENALTY"
    assert row["conflict_evidence_source"]["macd_hist_falling_in_uptrend"] == "_comp/macd"


def test_provenance_and_timestamps_preserved(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec())
    row = json.loads(p.read_text())
    assert row["data_provider"] == "yfinance"
    assert row["scan_timestamp_utc"] == _SCAN_TS
    assert row["market_as_of"] == "2026-08-20"
    assert row["data_freshness"] == "cached"
    assert row["rule_set_version"] == "setup_scanner-v3.9-gradeA"


@pytest.mark.parametrize("proxy", [True, False])
def test_direct_proxy_status_preserved(tmp_path, proxy):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec(is_proxy=proxy))
    assert json.loads(p.read_text())["is_proxy"] is proxy


# 14-17 ── append-only ──────────────────────────────────────────────────────
def test_append_adds_lines_without_touching_existing_bytes(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec(symbol="AAA.ST"))
    first = p.read_bytes()
    append_validation_record(str(p), _rec(symbol="BBB.ST"))
    after = p.read_bytes()
    assert after.startswith(first), "existing bytes must be untouched"
    assert len(after.splitlines()) == 2


def test_fsync_is_exercised(monkeypatch, tmp_path):
    calls = []
    import api.validation_record as vr
    monkeypatch.setattr(vr.os, "fsync", lambda fd: calls.append(fd))
    append_validation_record(str(tmp_path / "v.jsonl"), _rec())
    assert calls, "durability: fsync must be called on every append"


def test_module_has_no_read_modify_write_path():
    src = pathlib.Path(__file__).resolve().parents[1].joinpath("validation_record.py").read_text()
    for forbidden in ('open(path, "w"', ".truncate(", ".seek(", "os.replace", "shutil.move"):
        assert forbidden not in src, f"append-only violated by {forbidden!r}"


def test_corrupt_record_fails_closed(tmp_path):
    p = tmp_path / "v.jsonl"
    with pytest.raises(Exception):
        append_validation_record(str(p), _rec(conflict_ids={1, 2}))  # set is not JSON
    assert not p.exists() or p.read_text() == "", "a failed write must not persist a partial row"


# 19-21 ── secrets and size ─────────────────────────────────────────────────
def test_no_secret_bearing_fields():
    import re
    body = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "validation_record.py").read_text().split("class ValidationRecord")[1].split(
        "def compute_missing")[0]
    fields = re.findall(r"^\s{4}(\w+)\s*:", body, re.M)
    assert not [f for f in fields
                if re.search(r"api_key|token|password|secret|prompt|authorization", f, re.I)]


def test_measured_record_size_is_bounded(tmp_path):
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec())
    size = len(p.read_bytes())
    assert 600 < size < 2000, f"record size drifted to {size} bytes; storage estimate assumes ~1.2 KB"


def test_narrow_scope_annual_storage_within_reviewed_estimate(tmp_path):
    """Explicit assumptions: 20 records/scan, 2 regions, 4 scans/day, 365 days."""
    p = tmp_path / "v.jsonl"
    append_validation_record(str(p), _rec())
    per_record = len(p.read_bytes())
    annual_mb = per_record * 20 * 2 * 4 * 365 / 1024 / 1024
    assert annual_mb < 100, f"narrow-scope estimate {annual_mb:.1f} MB/yr exceeds headroom"


# 22-25 ── inertness ────────────────────────────────────────────────────────
def test_schema_is_not_referenced_by_scanner_or_routes():
    api_dir = pathlib.Path(__file__).resolve().parents[1]
    for name in ("setup_scanner.py", "phase2_router.py", "broad_scan.py", "main.py"):
        src = api_dir.joinpath(name).read_text()
        assert "validation_record" not in src, f"{name} must not import the inert schema"


def test_import_creates_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    subprocess.run([sys.executable, "-c",
                    "import sys; sys.path.insert(0, %r); import api.validation_record"
                    % str(pathlib.Path(__file__).resolve().parents[2])],
                   check=True, capture_output=True)
    assert set(tmp_path.iterdir()) == before, "importing the module must write nothing"


def test_no_production_ledger_access(tmp_path):
    root = pathlib.Path(__file__).resolve().parents[2]
    snap = {p: p.stat().st_size for p in root.glob("sentriq_ledger*.jsonl")}
    assert snap, "ledger fixtures must exist for this guard to mean anything"
    append_validation_record(str(tmp_path / "v.jsonl"), _rec())
    assert {p: p.stat().st_size for p in root.glob("sentriq_ledger*.jsonl")} == snap
    src = root.joinpath("api/validation_record.py").read_text()
    assert "sentriq_ledger" not in src


def test_no_writer_or_recording_activation():
    """The module must expose no scheduler, no default path, no auto-enable."""
    src = pathlib.Path(__file__).resolve().parents[1].joinpath("validation_record.py").read_text()
    for forbidden in ("DEFAULT_PATH", "atexit", "threading", "schedule", "APScheduler",
                      "os.environ.setdefault"):
        assert forbidden not in src, f"recording must not self-activate via {forbidden!r}"
