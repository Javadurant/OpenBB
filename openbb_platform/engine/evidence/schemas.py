from dataclasses import dataclass
from typing import List

@dataclass
class EvidenceScore:
    name: str
    score: float      # 0.0 → 1.0
    confidence: float # 0.0 → 1.0

@dataclass
class EvidenceScores:
    momentum: EvidenceScore
    trend: EvidenceScore
    structure: EvidenceScore
    volatility: EvidenceScore
    total: float