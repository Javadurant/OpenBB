from typing import Dict, Any
import pandas as pd
from engine.evidence.schemas import EvidenceScore


def evidence_to_dataframe(evidence: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert heterogeneous evidence objects into a UI-friendly table.

    Contract:
    - Must never raise due to mixed value types
    - Must preserve signal meaning without altering scores
    """

    rows = []

    for name, value in evidence.items():
        if isinstance(value, EvidenceScore):
            rows.append(
                {
                    "signal": name,
                    "score": value.score,
                    "confidence": value.confidence,
                }
            )
        else:
            rows.append(
                {
                    "signal": name,
                    "score": float(value),
                    "confidence": None,
                }
            )

    return pd.DataFrame(rows).sort_values(
        by=["confidence", "score"],
        ascending=[False, False],
        na_position="last",
    )
