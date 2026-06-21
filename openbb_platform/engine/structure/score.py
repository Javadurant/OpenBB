"""
Structure Evidence Score

Purpose:
- Evaluate market structure strength
- NO indicators
- NO prediction
- NO risk logic

This file returns ONE normalized score between 0.0 and 1.0
"""

import pandas as pd


def structure_score(df: pd.DataFrame) -> float:
    """
    Compute a simple, explainable market structure score.

    Logic (deterministic & beginner-safe):
    - Higher highs + higher lows → bullish structure
    - Lower highs + lower lows → bearish structure
    - Mixed → weak / neutral structure

    Returns:
        float: structure score between 0.0 and 1.0
    """

    # --- Safety checks (never trust input blindly) ---
    if df is None or len(df) < 5:
        return 0.5  # Neutral when data is insufficient

    required_cols = {"high", "low"}
    if not required_cols.issubset(df.columns):
        return 0.5  # Neutral if structure cannot be evaluated

    # --- Use only recent structure (institutional habit) ---
    recent = df.tail(5)

    highs = recent["high"].values
    lows = recent["low"].values

    # --- Structure conditions ---
    higher_highs = highs[-1] > highs[0]
    higher_lows = lows[-1] > lows[0]

    lower_highs = highs[-1] < highs[0]
    lower_lows = lows[-1] < lows[0]

    # --- Scoring ---
    if higher_highs and higher_lows:
        return 0.8  # Strong bullish structure

    if lower_highs and lower_lows:
        return 0.2  # Strong bearish structure

    return 0.5  # Neutral / mixed structure
