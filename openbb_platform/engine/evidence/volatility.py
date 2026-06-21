import pandas as pd
from .schemas import EvidenceScore

def volatility_score(df: pd.DataFrame) -> EvidenceScore:
    """
    Measures volatility expansion vs contraction.
    """
    if len(df) < 10:
        return EvidenceScore("volatility", 0.5, 0.0)

    returns = df["close"].pct_change()
    vol = returns.rolling(10).std().iloc[-1]

    score = 0.0 if vol > returns.std() else 1.0
    confidence = min(vol / returns.std(), 1.0)

    return EvidenceScore("volatility", score, confidence)
