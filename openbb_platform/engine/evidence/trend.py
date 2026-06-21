"""
Trend evidence score.
Single responsibility.
No dependencies on other evidence files.
"""
from .schemas import EvidenceScore

def trend_score(df) -> EvidenceScore:
    """
    Returns a normalized trend score between 0 and 1.
    For now: simple directional trend: last close vs first close.
    """

    if df is None or len(df) < 2:
        return EvidenceScore("trend", 0.5, 0.0)

    # Simple directional trend: last close vs first close
    start = df["close"].iloc[0]
    end = df["close"].iloc[-1]

    if end > start:
        score = 0.7   # bullish bias
    elif end < start:
        score = 0.3   # bearish bias
    else:
        score = 0.5   # neutral

    return EvidenceScore(name="trend", score=score, confidence=0.8)