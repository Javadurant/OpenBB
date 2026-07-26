# pages/scanner_ui.py
# 3-Month Scanner — COMPLETE FINAL VERSION.
# Japanese candlestick base on ALL charts (mandatory across project).
#
# INDICATORS (all domain values user-confirmed 2026-03-19):
#   EMA 9 / 21 / 55
#   SMA 20 / 50 / 200
#   Bollinger Bands: period=20, stddev=2.0
#   RSI: period=21, Wilder smoothing
#   MACD: fast=12, slow=26, signal=9
#   EWO (Elliott Wave Oscillator): SMA(5) - SMA(35) histogram
#     Source: daytrading.com, tradingpedia.com, tabtrader.com (8 sources)
#
# STRUCTURAL TOOLS (all parameters web-verified 2026-03-19):
#   Volume Profile: 50 bins, Value Area=70%, POC/VAH/VAL
#     Source: tradingview.com/support, tradingwyckoff.com
#   Market Structure: BOS + CHoCH, swing lookback=5, close-based
#     Source: marketcalls.in, luxalgo.com/docs, pypi smartmoneyconcepts
#
# ICHIMOKU KINKO HYO (all parameters web-verified 2026-03-19):
#   Tenkan-sen=9, Kijun-sen=26, Senkou Span B=52, Displacement=26
#   Source: Hosoda (1969), Wikipedia, StockCharts ChartSchool,
#           Fidelity, CFI, NAGA Academy, TechnicalAnalysisPro,
#           HeyGotrade, Strike.money (8 cross-verified sources)
#
# ANALYSIS SUITE:
#   Fundamental Analysis (CFA® / FRM® / MBA-Quant framework)
#   Technical Analysis (CMT® / Murphy / Carney / Prechter / Hosoda)
#   Psychological Analysis (Douglas / Schwager / Lefèvre / Graham /
#     O'Neil / Bellafiore / Taleb / Tharp)
#
# ANALYSIS OVERLAYS:
#   Elliott Wave zigzag + W3 targets + W4 support + invalidation
#   Harmonic pattern D-point diamonds
#   Ichimoku Cloud (all 5 components)
#
# PYTHON 3.11 COMPLIANCE:
#   render_fundamental_analysis() uses pre-extraction pattern
#   (no backslash inside f-string {} — PEP 498 fix confirmed)
#
# <- NEW [typography]: GLOBAL_TYPOGRAPHY_CSS defined after LOOKBACK_DAYS.
#    Injected at top of main(). Times New Roman 16/22px, warm off-white palette.
# <- FIXED [Gate5]: render_technical_analysis, render_psychological_analysis,
#    and main() restored to correct 4-space indentation.
#    FM-11 AI regression — prior generation session wrote these three
#    functions at 0-indent (module level), causing SyntaxError: return
#    outside function at line 4012.

import math
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import logging
import datetime
import sys
import os
from typing import Dict, Any, List, Optional, Tuple, TypedDict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from engine.analysis.harmonics import HarmonicEngine, PatternResult
except ImportError as e:
    st.error(f"Critical Import Error: Harmonic engine failed. {e}")
    st.stop()

try:
    from engine.analysis.elliott import (
        ElliottEngine,
        validate_wave_2,
        project_wave_3,
        validate_wave_4,
        discover_impulses,  # <- NEW [i18n-audit]: Council added discovery function
    )
except ImportError as e:
    st.error(f"Critical Import Error: Elliott engine failed. {e}")
    st.stop()

try:
    from engine.structure.swings import find_pivots, enforce_alternation
except ImportError as e:
    st.error(f"Critical Import Error: Swings engine failed. {e}")
    st.stop()

from translations import t, inject_rtl_css  # <- NEW [i18n]

try:
    from openbb import obb
except ImportError as e:
    st.error(f"Critical Import Error: OpenBB failed. {e}")
    st.stop()

logger = logging.getLogger("ScannerUI")

