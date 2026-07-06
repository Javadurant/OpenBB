# pages/ai_trading_agent.py
# QuantEdge — Full-Stack AI Trading Agent
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# HARMONIC PATTERN RATIOS:
#   Source: Carney, Scott M. — Harmonic Trading Vol.1 (2010), Vol.2 (2010),
#           Vol.3 (2016). FT Press / HarmonicTrader.com
#   Audit:  Paez | Karpathy | Selivanov | Nilsson
#   7 corrections from prior version documented inline.
#
# ELLIOTT WAVE RATIOS:
#   Source: Frost, A.J. & Prechter, R.R. — Elliott Wave Principle (10th Ed.)
#           ISBN: 978-0-932750-75-4 | New Classics Library, 2005
#   All ratios match FIBONACCI_RATIO_TABLE in reference document exactly.
#
# INDICATOR PERIODS (RSI/MACD/BB/Stochastic/ATR/Ichimoku):
#   Source: User master prompt document — verbatim values used, none invented.
#
# NO st.set_page_config() — called once only in app.py per project rule.
# <- NEW [ai_trading_agent]: Full-stack AI trading agent page
import datetime
import logging
from translations import t, inject_rtl_css  # <- NEW [i18n]
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

# ── Project root on sys.path ───────────────────────────────────────────────
_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from openbb import obb as _obb
    _OBB_AVAILABLE: bool = True
except ImportError:
    _OBB_AVAILABLE = False

try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE: bool = True
except ImportError:
    _GROQ_AVAILABLE = False

logger = logging.getLogger("AITradingAgent")

# ═══════════════════════════════════════════════════════════════════════════
# API EXPORT FUNCTIONS — FastAPI Bridge to Backend
# ═══════════════════════════════════════════════════════════════════════════

def get_signals(symbol: str, timeframe: str = "daily") -> Dict[str, Any]:
    """Get trading signals for a symbol — called by FastAPI"""
    try:
        data = yf.download(symbol, period="1y", progress=False)
        if data.empty:
            return {"error": f"No data for {symbol}"}
        
        close = data['Close'].iloc[-1]
        ma50 = data['Close'].ewm(span=50).mean().iloc[-1]
        trend = "bullish" if close > ma50 else "bearish"
        
        return {
            "symbol": symbol,
            "signals": {
                "trend": trend,
                "strength": 65,
                "entry_points": [float(close * 0.99)],
                "stop_loss": float(close * 0.95),
                "take_profit": [float(close * 1.05), float(close * 1.10)],
            },
            "timestamp": datetime.datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"get_signals error: {e}")
        return {"error": str(e)}

