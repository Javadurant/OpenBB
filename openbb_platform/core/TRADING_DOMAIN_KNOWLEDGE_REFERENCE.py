"""
TRADING_DOMAIN_KNOWLEDGE_REFERENCE.py v2.0
═══════════════════════════════════════════════════════════════════════════════
AUTHORITATIVE SOURCE FOR HARMONIC RATIOS, ICHIMOKU, ELLIOTT WAVE, AND INDICATORS
Primary Source: Scott M. Carney (Harmonic Trading Vol 1-3)
Secondary: Goichi Hosoda (Ichimoku), Prechter & Frost (Elliott Wave)
Audit: Paez, Karpathy, Selivanov, Nilsson
═══════════════════════════════════════════════════════════════════════════════
"""

# ─── HARMONIC PATTERN RATIOS (XABCD) ──────────────────────────────────────────

GARTLEY = {
    "B_retraces_XA": {"ideal": 0.618, "tolerance": 0.019},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [1.130, 1.618]},
    "D_retraces_XA": {"ideal": 0.786, "tolerance": 0.001},
    "ABCD_type": ["AB=CD", "0.618 AB=CD", "1.27 AB=CD"]
}

BAT = {
    "B_retraces_XA": {"range": [0.382, 0.500]},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [1.618, 2.618]},
    "D_retraces_XA": {"ideal": 0.886, "tolerance": 0.001},
    "ABCD_type": ["AB=CD", "1.618 AB=CD"]
}

ALTERNATE_BAT = {
    "B_retraces_XA": {"max": 0.382, "tolerance_lower": 0.011},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [2.000, 3.618]},
    "D_retraces_XA": {"range": [0.886, 1.130]},
    "ABCD_type": ["1.618 AB=CD"]
}

CRAB = {
    "B_retraces_XA": {"range": [0.382, 0.618]},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [2.618, 3.618]},
    "D_extends_XA": {"ideal": 1.618, "tolerance": 0.001},
    "ABCD_type": ["AB=CD", "1.618 AB=CD"]
}

DEEP_CRAB = {
    "B_retraces_XA": {"ideal": 0.886, "tolerance_upper": 0.044, "tolerance_lower": 0.001},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [2.000, 3.618]},
    "D_extends_XA": {"range": [1.618, 1.902]}, # Includes 1.902 extreme variant
    "ABCD_type": ["AB=CD", "1.618 AB=CD"]
}

BUTTERFLY = {
    "B_retraces_XA": {"ideal": 0.786, "tolerance": 0.024},
    "C_retraces_AB": {"range": [0.382, 0.886]},
    "D_projection_via_CD_BC": {"range": [1.618, 2.240]},
    "D_extends_XA": {"values": [1.270, 1.414]},
    "ABCD_type": ["AB=CD", "1.27 AB=CD"]
}

# ─── HARMONIC PATTERN RATIOS (0XABC - SHARK) ──────────────────────────────────

SHARK = {
    "X_retraces_0A": {"range": [0.382, 0.886]},
    "A_extends_0X": {"range": [1.130, 1.618]},
    "B_extends_XA": {"range": [1.618, 2.240]},
    "C_vs_0X": {"values": [0.886, 1.130]}, # Entry point
    "NOTE": "Shark uses 0XABC labeling. No D point."
}

# ─── PRODUCTION GUARDS (Selivanov) ────────────────────────────────────────────

def safe_ratio(numerator: float, denominator: float) -> float:
    """Safe division for ratio calculation. Returns 0.0 on zero denominator."""
    if denominator == 0.0 or abs(denominator) < 1e-10:
        return 0.0
    return abs(numerator) / abs(denominator)