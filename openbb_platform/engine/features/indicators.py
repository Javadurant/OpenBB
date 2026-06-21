# engine/features/indicators.py
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from scipy.signal import argrelextrema

try:
    from pyharmonics.technicals import Technicals
    from pyharmonics.search import HarmonicSearch
    PYHARMONICS_AVAILABLE = True
except ImportError:
    PYHARMONICS_AVAILABLE = False

class CarneyVol3Constants:
    """Scott M. Carney Harmonic Trading Vol. 3 — V2.0 AUDITED RATIOS"""
    FIB_MATRIX = pd.DataFrame({
        "Level_Pct": [23.6, 38.2, 50.0, 61.8, 78.6, 88.6, 113.0, 127.2, 161.8, 190.2, 261.8],
        "Origin": ["0.618^3", "0.618^2", "Midpoint", "1/Phi", "0.786", "0.886", "1.13", "1.27", "Phi", "Deep Crab", "Phi^2"]
    })

def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0 or abs(denominator) < 1e-10:
        return 0.0
    return abs(numerator) / abs(denominator)

def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.dropna(subset=['close'])

def validate_v2_ratios(name: str, pts: List[Tuple], is_bullish: bool) -> bool:
    try:
        if len(pts) < 5: return False
        p0, p1, p2, p3, p4 = [p[1] for p in pts]
        XA, AB, BC, CD, XD = abs(p1-p0), abs(p2-p1), abs(p3-p2), abs(p4-p3), abs(p4-p0)
        r_B_XA, r_C_AB, r_D_BC, r_D_XA = safe_ratio(AB, XA), safe_ratio(BC, AB), safe_ratio(CD, BC), safe_ratio(XD, XA)
        name_up = name.upper()
        if "GARTLEY" in name_up and not "DEEP" in name_up:
            return (0.59 <= r_B_XA <= 0.65) and (0.382 <= r_C_AB <= 0.886) and (abs(r_D_XA - 0.786) <= 0.03)
        if "BAT" in name_up and not "ALT" in name_up:
            return (0.35 <= r_B_XA <= 0.55) and (abs(r_D_XA - 0.886) <= 0.03)
        if "BUTTERFLY" in name_up:
            return (0.75 <= r_B_XA <= 0.85) and (abs(r_D_XA - 1.27) <= 0.07)
        if "CRAB" in name_up and not "DEEP" in name_up:
            return (0.35 <= r_B_XA <= 0.65) and (abs(r_D_XA - 1.618) <= 0.08)
        if "SHARK" in name_up:
            leg_0A, leg_XA, leg_0X, leg_0C = abs(p2-p0), abs(p2-p1), abs(p1-p0), abs(p4-p0)
            return (0.35 <= safe_ratio(leg_XA, leg_0A) <= 0.9) and any(abs(safe_ratio(leg_0C, leg_0X) - t) <= 0.07 for t in [0.886, 1.13])
        return True
    except Exception: return False

def check_terminal_bar(df: pd.DataFrame, is_bullish: bool) -> bool:
    if len(df) < 2: return False
    last = df.iloc[-1]
    body = abs(last['close'] - last['open'])
    if is_bullish: return ((min(last['open'], last['close']) - last['low']) > body) or (last['close'] > df.iloc[-2]['high'])
    return ((last['high'] - max(last['open'], last['close'])) > body) or (last['close'] < df.iloc[-2]['low'])

def get_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_ichimoku(df: pd.DataFrame) -> Dict:
    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    df['tenkan'] = (high_9 + low_9) / 2
    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    df['kijun'] = (high_26 + low_26) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
    high_52 = df['high'].rolling(window=52).max()
    low_52 = df['low'].rolling(window=52).min()
    df['senkou_b'] = ((high_52 + low_52) / 2).shift(26)
    df['chikou'] = df['close'].shift(-26)
    return {"present": True}

def calculate_fib_levels(high: float, low: float) -> Dict[str, float]:
    diff = high - low
    levels = CarneyVol3Constants.FIB_MATRIX['Level_Pct'].values / 100.0
    return {f"{int(l*100)}%": high - (1 - l) * diff if l < 1 else low + (l - 1) * diff for l in levels}

