# engine/risk/risk_management.py
import pandas as pd
import numpy as np
from typing import Dict

def calculate_position_size(account_size: float, risk_pct: float, entry_price: float, stop_loss: float) -> Dict:
    if entry_price == stop_loss:
        return {"units": 0, "risk_amount": 0, "msg": "Entry equals Stop Loss"}
    risk_per_share = abs(entry_price - stop_loss)
    total_risk_cash = account_size * risk_pct
    units = total_risk_cash / risk_per_share
    return {
        "units": round(units, 4),
        "total_risk_cash": round(total_risk_cash, 2),
        "risk_per_share": round(risk_per_share, 4),
        "position_value": round(units * entry_price, 2)
    }

def get_dynamic_risk_params(df: pd.DataFrame, side: str) -> Dict:
    """
    INTEGRATED: Now prioritizes Harmonic PRZ levels for Stop Loss.
    """
    # Import locally to avoid potential circular dependencies
    from engine.features.indicators import get_atr, detect_harmonics
    
    last_price = df['close'].iloc[-1]
    
    # Safe ATR calculation
    try:
        atr_series = get_atr(df)
        atr = atr_series.iloc[-1] if not atr_series.empty else (last_price * 0.01)
    except Exception:
        atr = last_price * 0.01 # Fallback 1% volatility
    
    harmonics = detect_harmonics(df)
    prz_level = None
    
    if harmonics and isinstance(harmonics, list):
        prz_level = harmonics[-1].get('target_z')

    if side == "BUY":
        # Check if pivot data exists in columns
        has_pivot = 'is_low' in df.columns and not df[df['is_low'] == True].empty
        structural_sl = prz_level if prz_level and prz_level < last_price else \
                        df[df['is_low'] == True]['pivot_low'].iloc[-1] if has_pivot else (last_price - (2 * atr))
        
        stop_loss = min(structural_sl, last_price - (1.5 * atr))
        take_profit = last_price + (abs(last_price - stop_loss) * 2)
    else:
        has_pivot = 'is_high' in df.columns and not df[df['is_high'] == True].empty
        structural_sl = prz_level if prz_level and prz_level > last_price else \
                        df[df['is_high'] == True]['pivot_high'].iloc[-1] if has_pivot else (last_price + (2 * atr))
        
        stop_loss = max(structural_sl, last_price + (1.5 * atr))
        take_profit = last_price - (abs(last_price - stop_loss) * 2)

    return {
        "entry": last_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "harmonic_prz": prz_level
    }