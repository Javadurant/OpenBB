from dataclasses import dataclass

@dataclass
class RiskResult:
    allowed: bool
    adjusted_probability: float
    risk_level: str        # "low" | "medium" | "high"
    reason: str
