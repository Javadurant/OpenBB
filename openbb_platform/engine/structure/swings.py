import pandas as pd
import numpy as np
from typing import List, Tuple

def find_pivots(data: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Principal Engineer Standard: Identifies peak/valley pivots.
    Uses a centered window to ensure look-ahead bias is managed.
    """
    df = data.copy()
    df['peak'] = (df['high'] == df['high'].rolling(window=window*2+1, center=True).max())
    df['valley'] = (df['low'] == df['low'].rolling(window=window*2+1, center=True).min())
    
    # Extract only the pivot points
    pivots = df[df['peak'] | df['valley']].copy()
    return pivots

