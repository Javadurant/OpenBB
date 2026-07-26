"""
engine/analysis/elliott.py
🌊 Elliott Wave Discovery Engine
Implements the 3 absolute rules for Motive Waves and structural validation.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import logging

# Configure logging for production observability
logger = logging.getLogger("ElliottEngine")

class ElliottEngine:
    """
    Validates wave counts against the Elliott Wave Verified Reference.
    Responsibility: Structural validation of impulse and corrective sequences.
    """
    
    def __init__(self) -> None:
        self.logger = logger

    def validate_impulse(self, p: List[float]) -> Dict[str, Any]:
        """
        Validates a 5-point sequence (0, 1, 2, 3, 4, 5).
        Prices: p[0]=Start, p[1]=W1, p[2]=W2, p[3]=W3, p[4]=W4, p[5]=W5
        
        Pattern: Directional Invariant Rule Enforcement
        Source: Elliott Wave Verified Reference
        """
        if len(p) < 6:
            return {"valid": False, "reason": "Incomplete wave sequence (Need 6 points)"}

        # Vectorized length calculations for Signal 3 (Numerical Stability)
        w1_len = abs(p[1] - p[0])
        w2_len = abs(p[2] - p[1])
        w3_len = abs(p[3] - p[2])
        w5_len = abs(p[5] - p[4])

        # Rule 1: Wave 2 never retraces more than 100% of Wave 1
        is_bullish = p[1] > p[0]
        if (is_bullish and p[2] < p[0]) or (not is_bullish and p[2] > p[0]):
            return {"valid": False, "reason": "Rule 1: W2 retraced 100% of W1"}

        # Rule 2: Wave 3 is never the shortest
        if w3_len < w1_len and w3_len < w5_len:
            return {"valid": False, "reason": "Rule 2: W3 is the shortest wave"}

        # Rule 3: Wave 4 never enters the territory of Wave 1
        # Implementation: In Bullish, W4 low (p[4]) > W1 high (p[1])
        # Implementation: In Bearish, W4 high (p[4]) < W1 low (p[1])
        if (is_bullish and p[4] <= p[1]) or (not is_bullish and p[4] >= p[1]):
             return {"valid": False, "reason": "Rule 3: W4/W1 overlap"}

        return {"valid": True, "reason": "Standard Impulse Confirmed"}

# ─── PROCEDURAL EXPORTS FOR UI INTEGRATION ──────────────────────────────────
# Adapted from: Elliott Wave Theory Patterns (stefandp)
# Purpose: Maintain backward compatibility with app.py imports

def validate_wave_2(p1: float, p2: float, p3: float) -> Dict[str, Any]:
    """
    Validates a potential Wave 2 retrace.
    p1: Start W1 | p2: End W1 | p3: End W2
    """
    try:
        w1_length = p2 - p1
        retrace_length = p2 - p3
        
        if w1_length == 0:
            return {"is_valid": False, "ratio": 0, "is_ideal": False}
            
        ratio = retrace_length / w1_length
        
        # Rule 1 Violation (Floating point safety)
        if ratio >= 0.999 or ratio <= 0:
            return {"is_valid": False, "ratio": ratio, "is_ideal": False}
            
        return {
            "is_valid": True,
            "ratio": ratio,
            "is_ideal": 0.5 <= ratio <= 0.618
        }
    except Exception as e:
        logger.error(f"Logic failure in validate_wave_2: {str(e)}")
        return {"is_valid": False, "ratio": 0, "is_ideal": False}

def project_wave_3(p1: float, p2: float, p3: float) -> Dict[str, Any]:
    """Projects Wave 3 Fibonacci extensions."""
    w1_length = p2 - p1
    return {
        "target_1618": p3 + (w1_length * 1.618),
        "target_2618": p3 + (w1_length * 2.618)
    }

# ← ADDED [Rule 3]: Mandatory Overlap Enforcement
def validate_wave_4(p1: float, p2: float, p3: float, p4: float, p5: float) -> Dict[str, Any]:
    """
    Validates Wave 4 context to ensure no overlap with Wave 1.
    
    Args:
        p1 (float): Start of Wave 1
        p2 (float): End of Wave 1 (Territory Boundary)
        p3 (float): End of Wave 2
        p4 (float): End of Wave 3
        p5 (float): End of Wave 4
        
    Returns:
        Dict: Validation status and overlap depth
    """
    try:
        is_bullish = p2 > p1
        
        # Calculate Overlap
        # In Bullish: Overlap occurs if W4 Low (p5) <= W1 High (p2)
        if is_bullish:
            overlap_depth = p2 - p5
            is_valid = p5 > p2
        else:
            # In Bearish: Overlap occurs if W4 High (p5) >= W1 Low (p2)
            overlap_depth = p5 - p2
            is_valid = p5 < p2
            
        return {
            "is_valid": is_valid,
            "overlap_depth": max(0, overlap_depth),
            "is_diagonal": not is_valid  # Rule 3 violation signals a potential Diagonal
        }
    except Exception as e:
        logger.error(f"Logic failure in validate_wave_4: {str(e)}")
        return {"is_valid": False, "overlap_depth": 0, "is_diagonal": False}

# ─── WAVE DISCOVERY — scans pivots and finds valid impulse structures ────────
# This was MISSING — the engine could only validate, not discover.
# Added per Council verdict: "the engine literally cannot scan for them"

def discover_impulses(pivots: list, min_wave1_pct: float = 0.02) -> List[Dict[str, Any]]:
    """
    Scans a sequence of alternating pivot prices for valid 5-wave impulse structures.
    
    This is the DISCOVERY function that was missing — ElliottEngine.validate_impulse()
    only validates a known wave count. This function finds them.
    
    Algorithm:
      1. Slide a 6-point window across the pivot sequence
      2. For each window, test both bullish and bearish orientation
      3. Validate against the 3 absolute rules
      4. Return all valid structures with their ratios and targets
    
    Args:
        pivots: List of float prices from alternating swing highs/lows.
                Must be pre-filtered by enforce_alternation() from swings.py.
        min_wave1_pct: Minimum Wave 1 size as % of price (filters noise).
                       Default 2% — filters micro-waves on daily charts.
    
    Returns:
        List of dicts, each containing:
          valid: bool, reason: str, points: list,
          is_bullish: bool, w2_ratio: float, w3_targets: dict,
          w4_support: float
    """
    engine = ElliottEngine()
    results = []
    n = len(pivots)
    
    if n < 6:
        return results
    
    for i in range(n - 5):
        window = pivots[i:i+6]
        
        # Filter noise: Wave 1 must be significant
        w1_len = abs(window[1] - window[0])
        base_price = abs(window[0]) if abs(window[0]) > 1e-10 else 1.0
        if w1_len / base_price < min_wave1_pct:
            continue
        
        # Validate
        result = engine.validate_impulse(window)
        
        if result["valid"]:
            is_bullish = window[1] > window[0]
            w1_length = window[1] - window[0]
            
            # Wave 2 retracement ratio
            w2_info = validate_wave_2(window[0], window[1], window[2])
            
            # Wave 3 projection targets
            w3_targets = project_wave_3(window[0], window[1], window[2])
            
            # Wave 4 overlap check
            w4_info = validate_wave_4(window[0], window[1], window[2], window[3], window[4])
            
            # Wave 4 support level (0.382 retracement of Wave 3)
            w3_length = abs(window[3] - window[2])
            if is_bullish:
                w4_support = window[3] - (0.382 * w3_length)
            else:
                w4_support = window[3] + (0.382 * w3_length)
            
            results.append({
                "valid": True,
                "reason": result["reason"],
                "points": list(window),
                "start_index": i,
                "is_bullish": is_bullish,
                "w2_ratio": w2_info.get("ratio", 0.0),
                "w2_ideal": w2_info.get("is_ideal", False),
                "w3_targets": w3_targets,
                "w4_overlap_ok": w4_info.get("is_valid", False),
                "w4_support": w4_support,
                "w5_target_equal_w1": window[4] + w1_length if is_bullish else window[4] - abs(w1_length),
                "w5_target_0618": window[4] + (0.618 * abs(window[3] - window[0])) if is_bullish else window[4] - (0.618 * abs(window[3] - window[0])),
            })
    
    logger.info("discover_impulses: found %d valid impulse structures from %d pivots.", len(results), n)
    return results
