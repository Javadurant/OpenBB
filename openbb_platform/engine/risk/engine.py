from engine.risk.schemas import RiskResult
from engine.risk.filters import volatility_filter, confidence_filter


def apply_risk_filter(
    probability: float,
    confidence: str,
    volatility_score: float,
) -> RiskResult:
    """
    Applies deterministic risk rules to prediction output.
    """

    # Confidence gate (hard veto)
    if not confidence_filter(confidence):
        return RiskResult(
            allowed=False,
            adjusted_probability=0.0,
            risk_level="high",
            reason="Confidence too low",
        )

    # Volatility penalty
    penalty = volatility_filter(volatility_score)
    adjusted_prob = round(probability * penalty, 2)

    # Risk level classification
    if penalty < 0.7:
        risk_level = "high"
    elif penalty < 0.9:
        risk_level = "medium"
    else:
        risk_level = "low"

    return RiskResult(
        allowed=True,
        adjusted_probability=adjusted_prob,
        risk_level=risk_level,
        reason="Risk conditions acceptable",
    )
