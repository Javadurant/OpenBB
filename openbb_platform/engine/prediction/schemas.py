from dataclasses import dataclass

@dataclass
class PredictionResult:
    direction: str          # "bullish" | "bearish" | "neutral"
    probability: float      # 0.0 - 1.0
    confidence: str         # "low" | "medium" | "high"
    explanation: str
