import pandas as pd

def smart_money_concepts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifies Liquidity Voids (FVG) and Order Blocks.
    """
    df = df.copy()
    df['fvg_bullish'] = False
    df['fvg_bearish'] = False
    
    # Bullish FVG: Low(n) > High(n-2)
    # Bearish FVG: High(n) < Low(n-2)
    for i in range(2, len(df)):
        if df['low'].iloc[i] > df['high'].iloc[i-2]:
            df.at[df.index[i-1], 'fvg_bullish'] = True
        elif df['high'].iloc[i] < df['low'].iloc[i-2]:
            df.at[df.index[i-1], 'fvg_bearish'] = True
            
    return df[['fvg_bullish', 'fvg_bearish']]