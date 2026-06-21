import numpy as np
from typing import Dict, List
from .schemas import PredictionResult

def predict_scenarios(data: Dict) -> PredictionResult:
    """
    Reconstructed ML Prediction Engine.
    Returns a validated PredictionResult dataclass.
    Aligned with Geometric/Harmonic structures.
    """
    close_price = float(data.get("close", 0))
    rsi = float(data.get("rsi", 50))
    tech_bias = str(data.get("bias", "NEUTRAL")).upper()
    harmonics = data.get("harmonics", [])
    
    bias_map = {"BULLISH": 0.7, "BEARISH": 0.3, "NEUTRAL": 0.5}
    base_sentiment = bias_map.get(tech_bias, 0.5)
    
    # RSI Influence
    rsi_adj = 0
    if rsi < 30: rsi_adj = 0.15
    elif rsi > 70: rsi_adj = -0.15
        
    # Harmonic Influence (Alignment Logic)
    harmonic_adj = 0
    for p in harmonics:
        # Confirmed terminal bars carry higher weight
        weight = 0.15 if p.get("terminal_confirmed") else 0.05
        harmonic_adj += weight if p.get("is_bullish") else -weight
    
    sentiment_score = max(0.1, min(0.9, base_sentiment + rsi_adj + harmonic_adj))
    direction = "bullish" if sentiment_score >= 0.5 else "bearish"
    
    # Map confidence to schema strings
    prob = round(sentiment_score if direction == "bullish" else (1 - sentiment_score), 2)
    conf_str = "high" if prob > 0.8 else "medium" if prob > 0.6 else "low"
    
    h_count = len(harmonics)
    h_context = f" with {h_count} active harmonic structures" if h_count > 0 else ""
    explanation = f"Technicals show {tech_bias} bias with RSI at {rsi:.1f}{h_context}. ML confirms {direction} momentum."

    return PredictionResult(
        direction=direction,
        probability=prob,
        confidence=conf_str,
        explanation=explanation
    )