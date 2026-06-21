"""
Evidence Engine (Phase 2)

Purpose:
- Convert raw indicators + structure into normalized scores
- NO prediction
- NO risk
- NO ML

This is an institutional-style scoring layer.
"""

from typing import Dict
import pandas as pd


def score_momentum(indicators: Dict) -> float:
    """
    Score momentum strength from indicators.
    Output is normalized between 0 and 100.
    """

    score = 0.0

    # Example logic (simple + safe)
    if indicators.get("rsi", 50) > 55:
        score += 25
    if indicators.get("macd_hist", 0) > 0:
        score += 25

    return min(score, 100)


def score_trend(structure: Dict) -> float:
    """
    Score trend quality from market structure.
    """

    score = 0.0

    if structure.get("trend") == "up":
        score += 50
    if structure.get("higher_highs"):
        score += 25
    if structure.get("higher_lows"):
        score += 25

    return min(score, 100)


def build_evidence(
    indicators: Dict,
    structure: Dict
) -> Dict[str, float]:
    """
    Main Evidence Builder.

    Returns normalized scores that higher layers can use later.
    """

    momentum = score_momentum(indicators)
    trend = score_trend(structure)

    evidence = {
        "momentum_score": momentum,
        "trend_score": trend,
        "total_score": round((momentum + trend) / 2, 2)
    }

    return evidence
