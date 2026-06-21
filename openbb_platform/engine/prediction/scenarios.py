def score_to_direction(score: float) -> str:
    """
    Converts aggregate evidence score into directional bias.
    """
    if score >= 65:
        return "bullish"
    if score <= 35:
        return "bearish"
    return "neutral"


def score_to_probability(score: float) -> float:
    """
    Maps evidence score (0-100) to probability (0.0-1.0).
    Keeps system conservative.
    """
    return round(score / 100.0, 2)


def probability_to_confidence(prob: float) -> str:
    """
    Converts probability into confidence buckets.
    """
    if prob >= 0.70:
        return "high"
    if prob >= 0.55:
        return "medium"
    return "low"
