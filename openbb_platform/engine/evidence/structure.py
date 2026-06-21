import pandas as pd
from engine.evidence.schemas import EvidenceScore

def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """
    Find the first matching column name from a list of candidates.
    This allows structure logic to remain stable across data providers.
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


def structure_score(df: pd.DataFrame) -> EvidenceScore:
    """
    Evaluates recent price structure (higher highs / lower lows).

    IMPORTANT CONTRACT:
    - This function must NEVER crash due to schema differences
    - If required columns are missing, return a neutral EvidenceScore
    """

    high_col = _resolve_column(df, ["high", "High", "h", "high_price"])
    low_col = _resolve_column(df, ["low", "Low", "l", "low_price"])

    # Defensive guard: schema mismatch → neutral signal
    if high_col is None or low_col is None or len(df) < 3:
        return EvidenceScore(
            name="structure",
            score=0.5,
            confidence=0.0,
        )

    # 🔧 MINIMAL FIX: enforce numeric dtype (single logical fix)
    highs = pd.to_numeric(df[high_col].iloc[-3:], errors="coerce")
    lows = pd.to_numeric(df[low_col].iloc[-3:], errors="coerce")

    higher_highs = highs.is_monotonic_increasing
    higher_lows = lows.is_monotonic_increasing

    # Normalized range 0.0 to 1.0 (Compliance fix)
    if higher_highs and higher_lows:
        score = 1.0
    elif not higher_highs and not higher_lows:
        score = 0.0
    else:
        score = 0.5

    return EvidenceScore(
        name="structure",
        score=score,
        confidence=0.7,
    )