"""
engine/deliberation_log.py

QuantEdge — Persistent Deliberation Log (Phase D)
Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH

ARCHITECTURE:
  SQLite-backed audit trail for every Council deliberation.
  Stores: decision_type, query, deliberation, synthesis, timestamp.

  Each /council/synthesize call automatically appends to this log,
  giving the user a permanent record of:
    - What questions they asked the Council
    - What data the advisors saw
    - What the AI's verdict was
    - When it happened

WHY THIS LAYER EXISTS:
  Without persistence, every deliberation evaporates when the gateway
  restarts. This is unacceptable for a trading platform — users need
  to review past decisions, audit advisor behavior, and learn from
  patterns.

DATABASE LOCATION:
  Default: <project_root>/quantedge_deliberations.db
  Override via QE_DELIBERATION_DB env var.

SCHEMA:
  deliberations(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,        -- ISO 8601 UTC
    decision_type TEXT NOT NULL,
    query       TEXT,
    verdict     TEXT,                  -- BUY | HOLD | SELL | NULL on synth fail
    confidence  INTEGER,               -- 0-100 | NULL on synth fail
    headline    TEXT,
    reasoning   TEXT,
    risks_json  TEXT,                  -- JSON array
    actions_json TEXT,                 -- JSON array
    deliberation_json TEXT NOT NULL,   -- Full advisor data
    synthesis_success INTEGER NOT NULL -- 0 or 1
  )
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger("QuantEdge.DeliberationLog")

# ── Configuration ───────────────────────────────────────────────────
DEFAULT_DB_FILENAME: str = "quantedge_deliberations.db"


def _resolve_db_path() -> Path:
    """
    Locate the SQLite DB file. Order of precedence:
      1. QE_DELIBERATION_DB env var (absolute path)
      2. <openbb_platform>/quantedge_deliberations.db
    """
    env_path = os.getenv("QE_DELIBERATION_DB")
    if env_path:
        return Path(env_path)
    # Default: alongside the gateway code
    here = Path(__file__).resolve().parent.parent  # openbb_platform/
    return here / DEFAULT_DB_FILENAME


DB_PATH: Path = _resolve_db_path()


# ── Schema setup ────────────────────────────────────────────────────
SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS deliberations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    decision_type     TEXT NOT NULL,
    query             TEXT,
    verdict           TEXT,
    confidence        INTEGER,
    headline          TEXT,
    reasoning         TEXT,
    risks_json        TEXT,
    actions_json      TEXT,
    deliberation_json TEXT NOT NULL,
    synthesis_success INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_deliberations_created_at
    ON deliberations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deliberations_verdict
    ON deliberations(verdict);

CREATE INDEX IF NOT EXISTS idx_deliberations_decision_type
    ON deliberations(decision_type);
"""


@contextmanager
def _connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with row factory + auto-close."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Create tables and indices if missing. Idempotent."""
    with _connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info("Deliberation DB initialized at %s", db_path or DB_PATH)


def _utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Public API ──────────────────────────────────────────────────────
def save_deliberation(
    decision_type: str,
    query: str,
    deliberation: List[Dict[str, Any]],
    synthesis: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
) -> int:
    """
    Persist a complete deliberation + synthesis to the log.

    Returns:
        The auto-generated `id` of the inserted row.

    Raises:
        sqlite3.DatabaseError on persistence failure.
    """
    created_at = _utc_now_iso()

    verdict        = synthesis.get("verdict")
    confidence_raw = synthesis.get("confidence")
    confidence     = int(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
    headline       = synthesis.get("headline", "")
    reasoning      = synthesis.get("reasoning", "")
    risks_json     = json.dumps(synthesis.get("risks", []), default=str)
    actions_json   = json.dumps(synthesis.get("actions", []), default=str)
    success_flag   = 1 if synthesis.get("success") else 0
    deliberation_json = json.dumps(deliberation, default=str)

    with _connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO deliberations
                (created_at, decision_type, query, verdict, confidence,
                 headline, reasoning, risks_json, actions_json,
                 deliberation_json, synthesis_success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at, decision_type, query, verdict, confidence,
                headline, reasoning, risks_json, actions_json,
                deliberation_json, success_flag,
            ),
        )
        row_id = cur.lastrowid

    logger.info(
        "Saved deliberation id=%d decision=%s verdict=%s confidence=%s",
        row_id, decision_type, verdict, confidence,
    )
    return int(row_id) if row_id is not None else 0


def list_deliberations(
    limit: int = 50,
    *,
    verdict_filter: Optional[str] = None,
    decision_type_filter: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Return recent deliberations in reverse chronological order.

    Args:
        limit:                  Max rows to return (1-500).
        verdict_filter:         If set, only rows with this verdict.
        decision_type_filter:   If set, only rows with this decision type.
    """
    limit = max(1, min(500, int(limit)))

    where_clauses: List[str] = []
    params: List[Any] = []
    if verdict_filter:
        where_clauses.append("verdict = ?")
        params.append(verdict_filter)
    if decision_type_filter:
        where_clauses.append("decision_type = ?")
        params.append(decision_type_filter)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)

    sql = f"""
        SELECT id, created_at, decision_type, query, verdict, confidence,
               headline, synthesis_success
        FROM deliberations
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """

    with _connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def get_deliberation(deliberation_id: int, *, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch a full deliberation by id. Returns None if not found.

    The deliberation_json and *_json fields are decoded into Python objects.
    """
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM deliberations WHERE id = ?",
            (int(deliberation_id),),
        ).fetchone()

    if row is None:
        return None

    out: Dict[str, Any] = dict(row)
    # Decode JSON columns
    for json_col in ("risks_json", "actions_json", "deliberation_json"):
        raw = out.get(json_col)
        if raw:
            try:
                out[json_col.replace("_json", "")] = json.loads(raw)
            except json.JSONDecodeError:
                out[json_col.replace("_json", "")] = None
    return out


def count_deliberations(*, db_path: Optional[Path] = None) -> int:
    """Return total deliberation count."""
    with _connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM deliberations").fetchone()
    return int(row["c"]) if row else 0


def stats(*, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return verdict and decision-type distribution."""
    with _connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM deliberations").fetchone()["c"]
        verdict_rows = conn.execute(
            "SELECT verdict, COUNT(*) AS c FROM deliberations GROUP BY verdict"
        ).fetchall()
        decision_rows = conn.execute(
            "SELECT decision_type, COUNT(*) AS c FROM deliberations GROUP BY decision_type"
        ).fetchall()
        success_row = conn.execute(
            "SELECT SUM(synthesis_success) AS s FROM deliberations"
        ).fetchone()

    return {
        "total":             int(total),
        "synthesis_success": int(success_row["s"] or 0),
        "by_verdict":        {(r["verdict"] or "NULL"): int(r["c"]) for r in verdict_rows},
        "by_decision_type":  {r["decision_type"]: int(r["c"]) for r in decision_rows},
        "db_path":           str(DB_PATH),
    }
