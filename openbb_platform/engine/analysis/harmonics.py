# engine/harmonics.py
import numpy as np
import pandas as pd
from typing import List, Dict, Optional

class HarmonicEngine:
    """
    Silicon Valley Grade Harmonic Detection Engine — FULL AUDIT EDITION v2.0.
    Enforces Scott Carney's 'Harmonic Trading' Vol 1-3 Ratios.
    Cross-verified: [CV1], [CV2], [CV3].
    """
    
    TOLERANCE = 0.001  # Standard precision for D-points

    @staticmethod
    def safe_ratio(numerator: float, denominator: float) -> float:
        """Section 12: Production Code Guard for ZeroDivisionError."""
        if denominator == 0.0 or abs(denominator) < 1e-10:
            return 0.0
        return abs(numerator) / abs(denominator)
    
    @staticmethod
    def find_pivots(df: pd.DataFrame, window: int = 3) -> List[Dict]: # ← FIXED: Window 5 was too restrictive for fractal detection
        """Identifies fractal high/low pivots for leg calculation."""
        pivots = []
        for i in range(window, len(df) - window):
            # Check for Peak (Fractal High)
            if all(df['high'].iloc[i] > df['high'].iloc[i-j] for j in range(1, window+1)) and \
               all(df['high'].iloc[i] > df['high'].iloc[i+j] for j in range(1, window+1)):
                pivots.append({'type': 'high', 'price': df['high'].iloc[i], 'index': i, 'time': df.index[i]})
            
            # Check for Trough (Fractal Low)
            if all(df['low'].iloc[i] < df['low'].iloc[i-j] for j in range(1, window+1)) and \
               all(df['low'].iloc[i] < df['low'].iloc[i+j] for j in range(1, window+1)):
                pivots.append({'type': 'low', 'price': df['low'].iloc[i], 'index': i, 'time': df.index[i]})
        return pivots

    def validate_ratios(self, p: List[float], name: str) -> bool:
        """
        Standard XABCD Pattern Validator (Sections 1-8).
        p order: X, A, B, C, D prices
        """
        XA_len = abs(p[1] - p[0])
        AB_len = abs(p[2] - p[1])
        BC_len = abs(p[3] - p[2])
        CD_len = abs(p[4] - p[3])
        XD_len = abs(p[4] - p[0])

        B_XA = self.safe_ratio(AB_len, XA_len)
        C_AB = self.safe_ratio(BC_len, AB_len)
        D_BC = self.safe_ratio(CD_len, BC_len)
        D_XA = self.safe_ratio(XD_len, XA_len)
        CD_AB = self.safe_ratio(CD_len, AB_len)

        # 1. GARTLEY [CV1]
        if name == "GARTLEY":
            return abs(B_XA - 0.618) <= 0.019 and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (1.130 - 0.001 <= D_BC <= 1.618 + 0.001) and \
                   abs(D_XA - 0.786) <= 0.001 and \
                   (abs(CD_AB - 1.000) <= 0.02 or abs(CD_AB - 1.270) <= 0.02)
        
        # 2. DEEP GARTLEY [CV3]
        elif name == "DEEP_GARTLEY":
            return abs(B_XA - 0.618) <= 0.019 and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (1.618 - 0.001 <= D_BC <= 2.618 + 0.001) and \
                   abs(D_XA - 0.886) <= 0.001 and \
                   abs(CD_AB - 1.000) <= 0.02

        # 3. BAT [CV2]
        elif name == "BAT":
            return (0.382 - 0.001 <= B_XA <= 0.500 + 0.001) and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (1.618 - 0.001 <= D_BC <= 2.618 + 0.001) and \
                   abs(D_XA - 0.886) <= 0.001 and \
                   (abs(CD_AB - 1.000) <= 0.02 or abs(CD_AB - 1.618) <= 0.02)

        # 4. ALTERNATE BAT [CV3]
        elif name == "ALTERNATE_BAT":
            return (0.370 <= B_XA <= 0.383) and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (2.000 - 0.001 <= D_BC <= 3.618 + 0.001) and \
                   (0.886 - 0.001 <= D_XA <= 1.130 + 0.001) and \
                   abs(CD_AB - 1.618) <= 0.02

        # 5. CRAB [CV1]
        elif name == "CRAB":
            return (0.382 - 0.001 <= B_XA <= 0.618 + 0.001) and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (2.618 - 0.001 <= D_BC <= 3.618 + 0.001) and \
                   abs(D_XA - 1.618) <= 0.001 and \
                   (abs(CD_AB - 1.000) <= 0.02 or abs(CD_AB - 1.618) <= 0.02)

        # 6 & 7. DEEP CRAB & 1.902 Variant [CV3]
        elif name == "DEEP_CRAB":
            b_point_check = (0.885 <= B_XA <= 0.930) # Carney +5% upper bound
            d_point_range = (1.618 - 0.001 <= D_XA <= 1.902 + 0.001)
            return b_point_check and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (2.000 - 0.001 <= D_BC <= 3.618 + 0.001) and \
                   d_point_range and \
                   (abs(CD_AB - 1.000) <= 0.02 or abs(CD_AB - 1.618) <= 0.02)

        # 8. BUTTERFLY [CV1]
        elif name == "BUTTERFLY":
            return abs(B_XA - 0.786) <= 0.024 and \
                   any(abs(C_AB - t) <= 0.001 for t in [0.382, 0.886]) and \
                   (1.618 - 0.001 <= D_BC <= 2.240 + 0.001) and \
                   any(abs(D_XA - t) <= 0.001 for t in [1.270, 1.414]) and \
                   (abs(CD_AB - 1.000) <= 0.02 or abs(CD_AB - 1.270) <= 0.02)

        return False

    def validate_shark_ratios(self, p: List[float]) -> bool:
        """Section 9: SHARK Pattern (0XABC Labeling)."""
        # Mapping: p[0]=0, p[1]=X, p[2]=A, p[3]=B, p[4]=C
        leg_0X = abs(p[1] - p[0])
        leg_XA = abs(p[2] - p[1])
        leg_AB = abs(p[3] - p[2])
        leg_BC = abs(p[4] - p[3])
        leg_0C = abs(p[4] - p[0])
        leg_0A = abs(p[2] - p[0])

        X_0A = self.safe_ratio(leg_XA, leg_0A) # User's B
        A_0X = self.safe_ratio(leg_0A, leg_0X) # User's C
        B_XA = self.safe_ratio(leg_AB, leg_XA) 
        C_0X = self.safe_ratio(leg_0C, leg_0X) # User's D (Entry)
        BC_XA = self.safe_ratio(leg_BC, leg_XA) # PRO AB=CD check

        return (0.382 - 0.001 <= X_0A <= 0.886 + 0.001) and \
               (1.130 - 0.001 <= A_0X <= 1.618 + 0.001) and \
               (1.618 - 0.001 <= B_XA <= 2.240 + 0.001) and \
               any(abs(C_0X - t) <= 0.001 for t in [0.886, 1.130]) and \
               any(abs(BC_XA - t) <= 0.02 for t in [1.000, 1.270, 1.618])

    def validate_reciprocal_abcd(self, p: List[float]) -> bool:
        """Section 10: RECIPROCAL AB=CD Pattern."""
        # Mapping: p[1]=A, p[2]=B, p[3]=C, p[4]=D (ignoring X)
        AB_len = abs(p[2] - p[1])
        BC_len = abs(p[3] - p[2])
        CD_len = abs(p[4] - p[3])

        C_AB = self.safe_ratio(BC_len, AB_len)
        D_BC = self.safe_ratio(CD_len, BC_len)
        CD_AB = self.safe_ratio(CD_len, AB_len)

        return (1.130 - 0.001 <= C_AB <= 3.618 + 0.001) and \
               (0.382 - 0.001 <= D_BC <= 0.886 + 0.001) and \
               (abs(CD_AB - 1.270) <= 0.02 or abs(CD_AB - 1.618) <= 0.02)

    def detect(self, df: pd.DataFrame) -> List[Dict]:
        """Scans pivots for all 10 patterns in Audit v2.0."""
        all_pivots = self.find_pivots(df)
        if len(all_pivots) < 5: return []
        
        detected = []
        # ← FIXED: Implemented sliding window to scan pivot history instead of hardcoded last 5
        # Range: from 5 points to the end, checking the last 10 sets of pivots for relevance
        scan_depth = min(10, len(all_pivots) - 4) 
        
        for i in range(len(all_pivots), len(all_pivots) - scan_depth, -1):
            current_set = all_pivots[i-5:i]
            if len(current_set) < 5: continue
            
            prices = [pt['price'] for pt in current_set]
            
            # Standard XABCD List
            xabcd_patterns = ["GARTLEY", "DEEP_GARTLEY", "BAT", "ALTERNATE_BAT", "CRAB", "DEEP_CRAB", "BUTTERFLY"]
            
            for name in xabcd_patterns:
                if self.validate_ratios(prices, name):
                    is_bullish = current_set[-1]['type'] == 'low'
                    pattern_id = f"{name}_{current_set[-1]['index']}"
                    # Avoid duplicate detection of the same pattern at the same completion point
                    if not any(d.get('id') == pattern_id for d in detected):
                        detected.append({
                            "id": pattern_id, # ← ADDED: unique identifier for filtering
                            "name": name, "points": [(p['index'], p['price']) for p in current_set],
                            "type": "BULLISH" if is_bullish else "BEARISH", "audit_v": "2.0"
                        })

            # Shark (0XABC) Logic
            if self.validate_shark_ratios(prices):
                is_bullish = current_set[-1]['type'] == 'low'
                detected.append({
                    "name": "SHARK", "points": [(p['index'], p['price']) for p in current_set],
                    "type": "BULLISH" if is_bullish else "BEARISH", "audit_v": "2.0", "labels": "0XABC"
                })

            # Reciprocal AB=CD
            if self.validate_reciprocal_abcd(prices):
                is_bullish = current_set[-1]['type'] == 'low'
                detected.append({
                    "name": "RECIP_ABCD", "points": [(p['index'], p['price']) for p in current_set],
                    "type": "BULLISH" if is_bullish else "BEARISH", "audit_v": "2.0"
                })
        
        return detected

def get_harmonic_analysis(df: pd.DataFrame) -> List[Dict]:
    engine = HarmonicEngine()
    return engine.detect(df)