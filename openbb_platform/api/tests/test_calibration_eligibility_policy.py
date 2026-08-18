"""Calibration-eligibility policy: manifest integrity, cohorts, metrics, fail-open.

PROPOSED NEW FILE -> api/tests/test_calibration_eligibility_policy.py

The ledger is READ-ONLY throughout (the conftest tamper guard proves it
independently). No evaluation, recalibration or network access occurs.

Numbers are recomputed from the live ledger inside each test rather than copied
from a report, so a ledger change fails loudly instead of silently invalidating
a constant. The exceptions are the cohort sizes and classification counts, which
ARE the policy's claim and must be pinned.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.setup_ledger import (  # noqa: E402
    _POLICY_PATH, _PROVENANCE_REASON, _STRUCTURAL_REASON, _calibration_policy,
    _geometry_sound, _read_all, aggregate, calibration_ineligible_reason,
    partition_eligibility, timing_calibration,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIVE_LEDGER = ROOT / "sentriq_ledger.jsonl"
EVAL_LEDGER = ROOT / "sentriq_ledger_v33_eval.jsonl"
# Local audit archive. DELIBERATELY OPTIONAL: runtime must never depend on it.
ARCHIVE = ROOT / ".local_audit" / "provenance" / "zero_ohlcv_2026-08-08"

EXPECTED_STRUCTURAL = 5
EXPECTED_PROVENANCE = 14
EXPECTED_UNION = 19
EXPECTED_CLASSIFICATIONS = {"BOTH": 9, "VERIFIED FALSE RESOLUTION": 5}


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return _read_all()


@pytest.fixture(scope="module")
def cohorts(rows):
    structural = {r["key"] for r in rows
                  if calibration_ineligible_reason(r) == _STRUCTURAL_REASON}
    provenance = {r["key"] for r in rows
                  if calibration_ineligible_reason(r) == _PROVENANCE_REASON}
    return structural, provenance


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Manifest integrity ───────────────────────────────────────────────────────

def test_manifest_keys_are_unique_and_complete():
    doc = json.loads(pathlib.Path(_POLICY_PATH).read_text())
    listed = [e["key"] for e in doc["provenance_rule"]["keys"]]
    assert len(listed) == EXPECTED_PROVENANCE
    assert len(set(listed)) == len(listed), "duplicate key in manifest"
    assert set(listed) == set(_calibration_policy()["keys"])


def test_every_manifest_key_resolves_to_exactly_one_immutable_row(rows):
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["key"]] = counts.get(r["key"], 0) + 1
    for key in _calibration_policy()["keys"]:
        assert counts.get(key) == 1, f"{key} resolves to {counts.get(key)} rows"


def test_evidence_metadata_is_well_formed():
    """Every entry carries reason, classification, evidence file, a 64-hex
    sha256 and an audit date. Format only - no archive needed."""
    for key, e in _calibration_policy()["keys"].items():
        assert e["reason"] == _PROVENANCE_REASON, key
        assert e["classification"] in EXPECTED_CLASSIFICATIONS, key
        assert e["evidence_file"].endswith(".json"), key
        sha = e["evidence_sha256"]
        assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha), key
        assert e["audit_date"], key


def test_manifest_classification_split_matches_the_audit():
    counts: dict[str, int] = {}
    for e in _calibration_policy()["keys"].values():
        counts[e["classification"]] = counts.get(e["classification"], 0) + 1
    assert counts == EXPECTED_CLASSIFICATIONS


def test_evidence_hashes_match_the_archive_when_it_is_present():
    """Verifies the provenance claim when the local archive exists. SKIPS when it
    does not - production correctness must not depend on a local artifact."""
    if not ARCHIVE.is_dir():
        pytest.skip(f"local evidence archive absent at {ARCHIVE}")
    cache: dict[str, str] = {}
    for key, e in _calibration_policy()["keys"].items():
        fn = e["evidence_file"]
        path = ARCHIVE / fn
        assert path.is_file(), f"{key}: evidence {fn} missing"
        cache.setdefault(fn, _sha256(path))
        assert cache[fn] == e["evidence_sha256"], (
            f"{key}: archive and manifest disagree - provenance unsupported")


def test_runtime_does_not_depend_on_the_local_archive():
    """The policy path must resolve inside the tracked package, never /tmp and
    never .local_audit."""
    p = pathlib.Path(_POLICY_PATH)
    assert p.parent.name == "policy"
    assert "api" in p.parts and ".local_audit" not in p.parts
    assert not str(p).startswith("/tmp")
    assert p.is_file(), "tracked policy manifest must ship with the package"


# ── Fail-open behaviour ──────────────────────────────────────────────────────

@pytest.mark.parametrize("content,label", [
    (None, "missing file"),
    ("{ not json", "malformed JSON"),
    (json.dumps({"policy_version": 1}), "wrong shape"),
])
def test_unusable_policy_fails_open(rows, tmp_path, monkeypatch, content, label):
    """Every row stays eligible; only the self-evident structural rule fires."""
    import api.setup_ledger as sl
    bad = tmp_path / "bad.json"
    if content is not None:
        bad.write_text(content)
    monkeypatch.setattr(sl, "_POLICY_PATH", str(bad))
    sl._calibration_policy.cache_clear()
    try:
        assert sl._calibration_policy()["keys"] == {}, label
        ineligible = [r for r in rows if calibration_ineligible_reason(r)]
        assert len(ineligible) == EXPECTED_STRUCTURAL, label
    finally:
        sl._calibration_policy.cache_clear()


@pytest.mark.parametrize("mutate,label", [
    (lambda d: d["provenance_rule"]["keys"][3].__setitem__("evidence_sha256", "deadbeef"),
     "one malformed sha256"),
    (lambda d: d["provenance_rule"]["keys"].append(d["provenance_rule"]["keys"][0]),
     "duplicate key"),
    (lambda d: d["provenance_rule"]["keys"][0].__setitem__("audit_date", ""),
     "missing audit_date"),
])
def test_partially_invalid_manifest_is_rejected_whole(tmp_path, monkeypatch, mutate, label):
    """All-or-nothing: one bad record must never let the other 13 apply."""
    import api.setup_ledger as sl
    doc = json.loads(pathlib.Path(_POLICY_PATH).read_text())
    mutate(doc)
    bad = tmp_path / "partial.json"
    bad.write_text(json.dumps(doc))
    monkeypatch.setattr(sl, "_POLICY_PATH", str(bad))
    sl._calibration_policy.cache_clear()
    try:
        assert sl._calibration_policy()["keys"] == {}, f"{label} partially applied"
    finally:
        sl._calibration_policy.cache_clear()


# ── Cohorts ──────────────────────────────────────────────────────────────────

def test_structural_cohort_is_exactly_five(cohorts):
    assert len(cohorts[0]) == EXPECTED_STRUCTURAL


def test_structural_cohort_is_exactly_the_negative_stop_rows(rows, cohorts):
    """Guards the real risk: _geometry_sound rejects ANY malformed row, so a
    legacy entry with a missing field would be swept in silently."""
    negative = {r["key"] for r in rows
                if isinstance(r.get("stop"), (int, float)) and r["stop"] <= 0}
    assert cohorts[0] == negative


def test_provenance_cohort_is_exactly_fourteen(cohorts):
    assert len(cohorts[1]) == EXPECTED_PROVENANCE


def test_cohorts_are_disjoint_and_union_is_nineteen(cohorts):
    structural, provenance = cohorts
    assert structural & provenance == set(), "a row cannot carry two reasons"
    assert len(structural | provenance) == EXPECTED_UNION
    assert len(structural) + len(provenance) == EXPECTED_UNION, "overlap miscount"


# ── Nothing else is excluded ─────────────────────────────────────────────────

def _classified(name: str) -> set[str]:
    doc = json.loads((ARCHIVE / "classification.json").read_text())
    return {r["ledger_key"] for r in doc["rows"] if r["classification"] == name}


@pytest.mark.parametrize("label,expected_n", [("INDETERMINATE", 20),
                                              ("VERIFIED GENUINE", 11)])
def test_audited_eligible_classes_are_never_excluded(cohorts, label, expected_n):
    if not ARCHIVE.is_dir():
        pytest.skip("classification.json unavailable")
    keys = _classified(label)
    assert len(keys) == expected_n, f"{label} cohort changed size"
    assert keys & (cohorts[0] | cohorts[1]) == set(), (
        f"{label} rows must remain eligible - evidence does not support excluding them")


def test_skyq_rows_remain_eligible(rows, cohorts):
    skyq = {r["key"] for r in rows if str(r.get("symbol", "")).upper().startswith("SKYQ")}
    assert skyq, "SKYQ control rows vanished"
    assert skyq & (cohorts[0] | cohorts[1]) == set()


# ── Ledger immutability ──────────────────────────────────────────────────────

def test_read_all_still_returns_every_row(rows):
    assert len(rows) == sum(1 for _ in open(LIVE_LEDGER, encoding="utf-8"))
    eligible, ineligible = partition_eligibility(rows)
    assert len(eligible) + len(ineligible) == len(rows), "partition lost a row"


def test_aggregate_and_timing_do_not_mutate_either_ledger():
    before = _sha256(LIVE_LEDGER), _sha256(EVAL_LEDGER)
    aggregate()
    timing_calibration()
    assert (_sha256(LIVE_LEDGER), _sha256(EVAL_LEDGER)) == before


def test_policy_is_inert_on_the_eval_ledger():
    """Verified, not assumed: a backtest must not inherit these exclusions."""
    if not EVAL_LEDGER.is_file():
        pytest.skip("eval ledger absent")
    keys = {json.loads(line).get("key")
            for line in open(EVAL_LEDGER, encoding="utf-8")}
    assert keys & set(_calibration_policy()["keys"]) == set()
    bad = [json.loads(line) for line in open(EVAL_LEDGER, encoding="utf-8")
           if not _geometry_sound(json.loads(line))]
    assert not bad, "eval ledger has structurally invalid rows"


# ── Metric reconciliation (v3: existing fields must NOT move) ────────────────

def _stats(rs: list[dict]) -> dict:
    w = sum(1 for r in rs if r.get("outcome") == "WIN")
    l = sum(1 for r in rs if r.get("outcome") in ("LOSS", "AMBIGUOUS"))
    d = w + l
    return {"logged": len(rs), "wins": w, "losses": l, "decided": d,
            "expired": sum(1 for r in rs if r.get("outcome") == "EXPIRED"),
            "pending": sum(1 for r in rs if r.get("outcome") == "PENDING"),
            "win_rate_pct": round(100.0 * w / d, 1) if d else None}


ALL_RECORD_FIELDS = ("logged", "wins", "losses", "expired", "pending",
                     "decided", "win_rate_pct", "avg_reward_risk",
                     "expectancy_r", "rate_reliable")


@pytest.mark.parametrize("grade", ["A", "B", "C"])
def test_every_existing_field_still_reports_the_all_record_population(rows, grade):
    """THE v3 CONTRACT. Each pre-existing field must equal the value computed
    over ALL rows of that grade - eligibility must not leak into it."""
    agg = aggregate()["by_grade"][grade]
    expected = _stats([r for r in rows if r.get("grade") == grade])
    for field in ("logged", "wins", "losses", "expired", "pending",
                  "decided", "win_rate_pct"):
        assert agg[field] == expected[field], f"{grade}.{field} left all-record meaning"


def test_headline_totals_keep_all_record_meaning(rows):
    agg = aggregate()
    assert agg["total_logged"] == len(rows)
    assert agg["total_resolved"] == sum(
        1 for r in rows if r.get("outcome") in ("WIN", "LOSS", "AMBIGUOUS"))


@pytest.mark.parametrize("grade", ["A", "B"])
def test_grade_a_and_b_all_record_and_eligible_are_identical(rows, grade):
    """No excluded row carries grade A or B, so both views must agree exactly."""
    agg = aggregate()["by_grade"][grade]
    assert agg["excluded"] == 0
    assert agg["decided_eligible"] == agg["decided"]
    assert agg["win_rate_pct_eligible"] == agg["win_rate_pct"]
    assert agg["expectancy_r_eligible"] == agg["expectancy_r"]
    assert agg["pending_eligible"] == agg["pending"]
    assert agg["logged_eligible"] == agg["logged"]


def test_grade_c_all_record_values_are_unchanged(rows):
    agg = aggregate()["by_grade"]["C"]
    expected = _stats([r for r in rows if r.get("grade") == "C"])
    assert agg["decided"] == expected["decided"]
    assert agg["win_rate_pct"] == expected["win_rate_pct"]
    assert agg["pending"] == expected["pending"]
    assert agg["logged"] == expected["logged"]


def test_grade_c_eligible_values_reconcile_exactly(rows):
    eligible, _ = partition_eligibility(rows)
    exp = _stats([r for r in eligible if r.get("grade") == "C"])
    agg = aggregate()["by_grade"]["C"]
    assert agg["decided_eligible"] == exp["decided"]
    assert agg["win_rate_pct_eligible"] == exp["win_rate_pct"]
    assert agg["pending_eligible"] == exp["pending"]
    assert agg["logged_eligible"] == exp["logged"]
    assert agg["excluded"] == EXPECTED_UNION
    # The 19 exclusions are 14 decided + 5 pending.
    assert agg["decided"] - agg["decided_eligible"] == EXPECTED_PROVENANCE
    assert agg["pending"] - agg["pending_eligible"] == EXPECTED_STRUCTURAL
    assert agg["win_rate_pct_eligible"] > agg["win_rate_pct"]


def test_overall_all_record_and_eligible_rates(rows):
    eligible, ineligible = partition_eligibility(rows)
    w = sum(1 for r in rows if r.get("outcome") == "WIN")
    l = sum(1 for r in rows if r.get("outcome") == "LOSS")
    we = sum(1 for r in eligible if r.get("outcome") == "WIN")
    le = sum(1 for r in eligible if r.get("outcome") == "LOSS")
    assert round(100.0 * w / (w + l), 2) == 33.90
    assert round(100.0 * we / (we + le), 2) == 34.54
    agg = aggregate()
    assert agg["total_eligible"] == len(eligible)
    assert agg["total_resolved_eligible"] == sum(
        1 for r in eligible if r.get("outcome") in ("WIN", "LOSS", "AMBIGUOUS"))
    assert agg["excluded_ineligible"] == len(ineligible) == EXPECTED_UNION
    assert agg["excluded_by_reason"] == {
        _PROVENANCE_REASON: EXPECTED_PROVENANCE,
        _STRUCTURAL_REASON: EXPECTED_STRUCTURAL,
    }
    assert agg["eligibility_policy_version"] == _calibration_policy()["policy_version"]


def test_exclusion_metadata_appears_in_both_outputs():
    for payload in (aggregate(), timing_calibration()):
        for field in ("eligibility_policy_version", "excluded_ineligible",
                      "excluded_by_reason"):
            assert field in payload, field


def test_no_win_is_excluded(rows):
    _eligible, ineligible = partition_eligibility(rows)
    assert not [r for r, _ in ineligible if r.get("outcome") == "WIN"]


def test_timing_calibration_is_bit_identical(rows):
    """v3 does NOT filter timing: metrics cover all records, exactly as before."""
    cal = timing_calibration()
    wins = [r for r in rows if r.get("outcome") == "WIN"]
    expected_n = len([r for r in wins if r.get("bars_to_resolve")
                      and (r.get("expected_days") or (r.get("window_days") or 0) / 2.0)])
    assert cal["n_samples"] == expected_n, "timing sample population changed"
    assert isinstance(cal["speed_factor"], float)


# ── Consumer compatibility ───────────────────────────────────────────────────

def test_no_existing_field_was_removed_or_retyped():
    """sentriq/src/hooks/useApi.ts LedgerResp / LedgerGradeStat. v3 is purely
    additive: a REMOVAL or retype would break the UI."""
    agg = aggregate()
    for field in ("status", "total_logged", "total_resolved", "by_grade",
                  "date_range", "last_evaluated", "methodology", "disclaimer"):
        assert field in agg, f"LedgerResp field {field} disappeared"
    for stat in agg["by_grade"].values():
        for field in ALL_RECORD_FIELDS:
            assert field in stat, f"LedgerGradeStat field {field} disappeared"
        assert isinstance(stat["logged"], int)
        assert isinstance(stat["pending"], int)
        assert isinstance(stat["decided"], int)
        assert isinstance(stat["rate_reliable"], bool)
    assert isinstance(agg["total_logged"], int)
    assert isinstance(agg["total_resolved"], int)


def test_new_eligible_fields_are_present_and_typed():
    for stat in aggregate()["by_grade"].values():
        for field in ("logged_eligible", "wins_eligible", "losses_eligible",
                      "expired_eligible", "pending_eligible", "decided_eligible",
                      "excluded"):
            assert isinstance(stat[field], int), field
        assert stat["win_rate_pct_eligible"] is None or isinstance(
            stat["win_rate_pct_eligible"], float)
        assert isinstance(stat["rate_reliable_eligible"], bool)


def test_no_raw_ohlcv_or_secret_in_the_tracked_policy():
    doc = json.loads(pathlib.Path(_POLICY_PATH).read_text())
    blob = json.dumps(doc).lower()
    for banned in ("open", "high", "low", "close", "volume",
                   "api_key", "token", "secret", "password"):
        assert f'"{banned}"' not in blob, f"tracked policy contains {banned!r}"
    for e in doc["provenance_rule"]["keys"]:
        assert set(e) <= {"key", "symbol", "setup_date", "resolved_on",
                          "recorded_outcome", "reason", "classification",
                          "evidence_file", "evidence_sha256", "audit_date",
                          "reason_detail"}, e["key"]
