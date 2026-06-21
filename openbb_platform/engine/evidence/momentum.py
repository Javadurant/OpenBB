import pandas as pd
from .schemas import EvidenceScore

def momentum_score(df: pd.DataFrame) -> EvidenceScore:
    """
    Measures directional momentum using simple price change.
    """
    if len(df) < 2:
        return EvidenceScore("momentum", 0.5, 0.0)

    delta = df["close"].iloc[-1] - df["close"].iloc[-2]

    score = 1.0 if delta > 0 else 0.0
    confidence = min(abs(delta) / df["close"].iloc[-2], 1.0)

    return EvidenceScore("momentum", score, confidence)
