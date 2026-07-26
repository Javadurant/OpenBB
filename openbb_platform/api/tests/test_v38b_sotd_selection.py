# api/tests/test_v38b_sotd_selection.py
"""v3.8 SOTD selection contract: grade-first, then score. Locks the fix that
makes Setup of the Day pick a real Grade-B 'solid alignment' over a
higher-score but more-conflicted Grade-C. Pure/deterministic, no network."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.phase2_router import _member_sort_key


def test_grade_beats_higher_score():
    # The exact live case: MORROW.ST (C, 80) must NOT beat NAVIGO (B, 77).
    members = [
        {"symbol": "MORROW.ST", "grade": "C", "score": 80.0},
        {"symbol": "NAVIGO.ST", "grade": "B", "score": 77.0},
        {"symbol": "TOP.ST", "grade": "A", "score": 60.0},
        {"symbol": "PROXY", "grade": "A", "score": 99.0, "proxy": True},
    ]
    members.sort(key=_member_sort_key)
    assert [m["symbol"] for m in members] == ["TOP.ST", "NAVIGO.ST", "MORROW.ST", "PROXY"]
    # Grade A direct wins; proxy ranked last despite score 99.


def test_within_grade_higher_score_wins():
    members = [{"symbol": "LO", "grade": "B", "score": 70.0},
               {"symbol": "HI", "grade": "B", "score": 75.0}]
    members.sort(key=_member_sort_key)
    assert members[0]["symbol"] == "HI"


def test_unknown_grade_ranks_last():
    members = [{"symbol": "C1", "grade": "C", "score": 50.0},
               {"symbol": "UNK", "grade": None, "score": 99.0}]
    members.sort(key=_member_sort_key)
    assert members[0]["symbol"] == "C1"


def test_missing_score_is_safe():
    members = [{"symbol": "A1", "grade": "B"}, {"symbol": "A2", "grade": "B", "score": 5.0}]
    members.sort(key=_member_sort_key)  # must not raise on missing score
    assert members[0]["symbol"] == "A2"