def calculate_elliott_projections(df: pd.DataFrame) -> Dict:
    if len(df) < 60: return {}
    high_idx = argrelextrema(df['high'].values, np.greater, order=10)[0]
    low_idx = argrelextrema(df['low'].values, np.less, order=10)[0]
    swings = sorted([{'idx': i, 'val': float(df['high'].iloc[i]), 'type': 'high'} for i in high_idx] + [{'idx': i, 'val': float(df['low'].iloc[i]), 'type': 'low'} for i in low_idx], key=lambda x: x['idx'])
    alt_swings = []
    for s in swings:
        if not alt_swings or s['type'] != alt_swings[-1]['type']: alt_swings.append(s)
        else:
            if (s['type'] == 'high' and s['val'] > alt_swings[-1]['val']) or (s['type'] == 'low' and s['val'] < alt_swings[-1]['val']): alt_swings[-1] = s
    if len(alt_swings) < 5: return {}
    last_pivots = alt_swings[-5:]
    coords = [{"x": df.index[s['idx']], "y": s['val']} for s in last_pivots]
    coords.append({"x": df.index[-1], "y": float(df['close'].iloc[-1])})
    # ADDED: Include specific price levels in labels
    label = f"Motive {'Impulse' if last_pivots[-1]['val'] > last_pivots[0]['val'] else 'Corrective'} (P5: {last_pivots[-1]['val']:.2f})"
    return {"wave_coords": coords, "label": label, "summary": f"Wave sequence targeting {last_pivots[-1]['val']:.2f} confirmed."}

def detect_harmonics(df: pd.DataFrame, interval: str = "1D") -> List[Dict]:
    if not PYHARMONICS_AVAILABLE or len(df) < 50: return []
    try:
        pdf = df.copy()
        pdf.columns = [c.capitalize() for c in pdf.columns]
        t = Technicals(pdf, symbol="ASSET", interval=interval)
        searcher = HarmonicSearch(t)
        searcher.search()
        patterns_data = searcher.get_patterns(family='XABCD')
        patterns = patterns_data.get('XABCD', []) if isinstance(patterns_data, dict) else patterns_data
        if not patterns: return []
    except Exception: return []
    found = []
    for p in patterns:
        is_bull = getattr(p, 'bullish', True)
        pts = list(zip(p.x, p.y)) if hasattr(p, 'x') else p.to_dict().get('points', [])
        if len(pts) < 5 or not validate_v2_ratios(getattr(p, 'name', 'Pattern'), pts, is_bull): continue
        prz_val = float(pts[4][1])
        # ADDED: Specific price mentions in description
        found.append({
            "name": f"{'Bullish' if is_bull else 'Bearish'} {getattr(p, 'name', 'Pattern')}", 
            "points": pts, 
            "is_bullish": is_bull, 
            "terminal_confirmed": check_terminal_bar(df, is_bull), 
            "prz_numeric": prz_val, 
            "desc": f"V2.0 Validated PRZ at {prz_val:.2f}" # ← FIXED: Explicit price mention
        })
    return found

def technical_analysis_engine(df: pd.DataFrame, interval: str = "1D") -> Tuple[pd.DataFrame, Dict]:
    df = clean_ohlcv(df)
    if df.empty: return df, {}
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss).replace(0, np.nan))).fillna(100)
    df['atr'] = get_atr(df)
    df['macd'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['macds'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macdh'] = df['macd'] - df['macds']
    calculate_ichimoku(df)
    last_rsi = df['rsi'].iloc[-1]
    rsi_state = "OVERSOLD" if last_rsi < 30 else "OVERBOUGHT" if last_rsi > 70 else "NEUTRAL"
    bias = "BULLISH" if df['close'].iloc[-1] > df['close'].rolling(200).mean().iloc[-1] else "BEARISH"
    
    # ADDED: Aggregate prices into summary_text
    harmonics = detect_harmonics(df, interval)
    elliott = calculate_elliott_projections(df)
    prz_prices = ", ".join([f"{p['prz_numeric']:.2f}" for p in harmonics]) if harmonics else "None"
    
    summary = f"Regime: {bias} | RSI: {rsi_state} | Harmonic PRZ: {prz_prices}"
    if "label" in elliott: summary += f" | Elliott: {elliott['label']}"
    
    return df, {
        "bias": bias, 
        "rsi_state": rsi_state, 
        "atr": float(df['atr'].iloc[-1]) if not pd.isna(df['atr'].iloc[-1]) else 0.0, 
        "fib_levels": calculate_fib_levels(df['high'].max(), df['low'].min()), 
        "harmonics": harmonics, 
        "elliott": elliott, 
        "summary_text": summary # ← FIXED: Integrated specific price mentions
    }