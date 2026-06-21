"""
Signal Builder
Collects indicator outputs and feeds a simple Decision Engine
"""

import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """
    Calculate Relative Strength Index (RSI)
    Beginner-friendly implementation
    """
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(rsi.iloc[-1], 2)


def build_signal(df: pd.DataFrame) -> dict:
    """
    Build a simple institutional-style signal from price data.
    """

    indicators = {}

    # ---- RSI (Momentum) ----
    indicators["rsi"] = calculate_rsi(df["close"])

    # ---- Simple Decision Logic ----
    rsi = indicators["rsi"]

    if rsi < 30:
        bias = "Bullish (Oversold)"
    elif rsi > 70:
        bias = "Bearish (Overbought)"
    else:
        bias = "Neutral"

    decision = {
        "bias": bias,
        "rsi": rsi,
    }

    return {
        "indicators": indicators,
        "decision": decision,
    }
