from typing import Dict, Any, List


def scenario_contributions(evidence: Dict[str, Any]) -> List[dict]:
    """
    Decomposes final directional bias into per-signal contributions.

    Contract:
    - Read-only
    - Never mutates evidence
    - Skips incompatible evidence safely
    """

    rows: List[dict] = []

    for name, value in evidence.items():
        if hasattr(value, "score") and hasattr(value, "confidence"):
            contribution = value.score * value.confidence
            rows.append(
                {
                    "signal": name,
                    "score": value.score,
                    "confidence": value.confidence,
                    "contribution": contribution,
                }
            )
        elif isinstance(value, (int, float)):
            rows.append(
                {
                    "signal": name,
                    "score": float(value),
                    "confidence": 1.0,
                    "contribution": float(value),
                }
            )

    return sorted(rows, key=lambda r: abs(r["contribution"]), reverse=True)
