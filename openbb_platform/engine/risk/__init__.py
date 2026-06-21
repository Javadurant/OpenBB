# ==========================================
# UNIFIED RISK INTERFACE (Zero Quality Loss)
# ==========================================

# 1. Primary Sizing Logic (Required by app.py)
from .risk_management import (
    calculate_position_size,
    get_dynamic_risk_params
)

# 2. Institutional Filters & Schemas (Additive)
try:
    from engine.risk.engine import apply_risk_filter
    from engine.risk.schemas import RiskResult
    HAS_INSTITUTIONAL_LOGIC = True
except ImportError:
    HAS_INSTITUTIONAL_LOGIC = False

# Define public API
__all__ = [
    "calculate_position_size", 
    "get_dynamic_risk_params"
]

if HAS_INSTITUTIONAL_LOGIC:
    __all__ += ["apply_risk_filter", "RiskResult"]