"""
api/feedback_store.py  — <- NEW [HELP/RATINGS]: anonymous star-rating + helpful store.

Append-only JSONL, mirroring the proven api/setup_ledger.py pattern (threading
lock + atomic rewrite). Stores ZERO PII: no user id, no IP, no query text — only
{ts, target_type, target_id, stars|helpful}. Used by Help articles, FAQ items,
AI answers, and website sections.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Final, Optional, TypedDict

logger = logging.getLogger(__name__)

# Store lives next to sentriq_ledger.jsonl (openbb_platform/).
_FEEDBACK_PATH: Final = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "sentriq_feedback.jsonl"
)
_WRITE_LOCK: Final = threading.Lock()

# Hard allow-list so a caller can never invent target namespaces.
_ALLOWED_TYPES: Final = frozenset(
    {"article", "faq", "ai_answer", "section"}
)
# target_id sanitiser: collapse anything that is not a safe id char.
_ID_SANITISE: Final = re.compile(r"[^A-Za-z0-9_.:\-/]+")
_MAX_ID_LEN: Final = 120
_MIN_STARS: Final = 1
_MAX_STARS: Final = 5


class Aggregate(TypedDict):
    """Public aggregate for a single rating target."""
    target_type: str
    target_id: str
    avg: Optional[float]
    count: int
    helpful_yes: int
    helpful_no: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitise_id(target_id: str) -> str:
    """Clamp + strip a target id to safe characters. Pure, no side effects."""
    s = _ID_SANITISE.sub("-", (target_id or "").strip())[:_MAX_ID_LEN]
    return s


def _read_all() -> list[dict]:
    """Read every record. Tolerates a missing file and skips corrupt lines."""
    if not os.path.exists(_FEEDBACK_PATH):
        return []
    out: list[dict] = []
    try:
        with open(_FEEDBACK_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("feedback_store: skipping corrupt line")
                    continue
    except OSError as exc:
        logger.error("feedback_store: read failed: %s", exc)
        return []
    return out


def record(
    target_type: str,
    target_id: str,
    *,
    stars: Optional[int] = None,
    helpful: Optional[bool] = None,
) -> Aggregate:
    """Append one feedback record and return the fresh aggregate for the target.

    Exactly one of `stars` (1..5) or `helpful` (bool) must be provided. Raises
    ValueError on invalid input so the router can return HTTP 422 cleanly.
    """
    if target_type not in _ALLOWED_TYPES:
        raise ValueError(f"target_type must be one of {sorted(_ALLOWED_TYPES)}")
    tid = _sanitise_id(target_id)
    if not tid:
        raise ValueError("target_id is empty after sanitisation")
    if (stars is None) == (helpful is None):
        raise ValueError("provide exactly one of stars or helpful")

    rec: dict[str, Any] = {"ts": _now_iso(), "target_type": target_type, "target_id": tid}
    if stars is not None:
        s = int(stars)
        if s < _MIN_STARS or s > _MAX_STARS:
            raise ValueError(f"stars must be {_MIN_STARS}..{_MAX_STARS}")
        rec["stars"] = s
    else:
        rec["helpful"] = bool(helpful)

    try:
        with _WRITE_LOCK:
            with open(_FEEDBACK_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
    except OSError as exc:
        logger.error("feedback_store: append failed: %s", exc)
        raise

    return aggregate(target_type, tid)


def aggregate(target_type: str, target_id: str) -> Aggregate:
    """Aggregate stars (avg + count) and helpful votes for one target.

    Float-safe: avg is computed only when count > 0 (no float == anywhere).
    """
    tid = _sanitise_id(target_id)
    star_sum = 0
    star_n = 0
    yes = 0
    no = 0
    for r in _read_all():
        if r.get("target_type") != target_type or r.get("target_id") != tid:
            continue
        if "stars" in r:
            try:
                star_sum += int(r["stars"])
                star_n += 1
            except (TypeError, ValueError):
                continue
        elif "helpful" in r:
            if bool(r["helpful"]):
                yes += 1
            else:
                no += 1
    avg = (star_sum / star_n) if star_n > 0 else None
    return Aggregate(
        target_type=target_type, target_id=tid,
        avg=(round(avg, 2) if avg is not None else None),
        count=star_n, helpful_yes=yes, helpful_no=no,
    )
