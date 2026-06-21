def volatility_filter(volatility_score: float) -> float:
    """
    Penalize probability in high-volatility regimes.
    volatility_score expected range: 0-100
    """
    if volatility_score > 70:
        return 0.6
    if volatility_score > 50:
        return 0.8
    return 1.0


def confidence_filter(confidence: str) -> bool:
    """
    Enforce minimum confidence requirement.
    """
    return confidence in ("medium", "high")
