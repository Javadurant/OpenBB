# engine/evidence/engine.py
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class EvidenceComponent:
    score: float  # Range [0, 1]
    details: str

@dataclass
class InstitutionalEvidence:
    trend: EvidenceComponent
    momentum: EvidenceComponent
    structure: EvidenceComponent
    total: float  # Weighted average

def aggregate_evidence(df: pd.DataFrame) -> InstitutionalEvidence:
    """
    Calculates the Institutional Alpha Score based on Trend, Momentum, and Structure.
    Mathematical formulation: 
    Total Score S = (w_t * T) + (w_m * M) + (w_s * S)
    """
    if df is None or df.empty or len(df) < 200:
        empty_comp = EvidenceComponent(0.0, "Insufficient Data")
        return InstitutionalEvidence(empty_comp, empty_comp, empty_comp, 0.0)

    # 1. TREND COMPONENT (Weight: 40%)
    # Logic: Proximity to 200 SMA and Slope of 50 SMA
    sma200 = df['close'].rolling(200).mean().iloc[-1]
    sma50 = df['close'].rolling(50).mean()
    curr_close = df['close'].iloc[-1]
    
    trend_score = 0.0
    if curr_close > sma200: trend_score += 0.5
    if sma50.iloc[-1] > sma50.iloc[-5]: trend_score += 0.5
    trend_comp = EvidenceComponent(trend_score, f"Close vs SMA200: {curr_close/sma200:.2%}")

    # 2. MOMENTUM COMPONENT (Weight: 30%)
    # Logic: RSI discipline and MACD Histogram
    last_rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else 50
    macd_h = df['macdh'].iloc[-1] if 'macdh' in df.columns else 0
    
    mom_score = 0.0
    if 40 < last_rsi < 60: mom_score += 0.3 # Equilibrium
    elif last_rsi > 60: mom_score += 0.7    # Bullish strength
    if macd_h > 0: mom_score += 0.3
    mom_comp = EvidenceComponent(min(1.0, mom_score), f"RSI: {last_rsi:.2f}")

    # 3. STRUCTURE COMPONENT (Weight: 30%)
    # Logic: Proximity to key technical levels (Fibs/Harmonics)
    # Simplified here: ATR-based volatility check
    atr_norm = (df['atr'].iloc[-1] / df['close'].iloc[-1]) * 100 if 'atr' in df.columns else 0
    struct_score = 0.5 if atr_norm < 2.0 else 0.8 # Lower relative vol = higher structure stability
    struct_comp = EvidenceComponent(struct_score, f"ATR Norm: {atr_norm:.2f}%")

    # Final Weighted Computation (Karpathy Numerical Stability)
    weights = np.array([0.4, 0.3, 0.3])
    scores = np.array([trend_comp.score, mom_comp.score, struct_comp.score])
    total_score = float(np.dot(weights, scores))

    return InstitutionalEvidence(
        trend=trend_comp,
        momentum=mom_comp,
        structure=struct_comp,
        total=round(total_score, 4)
    )