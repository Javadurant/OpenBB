"""
Central contract definitions.
All cross-module data shapes live here.
"""

from typing import TypedDict, Dict


class EvidenceScores(TypedDict):
    momentum: float
    trend: float
    volatility: float
    structure: float


class PredictionResult(TypedDict):
    direction: str          # "bullish" | "bearish" | "neutral"
    probability: float      # 0.0 – 1.0
    confidence: float       # 0.0 – 1.0


class SignalResult(TypedDict):
    action: str             # "buy" | "sell" | "hold"
    probability: float
    confidence: float
    risk: float


class PipelineResult(TypedDict):
    evidence: EvidenceScores
    prediction: PredictionResult
    signal: SignalResult
