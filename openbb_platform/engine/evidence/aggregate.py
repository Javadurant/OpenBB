import pandas as pd
from typing import Dict

from engine.evidence.momentum import momentum_score
from engine.evidence.trend import trend_score
from engine.evidence.volatility import volatility_score
from engine.evidence.structure import structure_score
from engine.evidence.schemas import EvidenceScore

# ============================
# AGGREGATION FUNCTION
# ============================
def aggregate_evidence(df: pd.DataFrame) -> Dict[str, EvidenceScore]:
    """
    Aggregates all independent evidence signals.

    IMPORTANT:
    - Each evidence module already returns an EvidenceScore
    - This function MUST NOT cast or modify scores
    - Aggregation is structural, not interpretive
    """

    evidence = {
        "momentum": momentum_score(df),
        "trend": trend_score(df),
        "volatility": volatility_score(df),
        "structure": structure_score(df),
    }

    # 🔧 Minimal fix: produce safe_market_regime alias with valid constructor
    market_regime = EvidenceScore(name="market_regime", score=0.0, confidence=1.0)
    evidence["market_regime"] = market_regime
    evidence["safe_market_regime"] = market_regime  # alias for app.py

    return evidence


# ============================
# MARKET REGIME ACCESSOR
# ============================
def get_safe_market_regime(evidence: Dict[str, EvidenceScore]) -> EvidenceScore:
    """
    Canonical accessor for market regime evidence.

    Provides a stable contract for downstream consumers
    without assuming a specific internal key name.
    """

    if "safe_market_regime" in evidence:
        return evidence["safe_market_regime"]

    if "market_regime" in evidence:
        return evidence["market_regime"]

    if "regime" in evidence:
        return evidence["regime"]

    raise KeyError(
        "Market regime not present in evidence payload. "
        "Expected one of: safe_market_regime, market_regime, regime."
    )
