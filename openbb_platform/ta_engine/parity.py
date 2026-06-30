"""
Golden-master parity utilities.

Loads TradingView reference cases (the Phase-9 schema) and compares them against
our detectors. Kept tiny and dependency-free so it can grow into the full
comparator (pivot tolerance, confirmation-state match, recency match) as live
reference cases become available.
"""
import json
import os
from typing import Dict

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")


def load_case(name: str) -> Dict:
    """Load a golden-master reference case by filename from ta_engine/golden/."""
    with open(os.path.join(_GOLDEN_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def ratio_within_window(value: float, window: Dict[str, float], tol: float = 0.0) -> bool:
    """True if `value` falls within [lo - tol, hi + tol] of a {lo, hi} window."""
    return (window["lo"] - tol) <= value <= (window["hi"] + tol)
