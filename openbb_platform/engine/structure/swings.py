# engine/structure/swings.py
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


def find_pivots(df: pd.DataFrame, order: int = 5) -> pd.DataFrame:
    """
    Identifies local peaks and valleys in price action.
    
    Args:
        df: DataFrame with at least a 'close' column.
        order: How many candles to the left and right to look for a peak.
               Higher order = more significant (macro) pivots.
    """
    data = df.copy()
    
    # Find local maxima and minima
    data['is_peak'] = data.iloc[
        argrelextrema(data.close.values, np.greater_equal, order=order)[0]
    ]['close']
    data['is_valley'] = data.iloc[
        argrelextrema(data.close.values, np.less_equal, order=order)[0]
    ]['close']
    
    # Filter only rows that are pivots
    pivots = data[
        (data['is_peak'].notnull()) | (data['is_valley'].notnull())
    ].copy()
    
    # Clean up the output to return a clean price series of pivots
    pivots['pivot_type'] = np.where(
        pivots['is_peak'].notnull(), 'high', 'low'
    )
    
    return pivots[['close', 'pivot_type']]


# <- ADDED [Gate 4c]: enforce_alternation() — required by HarmonicEngine.scan().
# Harmonic pattern detection requires strictly alternating pivot direction.
# find_pivots() can return consecutive same-direction pivots (two highs or
# two lows in a row) which causes all ratio conditions to fail, producing
# 0 patterns. This function is additive — find_pivots() is not modified,
# ensuring the Elliott Wave pipeline in app.py is unaffected.
def enforce_alternation(pivots: pd.DataFrame) -> pd.DataFrame:
    """
    Filters a pivot DataFrame to enforce strict peak-valley alternation.

    All harmonic pattern detectors (ABCD, XABCD, Shark, 5-0) require
    each consecutive pivot to reverse direction. If two consecutive pivots
    have the same type (both 'high' or both 'low'), the second is discarded
    and the one with the more extreme price is retained.

    Args:
        pivots: DataFrame with columns ['close', 'pivot_type'] as returned
                by find_pivots(). 'pivot_type' values must be 'high' or 'low'.

    Returns:
        DataFrame: Subset of input rows with strictly alternating pivot_type.
                   Index (DatetimeIndex) is preserved from the input.
    """
    if pivots.empty:
        return pivots.copy()

    alternating_rows = []
    last_type: str = ""

    for idx, row in pivots.iterrows():
        current_type: str = row['pivot_type']
        current_price: float = row['close']

        if current_type != last_type:
            # Direction changed — accept this pivot
            alternating_rows.append(idx)
            last_type = current_type
        else:
            # Same direction as prior pivot — keep the more extreme one
            if not alternating_rows:
                alternating_rows.append(idx)
                last_type = current_type
                continue
            prior_idx = alternating_rows[-1]
            prior_price: float = pivots.loc[prior_idx, 'close']
            if current_type == 'high':
                # Keep the higher of two consecutive highs
                if current_price > prior_price:
                    alternating_rows[-1] = idx
            else:
                # Keep the lower of two consecutive lows
                if current_price < prior_price:
                    alternating_rows[-1] = idx

    return pivots.loc[alternating_rows]