import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.features import *

print("FIB_W2_MAX:", TradingConstants.FIB_W2_MAX)
print("market_regime:", market_regime)
print("detect_harmonics:", detect_harmonics)
print("analyze_elliott_structure:", analyze_elliott_structure)
print("numpy / pandas:", type(np), type(pd))

# ==========================================
# 0. CONFIGURATION & CONSTANTS
# ==========================================

@dataclass
class TradingConstants:
    """
    Institutional settings for Time Cycles and Fibonacci Ratios.
    """
    TENKAN_CYCLES = [9, 18, 27, 36, 45, 54, 63, 72, 81, 90]
    KIJUN_CYCLES = [26, 52, 77, 103, 129]
    KEY_CYCLES = [17, 26, 35, 52]

    FIB_W2_MIN = 0.5
    FIB_W2_MAX = 0.786
    FIB_W4_MIN = 0.236
    FIB_W4_MAX = 0.382


# ==========================================
# 1. CORE HELPERS
# ==========================================

def _get_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ==========================================
# 2. MARKET REGIME
# ==========================================

def market_regime(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    plus_dm = df["high"].diff()
    minus_dm = -df["low"].diff()

    tr = _get_atr(df, 1).fillna(1)
    atr = tr.rolling(period).mean()

    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1)) * 100
    adx = dx.rolling(period).mean()

    return pd.DataFrame({
        "adx": adx,
        "trend_strength": np.where(adx > 25, "STRONG", "WEAK")
    })


# ==========================================
# 3. SWING STRUCTURE
# ==========================================

def find_swings(df: pd.DataFrame, order: int = 5) -> pd.DataFrame:
    highs = df["high"].values
    lows = df["low"].values

    pivot_high = np.zeros(len(df), dtype=bool)
    pivot_low = np.zeros(len(df), dtype=bool)

    for i in range(order, len(df) - order):
        if highs[i] == max(highs[i - order:i + order + 1]):
            pivot_high[i] = True
        if lows[i] == min(lows[i - order:i + order + 1]):
            pivot_low[i] = True

    return pd.DataFrame({
        "pivot_high": np.where(pivot_high, df["high"], np.nan),
        "pivot_low": np.where(pivot_low, df["low"], np.nan),
        "is_high": pivot_high,
        "is_low": pivot_low
    }, index=df.index)


# ==========================================
# 4. HARMONIC PATTERNS
# ==========================================

def detect_harmonics(df: pd.DataFrame, pivot_order: int = 5) -> List[Dict]:
    swings = find_swings(df, pivot_order)
    pivots = []

    for t, r in swings.iterrows():
        if not np.isnan(r["pivot_high"]):
            pivots.append(r["pivot_high"])
        if not np.isnan(r["pivot_low"]):
            pivots.append(r["pivot_low"])

    if len(pivots) < 5:
        return []

    return [{"pattern": "SIMPLIFIED_HARMONIC"}]


# ==========================================
# 5. ELLIOTT WAVE ANALYSIS
# ==========================================

def analyze_elliott_structure(df: pd.DataFrame, order: int = 5) -> Dict:
    swings = find_swings(df, order)
    pivots = swings.dropna(how="all")

    if len(pivots) < 5:
        return {"status": "Insufficient Data"}

    return {
        "wave_count_bias": "NEUTRAL",
        "w2_depth": None,
        "w4_depth": None
    }
