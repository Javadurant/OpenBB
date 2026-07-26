"""
engine/analysis/harmonics.py
Production-grade engine for detecting exactly 10 strictly audited Harmonic Patterns.

TOLERANCE FIX — 2026-04-27 (Council-verified, dual-source cross-reference)
═══════════════════════════════════════════════════════════════════════════
SOURCE 1: Carney Vol.1/Vol.2/Vol.3 via project HARMONIC_PATTERN_RATIO_REFERENCE.docx
SOURCE 2: TradingView Carney study + NAGA.com + TradingCenter.org

CRITICAL CORRECTIONS APPLIED:
  T01  BC/AB ALL PATTERNS: discrete {0.382,0.886} ±0.001 → RANGE [0.382,0.886] ±0.02
  T02  D/XA PRIMARY CONSTRAINTS: ±0.001 → ±3% of target value
  T03  CD/BC RANGE BOUNDS: ±0.001 → ±0.02 on range edges
  T04  Butterfly D/XA: discrete {1.270,1.414} ±0.001 → RANGE [1.250,1.434]
  T05  Shark C/0X: discrete {0.886,1.130} ±0.001 → discrete ±0.027 (±3%)

The 10 Patterns:
  1. AB=CD (Standard)    6. Butterfly
  2. Reciprocal AB=CD    7. Crab
  3. Gartley             8. Deep Crab
  4. Bat                 9. Shark (0XABC)
  5. Alternate Bat      10. 5-0 (0XABCD)
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatternResult:
    """Contract for a successfully validated harmonic pattern."""
    pattern_name: str
    points: Tuple[float, ...]
    is_bullish: bool
    stop_loss: float


def safe_ratio(numerator: float, denominator: float) -> float:
    """Safe division for ratio calculation. Returns 0.0 on zero denominator."""
    if denominator == 0.0 or abs(denominator) < 1e-10:
        return 0.0
    return abs(numerator) / abs(denominator)


class HarmonicValidator:
    """
    Pure mathematical validation engine for Harmonic Patterns.
    All ratio comparisons use abs(ratio - target) <= tolerance.
    No float == comparisons anywhere.
    """

    @staticmethod
    def _is_bullish_abcd(a: float, b: float, c: float, d: float) -> bool:
        return d < c

    @staticmethod
    def _is_bullish_xabcd(x: float, a: float, b: float, c: float, d: float) -> bool:
        return d < c

    @staticmethod
    def _is_bullish_0xabc(p0: float, px: float, pa: float, pb: float, pc: float) -> bool:
        return pc < pb

    @staticmethod
    def _is_bullish_0xabcd(p0: float, px: float, pa: float, pb: float, pc: float, pd: float) -> bool:
        return pd < pc


    # ── 1 & 2: ABCD PATTERNS ────────────────────────────────────────────────

    @classmethod
    def detect_abcd(cls, a: float, b: float, c: float, d: float) -> List[PatternResult]:
        """
        Validates Standard AB=CD and Reciprocal AB=CD patterns.
        Standard: C retraces AB 0.618-0.786 ±0.02, D extends BC 1.270-1.618 ±0.02
        Reciprocal [CV3]Ch.9: C extends AB 1.130-3.618, D retraces BC 0.382-0.886
        """
        results = []
        ab_len = abs(b - a)
        bc_len = abs(c - b)
        cd_len = abs(d - c)
        is_bull = cls._is_bullish_abcd(a, b, c, d)
        c_ret_ab = safe_ratio(bc_len, ab_len)
        d_ext_bc = safe_ratio(cd_len, bc_len)
        abcd_sym = safe_ratio(cd_len, ab_len)

        # 1. Standard AB=CD
        if ((0.618 - 0.02 <= c_ret_ab <= 0.786 + 0.02) and
            (1.270 - 0.02 <= d_ext_bc <= 1.618 + 0.02) and
            (0.900 <= abcd_sym <= 1.100)):
            sl_dist = 1.27 * ab_len
            sl = c - sl_dist if is_bull else c + sl_dist
            results.append(PatternResult("Standard AB=CD", (a, b, c, d), is_bull, sl))

        # 2. Reciprocal AB=CD [CV3]Ch.9 — C extends AB: 1.130-3.618
        if ((1.130 - 0.02 <= c_ret_ab <= 3.618 + 0.02) and
            (0.382 - 0.02 <= d_ext_bc <= 0.886 + 0.02) and
            (0.900 <= abcd_sym <= 1.100)):
            sl_dist = 1.27 * ab_len
            sl = c - sl_dist if is_bull else c + sl_dist
            results.append(PatternResult("Reciprocal AB=CD", (a, b, c, d), is_bull, sl))

        return results

    # ── 3 to 8: XABCD PATTERNS ──────────────────────────────────────────────

    @classmethod
    def detect_xabcd(cls, x: float, a: float, b: float, c: float, d: float) -> List[PatternResult]:
        """
        Validates Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab.
        ALL tolerances council-verified from two independent sources.
        """
        results = []
        xa_len = abs(a - x)
        ab_len = abs(b - a)
        bc_len = abs(c - b)
        cd_len = abs(d - c)
        ad_len = abs(d - a)    # <- CRITICAL FIX: was xd_len=abs(d-x). AD/XA is the universal D-point formula.
        # Proof: Gartley "0.786 retracement" means |A-D|/|A-X| = 0.786, NOT |D-X|/|A-X| (which = 0.214).
        # AD/XA works for BOTH retracement (Gartley/Bat: <1.0) AND extension (Butterfly/Crab: >1.0).

        r_ab_xa = safe_ratio(ab_len, xa_len)
        r_bc_ab = safe_ratio(bc_len, ab_len)  # T01: now tested as RANGE
        r_cd_bc = safe_ratio(cd_len, bc_len)
        r_ad_xa = safe_ratio(ad_len, xa_len)  # <- CRITICAL FIX: D-point ratio measured as AD/XA

        is_bull = cls._is_bullish_xabcd(x, a, b, c, d)

        # ── T01 APPLIED: BC/AB is a CONTINUOUS RANGE [0.382, 0.886] ±0.02 ──
        # Source: NAGA "BC can retrace 38.2% to 88.6% of AB"
        # Source: TradingView Carney table "C of BA 0.382-0.886"
        bc_ab_valid = (0.382 - 0.02 <= r_bc_ab <= 0.886 + 0.02)  # <- FIXED T01

        # ── 3. GARTLEY [CV1] pp.92-98 ────────────────────────────────────────
        # B/XA: 0.618 ±0.019 (±3%) [CV1]p.92 — UNCHANGED, already correct
        # BC/AB: RANGE [0.362, 0.906] <- FIXED T01
        # CD/BC: 1.130-1.618 ±0.02 <- FIXED T03
        # D/XA: 0.786 ±0.024 (±3%) <- FIXED T02
        if (abs(r_ab_xa - 0.618) <= 0.019 and       # B: ±3% correct
            bc_ab_valid and                            # C: RANGE [T01]
            (1.130 - 0.02 <= r_cd_bc <= 1.618 + 0.02) and  # CD/BC [T03]
            abs(r_ad_xa - 0.786) <= 0.024):           # D: ±3% [T02]
            sl = a - (1.13 * xa_len) if is_bull else a + (1.13 * xa_len)
            results.append(PatternResult("Gartley", (x, a, b, c, d), is_bull, sl))

        # ── 4. BAT [CV2] pp.67-72 ────────────────────────────────────────────
        # B/XA: 0.382-0.500 ±0.02 <- FIXED T03 range edges
        # BC/AB: RANGE <- FIXED T01
        # CD/BC: 1.618-2.618 ±0.02 <- FIXED T03
        # D/XA: 0.886 ±0.027 (±3%) <- FIXED T02
        if ((0.382 - 0.02 <= r_ab_xa <= 0.500 + 0.02) and  # B: range [T03]
            bc_ab_valid and                                    # C: RANGE [T01]
            (1.618 - 0.02 <= r_cd_bc <= 2.618 + 0.02) and    # CD/BC [T03]
            abs(r_ad_xa - 0.886) <= 0.027):                   # D: ±3% [T02]
            sl = a - (1.13 * xa_len) if is_bull else a + (1.13 * xa_len)
            results.append(PatternResult("Bat", (x, a, b, c, d), is_bull, sl))


        # ── 5. ALTERNATE BAT [CV3] Ch.5 ──────────────────────────────────────
        # B/XA: 0.382 MAX (+0.001/-0.011) — UNCHANGED, correct per CV3
        # BC/AB: RANGE <- FIXED T01
        # CD/BC: 2.000-3.618 ±0.02 <- FIXED T03
        # D/XA: RANGE [0.886, 1.130] ±0.02 <- FIXED T03
        if ((0.382 - 0.011 <= r_ab_xa <= 0.382 + 0.001) and  # B: MAX 0.382
            bc_ab_valid and                                      # C: RANGE [T01]
            (2.000 - 0.02 <= r_cd_bc <= 3.618 + 0.02) and      # CD/BC [T03]
            (0.886 - 0.02 <= r_ad_xa <= 1.130 + 0.02)):        # D: range [T03]
            sl = a - (1.27 * xa_len) if is_bull else a + (1.27 * xa_len)
            results.append(PatternResult("Alternate Bat", (x, a, b, c, d), is_bull, sl))

        # ── 6. BUTTERFLY [CV1] pp.128-133, [CV3] Ch.7 ───────────────────────
        # B/XA: 0.786 ±0.024 (±3%) — UNCHANGED, correct per CV1
        # BC/AB: RANGE <- FIXED T01
        # CD/BC: 1.618-2.240 ±0.02 <- FIXED T03
        # D/XA: RANGE [1.250, 1.434] <- FIXED T04 (was discrete ±0.001)
        if (abs(r_ab_xa - 0.786) <= 0.024 and               # B: ±3% correct
            bc_ab_valid and                                    # C: RANGE [T01]
            (1.618 - 0.02 <= r_cd_bc <= 2.240 + 0.02) and    # CD/BC [T03]
            (1.250 <= r_ad_xa <= 1.434)):                      # D: range [T04]
            sl = a - (1.414 * xa_len) if is_bull else a + (1.414 * xa_len)
            results.append(PatternResult("Butterfly", (x, a, b, c, d), is_bull, sl))

        # ── 7. CRAB [CV1] pp.152-157 ────────────────────────────────────────
        # B/XA: 0.382-0.618 ±0.02 <- FIXED T03
        # BC/AB: RANGE <- FIXED T01
        # CD/BC: 2.618-3.618 ±0.02 <- FIXED T03
        # D/XA: 1.618 ±0.049 (±3%) <- FIXED T02
        if ((0.382 - 0.02 <= r_ab_xa <= 0.618 + 0.02) and    # B: range [T03]
            bc_ab_valid and                                      # C: RANGE [T01]
            (2.618 - 0.02 <= r_cd_bc <= 3.618 + 0.02) and      # CD/BC [T03]
            abs(r_ad_xa - 1.618) <= 0.049):                     # D: ±3% [T02]
            sl = a - (2.0 * xa_len) if is_bull else a + (2.0 * xa_len)
            results.append(PatternResult("Crab", (x, a, b, c, d), is_bull, sl))

        # ── 8. DEEP CRAB [CV3] Ch.6 ─────────────────────────────────────────
        # B/XA: 0.886 [0.885, 0.930] — UNCHANGED, correct per CV3 +5% upper
        # BC/AB: RANGE <- FIXED T01
        # CD/BC: 2.000-3.618 ±0.02 <- FIXED T03
        # D/XA: 1.618 ±0.049 (±3%) <- FIXED T02
        if ((0.885 <= r_ab_xa <= 0.930) and                    # B: Deep Crab specific
            bc_ab_valid and                                      # C: RANGE [T01]
            (2.000 - 0.02 <= r_cd_bc <= 3.618 + 0.02) and      # CD/BC [T03]
            abs(r_ad_xa - 1.618) <= 0.049):                     # D: ±3% [T02]
            sl = a - (2.0 * xa_len) if is_bull else a + (2.0 * xa_len)
            results.append(PatternResult("Deep Crab", (x, a, b, c, d), is_bull, sl))

        return results


    # ── 9. SHARK (0XABC) [CV3] Ch.8 ─────────────────────────────────────────

    @classmethod
    def detect_shark(cls, p0: float, px: float, pa: float, pb: float, pc: float) -> Optional[PatternResult]:
        """
        Validates Shark Pattern (0XABC structure). No D point. C is the entry.
        AB/XA: 1.130-1.618 ±0.02 [CV3]Ch.8
        C/0X: 0.886 or 1.130 ±0.027 (±3%) <- FIXED T05
        BC/AB: 1.618-2.240 ±0.02 [CV3]Ch.8
        """
        leg_0x = abs(px - p0)
        leg_xa = abs(pa - px)
        leg_ab = abs(pb - pa)
        leg_0c = abs(pc - p0)
        leg_bc = abs(pc - pb)

        r_ab_xa = safe_ratio(leg_ab, leg_xa)
        r_0c_0x = safe_ratio(leg_0c, leg_0x)
        r_bc_ab = safe_ratio(leg_bc, leg_ab)

        if not (1.130 - 0.02 <= r_ab_xa <= 1.618 + 0.02):
            return None

        # C/0X: discrete 0.886 or 1.130 ±0.027 <- FIXED T05 (was ±0.001)
        shark_c_valid = (abs(r_0c_0x - 0.886) <= 0.027 or
                         abs(r_0c_0x - 1.130) <= 0.027)
        if not shark_c_valid:
            return None

        if not (1.618 - 0.02 <= r_bc_ab <= 2.240 + 0.02):
            return None

        is_bull = cls._is_bullish_0xabc(p0, px, pa, pb, pc)
        sl_buf = 0.005 * p0
        sl = p0 - sl_buf if is_bull else p0 + sl_buf
        return PatternResult("Shark", (p0, px, pa, pb, pc), is_bull, sl)

    # ── 10. 5-0 (0XABCD) [CV3] Ch.8 ─────────────────────────────────────────

    @classmethod
    def detect_5_0(cls, p0: float, px: float, pa: float, pb: float, pc: float, pd: float) -> Optional[PatternResult]:
        """
        Validates 5-0 Pattern (0XABCD structure).
        AB/XA: 1.130-1.618 ±0.02
        BC/AB: 1.618-2.240 ±0.02
        CD/BC: 0.500 ±0.010 [CV3]Ch.8 "exactly 0.50"
        CD/AB: 0.900-1.100 (Reciprocal AB=CD check)
        """
        leg_xa = abs(pa - px)
        leg_ab = abs(pb - pa)
        leg_bc = abs(pc - pb)
        leg_cd = abs(pd - pc)

        r_ab_xa = safe_ratio(leg_ab, leg_xa)
        r_bc_ab = safe_ratio(leg_bc, leg_ab)
        r_cd_bc = safe_ratio(leg_cd, leg_bc)
        r_cd_ab = safe_ratio(leg_cd, leg_ab)

        if not (1.130 - 0.02 <= r_ab_xa <= 1.618 + 0.02):
            return None
        if not (1.618 - 0.02 <= r_bc_ab <= 2.240 + 0.02):
            return None
        if not abs(r_cd_bc - 0.500) <= 0.010:
            return None
        if not (0.900 <= r_cd_ab <= 1.100):
            return None

        is_bull = cls._is_bullish_0xabcd(p0, px, pa, pb, pc, pd)
        sl_dist = 0.618 * leg_bc
        sl = pc - sl_dist if is_bull else pc + sl_dist
        return PatternResult("5-0", (p0, px, pa, pb, pc, pd), is_bull, sl)



# ── HARMONIC ENGINE WRAPPER ──────────────────────────────────────────────────

class HarmonicEngine:
    """
    Stateful orchestration wrapper around HarmonicValidator.
    Provides the instantiation interface expected by app.py and all UI pages.
    """

    def __init__(self) -> None:
        self._validator = HarmonicValidator()
        self.logger = logging.getLogger(__name__)

    def scan(self, prices: list) -> List[PatternResult]:
        """
        Runs all 10 pattern detectors against a price sequence.
        Args:
            prices: Ordered list of alternating pivot prices. Min 4 for ABCD, 6 for full.
        Returns:
            List of PatternResult for every confirmed pattern.
        """
        results: List[PatternResult] = []
        n = len(prices)

        # 4-point ABCD scan
        if n >= 4:
            for i in range(n - 3):
                found = HarmonicValidator.detect_abcd(prices[i], prices[i+1], prices[i+2], prices[i+3])
                results.extend(found)

        # 5-point XABCD scan
        if n >= 5:
            for i in range(n - 4):
                found = HarmonicValidator.detect_xabcd(prices[i], prices[i+1], prices[i+2], prices[i+3], prices[i+4])
                results.extend(found)

        # Shark 0XABC scan (5 points)
        if n >= 5:
            for i in range(n - 4):
                found = HarmonicValidator.detect_shark(prices[i], prices[i+1], prices[i+2], prices[i+3], prices[i+4])
                if found:
                    results.append(found)

        # 5-0 0XABCD scan (6 points)
        if n >= 6:
            for i in range(n - 5):
                found = HarmonicValidator.detect_5_0(prices[i], prices[i+1], prices[i+2], prices[i+3], prices[i+4], prices[i+5])
                if found:
                    results.append(found)

        self.logger.info("HarmonicEngine.scan: %d patterns confirmed from %d pivots.", len(results), n)
        return results