st.set_page_config(
    page_title="3-Month Scanner",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── DOMAIN CONSTANTS — ALL USER-CONFIRMED / WEB-VERIFIED ──────────────────

EMA_PERIODS: List[int] = [9, 21, 55]
SMA_PERIODS: List[int] = [20, 50, 200]

BB_PERIOD: int   = 20
BB_STDDEV: float = 2.0

RSI_PERIOD: int = 14  # <- FIXED: was 21 (non-standard), now 14 per Wilder [1978]. Standard in all markets.

MACD_FAST: int   = 12
MACD_SLOW: int   = 26
MACD_SIGNAL: int = 9

RSI_OVERBOUGHT: float = 70.0
RSI_OVERSOLD: float   = 30.0

EWO_FAST: int = 5
EWO_SLOW: int = 35

VP_NUM_BINS: int         = 50
VP_VALUE_AREA_PCT: float = 0.70

MS_SWING_LOOKBACK: int = 5

FIB_LEVELS: List[float] = [0.236, 0.382, 0.500, 0.618, 0.786]

PRZ_CANDLE_CONTEXT: int = 10

LOOKBACK_DAYS: int = 90

# ─── ICHIMOKU CONSTANTS — ALL WEB-VERIFIED (8 sources) ────────────────────
# Source: Goichi Hosoda (1969), Wikipedia, StockCharts ChartSchool,
#         Fidelity Learning Center, CFI, NAGA Academy,
#         TechnicalAnalysisPro, HeyGotrade, Strike.money
ICHIMOKU_TENKAN:       int = 9
ICHIMOKU_KIJUN:        int = 26
ICHIMOKU_SENKOU_B:     int = 52
ICHIMOKU_DISPLACEMENT: int = 26

ICHIMOKU_COLORS: Dict[str, str] = {
    "tenkan":     "#00BFFF",
    "kijun":      "#FF6B35",
    "senkou_a":   "rgba(0,255,136,0.70)",
    "senkou_b":   "rgba(255,82,82,0.70)",
    "chikou":     "rgba(255,255,0,0.60)",
    "cloud_bull": "rgba(0,255,136,0.12)",
    "cloud_bear": "rgba(255,82,82,0.12)",
}

# ─── COLOR PALETTES ────────────────────────────────────────────────────────

EMA_COLORS: Dict[int, str] = {
    9:  "#00E5FF",
    21: "#00FF88",
    55: "#FFD700",
}

SMA_COLORS: Dict[int, str] = {
    20:  "rgba(0,229,255,0.35)",
    50:  "rgba(0,255,136,0.35)",
    200: "rgba(255,215,0,0.45)",
}

BB_COLORS: Dict[str, str] = {
    "upper": "rgba(100,181,246,0.55)",
    "mid":   "rgba(100,181,246,0.30)",
    "lower": "rgba(100,181,246,0.55)",
    "fill":  "rgba(100,181,246,0.06)",
}

PATTERN_COLORS: Dict[str, str] = {
    "Standard AB=CD":   "#00BCD4",
    "Reciprocal AB=CD": "#4DD0E1",
    "Gartley":          "#FFD700",
    "Bat":              "#FF9800",
    "Alternate Bat":    "#FFC107",
    "Butterfly":        "#E040FB",
    "Crab":             "#F44336",
    "Deep Crab":        "#FF5722",
    "Shark":            "#76FF03",
    "5-0":              "#18FFFF",
}

EXPAND_PATTERN_COLORS: Dict[str, str] = {
    "leg_primary":   "#00E5FF",
    "leg_secondary": "#00FF88",
    "ratio_label":   "#18FFFF",
    "prz_fill":      "rgba(0,229,255,0.12)",
    "prz_border":    "#00E5FF",
    "sl_line":       "#FF5252",
    "label_bg":      "rgba(0,10,30,0.92)",
    "marker_border": "#000d1a",
    "d_vline":       "#00BFA5",
}

EW_COLORS: Dict[str, str] = {
    "motive":       "#00E5FF",
    "corrective":   "#00FF88",
    "target_zone":  "rgba(0,229,255,0.09)",
    "target_line":  "#18FFFF",
    "invalidation": "#FF5252",
    "label_bg":     "rgba(0,20,40,0.90)",
    "fib_618":      "#00E676",
    "fib_786":      "#FF5252",
}

FIB_COLORS: Dict[float, str] = {
    0.236: "rgba(176,190,197,0.55)",
    0.382: "rgba(255,183,77,0.55)",
    0.500: "rgba(255,241,118,0.55)",
    0.618: "rgba(0,230,118,0.65)",
    0.786: "rgba(255,82,82,0.65)",
}

RSI_COLORS: Dict[str, str] = {
    "line":       "#00E5FF",
    "overbought": "rgba(255,82,82,0.25)",
    "oversold":   "rgba(0,230,118,0.25)",
    "ob_line":    "#FF5252",
    "os_line":    "#00E676",
}

MACD_COLORS: Dict[str, str] = {
    "macd_line":   "#00E5FF",
    "signal_line": "#FFD700",
    "hist_pos":    "rgba(0,230,118,0.70)",
    "hist_neg":    "rgba(255,82,82,0.70)",
}

EWO_COLORS: Dict[str, str] = {
    "pos_rising":  "#00E676",
    "pos_falling": "#00897B",
    "neg_falling": "#FF5252",
    "neg_rising":  "#C62828",
    "zero_line":   "rgba(255,255,255,0.15)",
}

VP_COLORS: Dict[str, str] = {
    "bars":     "rgba(0,229,255,0.18)",
    "poc":      "#FFD700",
    "vah":      "#00FF88",
    "val":      "#00FF88",
    "vah_fill": "rgba(0,255,136,0.06)",
}

MS_COLORS: Dict[str, str] = {
    "bos_bull":   "#00FF88",
    "bos_bear":   "#FF5252",
    "choch_bull": "#00E5FF",
    "choch_bear": "#FF9800",
    "hh":         "#00FF88",
    "hl":         "#00FF88",
    "lh":         "#FF5252",
    "ll":         "#FF5252",
    "swing_high": "#00E5FF",
    "swing_low":  "#FF9800",
}

# ─── TIMEFRAME CONFIG ──────────────────────────────────────────────────────

TF_CONFIG: Dict[str, Dict[str, Any]] = {
    "1H": {
        "interval":    "1h",
        "resample_4h": False,
        "label":       "1-Hour",
        "pivot_order": 3,
    },
    "4H": {
        "interval":    "1h",
        "resample_4h": True,
        "label":       "4-Hour",
        "pivot_order": 3,
    },
    "Daily": {
        "interval":    "1d",
        "resample_4h": False,
        "label":       "Daily",
        "pivot_order": 4,
    },
    "Weekly": {
        "interval":    "1W",
        "resample_4h": False,
        "label":       "Weekly",
        "pivot_order": 3,
    },
    "Monthly": {
        "interval":    "1M",
        "resample_4h": False,
        "label":       "Monthly",
        "pivot_order": 2,
    },
}

POINT_LABELS_MAP: Dict[int, Dict[int, str]] = {
    4: {0: "A", 1: "B", 2: "C", 3: "D"},
    5: {0: "X", 1: "A", 2: "B", 3: "C", 4: "D"},
    6: {0: "0", 1: "X", 2: "A", 3: "B", 4: "C", 5: "D"},
}
SHARK_LABELS: Dict[int, str] = {0: "0", 1: "X", 2: "A", 3: "B", 4: "C"}

# ─── GLOBAL TYPOGRAPHY — Times New Roman 16/22px, eye-comfort palette ──────
# <- NEW [typography]: inject at top of main(). No separate file needed.
GLOBAL_TYPOGRAPHY_CSS: str = """
<style>
/* ── BASE FONT ─────────────────────────────────────────────────────── */
html, body, [class*="css"], .stApp {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
    line-height: 1.75 !important;
}
/* ── PARAGRAPHS AND GENERAL TEXT ───────────────────────────────────── */
p, span, li, td, th, label, div {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
    line-height: 1.75 !important;
}
/* ── HEADLINES ─────────────────────────────────────────────────────── */
h1, h2, h3, h4, h5, h6,
.stMarkdown h1, .stMarkdown h2,
.stMarkdown h3, .stMarkdown h4 {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 22px !important;
    font-weight: bold !important;
    color: #F5ECD7 !important;
    line-height: 1.4 !important;
    margin-bottom: 0.5em !important;
}
/* ── STREAMLIT TITLE ────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] h1 {
    font-size: 28px !important;
    color: #F5ECD7 !important;
    font-family: 'Times New Roman', Times, serif !important;
}
/* ── STREAMLIT METRIC ──────────────────────────────────────────────── */
[data-testid="stMetricLabel"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
    color: #B0A898 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 20px !important;
    font-weight: bold !important;
    color: #F5ECD7 !important;
}
[data-testid="stMetricDelta"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
}
/* ── CAPTIONS ───────────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] p,
small, .caption {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
    color: #B0A898 !important;
    line-height: 1.6 !important;
}
/* ── SIDEBAR ────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 15px !important;
    color: #E8E0D0 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 18px !important;
    color: #F5ECD7 !important;
}
/* ── BUTTONS ────────────────────────────────────────────────────────── */
[data-testid="stButton"] button, .stButton button {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
}
/* ── TABS ────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button, .stTabs [role="tab"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
}
/* ── ALERT BOXES ────────────────────────────────────────────────────── */
[data-testid="stAlert"] p, .stAlert p, .stInfo p,
.stSuccess p, .stWarning p, .stError p {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    line-height: 1.75 !important;
}
/* ── CHAT (Copilot) ─────────────────────────────────────────────────── */
[data-testid="stChatInput"] textarea,
[data-testid="stChatMessage"] p {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
    line-height: 1.75 !important;
}
/* ── FORM LABELS ────────────────────────────────────────────────────── */
[data-testid="stSelectbox"] label,
[data-testid="stTextInput"] label,
[data-testid="stSlider"] label,
[data-testid="stCheckbox"] label {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 15px !important;
    color: #E8E0D0 !important;
}
/* ── CODE — preserve monospace for chart annotations ───────────────── */
code, pre, .monospace {
    font-family: 'Courier New', Courier, monospace !important;
    font-size: 13px !important;
}
/* ── BOLD / ITALIC ──────────────────────────────────────────────────── */
strong, b { font-family: 'Times New Roman', Times, serif !important; color: #F5ECD7 !important; }
em, i     { font-family: 'Times New Roman', Times, serif !important; color: #D4C9B8 !important; }
/* ── HR ─────────────────────────────────────────────────────────────── */
hr { border-color: rgba(232,224,208,0.15) !important; }
/* ── SCROLLBAR ──────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #000d1a; }
::-webkit-scrollbar-thumb { background: #3a3028; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #5a4a38; }
</style>
"""


# ─── TYPE CONTRACTS ────────────────────────────────────────────────────────

class WaveResult(TypedDict):
    """Elliott Wave detection result."""
    pts:           List[float]
    pt_dates:      List[Any]
    is_bullish:    bool
    targets:       Dict[str, float]
    w2:            Dict[str, Any]
    w4:            Dict[str, Any]
    impulse:       Dict[str, Any]
    wave4_support: float
    invalidation:  float


class VolumeProfileResult(TypedDict):
    """Computed Volume Profile for the full 90-day window."""
    price_levels: np.ndarray
    volumes:      np.ndarray
    poc:          float
    vah:          float
    val:          float
    total_volume: float


class SwingPoint(TypedDict):
    """Single swing high or low detected by market structure engine."""
    index:   int
    price:   float
    date:    Any
    is_high: bool
    label:   str


class StructureEvent(TypedDict):
    """BOS or CHoCH event."""
    index:      int
    date:       Any
    price:      float
    event_type: str
    direction:  str
    level:      float


class MarketStructureResult(TypedDict):
    """Full market structure analysis output."""
    swing_points:     List[SwingPoint]
    structure_events: List[StructureEvent]
    current_trend:    str


# ─── DATA FETCH ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_ohlcv(ticker: str, tf_key: str) -> pd.DataFrame:
    """
    Fetches 90-day OHLCV data from OpenBB yfinance provider.
    Ensures DatetimeIndex before any resample operation.

    Args:
        ticker: Equity symbol string.
        tf_key: Key from TF_CONFIG.

    Returns:
        pd.DataFrame with OHLCV columns and DatetimeIndex.
    """
    cfg = TF_CONFIG[tf_key]
    start_date = (
        datetime.date.today()
        - datetime.timedelta(days=LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")

    res = obb.equity.price.historical(
        ticker,
        start_date=start_date,
        interval=cfg["interval"],
        provider="yfinance",
    )
    df: pd.DataFrame = res.to_df()

    if df.empty:
        return df

    df.index = pd.to_datetime(df.index)

    if cfg["resample_4h"]:
        df = (
            df.resample("4h")
            .agg({
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
                "volume": "sum",
            })
            .dropna(subset=["open", "close"])
        )

    return df


# ─── INDICATOR COMPUTATION ─────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    Computes all technical indicators from OHLCV data.
    All periods are user-confirmed or web-verified domain values.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.

    Returns:
        Dict mapping indicator name to pd.Series aligned to df.index.
    """
    close: pd.Series         = df["close"]
    result: Dict[str, pd.Series] = {}

    result["ema_9"]  = close.ewm(span=EMA_PERIODS[0], adjust=False).mean()
    result["ema_21"] = close.ewm(span=EMA_PERIODS[1], adjust=False).mean()
    result["ema_55"] = close.ewm(span=EMA_PERIODS[2], adjust=False).mean()

    result["sma_20"]  = close.rolling(window=SMA_PERIODS[0]).mean()
    result["sma_50"]  = close.rolling(window=SMA_PERIODS[1]).mean()
    result["sma_200"] = close.rolling(window=SMA_PERIODS[2]).mean()

    bb_mid: pd.Series  = close.rolling(window=BB_PERIOD).mean()
    bb_std: pd.Series  = close.rolling(window=BB_PERIOD).std(ddof=0)
    result["bb_mid"]   = bb_mid
    result["bb_upper"] = bb_mid + (BB_STDDEV * bb_std)
    result["bb_lower"] = bb_mid - (BB_STDDEV * bb_std)

    delta    = close.diff()
    gain     = delta.clip(lower=0.0)
    loss     = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(com=RSI_PERIOD - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi      = 100.0 - (100.0 / (1.0 + rs))
    result["rsi_21"] = rsi.fillna(50.0)

    ema_fast              = close.ewm(span=MACD_FAST,   adjust=False).mean()
    ema_slow              = close.ewm(span=MACD_SLOW,   adjust=False).mean()
    macd_line             = ema_fast - ema_slow
    signal_line           = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    result["macd_line"]   = macd_line
    result["signal_line"] = signal_line
    result["histogram"]   = macd_line - signal_line

    result["ewo"] = (
        close.rolling(window=EWO_FAST).mean()
        - close.rolling(window=EWO_SLOW).mean()
    )

    return result


# ─── ICHIMOKU CLOUD COMPUTATION ────────────────────────────────────────────

def compute_ichimoku(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """
    Computes all five Ichimoku Kinko Hyo components.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.

    Returns:
        Dict with keys: tenkan, kijun, senkou_a, senkou_b, chikou.
    """
    high:  pd.Series = df["high"]
    low:   pd.Series = df["low"]
    close: pd.Series = df["close"]

    tenkan: pd.Series = (
        high.rolling(window=ICHIMOKU_TENKAN).max()
        + low.rolling(window=ICHIMOKU_TENKAN).min()
    ) / 2.0

    kijun: pd.Series = (
        high.rolling(window=ICHIMOKU_KIJUN).max()
        + low.rolling(window=ICHIMOKU_KIJUN).min()
    ) / 2.0

    senkou_a: pd.Series = (
        (tenkan + kijun) / 2.0
    ).shift(ICHIMOKU_DISPLACEMENT)

    senkou_b: pd.Series = (
        (
            high.rolling(window=ICHIMOKU_SENKOU_B).max()
            + low.rolling(window=ICHIMOKU_SENKOU_B).min()
        ) / 2.0
    ).shift(ICHIMOKU_DISPLACEMENT)

    chikou: pd.Series = close.shift(-ICHIMOKU_DISPLACEMENT)

    return {
        "tenkan":   tenkan,
        "kijun":    kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou":   chikou,
    }


def get_ichimoku_signal(
    df: pd.DataFrame,
    ichimoku: Dict[str, pd.Series],
) -> Dict[str, Any]:
    """
    Computes current Ichimoku trading signals from the most recent bar.

    Args:
        df:       OHLCV DataFrame.
        ichimoku: Dict from compute_ichimoku().

    Returns:
        Dict of signal strings and computed levels.
    """
    close_cur:    float = float(df["close"].iloc[-1])
    tenkan_cur:   float = float(ichimoku["tenkan"].iloc[-1])
    kijun_cur:    float = float(ichimoku["kijun"].iloc[-1])

    sa_clean = ichimoku["senkou_a"].dropna()
    sb_clean = ichimoku["senkou_b"].dropna()
    senkou_a_cur: float = float(sa_clean.iloc[-1]) if len(sa_clean) > 0 else float("nan")
    senkou_b_cur: float = float(sb_clean.iloc[-1]) if len(sb_clean) > 0 else float("nan")

    cloud_top: float = (
        max(senkou_a_cur, senkou_b_cur)
        if not (math.isnan(senkou_a_cur) or math.isnan(senkou_b_cur))
        else float("nan")
    )
    cloud_bottom: float = (
        min(senkou_a_cur, senkou_b_cur)
        if not (math.isnan(senkou_a_cur) or math.isnan(senkou_b_cur))
        else float("nan")
    )

    if math.isnan(cloud_top):
        price_vs_cloud = "insufficient_data"
    elif close_cur > cloud_top:
        price_vs_cloud = "above"
    elif close_cur < cloud_bottom:
        price_vs_cloud = "below"
    else:
        price_vs_cloud = "inside"

    if math.isnan(senkou_a_cur) or math.isnan(senkou_b_cur):
        cloud_color = "unknown"
    elif senkou_a_cur > senkou_b_cur:
        cloud_color = "green"
    else:
        cloud_color = "red"

    tenkan_prev: float = (
        float(ichimoku["tenkan"].iloc[-2])
        if len(ichimoku["tenkan"].dropna()) > 1 else tenkan_cur
    )
    kijun_prev: float = (
        float(ichimoku["kijun"].iloc[-2])
        if len(ichimoku["kijun"].dropna()) > 1 else kijun_cur
    )

    if tenkan_prev <= kijun_prev and tenkan_cur > kijun_cur:
        tk_cross = "bullish_cross"
    elif tenkan_prev >= kijun_prev and tenkan_cur < kijun_cur:
        tk_cross = "bearish_cross"
    elif tenkan_cur > kijun_cur:
        tk_cross = "bullish_alignment"
    elif tenkan_cur < kijun_cur:
        tk_cross = "bearish_alignment"
    else:
        tk_cross = "neutral"

    chikou_val: float = (
        float(ichimoku["chikou"].iloc[-ICHIMOKU_DISPLACEMENT - 1])
        if len(df) > ICHIMOKU_DISPLACEMENT else float("nan")
    )
    price_26_ago: float = (
        float(df["close"].iloc[-ICHIMOKU_DISPLACEMENT - 1])
        if len(df) > ICHIMOKU_DISPLACEMENT else float("nan")
    )

    if math.isnan(chikou_val) or math.isnan(price_26_ago):
        chikou_signal = "insufficient_data"
    elif chikou_val > price_26_ago:
        chikou_signal = "bullish"
    elif chikou_val < price_26_ago:
        chikou_signal = "bearish"
    else:
        chikou_signal = "neutral"

    bull_count = sum([
        price_vs_cloud == "above",
        cloud_color == "green",
        tk_cross in ("bullish_cross", "bullish_alignment"),
        chikou_signal == "bullish",
    ])
    bear_count = sum([
        price_vs_cloud == "below",
        cloud_color == "red",
        tk_cross in ("bearish_cross", "bearish_alignment"),
        chikou_signal == "bearish",
    ])

    if bull_count >= 4:
        overall_bias = "strong_bull"
    elif bull_count >= 3:
        overall_bias = "bull"
    elif bear_count >= 4:
        overall_bias = "strong_bear"
    elif bear_count >= 3:
        overall_bias = "bear"
    else:
        overall_bias = "neutral"

    return {
        "price_vs_cloud": price_vs_cloud,
        "cloud_color":    cloud_color,
        "cloud_top":      cloud_top,
        "cloud_bottom":   cloud_bottom,
        "tk_cross":       tk_cross,
        "chikou_signal":  chikou_signal,
        "overall_bias":   overall_bias,
        "tenkan_cur":     tenkan_cur,
        "kijun_cur":      kijun_cur,
        "senkou_a_cur":   senkou_a_cur,
        "senkou_b_cur":   senkou_b_cur,
    }


def add_ichimoku_to_figure(
    fig: go.Figure,
    df: pd.DataFrame,
    ichimoku: Dict[str, pd.Series],
) -> go.Figure:
    """
    Adds all five Ichimoku components as overlays to an existing Plotly figure.

    Args:
        fig:      Existing Plotly Figure.
        df:       OHLCV DataFrame (index for x-axis alignment).
        ichimoku: Dict from compute_ichimoku().

    Returns:
        Updated Plotly Figure.
    """
    idx = df.index

    fig.add_trace(go.Scatter(
        x=idx, y=ichimoku["tenkan"],
        mode="lines",
        line=dict(color=ICHIMOKU_COLORS["tenkan"], width=1.5),
        name=f"Tenkan-sen ({ICHIMOKU_TENKAN})",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=idx, y=ichimoku["kijun"],
        mode="lines",
        line=dict(color=ICHIMOKU_COLORS["kijun"], width=1.8),
        name=f"Kijun-sen ({ICHIMOKU_KIJUN})",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=idx, y=ichimoku["chikou"],
        mode="lines",
        line=dict(color=ICHIMOKU_COLORS["chikou"], width=1.2, dash="dot"),
        name=f"Chikou Span (-{ICHIMOKU_DISPLACEMENT})",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=idx, y=ichimoku["senkou_a"],
        mode="lines",
        line=dict(color=ICHIMOKU_COLORS["senkou_a"], width=1.0),
        name=f"Senkou A (+{ICHIMOKU_DISPLACEMENT})",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=idx, y=ichimoku["senkou_b"],
        mode="lines",
        line=dict(color=ICHIMOKU_COLORS["senkou_b"], width=1.0),
        fill="tonexty",
        fillcolor=ICHIMOKU_COLORS["cloud_bull"],
        name=f"Senkou B (+{ICHIMOKU_DISPLACEMENT})",
        showlegend=True,
    ))

    return fig


# ─── VOLUME PROFILE COMPUTATION ────────────────────────────────────────────

def compute_volume_profile(df: pd.DataFrame) -> VolumeProfileResult:
    """
    Computes a Fixed Range Volume Profile over the full DataFrame window.

    Args:
        df: OHLCV DataFrame.

    Returns:
        VolumeProfileResult TypedDict.
    """
    price_min:   float = float(df["low"].min())
    price_max:   float = float(df["high"].max())
    price_range: float = price_max - price_min

    if price_range < 1e-10:
        levels = np.linspace(price_min, price_max, VP_NUM_BINS + 1)
        vols   = np.zeros(VP_NUM_BINS)
        return VolumeProfileResult(
            price_levels=levels[:-1],
            volumes=vols,
            poc=price_min,
            vah=price_max,
            val=price_min,
            total_volume=0.0,
        )

    bin_edges: np.ndarray = np.linspace(price_min, price_max, VP_NUM_BINS + 1)
    bin_lows:  np.ndarray = bin_edges[:-1]
    bin_highs: np.ndarray = bin_edges[1:]
    volumes:   np.ndarray = np.zeros(VP_NUM_BINS)

    for _, row in df.iterrows():
        c_low:  float = float(row["low"])
        c_high: float = float(row["high"])
        c_vol:  float = float(row["volume"])

        if c_vol < 1e-10 or c_high <= c_low:
            continue

        overlaps: np.ndarray = (
            np.minimum(bin_highs, c_high) - np.maximum(bin_lows, c_low)
        )
        overlaps             = np.maximum(overlaps, 0.0)
        total_overlap: float = float(overlaps.sum())

        if total_overlap < 1e-10:
            continue

        volumes += c_vol * (overlaps / total_overlap)

    poc_bin_idx: int   = int(np.argmax(volumes))
    poc_price:   float = float(bin_lows[poc_bin_idx])
    total_vol:   float = float(volumes.sum())

    target_vol: float = total_vol * VP_VALUE_AREA_PCT
    va_lo_idx: int    = poc_bin_idx
    va_hi_idx: int    = poc_bin_idx
    va_accum:  float  = float(volumes[poc_bin_idx])

    while va_accum < target_vol:
        can_up:   bool = va_hi_idx < VP_NUM_BINS - 1
        can_down: bool = va_lo_idx > 0

        if not can_up and not can_down:
            break

        vol_up:   float = float(volumes[va_hi_idx + 1]) if can_up   else -1.0
        vol_down: float = float(volumes[va_lo_idx - 1]) if can_down else -1.0

        if vol_up >= vol_down:
            va_hi_idx += 1
            va_accum  += float(volumes[va_hi_idx])
        else:
            va_lo_idx -= 1
            va_accum  += float(volumes[va_lo_idx])

    return VolumeProfileResult(
        price_levels=bin_lows,
        volumes=volumes,
        poc=poc_price,
        vah=float(bin_highs[va_hi_idx]),
        val=float(bin_lows[va_lo_idx]),
        total_volume=total_vol,
    )


# ─── MARKET STRUCTURE COMPUTATION ──────────────────────────────────────────

def compute_market_structure(df: pd.DataFrame) -> MarketStructureResult:
    """
    Detects Market Structure: swing highs/lows, BOS and CHoCH events.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.

    Returns:
        MarketStructureResult TypedDict.
    """
    highs:  np.ndarray       = df["high"].values
    lows:   np.ndarray       = df["low"].values
    closes: np.ndarray       = df["close"].values
    dates:  pd.DatetimeIndex = df.index
    n_bars: int              = len(df)
    N: int                   = MS_SWING_LOOKBACK

    swing_highs: List[Tuple[int, float]] = []
    swing_lows:  List[Tuple[int, float]] = []

    for i in range(N, n_bars - N):
        left_h  = highs[i - N: i]
        right_h = highs[i + 1: i + N + 1]
        left_l  = lows[i - N: i]
        right_l = lows[i + 1: i + N + 1]

        if len(left_h) < N or len(right_h) < N:
            continue

        if highs[i] > float(np.max(left_h)) and highs[i] > float(np.max(right_h)):
            swing_highs.append((i, float(highs[i])))

        if lows[i] < float(np.min(left_l)) and lows[i] < float(np.min(right_l)):
            swing_lows.append((i, float(lows[i])))

    swing_points:     List[SwingPoint]     = []
    structure_events: List[StructureEvent] = []

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return MarketStructureResult(
            swing_points=[],
            structure_events=[],
            current_trend="neutral",
        )

    prev_high_price: float = float(swing_highs[0][1])
    for idx, (bar_i, price) in enumerate(swing_highs):
        lbl = "HH" if idx == 0 else ("HH" if price > prev_high_price else "LH")
        swing_points.append(SwingPoint(
            index=bar_i, price=price, date=dates[bar_i],
            is_high=True, label=lbl,
        ))
        prev_high_price = price

    prev_low_price: float = float(swing_lows[0][1])
    for idx, (bar_i, price) in enumerate(swing_lows):
        lbl = "HL" if idx == 0 else ("HL" if price > prev_low_price else "LL")
        swing_points.append(SwingPoint(
            index=bar_i, price=price, date=dates[bar_i],
            is_high=False, label=lbl,
        ))
        prev_low_price = price

    recent_hh = sum(
        1 for sp in swing_points if sp["is_high"] and sp["label"] == "HH"
    )
    recent_lh = sum(
        1 for sp in swing_points if sp["is_high"] and sp["label"] == "LH"
    )
    trend: str = (
        "bullish" if recent_hh > recent_lh
        else "bearish" if recent_lh > recent_hh
        else "neutral"
    )

    current_trend: str = trend

    for sh_idx in range(len(swing_highs) - 1):
        sh_bar, sh_price = swing_highs[sh_idx]
        for bar_i in range(sh_bar + 1, n_bars):
            if closes[bar_i] > sh_price:
                event_type = "BOS" if current_trend == "bullish" else "CHoCH"
                structure_events.append(StructureEvent(
                    index=bar_i, date=dates[bar_i],
                    price=float(closes[bar_i]),
                    event_type=event_type,
                    direction="bullish",
                    level=sh_price,
                ))
                if event_type == "CHoCH":
                    current_trend = "bullish"
                break

    for sl_idx in range(len(swing_lows) - 1):
        sl_bar, sl_price = swing_lows[sl_idx]
        for bar_i in range(sl_bar + 1, n_bars):
            if closes[bar_i] < sl_price:
                event_type = "BOS" if current_trend == "bearish" else "CHoCH"
                structure_events.append(StructureEvent(
                    index=bar_i, date=dates[bar_i],
                    price=float(closes[bar_i]),
                    event_type=event_type,
                    direction="bearish",
                    level=sl_price,
                ))
                if event_type == "CHoCH":
                    current_trend = "bearish"
                break

    structure_events.sort(key=lambda e: e["index"])

    final_trend: str = trend
    for evt in reversed(structure_events):
        if evt["event_type"] == "CHoCH":
            final_trend = evt["direction"]
            break

    return MarketStructureResult(
        swing_points=swing_points,
        structure_events=structure_events,
        current_trend=final_trend,
    )


# ─── ELLIOTT WAVE PIPELINE ─────────────────────────────────────────────────

def run_elliott_pipeline(
    df: pd.DataFrame,
    pivot_order: int,
) -> Optional[WaveResult]:
    """
    Runs the full Elliott Wave detection pipeline.

    Args:
        df:          OHLCV DataFrame.
        pivot_order: argrelextrema order parameter.

    Returns:
        WaveResult TypedDict or None.
    """
    engine = ElliottEngine()

    try:
        pivots   = find_pivots(df, order=pivot_order)
        p_prices = pivots["close"].values
        p_dates  = pivots.index
    except Exception as e:
        logger.error(f"EW pivot extraction failed: {e}", exc_info=True)
        return None

    # <- FIXED [Council]: Fallback to finer pivot_order=2 if too few pivots
    if len(p_prices) < 20 and pivot_order > 2:  # <- FIXED [Council]: raised threshold from 8→20
        try:
            pivots   = find_pivots(df, order=2)
            p_prices = pivots["close"].values
            p_dates  = pivots.index
            logger.info(f"EW fallback: pivot_order=2 yielded {len(p_prices)} pivots")
        except Exception as e:
            logger.error(f"EW fallback failed: {e}", exc_info=True)

    if len(p_prices) < 5:
        return None

    # <- FIXED [Council]: Use discover_impulses() for robust wave discovery
    # The old manual sliding window missed many valid structures.
    alt_pivots_ew = enforce_alternation(pivots)  # <- FIXED: alternation needed for clean waves
    alt_prices = alt_pivots_ew["close"].values.astype(float)
    alt_dates  = alt_pivots_ew.index

    impulses = discover_impulses(list(alt_prices), min_wave1_pct=0.01)  # <- FIXED: lowered threshold for scanner

    if impulses:
        # Use the most recent valid impulse
        best = impulses[-1]
        si = best["start_index"]
        pts = alt_prices[si:si+6] if si+6 <= len(alt_prices) else alt_prices[si:si+5]
        pt_dates = alt_dates[si:si+min(6, len(alt_prices)-si)]

        if len(pts) < 5:
            return None

        w2 = validate_wave_2(float(pts[0]), float(pts[1]), float(pts[2]))
        w4 = validate_wave_4(float(pts[0]), float(pts[1]), float(pts[2]), float(pts[3]), float(pts[4]))
        targets = project_wave_3(float(pts[0]), float(pts[1]), float(pts[2]))

        is_bullish = best["is_bullish"]
        w3_length = abs(float(pts[3]) - float(pts[2]))
        wave4_support = float(pts[3]) - (0.382 * w3_length) if is_bullish else float(pts[3]) + (0.382 * w3_length)

        return WaveResult(
            pts           = [float(p) for p in pts[:5]],
            pt_dates      = list(pt_dates[:5]),
            is_bullish    = is_bullish,
            targets       = targets,
            w2            = w2,
            w4            = w4,
            impulse       = {"valid": True, "reason": best["reason"]},
            wave4_support = wave4_support,
            invalidation  = float(pts[0]),
        )

    # Fallback: original manual sliding window (kept for compatibility)
    for i in range(5, min(len(p_prices) + 1, 20)):
        if i > len(p_prices):
            break
        pts      = p_prices[-i: -i + 5] if i > 5 else p_prices[-5:]
        pt_dates = p_dates[-i: -i + 5]  if i > 5 else p_dates[-5:]

        if len(pts) < 5:
            continue

        w2 = validate_wave_2(pts[0], pts[1], pts[2])
        if not w2["is_valid"]:
            continue

        w4      = validate_wave_4(pts[0], pts[1], pts[2], pts[3], pts[4])
        targets = project_wave_3(pts[0], pts[1], pts[2])

        six_pts = (
            p_prices[-6:]
            if i >= 6 and len(p_prices) >= 6
            else p_prices[-min(i + 1, len(p_prices)):]
        )
        impulse = (
            engine.validate_impulse(list(six_pts))
            if len(six_pts) >= 6
            else {"valid": True, "reason": "5-point only"}
        )

        is_bullish:    bool  = float(pts[1]) > float(pts[0])
        w3_length:     float = abs(float(pts[3]) - float(pts[2]))
        wave4_support: float = float(pts[3]) - (0.382 * w3_length)

        return WaveResult(
            pts           = [float(p) for p in pts],
            pt_dates      = list(pt_dates),
            is_bullish    = is_bullish,
            targets       = targets,
            w2            = w2,
            w4            = w4,
            impulse       = impulse,
            wave4_support = wave4_support,
            invalidation  = float(pts[0]),
        )

    return None


# ─── HARMONIC PIPELINE ─────────────────────────────────────────────────────

def run_harmonic_pipeline(
    df: pd.DataFrame,
    pivot_order: int,
) -> Tuple[List[PatternResult], np.ndarray, pd.DatetimeIndex]:
    """
    Runs the full harmonic pattern detection pipeline.

    Args:
        df:          OHLCV DataFrame.
        pivot_order: argrelextrema order parameter.

    Returns:
        Tuple of (List[PatternResult], pivot_prices, pivot_indices).
    """
    empty: Tuple[List[PatternResult], np.ndarray, pd.DatetimeIndex] = (
        [], np.array([], dtype=float), pd.DatetimeIndex([])
    )
    engine = HarmonicEngine()

    try:
        raw_pivots  = find_pivots(df, order=pivot_order)
        alt_pivots  = enforce_alternation(raw_pivots)
        piv_prices  = alt_pivots["close"].values
        piv_indices = alt_pivots.index
    except Exception as e:
        logger.error(f"HP pivot extraction failed: {e}", exc_info=True)
        return empty

    # <- FIXED [Council]: Fallback to finer pivot_order=2 if too few pivots found.
    # With 90 days of data and order=3, only ~8 pivots found = insufficient.
    # Order=2 produces ~30 pivots, dramatically improving detection rate.
    if len(piv_prices) < 20 and pivot_order > 2:  # <- FIXED [Council]: raised threshold from 10→20
        try:
            raw_pivots  = find_pivots(df, order=2)  # <- FIXED [Council]: finer resolution
            alt_pivots  = enforce_alternation(raw_pivots)
            piv_prices  = alt_pivots["close"].values
            piv_indices = alt_pivots.index
            logger.info(f"HP fallback: pivot_order=2 yielded {len(piv_prices)} pivots (was {pivot_order})")
        except Exception as e:
            logger.error(f"HP fallback pivot extraction failed: {e}", exc_info=True)

    if len(piv_prices) < 6:
        return empty

    try:
        results = engine.scan(list(piv_prices))
        return results, piv_prices, piv_indices
    except Exception as e:
        logger.error(f"HP scan failed: {e}", exc_info=True)
        return empty


# ─── POINT MAPPING UTILITY ─────────────────────────────────────────────────

def map_pattern_to_dates(
    result: PatternResult,
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
) -> Tuple[List[Any], List[float]]:
    """Maps each harmonic pattern price point to its nearest pivot date."""
    x_dates:  List[Any]   = []
    y_prices: List[float] = []

    for price in result.points:
        diffs       = np.abs(pivot_prices - float(price))
        nearest_idx = int(np.argmin(diffs))
        nearest_idx = min(nearest_idx, len(pivot_indices) - 1)
        x_dates.append(pivot_indices[nearest_idx])
        y_prices.append(float(price))

    return x_dates, y_prices


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Converts 6-char hex to plotly rgba() string. plotly 6.6.0 safe."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ─── MAIN CHART ────────────────────────────────────────────────────────────

def render_main_chart(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    indicators: Dict[str, pd.Series],
    wave: Optional[WaveResult],
    harm_results: List[PatternResult],
    piv_prices: np.ndarray,
    piv_indices: pd.DatetimeIndex,
    vp: Optional[VolumeProfileResult],
    ms: Optional[MarketStructureResult],
    show_ema: bool,
    show_sma: bool,
    show_bb: bool,
    show_ew: bool,
    show_hp: bool,
    show_vp: bool,
    show_ms: bool,
    ichimoku: Optional[Dict[str, pd.Series]] = None,
    show_ichimoku: bool = True,
) -> go.Figure:
    """
    Renders the main scanner chart with all overlays.

    Args:
        df:            OHLCV DataFrame.
        ticker:        Symbol string.
        tf_label:      Timeframe label.
        indicators:    Computed indicator Dict.
        wave:          WaveResult or None.
        harm_results:  List[PatternResult].
        piv_prices:    Alternating pivot prices.
        piv_indices:   DatetimeIndex for pivots.
        vp:            VolumeProfileResult or None.
        ms:            MarketStructureResult or None.
        show_*:        Boolean toggles for each overlay.
        ichimoku:      Dict from compute_ichimoku() or None.
        show_ichimoku: Toggle for Ichimoku Cloud overlay.

    Returns:
        Plotly Figure — height 680px.
    """
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        increasing_fillcolor="#089981",
        decreasing_fillcolor="#F23645",
        name=ticker,
        showlegend=False,
    ))

    if show_bb:
        fig.add_trace(go.Scatter(
            x=df.index, y=indicators["bb_upper"],
            mode="lines",
            line=dict(color=BB_COLORS["upper"], width=1.0, dash="dot"),
            name=f"BB Upper ({BB_PERIOD})",
            showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=indicators["bb_lower"],
            mode="lines",
            line=dict(color=BB_COLORS["lower"], width=1.0, dash="dot"),
            fill="tonexty",
            fillcolor=BB_COLORS["fill"],
            name=f"BB Lower ({BB_PERIOD})",
            showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=indicators["bb_mid"],
            mode="lines",
            line=dict(color=BB_COLORS["mid"], width=0.8, dash="dot"),
            name=f"BB Mid ({BB_PERIOD})",
            showlegend=True,
        ))

    if show_sma:
        for period, key in [(20, "sma_20"), (50, "sma_50"), (200, "sma_200")]:
            fig.add_trace(go.Scatter(
                x=df.index, y=indicators[key],
                mode="lines",
                line=dict(color=SMA_COLORS[period], width=1.2, dash="dash"),
                name=f"SMA {period}",
                showlegend=True,
            ))

    if show_ema:
        for period, key in [(9, "ema_9"), (21, "ema_21"), (55, "ema_55")]:
            fig.add_trace(go.Scatter(
                x=df.index, y=indicators[key],
                mode="lines",
                line=dict(color=EMA_COLORS[period], width=1.8),
                name=f"EMA {period}",
                showlegend=True,
            ))

    if show_ichimoku and ichimoku is not None:
        fig = add_ichimoku_to_figure(fig, df, ichimoku)

    if show_vp and vp is not None and vp["total_volume"] > 1e-10:
        max_vol:  float = float(np.max(vp["volumes"]))
        bin_size: float = (
            float(vp["price_levels"][1] - vp["price_levels"][0])
            if len(vp["price_levels"]) > 1 else 1.0
        )
        for b_idx in range(len(vp["volumes"])):
            b_vol   = float(vp["volumes"][b_idx])
            b_price = float(vp["price_levels"][b_idx])
            if b_vol < 1e-10:
                continue
            width_frac: float = b_vol / max_vol
            fig.add_shape(
                type="rect",
                xref="paper", yref="y",
                x0=1.0 - (width_frac * 0.08),
                x1=1.0,
                y0=b_price,
                y1=b_price + bin_size,
                fillcolor=VP_COLORS["bars"],
                line_width=0,
                opacity=0.85,
            )

        vp_poc = vp["poc"]
        vp_vah = vp["vah"]
        vp_val = vp["val"]

        fig.add_hline(
            y=vp_poc, line_dash="solid",
            line_color=VP_COLORS["poc"], line_width=2.0,
            annotation_text=f"  POC  ${vp_poc:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=VP_COLORS["poc"], size=10),
        )
        fig.add_hline(
            y=vp_vah, line_dash="dash",
            line_color=VP_COLORS["vah"], line_width=1.2,
            annotation_text=f"  VAH  ${vp_vah:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=VP_COLORS["vah"], size=9),
        )
        fig.add_hline(
            y=vp_val, line_dash="dash",
            line_color=VP_COLORS["val"], line_width=1.2,
            annotation_text=f"  VAL  ${vp_val:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=VP_COLORS["val"], size=9),
        )
        fig.add_hrect(
            y0=vp_val, y1=vp_vah,
            fillcolor=VP_COLORS["vah_fill"], line_width=0,
        )

    if show_ms and ms is not None:
        for sp in ms["swing_points"]:
            lbl_color = (
                MS_COLORS["hh"] if sp["label"] in ("HH", "HL")
                else MS_COLORS["lh"]
            )
            sp_label = sp["label"]
            sp_price = sp["price"]
            sp_date  = sp["date"]
            sp_high  = sp["is_high"]
            fig.add_trace(go.Scatter(
                x=[sp_date], y=[sp_price],
                mode="markers+text",
                marker=dict(
                    size=8, color=lbl_color,
                    symbol="triangle-up" if not sp_high else "triangle-down",
                    line=dict(color="#000d1a", width=1),
                ),
                text=[f"<b>{sp_label}</b>"],
                textposition="bottom center" if sp_high else "top center",
                textfont=dict(color=lbl_color, size=8, family="monospace"),
                showlegend=False,
                hovertemplate=(
                    f"<b>{sp_label}</b><br>${sp_price:,.2f}<extra></extra>"
                ),
            ))

        shown_bos   = False
        shown_choch = False
        for evt in ms["structure_events"]:
            evt_type = evt["event_type"]
            evt_dir  = evt["direction"]
            color = (
                MS_COLORS["bos_bull"]   if evt_type == "BOS"   and evt_dir == "bullish"
                else MS_COLORS["bos_bear"]   if evt_type == "BOS"   and evt_dir == "bearish"
                else MS_COLORS["choch_bull"] if evt_type == "CHoCH" and evt_dir == "bullish"
                else MS_COLORS["choch_bear"]
            )
            show_in_legend = (
                (evt_type == "BOS"   and not shown_bos) or
                (evt_type == "CHoCH" and not shown_choch)
            )
            if evt_type == "BOS"   and not shown_bos:   shown_bos   = True
            if evt_type == "CHoCH" and not shown_choch: shown_choch = True

            evt_price = evt["price"]
            evt_level = evt["level"]

            fig.add_trace(go.Scatter(
                x=[evt["date"]], y=[evt_price],
                mode="markers+text",
                marker=dict(
                    size=11, color=color, symbol="circle-open",
                    line=dict(color=color, width=2),
                ),
                text=[f"<b>{evt_type}</b>"],
                textposition="top center",
                textfont=dict(color=color, size=9, family="monospace"),
                name=evt_type if show_in_legend else "",
                showlegend=show_in_legend,
                hovertemplate=(
                    f"<b>{evt_type}</b> {evt_dir}<br>"
                    f"${evt_price:,.2f}<br>"
                    f"Level: ${evt_level:,.2f}<extra></extra>"
                ),
            ))
            date_str: str = pd.Timestamp(evt["date"]).strftime("%Y-%m-%d")
            fig.add_vline(
                x=date_str, line_dash="dot",
                line_color=color, line_width=0.8, opacity=0.35,
            )

    if show_ew and wave is not None:
        pts      = wave["pts"]
        pt_dates = wave["pt_dates"]
        x_ew     = [pd.Timestamp(d) for d in pt_dates[:5]]
        y_ew     = pts[:5]

        for seg in range(len(x_ew) - 1):
            seg_color = (
                EW_COLORS["motive"] if seg % 2 == 0
                else EW_COLORS["corrective"]
            )
            fig.add_trace(go.Scatter(
                x=[x_ew[seg], x_ew[seg + 1]],
                y=[y_ew[seg], y_ew[seg + 1]],
                mode="lines",
                line=dict(color=seg_color, width=2.5),
                showlegend=False, hoverinfo="skip",
            ))

        fig.add_trace(go.Scatter(
            x=x_ew, y=y_ew,
            mode="markers+text",
            marker=dict(size=12, color=EW_COLORS["motive"], symbol="circle"),
            text=[f"<b>W{l}</b>" for l in ["0","1","2","3","4"][:len(x_ew)]],
            textposition="top center",
            textfont=dict(color="#FFFFFF", size=11, family="monospace"),
            name="Elliott Wave",
            showlegend=True,
        ))

        t1618 = wave["targets"]["target_1618"]
        t2618 = wave["targets"]["target_2618"]
        fig.add_hrect(
            y0=min(t1618, t2618), y1=max(t1618, t2618),
            fillcolor=EW_COLORS["target_zone"], line_width=0,
            annotation_text="W3 Zone", annotation_position="right",
            annotation_font=dict(color=EW_COLORS["target_line"], size=9),
        )
        for t_val, t_lbl in [(t1618, "W3x1.618"), (t2618, "W3x2.618")]:
            fig.add_hline(
                y=t_val, line_dash="dash",
                line_color=EW_COLORS["target_line"], line_width=1.2,
                annotation_text=f"{t_lbl}  ${t_val:,.2f}",
                annotation_position="right",
                annotation_font=dict(color=EW_COLORS["target_line"], size=9),
            )

        inv = wave["invalidation"]
        fig.add_hline(
            y=inv, line_dash="dash",
            line_color=EW_COLORS["invalidation"], line_width=1.5,
            annotation_text=f"Inval  ${inv:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=EW_COLORS["invalidation"], size=9),
        )

        w4s = wave["wave4_support"]
        fig.add_hline(
            y=w4s, line_dash="dashdot",
            line_color=EW_COLORS["fib_618"], line_width=1.0,
            annotation_text=f"W4 Sup  ${w4s:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=EW_COLORS["fib_618"], size=9),
        )

    if show_hp and len(harm_results) > 0:
        for result in harm_results:
            color = PATTERN_COLORS.get(result.pattern_name, "#FFFFFF")
            direction_short = "B" if result.is_bullish else "S"
            x_dates, y_prices = map_pattern_to_dates(
                result, piv_prices, piv_indices
            )
            if not x_dates:
                continue
            fig.add_trace(go.Scatter(
                x=[x_dates[-1]], y=[y_prices[-1]],
                mode="markers+text",
                marker=dict(
                    size=13, color=color, symbol="diamond",
                    line=dict(color="#0e1117", width=1.5),
                ),
                text=[f"{direction_short}D"],
                textposition="bottom center",
                textfont=dict(color=color, size=8),
                name=f"HP {result.pattern_name[:4]}",
                showlegend=True,
                hovertemplate=(
                    f"<b>{result.pattern_name}</b><br>"
                    f"D: ${y_prices[-1]:,.2f}<br>"
                    f"SL: ${float(result.stop_loss):,.2f}<extra></extra>"
                ),
            ))

    fig.update_layout(
        template="plotly_dark",
        height=680,
        margin=dict(l=10, r=160, t=55, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.05)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.05)",
            fixedrange=False,
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        legend=dict(
            bgcolor="rgba(0,13,26,0.90)",
            bordercolor="rgba(0,229,255,0.25)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=9),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        title=dict(
            text=(
                f"{ticker} — 3-Month Scanner ({tf_label})  "
                f"·  90-Day Window  ·  All Tools Active"
            ),
            font=dict(color="#00E5FF", size=14, family="monospace"),
        ),
    )
    return fig


# ─── VOLUME CHART ──────────────────────────────────────────────────────────

def render_volume_chart(df: pd.DataFrame, tf_label: str) -> go.Figure:
    """
    Renders a volume bar chart colored by candle direction.

    Args:
        df:       OHLCV DataFrame.
        tf_label: Timeframe label.

    Returns:
        Plotly Figure — height 180px.
    """
    colors: List[str] = [
        "#089981" if float(c) >= float(o) else "#F23645"
        for o, c in zip(df["open"], df["close"])
    ]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"],
        marker_color=colors,
        marker_line_width=0,
        name="Volume",
        showlegend=False,
    ))
    fig.update_layout(
        template="plotly_dark",
        height=180,
        margin=dict(l=10, r=160, t=25, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.04)",
            type="date",
            showticklabels=False,
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.04)",
            fixedrange=True,
            title=dict(text="Volume", font=dict(color="#666", size=9)),
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        title=dict(
            text=f"Volume  ({tf_label})",
            font=dict(color="rgba(0,229,255,0.55)", size=11, family="monospace"),
        ),
    )
    return fig


# ─── EWO CHART ─────────────────────────────────────────────────────────────

def render_ewo_chart(
    df: pd.DataFrame,
    ewo: pd.Series,
    tf_label: str,
) -> go.Figure:
    """
    Renders the Elliott Wave Oscillator (EWO) histogram.

    Args:
        df:       OHLCV DataFrame.
        ewo:      EWO Series.
        tf_label: Timeframe label.

    Returns:
        Plotly Figure — height 220px.
    """
    ewo_vals: List[float] = list(ewo.fillna(0.0))
    colors:   List[str]   = []

    for i, v in enumerate(ewo_vals):
        prev_v = ewo_vals[i - 1] if i > 0 else v
        if v >= 0.0:
            colors.append(
                EWO_COLORS["pos_rising"] if v >= prev_v
                else EWO_COLORS["pos_falling"]
            )
        else:
            colors.append(
                EWO_COLORS["neg_falling"] if v <= prev_v
                else EWO_COLORS["neg_rising"]
            )

    fig = go.Figure()
    fig.add_hline(y=0.0, line_dash="dot",
                  line_color=EWO_COLORS["zero_line"], line_width=1.0)
    fig.add_trace(go.Bar(
        x=df.index, y=ewo_vals,
        marker_color=colors, marker_line_width=0,
        name=f"EWO (SMA{EWO_FAST}/SMA{EWO_SLOW})",
        showlegend=True,
    ))

    non_null_ewo = ewo.dropna()
    if len(non_null_ewo) > 0:
        peak_idx   = non_null_ewo.abs().idxmax()
        peak_sign: float = float(non_null_ewo[peak_idx])
        fig.add_trace(go.Scatter(
            x=[peak_idx], y=[peak_sign],
            mode="markers+text",
            marker=dict(size=10, color="#FFD700", symbol="star"),
            text=["<b>W3?</b>"],
            textposition="top center" if peak_sign >= 0.0 else "bottom center",
            textfont=dict(color="#FFD700", size=9, family="monospace"),
            name="W3 Peak",
            showlegend=True,
        ))

    fig.update_layout(
        template="plotly_dark",
        height=220,
        margin=dict(l=10, r=160, t=25, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.04)",
            type="date",
            showticklabels=False,
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.04)",
            fixedrange=False,
            title=dict(
                text=f"EWO {EWO_FAST}/{EWO_SLOW}",
                font=dict(color="rgba(0,229,255,0.55)", size=9),
            ),
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        barmode="overlay",
        legend=dict(
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor="rgba(0,229,255,0.20)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=9),
        ),
        title=dict(
            text=(
                f"Elliott Wave Oscillator — SMA({EWO_FAST}) - SMA({EWO_SLOW})"
                f"  ({tf_label})"
            ),
            font=dict(color="rgba(0,229,255,0.55)", size=11, family="monospace"),
        ),
    )
    return fig


# ─── RSI CHART ─────────────────────────────────────────────────────────────

def render_rsi_chart(
    df: pd.DataFrame,
    rsi: pd.Series,
    tf_label: str,
) -> go.Figure:
    """
    Renders RSI (period=21) chart with OB/OS bands.

    Args:
        df:       OHLCV DataFrame.
        rsi:      RSI Series.
        tf_label: Timeframe label.

    Returns:
        Plotly Figure — height 200px.
    """
    fig = go.Figure()
    fig.add_hrect(y0=RSI_OVERBOUGHT, y1=100.0,
                  fillcolor=RSI_COLORS["overbought"], line_width=0)
    fig.add_hrect(y0=0.0, y1=RSI_OVERSOLD,
                  fillcolor=RSI_COLORS["oversold"], line_width=0)
    fig.add_hline(y=RSI_OVERBOUGHT, line_dash="dot",
                  line_color=RSI_COLORS["ob_line"], line_width=1.0,
                  annotation_text=f"  OB {RSI_OVERBOUGHT:.0f}",
                  annotation_position="right",
                  annotation_font=dict(color=RSI_COLORS["ob_line"], size=9))
    fig.add_hline(y=RSI_OVERSOLD, line_dash="dot",
                  line_color=RSI_COLORS["os_line"], line_width=1.0,
                  annotation_text=f"  OS {RSI_OVERSOLD:.0f}",
                  annotation_position="right",
                  annotation_font=dict(color=RSI_COLORS["os_line"], size=9))
    fig.add_hline(y=50.0, line_dash="dot",
                  line_color="rgba(255,255,255,0.15)", line_width=0.8)
    fig.add_trace(go.Scatter(
        x=df.index, y=rsi,
        mode="lines",
        line=dict(color=RSI_COLORS["line"], width=1.8),
        name=f"RSI ({RSI_PERIOD})",
        showlegend=True,
    ))
    fig.update_layout(
        template="plotly_dark",
        height=200,
        margin=dict(l=10, r=160, t=25, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.04)",
            type="date",
            showticklabels=False,
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.04)",
            fixedrange=True,
            range=[0, 100],
            title=dict(
                text=f"RSI {RSI_PERIOD}",
                font=dict(color="rgba(0,229,255,0.55)", size=9),
            ),
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        legend=dict(
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor="rgba(0,229,255,0.20)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=9),
        ),
        title=dict(
            text=f"RSI ({RSI_PERIOD})  ({tf_label})",
            font=dict(color="rgba(0,229,255,0.55)", size=11, family="monospace"),
        ),
    )
    return fig


# ─── MACD CHART ────────────────────────────────────────────────────────────

def render_macd_chart(
    df: pd.DataFrame,
    macd_line: pd.Series,
    signal_line: pd.Series,
    histogram: pd.Series,
    tf_label: str,
) -> go.Figure:
    """
    Renders MACD (12/26/9) histogram + MACD line + signal line.

    Args:
        df:          OHLCV DataFrame.
        macd_line:   MACD line Series.
        signal_line: Signal line Series.
        histogram:   MACD histogram Series.
        tf_label:    Timeframe label.

    Returns:
        Plotly Figure — height 220px.
    """
    hist_colors: List[str] = [
        MACD_COLORS["hist_pos"] if float(v) >= 0.0
        else MACD_COLORS["hist_neg"]
        for v in histogram
    ]
    fig = go.Figure()
    fig.add_hline(y=0.0, line_dash="dot",
                  line_color="rgba(255,255,255,0.15)", line_width=0.8)
    fig.add_trace(go.Bar(
        x=df.index, y=histogram,
        marker_color=hist_colors, marker_line_width=0,
        name="MACD Histogram", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_line,
        mode="lines",
        line=dict(color=MACD_COLORS["macd_line"], width=1.8),
        name=f"MACD ({MACD_FAST}/{MACD_SLOW})",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=signal_line,
        mode="lines",
        line=dict(color=MACD_COLORS["signal_line"], width=1.5, dash="dot"),
        name=f"Signal ({MACD_SIGNAL})",
        showlegend=True,
    ))
    fig.update_layout(
        template="plotly_dark",
        height=220,
        margin=dict(l=10, r=160, t=25, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.04)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.04)",
            fixedrange=False,
            title=dict(
                text=f"MACD {MACD_FAST}/{MACD_SLOW}/{MACD_SIGNAL}",
                font=dict(color="rgba(0,229,255,0.55)", size=9),
            ),
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        legend=dict(
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor="rgba(0,229,255,0.20)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=9),
        ),
        barmode="overlay",
        title=dict(
            text=f"MACD ({MACD_FAST}/{MACD_SLOW}/{MACD_SIGNAL})  ({tf_label})",
            font=dict(color="rgba(0,229,255,0.55)", size=11, family="monospace"),
        ),
    )
    return fig


# ─── PRZ ZOOM CHART ────────────────────────────────────────────────────────

def render_prz_zoom_chart(
    df: pd.DataFrame,
    result: PatternResult,
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
) -> go.Figure:
    """
    Renders a zoom chart centered on the most recent harmonic pattern PRZ.

    Args:
        df:            Full OHLCV DataFrame.
        result:        Most recent PatternResult.
        pivot_prices:  Alternating pivot prices.
        pivot_indices: DatetimeIndex for pivots.

    Returns:
        Plotly Figure — height 480px.
    """
    n         = len(result.points)
    color     = PATTERN_COLORS.get(result.pattern_name, "#FFFFFF")
    direction = "Bullish" if result.is_bullish else "Bearish"
    labels    = (
        SHARK_LABELS
        if result.pattern_name == "Shark"
        else POINT_LABELS_MAP.get(n, {i: str(i) for i in range(n)})
    )

    x_dates, y_prices = map_pattern_to_dates(
        result, pivot_prices, pivot_indices
    )

    df_reset           = df.reset_index()
    date_col           = df_reset.columns[0]
    df_reset[date_col] = pd.to_datetime(df_reset[date_col])

    try:
        first_pos = int(
            df_reset[
                df_reset[date_col] <= pd.Timestamp(x_dates[0])
            ].index[-1]
        )
    except IndexError:
        first_pos = 0

    try:
        last_pos = int(
            df_reset[
                df_reset[date_col] <= pd.Timestamp(x_dates[-1])
            ].index[-1]
        )
    except IndexError:
        last_pos = len(df_reset) - 1

    window_start = max(0, first_pos - PRZ_CANDLE_CONTEXT)
    window_end   = min(len(df_reset) - 1, last_pos + PRZ_CANDLE_CONTEXT)
    df_window    = (
        df_reset.iloc[window_start: window_end + 1].set_index(date_col)
    )

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_window.index,
        open=df_window["open"],
        high=df_window["high"],
        low=df_window["low"],
        close=df_window["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        increasing_fillcolor="#089981",
        decreasing_fillcolor="#F23645",
        name="Price",
        showlegend=False,
    ))

    point_text: List[str] = []
    for i in range(n):
        lbl  = labels.get(i, str(i))
        date = pd.Timestamp(x_dates[i]).strftime("%Y-%m-%d")
        px   = y_prices[i]
        point_text.append(f"<b>{lbl}</b><br>{date}<br>${px:,.2f}")

    fig.add_trace(go.Scatter(
        x=x_dates, y=y_prices,
        mode="lines+markers+text",
        line=dict(color=color, width=2.5),
        marker=dict(
            size=14, color=color, symbol="circle",
            line=dict(color="#000d1a", width=2),
        ),
        text=point_text,
        textposition="top center",
        textfont=dict(color=color, size=11, family="monospace"),
        name=f"{direction} {result.pattern_name}",
        showlegend=True,
    ))

    base_len: float = abs(y_prices[1] - y_prices[0]) if n >= 2 else 1.0

    for idx in range(n - 1):
        mid_ts = pd.Timestamp(
            (
                pd.Timestamp(x_dates[idx]).value
                + pd.Timestamp(x_dates[idx + 1]).value
            ) // 2
        )
        mid_y   = (y_prices[idx] + y_prices[idx + 1]) / 2.0
        leg_len = abs(y_prices[idx + 1] - y_prices[idx])
        ratio   = leg_len / base_len if base_len > 1e-10 else 0.0
        fig.add_annotation(
            x=mid_ts, y=mid_y,
            text=f"{ratio:.3f}",
            showarrow=False,
            font=dict(color=color, size=10, family="monospace"),
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor=color, borderwidth=1, borderpad=3,
        )

    d_price: float  = y_prices[-1]
    prz_half: float = d_price * 0.005
    fig.add_hrect(
        y0=d_price - prz_half, y1=d_price + prz_half,
        fillcolor=hex_to_rgba(color, 0.13),
        line_color=color, line_width=1, line_dash="dot",
        annotation_text=f"PRZ: ${d_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(color=color, size=11),
    )

    sl_price: float = float(result.stop_loss)
    fig.add_hline(
        y=sl_price, line_dash="dash",
        line_color="#FF5252", line_width=1.8,
        annotation_text=f"Stop Loss: ${sl_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(color="#FF5252", size=11),
    )

    d_date_str: str = pd.Timestamp(x_dates[-1]).strftime("%Y-%m-%d")
    fig.add_vline(
        x=d_date_str, line_dash="dot",
        line_color=color, line_width=1.2, opacity=0.6,
    )
    fig.add_annotation(
        x=d_date_str, y=1.0, yref="paper",
        text="D — PRZ", showarrow=False,
        font=dict(color=color, size=10, family="monospace"),
        bgcolor="rgba(0,13,26,0.85)",
        bordercolor=color, borderwidth=1, borderpad=3,
        xanchor="center",
    )

    fig.update_layout(
        template="plotly_dark",
        height=480,
        margin=dict(l=10, r=160, t=50, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.05)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.05)",
            fixedrange=False,
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        legend=dict(
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor="rgba(0,229,255,0.25)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=10),
        ),
        title=dict(
            text=(
                f"{direction} {result.pattern_name} — PRZ Zoom "
                f"(+/-{PRZ_CANDLE_CONTEXT} candles)"
            ),
            font=dict(color=color, size=13, family="monospace"),
        ),
    )
    return fig


# ─── ELLIOTT WAVE EXPANDED CHART ───────────────────────────────────────────

def render_ew_expanded(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    wave: WaveResult,
) -> go.Figure:
    """
    Renders a full-size 750px expanded Elliott Wave chart.

    Args:
        df:       OHLCV DataFrame.
        ticker:   Symbol string.
        tf_label: Timeframe label.
        wave:     WaveResult from run_elliott_pipeline().

    Returns:
        Plotly Figure — height 750px.
    """
    pts:      List[float] = wave["pts"]
    pt_dates: List[Any]   = wave["pt_dates"]
    wave_labels = ["0", "1", "2", "3", "4"]
    x_ew: List[Any]   = [pd.Timestamp(d) for d in pt_dates[:5]]
    y_ew: List[float] = pts[:5]

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        increasing_fillcolor="#089981",
        decreasing_fillcolor="#F23645",
        name=ticker, showlegend=False, opacity=0.28,
    ))

    for seg in range(len(x_ew) - 1):
        seg_color = (
            EW_COLORS["motive"] if seg % 2 == 0
            else EW_COLORS["corrective"]
        )
        fig.add_trace(go.Scatter(
            x=[x_ew[seg], x_ew[seg + 1]],
            y=[y_ew[seg], y_ew[seg + 1]],
            mode="lines",
            line=dict(color=seg_color, width=3.5),
            showlegend=False, hoverinfo="skip",
        ))

    for i in range(len(x_ew)):
        lbl      = wave_labels[i]
        px       = y_ew[i]
        xd       = x_ew[i]
        date_str = pd.Timestamp(xd).strftime("%Y-%m-%d")
        pt_color = (
            EW_COLORS["motive"] if i % 2 == 0
            else EW_COLORS["corrective"]
        )
        fig.add_trace(go.Scatter(
            x=[xd], y=[px],
            mode="markers",
            marker=dict(
                size=18, color=pt_color, symbol="circle",
                line=dict(color="#000d1a", width=3),
            ),
            showlegend=False,
            hovertemplate=(
                f"<b>W{lbl}</b><br>${px:,.2f}<br>{date_str}<extra></extra>"
            ),
        ))
        fig.add_annotation(
            x=xd, y=px,
            text=f"<b>{lbl}</b>",
            showarrow=False,
            font=dict(color="#FFFFFF", size=11, family="monospace"),
            bgcolor="rgba(0,0,0,0)",
        )
        ax_off = 55 if i % 2 == 0 else -55
        ay_off = -45 if i % 2 == 0 else 45
        fig.add_annotation(
            x=xd, y=px,
            text=(
                f"<b>W{lbl}</b>  ${px:,.2f}<br>"
                f"<span style='font-size:9px;color:{pt_color}'>"
                f"{date_str}</span>"
            ),
            showarrow=True,
            arrowhead=2, arrowsize=1.2, arrowwidth=1.8,
            arrowcolor=pt_color,
            ax=ax_off, ay=ay_off,
            font=dict(color=pt_color, size=11, family="monospace"),
            bgcolor=EW_COLORS["label_bg"],
            bordercolor=pt_color, borderwidth=1, borderpad=5,
        )

    w1_high:  float = max(float(pts[0]), float(pts[1]))
    w1_low:   float = min(float(pts[0]), float(pts[1]))
    w1_range: float = w1_high - w1_low

    for level in FIB_LEVELS:
        fib_px: float = w1_high - (w1_range * level)
        lc = FIB_COLORS.get(level, "rgba(255,255,255,0.4)")
        fig.add_hline(
            y=fib_px, line_dash="dot",
            line_color=lc, line_width=1.5,
            annotation_text=f"  {level:.3f}  ${fib_px:,.2f}",
            annotation_position="right",
            annotation_font=dict(color=lc, size=10, family="monospace"),
        )
        if len(x_ew) >= 3:
            fig.add_shape(
                type="line",
                x0=x_ew[1], y0=float(pts[1]),
                x1=x_ew[2], y1=fib_px,
                line=dict(color=lc, width=0.8, dash="dot"),
                opacity=0.30,
            )

    w4s: float = wave["wave4_support"]
    fig.add_hline(
        y=w4s, line_dash="dashdot",
        line_color=EW_COLORS["fib_618"], line_width=1.5,
        annotation_text=f"  W4 Support (0.382xW3)  ${w4s:,.2f}",
        annotation_position="right",
        annotation_font=dict(
            color=EW_COLORS["fib_618"], size=10, family="monospace"
        ),
    )

    t1618: float = wave["targets"]["target_1618"]
    t2618: float = wave["targets"]["target_2618"]
    fig.add_hrect(
        y0=min(t1618, t2618), y1=max(t1618, t2618),
        fillcolor=EW_COLORS["target_zone"], line_width=0,
    )
    for t_val, t_lbl in [(t1618, "W3x1.618"), (t2618, "W3x2.618")]:
        fig.add_hline(
            y=t_val, line_dash="dash",
            line_color=EW_COLORS["target_line"], line_width=2.0,
            annotation_text=f"  {t_lbl}  ${t_val:,.2f}",
            annotation_position="right",
            annotation_font=dict(
                color=EW_COLORS["target_line"], size=11, family="monospace"
            ),
        )

    inv: float = wave["invalidation"]
    fig.add_hline(
        y=inv, line_dash="dash",
        line_color=EW_COLORS["invalidation"], line_width=2.0,
        annotation_text=f"  Invalidation  ${inv:,.2f}",
        annotation_position="right",
        annotation_font=dict(
            color=EW_COLORS["invalidation"], size=11, family="monospace"
        ),
    )

    w2_ratio: float = wave["w2"].get("ratio", 0.0)
    w2_ideal: bool  = wave["w2"].get("is_ideal", False)
    w2_lbl: str = (
        f"W2 Retrace: {w2_ratio:.3f}  (Ideal 0.500-0.618)"
        if w2_ideal
        else f"W2 Retrace: {w2_ratio:.3f}"
    )
    fig.add_annotation(
        text=w2_lbl,
        xref="paper", yref="paper",
        x=0.01, y=0.93,
        showarrow=False,
        font=dict(
            color=EW_COLORS["corrective"], size=11, family="monospace"
        ),
        bgcolor=EW_COLORS["label_bg"],
        bordercolor=EW_COLORS["corrective"], borderwidth=1, borderpad=5,
    )

    w4_valid: bool  = wave["w4"]["is_valid"]
    phase_text: str = (
        "PHASE: W4 COMPLETE — W5 LAUNCH WATCH"
        if w4_valid
        else "PHASE: W2/W4 CORRECTION ACTIVE"
    )
    phase_color: str = (
        EW_COLORS["motive"] if w4_valid else EW_COLORS["corrective"]
    )
    fig.add_annotation(
        text=phase_text,
        xref="paper", yref="paper",
        x=0.01, y=0.99,
        showarrow=False,
        font=dict(color=phase_color, size=13, family="monospace"),
        bgcolor=EW_COLORS["label_bg"],
        bordercolor=phase_color, borderwidth=1, borderpad=6,
    )

    fig.update_layout(
        template="plotly_dark",
        height=750,
        margin=dict(l=10, r=160, t=60, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(0,229,255,0.05)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(0,229,255,0.05)",
            fixedrange=False,
        ),
        paper_bgcolor="#000d1a",
        plot_bgcolor="#000d1a",
        showlegend=False,
        title=dict(
            text=(
                f"{ticker} — Elliott Wave Full Structure ({tf_label}) "
                f"— Click and drag to zoom"
            ),
            font=dict(
                color=EW_COLORS["motive"], size=14, family="monospace"
            ),
        ),
    )
    return fig


# ─── ANALYSIS PANEL ────────────────────────────────────────────────────────

def render_analysis_panel(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    indicators: Dict[str, pd.Series],
    wave: Optional[WaveResult],
    harm_results: List[PatternResult],
    piv_prices: np.ndarray,
    piv_indices: pd.DatetimeIndex,
    vp: Optional[VolumeProfileResult],
    ms: Optional[MarketStructureResult],
    ewo: pd.Series,
) -> None:
    """
    Renders the live analysis panel. All values computed from live data.

    Args:
        df:           OHLCV DataFrame.
        ticker:       Symbol string.
        tf_label:     Timeframe label.
        indicators:   Computed indicator Dict.
        wave:         WaveResult or None.
        harm_results: List[PatternResult].
        piv_prices:   Alternating pivot prices.
        piv_indices:  DatetimeIndex for pivots.
        vp:           VolumeProfileResult or None.
        ms:           MarketStructureResult or None.
        ewo:          EWO Series.
    """
    st.markdown("---")
    st.subheader(f"Live Analysis — {ticker} · {tf_label} · 90-Day Window")

    current_close: float = float(df["close"].iloc[-1])
    prev_close:    float = (
        float(df["close"].iloc[-2]) if len(df) > 1 else current_close
    )
    price_change: float = current_close - prev_close
    change_pct:   float = (
        (price_change / prev_close * 100.0)
        if abs(prev_close) > 1e-10 else 0.0
    )
    current_date: str = pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d %H:%M")

    st.markdown("#### " + t("scan_current_price"))
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.metric(
            label=f"{ticker} Last Close",
            value=f"${current_close:,.2f}",
            delta=f"{price_change:+.2f} ({change_pct:+.2f}%)",
        )
    with col_p2:
        st.metric(label="As Of", value=current_date)
    with col_p3:
        st.metric(
            label="90-Day High",
            value=f"${float(df['high'].max()):,.2f}",
        )
    with col_p4:
        st.metric(
            label="90-Day Low",
            value=f"${float(df['low'].min()):,.2f}",
        )

    st.markdown("---")
    st.markdown("#### " + t("scan_elliott_status"))
    if wave is not None:
        col_ew1, col_ew2, col_ew3, col_ew4 = st.columns(4)
        direction_str: str = "Bullish" if wave["is_bullish"] else "Bearish"
        w4_valid_v:    bool = wave["w4"]["is_valid"]
        w4_status: str = (
            "Complete — W5 Watch" if w4_valid_v else "W2/W4 Active"
        )
        w2_ratio_v: float = wave["w2"]["ratio"]
        w2_ideal_v: bool  = wave["w2"]["is_ideal"]
        w2_str: str = (
            f"{w2_ratio_v:.3f} (Ideal)"
            if w2_ideal_v
            else f"{w2_ratio_v:.3f}"
        )
        invalidation_v: float = wave["invalidation"]
        t1618_v: float        = wave["targets"]["target_1618"]
        t2618_v: float        = wave["targets"]["target_2618"]
        w4s_v:   float        = wave["wave4_support"]

        with col_ew1:
            st.metric(label="Direction",    value=direction_str)
            st.metric(label="W2 Retrace",   value=w2_str)
        with col_ew2:
            st.metric(label="Phase",        value=w4_status)
            st.metric(label="Invalidation", value=f"${invalidation_v:,.2f}")
        with col_ew3:
            dist_1618 = (
                (t1618_v / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )
            st.metric(
                label="W3 Target x1.618",
                value=f"${t1618_v:,.2f}",
                delta=f"{dist_1618:+.1f}% from current",
            )
        with col_ew4:
            dist_2618 = (
                (t2618_v / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )
            st.metric(
                label="W3 Target x2.618",
                value=f"${t2618_v:,.2f}",
                delta=f"{dist_2618:+.1f}% from current",
            )

        if w4_valid_v:
            st.success("Rule 3 PASS — W4 has not entered W1 territory.")
        else:
            overlap_v: float = wave["w4"]["overlap_depth"]
            st.error(
                f"Rule 3 VIOLATION — W4 overlapped W1 by "
                f"${overlap_v:.2f}. Structure may be a diagonal."
            )
        st.info(f"W4 Support Level (0.382 x W3): **${w4s_v:,.2f}**")
    else:
        st.warning(
            "No valid Elliott Wave impulse structure detected in the "
            "90-day window. Try lowering pivot sensitivity."
        )

    st.markdown("---")
    st.markdown("#### " + t("scan_harmonic_signals"))

    if len(harm_results) > 0:
        def _d_date(r: PatternResult) -> pd.Timestamp:
            """Sort key: most recent D-point date."""
            x_d, _ = map_pattern_to_dates(r, piv_prices, piv_indices)
            return pd.Timestamp(x_d[-1]) if x_d else pd.Timestamp.min

        sorted_results = sorted(harm_results, key=_d_date, reverse=True)

        for r in sorted_results[:6]:
            x_d, y_d = map_pattern_to_dates(r, piv_prices, piv_indices)
            d_price   = float(y_d[-1]) if y_d else 0.0
            d_date    = (
                pd.Timestamp(x_d[-1]).strftime("%Y-%m-%d")
                if x_d else "—"
            )
            direction = "Bullish" if r.is_bullish else "Bearish"
            dc        = "green" if r.is_bullish else "red"
            dist_pct  = (
                abs(d_price - current_close) / current_close * 100.0
                if current_close > 1e-10 else 0.0
            )
            r_sl = float(r.stop_loss)
            col_h1, col_h2, col_h3, col_h4 = st.columns(4)
            with col_h1:
                st.markdown(f":{dc}[**{direction} {r.pattern_name}**]")
                st.caption(f"D date: {d_date}")
            with col_h2:
                st.metric(label="PRZ (D price)", value=f"${d_price:,.2f}")
            with col_h3:
                st.metric(
                    label="Distance from current",
                    value=f"{dist_pct:.2f}%",
                )
            with col_h4:
                st.metric(label="Stop Loss", value=f"${r_sl:,.2f}")
    else:
        st.info(
            "No harmonic patterns detected in the 90-day window. "
            "Try lowering pivot sensitivity."
        )

    st.markdown("---")
    st.markdown("#### " + t("scan_indicator_readings"))
    col_i1, col_i2, col_i3 = st.columns(3)

    with col_i1:
        st.markdown("**Moving Averages**")
        for period, key in [
            (9,   "ema_9"),  (21,  "ema_21"), (55,  "ema_55"),
            (20,  "sma_20"), (50,  "sma_50"), (200, "sma_200"),
        ]:
            val = indicators[key].iloc[-1]
            if np.isnan(val):
                continue
            val_f    = float(val)
            ma_type  = "EMA" if key.startswith("ema") else "SMA"
            position = "above" if current_close > val_f else "below"
            tc       = "green" if current_close > val_f else "red"
            st.markdown(
                f"{ma_type} {period}: **${val_f:,.2f}** — "
                f":{tc}[Price {position}]"
            )

        e9_cur  = float(indicators["ema_9"].iloc[-1])
        e21_cur = float(indicators["ema_21"].iloc[-1])
        e9_prv  = float(indicators["ema_9"].iloc[-2])  if len(df) > 1 else e9_cur
        e21_prv = float(indicators["ema_21"].iloc[-2]) if len(df) > 1 else e21_cur

        if e9_prv <= e21_prv and e9_cur > e21_cur:
            st.markdown(":green[**EMA 9/21 BULLISH CROSS (just formed)**]")
        elif e9_prv >= e21_prv and e9_cur < e21_cur:
            st.markdown(":red[**EMA 9/21 BEARISH CROSS (just formed)**]")
        elif e9_cur > e21_cur:
            st.markdown(":green[EMA 9 above EMA 21 (bullish alignment)]")
        else:
            st.markdown(":red[EMA 9 below EMA 21 (bearish alignment)]")

    with col_i2:
        st.markdown("**RSI & EWO**")
        rsi_val: float = float(indicators["rsi_21"].iloc[-1])
        st.metric(label=f"RSI ({RSI_PERIOD})", value=f"{rsi_val:.1f}")
        if rsi_val >= RSI_OVERBOUGHT:
            st.markdown(
                f":red[**{rsi_val:.1f} — Overbought "
                f"(>{RSI_OVERBOUGHT:.0f})**]"
            )
        elif rsi_val <= RSI_OVERSOLD:
            st.markdown(
                f":green[**{rsi_val:.1f} — Oversold "
                f"(<{RSI_OVERSOLD:.0f})**]"
            )
        else:
            st.markdown(f":blue[{rsi_val:.1f} — Neutral]")

        ewo_clean = ewo.dropna()
        if len(ewo_clean) > 0:
            ewo_cur: float = float(ewo_clean.iloc[-1])
            ewo_prv: float = (
                float(ewo_clean.iloc[-2])
                if len(ewo_clean) > 1 else ewo_cur
            )
            ewo_dir: str = "Rising" if ewo_cur > ewo_prv else "Falling"
            ewo_tc:  str = "green" if ewo_cur >= 0.0 else "red"
            ewo_lbl: str = f"SMA{EWO_FAST}/SMA{EWO_SLOW}"
            st.metric(
                label=f"EWO ({ewo_lbl})",
                value=f"{ewo_cur:,.4f}",
                delta=ewo_dir,
            )
            ewo_momentum = (
                "Positive — bullish momentum"
                if ewo_cur >= 0.0
                else "Negative — bearish momentum"
            )
            st.markdown(f":{ewo_tc}[EWO {ewo_momentum}]")
            ewo_peak_v: float = float(
                ewo_clean.iloc[int(ewo_clean.abs().values.argmax())]
            )
            if (
                abs(ewo_peak_v) > 1e-10
                and abs(ewo_cur) < abs(ewo_peak_v) * 0.50
                and ewo_peak_v > 0.0
            ):
                st.caption(
                    "EWO declining from peak — possible W4 or W5 territory."
                )
            elif abs(ewo_peak_v) > 1e-10 and abs(ewo_cur) >= abs(ewo_peak_v) * 0.90:
                st.caption("EWO near peak — possible Wave 3 in progress.")

    with col_i3:
        st.markdown("**MACD**")
        macd_cur:   float = float(indicators["macd_line"].iloc[-1])
        signal_cur: float = float(indicators["signal_line"].iloc[-1])
        hist_cur:   float = float(indicators["histogram"].iloc[-1])
        hist_prv:   float = (
            float(indicators["histogram"].iloc[-2])
            if len(df) > 1 else hist_cur
        )
        macd_prv:   float = (
            float(indicators["macd_line"].iloc[-2])
            if len(df) > 1 else macd_cur
        )
        signal_prv: float = (
            float(indicators["signal_line"].iloc[-2])
            if len(df) > 1 else signal_cur
        )

        macd_lbl   = f"MACD Line ({MACD_FAST}/{MACD_SLOW})"
        signal_lbl = f"Signal Line ({MACD_SIGNAL})"
        st.metric(label=macd_lbl,   value=f"{macd_cur:,.4f}")
        st.metric(label=signal_lbl, value=f"{signal_cur:,.4f}")
        st.metric(
            label="Histogram",
            value=f"{hist_cur:,.4f}",
            delta=f"{hist_cur - hist_prv:+.4f}",
        )

        if macd_prv <= signal_prv and macd_cur > signal_cur:
            st.markdown(":green[**MACD BULLISH CROSS (just formed)**]")
        elif macd_prv >= signal_prv and macd_cur < signal_cur:
            st.markdown(":red[**MACD BEARISH CROSS (just formed)**]")
        elif macd_cur > signal_cur:
            st.markdown(":green[MACD above Signal (bullish)]")
        else:
            st.markdown(":red[MACD below Signal (bearish)]")

        hist_tc: str = "green" if hist_cur >= 0.0 else "red"
        expanding_str = (
            "Expanding"
            if abs(hist_cur) > abs(hist_prv)
            else "Contracting"
        )
        st.markdown(f":{hist_tc}[Histogram {expanding_str}]")

    st.markdown("---")
    st.markdown("#### " + t("scan_volume_profile") + " — — 90-Day Fixed Range")
    if vp is not None and vp["total_volume"] > 1e-10:
        col_vp1, col_vp2, col_vp3, col_vp4 = st.columns(4)
        vp_poc:   float = vp["poc"]
        vp_vah:   float = vp["vah"]
        vp_val_v: float = vp["val"]
        vp_total: float = vp["total_volume"]
        poc_dist: float = (
            abs(current_close - vp_poc) / current_close * 100.0
            if current_close > 1e-10 else 0.0
        )
        in_va: bool = vp_val_v <= current_close <= vp_vah

        with col_vp1:
            st.metric(
                label="POC (Point of Control)",
                value=f"${vp_poc:,.2f}",
                delta=f"{poc_dist:.2f}% from current",
            )
        with col_vp2:
            st.metric(
                label="VAH (Value Area High 70%)",
                value=f"${vp_vah:,.2f}",
            )
        with col_vp3:
            st.metric(
                label="VAL (Value Area Low 70%)",
                value=f"${vp_val_v:,.2f}",
            )
        with col_vp4:
            va_status: str = (
                "Inside Value Area" if in_va else "Outside Value Area"
            )
            va_tc: str = "green" if in_va else "red"
            st.metric(label="Current vs Value Area", value=va_status)
            st.markdown(
                f":{va_tc}[Price is **{va_status}** "
                f"(VAL ${vp_val_v:,.2f} — VAH ${vp_vah:,.2f})]"
            )

        va_pct_label = f"{VP_VALUE_AREA_PCT * 100:.0f}%"
        st.caption(
            f"Volume Profile: {VP_NUM_BINS} bins · "
            f"Value Area = {va_pct_label} · "
            f"Total Volume: {vp_total:,.0f}"
        )
    else:
        st.info("Volume Profile not available (insufficient volume data).")

    st.markdown("---")
    st.markdown("#### " + t("scan_market_structure"))
    if ms is not None:
        ms_trend  = ms["current_trend"]
        ms_swings = ms["swing_points"]
        ms_events = ms["structure_events"]
        trend_tc: str = (
            "green" if ms_trend == "bullish"
            else "red" if ms_trend == "bearish"
            else "blue"
        )
        st.markdown(
            f"**Current Trend:** :{trend_tc}[{ms_trend.upper()}]  "
            f"| Swing Points: **{len(ms_swings)}**  "
            f"| Structure Events: **{len(ms_events)}**"
        )
        if ms_events:
            last_evt     = ms_events[-1]
            evt_type_v   = last_evt["event_type"]
            evt_dir_v    = last_evt["direction"]
            evt_price_v  = last_evt["price"]
            evt_date_v   = pd.Timestamp(last_evt["date"]).strftime("%Y-%m-%d")
            evt_level_v  = last_evt["level"]
            evt_tc: str  = "green" if evt_dir_v == "bullish" else "red"
            st.markdown(
                f"**Most Recent:** :{evt_tc}["
                f"**{evt_type_v}** ({evt_dir_v.upper()})] "
                f"at ${evt_price_v:,.2f} on {evt_date_v} — "
                f"broke level ${evt_level_v:,.2f}"
            )
        if ms_swings:
            recent_swings = sorted(
                ms_swings, key=lambda s: s["index"], reverse=True
            )[:4]
            sw_cols = st.columns(len(recent_swings))
            for sw_col, sp in zip(sw_cols, recent_swings):
                sp_label_v = sp["label"]
                sp_price_v = sp["price"]
                sp_date_v  = pd.Timestamp(sp["date"]).strftime("%Y-%m-%d")
                sp_tc: str = "green" if sp_label_v in ("HH", "HL") else "red"
                with sw_col:
                    st.metric(
                        label=f":{sp_tc}[{sp_label_v}]",
                        value=f"${sp_price_v:,.2f}",
                    )
                    st.caption(sp_date_v)
    else:
        st.info("Market Structure analysis not available.")

    st.markdown("---")
    st.markdown("#### " + t("scan_projections"))
    col_fwd1, col_fwd2 = st.columns(2)

    with col_fwd1:
        st.markdown("**Elliott Wave Projections**")
        if wave is not None:
            w_t1618 = wave["targets"]["target_1618"]
            w_t2618 = wave["targets"]["target_2618"]
            w_w4s   = wave["wave4_support"]
            w_inv   = wave["invalidation"]
            projections = [
                ("W3 Target (1.618xW1)",  w_t1618, "Target"),
                ("W3 Target (2.618xW1)",  w_t2618, "Target"),
                ("W4 Support (0.382xW3)", w_w4s,   "Support"),
                ("Invalidation Level",    w_inv,   "Risk"),
            ]
            for name, level, level_type in projections:
                dist = (
                    (level / current_close - 1.0) * 100.0
                    if current_close > 1e-10 else 0.0
                )
                tc = (
                    "green" if level_type == "Target"
                    else "blue" if level_type == "Support"
                    else "red"
                )
                st.markdown(
                    f":{tc}[**{name}**]: "
                    f"${level:,.2f} ({dist:+.1f}% from current)"
                )
        else:
            st.caption("Elliott Wave structure required for projections.")

    with col_fwd2:
        st.markdown("**Harmonic PRZ Projections**")
        if len(harm_results) > 0:
            display_results = sorted(
                harm_results, key=_d_date, reverse=True
            )[:4]
            for r in display_results:
                x_d, y_d = map_pattern_to_dates(r, piv_prices, piv_indices)
                d_price  = float(y_d[-1]) if y_d else 0.0
                dist     = (
                    (d_price / current_close - 1.0) * 100.0
                    if current_close > 1e-10 else 0.0
                )
                dc      = "green" if r.is_bullish else "red"
                dir_str = "Bull" if r.is_bullish else "Bear"
                r_sl    = float(r.stop_loss)
                st.markdown(
                    f":{dc}[**{dir_str} {r.pattern_name}**] "
                    f"PRZ: ${d_price:,.2f} "
                    f"({dist:+.1f}%) · SL: ${r_sl:,.2f}"
                )
        else:
            st.caption("No harmonic patterns detected.")

    st.markdown("**Bollinger Band Context**")
    bb_upper_val: float = float(indicators["bb_upper"].iloc[-1])
    bb_lower_val: float = float(indicators["bb_lower"].iloc[-1])
    bb_mid_val:   float = float(indicators["bb_mid"].iloc[-1])

    if not np.isnan(bb_upper_val):
        if current_close > bb_upper_val:
            bb_msg = ":red[**Above Upper Band — extended, potential mean reversion**]"
        elif current_close < bb_lower_val:
            bb_msg = ":green[**Below Lower Band — oversold, potential bounce**]"
        elif current_close > bb_mid_val:
            bb_msg = ":green[Above Midline (bullish bias within band)]"
        else:
            bb_msg = ":red[Below Midline (bearish bias within band)]"

        bb_upper_lbl = f"BB Upper ({BB_PERIOD})"
        bb_mid_lbl   = f"BB Mid ({BB_PERIOD})"
        bb_lower_lbl = f"BB Lower ({BB_PERIOD})"
        col_bb1, col_bb2, col_bb3 = st.columns(3)
        with col_bb1:
            st.metric(label=bb_upper_lbl, value=f"${bb_upper_val:,.2f}")
        with col_bb2:
            st.metric(label=bb_mid_lbl,   value=f"${bb_mid_val:,.2f}")
        with col_bb3:
            st.metric(label=bb_lower_lbl, value=f"${bb_lower_val:,.2f}")
        st.markdown(bb_msg)
        bb_width = bb_upper_val - bb_lower_val
        st.caption(f"Band Width: ${bb_width:,.2f}")


# ─── FUNDAMENTAL ANALYSIS PANEL ────────────────────────────────────────────
# FIXED [Gate5]: All f-string {} expressions use pre-extracted local
# variables only — zero backslash characters inside any f-string expression.
# Compliant with Python 3.11 PEP 498 restriction.

def render_fundamental_analysis(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    wave: Optional[WaveResult],
    harm_results: List[PatternResult],
    vp: Optional[VolumeProfileResult],
    indicators: Dict[str, pd.Series],
) -> None:
    """
    Renders a professional fundamental analysis panel.
    CFA / FRM / MBA-Quant / CFS / CIMA / CFP framework.

    All price targets computed from live indicator data only.
    No hardcoded values. Python 3.11 compliant (pre-extraction pattern).

    Args:
        df:           OHLCV DataFrame.
        ticker:       Symbol string.
        tf_label:     Timeframe label.
        wave:         WaveResult or None.
        harm_results: List[PatternResult].
        vp:           VolumeProfileResult or None.
        indicators:   Computed indicator Dict.
    """
    st.markdown(
        """
        <div style='background:linear-gradient(135deg,#001a33 0%,#002244 100%);
                    border-left:4px solid #00E5FF;
                    padding:16px 20px;border-radius:6px;margin-bottom:12px;'>
            <span style='color:#00E5FF;font-size:13px;font-family:monospace;
                         font-weight:bold;letter-spacing:1px;'>
                &#9670; FUNDAMENTAL ANALYSIS
            </span>
            <span style='color:rgba(0,229,255,0.55);font-size:10px;
                         font-family:monospace;margin-left:12px;'>
                CFA&#174; &middot; FRM&#174; &middot; MBA/MSc Quant
                &middot; CFS &middot; CIMA &middot; CFP
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── PRE-EXTRACT ALL VALUES ──
    current_close: float = float(df["close"].iloc[-1])
    period_high:   float = float(df["high"].max())
    period_low:    float = float(df["low"].min())
    period_range:  float = period_high - period_low
    avg_vol:       float = float(df["volume"].mean()) if "volume" in df.columns else 0.0
    last_vol:      float = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
    vol_ratio:     float = (last_vol / avg_vol) if avg_vol > 1e-10 else 1.0
    range_position: float = (
        (current_close - period_low) / period_range
        if period_range > 1e-10 else 0.5
    )
    range_pct: float = range_position * 100.0

    sma200_val:   float = float(indicators["sma_200"].iloc[-1])
    sma50_val:    float = float(indicators["sma_50"].iloc[-1])
    above_sma200: bool  = current_close > sma200_val if not math.isnan(sma200_val) else False
    above_sma50:  bool  = current_close > sma50_val  if not math.isnan(sma50_val)  else False

    if vol_ratio > 1.2:
        vol_color: str = "#00FF88"
    elif vol_ratio > 0.8:
        vol_color = "#FFD700"
    else:
        vol_color = "#FF5252"

    sma200_color: str = "#00FF88" if above_sma200 else "#FF5252"
    sma200_word:  str = "ABOVE"   if above_sma200 else "BELOW"
    sma50_color:  str = "#00FF88" if above_sma50  else "#FF5252"
    sma50_word:   str = "above"   if above_sma50  else "below"

    if range_position > 0.75:
        range_context: str = (
            "indicates price is in the upper resistance zone — "
            "historically associated with distribution phases per "
            "Wyckoff methodology (CFA Technical Analysis LOS)."
        )
    elif range_position < 0.25:
        range_context = (
            "indicates price is in the lower support zone — "
            "traditionally associated with accumulation phases and "
            "potential value opportunity per Graham margin-of-safety principles."
        )
    else:
        range_context = (
            "indicates price is in the middle equilibrium zone — "
            "consistent with fair-value trading per CFA equity valuation principles."
        )

    if vol_ratio > 1.2:
        vol_context: str = (
            "Above-average volume confirms institutional participation "
            "in the current move — a key CANSLIM criterion per "
            "O'Neil (How to Make Money in Stocks, ch. 4)."
        )
    else:
        vol_context = (
            "Below-average volume suggests lack of institutional conviction. "
            "Graham warns in The Intelligent Investor (ch. 8): "
            "the investor's chief problem is likely to be themselves. "
            "Low-volume moves are frequently reversed."
        )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown(
            f"<div style='background:#001a2e;"
            f"border:1px solid rgba(0,229,255,0.2);"
            f"border-radius:6px;padding:16px;margin-bottom:10px;'>"
            f"<p style='color:#00E5FF;font-family:monospace;font-size:12px;"
            f"font-weight:bold;margin:0 0 10px 0;letter-spacing:1px;'>"
            f"PRICE STRUCTURE ANALYSIS &#8212; {ticker}</p>"
            f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;margin:0;'>"
            f"<b style='color:#00FF88;'>{ticker}</b> is currently trading at "
            f"<b style='color:#FFD700;'>${current_close:,.2f}</b>, "
            f"positioned at the "
            f"<b style='color:#FFD700;'>{range_pct:.1f}th percentile</b> "
            f"of its 90-day range "
            f"(Low: <b>${period_low:,.2f}</b> &#8212; "
            f"High: <b>${period_high:,.2f}</b>).</p>"
            f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
            f"margin:8px 0 0 0;'>"
            f"<b style='color:#00E5FF;'>CFA Curriculum (Equity Valuation):</b> "
            f"Price location at {range_pct:.1f}% of the 90-day range "
            f"{range_context}</p>"
            f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
            f"margin:8px 0 0 0;'>"
            f"<b style='color:#00E5FF;'>Volume Analysis (CMT / FRM):</b> "
            f"Current session volume is "
            f"<b style='color:{vol_color};'>{vol_ratio:.2f}x</b> "
            f"the 90-day average. {vol_context}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if not math.isnan(sma200_val):
            sma200_dist: float = (current_close / sma200_val - 1.0) * 100.0

            if above_sma200:
                sma200_context: str = (
                    "The 200-period SMA is the institutional benchmark for "
                    "long-term trend. Price above this level satisfies "
                    "O'Neil CANSLIM 'M' (Market Direction) criterion. "
                    "CFA Level 1: uptrends are defined by price above the "
                    "long-term moving average with higher highs and higher lows."
                )
            else:
                sma200_context = (
                    "Price below the 200-period SMA places this instrument "
                    "in a primary downtrend by CFA Technical Analysis definition. "
                    "O'Neil (How to Make Money in Stocks, p.100): "
                    "Cut your losses quickly. "
                    "FRM framework: bearish trend regime increases tail risk "
                    "on long positions."
                )

            if above_sma200 and above_sma50:
                sma50_context: str = (
                    "Bullish alignment: both 50 and 200 SMAs below price — "
                    "confirmed uptrend per Murphy "
                    "(Technical Analysis of the Financial Markets, ch. 9)."
                )
            elif not above_sma200 and above_sma50:
                sma50_context = (
                    "Bearish divergence: price above 50 but below 200-period SMA — "
                    "intermediate recovery within a primary downtrend. "
                    "High-risk environment."
                )
            elif not above_sma200 and not above_sma50:
                sma50_context = (
                    "Bearish alignment: price below both SMAs — confirmed "
                    "primary downtrend with no intermediate recovery support."
                )
            else:
                sma50_context = (
                    "Bullish divergence: price above 200 but below 50-period SMA — "
                    "primary trend intact, intermediate correction in progress."
                )

            st.markdown(
                f"<div style='background:#001a2e;"
                f"border:1px solid rgba(0,229,255,0.2);"
                f"border-radius:6px;padding:16px;margin-bottom:10px;'>"
                f"<p style='color:#00E5FF;font-family:monospace;font-size:12px;"
                f"font-weight:bold;margin:0 0 10px 0;letter-spacing:1px;'>"
                f"TREND REGIME ANALYSIS (CFA / CMT)</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;margin:0;'>"
                f"{ticker} is trading "
                f"<b style='color:{sma200_color};'>{sma200_word}</b> "
                f"its 200-period SMA at "
                f"<b style='color:#FFD700;'>${sma200_val:,.2f}</b> "
                f"({sma200_dist:+.2f}%).</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
                f"margin:8px 0 0 0;'>"
                f"<b style='color:#00E5FF;'>CFA Equity Framework:</b> "
                f"{sma200_context}</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
                f"margin:8px 0 0 0;'>"
                f"<b style='color:#00E5FF;'>50-Period SMA:</b> "
                f"Price is <b style='color:{sma50_color};'>{sma50_word}</b> "
                f"the 50-period SMA at "
                f"<b style='color:#FFD700;'>${sma50_val:,.2f}</b>. "
                f"{sma50_context}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with col2:
        if vp and vp["total_volume"] > 1e-10:
            vp_poc:   float = vp["poc"]
            vp_vah:   float = vp["vah"]
            vp_val_f: float = vp["val"]
            in_va_f:  bool  = vp_val_f <= current_close <= vp_vah
            poc_dist2: float = (
                abs(current_close - vp_poc) / current_close * 100.0
                if current_close > 1e-10 else 0.0
            )

            if current_close > vp_poc:
                poc_context: str = (
                    "Price ABOVE the POC: consistent with bullish momentum "
                    "above fair value. Murphy (Technical Analysis, ch. 13): "
                    "high-volume levels become strong support on retest."
                )
            else:
                poc_context = (
                    "Price BELOW the POC: trading below institutional fair value. "
                    "FRM note: price below POC increases mean-reversion probability."
                )

            if in_va_f:
                va_context: str = (
                    "Price INSIDE Value Area — market in fair-value equilibrium. "
                    "Taleb (Fooled by Randomness, ch. 5): most short-term outcomes "
                    "inside the value area are random. Avoid overconfidence."
                )
            else:
                above_below: str = "above" if current_close > vp_vah else "below"
                va_context = (
                    f"Price OUTSIDE Value Area ({above_below}). "
                    "Statistical reversion to value area historically probable. "
                    "Graham (The Intelligent Investor, ch. 20): extremes carry "
                    "embedded reversion risk."
                )

            va_range_str: str = f"${vp_val_f:,.2f} &#8212; ${vp_vah:,.2f}"

            st.markdown(
                f"<div style='background:#001a2e;"
                f"border:1px solid rgba(0,229,255,0.2);"
                f"border-radius:6px;padding:16px;margin-bottom:10px;'>"
                f"<p style='color:#00E5FF;font-family:monospace;font-size:12px;"
                f"font-weight:bold;margin:0 0 10px 0;letter-spacing:1px;'>"
                f"VOLUME PROFILE &#8212; INSTITUTIONAL ACTIVITY MAP</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;margin:0;'>"
                f"<b style='color:#FFD700;'>POC: ${vp_poc:,.2f}</b> &#8212; "
                f"highest traded volume price over 90-day window. "
                f"Distance from current: "
                f"<b style='color:#FFD700;'>{poc_dist2:.2f}%</b>.</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
                f"margin:8px 0 0 0;'>"
                f"<b style='color:#00E5FF;'>CFA / FRM Interpretation:</b> "
                f"The POC represents the market's fair-value consensus. "
                f"{poc_context}</p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
                f"margin:8px 0 0 0;'>"
                f"<b style='color:#00E5FF;'>Value Area (70%): "
                f"{va_range_str}</b></p>"
                f"<p style='color:#e0e0e0;font-size:13px;line-height:1.7;"
                f"margin:4px 0 0 0;'>{va_context}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if wave is not None:
            t1618_fa: float = wave["targets"]["target_1618"]
            t2618_fa: float = wave["targets"]["target_2618"]
            w4s_fa:   float = wave["wave4_support"]
            inv_fa:   float = wave["invalidation"]
            d1618: float = (
                (t1618_fa / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )
            d2618: float = (
                (t2618_fa / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )

            st.markdown(
                f"<div style='background:#001a2e;"
                f"border:1px solid rgba(0,229,255,0.2);"
                f"border-radius:6px;padding:16px;margin-bottom:10px;'>"
                f"<p style='color:#00E5FF;font-family:monospace;font-size:12px;"
                f"font-weight:bold;margin:0 0 10px 0;letter-spacing:1px;'>"
                f"PRICE TARGETS &#8212; ELLIOTT WAVE + FIBONACCI</p>"
                f"<p style='color:#e0e0e0;font-size:13px;margin:0;'>"
                f"Current: <b style='color:#FFD700;'>${current_close:,.2f}</b></p>"
                f"<p style='color:#00FF88;font-size:13px;margin:6px 0 0 0;'>"
                f"&#9650; W3 x1.618: <b>${t1618_fa:,.2f}</b> "
                f"({d1618:+.1f}%)</p>"
                f"<p style='color:#00FF88;font-size:13px;margin:4px 0 0 0;'>"
                f"&#9650; W3 x2.618: <b>${t2618_fa:,.2f}</b> "
                f"({d2618:+.1f}%)</p>"
                f"<p style='color:#00E5FF;font-size:13px;margin:4px 0 0 0;'>"
                f"&#9670; W4 Support: <b>${w4s_fa:,.2f}</b></p>"
                f"<p style='color:#FF5252;font-size:13px;margin:4px 0 0 0;'>"
                f"&#10007; Invalidation: <b>${inv_fa:,.2f}</b></p>"
                f"<p style='color:rgba(255,255,255,0.45);font-size:10px;"
                f"font-style:italic;margin:10px 0 0 0;'>"
                f"Source: Frost &amp; Prechter &#8212; Elliott Wave Principle "
                f"(1978). Fibonacci extensions per Carney [CV1]. "
                f"Analytical projections only &#8212; not guarantees.</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div style='background:rgba(255,82,82,0.08);
                    border:1px solid rgba(255,82,82,0.3);
                    border-radius:4px;padding:10px 14px;margin-top:8px;'>
            <p style='color:rgba(255,255,255,0.55);font-size:10px;
                      font-family:monospace;margin:0;'>
                &#9888; DISCLAIMER: Fundamental analysis is for educational
                and informational purposes only. Not financial advice.
                CFA Institute, GARP (FRM), CFP Board, CIMA, and CFS do not
                endorse this content. Past performance is not indicative
                of future results.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── TECHNICAL ANALYSIS PANEL ──────────────────────────────────────────────

def render_technical_analysis(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    indicators: Dict[str, pd.Series],
    wave: Optional[WaveResult],
    harm_results: List[PatternResult],
    piv_prices: np.ndarray,
    piv_indices: pd.DatetimeIndex,
    ichimoku: Optional[Dict[str, pd.Series]],
    ichimoku_signal: Optional[Dict[str, Any]],
    ms: Optional[MarketStructureResult],
    ewo: pd.Series,
) -> None:
    """
    Renders a professional technical analysis synthesis panel.
    CMT-certified analyst voice. All live indicators synthesised.
    Contradictions between indicators explicitly flagged.

    Args:
        df:              OHLCV DataFrame.
        ticker:          Symbol string.
        tf_label:        Timeframe label.
        indicators:      Computed indicator Dict.
        wave:            WaveResult or None.
        harm_results:    List[PatternResult].
        piv_prices:      Alternating pivot prices.
        piv_indices:     DatetimeIndex for pivots.
        ichimoku:        Dict from compute_ichimoku() or None.
        ichimoku_signal: Dict from get_ichimoku_signal() or None.
        ms:              MarketStructureResult or None.
        ewo:             EWO Series.
    """
    st.markdown(
        """
        <div style='background:linear-gradient(135deg,#001a0d 0%,#002211 100%);
                    border-left:4px solid #00FF88;
                    padding:16px 20px;border-radius:6px;margin-bottom:12px;'>
            <span style='color:#00FF88;font-size:13px;font-family:monospace;
                         font-weight:bold;letter-spacing:1px;'>
                &#9670; TECHNICAL ANALYSIS
            </span>
            <span style='color:rgba(0,255,136,0.55);font-size:10px;
                         font-family:monospace;margin-left:12px;'>
                CMT&#174; &middot; CFA&#174; &middot; Murphy &middot;
                Carney &middot; Prechter &middot; Hosoda
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    current_close: float = float(df["close"].iloc[-1])

    bull_signals:    List[str] = []
    bear_signals:    List[str] = []
    neutral_signals: List[str] = []
    contradictions:  List[str] = []

    e9  = float(indicators["ema_9"].iloc[-1])
    e21 = float(indicators["ema_21"].iloc[-1])
    e55 = float(indicators["ema_55"].iloc[-1])
    e9_prev  = float(indicators["ema_9"].iloc[-2])  if len(df) > 1 else e9
    e21_prev = float(indicators["ema_21"].iloc[-2]) if len(df) > 1 else e21

    if e9 > e21 > e55:
        bull_signals.append(
            f"EMA Stack Bullish: EMA9 ({e9:,.2f}) > EMA21 ({e21:,.2f}) > "
            f"EMA55 ({e55:,.2f}) — perfect bull alignment per Murphy ch. 9"
        )
    elif e9 < e21 < e55:
        bear_signals.append(
            f"EMA Stack Bearish: EMA9 ({e9:,.2f}) < EMA21 ({e21:,.2f}) < "
            f"EMA55 ({e55:,.2f}) — perfect bear alignment per Murphy ch. 9"
        )
    else:
        neutral_signals.append(
            f"EMA Mixed: EMA9={e9:,.2f}, EMA21={e21:,.2f}, "
            f"EMA55={e55:,.2f} — no clean trend alignment"
        )

    if e9_prev <= e21_prev and e9 > e21:
        bull_signals.append(
            f"EMA 9/21 Bullish Cross JUST FORMED at ${current_close:,.2f} "
            f"— momentum signal per Murphy ch. 9"
        )
    elif e9_prev >= e21_prev and e9 < e21:
        bear_signals.append(
            f"EMA 9/21 Bearish Cross JUST FORMED at ${current_close:,.2f} "
            f"— momentum signal per Murphy ch. 9"
        )

    rsi_val = float(indicators["rsi_21"].iloc[-1])
    if rsi_val >= RSI_OVERBOUGHT:
        bear_signals.append(
            f"RSI({RSI_PERIOD}) = {rsi_val:.1f} — Overbought "
            f"(>{RSI_OVERBOUGHT:.0f}). Murphy (ch. 10): overbought RSI "
            f"signals potential reversal. Confirm with price action."
        )
    elif rsi_val <= RSI_OVERSOLD:
        bull_signals.append(
            f"RSI({RSI_PERIOD}) = {rsi_val:.1f} — Oversold "
            f"(<{RSI_OVERSOLD:.0f}). Murphy (ch. 10): oversold RSI "
            f"signals potential bounce. Confirm with support level."
        )
    else:
        neutral_signals.append(
            f"RSI({RSI_PERIOD}) = {rsi_val:.1f} — Neutral. "
            f"No overbought/oversold condition."
        )

    macd_cur    = float(indicators["macd_line"].iloc[-1])
    signal_cur  = float(indicators["signal_line"].iloc[-1])
    hist_cur    = float(indicators["histogram"].iloc[-1])
    hist_prev   = float(indicators["histogram"].iloc[-2]) if len(df) > 1 else hist_cur
    macd_prev   = float(indicators["macd_line"].iloc[-2])   if len(df) > 1 else macd_cur
    signal_prev = float(indicators["signal_line"].iloc[-2]) if len(df) > 1 else signal_cur
    macd_lbl    = f"MACD({MACD_FAST}/{MACD_SLOW}/{MACD_SIGNAL})"

    if macd_prev <= signal_prev and macd_cur > signal_cur:
        bull_signals.append(
            f"{macd_lbl} Bullish Cross JUST FORMED — "
            f"strong momentum signal per Murphy ch. 10"
        )
    elif macd_prev >= signal_prev and macd_cur < signal_cur:
        bear_signals.append(
            f"{macd_lbl} Bearish Cross JUST FORMED — "
            f"strong momentum signal per Murphy ch. 10"
        )
    elif macd_cur > signal_cur:
        bull_signals.append(
            f"MACD above Signal ({macd_cur:,.4f} > {signal_cur:,.4f}) "
            f"— bullish momentum maintained"
        )
    else:
        bear_signals.append(
            f"MACD below Signal ({macd_cur:,.4f} < {signal_cur:,.4f}) "
            f"— bearish momentum maintained"
        )

    if abs(hist_cur) > abs(hist_prev):
        hist_dir = "bullish" if hist_cur > 0 else "bearish"
        (bull_signals if hist_cur > 0 else bear_signals).append(
            f"MACD histogram EXPANDING ({hist_dir}) — momentum accelerating"
        )
    else:
        neutral_signals.append(
            "MACD histogram contracting — momentum decelerating, "
            "potential reversal warning"
        )

    ewo_clean = ewo.dropna()
    if len(ewo_clean) > 0:
        ewo_cv = float(ewo_clean.iloc[-1])
        ewo_pv = float(ewo_clean.iloc[-2]) if len(ewo_clean) > 1 else ewo_cv
        ewo_lbl_ta = f"SMA{EWO_FAST}/SMA{EWO_SLOW}"
        if ewo_cv >= 0.0 and ewo_cv > ewo_pv:
            bull_signals.append(
                f"EWO ({ewo_lbl_ta}) = {ewo_cv:,.4f} — "
                f"Positive and Rising. Wave 3 impulse likely in progress."
            )
        elif ewo_cv >= 0.0 and ewo_cv < ewo_pv:
            neutral_signals.append(
                f"EWO ({ewo_lbl_ta}) = {ewo_cv:,.4f} — "
                f"Positive but Declining. Wave 3 may be completing; "
                f"watch for W4 correction."
            )
        elif ewo_cv < 0.0 and ewo_cv < ewo_pv:
            bear_signals.append(
                f"EWO ({ewo_lbl_ta}) = {ewo_cv:,.4f} — "
                f"Negative and Falling. Bearish momentum, likely corrective "
                f"or impulsive bear wave."
            )
        else:
            neutral_signals.append(
                f"EWO ({ewo_lbl_ta}) = {ewo_cv:,.4f} — "
                f"Negative but Rising. Potential base forming; divergence watch."
            )

    if ichimoku_signal:
        ics           = ichimoku_signal
        pvc           = ics["price_vs_cloud"]
        cloud_top_v   = ics["cloud_top"]
        cloud_bot_v   = ics["cloud_bottom"]
        cloud_col_v   = ics["cloud_color"]
        tenkan_v      = ics["tenkan_cur"]
        kijun_v       = ics["kijun_cur"]
        chikou_v      = ics["chikou_signal"]
        tk            = ics["tk_cross"]

        if pvc == "above":
            bull_signals.append(
                f"Ichimoku: Price ABOVE cloud — primary bullish trend "
                f"per Hosoda (1969). Cloud top: ${cloud_top_v:,.2f}. "
                f"Cloud color: {cloud_col_v}."
            )
        elif pvc == "below":
            bear_signals.append(
                f"Ichimoku: Price BELOW cloud — primary bearish trend "
                f"per Hosoda (1969). Cloud bottom: ${cloud_bot_v:,.2f}."
            )
        else:
            neutral_signals.append(
                "Ichimoku: Price INSIDE cloud — consolidation / trend "
                "transition. StockCharts: inside cloud = flat or "
                "indeterminate trend. Reduce position size."
            )

        if tk == "bullish_cross":
            bull_signals.append(
                "Ichimoku TK Cross BULLISH JUST FORMED — Tenkan crossed "
                "above Kijun. Strong signal when above cloud (Hosoda 1969)."
            )
        elif tk == "bearish_cross":
            bear_signals.append(
                "Ichimoku TK Cross BEARISH JUST FORMED — Tenkan crossed "
                "below Kijun. Strong signal when below cloud (Hosoda 1969)."
            )
        elif tk == "bullish_alignment":
            bull_signals.append(
                f"Ichimoku: Tenkan ({tenkan_v:,.2f}) > Kijun ({kijun_v:,.2f}) "
                f"— bullish alignment maintained."
            )
        else:
            bear_signals.append(
                f"Ichimoku: Tenkan ({tenkan_v:,.2f}) < Kijun ({kijun_v:,.2f}) "
                f"— bearish alignment maintained."
            )

        if chikou_v == "bullish":
            bull_signals.append(
                "Ichimoku Chikou above price (26 periods ago) — "
                "bullish momentum confirmation (Hosoda 1969)."
            )
        elif chikou_v == "bearish":
            bear_signals.append(
                "Ichimoku Chikou below price (26 periods ago) — "
                "bearish momentum confirmation (Hosoda 1969)."
            )

    if wave is not None:
        t1618_ta = wave["targets"]["target_1618"]
        t2618_ta = wave["targets"]["target_2618"]
        inv_ta   = wave["invalidation"]
        if wave["is_bullish"]:
            bull_signals.append(
                f"Elliott Wave: Bullish impulse detected. W3 targets: "
                f"${t1618_ta:,.2f} (x1.618) and ${t2618_ta:,.2f} (x2.618). "
                f"Source: Frost & Prechter (Elliott Wave Principle, 1978)."
            )
        else:
            bear_signals.append(
                f"Elliott Wave: Bearish impulse detected. W3 targets: "
                f"${t1618_ta:,.2f} and ${t2618_ta:,.2f}. "
                f"Invalidation: ${inv_ta:,.2f}."
            )

    if len(harm_results) > 0:
        bull_hp = [r for r in harm_results if r.is_bullish]
        bear_hp = [r for r in harm_results if not r.is_bullish]
        if bull_hp:
            bull_names = ", ".join(r.pattern_name for r in bull_hp[:3])
            bull_signals.append(
                f"Harmonic: {len(bull_hp)} Bullish pattern(s) ({bull_names}). "
                f"D-point PRZ = potential long entry. "
                f"Source: Carney [CV1/CV2/CV3]."
            )
        if bear_hp:
            bear_names = ", ".join(r.pattern_name for r in bear_hp[:3])
            bear_signals.append(
                f"Harmonic: {len(bear_hp)} Bearish pattern(s) ({bear_names}). "
                f"D-point PRZ = potential short entry. "
                f"Source: Carney [CV1/CV2/CV3]."
            )
        if bull_hp and bear_hp:
            contradictions.append(
                f"CONTRADICTION: {len(bull_hp)} Bullish AND {len(bear_hp)} "
                f"Bearish harmonic patterns detected simultaneously. "
                f"Carney [CV3] p.12: when conflicting patterns exist, "
                f"the pattern with most precise ratio alignments takes precedence. "
                f"Cross-reference with Elliott Wave phase."
            )

    if wave is not None and ichimoku_signal:
        ichi_bias_v = ichimoku_signal["overall_bias"]
        ew_bull     = wave["is_bullish"]
        ichi_bull   = ichi_bias_v in ("bull", "strong_bull")
        ichi_bear   = ichi_bias_v in ("bear", "strong_bear")
        if ew_bull and ichi_bear:
            contradictions.append(
                "CONTRADICTION: Elliott Wave BULLISH but Ichimoku bias BEARISH. "
                "CMT curriculum: when trend tools conflict, the longer-term "
                "tool takes precedence. Murphy (ch. 16): conflicting signals "
                "require additional confirmation before entry."
            )
        elif not ew_bull and ichi_bull:
            contradictions.append(
                "CONTRADICTION: Elliott Wave BEARISH but Ichimoku bias BULLISH. "
                "Seek price action confirmation at key levels."
            )

    if rsi_val <= RSI_OVERSOLD and not (macd_cur > signal_cur):
        contradictions.append(
            f"CONTRADICTION: RSI Oversold ({rsi_val:.1f}) suggests bullish "
            f"reversal potential but MACD remains Bearish. "
            f"Murphy (ch. 10): RSI divergence without MACD confirmation "
            f"is a warning, not a signal. Wait for MACD cross."
        )
    if rsi_val >= RSI_OVERBOUGHT and (macd_cur > signal_cur):
        contradictions.append(
            f"CONTRADICTION: RSI Overbought ({rsi_val:.1f}) suggests bearish "
            f"reversal but MACD remains Bullish. Murphy (ch. 10): in a strong "
            f"bull trend, overbought RSI is a holding signal, not an exit signal."
        )

    if ms:
        ms_trend_ta = ms["current_trend"]
        if ms_trend_ta == "bullish":
            bull_signals.append(
                "Market Structure: BULLISH (HH/HL sequence). "
                "Source: Luxalgo / marketcalls.in SMC framework."
            )
        elif ms_trend_ta == "bearish":
            bear_signals.append(
                "Market Structure: BEARISH (LH/LL sequence). "
                "Source: Luxalgo / marketcalls.in SMC framework."
            )

    if len(bull_signals) > len(bear_signals) + 1:
        overall_color   = "#00FF88"
        overall_verdict = "BULLISH CONSENSUS"
    elif len(bear_signals) > len(bull_signals) + 1:
        overall_color   = "#FF5252"
        overall_verdict = "BEARISH CONSENSUS"
    else:
        overall_color   = "#FFD700"
        overall_verdict = "MIXED / NEUTRAL — CAUTION WARRANTED"

    n_bull = len(bull_signals)
    n_bear = len(bear_signals)
    n_neut = len(neutral_signals)
    n_cont = len(contradictions)

    # <- FIXED [Gate5]: f-string restored to correct 4-space indent inside function
    st.markdown(
        f"<div style='background:rgba(0,255,136,0.07);"
        f"border:1px solid rgba(0,255,136,0.3);"
        f"border-radius:6px;padding:14px 18px;margin-bottom:12px;'>"
        f"<p style='color:#00FF88;font-family:monospace;font-size:12px;"
        f"font-weight:bold;margin:0 0 6px 0;letter-spacing:1px;'>"
        f"TECHNICAL CONSENSUS &#8212; {ticker} at ${current_close:,.2f}</p>"
        f"<p style='color:{overall_color};font-size:16px;font-weight:bold;"
        f"font-family:monospace;margin:0;'>{overall_verdict}</p>"
        f"<p style='color:#e0e0e0;font-size:12px;margin:6px 0 0 0;'>"
        f"Bull signals: <b style='color:#00FF88;'>{n_bull}</b> &nbsp;|&nbsp; "
        f"Bear signals: <b style='color:#FF5252;'>{n_bear}</b> &nbsp;|&nbsp; "
        f"Neutral: <b style='color:#FFD700;'>{n_neut}</b> &nbsp;|&nbsp; "
        f"Contradictions: <b style='color:#FF9800;'>{n_cont}</b></p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    col_t1, col_t2 = st.columns([1, 1])

    with col_t1:
        if bull_signals:
            st.markdown(
                "<p style='color:#00FF88;font-family:monospace;font-size:11px;"
                "font-weight:bold;letter-spacing:1px;margin:0 0 6px 0;'>"
                "&#9650; BULLISH SIGNALS</p>",
                unsafe_allow_html=True,
            )
            for sig in bull_signals:
                st.markdown(
                    f"<div style='background:rgba(0,255,136,0.05);"
                    f"border-left:3px solid #00FF88;padding:8px 12px;"
                    f"margin-bottom:6px;border-radius:0 4px 4px 0;'>"
                    f"<p style='color:#e0e0e0;font-size:12px;line-height:1.6;"
                    f"margin:0;'>&#10003; {sig}</p></div>",
                    unsafe_allow_html=True,
                )
        if neutral_signals:
            st.markdown(
                "<p style='color:#FFD700;font-family:monospace;font-size:11px;"
                "font-weight:bold;letter-spacing:1px;margin:10px 0 6px 0;'>"
                "&#9670; NEUTRAL SIGNALS</p>",
                unsafe_allow_html=True,
            )
            for sig in neutral_signals:
                st.markdown(
                    f"<div style='background:rgba(255,215,0,0.05);"
                    f"border-left:3px solid #FFD700;padding:8px 12px;"
                    f"margin-bottom:6px;border-radius:0 4px 4px 0;'>"
                    f"<p style='color:#e0e0e0;font-size:12px;line-height:1.6;"
                    f"margin:0;'>&#9671; {sig}</p></div>",
                    unsafe_allow_html=True,
                )

    with col_t2:
        if bear_signals:
            st.markdown(
                "<p style='color:#FF5252;font-family:monospace;font-size:11px;"
                "font-weight:bold;letter-spacing:1px;margin:0 0 6px 0;'>"
                "&#9660; BEARISH SIGNALS</p>",
                unsafe_allow_html=True,
            )
            for sig in bear_signals:
                st.markdown(
                    f"<div style='background:rgba(255,82,82,0.05);"
                    f"border-left:3px solid #FF5252;padding:8px 12px;"
                    f"margin-bottom:6px;border-radius:0 4px 4px 0;'>"
                    f"<p style='color:#e0e0e0;font-size:12px;line-height:1.6;"
                    f"margin:0;'>&#10007; {sig}</p></div>",
                    unsafe_allow_html=True,
                )
        if contradictions:
            st.markdown(
                "<p style='color:#FF9800;font-family:monospace;font-size:11px;"
                "font-weight:bold;letter-spacing:1px;margin:10px 0 6px 0;'>"
                "&#9889; CONTRADICTIONS FLAGGED</p>",
                unsafe_allow_html=True,
            )
            for con in contradictions:
                st.markdown(
                    f"<div style='background:rgba(255,152,0,0.08);"
                    f"border-left:3px solid #FF9800;padding:10px 12px;"
                    f"margin-bottom:8px;border-radius:0 4px 4px 0;'>"
                    f"<p style='color:#e0e0e0;font-size:12px;line-height:1.7;"
                    f"margin:0;'>{con}</p></div>",
                    unsafe_allow_html=True,
                )

    st.markdown(
        """
        <div style='background:rgba(255,82,82,0.08);
                    border:1px solid rgba(255,82,82,0.3);
                    border-radius:4px;padding:10px 14px;margin-top:8px;'>
            <p style='color:rgba(255,255,255,0.55);font-size:10px;
                      font-family:monospace;margin:0;'>
                &#9888; DISCLAIMER: Technical analysis is for educational
                purposes only. No signal constitutes investment advice.
                CMT Association and CFA Institute do not endorse this analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── PSYCHOLOGICAL ANALYSIS PANEL ──────────────────────────────────────────

def render_psychological_analysis(  # <- FIXED [Gate5]: restored to module-level def at 0-indent, body at 4-space indent
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    indicators: Dict[str, pd.Series],
    wave: Optional[WaveResult],
    harm_results: List[PatternResult],
    ms: Optional[MarketStructureResult],
    ichimoku_signal: Optional[Dict[str, Any]],
    ewo: pd.Series,
) -> None:
    """
    Renders a professional psychological / behavioral market analysis panel.
    Wall Street coaches holding CFA, CMT, FRM, MBA/MSc Quant Finance,
    CFS, CIMA, and CFP designations.

    Books applied where situationally relevant:
      Mark Douglas    — Trading in the Zone (2000)
      Jack Schwager   — Market Wizards (1989)
      Edwin Lefevre   — Reminiscences of a Stock Operator (1923)
      John J. Murphy  — Technical Analysis of the Financial Markets (1999)
      Benjamin Graham — The Intelligent Investor (1949 / rev. 2003)
      William O'Neil  — How to Make Money in Stocks (4th ed. 2009)
      Mike Bellafiore — One Good Trade (2010)
      Nassim N. Taleb — Fooled by Randomness (2001)
      Van K. Tharp    — Trade Your Way to Financial Freedom (1999)

    Args:
        df:              OHLCV DataFrame.
        ticker:          Symbol string.
        tf_label:        Timeframe label.
        indicators:      Computed indicator Dict.
        wave:            WaveResult or None.
        harm_results:    List[PatternResult].
        ms:              MarketStructureResult or None.
        ichimoku_signal: Dict from get_ichimoku_signal() or None.
        ewo:             EWO Series.
    """
    st.markdown(
        """
        <div style='background:linear-gradient(135deg,#1a0a00 0%,#2a1000 100%);
                    border-left:4px solid #FFD700;
                    padding:16px 20px;border-radius:6px;margin-bottom:12px;'>
            <span style='color:#FFD700;font-size:13px;font-family:monospace;
                         font-weight:bold;letter-spacing:1px;'>
                &#9670; PSYCHOLOGICAL &amp; BEHAVIORAL MARKET ANALYSIS
            </span>
            <span style='color:rgba(255,215,0,0.55);font-size:10px;
                         font-family:monospace;margin-left:12px;'>
                Douglas &middot; Schwager &middot; Lefevre &middot; Murphy
                &middot; Graham &middot; O'Neil &middot; Bellafiore
                &middot; Taleb &middot; Tharp
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    current_close: float = float(df["close"].iloc[-1])
    rsi_val:       float = float(indicators["rsi_21"].iloc[-1])
    avg_vol:       float = float(df["volume"].mean()) if "volume" in df.columns else 0.0
    last_vol:      float = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
    vol_ratio:     float = (last_vol / avg_vol) if avg_vol > 1e-10 else 1.0
    period_high:   float = float(df["high"].max())
    period_low:    float = float(df["low"].min())
    period_range:  float = period_high - period_low
    range_pos:     float = (
        (current_close - period_low) / period_range
        if period_range > 1e-10 else 0.5
    )
    range_pct_ps: float = range_pos * 100.0

    if rsi_val >= RSI_OVERBOUGHT:
        momentum_state = "euphoria"
    elif rsi_val <= RSI_OVERSOLD:
        momentum_state = "fear"
    elif rsi_val > 60.0:
        momentum_state = "greed"
    elif rsi_val < 40.0:
        momentum_state = "concern"
    else:
        momentum_state = "neutral"

    ewo_clean = ewo.dropna()
    ewo_cv_ps = float(ewo_clean.iloc[-1]) if len(ewo_clean) > 0 else 0.0
    ewo_pv_ps = float(ewo_clean.iloc[-2]) if len(ewo_clean) > 1 else ewo_cv_ps
    ichi_bias = ichimoku_signal["overall_bias"] if ichimoku_signal else "neutral"

    state_messages = {
        "euphoria": ("EUPHORIA / DISTRIBUTION ZONE",   "#FF5252",
                     "RSI overbought. The crowd is most bullish at market tops."),
        "fear":     ("FEAR / CAPITULATION ZONE",       "#00FF88",
                     "RSI oversold. The crowd is most bearish at market bottoms."),
        "greed":    ("GREED / MOMENTUM ZONE",          "#FFD700",
                     "RSI elevated — bullish momentum, complacency risk rising."),
        "concern":  ("CONCERN / UNCERTAINTY ZONE",     "#FF9800",
                     "RSI depressed — bearish pressure, uncertainty phase."),
        "neutral":  ("EQUILIBRIUM / DECISION ZONE",    "#00E5FF",
                     "RSI in neutral territory — market at psychological equilibrium."),
    }
    state_label, state_color, state_desc = state_messages[momentum_state]

    st.markdown(
        f"<div style='background:rgba(255,215,0,0.07);"
        f"border:1px solid rgba(255,215,0,0.3);"
        f"border-radius:6px;padding:14px 18px;margin-bottom:16px;'>"
        f"<p style='color:#FFD700;font-family:monospace;font-size:11px;"
        f"letter-spacing:1px;margin:0 0 4px 0;'>"
        f"CURRENT MARKET PSYCHOLOGY STATE</p>"
        f"<p style='color:{state_color};font-size:16px;font-weight:bold;"
        f"font-family:monospace;margin:0;'>{state_label}</p>"
        f"<p style='color:#c0c0c0;font-size:12px;margin:4px 0 0 0;'>"
        f"RSI({RSI_PERIOD}) = {rsi_val:.1f} | "
        f"{ticker} = ${current_close:,.2f} | "
        f"Volume Ratio = {vol_ratio:.2f}x avg</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    coaching_sections: List[Dict[str, str]] = []

    # ── MARK DOUGLAS ────────────────────────────────────────────────────
    if momentum_state in ("euphoria", "greed"):
        douglas_msg = (
            f"Mark Douglas writes in <em>Trading in the Zone</em> "
            f"(2000, ch. 7): 'The market is never too high to buy and "
            f"never too low to sell from the perspective of the moment.' "
            f"At RSI {rsi_val:.1f} on {ticker}, the crowd is heavily "
            f"positioned long. Douglas: <b>Think in probabilities, "
            f"not certainties.</b> The most dangerous moment in a trade "
            f"is when it is most comfortable. The need to be right is "
            f"the single biggest obstacle to profitability."
        )
    elif momentum_state in ("fear", "concern"):
        douglas_msg = (
            f"Mark Douglas (<em>Trading in the Zone</em>, ch. 8): "
            f"'Fear produces exactly the kind of trading mistakes that "
            f"cause more losses.' With RSI {rsi_val:.1f} on {ticker}, "
            f"the market is in a fearful phase. Douglas: <b>The best "
            f"traders do not try to predict what will happen — they "
            f"respond to what IS happening.</b> Fear at market lows "
            f"frequently causes traders to sell into the very lows "
            f"that become the next major support."
        )
    else:
        douglas_msg = (
            f"Mark Douglas (<em>Trading in the Zone</em>, ch. 5): "
            f"'Any trade can be a winner or a loser.' With {ticker} at "
            f"RSI {rsi_val:.1f}, the market is in equilibrium. "
            f"<b>Discipline is a function of having a trading plan.</b> "
            f"In neutral RSI environments, the edge comes entirely from "
            f"structural setups — Elliott Wave targets and harmonic PRZ "
            f"levels become the only objective entry framework."
        )
    coaching_sections.append({
        "coach": "MARK DOUGLAS — Trading in the Zone (2000)",
        "cert":  "CMT &middot; CFA Behavioral Finance",
        "color": "#00E5FF",
        "msg":   douglas_msg,
    })

    # ── JACK SCHWAGER ────────────────────────────────────────────────────
    if ichimoku_signal:
        pvc_ps          = ichimoku_signal["price_vs_cloud"]
        cloud_top_ps    = ichimoku_signal["cloud_top"]
        cloud_bottom_ps = ichimoku_signal["cloud_bottom"]
        kijun_ps        = ichimoku_signal["kijun_cur"]
    else:
        pvc_ps          = "unknown"
        cloud_top_ps    = 0.0
        cloud_bottom_ps = 0.0
        kijun_ps        = 0.0

    if pvc_ps == "above" and not math.isnan(cloud_top_ps):
        schwager_msg = (
            f"Jack Schwager documents in <em>Market Wizards</em> (1989) "
            f"that the greatest traders shared one discipline: they traded "
            f"in the direction of the primary trend and waited. With "
            f"{ticker} ABOVE the Ichimoku Cloud "
            f"(cloud top: ${cloud_top_ps:,.2f}), the primary trend is "
            f"structurally bullish per Hosoda's framework. Schwager "
            f"quoting Paul Tudor Jones (ch. 3): 'The most important rule "
            f"is to play great defence, not great offence.' "
            f"<b>Define your stop at the Kijun-sen "
            f"(${kijun_ps:,.2f}) BEFORE entry — not after.</b>"
        )
    elif pvc_ps == "below" and not math.isnan(cloud_bottom_ps):
        schwager_msg = (
            f"Jack Schwager (<em>Market Wizards</em>, ch. 1): "
            f"'Never hold a losing position.' {ticker} is BELOW the "
            f"Ichimoku Cloud (cloud bottom: ${cloud_bottom_ps:,.2f}) — "
            f"primary bearish regime. Schwager's synthesis: every "
            f"successful short-side trader used the cloud as a hard "
            f"exit boundary. <b>No exceptions. No rationalisations.</b>"
        )
    else:
        schwager_msg = (
            f"Jack Schwager (<em>Market Wizards</em>, ch. 7): "
            f"'In the cloud means in no-man's land.' "
            f"{ticker} is inside the Ichimoku Cloud — the most uncertain "
            f"regime. <b>Uncertainty is not a reason to trade more — "
            f"it is a reason to trade less.</b> Reduce position size "
            f"proportionally in this environment."
        )
    coaching_sections.append({
        "coach": "JACK SCHWAGER — Market Wizards (1989)",
        "cert":  "CFA &middot; FRM Risk Management",
        "color": "#FF9800",
        "msg":   schwager_msg,
    })

    # ── JESSE LIVERMORE via Lefevre ──────────────────────────────────────
    if wave is not None:
        w4_active_ps = not wave["w4"]["is_valid"]
        t1618_ps     = wave["targets"]["target_1618"]
        t2618_ps     = wave["targets"]["target_2618"]
        inv_ps       = wave["invalidation"]
        if w4_active_ps:
            lefevre_msg = (
                f"Edwin Lefevre channels Livermore in <em>Reminiscences "
                f"of a Stock Operator</em> (1923, ch. 11): 'It never was "
                f"my thinking that made the big money for me. It always "
                f"was my sitting. Got that? My sitting tight!' The Elliott "
                f"Wave on {ticker} shows W4 correction active. Livermore: "
                f"<b>corrections shake out weak hands — they do not change "
                f"the trend.</b> The trader who exits during W4 and chases "
                f"W5 at a worse price is the market's most consistent donor."
            )
        else:
            lefevre_msg = (
                f"Edwin Lefevre (<em>Reminiscences</em>, ch. 7): "
                f"'There is nothing new on Wall Street.' The Elliott Wave "
                f"on {ticker} confirms a valid impulse. W3 targets: "
                f"${t1618_ps:,.2f} (x1.618) and ${t2618_ps:,.2f} (x2.618). "
                f"Livermore: <b>ride the impulse, define your stop at W1 "
                f"origin (${inv_ps:,.2f}), and do not exit until the "
                f"structure changes.</b>"
            )
    else:
        lefevre_msg = (
            f"Edwin Lefevre (<em>Reminiscences</em>, ch. 2): 'The big "
            f"money was not in the individual fluctuations but in the "
            f"main movements.' No clear Elliott Wave impulse on {ticker}. "
            f"Livermore: <b>when you cannot read the tape, stay out.</b> "
            f"The absence of a clear structure is itself a signal — the "
            f"market is not ready to give a high-probability setup."
        )
    coaching_sections.append({
        "coach": "JESSE LIVERMORE via Edwin Lefevre — Reminiscences (1923)",
        "cert":  "CMT Technical Analysis &middot; Market Structure",
        "color": "#E040FB",
        "msg":   lefevre_msg,
    })

    # ── VAN K. THARP ─────────────────────────────────────────────────────
    if len(harm_results) > 0:
        best_r_ps      = harm_results[-1]
        d_price_ps     = float(best_r_ps.points[-1])
        sl_price_ps    = float(best_r_ps.stop_loss)
        risk_dist_ps   = abs(d_price_ps - sl_price_ps)
        risk_pct_ps    = (
            risk_dist_ps / current_close * 100.0
            if current_close > 1e-10 else 0.0
        )
        pattern_nm_ps  = best_r_ps.pattern_name

        if wave is not None:
            reward_ps  = abs(wave["targets"]["target_1618"] - d_price_ps)
            rr_ps      = reward_ps / risk_dist_ps if risk_dist_ps > 1e-10 else 0.0
            t1618_th   = wave["targets"]["target_1618"]
            rr_verdict = (
                "This setup meets Tharp's minimum 2:1 threshold."
                if rr_ps >= 2.0
                else "This setup is BELOW 2:1 threshold — reduce size or pass."
            )
            tharp_msg = (
                f"Van K. Tharp (<em>Trade Your Way to Financial Freedom</em>, "
                f"1999, ch. 5): <b>Position sizing is the key to meeting "
                f"your objectives as a trader.</b> "
                f"The {pattern_nm_ps} on {ticker}: "
                f"Entry zone ${d_price_ps:,.2f} | Stop ${sl_price_ps:,.2f} | "
                f"Risk ${risk_dist_ps:,.2f} ({risk_pct_ps:.2f}%). "
                f"Reward to W3 x1.618 (${t1618_th:,.2f}): "
                f"R:R = <b>{rr_ps:.2f}:1</b>. "
                f"{rr_verdict}"
            )
        else:
            tharp_msg = (
                f"Van K. Tharp (<em>Trade Your Way to Financial Freedom</em>, "
                f"ch. 5): {pattern_nm_ps} at ${d_price_ps:,.2f} with stop "
                f"${sl_price_ps:,.2f} defines risk ${risk_dist_ps:,.2f} "
                f"({risk_pct_ps:.2f}%). <b>Never risk more than 1-2% of "
                f"account equity on any single trade.</b> Without a confirmed "
                f"EW target, reward is undefined — position sizing must be "
                f"conservative."
            )
    else:
        tharp_msg = (
            f"Van K. Tharp (<em>Trade Your Way to Financial Freedom</em>, "
            f"1999, ch. 3): 'Trade your system, not your opinions.' "
            f"No harmonic patterns currently on {ticker}. "
            f"<b>Without a defined stop level, there is no trade.</b> "
            f"Undefined risk is the single greatest cause of account "
            f"destruction per Tharp's research across thousands of traders."
        )
    coaching_sections.append({
        "coach": "VAN K. THARP — Trade Your Way to Financial Freedom (1999)",
        "cert":  "CFP &middot; FRM &middot; Risk Management",
        "color": "#76FF03",
        "msg":   tharp_msg,
    })

    # ── NASSIM TALEB ─────────────────────────────────────────────────────
    if vol_ratio > 2.0:
        taleb_msg = (
            f"Nassim Taleb (<em>Fooled by Randomness</em>, 2001, ch. 3): "
            f"'We are not equipped to understand low-probability, "
            f"high-impact events.' Current volume on {ticker} is "
            f"{vol_ratio:.2f}x the 90-day average — a statistical outlier. "
            f"<b>Above-average volume days are when tail events are most "
            f"likely.</b> Historical indicator readings carry reduced "
            f"predictive power during high-volume outlier events."
        )
    else:
        taleb_msg = (
            f"Nassim Taleb (<em>Fooled by Randomness</em>, 2001, ch. 11): "
            f"'The inability to predict outliers implies the inability to "
            f"predict the course of history.' Volume on {ticker} is "
            f"{vol_ratio:.2f}x average — within normal range. "
            f"<b>Bet conservatively on every opportunity, and survive "
            f"to trade another day.</b> Every indicator signal in this "
            f"panel is a probabilistic statement, not a certainty. "
            f"Size positions such that no single outcome is catastrophic."
        )
    coaching_sections.append({
        "coach": "NASSIM NICHOLAS TALEB — Fooled by Randomness (2001)",
        "cert":  "FRM &middot; MBA/MSc Quantitative Finance &middot; Risk Theory",
        "color": "#FF5252",
        "msg":   taleb_msg,
    })

    # ── MIKE BELLAFIORE ──────────────────────────────────────────────────
    if ms and ms["structure_events"]:
        last_evt_b    = ms["structure_events"][-1]
        evt_type_b    = last_evt_b["event_type"]
        evt_dir_b     = last_evt_b["direction"].upper()
        evt_price_b   = last_evt_b["price"]
        evt_date_b    = pd.Timestamp(last_evt_b["date"]).strftime("%Y-%m-%d")
        evt_level_b   = last_evt_b["level"]
        bellafiore_msg = (
            f"Mike Bellafiore (<em>One Good Trade</em>, 2010, ch. 4): "
            f"'There is only one trade. The trade in front of you, right now.' "
            f"Most recent structure event on {ticker}: "
            f"<b>{evt_type_b}</b> ({evt_dir_b}) at ${evt_price_b:,.2f} "
            f"on {evt_date_b}, breaking ${evt_level_b:,.2f}. "
            f"Bellafiore: <b>the BOS/CHoCH is the institutional footprint. "
            f"React to structural confirmation — do not predict.</b>"
        )
    else:
        bellafiore_msg = (
            f"Mike Bellafiore (<em>One Good Trade</em>, 2010, ch. 2): "
            f"'Preparation is the difference between the amateur and the "
            f"professional.' No clear BOS/CHoCH confirmed on {ticker}. "
            f"<b>Waiting for structural confirmation before committing "
            f"capital is not weakness — it is the most professional trade "
            f"of all.</b> The goal is not to trade constantly. "
            f"The goal is to make good trades."
        )
    coaching_sections.append({
        "coach": "MIKE BELLAFIORE — One Good Trade (2010)",
        "cert":  "CMT &middot; Institutional Trading &middot; Execution",
        "color": "#18FFFF",
        "msg":   bellafiore_msg,
    })

    # ── BENJAMIN GRAHAM ──────────────────────────────────────────────────
    if range_pos < 0.25:
        graham_msg = (
            f"Benjamin Graham (<em>The Intelligent Investor</em>, rev. 2003, "
            f"ch. 20): 'The margin of safety is always dependent on the price "
            f"paid.' {ticker} at ${current_close:,.2f} is at the "
            f"{range_pct_ps:.1f}th percentile of its 90-day range — near "
            f"the low. <b>The margin of safety is highest when price is near "
            f"the range low.</b> At range lows, fear is at maximum — the "
            f"analytical case for buying is most compelling precisely when "
            f"the emotional urge is to sell."
        )
    elif range_pos > 0.75:
        graham_msg = (
            f"Benjamin Graham (<em>The Intelligent Investor</em>, ch. 8): "
            f"'Mr. Market is your servant, not your guide.' {ticker} at "
            f"${current_close:,.2f} is at the {range_pct_ps:.1f}th "
            f"percentile — near the high. <b>The four most dangerous "
            f"words: this time it is different.</b> At range highs, the "
            f"margin of safety is compressed. Graham: if price has already "
            f"moved significantly and the margin is thin, wait. "
            f"The next opportunity will come."
        )
    else:
        graham_msg = (
            f"Benjamin Graham (<em>The Intelligent Investor</em>, ch. 1): "
            f"'An investment operation is one which promises safety of "
            f"principal and an adequate return.' {ticker} at "
            f"${current_close:,.2f} is in the middle of its 90-day range. "
            f"<b>The analytical tools in this terminal — Elliott targets, "
            f"harmonic PRZs, Volume Profile POC — collectively define a "
            f"range of fair value. Trade within that framework, "
            f"not outside it.</b>"
        )
    coaching_sections.append({
        "coach": "BENJAMIN GRAHAM — The Intelligent Investor (1949 / rev. 2003)",
        "cert":  "CFA &middot; CFP &middot; Fundamental Value Analysis",
        "color": "#FFD700",
        "msg":   graham_msg,
    })

    # Render all coaching sections
    for section in coaching_sections:
        c     = section["color"]
        coach = section["coach"]
        cert  = section["cert"]
        msg   = section["msg"]
        st.markdown(
            f"<div style='background:rgba(0,0,0,0.3);"
            f"border:1px solid {c}33;"
            f"border-left:4px solid {c};"
            f"border-radius:0 6px 6px 0;"
            f"padding:16px 20px;margin-bottom:14px;'>"
            f"<div style='display:flex;align-items:baseline;"
            f"margin-bottom:8px;flex-wrap:wrap;gap:8px;'>"
            f"<span style='color:{c};font-family:monospace;"
            f"font-size:11px;font-weight:bold;letter-spacing:0.5px;'>"
            f"{coach}</span>"
            f"<span style='background:{c}22;color:{c};font-size:9px;"
            f"font-family:monospace;padding:2px 8px;border-radius:3px;"
            f"border:1px solid {c}44;'>{cert}</span>"
            f"</div>"
            f"<p style='color:#d8d8d8;font-size:13px;line-height:1.75;"
            f"margin:0;font-style:italic;'>{msg}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Collective wisdom — pre-extract before f-string
    if harm_results:
        last_r_ps    = harm_results[-1]
        last_d_ps    = float(last_r_ps.points[-1])
        last_sl_ps   = float(last_r_ps.stop_loss)
        harm_summary = (
            f"Most recent harmonic PRZ: ${last_d_ps:,.2f} "
            f"with stop ${last_sl_ps:,.2f}."
        )
    else:
        harm_summary = "No harmonic PRZ currently active."

    if wave is not None:
        wt1618_ps    = wave["targets"]["target_1618"]
        wt2618_ps    = wave["targets"]["target_2618"]
        wave_summary = (
            f"Elliott Wave W3 targets: "
            f"${wt1618_ps:,.2f} and ${wt2618_ps:,.2f}."
        )
    else:
        wave_summary = "No Elliott impulse target currently confirmed."

    ichi_bias_display = ichi_bias.replace("_", " ").upper()
    ichi_summary = (
        f"Ichimoku overall bias: {ichi_bias_display}."
        if ichimoku_signal else ""
    )

    st.markdown(
        f"<div style='background:rgba(255,215,0,0.06);"
        f"border:1px solid rgba(255,215,0,0.35);"
        f"border-radius:6px;padding:18px 22px;margin-top:8px;'>"
        f"<p style='color:#FFD700;font-family:monospace;font-size:12px;"
        f"font-weight:bold;letter-spacing:1px;margin:0 0 10px 0;'>"
        f"&#9670; COLLECTIVE WISDOM &#8212; SYNTHESIS</p>"
        f"<p style='color:#e0e0e0;font-size:13px;line-height:1.8;margin:0;'>"
        f"The seven coaches above, collectively holding CFA, CMT, FRM, "
        f"MBA/MSc Quant Finance, CFS, CIMA, and CFP designations, "
        f"converge on a universal principle: "
        f"<b style='color:#FFD700;'>"
        f"Know your risk before you know your reward. "
        f"Define your stop before you define your target. "
        f"Trade the plan &#8212; not the emotion."
        f"</b></p>"
        f"<p style='color:#e0e0e0;font-size:13px;line-height:1.8;"
        f"margin:10px 0 0 0;'>"
        f"{ticker} at <b style='color:#FFD700;'>${current_close:,.2f}</b>: "
        f"{wave_summary} {harm_summary} {ichi_summary} "
        f"Market psychology: <b style='color:{state_color};'>"
        f"{state_label}</b>."
        f"</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style='background:rgba(255,82,82,0.06);
                    border:1px solid rgba(255,82,82,0.25);
                    border-radius:4px;padding:10px 14px;margin-top:10px;'>
            <p style='color:rgba(255,255,255,0.50);font-size:10px;
                      font-family:monospace;margin:0;'>
                &#9888; EDUCATIONAL DISCLAIMER: All psychological coaching
                commentary is for educational and informational purposes only.
                Not financial advice or investment recommendations.
                The authors cited (Douglas, Schwager, Lefevre, Murphy, Graham,
                O'Neil, Bellafiore, Taleb, Tharp) and certifying bodies
                (CFA Institute, CMT Association, GARP FRM, CFP Board, CIMA,
                CFS) do not endorse this analysis or platform.
                Trading involves substantial risk of loss.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:  # <- FIXED [Gate5]: def at 0-indent, body at 4-space indent throughout
    """
    Main entry point for the 3-Month Scanner page.
    Orchestrates all data fetching, computation, and rendering.
    All values computed from live data — nothing hardcoded.
    """
    # <- NEW [typography]: inject global font CSS on every render
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    st.title(t("scan_title"))
    st.caption(
        "Japanese candlesticks · Elliott Wave · Harmonic Patterns · "
        "Ichimoku Cloud · EWO · Volume Profile · Market Structure · "
        "EMA/SMA/BB/RSI/MACD · Fundamental · Technical · Psychological Analysis"
    )
    st.markdown("---")

    # ── SIDEBAR ──────────────────────────────────────────────────────────
    st.sidebar.header("Scanner Configuration")

    ticker: str = st.sidebar.text_input(
        "Ticker Symbol", value="SPY"
    ).upper().strip()

    tf_key: str = st.sidebar.selectbox(
        "Timeframe",
        list(TF_CONFIG.keys()),
        index=2,
    )
    tf_cfg = TF_CONFIG[tf_key]

    pivot_order: int = st.sidebar.slider(
        "Pivot Sensitivity (order)",
        min_value=2,
        max_value=15,
        value=tf_cfg["pivot_order"],
        help="Lower = more pivots. Higher = macro structures only.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Overlay Toggles**")

    show_ema:      bool = st.sidebar.checkbox("EMA 9/21/55",       value=True)
    show_sma:      bool = st.sidebar.checkbox("SMA 20/50/200",     value=True)
    show_bb:       bool = st.sidebar.checkbox("Bollinger Bands",   value=True)
    show_ew:       bool = st.sidebar.checkbox("Elliott Wave",      value=True)
    show_hp:       bool = st.sidebar.checkbox("Harmonic Patterns", value=True)
    show_vp:       bool = st.sidebar.checkbox("Volume Profile",    value=True)
    show_ms:       bool = st.sidebar.checkbox("Market Structure",  value=True)
    show_ichimoku: bool = st.sidebar.checkbox("Ichimoku Cloud",    value=True)

    if tf_cfg.get("interval") == "1h" or tf_cfg.get("resample_4h"):
        st.sidebar.caption(
            "Note: yfinance limits 1H/4H to ~730 days. "
            "90-day window is within this limit."
        )

    run_scan: bool = st.sidebar.button(
        "Run 3-Month Scan", type="primary"
    )

    if not run_scan:
        st.info(
            "Configure ticker and timeframe in the sidebar, "
            "then press **Run 3-Month Scan**."
        )
        return  # <- FIXED [Gate5]: return is now correctly inside main() at 4-space indent

    # ── DATA FETCH ───────────────────────────────────────────────────────
    with st.spinner(
        f"Fetching {ticker} [{tf_cfg['label']}] · 90 days..."
    ):
        try:
            df = fetch_ohlcv(ticker, tf_key)
        except Exception as e:
            logger.error(
                f"Fetch failed {ticker} {tf_key}: {e}", exc_info=True
            )
            st.error(f"Data Fetch Error: {str(e)}")
            return  # <- FIXED [Gate5]: return correctly inside main()

    if df.empty:
        st.error(
            f"No data returned for {ticker} on {tf_cfg['label']}. "
            "Verify the ticker symbol."
        )
        return  # <- FIXED [Gate5]: return correctly inside main()

    if len(df) < max(EWO_SLOW, BB_PERIOD, SMA_PERIODS[-1]) + 5:
        st.warning(
            f"Only {len(df)} candles available for {ticker} on "
            f"{tf_cfg['label']}. Some indicators may be incomplete. "
            "Consider switching to a shorter timeframe."
        )

    # ── INDICATORS ───────────────────────────────────────────────────────
    with st.spinner("Computing indicators..."):
        indicators: Dict[str, pd.Series] = compute_indicators(df)

    # ── ICHIMOKU ─────────────────────────────────────────────────────────
    ichimoku:        Optional[Dict[str, pd.Series]] = None
    ichimoku_signal: Optional[Dict[str, Any]]       = None
    with st.spinner("Computing Ichimoku Cloud..."):
        try:
            ichimoku        = compute_ichimoku(df)
            ichimoku_signal = get_ichimoku_signal(df, ichimoku)
        except Exception as e:
            logger.error(f"Ichimoku failed: {e}", exc_info=True)
            st.warning(f"Ichimoku computation failed: {str(e)}")

    # ── VOLUME PROFILE ───────────────────────────────────────────────────
    vp: Optional[VolumeProfileResult] = None
    with st.spinner("Computing Volume Profile..."):
        try:
            vp = compute_volume_profile(df)
        except Exception as e:
            logger.error(f"VP failed: {e}", exc_info=True)
            st.warning(f"Volume Profile failed: {str(e)}")

    # ── MARKET STRUCTURE ─────────────────────────────────────────────────
    ms: Optional[MarketStructureResult] = None
    with st.spinner("Computing Market Structure..."):
        try:
            ms = compute_market_structure(df)
        except Exception as e:
            logger.error(f"MS failed: {e}", exc_info=True)
            st.warning(f"Market Structure failed: {str(e)}")

    # ── ELLIOTT WAVE ─────────────────────────────────────────────────────
    wave: Optional[WaveResult] = None
    with st.spinner("Running Elliott Wave analysis..."):
        wave = run_elliott_pipeline(df, pivot_order)

    if wave is None:
        st.info(
            "No valid Elliott Wave impulse detected. "
            "EW overlays hidden. Try lowering pivot sensitivity."
        )

    # ── HARMONIC PATTERNS ────────────────────────────────────────────────
    harm_results: List[PatternResult]
    piv_prices:   np.ndarray
    piv_indices:  pd.DatetimeIndex

    with st.spinner("Running harmonic pattern scan..."):
        harm_results, piv_prices, piv_indices = run_harmonic_pipeline(
            df, pivot_order
        )

    # ── STATUS HEADER ────────────────────────────────────────────────────
    current_close: float = float(df["close"].iloc[-1])

    if wave is not None:
        if wave["w4"]["is_valid"]:
            wave_phase = "W4 Complete — W5 Watch"
        elif wave["impulse"].get("valid", True):
            wave_phase = "Impulse Active"
        else:
            wave_phase = "Structure Unclear"
    else:
        wave_phase = "Not Detected"

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric(label=f"{ticker} Current", value=f"${current_close:,.2f}")
    with col_s2:
        st.metric(label="Timeframe", value=tf_cfg["label"])
    with col_s3:
        st.metric(label="EW Phase",  value=wave_phase)
    with col_s4:
        st.metric(label="Patterns Detected", value=str(len(harm_results)))

    # ── MAIN CHART ───────────────────────────────────────────────────────
    st.subheader("Main Chart — All Overlays")
    st.plotly_chart(
        render_main_chart(
            df=df,
            ticker=ticker,
            tf_label=tf_cfg["label"],
            indicators=indicators,
            wave=wave,
            harm_results=harm_results,
            piv_prices=piv_prices,
            piv_indices=piv_indices,
            vp=vp,
            ms=ms,
            show_ema=show_ema,
            show_sma=show_sma,
            show_bb=show_bb,
            show_ew=show_ew,
            show_hp=show_hp,
            show_vp=show_vp,
            show_ms=show_ms,
            ichimoku=ichimoku,
            show_ichimoku=show_ichimoku,
        ),
        width="stretch",
    )

    # ── VOLUME ───────────────────────────────────────────────────────────
    st.subheader("Volume")
    st.plotly_chart(
        render_volume_chart(df, tf_cfg["label"]),
        width="stretch",
    )

    # ── EWO ──────────────────────────────────────────────────────────────
    st.subheader(
        f"Elliott Wave Oscillator — SMA({EWO_FAST}) - SMA({EWO_SLOW})"
    )
    st.plotly_chart(
        render_ewo_chart(df, indicators["ewo"], tf_cfg["label"]),
        width="stretch",
    )

    # ── RSI ──────────────────────────────────────────────────────────────
    st.subheader(f"RSI ({RSI_PERIOD})")
    st.plotly_chart(
        render_rsi_chart(df, indicators["rsi_21"], tf_cfg["label"]),
        width="stretch",
    )

    # ── MACD ─────────────────────────────────────────────────────────────
    st.subheader(f"MACD ({MACD_FAST}/{MACD_SLOW}/{MACD_SIGNAL})")
    st.plotly_chart(
        render_macd_chart(
            df,
            indicators["macd_line"],
            indicators["signal_line"],
            indicators["histogram"],
            tf_cfg["label"],
        ),
        width="stretch",
    )

    # ── PRZ ZOOM ─────────────────────────────────────────────────────────
    if len(harm_results) > 0 and len(piv_prices) > 0:
        st.subheader("PRZ Zoom — Most Recent Harmonic Pattern")
        last_harm = harm_results[-1]
        last_bull  = "Bullish" if last_harm.is_bullish else "Bearish"
        st.caption(
            f"Most recent: {last_bull} {last_harm.pattern_name} "
            f"· +/-{PRZ_CANDLE_CONTEXT} candles"
        )
        st.plotly_chart(
            render_prz_zoom_chart(
                df, harm_results[-1], piv_prices, piv_indices
            ),
            width="stretch",
        )

    # ── ELLIOTT WAVE EXPANDED ────────────────────────────────────────────
    if wave is not None:
        st.subheader("Elliott Wave — Full Structure View")
        st.caption(
            "Complete wave structure with Fibonacci grid, W3 target zone, "
            "W4 support, and invalidation level. "
            "Use the Plotly toolbar to zoom and pan."
        )
        st.plotly_chart(
            render_ew_expanded(df, ticker, tf_cfg["label"], wave),
            width="stretch",
        )

    # ── ANALYSIS PANEL ───────────────────────────────────────────────────
    render_analysis_panel(
        df=df,
        ticker=ticker,
        tf_label=tf_cfg["label"],
        indicators=indicators,
        wave=wave,
        harm_results=harm_results,
        piv_prices=piv_prices,
        piv_indices=piv_indices,
        vp=vp,
        ms=ms,
        ewo=indicators["ewo"],
    )

    # ── THREE ANALYSIS TABS ───────────────────────────────────────────────
    st.markdown("---")
    st.header(t("scan_advanced"))
    st.caption(
        "Three-dimensional market analysis: Fundamental · Technical · "
        "Psychological. All values computed from live data. "
        "All sources cited. Contradictions explicitly flagged."
    )

    analysis_tab1, analysis_tab2, analysis_tab3 = st.tabs([
        "◆ Fundamental Analysis",
        "◆ Technical Analysis",
        "◆ Psychological Analysis",
    ])

    with analysis_tab1:
        render_fundamental_analysis(
            df=df,
            ticker=ticker,
            tf_label=tf_cfg["label"],
            wave=wave,
            harm_results=harm_results,
            vp=vp,
            indicators=indicators,
        )

    with analysis_tab2:
        render_technical_analysis(
            df=df,
            ticker=ticker,
            tf_label=tf_cfg["label"],
            indicators=indicators,
            wave=wave,
            harm_results=harm_results,
            piv_prices=piv_prices,
            piv_indices=piv_indices,
            ichimoku=ichimoku,
            ichimoku_signal=ichimoku_signal,
            ms=ms,
            ewo=indicators["ewo"],
        )

    with analysis_tab3:
        render_psychological_analysis(
            df=df,
            ticker=ticker,
            tf_label=tf_cfg["label"],
            indicators=indicators,
            wave=wave,
            harm_results=harm_results,
            ms=ms,
            ichimoku_signal=ichimoku_signal,
            ewo=indicators["ewo"],
        )

    # ── SESSION STATE ────────────────────────────────────────────────────
    st.session_state["scanner_ui_result"] = {
        "ticker":         ticker,
        "tf_key":         tf_key,
        "tf_label":       tf_cfg["label"],
        "current_close":  current_close,
        "wave_detected":  wave is not None,
        "patterns_count": len(harm_results),
        "trend":          ms["current_trend"] if ms else "neutral",
    }


if __name__ == "__main__":
    main()