def get_strategies(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """Get trading strategies — called by FastAPI"""
    if symbols is None:
        symbols = ["AAPL", "MSFT", "TSLA"]
    
    strategies = []
    for symbol in symbols:
        strategies.append({
            "symbol": symbol,
            "strategy": "Elliott Wave + Harmonic Pattern",
            "confidence": 75,
            "recommendation": "BUY",
        })
    
    return {"strategies": strategies, "timestamp": datetime.datetime.now().isoformat()}

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 0 — SAFE RATIO HELPER (mandatory guard per audit Section 12)
# Source: Carney audit — Selivanov implementation sign-off
# ═══════════════════════════════════════════════════════════════════════════

def safe_ratio(numerator: float, denominator: float) -> float:
    """
    Safe division for all pattern ratio calculations.
    Returns 0.0 when denominator is zero or near-zero.
    MANDATORY: called before every ratio computation per audit Section 12.
    """
    if abs(denominator) < 1e-10:
        return 0.0
    return abs(numerator) / abs(denominator)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — ELLIOTT WAVE FIBONACCI RATIOS
# Source: Frost & Prechter — Elliott Wave Principle (10th Ed.)
# ISBN: 978-0-932750-75-4 | New Classics Library, 2005
# Every value matches FIBONACCI_RATIO_TABLE in the reference document.
# ═══════════════════════════════════════════════════════════════════════════

# Wave 2 retracement of Wave 1 [PF] p.28
# Primary: 0.618 | Secondary: 0.500 | Tertiary: 0.382
# Valid range: 0.382–0.999 (any retracement < 1.000 is valid per Rule 1)
EW_W2_PRIMARY:     float = 0.618
EW_W2_SECONDARY:   float = 0.500
EW_W2_TERTIARY:    float = 0.382
EW_W2_RANGE_MIN:   float = 0.382   # lower bound of typical retracement
EW_W2_RANGE_MAX:   float = 0.999   # absolute max — Rule 1: never >= 1.000
EW_W2_TOLERANCE:   float = 0.020   # ±2% per FLOAT_COMPARISON_RULE in [PF]

# Wave 3 extension of Wave 1 [PF] pp.29–33
# Primary: 1.618 | Secondary: 2.618 | Tertiary: 4.236
EW_W3_PRIMARY:     float = 1.618
EW_W3_SECONDARY:   float = 2.618
EW_W3_TERTIARY:    float = 4.236
EW_W3_ALSO_VALID:  Tuple[float, ...] = (1.000, 2.000)
EW_W3_TOLERANCE:   float = 0.020

# Wave 4 retracement of Wave 3 [PF] pp.34–37
# Primary: 0.382 | Secondary: 0.236 | Tertiary: 0.500
# Must not violate Rule 3 (no overlap with Wave 1 territory)
EW_W4_PRIMARY:     float = 0.382
EW_W4_SECONDARY:   float = 0.236
EW_W4_RANGE_MIN:   float = 0.236
EW_W4_RANGE_MAX:   float = 0.500
EW_W4_TOLERANCE:   float = 0.020

# Wave 5 relationships [PF] pp.38–42
# Primary: equality with Wave 1 (1.000 × Wave 1 length)
# Secondary: 0.618 × (Wave 1 start to Wave 3 end distance)
# Extended: 1.618 × Wave 1 length
EW_W5_EQUALITY:    float = 1.000
EW_W5_FIBONACCI:   float = 0.618
EW_W5_EXTENDED:    float = 1.618
EW_W5_TOLERANCE:   float = 0.020

# ZigZag minimum swing — user master prompt document (5%)
ZIGZAG_MIN_SWING:  float = 0.050

# Fibonacci retracement and extension levels
# Source: [PF] — standard Fibonacci sequence
FIB_RETRACE: Tuple[float, ...] = (0.236, 0.382, 0.500, 0.618, 0.786)
FIB_EXTEND:  Tuple[float, ...] = (1.272, 1.618, 2.618, 4.236)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — HARMONIC PATTERN RATIOS (10 PATTERNS)
# Primary Source: Carney Vol.1 (2010), Vol.2 (2010), Vol.3 (2016)
# Audit: Paez | Karpathy | Selivanov | Nilsson
# 7 corrections from prior version — all documented in audit Section 11
#
# STRUCTURE per pattern:
#   "B_retraces_XA"        → AB_len / XA_len
#   "C_retraces_AB"        → BC_len / AB_len
#   "D_projection_CD_BC"   → CD_len / BC_len
#   "D_constraint"         → abs(D - X) / XA_len (or extension variant)
#   "D_is_extension"       → True if D goes beyond X (ratio > 1.0)
#   "ABCD_types"           → valid AB=CD multipliers
#   Each sub-dict has: ideal, valid_range, tolerance, source
# ═══════════════════════════════════════════════════════════════════════════

# ── Pattern 1: GARTLEY ─────────────────────────────────────────────────────
# Source: [CV1] Chapter 5, pp.89–124 | [CV3] Chapter 4
# Corrections applied: B/XA wrong field in user extraction (now correct)
#   XA=0.786 clarified as D-point retracement formula not XA leg value
HARMONIC_GARTLEY: Dict[str, Any] = {
    "name": "GARTLEY",
    "source": "[CV1] p.92–98 | [CV3] p.44–51",
    # B: 0.618 XA ±3% → ±0.019 [CV1] p.92
    "B_of_XA": {
        "ideal": 0.618, "tol": 0.019,
        "lo": 0.599, "hi": 0.637,
    },
    # C: 0.382 OR 0.886 AB [CV1] p.95
    # CORRECTED: user placed CD extension values here — moved to D_proj below
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    # CD/BC: 1.130–1.618 [CV1] p.96 | [CV3] p.47
    # CORRECTED: user had these values under BC field — correctly placed here
    "D_proj_CD_BC": {
        "lo": 1.130, "hi": 1.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    # AB=CD types: AB=CD or 1.27 AB=CD [CV1] p.97
    "ABCD_types": (1.000, 1.270),
    "ABCD_tol": 0.020,
    # D primary constraint: XD/XA = 0.786 [CV1] p.98
    # CORRECTED: "XA=0.786" means D retraces 78.6% of XA from X — not XA equals 0.786
    "D_constraint": {
        "ideal": 0.786, "tol": 0.024,  # FIXED now ±3%,
        "lo": 0.785, "hi": 0.787,
    },
    "D_is_extension": False,   # D retraces (ratio < 1.0)
}

# ── Pattern 2: DEEP GARTLEY ────────────────────────────────────────────────
# Source: [CV3] Chapter 4
# CORRECTED: user listed D = "0.786–0.886" as range.
#   [CV3] defines Deep Gartley STRICTLY at 0.886. 0.786 = standard Gartley.
HARMONIC_DEEP_GARTLEY: Dict[str, Any] = {
    "name": "DEEP_GARTLEY",
    "source": "[CV3] Chapter 4",
    "B_of_XA": {
        "ideal": 0.618, "tol": 0.019,
        "lo": 0.599, "hi": 0.637,
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    # Deeper CD range than standard Gartley [CV3] Chapter 4
    "D_proj_CD_BC": {
        "lo": 1.618, "hi": 2.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000,),   # Standard AB=CD only — no 1.27 variant [CV3]
    "ABCD_tol": 0.020,
    # D constraint: STRICT 0.886 [CV3] — NOT a range with 0.786
    "D_constraint": {
        "ideal": 0.886, "tol": 0.027,  # FIXED now ±3%,
        "lo": 0.885, "hi": 0.887,
    },
    "D_is_extension": False,
}

# ── Pattern 3: BAT ─────────────────────────────────────────────────────────
# Source: [CV2] p.67–75 | [CV3] Chapter 5
# Audit: ✅ All ratios confirmed. No corrections required.
HARMONIC_BAT: Dict[str, Any] = {
    "name": "BAT",
    "source": "[CV2] p.67–75 | [CV3] p.73–78",
    # B: 0.382–0.500 XA [CV2] p.67
    # Critical distinguisher from Gartley (0.618). If B > 0.500 → NOT a Bat.
    "B_of_XA": {
        "lo": 0.382, "hi": 0.500, "tol": 0.02,  # FIXED now ±0.02,
        "range_mode": True,   # any value in range (not discrete values)
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    "D_proj_CD_BC": {
        "lo": 1.618, "hi": 2.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000, 1.618),
    "ABCD_tol": 0.020,
    # D constraint: 0.886 XA [CV2] p.72 — primary defining ratio of Bat
    "D_constraint": {
        "ideal": 0.886, "tol": 0.027,  # FIXED now ±3%,
        "lo": 0.885, "hi": 0.887,
    },
    "D_is_extension": False,
}

# ── Pattern 4: ALTERNATE BAT ───────────────────────────────────────────────
# Source: [CV3] Chapter 5
# CORRECTED (2): CD field and ABCD type
#   CD 2.0–3.618 was in BC field in user extraction — moved here
#   ABCD type: ONLY 1.618 AB=CD per [CV3]. Standard AB=CD does NOT qualify.
HARMONIC_ALT_BAT: Dict[str, Any] = {
    "name": "ALTERNATE_BAT",
    "source": "[CV3] Chapter 5",
    # B: 0.382 MAX (upper limit not midpoint) [CV3]
    # -3% tolerance = lower bound 0.382 - 0.011 = 0.371
    # upper bound = 0.382 + 0.001 (near-zero — 0.382 is the MAX)
    "B_of_XA": {
        "ideal": 0.382, "tol_lower": 0.011, "tol_upper": 0.001,
        "lo": 0.371, "hi": 0.383,
        "max_mode": True,   # 0.382 is strict upper limit
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    # CORRECTED: user placed 2.0–3.618 under BC — correctly placed here [CV3]
    "D_proj_CD_BC": {
        "lo": 2.000, "hi": 3.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    # CORRECTED: ONLY 1.618 AB=CD [CV3]. Standard AB=CD = NOT Alternate Bat.
    "ABCD_types": (1.618,),
    "ABCD_tol": 0.020,
    # D constraint: 0.886–1.130 XA range [CV3]
    "D_constraint": {
        "lo": 0.886, "hi": 1.130, "tol": 0.02,  # FIXED now ±0.02,
        "range_mode": True,
    },
    "D_is_extension": False,   # stays inside XA at 0.886; at 1.13 = mild ext
}

# ── Pattern 5: CRAB ────────────────────────────────────────────────────────
# Source: [CV1] Chapter 7, pp.149–178 | [CV3] Chapter 6
# Audit: ✅ All ratios confirmed. No corrections required.
# NOTE: D EXTENDS beyond X. D_is_extension = True. XD/XA > 1.0.
HARMONIC_CRAB: Dict[str, Any] = {
    "name": "CRAB",
    "source": "[CV1] p.152–161 | [CV3] Chapter 6",
    # B: 0.382–0.618 XA [CV1] p.152
    "B_of_XA": {
        "lo": 0.382, "hi": 0.618, "tol": 0.02,  # FIXED now ±0.02,
        "range_mode": True,
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    # CD/BC: 2.618–3.618 [CV1] p.155 — deepest extension of all XABCD patterns
    "D_proj_CD_BC": {
        "lo": 2.618, "hi": 3.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000, 1.618),
    "ABCD_tol": 0.020,
    # D extends 1.618 XA BEYOND X [CV1] p.157
    "D_constraint": {
        "ideal": 1.618, "tol": 0.049,  # FIXED now ±3%,
        "lo": 1.617, "hi": 1.619,
    },
    "D_is_extension": True,   # D has gone PAST X's original price
}

# ── Pattern 6: DEEP CRAB ───────────────────────────────────────────────────
# Source: [CV3] Chapter 6
# NUANCED: B = 0.886 +5% upper bound per [CV3].
#   Upper: 0.886 × 1.05 = 0.930. Lower: 0.885 (near 0.886 floor).
#   Sole distinguisher from standard Crab (B = 0.382–0.618).
HARMONIC_DEEP_CRAB: Dict[str, Any] = {
    "name": "DEEP_CRAB",
    "source": "[CV3] Chapter 6",
    # B: 0.886 with +5% upper tolerance per [CV3]
    # Lower bound tight (0.885), upper = 0.886 × 1.05 = 0.930
    "B_of_XA": {
        "ideal": 0.886, "tol_upper": 0.044, "tol_lower": 0.001,
        "lo": 0.885, "hi": 0.930,
        "upper_tolerance_mode": True,
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    "D_proj_CD_BC": {
        "lo": 2.000, "hi": 3.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000, 1.618),
    "ABCD_tol": 0.020,
    # D extends 1.618 XA [CV3] — same D-point as standard Crab
    # B point (0.886) is the SOLE distinguisher
    "D_constraint": {
        "ideal": 1.618, "tol": 0.049,  # FIXED now ±3%,
        "lo": 1.617, "hi": 1.619,
    },
    "D_is_extension": True,
}

# ── Pattern 7: DEEP CRAB 1.902 ─────────────────────────────────────────────
# Source: [CV3] Chapter 6 — extreme variant
# 1.902 = √Φ × Φ = √1.618 × 1.618 ≈ 1.272 × 1.618 ≈ 1.902
# Karpathy note: 1.902 is a documented Fibonacci derived ratio per [CV3]
HARMONIC_DEEP_CRAB_1902: Dict[str, Any] = {
    "name": "DEEP_CRAB_1902",
    "source": "[CV3] Chapter 6",
    # B same as Deep Crab
    "B_of_XA": {
        "ideal": 0.886, "tol_upper": 0.044, "tol_lower": 0.001,
        "lo": 0.885, "hi": 0.930,
        "upper_tolerance_mode": True,
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    "D_proj_CD_BC": {
        "lo": 2.000, "hi": 3.618, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000, 1.618),
    "ABCD_tol": 0.020,
    # D extends 1.618–1.902 XA range [CV3]
    # 1.902 = maximum extreme of Deep Crab family
    "D_constraint": {
        "lo": 1.618, "hi": 1.902, "tol": 0.02,  # FIXED now ±0.02,
        "range_mode": True,
    },
    "D_is_extension": True,
}

# ── Pattern 8: BUTTERFLY ───────────────────────────────────────────────────
# Source: [CV1] Chapter 6, pp.125–148 | [CV3] Chapter 7
# Audit: ✅ All ratios confirmed. No corrections required.
# NOTE: D extends beyond X. Primary 1.27, extreme variant 1.414 [CV1] p.133.
HARMONIC_BUTTERFLY: Dict[str, Any] = {
    "name": "BUTTERFLY",
    "source": "[CV1] p.128–137 | [CV3] Chapter 7",
    # B: 0.786 XA ±3% [CV1] p.128 → ±3% of 0.786 = ±0.02358 ≈ ±0.024
    "B_of_XA": {
        "ideal": 0.786, "tol": 0.024,
        "lo": 0.762, "hi": 0.810,
    },
    "C_of_AB": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now RANGE ±0.02,
    },
    # CD/BC: 1.618–2.24 [CV3] Chapter 7 refinement
    "D_proj_CD_BC": {
        "lo": 1.618, "hi": 2.240, "tol": 0.02,  # FIXED now ±0.02,
    },
    "ABCD_types": (1.000, 1.270),
    "ABCD_tol": 0.020,
    # D extends XA: primary 1.270, extreme variant 1.414 [CV1] p.133
    "D_constraint": {
        "lo": 1.250, "hi": 1.434, "tol": 0.02,  # FIXED now range,
        "discrete_mode": True,
    },
    "D_is_extension": True,
}

# ── Pattern 9: SHARK (0XABC labeling — COMPLETELY SEPARATE) ───────────────
# Source: [CV3] Chapter 8
# CRITICAL: Shark uses 0, X, A, B, C labels — NOT XABCD.
# There is NO D point. C is the completion and entry point.
# Must be detected by a separate function (detect_shark).
# Label mapping (user notation → Carney [CV3]):
#   User "B retraces XA"    → [CV3]: X retraces 0A leg
#   User "C extends AB"     → [CV3]: A leg vs 0X leg
#   User "D = 0.886–1.130"  → [CV3]: C point vs 0X (C IS the entry)
HARMONIC_SHARK: Dict[str, Any] = {
    "name": "SHARK",
    "source": "[CV3] Chapter 8",
    "labeling": "0XABC",
    "entry_point": "C",   # NO D point — C is the completion
    # X retraces 0A: 0.382–0.886 [CV3] (user's "B retraces XA" corrected label)
    "X_of_0A": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now ±0.02,
        "formula": "leg_XA / leg_0A",
    },
    # A vs 0X: 1.130–1.618 [CV3] (user's "C extends AB" corrected label)
    "A_of_0X": {
        "lo": 1.130, "hi": 1.618, "tol": 0.02,  # FIXED now ±0.02,
        "formula": "leg_0A / leg_0X",
    },
    # B extends XA: 1.618–2.240 [CV3]
    "B_of_XA_ext": {
        "lo": 1.618, "hi": 2.240, "tol": 0.02,  # FIXED now ±0.02,
        "formula": "leg_AB / leg_XA",
    },
    # C vs 0X: 0.886 OR 1.130 — THIS IS THE ENTRY POINT [CV3]
    "C_of_0X": {
        "values": (0.886, 1.130), "tol": 0.027,  # FIXED now ±3%,
        "formula": "leg_0C / leg_0X",
    },
    # PRO_ABC: AB=CD confirmation values [CV3]
    "PRO_ABC": (1.000, 1.270, 1.618),
    "PRO_ABC_tol": 0.020,
}

# ── Pattern 10: RECIPROCAL AB=CD ───────────────────────────────────────────
# Source: [CV3] Chapter 9
# CORRECTED (2): base legs missing in user extraction — added explicitly.
#   C: 1.13–3.618 extension of AB leg (not XA, not BC)
#   D: 0.382–0.886 retracement of BC leg (not XA)
# No XA D-point constraint — uses separate detection logic.
HARMONIC_RECIP_ABCD: Dict[str, Any] = {
    "name": "RECIPROCAL_ABCD",
    "source": "[CV3] Chapter 9",
    # C extends AB: 1.130–3.618 [CV3] (CORRECTED: base leg = AB, not XA)
    "C_extends_AB": {
        "lo": 1.130, "hi": 3.618, "tol": 0.02,  # FIXED now ±0.02,
        "formula": "BC_len / AB_len",
    },
    # D retraces BC: 0.382–0.886 [CV3] (CORRECTED: base leg = BC, not XA)
    "D_retraces_BC": {
        "lo": 0.382, "hi": 0.886, "tol": 0.02,  # FIXED now ±0.02,
        "formula": "CD_len / BC_len",
    },
    # ABCD types: 1.27 or 1.618 AB=CD only [CV3]
    "ABCD_types": (1.270, 1.618),
    "ABCD_tol": 0.020,
    "PRO_ABC": (1.000, 1.270, 1.618),
}

# ── Pattern 11: CYPHER ─────────────────────────────────────────────────────
# Source: Carney *Harmonic Trading* / [CV3]. ADDED [H4].
# CRITICAL EXCEPTION: C is an EXTENSION of XA (XC/XA), NOT a retracement of AB.
# B retraces XA (0.382-0.618); D completes at the 0.786 retracement of the XC leg.
HARMONIC_CYPHER: Dict[str, Any] = {
    "name": "CYPHER",
    "source": "[CV3] — Cypher",
    "B_of_XA": {"lo": 0.382, "hi": 0.618, "tol": 0.02, "formula": "AB_len / XA_len"},
    # PARITY: TradingFinder HP.XABCD Cypher uses C-of-XA window 1.13-1.414 (vs Carney
    # 1.272-1.414). Matched to the TradingView script per user decision so we draw the
    # same Cyphers it draws. See ta_engine/golden/cypher_btc_tradingfinder.json.
    "C_of_XA": {"lo": 1.130, "hi": 1.414, "tol": 0.02, "formula": "XC_len / XA_len (EXTENSION)"},
    "D_of_XC": {"ideal": 0.786, "tol": 0.024, "formula": "CD_len / XC_len"},
}

# ── Pattern 12: 5-0 ────────────────────────────────────────────────────────
# Source: Carney *Harmonic Trading Vol.2* / [CV3]. ADDED [H4].
# Reciprocal: AB is a large leg of XA (1.13-1.618); BC extends AB (1.618-2.24);
# D completes at the 0.50 retracement of BC (the defining 5-0 ratio).
HARMONIC_FIVE_ZERO: Dict[str, Any] = {
    "name": "FIVE_ZERO",
    "source": "[CV3] — 5-0",
    "AB_of_XA": {"lo": 1.130, "hi": 1.618, "tol": 0.02, "formula": "AB_len / XA_len"},
    "BC_of_AB": {"lo": 1.618, "hi": 2.240, "tol": 0.02, "formula": "BC_len / AB_len"},
    "D_of_BC":  {"ideal": 0.500, "tol": 0.020, "formula": "CD_len / BC_len"},
}

# ── Pattern 13: THREE DRIVES ───────────────────────────────────────────────
# Source: Carney / [CV3]. ADDED [H4].
# Three symmetric drives separated by two pullbacks. Pullbacks retrace 0.618-0.786
# of the prior drive; each drive extends 1.13-1.618 of the prior pullback; the three
# drives are roughly equal (symmetry). Completes AT drive 3 — a REAL pivot, not a
# projection — so its D is inherently present in the detection window.
HARMONIC_THREE_DRIVES: Dict[str, Any] = {
    "name": "THREE_DRIVES",
    "source": "[CV3] — Three Drives",
    "pullback":  {"lo": 0.618, "hi": 0.786, "tol": 0.03},
    "drive_ext": {"lo": 1.130, "hi": 1.618, "tol": 0.03},
    "symmetry_tol": 0.30,   # drives 2 & 3 within ±30% of drive 1 length
}

# Master list of the 8 XABCD patterns (used by shared detector)
XABCD_PATTERNS: Tuple[Dict[str, Any], ...] = (
    HARMONIC_GARTLEY,
    HARMONIC_DEEP_GARTLEY,
    HARMONIC_BAT,
    HARMONIC_ALT_BAT,
    HARMONIC_CRAB,
    HARMONIC_DEEP_CRAB,
    HARMONIC_DEEP_CRAB_1902,
    HARMONIC_BUTTERFLY,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — INDICATOR PERIODS & CONSTANTS
# Source: User master prompt document — verbatim, none invented
# ═══════════════════════════════════════════════════════════════════════════

# Ichimoku — user document
ICH_TENKAN:   int = 9
ICH_KIJUN:    int = 26
ICH_SENKOU_B: int = 52
ICH_SHIFT:    int = 26

# RSI — user document
RSI_PERIOD:     int   = 14
RSI_OVERBOUGHT: float = 70.0
RSI_OVERSOLD:   float = 30.0

# MACD — user document
MACD_FAST:   int = 12
MACD_SLOW:   int = 26
MACD_SIGNAL: int = 9

# Bollinger Bands — user document
BB_PERIOD:  int   = 20
BB_STD_DEV: float = 2.0

# Moving average periods — user document
MA_PERIODS: Tuple[int, ...] = (9, 21, 50, 200)

# Stochastic — user document
STOCH_K:  int   = 14
STOCH_D:  int   = 3
STOCH_OB: float = 80.0
STOCH_OS: float = 20.0

# ATR — user document
ATR_PERIOD:          int   = 14

# ── BOLLINGER BANDS [Bollinger 1983] ────────────────────────────────────────
BB_PERIOD:           int   = 20        # <- ADDED: Standard Bollinger Bands period
BB_STDDEV:           float = 2.0       # <- ADDED: Standard deviation multiplier [Bollinger 1983]

# ── ADX (Average Directional Index) [Wilder 1978] ──────────────────────────
ADX_PERIOD:          int   = 14        # <- Wilder default period
ADX_THRESHOLD:       float = 25.0      # <- ADDED: Institutional threshold for "strong trend" [Bloomberg]
ATR_STOP_MULTIPLIER: float = 1.5   # 1.5 × ATR — user document

# PRZ confidence — user document (method agreement count → confidence %)
PRZ_CONFIDENCE: Dict[int, float] = {1: 0.60, 2: 0.75, 3: 0.85, 4: 0.85, 5: 0.85, 6: 0.85}

# Staged exit — user document
EXIT_T1_PCT: float = 0.50
EXIT_T2_PCT: float = 0.30
EXIT_T3_PCT: float = 0.20

# Minimum R:R — user document
MIN_RR_RATIO: float = 2.0

# Harmonic pattern tolerance levels — user document (pattern tolerance)
TOLERANCE_PERFECT: float = 0.010   # ±1% → +25 confluence pts
TOLERANCE_GOOD:    float = 0.020   # ±2% → +20 pts
TOLERANCE_FAIR:    float = 0.030   # ±3% → +15 pts

CACHE_TTL:   int = 300
GROQ_MODEL:  str = "llama-3.3-70b-versatile"

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — CONFLUENCE POINT VALUES
# Source: User master prompt document — every value verbatim
# ═══════════════════════════════════════════════════════════════════════════

CS_EW_W3_COMPLETE:      int =  20
CS_EW_W5_REVERSAL:      int = -25
CS_EW_ABC_COMPLETE:     int =  15
CS_HARM_PERFECT:        int =  25
CS_HARM_GOOD:           int =  20
CS_HARM_FAIR:           int =  15
CS_HARM_FAILURE:        int = -20
CS_ICH_PRICE_ABOVE:     int =  20
CS_ICH_PRICE_BELOW:     int = -20
CS_ICH_CLOUD_THICK:     int =  20
CS_ICH_CLOUD_THIN:      int =   5
CS_ICH_CROSS_ABOVE:     int =  15
CS_ICH_CROSS_BELOW:     int = -15
CS_ICH_CHIKOU_BULL:     int =  10
CS_ICH_CHIKOU_BEAR:     int = -10
CS_RSI_OVERSOLD_UP:     int =  10
CS_RSI_OB_DOWN:         int = -10
CS_RSI_BULL_DIV:        int =  15
CS_RSI_BEAR_DIV:        int = -15
CS_MACD_CROSS_BULL:     int =  15
CS_MACD_CROSS_BEAR:     int = -15
CS_MACD_HIST_EXP_UP:    int =  10
CS_MACD_HIST_CONTR_UP:  int = -10
CS_MACD_BULL_DIV:       int =  20
CS_MACD_BEAR_DIV:       int = -20
CS_BB_BOUNCE_LOWER:     int =  15
CS_BB_BOUNCE_UPPER:     int = -15
CS_BB_EXPANDING:        int =  10
CS_BB_CONTRACTING:      int =   5
CS_MA_ABOVE_200:        int =  20
CS_MA_BELOW_200:        int = -20
CS_MA_BULL_ALIGN:       int =  15
CS_MA_BEAR_ALIGN:       int = -15
CS_MA_GOLDEN_CROSS:     int =  25
CS_MA_DEATH_CROSS:      int = -25
CS_STOCH_CROSS_UP_OS:   int =  15
CS_STOCH_CROSS_DN_OB:   int = -15
CS_STOCH_BULL_DIV:      int =  20
CS_STOCH_BEAR_DIV:      int = -20
CS_ATR_EXPANDING:       int =  10
CS_ATR_CONTRACTING:     int =  -5
CS_ATR_52W_HIGH:        int =  15
CS_OBV_BULL:            int =  15
CS_OBV_HIDDEN_BULL:     int =  20
CS_OBV_HIDDEN_BEAR:     int = -20
CS_VWAP_BREAK_UP:       int =  10
CS_VWAP_BOUNCE:         int =  10
CS_VWAP_BREAK_DOWN:     int = -15
CS_INST_INC_HIGH:       int =  20
CS_INST_INC_LOW:        int =  15
CS_INST_DEC_LOW:        int = -10
CS_INST_DEC_HIGH:       int = -20
CS_INSIDER_BUY:         int =  20
CS_INSIDER_SELL:        int = -25
CS_BLOCK_BUY:           int =  20
CS_BLOCK_SELL:          int = -20
CS_SENTIMENT_BULL:      int =  15
CS_SENTIMENT_BEAR:      int = -10
CS_MACRO_GOLDILOCKS:    int =  15
CS_MACRO_STAGFLATION:   int = -20

# Macro quadrant definitions — user document
MACRO_QUADRANTS: Dict[str, Dict[str, str]] = {
    "Q1": {"label": "GOLDILOCKS",  "growth": "↑", "inflation": "↓",
           "color": "#00FF88", "strategy": "Aggressive long equities, growth stocks favored"},
    "Q2": {"label": "RISING RATES","growth": "↑", "inflation": "↑",
           "color": "#FFD700", "strategy": "Buy value stocks, shorter duration bonds"},
    "Q3": {"label": "DEFLATION",   "growth": "↓", "inflation": "↓",
           "color": "#00E5FF", "strategy": "Buy long-duration bonds, treasuries, gold"},
    "Q4": {"label": "STAGFLATION", "growth": "↓", "inflation": "↑",
           "color": "#FF5252", "strategy": "Avoid equities, buy gold, commodities"},
}

MAJOR_FUNDS: Dict[str, Dict[str, Any]] = {
    "Berkshire Hathaway":    {"accuracy": 0.68, "style": "VALUE",      "holding_yrs": 5},
    "Oaktree Capital":       {"accuracy": 0.72, "style": "CONTRARIAN", "holding_yrs": 5},
    "Renaissance Tech":      {"accuracy": 0.75, "style": "QUANT",      "holding_yrs": 1},
    "ARK Invest":            {"accuracy": 0.62, "style": "GROWTH",     "holding_yrs": 3},
    "Citadel":               {"accuracy": 0.68, "style": "MULTI",      "holding_yrs": 1},
    "ValueAct Capital":      {"accuracy": 0.70, "style": "ACTIVIST",   "holding_yrs": 4},
    "Elliott Management":    {"accuracy": 0.72, "style": "ACTIVIST",   "holding_yrs": 3},
    "Point72":               {"accuracy": 0.65, "style": "MULTI",      "holding_yrs": 2},
    "Tiger Global":          {"accuracy": 0.58, "style": "GROWTH",     "holding_yrs": 2},
    "Millennium Mgmt":       {"accuracy": 0.60, "style": "MULTI",      "holding_yrs": 1},
}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 — TYPED RESULT CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════

class HarmonicResult(TypedDict):
    pattern:    str
    found:      bool
    quality:    str
    worst_dev:  float
    conf_pts:   int
    prz_low:    float
    prz_high:   float
    d_price:    float
    ratios:     Dict[str, float]


class WaveResult(TypedDict):
    swings_found: int
    wave_phase:   str
    conf_pts:     int
    fib_levels:   Dict[str, float]
    swing_prices: List[float]


class IchimokuResult(TypedDict):
    tenkan:        float
    kijun:         float
    senkou_a:      float
    senkou_b:      float
    cloud_top:     float
    cloud_bot:     float
    cloud_color:   str
    cloud_thick:   bool
    price_vs_cloud: str
    chikou_signal: str
    tk_cross:      str
    conf_pts:      int


class PRZResult(TypedDict):
    price_zone_low:  float
    price_zone_high: float
    methods_count:   int
    confidence:      float
    methods:         List[str]
    target_1:        float
    target_2:        float
    target_3:        float
    stop_loss:       float
    entry:           float
    rr_ratio:        float
    rr_valid:        bool


class MasterSignal(TypedDict):
    ticker:           str
    timestamp:        str
    signal:           str
    confluence_score: int
    confidence_pct:   float
    elliott_pts:      int
    harmonic_pts:     int
    ichimoku_pts:     int
    indicator_pts:    int
    sentiment_pts:    int
    institutional_pts: int
    macro_pts:        int
    prz:              Optional[PRZResult]
    macro_quadrant:   str
    risk_warnings:    List[str]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 — DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════

# ── Exchange-native data feed: EOD Historical Data (EODHD) ───────────────────
# EODHD sources OHLCV directly from the listing exchange, so it matches the feed
# TradingView uses (verified pivot-exact vs OMXSTO on SEB-A.ST / VOLV-B.ST). This
# removes the sub-unit yfinance drift that broke fine harmonic pivots. Generic:
# covers global equities, ETFs, funds, indices, crypto & FX. Raw (unadjusted) close.
def _dotenv_get(name: str):
    import os, pathlib
    v = os.getenv(name)
    if v:
        return v
    for p in (pathlib.Path(".env"), pathlib.Path(__file__).resolve().parent.parent / ".env"):
        try:
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return None


def _eodhd_symbol(ticker: str) -> str:
    """Map a yfinance-style ticker to EODHD's SYMBOL.EXCHANGE format."""
    t = ticker.strip().upper()
    if "." in t:
        return t                                   # already exchange-suffixed (VOLV-B.ST, BMW.DE)
    if t.endswith("-USD") or t.endswith("USDT"):
        return t.replace("-USD", "") + "-USD.CC"   # crypto (best-effort)
    if "=X" in t:
        return t.replace("=X", "") + ".FOREX"      # FX (best-effort)
    return t + ".US"                               # bare US equity / ETF


def _fetch_eodhd(ticker: str, start: str, period: str = "d") -> pd.DataFrame:
    """Exchange-native OHLCV from EODHD. period in {'d','w','m'}. Empty df on any
    failure so callers transparently fall back to the OpenBB/yfinance chain."""
    key = _dotenv_get("EODHD_API_KEY")
    if not key:
        return pd.DataFrame()
    try:
        import urllib.request, urllib.parse, json as _json
        sym = urllib.parse.quote(_eodhd_symbol(ticker))
        url = (f"https://eodhd.com/api/eod/{sym}?api_token={key}&fmt=json"
               f"&from={start}&period={period}")
        with urllib.request.urlopen(url, timeout=15) as r:
            rows = _json.loads(r.read())
        if not rows or not isinstance(rows, list):
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if df.empty or "close" not in df:
            return pd.DataFrame()
        df.index = pd.to_datetime(df["date"])
        for c in ("open", "high", "low", "close", "volume"):
            if c not in df:
                df[c] = float("nan")
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        return df
    except Exception as exc:
        logger.warning("EODHD [%s]: %s", ticker, exc)
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def _fetch_ohlcv(ticker: str, years: int = 2) -> pd.DataFrame:
    """
    Fetches daily OHLCV. Tries OpenBB 4.x first, falls back to yfinance.
    Columns lowercased. DatetimeIndex returned.
    """
    start = (datetime.date.today() - datetime.timedelta(days=365 * years)).strftime("%Y-%m-%d")
    df = _fetch_eodhd(ticker, start, "d")          # <- exchange-native primary (matches TradingView)
    if not df.empty:
        return df
    if _OBB_AVAILABLE:
        try:
            res = _obb.equity.price.historical(ticker, start_date=start, provider="yfinance")
            df  = res.to_df()
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df.index   = pd.to_datetime(df.index)
                return df
        except Exception as exc:
            logger.warning("OpenBB [%s]: %s", ticker, exc)
    # FIXED [SEB-A.ST 404]: a valid symbol (SEB-A.ST returns 250 rows when fetched
    # standalone) was hard-404ing because this path fires TWO back-to-back Yahoo
    # requests (OpenBB provider=yfinance above, then this fallback) with no delay
    # and no retry, returning empty on the first miss. Yahoo rate-limits rapid
    # bursts, so the second hit returns EMPTY for a good ticker. Resilient chain:
    # history -> backoff retry -> yf.download (a different Yahoo endpoint).
    import time as _time
    for attempt in range(3):
        try:
            # PARITY [harmonic]: auto_adjust=False -> RAW (unadjusted) to match TradingView's
            # OMXSTO feed. auto_adjust=True gave SEB ~170 in Oct'25; TradingView shows ~181
            # (= our Cypher D 180.89). Verified empirically 2026-07-01.
            df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df.index   = pd.to_datetime(df.index)
                return df
        except Exception as exc:  # transient (rate-limit / timeout) — retry
            logger.warning("yfinance history [%s] attempt %d: %s", ticker, attempt + 1, exc)
        _time.sleep(0.6 * (attempt + 1))   # linear backoff between Yahoo hits
    try:
        df = yf.download(ticker, start=start, auto_adjust=False, progress=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):   # yf.download may return MultiIndex cols
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            df.index   = pd.to_datetime(df.index)
            return df
    except Exception as exc:
        logger.error("yfinance download [%s]: %s", ticker, exc)
    logger.error("yfinance [%s]: no data after retries + download fallback", ticker)
    return pd.DataFrame()


_TF_YF = {  # <- NEW [H-MTF]: (period, interval) per timeframe for yfinance
    "hourly":  ("3mo", "1h"),   # <- NEW [H-MTF-2]: intraday hourly candles
    "weekly":  ("5y",  "1wk"),
    "monthly": ("max", "1mo"),
}


def _fetch_ohlcv_tf(ticker: str, timeframe: str = "daily") -> pd.DataFrame:
    """Fetch OHLCV at the requested timeframe.  # <- NEW [H-MTF]

    'daily' reuses _fetch_ohlcv (OpenBB -> yfinance, ~2y). 'weekly'/'monthly' use
    yfinance period+interval. Returns lowercased columns + DatetimeIndex (empty df on failure).
    A harmonic pattern is scale-relative, so each timeframe is a distinct analysis.
    """
    tf = (timeframe or "daily").lower()
    if tf == "daily" or tf not in _TF_YF:
        return _fetch_ohlcv(ticker, years=2)
    # exchange-native primary for weekly/monthly (EODHD supports period w/m directly).
    _eod_p = {"weekly": "w", "monthly": "m"}.get(tf)
    if _eod_p:
        _start = (datetime.date.today() - datetime.timedelta(days=365 * 6)).strftime("%Y-%m-%d")
        _edf = _fetch_eodhd(ticker, _start, _eod_p)
        if not _edf.empty:
            return _edf
    period, interval = _TF_YF[tf]
    # FIXED [SEB-A.ST 404]: same Yahoo rate-limit resilience as _fetch_ohlcv —
    # retry with backoff, then fall back to yf.download before giving up.
    import time as _time
    for attempt in range(3):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df.index   = pd.to_datetime(df.index)
                return df
        except Exception as exc:
            logger.warning("yfinance tf history [%s/%s] attempt %d: %s", ticker, tf, attempt + 1, exc)
        _time.sleep(0.6 * (attempt + 1))
    try:
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            df.index   = pd.to_datetime(df.index)
            return df
    except Exception as exc:
        logger.error("yfinance tf download [%s/%s]: %s", ticker, tf, exc)
    logger.error("yfinance tf [%s/%s]: no data after retries + download fallback", ticker, tf)
    return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def _fetch_info(ticker: str) -> Dict[str, Any]:
    """Fetches fundamental info via yfinance."""
    try:
        info = yf.Ticker(ticker).info
        if not info or len(info) < 5:
            return {}
        return {
            "name":           info.get("longName") or info.get("shortName") or ticker,
            "sector":         info.get("sector", "Unknown"),
            "industry":       info.get("industry", "Unknown"),
            "market_cap":     info.get("marketCap"),
            "current_price":  info.get("currentPrice") or info.get("regularMarketPrice"),
            "52w_high":       info.get("fiftyTwoWeekHigh"),
            "52w_low":        info.get("fiftyTwoWeekLow"),
            "pe_ratio":       info.get("trailingPE"),
            "forward_pe":     info.get("forwardPE"),
            "beta":           info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio":   info.get("payoutRatio"),
            "profit_margin":  info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth":info.get("earningsGrowth"),
            "roe":            info.get("returnOnEquity"),
            "total_cash":     info.get("totalCash"),
            "total_debt":     info.get("totalDebt"),
            "free_cashflow":  info.get("freeCashflow"),
            "ebitda":         info.get("ebitda"),
            "recommendation": info.get("recommendationKey"),
            "target_mean":    info.get("targetMeanPrice"),
            "short_ratio":    info.get("shortRatio"),
            "shares_out":     info.get("sharesOutstanding"),
            "description":    (info.get("longBusinessSummary") or "")[:4000],  # <- FIXED: full About (was cut at 500)
        }
    except Exception as exc:
        logger.error("_fetch_info [%s]: %s", ticker, exc)
        return {}


@st.cache_data(ttl=CACHE_TTL)
def _fetch_macro_proxies() -> Dict[str, Any]:
    """Fetches macro proxy tickers for regime quadrant classification."""
    proxies = {
        "^GSPC": "S&P 500",   "^VIX": "VIX",   "^TNX": "10Y Yield",
        "DX-Y.NYB": "DXY",    "GLD": "Gold",   "CL=F": "WTI Oil",
        "TLT": "20Y Bonds",   "HYG": "HY Bonds",
    }
    result: Dict[str, Any] = {}
    for tkr, name in proxies.items():
        try:
            hist = yf.Ticker(tkr).history(period="1y")
            if hist.empty or len(hist) < 2:
                continue
            cur    = float(hist["Close"].iloc[-1])
            yr_ago = float(hist["Close"].iloc[0])
            chg_1y = (cur / yr_ago - 1.0) * 100.0 if yr_ago > 1e-10 else 0.0
            chg_1m = (
                (cur / float(hist["Close"].iloc[-21]) - 1.0) * 100.0
                if len(hist) >= 21 else 0.0
            )
            result[tkr] = {
                "name": name, "current": cur,
                "chg_1y": chg_1y, "chg_1m": chg_1m,
                "52w_high": float(hist["High"].max()),
                "52w_low":  float(hist["Low"].min()),
            }
        except Exception as exc:
            logger.debug("Macro proxy [%s]: %s", tkr, exc)
    return result


@st.cache_data(ttl=CACHE_TTL)
def _fetch_institutional_proxy(ticker: str) -> Dict[str, Any]:
    """Fetches institutional ownership proxy from yfinance."""
    result: Dict[str, Any] = {
        "inst_pct": 0.0, "insider_pct": 0.0, "top_holders": [],
    }
    try:
        t  = yf.Ticker(ticker)
        mh = t.major_holders
        if mh is not None and not mh.empty:
            try:
                result["inst_pct"]    = float(str(mh.iloc[2, 0]).replace("%", ""))
                result["insider_pct"] = float(str(mh.iloc[1, 0]).replace("%", ""))
            except (IndexError, ValueError):
                pass
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            rows: List[Dict[str, Any]] = []
            for _, row in ih.head(8).iterrows():
                rows.append({
                    "holder": str(row.get("Holder", "?")),
                    "shares": int(row.get("Shares", 0)),
                    "pct":    float(row.get("% Out", 0) or 0),
                })
            result["top_holders"] = rows
    except Exception as exc:
        logger.debug("Institutional proxy [%s]: %s", ticker, exc)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7 — ZIGZAG & ELLIOTT WAVE (Frost & Prechter ratios)
# ═══════════════════════════════════════════════════════════════════════════

def compute_zigzag(close: pd.Series, min_swing_pct: float = ZIGZAG_MIN_SWING) -> List[Tuple[int, float]]:
    """
    Computes ZigZag swing points using 5% minimum swing threshold.
    Source: User master prompt document (5% threshold).
    Returns list of (bar_index, price) tuples representing swing points.
    """
    if len(close) < 10:
        return []
    prices      = close.values.astype(float)
    n           = len(prices)
    direction   = 0          # 1=up, -1=down
    last_idx    = 0
    last_price  = prices[0]
    swings: List[Tuple[int, float]] = [(0, prices[0])]

    for i in range(1, n):
        p = prices[i]
        if last_price < 1e-10:
            continue
        chg = (p - last_price) / last_price

        if direction == 0:
            if chg >= min_swing_pct:
                direction  = 1
                last_idx   = i
                last_price = p
            elif chg <= -min_swing_pct:
                direction  = -1
                last_idx   = i
                last_price = p
        elif direction == 1:
            if p > last_price:
                last_idx   = i
                last_price = p
            elif last_price > 1e-10 and (last_price - p) / last_price >= min_swing_pct:
                swings.append((last_idx, last_price))
                direction  = -1
                last_idx   = i
                last_price = p
        else:
            if p < last_price:
                last_idx   = i
                last_price = p
            elif last_price > 1e-10 and (p - last_price) / last_price >= min_swing_pct:
                swings.append((last_idx, last_price))
                direction  = 1
                last_idx   = i
                last_price = p

    swings.append((last_idx, last_price))
    return swings


def analyse_elliott_waves(swings: List[Tuple[int, float]]) -> WaveResult:
    """
    Analyses ZigZag swings for Elliott Wave phase detection.

    All ratios from Frost & Prechter — Elliott Wave Principle (10th Ed.):
      Wave 2 retrace W1: primary 0.618, secondary 0.500, tertiary 0.382
                         valid range 0.382–0.999 [PF] p.28
      Wave 3 ext of W1:  primary 1.618 [PF] pp.29–33
      Wave 4 retrace W3: primary 0.382, range 0.236–0.500 [PF] pp.34–37
      Rule 1: Wave 2 never >= 100% of Wave 1 [PF] p.21
      Rule 2: Wave 3 never shortest of W1/W3/W5 [PF] p.21
      Rule 3: Wave 4 never enters Wave 1 territory [PF] p.21

    Returns WaveResult with wave_phase and confluence_pts.
    """
    empty: WaveResult = {
        "swings_found": len(swings), "wave_phase": "NONE",
        "conf_pts": 0, "fib_levels": {}, "swing_prices": [],
    }
    if len(swings) < 5:
        return empty

    pts = [p for _, p in swings[-6:]]
    if len(pts) < 5:
        return empty
    w0, w1, w2, w3, w4 = pts[0], pts[1], pts[2], pts[3], pts[4]

    # Leg lengths — measured as absolute price distance per [PF] Rule 2
    len_w1 = abs(w1 - w0)
    len_w2 = abs(w2 - w1)
    len_w3 = abs(w3 - w2)
    len_w4 = abs(w4 - w3)

    if len_w1 < 1e-10 or len_w3 < 1e-10:
        return {**empty, "swing_prices": [w0, w1, w2, w3, w4]}

    # Fibonacci levels from latest swing range
    swing_hi  = max(w0, w1, w2, w3, w4)
    swing_lo  = min(w0, w1, w2, w3, w4)
    swing_rng = swing_hi - swing_lo
    fib_levels: Dict[str, float] = {}
    for lvl in FIB_RETRACE:
        fib_levels[f"r{int(lvl * 1000)}"] = swing_hi - swing_rng * lvl
    for ext in FIB_EXTEND:
        fib_levels[f"e{int(ext * 1000)}"] = swing_lo + swing_rng * ext

    # Rule 1: Wave 2 must not retrace >= 100% of Wave 1 [PF] p.21
    w2_ratio = safe_ratio(len_w2, len_w1)
    rule1_ok  = w2_ratio < 1.000   # strictly less than 100%

    # Wave 2 guideline check [PF] p.28
    w2_valid = (
        rule1_ok
        and (EW_W2_RANGE_MIN - EW_W2_TOLERANCE) <= w2_ratio <= (EW_W2_RANGE_MAX)
    )

    # Wave 3 guideline check [PF] pp.29–33
    w3_ratio = safe_ratio(len_w3, len_w1)
    w3_valid = (
        abs(w3_ratio - EW_W3_PRIMARY) <= EW_W3_TOLERANCE
        or abs(w3_ratio - EW_W3_SECONDARY) <= EW_W3_TOLERANCE
        or w3_ratio >= 1.000   # any extension counts as valid
    )

    # Rule 2: Wave 3 is never the SHORTEST of waves 1/3/5 [PF] p.21
    # FIXED [E2]: the old `len_w3 > len_w1` was wrong -- W1 > W3 is perfectly legal
    # when W1 is the extended wave (Rule 2 only forbids W3 being the *shortest* of the
    # three motive waves, and W5 isn't in scope here). That over-strict test silently
    # rejected every valid W1-extension impulse. With only 4 legs visible the strict
    # rule is indeterminate, so we reject ONLY the unambiguous violation: W3 shorter
    # than every other leg we can see (W1, W2, AND W4) -- a degenerate/mislabelled W3.
    rule2_ok = not (len_w3 < len_w1 and len_w3 < len_w2 and len_w3 < len_w4)

    # Wave 4 guideline check [PF] pp.34–37
    w4_ratio = safe_ratio(len_w4, len_w3)
    w4_valid = (
        (EW_W4_RANGE_MIN - EW_W4_TOLERANCE) <= w4_ratio <= (EW_W4_RANGE_MAX + EW_W4_TOLERANCE)
    )

    # Rule 3: Wave 4 must not enter Wave 1 territory [PF] p.21
    # Bullish: W4 low must be above W1 high
    # We approximate directional check from swing structure
    is_bullish = w1 > w0
    if is_bullish:
        rule3_ok = w4 > w1   # W4 must stay above W1 high in bullish
    else:
        rule3_ok = w4 < w1   # W4 must stay below W1 low in bearish

    phase    = "NONE"
    conf_pts = 0

    if rule1_ok and rule2_ok and w2_valid and w3_valid and not w4_valid:
        # W3 appears complete, W4 not yet confirmed — W3 complete signal
        phase    = "W3_COMPLETE"
        conf_pts = CS_EW_W3_COMPLETE

    elif rule1_ok and rule2_ok and w2_valid and w3_valid and w4_valid and rule3_ok:
        # W4 complete — W5 potential reversal zone approaching
        # Compute W5 targets [PF] pp.38–42
        w5_eq_target  = w4 + len_w1 * (1.0 if is_bullish else -1.0)         # equality
        w5_fib_target = w4 + abs(w3 - w0) * EW_W5_FIBONACCI * (1.0 if is_bullish else -1.0)
        fib_levels["w5_equality"]  = w5_eq_target
        fib_levels["w5_fibonacci"] = w5_fib_target
        phase    = "W5_REVERSAL"
        conf_pts = CS_EW_W5_REVERSAL

    # ABC corrective check (3-swing minimum) [PF] pp.51–54
    if phase == "NONE" and len(pts) >= 3:
        a_len = abs(pts[-2] - pts[-3])
        b_len = abs(pts[-1] - pts[-2])
        if a_len > 1e-10:
            bc_r = safe_ratio(b_len, a_len)
            # Zigzag Wave B: 0.382–0.790 [PF] p.52
            if 0.382 - EW_W2_TOLERANCE <= bc_r <= 0.790 + EW_W2_TOLERANCE:
                phase    = "ABC_COMPLETE"
                conf_pts = CS_EW_ABC_COMPLETE

    return {
        "swings_found": len(swings),
        "wave_phase":   phase,
        "conf_pts":     conf_pts,
        "fib_levels":   fib_levels,
        "swing_prices": [w0, w1, w2, w3, w4],
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8 — HARMONIC PATTERN DETECTION (10 PATTERNS)
# Carney Vol.1/2/3 — all ratios from audited reference document
# ═══════════════════════════════════════════════════════════════════════════

def _quality_from_dev(worst_dev: float) -> Tuple[str, int]:
    """
    Maps worst ratio deviation to quality grade and confluence points.
    Thresholds: ±1%=PERFECT(+25), ±2%=GOOD(+20), ±3%=FAIR(+15) — user document.
    """
    if worst_dev <= TOLERANCE_PERFECT:
        return "PERFECT", CS_HARM_PERFECT
    if worst_dev <= TOLERANCE_GOOD:
        return "GOOD", CS_HARM_GOOD
    if worst_dev <= TOLERANCE_FAIR:
        return "FAIR", CS_HARM_FAIR
    return "NONE", 0


def _check_B_XABCD(pattern: Dict[str, Any], ratio_ab_xa: float) -> Tuple[bool, float]:
    """
    Validates B point for XABCD patterns.
    Returns (passes, deviation).
    Handles range_mode, max_mode, and discrete ideal modes.
    """
    spec = pattern["B_of_XA"]

    # max_mode: Alternate Bat — 0.382 is upper limit [CV3] Chapter 5
    if spec.get("max_mode"):
        lo = spec["lo"]
        hi = spec["hi"]
        passes = lo <= ratio_ab_xa <= hi
        dev    = abs(ratio_ab_xa - spec["ideal"]) if passes else float("inf")
        return passes, dev

    # upper_tolerance_mode: Deep Crab — asymmetric tolerance [CV3] Chapter 6
    if spec.get("upper_tolerance_mode"):
        lo = spec["lo"]
        hi = spec["hi"]
        passes = lo <= ratio_ab_xa <= hi
        dev    = abs(ratio_ab_xa - spec["ideal"]) if passes else float("inf")
        return passes, dev

    # range_mode: Bat, Crab — any value in range [CV2] / [CV1]
    if spec.get("range_mode"):
        tol    = spec["tol"]
        passes = (spec["lo"] - tol) <= ratio_ab_xa <= (spec["hi"] + tol)
        mid    = (spec["lo"] + spec["hi"]) / 2.0
        dev    = abs(ratio_ab_xa - mid)
        return passes, dev

    # default: discrete ideal with symmetric tolerance (Gartley, Bat ideal, Butterfly)
    tol    = spec["tol"]
    ideal  = spec["ideal"]
    dev    = abs(ratio_ab_xa - ideal)
    return dev <= tol, dev


def _check_C_AB(pattern: Dict[str, Any], ratio_bc_ab: float) -> Tuple[bool, float]:
    """
    Validates C point. All XABCD patterns: BC/AB is a continuous RANGE [0.382, 0.886].
    FIXED [Council T01]: was discrete {0.382, 0.886} ±0.001 → now range [lo, hi] ±tol.
    Returns (passes, deviation from midpoint).
    """
    spec = pattern["C_of_AB"]
    tol  = spec["tol"]

    # FIXED [Council T01]: C_of_AB is now a RANGE with lo/hi, not discrete values
    if "lo" in spec and "hi" in spec:
        lo = spec["lo"]
        hi = spec["hi"]
        passes = (lo - tol) <= ratio_bc_ab <= (hi + tol)
        mid = (lo + hi) / 2.0
        dev = abs(ratio_bc_ab - mid) if passes else float("inf")
        return passes, dev

    # Legacy fallback: discrete values (kept for backward compatibility)
    values = spec.get("values", (0.382, 0.886))
    devs   = [abs(ratio_bc_ab - v) for v in values]
    best   = min(devs)
    return best <= tol, best


def _check_D_proj(pattern: Dict[str, Any], ratio_cd_bc: float) -> Tuple[bool, float]:
    """
    Validates CD/BC extension projection. Range check.
    Returns (passes, deviation from nearest bound).
    """
    spec = pattern["D_proj_CD_BC"]
    tol  = spec["tol"]
    lo   = spec["lo"]
    hi   = spec["hi"]
    if (lo - tol) <= ratio_cd_bc <= (hi + tol):
        mid = (lo + hi) / 2.0
        return True, abs(ratio_cd_bc - mid)
    return False, float("inf")


def _check_ABCD_type(pattern: Dict[str, Any], ratio_cd_ab: float) -> Tuple[bool, float]:
    """
    Validates AB=CD type. Checks each valid multiplier.
    Returns (passes, deviation from nearest valid type).
    """
    types = pattern["ABCD_types"]
    tol   = pattern["ABCD_tol"]
    devs  = [abs(ratio_cd_ab - t) for t in types]
    best  = min(devs)
    return best <= tol, best


def _check_D_constraint_XABCD(
    pattern: Dict[str, Any],
    ratio_xd_xa: float,
) -> Tuple[bool, float]:
    """
    Validates D primary constraint (XD/XA ratio — retracement or extension).
    Handles discrete values, range_mode, and discrete_mode.
    Returns (passes, deviation).
    """
    spec = pattern["D_constraint"]

    # discrete_mode: Butterfly — D was 1.270 OR 1.414, now RANGE [1.250, 1.434] [T04]
    if spec.get("discrete_mode"):
        tol = spec["tol"]
        # FIXED [Council T04]: Butterfly D changed from discrete values to lo/hi range
        if "lo" in spec and "hi" in spec:
            lo = spec["lo"]
            hi = spec["hi"]
            passes = (lo - tol) <= ratio_xd_xa <= (hi + tol)
            mid = (lo + hi) / 2.0
            dev = abs(ratio_xd_xa - mid) if passes else float("inf")
            return passes, dev
        # Legacy fallback: discrete values
        values = spec.get("values", ())
        devs   = [abs(ratio_xd_xa - v) for v in values]
        best   = min(devs) if devs else float("inf")
        return best <= tol, best

    # range_mode: Alternate Bat (0.886–1.130) [CV3] Chapter 5
    #             Deep Crab 1.902 (1.618–1.902) [CV3] Chapter 6
    if spec.get("range_mode"):
        tol    = spec["tol"]
        lo     = spec["lo"]
        hi     = spec["hi"]
        passes = (lo - tol) <= ratio_xd_xa <= (hi + tol)
        mid    = (lo + hi) / 2.0
        dev    = abs(ratio_xd_xa - mid) if passes else float("inf")
        return passes, dev

    # default: single ideal value with tight tolerance
    ideal = spec["ideal"]
    tol   = spec["tol"]
    dev   = abs(ratio_xd_xa - ideal)
    return dev <= tol, dev


def _detect_xabcd_pattern(
    pattern: Dict[str, Any],
    x: float, a: float, b: float, c: float,
) -> HarmonicResult:
    """
    Detects one XABCD harmonic pattern from four swing point prices.
    D is the projected completion price — computed from C + CD extension.

    All ratio guards applied per audit Section 12 (safe_ratio).
    No float == comparisons — all use abs(value - target) <= tolerance.

    Args:
        pattern: One of the 8 XABCD pattern dicts.
        x, a, b, c: Four consecutive swing prices (X, A, B, C).

    Returns HarmonicResult.
    """
    name = pattern["name"]
    empty: HarmonicResult = {
        "pattern": name, "found": False, "quality": "NONE",
        "worst_dev": float("inf"), "conf_pts": 0,
        "prz_low": 0.0, "prz_high": 0.0, "d_price": 0.0, "ratios": {},
    }

    xa_len = abs(a - x)
    ab_len = abs(b - a)
    bc_len = abs(c - b)

    # Guard: all legs must have non-zero length
    if xa_len < 1e-10 or ab_len < 1e-10 or bc_len < 1e-10:
        return empty

    r_ab_xa = safe_ratio(ab_len, xa_len)
    r_bc_ab = safe_ratio(bc_len, ab_len)

    # Step 1: Check B point
    b_ok, b_dev = _check_B_XABCD(pattern, r_ab_xa)
    if not b_ok:
        return {**empty, "ratios": {"AB_XA": round(r_ab_xa, 4)}}

    # Step 2: Check C point
    c_ok, c_dev = _check_C_AB(pattern, r_bc_ab)
    if not c_ok:
        return {**empty, "ratios": {"AB_XA": round(r_ab_xa, 4), "BC_AB": round(r_bc_ab, 4)}}

    # Step 3: Project D from the PRIMARY D-point constraint (XD/XA) -- FIXED [H-MATCH].
    # Carney's DEFINING ratio is the D-point (XD/XA); CD/BC is a looser confirmation.
    # The old code projected D from the CD/BC midpoint and then tested the tight XD/XA,
    # which is backwards and almost never validated (XABCD detection was ~0). We now
    # project D to the pattern's XD/XA ideal (or range midpoint) on the geometrically
    # correct side, then confirm CD/BC as a range. No ratio/tolerance changed.
    d_spec     = pattern["D_constraint"]
    d_ideal_xd = d_spec["ideal"] if "ideal" in d_spec else (d_spec["lo"] + d_spec["hi"]) / 2.0
    is_ext     = pattern.get("D_is_extension", False)
    bullish    = a > x                          # X is a swing low -> bullish completion at D
    if is_ext:                                  # extension: D travels BEYOND X
        d_price = (x - d_ideal_xd * xa_len) if bullish else (x + d_ideal_xd * xa_len)
    else:                                       # retracement: D stays on the A-side of X
        d_price = (x + d_ideal_xd * xa_len) if bullish else (x - d_ideal_xd * xa_len)

    xd_len = abs(d_price - x)
    cd_len = abs(d_price - c)
    if cd_len < 1e-10:
        return empty

    r_cd_bc = safe_ratio(cd_len, bc_len)
    r_xd_xa = safe_ratio(xd_len, xa_len)
    r_cd_ab = safe_ratio(cd_len, ab_len)

    # Step 4: CD/BC confirmation (range gate)
    cd_ok, _cd_dev = _check_D_proj(pattern, r_cd_bc)
    if not cd_ok:
        return {**empty, "ratios": {
            "AB_XA": round(r_ab_xa, 4), "BC_AB": round(r_bc_ab, 4),
            "CD_BC": round(r_cd_bc, 4),
        }}

    # Step 5: D primary constraint -- passes by construction (projected to ideal); re-checked
    # so range-D patterns (Alt Bat / Deep Crab 1.902 / Butterfly) verify they stay in range.
    d_ok, _d_dev = _check_D_constraint_XABCD(pattern, r_xd_xa)
    if not d_ok:
        return {**empty, "ratios": {
            "AB_XA": round(r_ab_xa, 4), "BC_AB": round(r_bc_ab, 4),
            "CD_BC": round(r_cd_bc, 4), "XD_XA": round(r_xd_xa, 4),
        }}

    # Step 6: AB=CD type confirmation (recorded, not a hard gate)
    abcd_ok, _abcd_dev = _check_ABCD_type(pattern, r_cd_ab)

    # Quality from RANGE-AWARE deviation -- FIXED [H-MATCH]: inside a range = full marks
    # (dev 0); the 1/2/3% grade then reflects how precisely the tight defining ratios
    # (B-point, ideal D-point) are hit. The old code used distance-from-range-midpoint,
    # which made wide-range patterns (e.g. Crab CD/BC 2.0-3.618) always grade NONE and
    # silently vanish even when every ratio was within spec.
    def _rdev(ratio: float, lo, hi, ideal=None) -> float:
        if ideal is not None:
            return abs(ratio - ideal)
        if lo is None or hi is None:
            return 0.0
        if (lo - 1e-9) <= ratio <= (hi + 1e-9):
            return 0.0
        return min(abs(ratio - lo), abs(ratio - hi))

    _bs = pattern["B_of_XA"]; _cs = pattern["C_of_AB"]; _ps = pattern["D_proj_CD_BC"]
    b_dev  = _rdev(r_ab_xa, _bs.get("lo"), _bs.get("hi"), _bs.get("ideal"))
    c_dev  = _rdev(r_bc_ab, _cs.get("lo"), _cs.get("hi"))
    cd_dev = _rdev(r_cd_bc, _ps.get("lo"), _ps.get("hi"))
    d_dev  = _rdev(r_xd_xa, d_spec.get("lo"), d_spec.get("hi"), d_spec.get("ideal"))
    # FIXED [H2]: the grade must reflect how well the MARKET-DETERMINED pivots fit. Only
    # B (AB/XA) and C (BC/AB) are measured from real swings; CD/BC and XD/XA are functions
    # of the PROJECTED D, so cd_dev/d_dev are ~0 by construction and previously forced an
    # undeserved "PERFECT" (+25 conf) on almost every match. They stay as gates above
    # (Steps 4-5) and are still reported in `ratios`; they no longer inflate the grade.
    worst_dev = max(b_dev, c_dev)
    quality, conf_pts = _quality_from_dev(worst_dev)

    if quality == "NONE":
        return {**empty, "ratios": {
            "AB_XA": round(r_ab_xa, 4), "BC_AB": round(r_bc_ab, 4),
            "CD_BC": round(r_cd_bc, 4), "XD_XA": round(r_xd_xa, 4),
        }}

    # PRZ zone: +/-0.5% around the projected D
    prz_margin = d_price * 0.005 if d_price > 1e-10 else 0.005
    prz_lo     = d_price - prz_margin
    prz_hi     = d_price + prz_margin

    return {
        "pattern":   name,
        "found":     True,
        "quality":   quality,
        "worst_dev": round(worst_dev, 4),
        "conf_pts":  conf_pts,
        "prz_low":   round(prz_lo,   4),
        "prz_high":  round(prz_hi,   4),
        "d_price":   round(d_price,  4),
        "direction": "bullish" if bullish else "bearish",   # <- ADDED [H-MATCH]
        "abcd_ok":   bool(abcd_ok),                          # <- ADDED [H-MATCH]
        "ratios": {
            "AB_XA": round(r_ab_xa, 4),
            "BC_AB": round(r_bc_ab, 4),
            "CD_BC": round(r_cd_bc, 4),
            "XD_XA": round(r_xd_xa, 4),
            "CD_AB": round(r_cd_ab, 4),
        },
    }

def detect_shark(swings: List[Tuple[int, float]]) -> HarmonicResult:
    """
    Detects Shark pattern using 0XABC labeling per [CV3] Chapter 8.

    CRITICAL: Shark uses 0, X, A, B, C — NOT XABCD.
    There is NO D point. C is the completion/entry.
    This function is completely separate from detect_xabcd_pattern.

    Leg formulas per audit:
      X_of_0A: leg_XA / leg_0A  → 0.382–0.886
      A_of_0X: leg_0A / leg_0X  → 1.130–1.618
      B_of_XA: leg_AB / leg_XA  → 1.618–2.240
      C_of_0X: leg_0C / leg_0X  → 0.886 OR 1.130 (ENTRY)
    """
    spec = HARMONIC_SHARK
    name = "SHARK"
    empty: HarmonicResult = {
        "pattern": name, "found": False, "quality": "NONE",
        "worst_dev": float("inf"), "conf_pts": 0,
        "prz_low": 0.0, "prz_high": 0.0, "d_price": 0.0, "ratios": {},
    }

    if len(swings) < 5:
        return empty

    # Shark needs 5 pivots: 0, X, A, B, C
    pts = [p for _, p in swings[-5:]]
    p0, px, pa, pb, pc = pts[0], pts[1], pts[2], pts[3], pts[4]

    leg_0x = abs(px - p0)
    leg_xa = abs(pa - px)
    leg_0a = abs(pa - p0)
    leg_ab = abs(pb - pa)
    leg_bc = abs(pc - pb)
    leg_0c = abs(pc - p0)

    if leg_0x < 1e-10 or leg_0a < 1e-10 or leg_xa < 1e-10:
        return empty

    r_x_0a  = safe_ratio(leg_xa, leg_0a)    # X retraces 0A
    r_a_0x  = safe_ratio(leg_0a, leg_0x)    # A vs 0X
    r_b_xa  = safe_ratio(leg_ab, leg_xa)    # B extends XA
    r_c_0x  = safe_ratio(leg_0c, leg_0x)    # C vs 0X (ENTRY)

    tol = spec["X_of_0A"]["tol"]

    # Check X/0A: 0.382–0.886
    x_ok = (spec["X_of_0A"]["lo"] - tol) <= r_x_0a <= (spec["X_of_0A"]["hi"] + tol)
    x_dev = 0.0 if x_ok else min(abs(r_x_0a - spec["X_of_0A"]["lo"]), abs(r_x_0a - spec["X_of_0A"]["hi"]))  # <- FIXED [H-MATCH]: range-aware

    # Check A/0X: 1.130–1.618
    a_ok = (spec["A_of_0X"]["lo"] - tol) <= r_a_0x <= (spec["A_of_0X"]["hi"] + tol)
    a_dev = 0.0 if a_ok else min(abs(r_a_0x - spec["A_of_0X"]["lo"]), abs(r_a_0x - spec["A_of_0X"]["hi"]))  # <- FIXED [H-MATCH]: range-aware

    # Check B/XA: 1.618–2.240
    b_ok = (spec["B_of_XA_ext"]["lo"] - tol) <= r_b_xa <= (spec["B_of_XA_ext"]["hi"] + tol)
    b_dev = 0.0 if b_ok else min(abs(r_b_xa - spec["B_of_XA_ext"]["lo"]), abs(r_b_xa - spec["B_of_XA_ext"]["hi"]))  # <- FIXED [H-MATCH]: range-aware

    # Check C/0X: 0.886 OR 1.130 — PRIMARY CONSTRAINT / ENTRY POINT
    c_devs = [abs(r_c_0x - v) for v in spec["C_of_0X"]["values"]]
    c_dev  = min(c_devs)
    c_ok   = c_dev <= spec["C_of_0X"]["tol"]

    if not (x_ok and a_ok and b_ok and c_ok):
        return {**empty, "ratios": {
            "X_0A": round(r_x_0a, 4), "A_0X": round(r_a_0x, 4),
            "B_XA": round(r_b_xa, 4), "C_0X": round(r_c_0x, 4),
        }}

    worst_dev = max(x_dev, a_dev, b_dev, c_dev)
    quality, conf_pts = _quality_from_dev(worst_dev)

    if quality == "NONE":
        return empty

    # Entry = C price. PRZ = ±0.5% around C.
    prz_margin = pc * 0.005 if pc > 1e-10 else 0.005

    return {
        "pattern":   "SHARK",
        "found":     True,
        "quality":   quality,
        "worst_dev": round(worst_dev, 4),
        "conf_pts":  conf_pts,
        "prz_low":   round(pc - prz_margin, 4),
        "prz_high":  round(pc + prz_margin, 4),
        "d_price":   round(pc, 4),   # C is the entry (no D)
        "ratios": {
            "X_0A": round(r_x_0a, 4),
            "A_0X": round(r_a_0x, 4),
            "B_XA": round(r_b_xa, 4),
            "C_0X": round(r_c_0x, 4),
        },
    }


def detect_reciprocal_abcd(swings: List[Tuple[int, float]]) -> HarmonicResult:
    """
    Detects Reciprocal AB=CD pattern per [CV3] Chapter 9.

    No XA D-point constraint. Uses:
      C extends AB: BC_len / AB_len = 1.130–3.618
      D retraces BC: CD_len / BC_len = 0.382–0.886
      ABCD types: 1.27 or 1.618 AB=CD

    CORRECTED from prior version: base legs now correctly identified.
    """
    spec = HARMONIC_RECIP_ABCD
    name = "RECIPROCAL_ABCD"
    empty: HarmonicResult = {
        "pattern": name, "found": False, "quality": "NONE",
        "worst_dev": float("inf"), "conf_pts": 0,
        "prz_low": 0.0, "prz_high": 0.0, "d_price": 0.0, "ratios": {},
    }

    if len(swings) < 5:
        return empty

    pts = [p for _, p in swings[-5:]]
    xa_price, a_price, b_price, c_price = pts[0], pts[1], pts[2], pts[3]

    xa_len = abs(a_price - xa_price)
    ab_len = abs(b_price - a_price)
    bc_len = abs(c_price - b_price)

    if xa_len < 1e-10 or ab_len < 1e-10 or bc_len < 1e-10:
        return empty

    # C extends AB: BC_len / AB_len [CV3] Chapter 9
    r_c_ab = safe_ratio(bc_len, ab_len)
    tol    = spec["C_extends_AB"]["tol"]
    c_ok   = (spec["C_extends_AB"]["lo"] - tol) <= r_c_ab <= (spec["C_extends_AB"]["hi"] + tol)
    if not c_ok:
        return {**empty, "ratios": {"C_extends_AB": round(r_c_ab, 4)}}

    c_dev = abs(r_c_ab - (spec["C_extends_AB"]["lo"] + spec["C_extends_AB"]["hi"]) / 2.0)

    # Project D: use midpoint of D retracement range applied to BC
    d_retrace_mid = (spec["D_retraces_BC"]["lo"] + spec["D_retraces_BC"]["hi"]) / 2.0
    cd_projected  = bc_len * d_retrace_mid
    if c_price < b_price:    # BC was down → CD projects up
        d_price = c_price + cd_projected
    else:
        d_price = c_price - cd_projected

    cd_len = abs(d_price - c_price)
    if cd_len < 1e-10:
        return empty

    r_d_bc = safe_ratio(cd_len, bc_len)
    d_tol  = spec["D_retraces_BC"]["tol"]
    d_ok   = (spec["D_retraces_BC"]["lo"] - d_tol) <= r_d_bc <= (spec["D_retraces_BC"]["hi"] + d_tol)
    if not d_ok:
        return {**empty, "ratios": {"C_extends_AB": round(r_c_ab, 4), "D_retraces_BC": round(r_d_bc, 4)}}

    d_dev = abs(r_d_bc - (spec["D_retraces_BC"]["lo"] + spec["D_retraces_BC"]["hi"]) / 2.0)

    # ABCD type check
    r_cd_ab = safe_ratio(cd_len, ab_len)
    abcd_devs = [abs(r_cd_ab - t) for t in spec["ABCD_types"]]
    abcd_dev  = min(abcd_devs)
    abcd_ok   = abcd_dev <= spec["ABCD_tol"]

    worst_dev = max(c_dev, d_dev)
    if abcd_ok:
        worst_dev = max(worst_dev, abcd_dev)

    quality, conf_pts = _quality_from_dev(worst_dev)
    if quality == "NONE":
        return empty

    prz_margin = d_price * 0.005 if d_price > 1e-10 else 0.005

    return {
        "pattern":   name,
        "found":     True,
        "quality":   quality,
        "worst_dev": round(worst_dev, 4),
        "conf_pts":  conf_pts,
        "prz_low":   round(d_price - prz_margin, 4),
        "prz_high":  round(d_price + prz_margin, 4),
        "d_price":   round(d_price, 4),
        "direction": ("bullish" if d_price < c_price else "bearish"),   # <- ADDED [H-MATCH]: AB=CD entry low=buy(bullish) / high=sell(bearish)
        "ratios": {
            "C_extends_AB":  round(r_c_ab,  4),
            "D_retraces_BC": round(r_d_bc,  4),
            "CD_AB":         round(r_cd_ab, 4),
        },
    }


def _empty_harm(name: str) -> HarmonicResult:   # <- ADDED [H4]: shared not-found shape
    return {
        "pattern": name, "found": False, "quality": "NONE",
        "worst_dev": float("inf"), "conf_pts": 0,
        "prz_low": 0.0, "prz_high": 0.0, "d_price": 0.0, "ratios": {},
    }


def _band_dev(r: float, lo: float, hi: float) -> float:   # <- ADDED [H4]: range-aware deviation
    if (lo - 1e-9) <= r <= (hi + 1e-9):
        return 0.0
    return min(abs(r - lo), abs(r - hi))


def _recency_limit(swings: List[Tuple[int, float]]) -> int:   # <- ADDED [H5]
    """How old (in bars) a pattern's LAST pivot may be and still count as actionable.

    A daily-timeframe harmonic must be tradeable NOW — not a textbook shape pivoted
    18 months ago. We gate every found pattern AND the near-miss so its last pivot sits
    in the recent tail of the series (~the last quarter of the window, floored at 60 bars,
    a sane daily-swing horizon). If nothing recent qualifies the engine reports NONE,
    which is the truthful state ("no harmonic found in the recent window").
    """
    if not swings:
        return 10 ** 9
    total = swings[-1][0] + 1
    return max(60, int(0.25 * total))


def detect_cypher(swings: List[Tuple[int, float]]) -> HarmonicResult:
    """
    Detects the CYPHER pattern (X,A,B,C → projected D). ADDED [H4].

    Carney exception: C is an EXTENSION of XA (XC/XA = 1.272–1.414), NOT a
    retracement of AB. B retraces XA (0.382–0.618). D is projected at the 0.786
    retracement of the XC leg. Grade is driven only by the MARKET-determined
    ratios (B, C); D is projected to its ideal (consistent with the H2 fix).
    """
    spec = HARMONIC_CYPHER
    empty = _empty_harm("CYPHER")
    if len(swings) < 4:
        return empty
    x, a, b, c = (p for _, p in swings[-4:])
    xa = abs(a - x); ab = abs(b - a); xc = abs(c - x)
    if xa < 1e-10 or ab < 1e-10 or xc < 1e-10:
        return empty

    r_b = safe_ratio(ab, xa)     # B retraces XA
    r_c = safe_ratio(xc, xa)     # C EXTENDS XA (the exception)
    bs, cs = spec["B_of_XA"], spec["C_of_XA"]
    b_ok = (bs["lo"] - bs["tol"]) <= r_b <= (bs["hi"] + bs["tol"])
    c_ok = (cs["lo"] - cs["tol"]) <= r_c <= (cs["hi"] + cs["tol"])
    if not (b_ok and c_ok):
        return {**empty, "ratios": {"AB_XA": round(r_b, 4), "XC_XA": round(r_c, 4)}}

    d_ideal = spec["D_of_XC"]["ideal"]            # project D: 0.786 retrace of XC
    d_price = (c - d_ideal * xc) if c > x else (c + d_ideal * xc)
    r_d = safe_ratio(abs(d_price - c), xc)

    worst = max(_band_dev(r_b, bs["lo"], bs["hi"]), _band_dev(r_c, cs["lo"], cs["hi"]))
    quality, conf = _quality_from_dev(worst)
    if quality == "NONE":
        return {**empty, "ratios": {"AB_XA": round(r_b, 4), "XC_XA": round(r_c, 4)}}

    prz = d_price * 0.005 if d_price > 1e-10 else 0.005
    return {
        "pattern": "CYPHER", "found": True, "quality": quality,
        "worst_dev": round(worst, 4), "conf_pts": conf,
        "prz_low": round(d_price - prz, 4), "prz_high": round(d_price + prz, 4),
        "d_price": round(d_price, 4),
        "direction": "bullish" if d_price < c else "bearish",
        "ratios": {"AB_XA": round(r_b, 4), "XC_XA": round(r_c, 4), "CD_XC": round(r_d, 4)},
    }


def detect_five_zero(swings: List[Tuple[int, float]]) -> HarmonicResult:
    """
    Detects the 5-0 pattern (X,A,B,C → projected D). ADDED [H4].

    AB is a large reciprocal leg of XA (1.13–1.618); BC extends AB (1.618–2.24);
    D completes at the 0.50 retracement of BC (the defining 5-0 ratio). Grade is
    driven by the market-determined AB/XA and BC/AB; D is projected (H2-consistent).
    """
    spec = HARMONIC_FIVE_ZERO
    empty = _empty_harm("FIVE_ZERO")
    if len(swings) < 4:
        return empty
    x, a, b, c = (p for _, p in swings[-4:])
    xa = abs(a - x); ab = abs(b - a); bc = abs(c - b)
    if xa < 1e-10 or ab < 1e-10 or bc < 1e-10:
        return empty

    r_ab = safe_ratio(ab, xa)
    r_bc = safe_ratio(bc, ab)
    abs_, bcs = spec["AB_of_XA"], spec["BC_of_AB"]
    ab_ok = (abs_["lo"] - abs_["tol"]) <= r_ab <= (abs_["hi"] + abs_["tol"])
    bc_ok = (bcs["lo"] - bcs["tol"]) <= r_bc <= (bcs["hi"] + bcs["tol"])
    if not (ab_ok and bc_ok):
        return {**empty, "ratios": {"AB_XA": round(r_ab, 4), "BC_AB": round(r_bc, 4)}}

    d_ideal = spec["D_of_BC"]["ideal"]            # project D: 0.50 retrace of BC
    d_price = (c - d_ideal * bc) if c > b else (c + d_ideal * bc)
    r_d = safe_ratio(abs(d_price - c), bc)

    worst = max(_band_dev(r_ab, abs_["lo"], abs_["hi"]), _band_dev(r_bc, bcs["lo"], bcs["hi"]))
    quality, conf = _quality_from_dev(worst)
    if quality == "NONE":
        return {**empty, "ratios": {"AB_XA": round(r_ab, 4), "BC_AB": round(r_bc, 4)}}

    prz = d_price * 0.005 if d_price > 1e-10 else 0.005
    return {
        "pattern": "FIVE_ZERO", "found": True, "quality": quality,
        "worst_dev": round(worst, 4), "conf_pts": conf,
        "prz_low": round(d_price - prz, 4), "prz_high": round(d_price + prz, 4),
        "d_price": round(d_price, 4),
        "direction": "bullish" if d_price < c else "bearish",
        "ratios": {"AB_XA": round(r_ab, 4), "BC_AB": round(r_bc, 4), "CD_BC": round(r_d, 4)},
    }


def detect_three_drives(swings: List[Tuple[int, float]]) -> HarmonicResult:
    """
    Detects THREE DRIVES from 6 pivots p0..p5. ADDED [H4].

    Drives D1(p0→p1), D2(p2→p3), D3(p4→p5); pullbacks PB1(p1→p2), PB2(p3→p4).
    Each pullback retraces 0.618–0.786 of the prior drive; the three drives are
    in the SAME direction and roughly equal (±symmetry_tol). Unlike the projected
    XABCD patterns, Three Drives COMPLETES at p5 — a real pivot — so d_price=p5 is
    the actual completion (not a projection).
    """
    spec = HARMONIC_THREE_DRIVES
    empty = _empty_harm("THREE_DRIVES")
    if len(swings) < 6:
        return empty
    p0, p1, p2, p3, p4, p5 = (p for _, p in swings[-6:])
    d1 = abs(p1 - p0); pb1 = abs(p2 - p1)
    d2 = abs(p3 - p2); pb2 = abs(p4 - p3)
    d3 = abs(p5 - p4)
    if min(d1, pb1, d2, pb2, d3) < 1e-10:
        return empty

    # Drives must share direction (a trending three-drives), pullbacks oppose.
    dir1, dir2, dir3 = (p1 - p0), (p3 - p2), (p5 - p4)
    if not (dir1 > 0 and dir2 > 0 and dir3 > 0) and not (dir1 < 0 and dir2 < 0 and dir3 < 0):
        return empty

    r_pb1 = safe_ratio(pb1, d1)
    r_pb2 = safe_ratio(pb2, d2)
    pbs = spec["pullback"]
    pb1_ok = (pbs["lo"] - pbs["tol"]) <= r_pb1 <= (pbs["hi"] + pbs["tol"])
    pb2_ok = (pbs["lo"] - pbs["tol"]) <= r_pb2 <= (pbs["hi"] + pbs["tol"])
    # symmetry: drives 2 & 3 within ±symmetry_tol of drive 1
    sym_ok = (abs(d2 - d1) <= spec["symmetry_tol"] * d1) and (abs(d3 - d1) <= spec["symmetry_tol"] * d1)
    if not (pb1_ok and pb2_ok and sym_ok):
        return {**empty, "ratios": {"PB1_D1": round(r_pb1, 4), "PB2_D2": round(r_pb2, 4),
                                    "D2_D1": round(safe_ratio(d2, d1), 4),
                                    "D3_D1": round(safe_ratio(d3, d1), 4)}}

    pb_dev  = max(_band_dev(r_pb1, pbs["lo"], pbs["hi"]), _band_dev(r_pb2, pbs["lo"], pbs["hi"]))
    sym_dev = max(abs(d2 - d1), abs(d3 - d1)) / d1   # 0..symmetry_tol
    worst   = max(pb_dev, sym_dev)
    quality, conf = _quality_from_dev(worst)
    if quality == "NONE":
        return {**empty, "ratios": {"PB1_D1": round(r_pb1, 4), "PB2_D2": round(r_pb2, 4)}}

    d_price = p5                                       # completion = real pivot
    prz = d_price * 0.005 if d_price > 1e-10 else 0.005
    return {
        "pattern": "THREE_DRIVES", "found": True, "quality": quality,
        "worst_dev": round(worst, 4), "conf_pts": conf,
        "prz_low": round(d_price - prz, 4), "prz_high": round(d_price + prz, 4),
        "d_price": round(d_price, 4),
        "direction": "bearish" if dir3 > 0 else "bullish",   # up-drives exhaust into a high → sell
        "ratios": {"PB1_D1": round(r_pb1, 4), "PB2_D2": round(r_pb2, 4),
                   "D2_D1": round(safe_ratio(d2, d1), 4), "D3_D1": round(safe_ratio(d3, d1), 4)},
    }


def scan_all_harmonic_patterns(swings: List[Tuple[int, float]]) -> List[HarmonicResult]:
    """
    Scans for all 13 harmonic patterns from the audited Carney reference.

    Patterns 1–8 (XABCD): shared detector, 4-pivot (X,A,B,C) window slid over ALL swings.
    Pattern 9 (Shark):       dedicated detector using 0XABC labeling.
    Pattern 10 (Recip):      dedicated detector using BC-based D constraint.
    Pattern 11 (Cypher):     C is an EXTENSION of XA (the Carney exception); D=0.786 XC. [H4]
    Pattern 12 (5-0):        AB reciprocal of XA; D at 0.50 of BC. [H4]
    Pattern 13 (Three Drives): 6-pivot symmetry, completes at a real pivot. [H4]

    Returns list of 13 HarmonicResult dicts (found or not found per pattern).
    """
    # FIXED [Council H-SCAN]: previously only the single most-recent pivot window
    # (swings[-5:]) was ever tested, so a textbook pattern completing anywhere but
    # the final few pivots was invisible -> detection effectively never fired.
    # Now every detector slides its pivot window across ALL consecutive swing
    # combinations and keeps the best (lowest worst_dev, most-recent on tie) FOUND
    # result per pattern. The per-window matchers (_detect_xabcd_pattern,
    # detect_shark, detect_reciprocal_abcd) are called VERBATIM on each window --
    # no ratio, tolerance, or pattern math is changed, only the window coverage.
    def _empty(name: str) -> HarmonicResult:  # <- ADDED [H-SCAN]: not-found placeholder (unchanged shape)
        return {
            "pattern": name, "found": False, "quality": "NONE",
            "worst_dev": float("inf"), "conf_pts": 0,
            "prz_low": 0.0, "prz_high": 0.0, "d_price": 0.0, "ratios": {},
        }

    def _keep_best(best: HarmonicResult, cand: HarmonicResult) -> HarmonicResult:  # <- ADDED [H-SCAN]
        # Prefer the MOST RECENT found window (windows iterate ascending, so the last
        # found candidate wins). A forming harmonic completes at recent pivots, so the
        # latest valid completion is the actionable one a trader cares about now -- this
        # mirrors how charting tools surface "the" pattern. Quality is still reported per
        # pattern via its grade; selection just favours recency over textbook-perfection.
        if not cand.get("found"):
            return best
        return cand

    def _confirm(res: HarmonicResult, nxt: Optional[float]) -> None:  # <- ADDED [H-CONFIRM]
        # Mark whether the real pivot AFTER C actually reached the projected PRZ. The XABCD
        # / Shark / Recip detectors PROJECT D to the pattern's ideal ratio, so the Step-5
        # XD/XA re-check is tautological -> "found" proves only the X-A-B-C geometry, never
        # that price reversed at D. d_confirmed=True => a real completion a trader can act on;
        # False => a forming/projected pattern (watch, don't trade). Purely additive: no
        # existing field, ratio, tolerance, or selection behaviour changes.
        lo = res.get("prz_low", 0.0)
        hi = res.get("prz_high", 0.0)
        if nxt is None or hi <= lo:
            res["d_confirmed"] = False
            return
        res["d_actual"]    = round(nxt, 4)
        res["d_confirmed"] = bool(lo <= nxt <= hi)

    results: List[HarmonicResult] = []
    n      = len(swings)
    prices = [p for _, p in swings]

    # Patterns 1-8 (XABCD): slide a 4-pivot (X,A,B,C) window over every swing combo.
    for pattern in XABCD_PATTERNS:
        best = _empty(pattern["name"])
        for i in range(0, max(0, n - 3)):                       # <- ADDED [H-SCAN]: all 4-pivot windows
            cand = _detect_xabcd_pattern(
                pattern, prices[i], prices[i + 1], prices[i + 2], prices[i + 3]
            )
            if cand.get("found"):                               # <- ADDED [H-MTF]: bar-indices for date mapping
                cand["pivot_idx"] = [swings[i][0], swings[i + 1][0], swings[i + 2][0], swings[i + 3][0]]
                _confirm(cand, prices[i + 4] if i + 4 < n else None)   # <- ADDED [H-CONFIRM]
            best = _keep_best(best, cand)
        results.append(best)

    # Pattern 9 (Shark): slide a 5-pivot (0,X,A,B,C) window. detect_shark reads
    # swings[-5:]; feeding each exact 5-pivot slice evaluates that window with the
    # shark math fully unchanged.
    shark_best = _empty("SHARK")
    for i in range(0, max(0, n - 4)):                           # <- ADDED [H-SCAN]: all 5-pivot windows
        _sc = detect_shark(swings[i:i + 5])
        if _sc.get("found"):                                    # <- ADDED [H-MTF]
            _sc["pivot_idx"] = [swings[i + k][0] for k in range(5)]
            _confirm(_sc, prices[i + 5] if i + 5 < n else None)       # <- ADDED [H-CONFIRM]
        shark_best = _keep_best(shark_best, _sc)
    results.append(shark_best)

    # Pattern 10 (Reciprocal AB=CD): 4-pivot (X,A,B,C) window. detect_reciprocal_abcd
    # requires len>=5 and reads pts[0:4] of swings[-5:]; we pad each 4-pivot window
    # to a 5-element slice (the 5th pivot is never read by pts[0:4]) so EVERY window
    # -- including the most recent four pivots -- is evaluated, math unchanged.
    recip_best = _empty("RECIPROCAL_ABCD")
    for i in range(0, max(0, n - 3)):                           # <- ADDED [H-SCAN]: all 4-pivot windows
        window4 = swings[i:i + 4]
        padded  = window4 + [window4[-1]]                       # dummy 5th pivot; ignored by pts[0:4]
        _rc = detect_reciprocal_abcd(padded)
        if _rc.get("found"):                                    # <- ADDED [H-MTF]
            _rc["pivot_idx"] = [window4[k][0] for k in range(len(window4))]
            _confirm(_rc, prices[i + 4] if i + 4 < n else None)       # <- ADDED [H-CONFIRM]
        recip_best = _keep_best(recip_best, _rc)
    results.append(recip_best)

    # Pattern 11 (Cypher) & 12 (5-0): 4-pivot (X,A,B,C) windows, D projected. ADDED [H4].
    for _det, _nm in ((detect_cypher, "CYPHER"), (detect_five_zero, "FIVE_ZERO")):
        _best = _empty(_nm)
        for i in range(0, max(0, n - 3)):
            _cand = _det(swings[i:i + 4])
            if _cand.get("found"):
                _cand["pivot_idx"] = [swings[i + k][0] for k in range(4)]
                _confirm(_cand, prices[i + 4] if i + 4 < n else None)
            _best = _keep_best(_best, _cand)
        results.append(_best)

    # Pattern 13 (Three Drives): 6-pivot window; completes at the real pivot p5. ADDED [H4].
    td_best = _empty("THREE_DRIVES")
    for i in range(0, max(0, n - 5)):
        _td = detect_three_drives(swings[i:i + 6])
        if _td.get("found"):
            _td["pivot_idx"] = [swings[i + k][0] for k in range(6)]
            _confirm(_td, prices[i + 6] if i + 6 < n else None)
        td_best = _keep_best(td_best, _td)
    results.append(td_best)

    # [H5] RECENCY GATE: a pattern is only actionable if its LAST pivot is in the recent
    # tail of the series. Demote stale founds (e.g. an 18-month-old shape on a daily view)
    # to not-found so the UI never surfaces them — matching "no harmonic found in 2026 =>
    # show none". Ratios are preserved + a `stale` flag is set for transparency.
    if swings:
        _last    = swings[-1][0]
        _recency = _recency_limit(swings)
        for _r in results:
            _pid = _r.get("pivot_idx")
            if _r.get("found") and _pid and (_last - max(_pid)) > _recency:
                _r["found"]    = False
                _r["quality"]  = "NONE"
                _r["conf_pts"] = 0
                _r["stale"]    = True

    return results


def harmonic_near_miss(swings: List[Tuple[int, float]]) -> Optional[Dict[str, Any]]:
    """Nearest harmonic NEAR-MISS for charts with no confirmed pattern.  # <- NEW [H-MTF]

    This is a SEPARATE 'nearest-to' readout and NEVER relaxes the live detector --
    Carney tolerances for confirmed patterns are untouched. For every XABCD pattern and
    every 4-pivot window it projects D from the primary XD/XA ratio and measures how far
    the B / C / CD-BC ratios sit OUTSIDE their ranges (0 if inside). Returns the single
    closest candidate with the extra tolerance it would need ('miss'), or None.
    """
    prices = [p for _, p in swings]
    if len(prices) < 4:
        return None

    def _over(r: float, lo: Optional[float], hi: Optional[float]) -> float:
        if lo is None or hi is None:
            return 0.0
        if (lo - 1e-9) <= r <= (hi + 1e-9):
            return 0.0
        return min(abs(r - lo), abs(r - hi))

    last_idx = swings[-1][0]                       # <- ADDED [H5]
    recency  = _recency_limit(swings)              # <- ADDED [H5]
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for pat in XABCD_PATTERNS:
        d_spec  = pat["D_constraint"]
        d_ideal = d_spec["ideal"] if "ideal" in d_spec else (d_spec["lo"] + d_spec["hi"]) / 2.0
        is_ext  = pat.get("D_is_extension", False)
        bs, cs, ps = pat["B_of_XA"], pat["C_of_AB"], pat["D_proj_CD_BC"]
        for i in range(len(prices) - 3):
            # [H5] only the RECENT tail is tradeable — skip windows whose C pivot is stale.
            if (last_idx - swings[i + 3][0]) > recency:
                continue
            x, a, b, c = prices[i], prices[i + 1], prices[i + 2], prices[i + 3]
            xa = abs(a - x); ab = abs(b - a); bc = abs(c - b)
            if min(xa, ab, bc) < 1e-10:
                continue
            rb = safe_ratio(ab, xa); rc = safe_ratio(bc, ab)
            bullish = a > x
            if is_ext:
                d = (x - d_ideal * xa) if bullish else (x + d_ideal * xa)
            else:
                d = (x + d_ideal * xa) if bullish else (x - d_ideal * xa)
            cd = abs(d - c)
            if cd < 1e-10:
                continue
            rcd = safe_ratio(cd, bc)
            miss = max(_over(rb, bs.get("lo"), bs.get("hi")),
                       _over(rc, cs.get("lo"), cs.get("hi")),
                       _over(rcd, ps.get("lo"), ps.get("hi")))
            if best is None or miss < best[0]:
                margin = d * 0.005 if d > 1e-10 else 0.005
                best = (miss, {
                    "pattern":   pat["name"],
                    "direction": "bullish" if bullish else "bearish",
                    "d_price":   round(d, 4),
                    "prz_low":   round(d - margin, 4),
                    "prz_high":  round(d + margin, 4),
                    "miss":      round(miss, 4),
                    "pivot_idx": [swings[i][0], swings[i + 1][0], swings[i + 2][0], swings[i + 3][0]],
                })
    # [H5] a "near-miss" must actually be NEAR. If the closest RECENT candidate still needs a
    # large extra tolerance it is not a near-miss — it is no pattern. Cap it so the UI shows a
    # truthful "no harmonic" instead of a junk readout (Carney near-miss ≈ a few % extra room).
    NEAR_MISS_MAX = 0.10
    return best[1] if (best and best[0] <= NEAR_MISS_MAX) else None


def compute_proximity_readouts(                                   # <- NEW [PROX]
    last_price: Optional[float],
    rsi: Optional[float],
    macd_line: Optional[float],
    macd_signal: Optional[float],
    macd_hist: Optional[float],
    bb_upper: Optional[float],
    bb_lower: Optional[float],
    price_vs_cloud: Optional[str],
    cloud_top: Optional[float],
    cloud_bot: Optional[float],
    tk_cross: Optional[str],
    wave_phase: Optional[str],
) -> List[Dict[str, Any]]:
    """SEPARATE 'nearest-to / leaning' readout for the non-harmonic engines.

    Mirrors the harmonic near-miss idea: it NEVER changes an indicator value or the
    engine's own thresholds (RSI_OVERBOUGHT / RSI_OVERSOLD, the computed Bollinger
    bands, the Ichimoku cloud edges, the MACD signal line). It only measures how close
    each indicator sits to its next actionable level and which way it leans, so a
    'neutral' reading still tells the trader which direction it is closest to flipping.
    All comparisons are tolerance-based (no float ==). Returns a list of readout dicts.
    """
    out: List[Dict[str, Any]] = []
    lp = float(last_price) if last_price is not None else 0.0

    # RSI -> distance to the engine's own overbought / oversold lines
    if rsi is not None:
        r = float(rsi)
        if r >= RSI_OVERBOUGHT:
            out.append({"name": "RSI", "state": "overbought", "lean": "bearish",
                        "to": f"overbought ({RSI_OVERBOUGHT:.0f})",
                        "note": f"RSI {r:.1f} is {r - RSI_OVERBOUGHT:.1f} above overbought ({RSI_OVERBOUGHT:.0f}) \u2014 stretched, reversal risk."})
        elif r <= RSI_OVERSOLD:
            out.append({"name": "RSI", "state": "oversold", "lean": "bullish",
                        "to": f"oversold ({RSI_OVERSOLD:.0f})",
                        "note": f"RSI {r:.1f} is {RSI_OVERSOLD - r:.1f} below oversold ({RSI_OVERSOLD:.0f}) \u2014 stretched, bounce potential."})
        else:
            d_ob = RSI_OVERBOUGHT - r
            d_os = r - RSI_OVERSOLD
            lean = "bullish" if r > 50.0 + 1e-9 else "bearish" if r < 50.0 - 1e-9 else "neutral"
            nearer = (f"overbought ({RSI_OVERBOUGHT:.0f}), {d_ob:.1f} away" if d_ob <= d_os
                      else f"oversold ({RSI_OVERSOLD:.0f}), {d_os:.1f} away")
            out.append({"name": "RSI", "state": "neutral", "lean": lean, "to": nearer,
                        "note": f"RSI {r:.1f} \u2014 neutral, leaning {lean}; {d_ob:.1f} from overbought ({RSI_OVERBOUGHT:.0f}), {d_os:.1f} from oversold ({RSI_OVERSOLD:.0f})."})

    # MACD -> distance to a signal-line crossover is exactly |histogram|
    if macd_hist is not None:
        h = float(macd_hist)
        if h > 1e-12:
            out.append({"name": "MACD", "state": "above signal", "lean": "bullish", "to": "signal-line crossover",
                        "note": f"MACD is above its signal line (histogram +{h:.4f}); a bearish cross is {abs(h):.4f} away."})
        elif h < -1e-12:
            out.append({"name": "MACD", "state": "below signal", "lean": "bearish", "to": "signal-line crossover",
                        "note": f"MACD is below its signal line (histogram {h:.4f}); a bullish cross is {abs(h):.4f} away."})
        else:
            out.append({"name": "MACD", "state": "at crossover", "lean": "neutral", "to": "signal-line crossover",
                        "note": "MACD is sitting on its signal line \u2014 a crossover is imminent either way."})

    # Bollinger -> distance to the engine's computed bands
    if bb_upper is not None and bb_lower is not None and lp > 1e-10:
        up = float(bb_upper); dn = float(bb_lower); mid = (up + dn) / 2.0
        if lp >= up:
            out.append({"name": "Bollinger", "state": "at/above upper band", "lean": "bullish", "to": "upper band",
                        "note": f"Price {lp:.2f} is at/above the upper band ({up:.2f}) \u2014 strong push or overextension."})
        elif lp <= dn:
            out.append({"name": "Bollinger", "state": "at/below lower band", "lean": "bearish", "to": "lower band",
                        "note": f"Price {lp:.2f} is at/below the lower band ({dn:.2f}) \u2014 weak or oversold stretch."})
        else:
            d_up = (up - lp) / lp * 100.0
            d_dn = (lp - dn) / lp * 100.0
            lean = "bullish" if lp > mid + 1e-9 else "bearish" if lp < mid - 1e-9 else "neutral"
            nearer = (f"upper band ({up:.2f}), {d_up:.1f}% away" if d_up <= d_dn
                      else f"lower band ({dn:.2f}), {d_dn:.1f}% away")
            out.append({"name": "Bollinger", "state": "inside bands", "lean": lean, "to": nearer,
                        "note": f"Price {lp:.2f} inside the bands, leaning {lean}; {d_up:.1f}% from upper ({up:.2f}), {d_dn:.1f}% from lower ({dn:.2f})."})

    # Ichimoku -> distance to the cloud edges
    pvc = (price_vs_cloud or "UNKNOWN").upper()
    ct = float(cloud_top) if cloud_top is not None else 0.0
    cb = float(cloud_bot) if cloud_bot is not None else 0.0
    if pvc != "UNKNOWN" and lp > 1e-10 and ct > 1e-10:
        if pvc == "ABOVE":
            d = (lp - ct) / lp * 100.0
            out.append({"name": "Ichimoku", "state": "above cloud", "lean": "bullish", "to": "cloud top",
                        "note": f"Price is above the cloud (bullish); {d:.1f}% above the cloud top ({ct:.2f}) \u2014 a drop there would re-enter the cloud (neutral)."})
        elif pvc == "BELOW":
            d = (cb - lp) / lp * 100.0
            out.append({"name": "Ichimoku", "state": "below cloud", "lean": "bearish", "to": "cloud bottom",
                        "note": f"Price is below the cloud (bearish); {d:.1f}% below the cloud bottom ({cb:.2f})."})
        else:
            d_top = (ct - lp) / lp * 100.0
            d_bot = (lp - cb) / lp * 100.0
            tkc = (tk_cross or "").upper()
            lean = "bullish" if tkc == "BULL" else "bearish" if tkc == "BEAR" else "neutral"
            nearer = (f"cloud top ({ct:.2f}), {d_top:.1f}% away" if d_top <= d_bot
                      else f"cloud bottom ({cb:.2f}), {d_bot:.1f}% away")
            out.append({"name": "Ichimoku", "state": "inside cloud", "lean": lean, "to": nearer,
                        "note": f"Price is inside the cloud (no trend), leaning {lean}; a bullish signal is {d_top:.1f}% up at the cloud top ({ct:.2f}), bearish {d_bot:.1f}% down at the bottom ({cb:.2f})."})

    # Elliott -> surface the engine's OWN phase + the next structural step (no ratios)
    ph = (wave_phase or "NONE").upper()
    ew_map = {
        "W3_COMPLETE": ("wave 3 complete", "Wave 3 complete \u2014 expect a Wave 4 pullback, then a Wave 5 advance."),
        "W5_REVERSAL": ("wave 5 reversal", "Wave 5 reversal zone \u2014 a major top/bottom may be forming; an A-B-C correction typically follows."),
    }
    if ph in ew_map:
        st, note = ew_map[ph]
        out.append({"name": "Elliott Wave", "state": st, "lean": "neutral", "to": "next wave", "note": note})
    elif ph != "NONE":
        out.append({"name": "Elliott Wave", "state": ph.lower(), "lean": "neutral", "to": "next wave",
                    "note": f"Current Elliott phase: {ph}."})

    return out


def compute_andrews_pitchfork(                                    # <- NEW [PROX]
    swings: List[Tuple[int, float]],
    df: pd.DataFrame,
) -> Optional[Dict[str, Any]]:
    """Andrews Pitchfork from the three most-recent swing pivots (pure geometry).

    Median line runs from the oldest of the three pivots (P0) through the midpoint of
    the next two (P1, P2); the two rails are parallels through P1 and P2. Returns the
    median / upper / lower values at the latest bar plus where price sits, or None when
    there are fewer than three pivots. No domain ratios are used -- this is straight-line
    geometry, so nothing is invented.
    """
    if not swings or len(swings) < 3 or df is None or df.empty:
        return None
    try:
        p0_x, p0_y = float(swings[-3][0]), float(swings[-3][1])
        p1_x, p1_y = float(swings[-2][0]), float(swings[-2][1])
        p2_x, p2_y = float(swings[-1][0]), float(swings[-1][1])
        mx = (p1_x + p2_x) / 2.0
        my = (p1_y + p2_y) / 2.0
        dx = mx - p0_x
        if abs(dx) < 1e-9:
            return None
        slope = (my - p0_y) / dx
        x_now = float(len(df) - 1)
        median = p0_y + slope * (x_now - p0_x)
        line1  = p1_y + slope * (x_now - p1_x)
        line2  = p2_y + slope * (x_now - p2_x)
        upper  = max(line1, line2)
        lower  = min(line1, line2)
        lp = float(df["close"].iloc[-1])
        if lp > upper + 1e-9:
            position = "above upper rail"
        elif lp < lower - 1e-9:
            position = "below lower rail"
        elif lp > median + 1e-9:
            position = "upper half"
        elif lp < median - 1e-9:
            position = "lower half"
        else:
            position = "on median"
        rail1_at_start = p1_y + slope * (p0_x - p1_x)   # <- ADDED [PF-DRAW]: rail values at the left anchor x
        rail2_at_start = p2_y + slope * (p0_x - p2_x)
        return {"median": round(median, 4), "upper": round(upper, 4), "lower": round(lower, 4),
                "position": position, "last_price": round(lp, 4),
                "anchor_idx": [int(p0_x), int(p1_x), int(p2_x)],
                "lines_idx": {                                 # <- ADDED [PF-DRAW]: drawable (bar_index, value) endpoints
                    "median": [[int(p0_x), round(p0_y, 4)], [int(x_now), round(median, 4)]],
                    "rail1":  [[int(p0_x), round(rail1_at_start, 4)], [int(x_now), round(line1, 4)]],
                    "rail2":  [[int(p0_x), round(rail2_at_start, 4)], [int(x_now), round(line2, 4)]],
                }}
    except (ValueError, TypeError, ZeroDivisionError, IndexError) as exc:
        logger.warning("pitchfork: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9 — ICHIMOKU CLOUD
# Periods: Tenkan=9, Kijun=26, Senkou B=52, shift=26 — user document
# Confluence points per user document
# ═══════════════════════════════════════════════════════════════════════════

def compute_ichimoku(df: pd.DataFrame) -> IchimokuResult:
    """
    Computes all Ichimoku Cloud components.
    All periods from user master prompt document.
    All confluence point values from user document.
    """
    empty: IchimokuResult = {
        "tenkan": 0.0, "kijun": 0.0, "senkou_a": 0.0, "senkou_b": 0.0,
        "cloud_top": 0.0, "cloud_bot": 0.0, "cloud_color": "UNKNOWN",
        "cloud_thick": False, "price_vs_cloud": "UNKNOWN",
        "chikou_signal": "NEUTRAL", "tk_cross": "NEUTRAL", "conf_pts": 0,
    }
    if df.empty or len(df) < ICH_SENKOU_B + ICH_SHIFT:
        return empty

    hi = df["high"]  if "high"  in df.columns else df["close"]
    lo = df["low"]   if "low"   in df.columns else df["close"]
    cl = df["close"]

    tenkan   = (hi.rolling(ICH_TENKAN).max()    + lo.rolling(ICH_TENKAN).min())    / 2.0
    kijun    = (hi.rolling(ICH_KIJUN).max()     + lo.rolling(ICH_KIJUN).min())     / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).shift(ICH_SHIFT)
    senkou_b = (
        (hi.rolling(ICH_SENKOU_B).max() + lo.rolling(ICH_SENKOU_B).min()) / 2.0
    ).shift(ICH_SHIFT)
    chikou   = cl.shift(-ICH_SHIFT)

    def _last(s: pd.Series) -> float:
        d = s.dropna()
        return float(d.iloc[-1]) if len(d) > 0 else 0.0

    tk_v = _last(tenkan)
    kj_v = _last(kijun)
    sa_v = _last(senkou_a)
    sb_v = _last(senkou_b)
    cur  = _last(cl)

    if tk_v < 1e-10 or kj_v < 1e-10 or sa_v < 1e-10 or sb_v < 1e-10:
        return empty

    cloud_top   = max(sa_v, sb_v)
    cloud_bot   = min(sa_v, sb_v)
    cloud_color = "GREEN" if sa_v > sb_v else "RED"
    cloud_thick = (cloud_top - cloud_bot) / cur > 0.02 if cur > 1e-10 else False

    if cur > cloud_top:
        price_vs_cloud = "ABOVE"
    elif cur < cloud_bot:
        price_vs_cloud = "BELOW"
    else:
        price_vs_cloud = "INSIDE"

    tk_prev  = float(tenkan.dropna().iloc[-2]) if len(tenkan.dropna()) >= 2 else tk_v
    kj_prev  = float(kijun.dropna().iloc[-2])  if len(kijun.dropna())  >= 2 else kj_v
    if tk_v > kj_v and tk_prev <= kj_prev:
        tk_cross = "BULL"
    elif tk_v < kj_v and tk_prev >= kj_prev:
        tk_cross = "BEAR"
    else:
        tk_cross = "NEUTRAL"

    # Chikou vs price 26 bars ago
    chikou_v    = float(chikou.dropna().iloc[-ICH_SHIFT - 1]) if len(chikou.dropna()) > ICH_SHIFT else 0.0
    price_26ago = float(cl.iloc[-ICH_SHIFT - 1]) if len(cl) > ICH_SHIFT else cur
    if chikou_v > price_26ago and chikou_v > cloud_top:
        chikou_signal = "BULL_CONF"
    elif chikou_v < price_26ago and chikou_v < cloud_bot:
        chikou_signal = "BEAR_CONF"
    else:
        chikou_signal = "WEAK"

    # Confluence scoring — user document values
    conf_pts = 0
    if price_vs_cloud == "ABOVE":
        conf_pts += CS_ICH_PRICE_ABOVE
    elif price_vs_cloud == "BELOW":
        conf_pts += CS_ICH_PRICE_BELOW

    conf_pts += CS_ICH_CLOUD_THICK if cloud_thick else CS_ICH_CLOUD_THIN

    if tk_cross == "BULL":
        conf_pts += CS_ICH_CROSS_ABOVE
    elif tk_cross == "BEAR":
        conf_pts += CS_ICH_CROSS_BELOW

    if chikou_signal == "BULL_CONF":
        conf_pts += CS_ICH_CHIKOU_BULL
    elif chikou_signal == "BEAR_CONF":
        conf_pts += CS_ICH_CHIKOU_BEAR

    return {
        "tenkan":        round(tk_v,    4),
        "kijun":         round(kj_v,    4),
        "senkou_a":      round(sa_v,    4),
        "senkou_b":      round(sb_v,    4),
        "cloud_top":     round(cloud_top, 4),
        "cloud_bot":     round(cloud_bot, 4),
        "cloud_color":   cloud_color,
        "cloud_thick":   cloud_thick,
        "price_vs_cloud": price_vs_cloud,
        "chikou_signal": chikou_signal,
        "tk_cross":      tk_cross,
        "conf_pts":      conf_pts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10 — INDICATOR SUITE
# All periods from user document. All CS values from user document.
# ═══════════════════════════════════════════════════════════════════════════

def compute_all_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes RSI(14), MACD(12/26/9), Bollinger(20,2), EMA(9/21/50/200),
    Stochastic(14/3/3), ATR(14), OBV, VWAP.
    All periods and confluence point values from user master prompt document.
    """
    if df.empty or len(df) < 30:
        return {"conf_pts": 0, "series": {}}

    cl  = df["close"]
    hi  = df["high"]   if "high"   in df.columns else cl
    lo  = df["low"]    if "low"    in df.columns else cl
    vol = df["volume"] if "volume" in df.columns else pd.Series(0.0, index=df.index)

    series: Dict[str, pd.Series] = {}
    conf_pts = 0
    cur      = float(cl.iloc[-1])
    cl_prev  = float(cl.iloc[-2]) if len(cl) >= 2 else cur

    # ── EMA 9/21/50/200 ──────────────────────────────────────────────────
    for p in MA_PERIODS:
        series[f"ema_{p}"] = cl.ewm(span=p, adjust=False).mean()

    ema_9   = float(series["ema_9"].iloc[-1])
    ema_21  = float(series["ema_21"].iloc[-1])
    ema_50  = float(series["ema_50"].iloc[-1])
    ema_200 = float(series["ema_200"].iloc[-1])

    if cur > ema_200:
        conf_pts += CS_MA_ABOVE_200
    else:
        conf_pts += CS_MA_BELOW_200

    if ema_9 > ema_21 > ema_50 > ema_200:
        conf_pts += CS_MA_BULL_ALIGN
    elif ema_9 < ema_21 < ema_50 < ema_200:
        conf_pts += CS_MA_BEAR_ALIGN

    ema_50_prev  = float(series["ema_50"].iloc[-2])  if len(series["ema_50"]) >= 2 else ema_50
    ema_200_prev = float(series["ema_200"].iloc[-2]) if len(series["ema_200"]) >= 2 else ema_200
    if ema_50_prev <= ema_200_prev and ema_50 > ema_200:
        conf_pts += CS_MA_GOLDEN_CROSS
    elif ema_50_prev >= ema_200_prev and ema_50 < ema_200:
        conf_pts += CS_MA_DEATH_CROSS

    # ── RSI(14) ──────────────────────────────────────────────────────────
    delta    = cl.diff()
    gain     = delta.clip(lower=0.0)
    loss     = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(com=RSI_PERIOD - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi      = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)
    series["rsi"] = rsi
    rsi_val  = float(rsi.iloc[-1])

    if rsi_val < RSI_OVERSOLD and cur > cl_prev:
        conf_pts += CS_RSI_OVERSOLD_UP
    if rsi_val > RSI_OVERBOUGHT and cur < cl_prev:
        conf_pts += CS_RSI_OB_DOWN

    if len(cl) >= 20:
        cl_hi20  = float(cl.tail(20).max())
        rsi_hi20 = float(rsi.tail(20).max())
        cl_lo20  = float(cl.tail(20).min())
        rsi_lo20 = float(rsi.tail(20).min())
        if cur >= cl_hi20 * 0.995 and rsi_val < rsi_hi20 * 0.97:
            conf_pts += CS_RSI_BEAR_DIV
        if cur <= cl_lo20 * 1.005 and rsi_val > rsi_lo20 * 1.03:
            conf_pts += CS_RSI_BULL_DIV

    # ── MACD(12/26/9) ────────────────────────────────────────────────────
    ema12  = cl.ewm(span=MACD_FAST,   adjust=False).mean()
    ema26  = cl.ewm(span=MACD_SLOW,   adjust=False).mean()
    macd_l = ema12 - ema26
    sig_l  = macd_l.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hist   = macd_l - sig_l
    series["macd_line"]   = macd_l
    series["macd_signal"] = sig_l
    series["macd_hist"]   = hist

    macd_v  = float(macd_l.iloc[-1])
    sig_v   = float(sig_l.iloc[-1])
    hist_v  = float(hist.iloc[-1])
    macd_p  = float(macd_l.iloc[-2]) if len(macd_l) >= 2 else macd_v
    sig_p   = float(sig_l.iloc[-2]) if len(sig_l) >= 2 else sig_v
    hist_p  = float(hist.iloc[-2]) if len(hist) >= 2 else hist_v

    if macd_p <= sig_p and macd_v > sig_v:
        conf_pts += CS_MACD_CROSS_BULL
    elif macd_p >= sig_p and macd_v < sig_v:
        conf_pts += CS_MACD_CROSS_BEAR
    if hist_v > 0 and hist_v > hist_p:
        conf_pts += CS_MACD_HIST_EXP_UP
    elif hist_v > 0 and hist_v < hist_p:
        conf_pts += CS_MACD_HIST_CONTR_UP

    # ── Bollinger Bands(20,2) ─────────────────────────────────────────────
    bb_mid = cl.rolling(BB_PERIOD).mean()
    bb_std = cl.rolling(BB_PERIOD).std(ddof=0)
    bb_up  = bb_mid + BB_STD_DEV * bb_std
    bb_dn  = bb_mid - BB_STD_DEV * bb_std
    series["bb_upper"] = bb_up
    series["bb_mid"]   = bb_mid
    series["bb_lower"] = bb_dn

    bb_up_v  = float(bb_up.iloc[-1])
    bb_dn_v  = float(bb_dn.iloc[-1])
    bb_up_p  = float(bb_up.iloc[-2]) if len(bb_up) >= 2 else bb_up_v
    bb_dn_p  = float(bb_dn.iloc[-2]) if len(bb_dn) >= 2 else bb_dn_v
    bb_width = bb_up_v - bb_dn_v
    bb_w_p   = bb_up_p - bb_dn_p

    if cur <= bb_dn_v * 1.005 and cur > cl_prev:
        conf_pts += CS_BB_BOUNCE_LOWER
    if cur >= bb_up_v * 0.995 and cur < cl_prev:
        conf_pts += CS_BB_BOUNCE_UPPER
    if bb_w_p > 1e-10:
        conf_pts += CS_BB_EXPANDING if bb_width > bb_w_p else CS_BB_CONTRACTING

    # ── Stochastic(14/3/3) ───────────────────────────────────────────────
    lo14    = lo.rolling(STOCH_K).min()
    hi14    = hi.rolling(STOCH_K).max()
    denom   = (hi14 - lo14).replace(0.0, float("nan"))
    stoch_k = ((cl - lo14) / denom * 100.0).fillna(50.0)
    stoch_d = stoch_k.rolling(STOCH_D).mean()
    series["stoch_k"] = stoch_k
    series["stoch_d"] = stoch_d

    sk_v  = float(stoch_k.iloc[-1])
    sd_v  = float(stoch_d.iloc[-1])
    sk_p  = float(stoch_k.iloc[-2]) if len(stoch_k) >= 2 else sk_v
    sd_p  = float(stoch_d.iloc[-2]) if len(stoch_d) >= 2 else sd_v

    if sk_p <= sd_p and sk_v > sd_v and sk_v < STOCH_OS + 5.0:
        conf_pts += CS_STOCH_CROSS_UP_OS
    if sk_p >= sd_p and sk_v < sd_v and sk_v > STOCH_OB - 5.0:
        conf_pts += CS_STOCH_CROSS_DN_OB

    # ── ATR(14) ───────────────────────────────────────────────────────────
    tr = pd.DataFrame({
        "hl": hi - lo,
        "hc": (hi - cl.shift(1)).abs(),
        "lc": (lo - cl.shift(1)).abs(),
    }).max(axis=1)
    atr      = tr.ewm(span=ATR_PERIOD, adjust=False).mean()
    series["atr"] = atr
    atr_v    = float(atr.iloc[-1])
    atr_p    = float(atr.iloc[-2]) if len(atr) >= 2 else atr_v
    atr_52wh = float(atr.tail(252).max()) if len(atr) >= 252 else float(atr.max())

    conf_pts += CS_ATR_EXPANDING if atr_v > atr_p else CS_ATR_CONTRACTING
    if atr_v >= atr_52wh * 0.95:
        conf_pts += CS_ATR_52W_HIGH

    # ── OBV ───────────────────────────────────────────────────────────────
    obv_vals: List[float] = [0.0]
    cl_arr   = cl.values
    vol_arr  = vol.values
    for i in range(1, len(cl_arr)):
        prev_obv = obv_vals[-1]
        if cl_arr[i] > cl_arr[i - 1]:
            obv_vals.append(prev_obv + float(vol_arr[i]))
        elif cl_arr[i] < cl_arr[i - 1]:
            obv_vals.append(prev_obv - float(vol_arr[i]))
        else:
            obv_vals.append(prev_obv)
    obv = pd.Series(obv_vals, index=df.index)
    series["obv"] = obv

    if len(obv) >= 20:
        obv_now  = float(obv.iloc[-1])
        obv_hi20 = float(obv.tail(20).max())
        obv_p20  = float(obv.iloc[-20])
        cl_p20   = float(cl.iloc[-20])
        if obv_now > obv_hi20 * 0.98:
            conf_pts += CS_OBV_BULL
        if obv_now > obv_p20 and cur < cl_p20:
            conf_pts += CS_OBV_HIDDEN_BULL
        if obv_now < obv_p20 and cur > cl_p20:
            conf_pts += CS_OBV_HIDDEN_BEAR

    # ── VWAP ──────────────────────────────────────────────────────────────
    vol_sum = float(vol.sum())
    if vol_sum > 1e-10:
        vwap_num = (cl * vol).cumsum()
        vwap_den = vol.cumsum().replace(0.0, float("nan"))
        vwap     = vwap_num / vwap_den
        series["vwap"] = vwap
        vwap_v   = float(vwap.iloc[-1])
        vwap_p   = float(vwap.iloc[-2]) if len(vwap) >= 2 else vwap_v
        cl_pp    = float(cl.iloc[-3])   if len(cl) >= 3 else cl_prev
        if cl_prev <= vwap_p and cur > vwap_v:
            conf_pts += CS_VWAP_BREAK_UP
        if cl_prev >= vwap_p and cur <= vwap_v:
            conf_pts += CS_VWAP_BREAK_DOWN
    else:
        series["vwap"] = pd.Series(float("nan"), index=df.index)
        vwap_v = 0.0

    return {
        "conf_pts":   conf_pts,
        "series":     series,
        "rsi_val":    round(rsi_val, 2),
        "macd_val":   round(macd_v, 4),
        "macd_sig":   round(sig_v,  4),
        "macd_hist":  round(hist_v, 4),
        "bb_upper":   round(bb_up_v, 4),
        "bb_lower":   round(bb_dn_v, 4),
        "bb_width":   round(bb_width, 4),
        "stoch_k":    round(sk_v,   2),
        "stoch_d":    round(sd_v,   2),
        "atr":        round(atr_v,  4),
        "ema_9":      round(ema_9,  4),
        "ema_21":     round(ema_21, 4),
        "ema_50":     round(ema_50, 4),
        "ema_200":    round(ema_200, 4),
        "vwap":       round(vwap_v, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11 — PRZ CONFLUENCE (6 methods — user document)
# ═══════════════════════════════════════════════════════════════════════════

def compute_prz_confluence(
    df:        pd.DataFrame,
    swings:    List[Tuple[int, float]],
    harmonics: List[HarmonicResult],
    ich:       IchimokuResult,
    ind:       Dict[str, Any],
) -> PRZResult:
    """
    Computes PRZ (Potential Reversal Zone) from 6 methods:
      1. Fibonacci extensions (Frost & Prechter ratios)
      2. Harmonic pattern PRZ zones (Carney ratios)
      3. Ichimoku cloud projections (user document periods)
      4. Pivot points
      5. VWAP projection
      6. Previous swing highs

    Confidence: 3+ methods = 85%, 2 = 75%, 1 = 60% — user document.
    Stop: 1.5 × ATR below entry — user document.
    Staged exit: T1=50%, T2=30%, T3=20% — user document.
    Minimum R:R = 2.0 — user document.
    """
    empty: PRZResult = {
        "price_zone_low": 0.0, "price_zone_high": 0.0,
        "methods_count": 0, "confidence": 0.0, "methods": [],
        "target_1": 0.0, "target_2": 0.0, "target_3": 0.0,
        "stop_loss": 0.0, "entry": 0.0, "rr_ratio": 0.0, "rr_valid": False,
    }
    if df.empty or len(df) < 30:
        return empty

    cur       = float(df["close"].iloc[-1])
    atr_val   = ind.get("atr", 0.0)
    stop_loss = cur - ATR_STOP_MULTIPLIER * atr_val if atr_val > 1e-10 else cur * 0.97

    candidates: List[float] = []

    # Method 1: Fibonacci extensions from swing range [PF]
    if len(swings) >= 2:
        s_lo = min(p for _, p in swings[-5:]) if len(swings) >= 5 else min(p for _, p in swings)
        s_hi = max(p for _, p in swings[-5:]) if len(swings) >= 5 else max(p for _, p in swings)
        rng  = s_hi - s_lo
        for ext in FIB_EXTEND:
            t = s_lo + rng * ext
            if t > cur * 1.001:
                candidates.append(t)

    # Method 2: Harmonic PRZ zones (Carney)
    for h in harmonics:
        if h["found"] and h["d_price"] > cur * 1.001:
            candidates.append(h["d_price"])

    # Method 3: Ichimoku cloud projection
    for lvl in (ich["senkou_a"], ich["senkou_b"]):
        if lvl > cur * 1.001:
            candidates.append(lvl)

    # Method 4: Pivot points
    if len(df) >= 2:
        ph    = float(df["high"].iloc[-2])  if "high" in df.columns else cur
        pl    = float(df["low"].iloc[-2])   if "low"  in df.columns else cur
        pc    = float(df["close"].iloc[-2])
        pivot = (ph + pl + pc) / 3.0
        r1    = pivot * 2.0 - pl
        r2    = pivot + (ph - pl)
        if r1 > cur * 1.001:
            candidates.append(r1)
        if r2 > cur * 1.001:
            candidates.append(r2)

    # Method 5: VWAP projection
    vwap_series = ind.get("series", {}).get("vwap")
    if vwap_series is not None and not pd.isna(vwap_series).all():
        vwap_last = float(vwap_series.dropna().iloc[-1])
        if vwap_last > cur * 1.001:
            candidates.append(vwap_last * 1.005)

    # Method 6: Previous swing highs (50 bars)
    if "high" in df.columns and len(df) >= 50:
        for val in df["high"].rolling(5).max().tail(50).dropna().values:
            fv = float(val)
            if fv > cur * 1.005:
                candidates.append(fv)

    if not candidates:
        return empty

    # Cluster within 2% of each other
    sorted_cands = sorted([t for t in candidates if t > cur * 1.001])
    if not sorted_cands:
        return empty

    clusters: List[List[float]] = []
    for p in sorted_cands:
        placed = False
        for grp in clusters:
            if grp and abs(p - grp[0]) / grp[0] <= 0.02 if grp[0] > 1e-10 else False:
                grp.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])

    cluster_info = sorted(
        [(float(np.mean(g)), len(g)) for g in clusters],
        key=lambda x: x[1], reverse=True,
    )

    if not cluster_info:
        return empty

    while len(cluster_info) < 3:
        last = cluster_info[-1][0]
        cluster_info.append((last * 1.03, 0))

    t1, t1_cnt = cluster_info[0]
    t2         = cluster_info[1][0] if cluster_info[1][0] > t1 else t1 * 1.03
    t3         = cluster_info[2][0] if cluster_info[2][0] > t2 else t2 * 1.03

    confidence  = PRZ_CONFIDENCE.get(min(t1_cnt, 6), 0.60)
    prz_margin  = t1 * 0.01
    rr_reward   = t3 - cur
    rr_risk     = cur - stop_loss
    rr_ratio    = safe_ratio(rr_reward, rr_risk)
    rr_valid    = rr_ratio >= MIN_RR_RATIO

    return {
        "price_zone_low":  round(t1 - prz_margin, 4),
        "price_zone_high": round(t1 + prz_margin, 4),
        "methods_count":   t1_cnt,
        "confidence":      round(confidence, 3),
        "methods":         [f"M{i+1}" for i in range(min(t1_cnt, 6))],
        "target_1":        round(t1, 4),
        "target_2":        round(t2, 4),
        "target_3":        round(t3, 4),
        "stop_loss":       round(stop_loss, 4),
        "entry":           round(cur, 4),
        "rr_ratio":        round(rr_ratio, 2),
        "rr_valid":        rr_valid,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 12 — MACRO REGIME, SENTIMENT, INSTITUTIONAL, MASTER SIGNAL
# ═══════════════════════════════════════════════════════════════════════════

def classify_macro_regime(macro: Dict[str, Any]) -> Tuple[str, int]:
    """
    Classifies macro into 4 quadrants from user document:
      Q1 GOLDILOCKS: Growth↑, Inflation↓ → +15 pts
      Q2 RISING RATES: Growth↑, Inflation↑ → 0 pts
      Q3 DEFLATION: Growth↓, Inflation↓ → 0 pts
      Q4 STAGFLATION: Growth↓, Inflation↑ → -20 pts
    """
    if not macro:
        return "UNKNOWN", 0
    spy_d = macro.get("^GSPC", {})
    tnx_d = macro.get("^TNX", {})
    gld_d = macro.get("GLD", {})
    growth_up    = spy_d.get("chg_1m", 0.0) > 0.0
    inflation_up = (tnx_d.get("chg_1m", 0.0) + gld_d.get("chg_1m", 0.0)) > 0.0
    if growth_up and not inflation_up:
        return "Q1", CS_MACRO_GOLDILOCKS
    elif growth_up and inflation_up:
        return "Q2", 0
    elif not growth_up and not inflation_up:
        return "Q3", 0
    else:
        return "Q4", CS_MACRO_STAGFLATION


def score_sentiment_via_groq(ticker: str, company_name: str, api_key: str) -> Tuple[float, int]:
    """
    Sentiment scoring via Groq LLaMA (FinBERT not assumed installed).
    Returns (score -1.0 to +1.0, confluence_pts).
    """
    if not _GROQ_AVAILABLE or not api_key:
        return 0.0, 0
    try:
        import json
        client = _Groq(api_key=api_key)
        resp   = client.chat.completions.create(
            model=GROQ_MODEL, max_tokens=200,
            messages=[{
                "role": "system",
                "content": (
                    "You are a financial sentiment analyst. "
                    "Return ONLY valid JSON: "
                    '{"score": float -1.0 to 1.0, "classification": string, "confidence": float}. '
                    "No markdown. No other text."
                ),
            }, {
                "role": "user",
                "content": (
                    f"Assess current market sentiment for {company_name} ({ticker}) "
                    "based on fundamental performance, analyst consensus, positioning. JSON only."
                ),
            }],
        )
        raw  = (resp.choices[0].message.content or "{}").strip()
        raw  = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        score = max(-1.0, min(1.0, float(data.get("score", 0.0))))
        pts   = CS_SENTIMENT_BULL if score > 0.5 else (CS_SENTIMENT_BEAR if score < -0.3 else 0)
        return round(score, 3), pts
    except Exception as exc:
        logger.debug("Sentiment [%s]: %s", ticker, exc)
        return 0.0, 0


def score_institutional(inst_data: Dict[str, Any]) -> int:
    """Scores institutional ownership from yfinance proxy. User document thresholds."""
    conf_pts    = 0
    inst_pct    = inst_data.get("inst_pct", 0.0)
    insider_pct = inst_data.get("insider_pct", 0.0)
    if inst_pct > 70.0:
        conf_pts += CS_INST_INC_HIGH
    elif inst_pct > 50.0:
        conf_pts += CS_INST_INC_LOW
    elif inst_pct < 10.0:
        conf_pts += CS_INST_DEC_HIGH
    if insider_pct > 10.0:
        conf_pts += CS_INSIDER_BUY // 2
    return conf_pts


def compute_master_signal(
    ticker:    str,
    df:        pd.DataFrame,
    info:      Dict[str, Any],
    macro:     Dict[str, Any],
    inst_data: Dict[str, Any],
    api_key:   str,
) -> MasterSignal:
    """
    Orchestrates all 10 analysis engines → master confluence signal.
    Confluence score range: ~-200 to +200.
    Signal thresholds: STRONG BUY ≥80, BUY ≥50, HOLD ≥10, SELL ≥-30, STRONG SELL <-30.
    """
    warnings: List[str] = []
    total_pts = 0

    close  = df["close"] if not df.empty else pd.Series(dtype=float)
    swings = compute_zigzag(close) if not close.empty else []
    ew_res = analyse_elliott_waves(swings)
    ew_pts = ew_res["conf_pts"]
    total_pts += ew_pts

    # 10-pattern harmonic scan
    harm_list = scan_all_harmonic_patterns(swings)
    harm_pts  = sum(h["conf_pts"] for h in harm_list if h["found"])
    total_pts += harm_pts

    ich     = compute_ichimoku(df)
    ich_pts = ich["conf_pts"]
    total_pts += ich_pts

    ind     = compute_all_indicators(df)
    ind_pts = ind.get("conf_pts", 0)
    total_pts += ind_pts

    prz = compute_prz_confluence(df, swings, harm_list, ich, ind)
    if not prz["rr_valid"] and prz["entry"] > 1e-10:
        warnings.append(f"R:R = {prz['rr_ratio']:.1f} — below minimum {MIN_RR_RATIO:.0f}:1. Trade rejected.")

    quad, macro_pts = classify_macro_regime(macro)
    total_pts += macro_pts
    if quad == "Q4":
        warnings.append("STAGFLATION regime — reduce equity exposure.")

    company = info.get("name", ticker)
    sent_score, sent_pts = score_sentiment_via_groq(ticker, company, api_key)
    total_pts += sent_pts

    inst_pts   = score_institutional(inst_data)
    total_pts += inst_pts

    if total_pts >= 80:
        signal = "STRONG BUY"
    elif total_pts >= 50:
        signal = "BUY"
    elif total_pts >= 10:
        signal = "HOLD"
    elif total_pts >= -30:
        signal = "SELL"
    else:
        signal = "STRONG SELL"

    confidence_pct = min(100.0, max(0.0, (total_pts + 200.0) / 4.0))

    return {
        "ticker":             ticker,
        "timestamp":          datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "signal":             signal,
        "confluence_score":   total_pts,
        "confidence_pct":     round(confidence_pct, 1),
        "elliott_pts":        ew_pts,
        "harmonic_pts":       harm_pts,
        "ichimoku_pts":       ich_pts,
        "indicator_pts":      ind_pts,
        "sentiment_pts":      sent_pts,
        "institutional_pts":  inst_pts,
        "macro_pts":          macro_pts,
        "prz":                prz if prz["entry"] > 1e-10 else None,
        "macro_quadrant":     quad,
        "risk_warnings":      warnings,
    }
# ═══════════════════════════════════════════════════════════════════════════
# SECTION 13 — STREAMLIT UI
# All signal thresholds, confluence point labels, and color mappings are
# derived exclusively from Section 4 constants — none invented here.
# No st.set_page_config() — called once in app.py per project rule.
# ═══════════════════════════════════════════════════════════════════════════

# ── Signal colour map (display only — values from Section 12 thresholds) ──
_SIGNAL_COLORS: Dict[str, str] = {
    "STRONG BUY":  "#00FF88",
    "BUY":         "#00CC66",
    "HOLD":        "#FFD700",
    "SELL":        "#FF8C00",
    "STRONG SELL": "#FF3333",
}

_SIGNAL_ICONS: Dict[str, str] = {
    "STRONG BUY":  "🚀",
    "BUY":         "📈",
    "HOLD":        "⏸️",
    "SELL":        "📉",
    "STRONG SELL": "🔻",
}

# ── Plotly theme constants (display only) ──────────────────────────────────
_BG        = "#0D1117"
_GRID      = "#1C2333"
_TEXT      = "#E6EDF3"
_BULL_CANDLE = "#00FF88"
_BEAR_CANDLE = "#FF3333"


# ═══════════════════════════════════════════════════════════════════════════
# CHART BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _build_chart(
    df:      pd.DataFrame,
    ticker:  str,
    ind:     Dict[str, Any],
    ich:     IchimokuResult,
    swings:  List[Tuple[int, float]],
    harmonics: List[HarmonicResult],
    prz:     PRZResult,
) -> go.Figure:
    """
    Builds 4-panel Plotly chart:
      Row 1 (60%): Candlestick + EMA9/21/50/200 + Ichimoku cloud +
                   Bollinger Bands + VWAP + ZigZag swings +
                   Harmonic PRZ zones + PRZ targets
      Row 2 (15%): RSI(14) with OB/OS lines
      Row 3 (15%): MACD histogram + line + signal
      Row 4 (10%): Volume
    All series references use ind["series"] populated by compute_all_indicators.
    """
    if df.empty:
        return go.Figure()

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.60, 0.15, 0.15, 0.10],
        vertical_spacing=0.02,
    )

    dates = df.index
    series = ind.get("series", {})

    # ── Row 1: Candlestick ────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=dates,
        open=df["open"]  if "open"  in df.columns else df["close"],
        high=df["high"]  if "high"  in df.columns else df["close"],
        low=df["low"]    if "low"   in df.columns else df["close"],
        close=df["close"],
        name=ticker,
        increasing_line_color=_BULL_CANDLE,
        decreasing_line_color=_BEAR_CANDLE,
        increasing_fillcolor=_BULL_CANDLE,
        decreasing_fillcolor=_BEAR_CANDLE,
        showlegend=False,
    ), row=1, col=1)

    # ── Ichimoku cloud ────────────────────────────────────────────────────
    sa_series = ((
        (df["high"].rolling(ICH_TENKAN).max() + df["low"].rolling(ICH_TENKAN).min()) / 2.0 +
        (df["high"].rolling(ICH_KIJUN).max()  + df["low"].rolling(ICH_KIJUN).min())  / 2.0
    ) / 2.0).shift(ICH_SHIFT)

    sb_series = (
        (df["high"].rolling(ICH_SENKOU_B).max() + df["low"].rolling(ICH_SENKOU_B).min()) / 2.0
    ).shift(ICH_SHIFT)

    cloud_color = ich.get("cloud_color", "GREEN")
    fill_color  = "rgba(0,255,136,0.08)" if cloud_color == "GREEN" else "rgba(255,51,51,0.08)"

    fig.add_trace(go.Scatter(
        x=dates, y=sa_series,
        line={"color": "rgba(0,255,136,0.4)", "width": 1},
        name="Senkou A", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=sb_series,
        line={"color": "rgba(255,51,51,0.4)", "width": 1},
        fill="tonexty", fillcolor=fill_color,
        name="Senkou B", showlegend=False,
    ), row=1, col=1)

    # ── EMA lines ─────────────────────────────────────────────────────────
    ema_styles: List[Tuple[int, str, float]] = [
        (9,   "#00BFFF", 1.0),
        (21,  "#FF69B4", 1.0),
        (50,  "#FFD700", 1.5),
        (200, "#FF8C00", 2.0),
    ]
    for period, color, width in ema_styles:
        key = f"ema_{period}"
        if key in series:
            fig.add_trace(go.Scatter(
                x=dates, y=series[key],
                line={"color": color, "width": width},
                name=f"EMA{period}", showlegend=True,
            ), row=1, col=1)

    # ── Bollinger Bands ───────────────────────────────────────────────────
    for key, name in (("bb_upper", "BB Upper"), ("bb_lower", "BB Lower")):
        if key in series:
            fig.add_trace(go.Scatter(
                x=dates, y=series[key],
                line={"color": "rgba(100,100,255,0.5)", "width": 1, "dash": "dot"},
                name=name, showlegend=False,
            ), row=1, col=1)

    # ── VWAP ──────────────────────────────────────────────────────────────
    if "vwap" in series:
        fig.add_trace(go.Scatter(
            x=dates, y=series["vwap"],
            line={"color": "#FF00FF", "width": 1.5, "dash": "dash"},
            name="VWAP", showlegend=True,
        ), row=1, col=1)

    # ── ZigZag swings ─────────────────────────────────────────────────────
    if len(swings) >= 2:
        zz_idx    = [i for i, _ in swings]
        zz_prices = [p for _, p in swings]
        zz_dates  = [dates[min(i, len(dates) - 1)] for i in zz_idx]
        fig.add_trace(go.Scatter(
            x=zz_dates, y=zz_prices,
            mode="lines+markers",
            line={"color": "rgba(255,255,255,0.3)", "width": 1, "dash": "dot"},
            marker={"size": 5, "color": "#FFFFFF"},
            name="ZigZag", showlegend=False,
        ), row=1, col=1)

    # ── Harmonic PRZ zones ────────────────────────────────────────────────
    cur = float(df["close"].iloc[-1])
    last_date = dates[-1]
    for h in harmonics:
        if h["found"] and h["d_price"] > 1e-10:
            color = "#00FF88" if h["d_price"] > cur else "#FF3333"
            fig.add_hline(
                y=h["d_price"],
                line_dash="dot",
                line_color=color,
                line_width=1,
                annotation_text=f"{h['pattern']} D ({h['quality']})",
                annotation_font_color=color,
                annotation_font_size=9,
                row=1, col=1,
            )

    # ── PRZ target lines ──────────────────────────────────────────────────
    if prz and prz.get("entry", 0.0) > 1e-10:
        for label, val, color in (
            ("T1", prz["target_1"], "#00FF88"),
            ("T2", prz["target_2"], "#00CC66"),
            ("T3", prz["target_3"], "#009944"),
            ("SL", prz["stop_loss"], "#FF3333"),
        ):
            fig.add_hline(
                y=val,
                line_dash="dash",
                line_color=color,
                line_width=1.5,
                annotation_text=f"{label}: {val:.2f}",
                annotation_font_color=color,
                annotation_font_size=10,
                row=1, col=1,
            )

    # ── Row 2: RSI ────────────────────────────────────────────────────────
    if "rsi" in series:
        fig.add_trace(go.Scatter(
            x=dates, y=series["rsi"],
            line={"color": "#00BFFF", "width": 1.5},
            name="RSI(14)", showlegend=False,
        ), row=2, col=1)
        for level, color in ((RSI_OVERBOUGHT, "#FF3333"), (RSI_OVERSOLD, "#00FF88")):
            fig.add_hline(y=level, line_dash="dot", line_color=color,
                          line_width=1, row=2, col=1)
        fig.add_hline(y=50.0, line_dash="dot",
                      line_color="rgba(255,255,255,0.2)", line_width=1, row=2, col=1)

    # ── Row 3: MACD ───────────────────────────────────────────────────────
    if "macd_hist" in series:
        hist_vals = series["macd_hist"]
        bar_colors = [
            _BULL_CANDLE if float(v) >= 0.0 else _BEAR_CANDLE
            for v in hist_vals
        ]
        fig.add_trace(go.Bar(
            x=dates, y=hist_vals,
            marker_color=bar_colors,
            name="MACD Hist", showlegend=False,
            opacity=0.7,
        ), row=3, col=1)
    if "macd_line" in series:
        fig.add_trace(go.Scatter(
            x=dates, y=series["macd_line"],
            line={"color": "#00BFFF", "width": 1.5},
            name="MACD", showlegend=False,
        ), row=3, col=1)
    if "macd_signal" in series:
        fig.add_trace(go.Scatter(
            x=dates, y=series["macd_signal"],
            line={"color": "#FF69B4", "width": 1.5},
            name="Signal", showlegend=False,
        ), row=3, col=1)
    fig.add_hline(y=0.0, line_dash="dot",
                  line_color="rgba(255,255,255,0.2)", line_width=1, row=3, col=1)

    # ── Row 4: Volume ─────────────────────────────────────────────────────
    if "volume" in df.columns:
        cl_arr = df["close"].values
        op_arr = (df["open"].values if "open" in df.columns else cl_arr)
        vol_colors = [
            _BULL_CANDLE if float(cl_arr[i]) >= float(op_arr[i]) else _BEAR_CANDLE
            for i in range(len(cl_arr))
        ]
        fig.add_trace(go.Bar(
            x=dates, y=df["volume"],
            marker_color=vol_colors,
            name="Volume", showlegend=False,
            opacity=0.6,
        ), row=4, col=1)

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        height=900,
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font={"color": _TEXT, "family": "monospace"},
        margin={"l": 50, "r": 50, "t": 40, "b": 20},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"size": 10}},
        xaxis_rangeslider_visible=False,
        title={
            "text": f"QuantEdge — {ticker}",
            "font": {"size": 16, "color": _TEXT},
            "x": 0.5,
        },
    )
    for i in range(1, 5):
        fig.update_xaxes(
            gridcolor=_GRID, showgrid=True,
            zeroline=False, row=i, col=1,
        )
        fig.update_yaxes(
            gridcolor=_GRID, showgrid=True,
            zeroline=False, row=i, col=1,
        )

    # Row labels
    fig.update_yaxes(title_text="Price",  row=1, col=1)
    fig.update_yaxes(title_text="RSI",    row=2, col=1)
    fig.update_yaxes(title_text="MACD",   row=3, col=1)
    fig.update_yaxes(title_text="Volume", row=4, col=1)

    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CONFLUENCE SCORECARD RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_scorecard(sig: MasterSignal) -> None:
    """Renders the master confluence scorecard using st.metric and columns."""
    signal     = sig["signal"]
    score      = sig["confluence_score"]
    conf_pct   = sig["confidence_pct"]
    color      = _SIGNAL_COLORS.get(signal, "#FFFFFF")
    icon       = _SIGNAL_ICONS.get(signal, "")

    st.markdown(
        f"""
        <div style="
            background: {color}18;
            border: 2px solid {color};
            border-radius: 12px;
            padding: 20px 28px;
            text-align: center;
            margin-bottom: 16px;
        ">
            <div style="font-size:3rem;">{icon}</div>
            <div style="font-size:2.2rem; font-weight:900;
                        color:{color}; letter-spacing:3px;">
                {signal}
            </div>
            <div style="font-size:1.1rem; color:#AAA; margin-top:4px;">
                Confluence Score: <b style="color:{color}">{score:+d}</b>
                &nbsp;|&nbsp; Confidence: <b style="color:{color}">{conf_pct:.1f}%</b>
            </div>
            <div style="font-size:0.85rem; color:#666; margin-top:6px;">
                {sig['ticker']} · {sig['timestamp']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Score breakdown
    cols = st.columns(7)
    breakdown = [
        ("Elliott",     sig["elliott_pts"],      "🌊"),
        ("Harmonic",    sig["harmonic_pts"],      "🔷"),
        ("Ichimoku",    sig["ichimoku_pts"],      "☁️"),
        ("Indicators",  sig["indicator_pts"],     "📊"),
        ("Sentiment",   sig["sentiment_pts"],     "💬"),
        ("Institutional", sig["institutional_pts"], "🏦"),
        ("Macro",       sig["macro_pts"],         "🌐"),
    ]
    for col, (label, pts, icon_b) in zip(cols, breakdown):
        pt_color = "#00FF88" if pts > 0 else ("#FF3333" if pts < 0 else "#888888")
        col.markdown(
            f"""
            <div style="background:#0D1117; border:1px solid #1C2333;
                        border-radius:8px; padding:10px; text-align:center;">
                <div style="font-size:1.4rem;">{icon_b}</div>
                <div style="font-size:0.75rem; color:#888;">{label}</div>
                <div style="font-size:1.3rem; font-weight:700;
                            color:{pt_color}">{pts:+d}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# PRZ PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_prz(prz: PRZResult) -> None:
    """Renders PRZ zone, targets, stop-loss, and R:R in a clean panel."""
    if not prz or prz.get("entry", 0.0) < 1e-10:
        st.info("PRZ: Insufficient data to compute reversal zone.")
        return

    rr_color = "#00FF88" if prz["rr_valid"] else "#FF8C00"
    conf_pct = int(prz["confidence"] * 100)

    st.markdown("### 🎯 " + t("agent_prz"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry",      f"${prz['entry']:.2f}")
    c2.metric("Stop Loss",  f"${prz['stop_loss']:.2f}",
              delta=f"{prz['stop_loss'] - prz['entry']:.2f}")
    c3.metric("R:R Ratio",  f"{prz['rr_ratio']:.1f}:1",
              delta="✅ Valid" if prz["rr_valid"] else "⚠️ Below 2:1")
    c4.metric("Confidence", f"{conf_pct}%",
              delta=f"{prz['methods_count']} methods")

    st.markdown("**Exit Targets (staged: T1=50% · T2=30% · T3=20%)**")
    t1c, t2c, t3c = st.columns(3)
    t1c.metric("Target 1",
               f"${prz['target_1']:.2f}",
               delta=f"+{(prz['target_1'] - prz['entry']) / prz['entry'] * 100:.1f}%")
    t2c.metric("Target 2",
               f"${prz['target_2']:.2f}",
               delta=f"+{(prz['target_2'] - prz['entry']) / prz['entry'] * 100:.1f}%")
    t3c.metric("Target 3",
               f"${prz['target_3']:.2f}",
               delta=f"+{(prz['target_3'] - prz['entry']) / prz['entry'] * 100:.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
# HARMONIC RESULTS RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_harmonics(harmonics: List[HarmonicResult]) -> None:
    """Renders harmonic pattern detection results table."""
    found = [h for h in harmonics if h["found"]]
    not_found = [h for h in harmonics if not h["found"]]

    st.markdown(f"### 🔷 Harmonic Patterns ({len(found)} detected of 10 scanned)")

    if found:
        for h in found:
            q_color = {
                "PERFECT": "#00FF88",
                "GOOD":    "#00CC66",
                "FAIR":    "#FFD700",
            }.get(h["quality"], "#888")
            ratios_str = "  ·  ".join(
                f"{k}={v:.3f}" for k, v in h["ratios"].items()
            )
            st.markdown(
                f"""
                <div style="background:#0D1117; border:1px solid {q_color};
                            border-radius:8px; padding:12px; margin-bottom:8px;">
                    <span style="color:{q_color}; font-weight:700;
                                 font-size:1.05rem;">
                        {h['pattern']}
                    </span>
                    &nbsp;
                    <span style="background:{q_color}22; color:{q_color};
                                 padding:2px 8px; border-radius:4px;
                                 font-size:0.8rem;">
                        {h['quality']} · dev={h['worst_dev']:.4f} · +{h['conf_pts']}pts
                    </span>
                    <br/>
                    <span style="color:#888; font-size:0.8rem; font-family:monospace;">
                        D={h['d_price']:.4f} &nbsp;|&nbsp;
                        PRZ [{h['prz_low']:.4f} – {h['prz_high']:.4f}] &nbsp;|&nbsp;
                        {ratios_str}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='color:#666; font-size:0.9rem;'>"
            "No harmonic patterns detected in current swing structure.</div>",
            unsafe_allow_html=True,
        )

    with st.expander(f"Not detected ({len(not_found)} patterns)"):
        for h in not_found:
            st.markdown(
                f"<span style='color:#333;'>✗ {h['pattern']}</span>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════
# MACRO REGIME RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_macro(quad: str, macro_data: Dict[str, Any]) -> None:
    """Renders macro regime quadrant and proxy ticker summary."""
    st.markdown("### 🌐 " + t("agent_macro"))
    q_info = MACRO_QUADRANTS.get(quad, {"label": quad, "color": "#888",
                                         "growth": "?", "inflation": "?",
                                         "strategy": "Unknown"})
    st.markdown(
        f"""
        <div style="background:{q_info['color']}18; border:1px solid {q_info['color']};
                    border-radius:8px; padding:14px; margin-bottom:12px;">
            <span style="color:{q_info['color']}; font-weight:700; font-size:1.1rem;">
                {quad}: {q_info['label']}
            </span>
            &nbsp;·&nbsp;
            Growth {q_info['growth']} &nbsp;·&nbsp; Inflation {q_info['inflation']}
            <br/>
            <span style="color:#AAA; font-size:0.85rem;">{q_info['strategy']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if macro_data:
        proxy_rows = []
        for tkr, d in macro_data.items():
            proxy_rows.append({
                "Ticker":  tkr,
                "Name":    d.get("name", tkr),
                "Price":   f"{d.get('current', 0.0):.2f}",
                "1M%":     f"{d.get('chg_1m', 0.0):+.1f}%",
                "1Y%":     f"{d.get('chg_1y', 0.0):+.1f}%",
            })
        if proxy_rows:
            st.dataframe(
                pd.DataFrame(proxy_rows),
                use_container_width=True,
                hide_index=True,
            )


# ═══════════════════════════════════════════════════════════════════════════
# FUNDAMENTAL PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_fundamentals(info: Dict[str, Any]) -> None:
    """Renders key fundamental metrics from yfinance info dict."""
    if not info:
        st.info("Fundamental data unavailable.")
        return

    st.markdown("### 📋 " + t("agent_fundamentals"))
    c1, c2, c3, c4 = st.columns(4)

    def _fmt(val: Any, fmt: str = ".2f", suffix: str = "") -> str:
        if val is None:
            return "N/A"
        try:
            if fmt == "B":
                return f"${float(val) / 1e9:.1f}B"
            return f"{float(val):{fmt}}{suffix}"
        except (TypeError, ValueError):
            return str(val)

    c1.metric("Market Cap",    _fmt(info.get("market_cap"), "B"))
    c2.metric("P/E (TTM)",     _fmt(info.get("pe_ratio"),   ".1f"))
    c3.metric("Fwd P/E",       _fmt(info.get("forward_pe"), ".1f"))
    c4.metric("Beta",          _fmt(info.get("beta"),        ".2f"))

    c1.metric("52W High",      _fmt(info.get("52w_high"), ".2f", "$"))
    c2.metric("52W Low",       _fmt(info.get("52w_low"),  ".2f", "$"))
    c3.metric("Div Yield",     _fmt(info.get("dividend_yield"), ".2%") if info.get("dividend_yield") else "N/A")
    c4.metric("Short Ratio",   _fmt(info.get("short_ratio"), ".1f"))

    c1.metric("ROE",           _fmt(info.get("roe"),             ".1%") if info.get("roe") else "N/A")
    c2.metric("Profit Margin", _fmt(info.get("profit_margin"),   ".1%") if info.get("profit_margin") else "N/A")
    c3.metric("Rev Growth",    _fmt(info.get("revenue_growth"),  ".1%") if info.get("revenue_growth") else "N/A")
    c4.metric("EPS Growth",    _fmt(info.get("earnings_growth"), ".1%") if info.get("earnings_growth") else "N/A")

    if info.get("description"):
        with st.expander("Company Description"):
            st.markdown(info["description"])


# ═══════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_institutional(inst: Dict[str, Any]) -> None:
    """Renders institutional ownership summary."""
    st.markdown("### 🏦 " + t("agent_institutional"))
    c1, c2 = st.columns(2)
    c1.metric("Institutional %", f"{inst.get('inst_pct', 0.0):.1f}%")
    c2.metric("Insider %",       f"{inst.get('insider_pct', 0.0):.1f}%")
    holders = inst.get("top_holders", [])
    if holders:
        st.dataframe(
            pd.DataFrame(holders).rename(columns={
                "holder": "Holder", "shares": "Shares", "pct": "% Out",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ELLIOTT WAVE PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_elliott(ew: WaveResult) -> None:
    """Renders Elliott Wave analysis summary."""
    st.markdown("### 🌊 " + t("agent_elliott"))
    phase    = ew.get("wave_phase", "NONE")
    conf_pts = ew.get("conf_pts", 0)
    swings_n = ew.get("swings_found", 0)

    phase_labels = {
        "W3_COMPLETE":  ("Wave 3 Complete — W4 retracement expected", "#FFD700"),
        "W5_REVERSAL":  ("Wave 5 Reversal Zone — Major top/bottom approaching", "#FF3333"),
        "ABC_COMPLETE": ("ABC Correction Complete — Trend resumption likely", "#00FF88"),
        "NONE":         ("Insufficient swing structure for wave count", "#555555"),
    }
    label, color = phase_labels.get(phase, (phase, "#888888"))

    st.markdown(
        f"""
        <div style="background:{color}18; border:1px solid {color};
                    border-radius:8px; padding:12px;">
            <span style="color:{color}; font-weight:700;">{phase}</span>
            &nbsp;·&nbsp;
            <span style="color:#AAA; font-size:0.9rem;">{label}</span>
            &nbsp;·&nbsp;
            <span style="color:{color};">{conf_pts:+d} pts</span>
            &nbsp;·&nbsp;
            <span style="color:#666; font-size:0.85rem;">{swings_n} swings found</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fib = ew.get("fib_levels", {})
    if fib:
        with st.expander("Fibonacci Levels"):
            fib_rows = [{"Level": k, "Price": f"{v:.4f}"} for k, v in sorted(fib.items())]
            st.dataframe(pd.DataFrame(fib_rows), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# INDICATOR SUMMARY RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def _render_indicators(ind: Dict[str, Any]) -> None:
    """Renders indicator snapshot metrics."""
    st.markdown("### 📊 " + t("agent_indicators"))
    if not ind or ind.get("conf_pts") is None:
        st.info("Indicator data unavailable.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    rsi = ind.get("rsi_val", 50.0)
    rsi_color = "#FF3333" if rsi > RSI_OVERBOUGHT else ("#00FF88" if rsi < RSI_OVERSOLD else "#FFD700")
    c1.metric("RSI(14)", f"{rsi:.1f}")

    c2.metric("MACD Hist", f"{ind.get('macd_hist', 0.0):.4f}")
    c3.metric("Stoch %K",  f"{ind.get('stoch_k', 50.0):.1f}")
    c4.metric("ATR(14)",   f"{ind.get('atr', 0.0):.4f}")
    c5.metric("Ind Pts",   f"{ind.get('conf_pts', 0):+d}")

    c1b, c2b, c3b, c4b = st.columns(4)
    c1b.metric("EMA 9",   f"{ind.get('ema_9',   0.0):.2f}")
    c2b.metric("EMA 50",  f"{ind.get('ema_50',  0.0):.2f}")
    c3b.metric("EMA 200", f"{ind.get('ema_200', 0.0):.2f}")
    c4b.metric("VWAP",    f"{ind.get('vwap',    0.0):.2f}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PAGE ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    """
    QuantEdge AI Trading Agent — main Streamlit entry point.
    Orchestrates sidebar → data fetch → analysis → render.
    No st.set_page_config() — called once in app.py.
    """

    # ── Custom dark CSS ───────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .stApp { background-color: #0D1117; }
        .stMetric { background: #0D1117 !important; }
        .stMetricLabel { color: #888 !important; font-size: 0.78rem !important; }
        .stMetricValue { color: #E6EDF3 !important; }
        .stDataFrame { background: #0D1117; }
        div[data-testid="stSidebar"] { background-color: #0D1117; }
        hr { border-color: #1C2333; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center; padding:10px 0 20px 0;">
                <div style="font-size:1.5rem; font-weight:900;
                            color:#00FF88; letter-spacing:3px;">
                    QuantEdge
                </div>
                <div style="color:#555; font-size:0.75rem; margin-top:4px;">
                    AI Trading Agent · v2.0
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ticker = st.text_input(
            "Ticker Symbol",
            value=st.session_state.get("ticker", "AAPL"),
            placeholder="e.g. AAPL, TSLA, NVDA",
            key="ticker_input",
        ).strip().upper()

        years = st.selectbox(
            "Data History",
            options=[1, 2, 3, 5],
            index=1,
            format_func=lambda x: f"{x} Year{'s' if x > 1 else ''}",
        )

        st.markdown("---")
        groq_key = st.text_input(
            "Groq API Key (optional)",
            type="password",
            value=st.session_state.get("groq_key", ""),
            help="Enables AI sentiment scoring via LLaMA. Leave blank to skip.",
            key="groq_key_input",
        )

        st.markdown("---")
        analyse_btn = st.button(
            "🚀 Analyse",
            use_container_width=True,
            type="primary",
        )

        st.markdown("---")
        st.markdown(
            """
            <div style="color:#333; font-size:0.7rem; line-height:1.6;">
                <b style="color:#555;">Engines</b><br/>
                Elliott Wave · 10 Harmonics<br/>
                Ichimoku Cloud · RSI · MACD<br/>
                Bollinger · Stochastic · ATR<br/>
                OBV · VWAP · PRZ · Macro<br/>
                Sentiment · Institutional
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Session state initialisation ──────────────────────────────────────
    if "result" not in st.session_state:
        st.session_state["result"] = None
    if "chart_data" not in st.session_state:
        st.session_state["chart_data"] = None

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin-bottom:24px;">
            <h1 style="color:#E6EDF3; font-size:1.8rem; font-weight:900;
                       letter-spacing:2px; margin:0;">
                QuantEdge
                <span style="color:#00FF88;">AI</span>
                Trading Agent
            </h1>
            <p style="color:#555; font-size:0.85rem; margin:4px 0 0 0;">
                Elliott Wave · Harmonic Patterns · Ichimoku ·
                Multi-Indicator Confluence · Macro Regime
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Analysis trigger ──────────────────────────────────────────────────
    if analyse_btn and ticker:
        st.session_state["ticker"]   = ticker
        st.session_state["groq_key"] = groq_key

        with st.spinner(f"Fetching data for {ticker}…"):
            df       = _fetch_ohlcv(ticker, years=years)
            info     = _fetch_info(ticker)
            macro    = _fetch_macro_proxies()
            inst     = _fetch_institutional_proxy(ticker)

        if df.empty:
            st.error(
                f"No price data returned for **{ticker}**. "
                "Check the ticker symbol and your internet connection."
            )
            st.session_state["result"]     = None
            st.session_state["chart_data"] = None
            return

        with st.spinner("Running analysis engines…"):
            # Pre-compute all sub-results for chart and panels
            close    = df["close"]
            swings   = compute_zigzag(close)
            ew_res   = analyse_elliott_waves(swings)
            harm_list = scan_all_harmonic_patterns(swings)
            ich      = compute_ichimoku(df)
            ind      = compute_all_indicators(df)
            prz      = compute_prz_confluence(df, swings, harm_list, ich, ind)
            sig      = compute_master_signal(ticker, df, info, macro, inst, groq_key)

        st.session_state["result"] = {
            "sig":      sig,
            "ew_res":   ew_res,
            "harm_list": harm_list,
            "ich":      ich,
            "ind":      ind,
            "prz":      prz,
            "macro":    macro,
            "info":     info,
            "inst":     inst,
            "swings":   swings,
        }
        st.session_state["chart_data"] = {
            "df": df, "ticker": ticker, "ind": ind, "ich": ich,
            "swings": swings, "harmonics": harm_list, "prz": prz,
        }

    # ── Render results ────────────────────────────────────────────────────
    res = st.session_state.get("result")
    cd  = st.session_state.get("chart_data")

    if res is None:
        # Welcome / idle state
        st.markdown(
            """
            <div style="
                border: 1px solid #1C2333;
                border-radius: 12px;
                padding: 60px 40px;
                text-align: center;
                background: #0D1117;
                margin-top: 40px;
            ">
                <div style="font-size:4rem; margin-bottom:16px;">🔬</div>
                <div style="color:#E6EDF3; font-size:1.3rem; font-weight:700;">
                    Enter a ticker and click Analyse
                </div>
                <div style="color:#555; font-size:0.9rem; margin-top:8px;">
                    Full-stack analysis: Elliott Wave · 10 Harmonic Patterns ·
                    Ichimoku · 8 Indicators · PRZ · Macro · Sentiment
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    sig      = res["sig"]
    ew_res   = res["ew_res"]
    harm_list = res["harm_list"]
    ich      = res["ich"]
    ind      = res["ind"]
    prz      = res["prz"]
    macro    = res["macro"]
    info     = res["info"]
    inst     = res["inst"]
    swings   = res["swings"]

    # ── Risk warnings (top of page) ───────────────────────────────────────
    for w in sig.get("risk_warnings", []):
        st.warning(w)

    # ── Master scorecard ──────────────────────────────────────────────────
    _render_scorecard(sig)

    st.markdown("---")

    # ── Candlestick chart ─────────────────────────────────────────────────
    if cd:
        fig = _build_chart(
            df       = cd["df"],
            ticker   = cd["ticker"],
            ind      = cd["ind"],
            ich      = cd["ich"],
            swings   = cd["swings"],
            harmonics = cd["harmonics"],
            prz      = cd["prz"],
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── PRZ panel ─────────────────────────────────────────────────────────
    _render_prz(prz)

    st.markdown("---")

    # ── Two-column layout: harmonics left, Elliott right ──────────────────
    col_h, col_e = st.columns([3, 2])
    with col_h:
        _render_harmonics(harm_list)
    with col_e:
        _render_elliott(ew_res)

    st.markdown("---")

    # ── Indicators ────────────────────────────────────────────────────────
    _render_indicators(ind)

    st.markdown("---")

    # ── Macro + Institutional row ─────────────────────────────────────────
    col_m, col_i = st.columns([3, 2])
    with col_m:
        _render_macro(sig["macro_quadrant"], macro)
    with col_i:
        _render_institutional(inst)

    st.markdown("---")

    # ── Fundamentals ──────────────────────────────────────────────────────
    _render_fundamentals(info)

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="text-align:center; color:#333; font-size:0.72rem;
                    margin-top:40px; padding-bottom:20px;">
            QuantEdge AI Trading Agent · For research purposes only ·
            Not financial advice · All analysis is probabilistic
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────
main()