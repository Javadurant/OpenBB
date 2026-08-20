"""
validation_record.py — versioned, append-only evidence records for model validation.
====================================================================================

WHY THIS EXISTS
---------------
The trust ledger answers "did the target get hit?". It cannot answer "which
rule was responsible?", because it stores 19 fields and none of them is a
conflict identifier, a trend state, an integrity label or a regime. That gap is
why the Grade-A conflict severity question is currently unanswerable in either
direction — retrospectively OR prospectively.

This module defines the record that closes it. It is deliberately NOT wired to
anything: nothing here is called by the scanner, the router or the ledger, and
`append_validation_record` is inert unless a caller passes an explicit path.
Activation is a separate, reviewed decision.

HARD RULES
----------
* Additive only. The trust ledger is untouched; this is a parallel file.
* Append-only. No update, no rewrite, no delete path exists in this module.
* Versioned. Every row carries SCHEMA_VERSION and the rule-set identity, so a
  later rule change can never be mistaken for a data change.
* Missing stays missing. A field the scan did not observe is written as null
  and named in `missing_fields`. Nothing is inferred, defaulted or backfilled.
* No look-ahead. Outcome fields are written by a LATER append, never by the
  scan-time append; the writer refuses to accept an outcome on a scan record.
* No secrets, no prompts. Only numeric/state evidence and provenance labels.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

SCHEMA_VERSION: str = "validation-record-v1"

# Fields that may legitimately be absent. Anything absent is reported in
# `missing_fields` rather than silently defaulted — an unobserved rule must
# never read as a satisfied rule.
OPTIONAL_FIELDS: tuple[str, ...] = (
    "extended_atr", "atr_14", "rsi_14", "monthly_rsi", "weekly_rsi",
    "ma100_state", "integrity_label", "market_regime_risk_on",
    "sector", "liquidity_turnover_20d", "expected_days",
)


@dataclass(frozen=True)
class ValidationRecord:
    """One scan-time observation. Immutable by construction."""

    # -- identity / versioning ------------------------------------------------
    schema_version: str
    rule_set_version: str          # e.g. the scanner's grading contract identity
    record_kind: str               # "scan" | "outcome"
    key: str                       # date:symbol:grade — joins to the trust ledger

    # -- instrument -----------------------------------------------------------
    symbol: str
    resolved_instrument: str
    region: str
    asset_class: str
    sector: Optional[str]
    is_proxy: bool

    # -- provenance / freshness ----------------------------------------------
    data_provider: str
    scan_timestamp_utc: str
    market_as_of: str
    data_freshness: str            # "live" | "cached" | "stale"
    bars_available: Optional[int]

    # -- grade + score --------------------------------------------------------
    grade: str
    score: Optional[float]
    score_denominator: Optional[float]   # sub_scores_max sum — grades are score
                                         # independent, so this is evidence, not cause
    setup_classification: Optional[str]

    # -- levels ---------------------------------------------------------------
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    reward_risk: Optional[float]

    # -- the structural Grade-A inputs, recorded verbatim ---------------------
    atr_14: Optional[float]
    extended_atr: Optional[float]
    rsi_14: Optional[float]
    weekly_rsi: Optional[float]
    monthly_rsi: Optional[float]
    daily_trend: Optional[str]
    weekly_trend: Optional[str]
    monthly_trend: Optional[str]
    timeframes_aligned: Optional[int]
    ma100_state: Optional[bool]

    # -- conflicts, as identifiers rather than prose --------------------------
    conflict_ids: list[str]              # stable machine ids, not display text
    conflict_severity_provisional: dict[str, str]   # id -> proposed class
    conflict_evidence_source: dict[str, str]        # id -> engine that raised it

    # -- gates ----------------------------------------------------------------
    integrity_label: Optional[str]
    integrity_hard_blocks: list[str]
    market_regime_index: Optional[str]
    market_regime_risk_on: Optional[bool]

    # -- completeness ---------------------------------------------------------
    missing_fields: list[str] = field(default_factory=list)
    data_completeness_pct: Optional[float] = None

    # -- outcome: NEVER written at scan time ---------------------------------
    outcome: Optional[str] = None
    bars_to_resolve: Optional[int] = None
    mae_r: Optional[float] = None        # only when measurable without look-ahead
    mfe_r: Optional[float] = None
    outcome_recorded_at_utc: Optional[str] = None


def compute_missing(rec: dict[str, Any]) -> tuple[list[str], float]:
    """Name every optional field the scan did not observe, and score completeness.

    Returned as data, not as a silent default: a caller reading this record can
    always tell 'not observed' apart from 'observed and false'.
    """
    missing = [f for f in OPTIONAL_FIELDS if rec.get(f) is None]
    pct = 100.0 * (len(OPTIONAL_FIELDS) - len(missing)) / len(OPTIONAL_FIELDS)
    return missing, round(pct, 1)


def append_validation_record(path: str, rec: ValidationRecord) -> None:
    """Append one JSON line. Inert unless a caller supplies a path.

    Refuses to write an outcome on a scan record — that is the shape a
    look-ahead bug would take, so it fails loudly instead of persisting.
    """
    if rec.record_kind == "scan" and rec.outcome is not None:
        raise ValueError("look-ahead guard: a scan record must not carry an outcome")
    if rec.record_kind == "outcome":
        # An outcome cannot predate the scan that predicted it. Without this the
        # module would accept a row asserting the result was known before the
        # signal existed — the precise shape of a look-ahead bug, in the one
        # module whose job is to make look-ahead impossible.
        if rec.outcome_recorded_at_utc is None:
            raise ValueError("outcome record must carry outcome_recorded_at_utc")
        if rec.outcome_recorded_at_utc < rec.scan_timestamp_utc:
            raise ValueError(
                "look-ahead guard: outcome_recorded_at_utc precedes scan_timestamp_utc")
    if rec.schema_version != SCHEMA_VERSION:
        raise ValueError(f"schema mismatch: {rec.schema_version!r} != {SCHEMA_VERSION!r}")
    line = json.dumps(asdict(rec), separators=(",", ":"), sort_keys=True)
    # Append-only, line-atomic. No read-modify-write path exists in this module.
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
