# pages/confluence_ui.py
# <- FIXED [Gate 2c ERROR-A]: TF_CONFIG interval "1wk" -> "1W", "1mo" -> "1M".
# <- FIXED [Gate 2c ERROR-B]: fetch_ohlcv resample_1y branch.
#    df.index = pd.to_datetime(df.index) applied before df.resample("YE")
#    to ensure DatetimeIndex. OpenBB .to_df() may return plain Index.
# <- NEW [typography]: GLOBAL_TYPOGRAPHY_CSS defined after SHARK_LABELS.
#    Injected at top of main(). Times New Roman 16/22px, warm off-white palette.

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import logging
from translations import t, inject_rtl_css  # <- NEW [i18n]
import datetime
import sys
import os
from typing import Dict, Any, List, Optional, Tuple, TypedDict

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from engine.analysis.elliott import (
        ElliottEngine,
        validate_wave_2,
        project_wave_3,
        validate_wave_4,
    )
except ImportError as e:
    st.error(f"Critical Import Error: Elliott engine failed. {e}")
    st.stop()

try:
    from engine.analysis.harmonics import HarmonicEngine, PatternResult
except ImportError as e:
    st.error(f"Critical Import Error: Harmonic engine failed. {e}")
    st.stop()

try:
    from engine.structure.swings import find_pivots, enforce_alternation
except ImportError as e:
    st.error(f"Critical Import Error: Swings engine failed. {e}")
    st.stop()

try:
    from openbb import obb
except ImportError as e:
    st.error(f"Critical Import Error: OpenBB failed. {e}")
    st.stop()

logger = logging.getLogger("ConfluenceUI")

st.set_page_config(
    page_title="EW + HP Golden Setup",
    layout="wide",
)

# ─── CONSTANTS ─────────────────────────────────────────────────────────────

CONFLUENCE_THRESHOLD_PCT: float = 0.02

FIB_RETRACEMENT_LEVELS: List[float] = [0.236, 0.382, 0.500, 0.618, 0.786]

FIB_COLORS: Dict[float, str] = {
    0.236: "rgba(255,255,255,0.25)",
    0.382: "rgba(255,165,0,0.45)",
    0.500: "rgba(255,255,0,0.45)",
    0.618: "rgba(0,255,136,0.55)",
    0.786: "rgba(255,80,80,0.55)",
}

# <- FIXED [Gate 2c ERROR-A]: interval strings corrected.
TF_CONFIG: Dict[str, Dict[str, Any]] = {
    "Hourly (10Y)": {
        "interval":     "1h",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": True,
        "label":        "Hourly",
        "pivot_order":  3,
    },
    "Four Hour (10Y)": {
        "interval":     "1h",
        "resample_4h":  True,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": True,
        "label":        "4-Hour",
        "pivot_order":  3,
    },
    "Daily (10Y)": {
        "interval":     "1d",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Daily",
        "pivot_order":  5,
    },
    "Weekly (10Y)": {
        "interval":     "1W",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Weekly",
        "pivot_order":  5,
    },
    "Monthly (10Y)": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Monthly",
        "pivot_order":  3,
    },
    "Yearly (10Y)": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  True,
        "years":        10,
        "intraday_cap": False,
        "label":        "Yearly",
        "pivot_order":  2,
    },
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

class WavePhase(TypedDict):
    active_wave:     str
    is_bullish:      bool
    invalidation:    float
    target_1618:     float
    target_2618:     float
    w2_ratio:        float
    w2_is_ideal:     bool
    w4_valid:        bool
    w4_overlap:      float
    impulse_valid:   bool
    impulse_reason:  str
    pts:             List[float]
    pt_dates:        List[str]


class ConfluenceResult(TypedDict):
    has_confluence:        bool
    ew_phase:              WavePhase
    overlapping_patterns:  List[Dict[str, Any]]
    overlap_threshold_pct: float
    ew_level_used:         str
    ew_level_price:        float


# ─── DATA FETCH ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_ohlcv(ticker: str, tf_key: str) -> pd.DataFrame:
    """
    Fetches OHLCV data from OpenBB yfinance provider.
    Applies 4H or Yearly resampling in pandas where required.
    Ensures DatetimeIndex before resampling operations.

    Args:
        ticker: Equity symbol string.
        tf_key: Key from TF_CONFIG.

    Returns:
        pd.DataFrame with OHLCV columns and DatetimeIndex.
    """
    cfg = TF_CONFIG[tf_key]
    start_date = (
        datetime.date.today()
        - datetime.timedelta(days=365 * cfg["years"])
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

    # <- FIXED [Gate 2c ERROR-B]: ensure DatetimeIndex before any resample.
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

    if cfg["resample_1y"]:
        df = (
            df.resample("YE")
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


# ─── ELLIOTT WAVE PIPELINE ─────────────────────────────────────────────────

def run_elliott_pipeline(
    df: pd.DataFrame,
    pivot_order: int,
    lookback: int,
) -> Optional[WavePhase]:
    """
    Runs the full Elliott Wave detection pipeline on a price DataFrame.

    Args:
        df:          OHLCV DataFrame.
        pivot_order: argrelextrema order parameter.
        lookback:    Maximum number of pivots to scan back.

    Returns:
        WavePhase dict or None.
    """
    engine = ElliottEngine()

    try:
        pivots   = find_pivots(df, order=pivot_order)
        p_prices = pivots["close"].values
        p_dates  = pivots.index
    except Exception as e:
        logger.error(f"Elliott pivot extraction failed: {e}", exc_info=True)
        return None

    if len(p_prices) < 6:
        return None

    for i in range(5, min(len(p_prices), lookback + 1)):
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
            if i >= 6
            else p_prices[-min(i + 1, len(p_prices)):]
        )
        impulse_result = (
            engine.validate_impulse(list(six_pts))
            if len(six_pts) >= 6
            else {"valid": True, "reason": "5-point only"}
        )

        is_bullish: bool = float(pts[1]) > float(pts[0])

        if w4["is_valid"]:
            active_wave = "W4 complete — W5 watch"
        elif not impulse_result.get("valid", True):
            active_wave = impulse_result.get("reason", "Structure invalid")
        else:
            active_wave = "W2/W4 correction active"

        wave3_length: float  = abs(float(pts[3]) - float(pts[2]))
        wave4_support: float = float(pts[3]) - (0.382 * wave3_length)

        return WavePhase(
            active_wave    = active_wave,
            is_bullish     = is_bullish,
            invalidation   = float(pts[0]),
            target_1618    = targets["target_1618"],
            target_2618    = targets["target_2618"],
            w2_ratio       = w2["ratio"],
            w2_is_ideal    = w2["is_ideal"],
            w4_valid       = w4["is_valid"],
            w4_overlap     = w4["overlap_depth"],
            impulse_valid  = impulse_result.get("valid", True),
            impulse_reason = impulse_result.get("reason", ""),
            pts            = [float(p) for p in pts],
            pt_dates       = [str(d) for d in pt_dates],
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
    engine = HarmonicEngine()
    empty  = ([], np.array([], dtype=float), pd.DatetimeIndex([]))

    try:
        raw_pivots  = find_pivots(df, order=pivot_order)
        alt_pivots  = enforce_alternation(raw_pivots)
        piv_prices  = alt_pivots["close"].values
        piv_indices = alt_pivots.index
    except Exception as e:
        logger.error(f"Harmonic pivot extraction failed: {e}", exc_info=True)
        return empty

    if len(piv_prices) < 6:
        return empty

    try:
        results = engine.scan(list(piv_prices))
        return results, piv_prices, piv_indices
    except Exception as e:
        logger.error(f"Harmonic scan failed: {e}", exc_info=True)
        return empty


# ─── CONFLUENCE DETECTOR ───────────────────────────────────────────────────

def detect_confluence(
    ew_phase: WavePhase,
    harm_results: List[PatternResult],
    piv_prices: np.ndarray,
    piv_indices: pd.DatetimeIndex,
) -> ConfluenceResult:
    """
    Detects whether any harmonic PRZ falls within CONFLUENCE_THRESHOLD_PCT
    of a key Elliott Wave level.

    Args:
        ew_phase:     WavePhase from run_elliott_pipeline().
        harm_results: List[PatternResult] from run_harmonic_pipeline().
        piv_prices:   Alternating pivot prices.
        piv_indices:  DatetimeIndex for pivots.

    Returns:
        ConfluenceResult TypedDict.
    """
    ew_levels: List[Tuple[str, float]] = [
        ("W3 Target 1.618", ew_phase["target_1618"]),
        ("W3 Target 2.618", ew_phase["target_2618"]),
        ("Invalidation W1", ew_phase["invalidation"]),
    ]

    overlapping: List[Dict[str, Any]] = []
    best_level_name:  str   = ""
    best_level_price: float = 0.0

    for result in harm_results:
        d_price = float(result.points[-1])

        diffs       = np.abs(piv_prices - d_price)
        nearest_idx = int(np.argmin(diffs))
        nearest_idx = min(nearest_idx, len(piv_indices) - 1)
        d_date      = str(piv_indices[nearest_idx])

        for level_name, level_price in ew_levels:
            if abs(level_price) < 1e-10:
                continue
            overlap_pct = abs(d_price - level_price) / abs(level_price)
            if overlap_pct <= CONFLUENCE_THRESHOLD_PCT:
                overlapping.append({
                    "pattern_name":   result.pattern_name,
                    "is_bullish":     result.is_bullish,
                    "d_price":        d_price,
                    "d_date":         d_date,
                    "stop_loss":      float(result.stop_loss),
                    "ew_level_name":  level_name,
                    "ew_level_price": level_price,
                    "overlap_pct":    round(overlap_pct * 100, 3),
                    "points":         [float(p) for p in result.points],
                })
                if not best_level_name:
                    best_level_name  = level_name
                    best_level_price = level_price
                break

    has_confluence = len(overlapping) > 0

    return ConfluenceResult(
        has_confluence        = has_confluence,
        ew_phase              = ew_phase,
        overlapping_patterns  = overlapping,
        overlap_threshold_pct = CONFLUENCE_THRESHOLD_PCT * 100,
        ew_level_used         = best_level_name if has_confluence else "None",
        ew_level_price        = best_level_price if has_confluence else 0.0,
    )


# ─── CONFLUENCE CHART ──────────────────────────────────────────────────────

def render_confluence_chart(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    ew_phase: WavePhase,
    harm_results: List[PatternResult],
    piv_prices: np.ndarray,
    piv_indices: pd.DatetimeIndex,
    confluence: ConfluenceResult,
) -> go.Figure:
    """
    Renders a unified confluence chart combining Elliott Wave structure,
    Fibonacci grid, harmonic D-points, and Golden Setup zone highlight.

    Args:
        df:           OHLCV DataFrame.
        ticker:       Symbol string.
        tf_label:     Timeframe label.
        ew_phase:     Elliott Wave phase result.
        harm_results: All detected harmonic patterns.
        piv_prices:   Alternating pivot prices.
        piv_indices:  DatetimeIndex for pivots.
        confluence:   Confluence detection result.

    Returns:
        Plotly Figure.
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
        name=ticker,
        showlegend=False,
        opacity=0.55,
    ))

    pts      = ew_phase["pts"]
    pt_dates = ew_phase["pt_dates"]
    is_bull  = ew_phase["is_bullish"]

    wave_x = [pd.Timestamp(d) for d in pt_dates if d]
    wave_y = pts[: len(wave_x)]

    fig.add_trace(go.Scatter(
        x=wave_x,
        y=wave_y,
        mode="lines+markers+text",
        line=dict(
            color="#00E5FF" if is_bull else "#FF6B6B",
            width=2.5,
        ),
        marker=dict(size=11, color="#00E5FF", symbol="circle"),
        text=["0", "1", "2", "3", "4"][: len(wave_y)],
        textposition="top center",
        textfont=dict(color="#FFFFFF", size=13, family="monospace"),
        name="Elliott Wave",
        showlegend=True,
    ))

    if len(pts) >= 2:
        w1_high  = max(float(pts[0]), float(pts[1]))
        w1_low   = min(float(pts[0]), float(pts[1]))
        w1_range = w1_high - w1_low

        for level in FIB_RETRACEMENT_LEVELS:
            fib_price = w1_high - (w1_range * level)
            fig.add_hline(
                y=fib_price,
                line_dash="dot",
                line_color=FIB_COLORS.get(level, "rgba(255,255,255,0.3)"),
                line_width=1.0,
                annotation_text=f"  {level:.3f}  ${fib_price:,.2f}",
                annotation_position="right",
                annotation_font=dict(
                    color=FIB_COLORS.get(level, "rgba(255,255,255,0.5)"),
                    size=9,
                ),
            )

    t1618 = ew_phase["target_1618"]
    t2618 = ew_phase["target_2618"]

    fig.add_hrect(
        y0=min(t1618, t2618),
        y1=max(t1618, t2618),
        fillcolor="rgba(0,229,255,0.08)",
        line_width=0,
        annotation_text="W3 Target Zone",
        annotation_position="right",
        annotation_font=dict(color="#00E5FF", size=9),
    )

    for val, lbl in [(t1618, "W3 x1.618"), (t2618, "W3 x2.618")]:
        fig.add_hline(
            y=val,
            line_dash="dash",
            line_color="#00E5FF",
            line_width=1.2,
            annotation_text=f"  {lbl}  ${val:,.2f}",
            annotation_position="right",
            annotation_font=dict(color="#00E5FF", size=9),
        )

    inv = ew_phase["invalidation"]
    fig.add_hline(
        y=inv,
        line_dash="dash",
        line_color="#FF4444",
        line_width=1.5,
        annotation_text=f"  Invalidation  ${inv:,.2f}",
        annotation_position="right",
        annotation_font=dict(color="#FF4444", size=9),
    )

    for result in harm_results:
        color   = PATTERN_COLORS.get(result.pattern_name, "#FFFFFF")
        d_price = float(result.points[-1])

        diffs       = np.abs(piv_prices - d_price)
        nearest_idx = int(np.argmin(diffs))
        nearest_idx = min(nearest_idx, len(piv_indices) - 1)
        d_date      = piv_indices[nearest_idx]
        direction   = "Bull" if result.is_bullish else "Bear"

        fig.add_trace(go.Scatter(
            x=[d_date],
            y=[d_price],
            mode="markers+text",
            marker=dict(
                size=13,
                color=color,
                symbol="diamond",
                line=dict(color="#0e1117", width=1.5),
            ),
            text=[f"D:{result.pattern_name[:4]}"],
            textposition="bottom center",
            textfont=dict(color=color, size=9),
            name=f"{direction} {result.pattern_name} D",
            showlegend=True,
        ))

    if confluence["has_confluence"]:
        conf_price = confluence["ew_level_price"]
        conf_half  = conf_price * CONFLUENCE_THRESHOLD_PCT

        fig.add_hrect(
            y0=conf_price - conf_half,
            y1=conf_price + conf_half,
            fillcolor="rgba(255,215,0,0.18)",
            line_color="#FFD700",
            line_width=1.5,
            line_dash="dot",
            annotation_text=(
                f"GOLDEN SETUP ZONE  "
                f"${conf_price:,.2f} "
                f"(+/-{confluence['overlap_threshold_pct']:.0f}%)"
            ),
            annotation_position="right",
            annotation_font=dict(color="#FFD700", size=11),
        )

    phase_color = "#FFD700" if confluence["has_confluence"] else "#00E5FF"
    phase_text  = (
        "GOLDEN SETUP DETECTED"
        if confluence["has_confluence"]
        else f"EW Phase: {ew_phase['active_wave']}"
    )

    fig.add_annotation(
        text=phase_text,
        xref="paper", yref="paper",
        x=0.01, y=0.97,
        showarrow=False,
        font=dict(color=phase_color, size=12, family="monospace"),
        bgcolor="rgba(14,17,23,0.90)",
        bordercolor=phase_color,
        borderwidth=1,
        borderpad=6,
    )

    fig.update_layout(
        template="plotly_dark",
        height=700,
        margin=dict(l=10, r=150, t=55, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(128,128,128,0.07)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(128,128,128,0.07)",
            fixedrange=False,
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        legend=dict(
            bgcolor="rgba(14,17,23,0.85)",
            bordercolor="rgba(128,128,128,0.3)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=9),
        ),
        title=dict(
            text=f"{ticker} — EW + HP Confluence Map ({tf_label})",
            font=dict(color="#e0e0e0", size=15),
        ),
    )
    return fig


# ─── EDUCATION PANEL ───────────────────────────────────────────────────────

def render_education_panel(
    ew_phase: Optional[WavePhase],
    confluence: Optional[ConfluenceResult],
    ticker: str,
) -> None:
    """
    Renders the EW + HP theory and live-linked analysis panel.
    All price levels are computed from live data.

    Args:
        ew_phase:    Live Elliott Wave phase result, or None.
        confluence:  Live confluence result, or None.
        ticker:      Symbol for contextual display.
    """
    st.markdown("---")
    st.subheader("The Elliott Wave + Harmonic Confluence Framework")

    col_ew, col_hp = st.columns([1, 1])

    with col_ew:
        st.markdown(
            """
### Elliott Wave Theory — The Market Map

EW identifies the **current phase of market psychology**.
It tells you where the trend is likely headed over the long term.

**The Trend (Waves 1, 3, 5)**
When the crowd is buying or selling in a clear direction.
Wave 3 is typically the strongest and longest wave.

**The Correction (Waves 2, 4, A-B-C)**
When the market rests or traps over-eager traders before the
next big move.

**The Three Absolute Rules (Never Broken)**
1. Wave 2 never retraces more than 100% of Wave 1.
2. Wave 3 is never the shortest motive wave.
3. Wave 4 never enters the price territory of Wave 1.

**The Goal**
Use EW to ensure you are not buying the top of a finished
five-wave move. EW gives you the **Map**.
            """
        )

        if ew_phase is not None:
            st.markdown("**Live Elliott Status**")
            direction_str  = "Bullish" if ew_phase["is_bullish"] else "Bearish"
            wave3_length   = abs(ew_phase["pts"][3] - ew_phase["pts"][2]) if len(ew_phase["pts"]) >= 4 else 0.0
            wave4_support  = ew_phase["pts"][3] - (0.382 * wave3_length) if len(ew_phase["pts"]) >= 4 else 0.0
            st.info(
                f"**{ticker} — {direction_str}**\n\n"
                f"Phase: {ew_phase['active_wave']}\n\n"
                f"W2 Retrace: {ew_phase['w2_ratio']:.3f} "
                + ("(Ideal)" if ew_phase["w2_is_ideal"] else "(Valid)") + "\n\n"
                f"W3 Target 1.618: ${ew_phase['target_1618']:,.2f}\n\n"
                f"W3 Target 2.618: ${ew_phase['target_2618']:,.2f}\n\n"
                f"W4 Support (0.382 x W3): ${wave4_support:,.2f}\n\n"
                f"Invalidation: ${ew_phase['invalidation']:,.2f}"
            )

            if ew_phase["w4_valid"]:
                st.success("Rule 3 PASS — W4 has not entered W1 territory.")
            else:
                st.error(
                    f"Rule 3 VIOLATION — W4 overlapped W1 by "
                    f"${ew_phase['w4_overlap']:.2f}."
                )
        else:
            st.warning(
                f"No valid Elliott impulse detected for {ticker}. "
                "Try adjusting pivot sensitivity."
            )

    with col_hp:
        st.markdown(
            """
### Harmonic Patterns — The Sniper Entry

HP provides **exact price coordinates** for a reversal using
Fibonacci mathematics.

**The PRZ (Potential Reversal Zone)**
A specific, narrow price box where the pattern completes.

**The Math**
Patterns like the Gartley, Bat, or Butterfly require price to
hit specific Fibonacci ratios before a trade is valid.

**The Goal**
Use HP to find the **tightest possible entry** with the
smallest necessary stop loss. HP gives you the **Sniper Scope**.
            """
        )

        if confluence is not None:
            harm_data = st.session_state.get("conf_harm_results", {})
            patterns  = harm_data.get("patterns", [])
            if patterns:
                st.markdown("**Live Harmonic Status**")
                for p in patterns[:5]:
                    direction_str = "Bullish" if p["is_bullish"] else "Bearish"
                    color_str     = "green" if p["is_bullish"] else "red"
                    st.markdown(
                        f":{color_str}[{direction_str} **{p['pattern_name']}**] — "
                        f"D: ${p['d_price']:,.2f} — "
                        f"SL: ${p['stop_loss']:,.2f}"
                    )
            else:
                st.warning(
                    f"No harmonic patterns detected for {ticker}."
                )

    st.markdown("---")
    st.subheader("The Golden Setup — EW + HP Confluence")

    st.markdown(
        """
A trade reaches its **highest probability of success** when
Elliott Wave and Harmonic Patterns overlap at the same price zone.

| Tool | What It Provides |
|---|---|
| **Elliott Wave** | The Map — direction, phase, long-term context |
| **Harmonic Patterns** | The Sniper Scope — exact entry and stop loss |
| **Confluence** | The Golden Setup — both confirm the same level |

> EW tells you the **Why** and the **Where**.
> Harmonics tell you the **When** and the **At What Price**.
        """
    )

    if confluence is not None:
        if confluence["has_confluence"]:
            st.success(
                f"GOLDEN SETUP DETECTED on {ticker} — "
                f"{len(confluence['overlapping_patterns'])} "
                f"pattern(s) converging within "
                f"{confluence['overlap_threshold_pct']:.0f}% of "
                f"{confluence['ew_level_used']} "
                f"(${confluence['ew_level_price']:,.2f})"
            )

            for item in confluence["overlapping_patterns"]:
                direction_str = "Bullish" if item["is_bullish"] else "Bearish"
                color_str     = "green" if item["is_bullish"] else "red"

                with st.expander(
                    f":{color_str}[{direction_str} "
                    f"{item['pattern_name']}] — "
                    f"PRZ: ${item['d_price']:,.2f} — "
                    f"EW Level: {item['ew_level_name']} "
                    f"${item['ew_level_price']:,.2f} — "
                    f"Overlap: {item['overlap_pct']:.2f}%",
                    expanded=True,
                ):
                    gcol1, gcol2 = st.columns([1, 1])

                    with gcol1:
                        st.markdown("**Golden Setup Details**")
                        st.metric("EW Level", f"${item['ew_level_price']:,.2f}", delta=item["ew_level_name"])
                        st.metric("Harmonic PRZ (D)", f"${item['d_price']:,.2f}", delta=item["pattern_name"])
                        st.metric("Price Overlap", f"{item['overlap_pct']:.3f}%")
                        st.error(f"Stop Loss: ${item['stop_loss']:,.2f}")

                    with gcol2:
                        st.markdown("**What This Confluence Means**")
                        ew_phase_desc  = confluence["ew_phase"]["active_wave"]
                        direction_long = "bullish" if item["is_bullish"] else "bearish"
                        st.info(
                            f"Elliott Wave says: **{ew_phase_desc}**\n\n"
                            f"The **{item['pattern_name']}** pattern is "
                            f"completing its PRZ at ${item['d_price']:,.2f} "
                            f"— within {item['overlap_pct']:.2f}% of the "
                            f"EW {item['ew_level_name']} level.\n\n"
                            f"This is a **{direction_long} Golden Setup**: "
                            f"the EW Map and the Harmonic Sniper Scope are "
                            f"pointing to the same price zone."
                        )
                        st.warning(
                            "Smart money behaviour: Institutional algorithms "
                            "monitor both Elliott structure and Fibonacci "
                            "extension levels. When both frameworks converge, "
                            "order density at this zone increases sharply. "
                            "A confirming candle at the PRZ is the trigger."
                        )
                        st.error(
                            f"Invalidation: A close beyond "
                            f"${item['stop_loss']:,.2f} "
                            f"voids both the harmonic structure and the "
                            f"Elliott impulse context simultaneously."
                        )
        else:
            st.info(
                f"No Golden Setup detected for {ticker}. "
                f"No harmonic PRZ falls within "
                f"{confluence['overlap_threshold_pct']:.0f}% of any "
                f"Elliott Wave level."
            )


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point for the EW + HP Golden Setup Confluence page."""
    # <- NEW [typography]: inject global font CSS on every render
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    st.title(t("cf_title"))
    st.caption(
        "Elliott Wave gives the Map. "
        "Harmonic Patterns give the Sniper Entry. "
        "Confluence gives the Golden Setup."
    )
    st.markdown("---")

    st.sidebar.header("Confluence Configuration")

    ticker: str = st.sidebar.text_input(
        "Ticker Symbol", value="SPY"
    ).upper().strip()

    tf_key: str = st.sidebar.selectbox(
        "Timeframe",
        list(TF_CONFIG.keys()),
        index=2,
    )
    tf_cfg = TF_CONFIG[tf_key]

    if tf_cfg["intraday_cap"]:
        st.sidebar.caption(
            "Note: yfinance limits 1H and 4H data to approximately "
            "730 days regardless of the 10Y window selected."
        )

    ew_lookback: int = st.sidebar.slider(
        "EW Pivot Scan Depth", min_value=5, max_value=20, value=10
    )

    harm_pivot_order: int = st.sidebar.slider(
        "Harmonic Pivot Sensitivity (order)",
        min_value=2,
        max_value=20,
        value=tf_cfg["pivot_order"],
    )

    if st.sidebar.button("Run Confluence Scan"):

        with st.spinner(f"Fetching {ticker} [{tf_cfg['label']}] data..."):
            try:
                df = fetch_ohlcv(ticker, tf_key)
            except Exception as e:
                logger.error(
                    f"Fetch failed {ticker} {tf_key}: {e}", exc_info=True
                )
                st.error(f"Data Fetch Error: {str(e)}")
                st.stop()

        if df.empty:
            st.error(
                f"No data returned for {ticker}. "
                "Verify the ticker symbol and timeframe."
            )
            st.stop()

        with st.spinner("Running Elliott Wave analysis..."):
            ew_phase = run_elliott_pipeline(
                df,
                pivot_order=tf_cfg["pivot_order"],
                lookback=ew_lookback,
            )

        with st.spinner("Running harmonic pattern scan..."):
            harm_results, piv_prices, piv_indices = run_harmonic_pipeline(
                df, pivot_order=harm_pivot_order
            )

        confluence: Optional[ConfluenceResult] = None
        if ew_phase is not None:
            confluence = detect_confluence(
                ew_phase, harm_results, piv_prices, piv_indices
            )

        st.markdown(
            f"**{ticker} — {tf_cfg['label']} scan complete.**  "
            f"EW: "
            + (f"`{ew_phase['active_wave']}`" if ew_phase else "`Not detected`")
            + f"   |   Patterns: `{len(harm_results)}`"
            + (
                f"   |   **GOLDEN SETUP: "
                f"{len(confluence['overlapping_patterns'])} detected**"
                if confluence and confluence["has_confluence"]
                else "   |   No confluence"
            )
        )

        if ew_phase is not None:
            st.subheader("Confluence Map")
            empty_conf = ConfluenceResult(
                has_confluence        = False,
                ew_phase              = ew_phase,
                overlapping_patterns  = [],
                overlap_threshold_pct = CONFLUENCE_THRESHOLD_PCT * 100,
                ew_level_used         = "None",
                ew_level_price        = 0.0,
            )
            conf_fig = render_confluence_chart(
                df, ticker, tf_cfg["label"],
                ew_phase, harm_results, piv_prices, piv_indices,
                confluence if confluence else empty_conf,
            )
            st.plotly_chart(conf_fig, width="stretch")
        else:
            st.warning(
                "Elliott Wave structure not detected. "
                "Try adjusting pivot sensitivity."
            )

        st.session_state["conf_ew_phase"]      = ew_phase
        st.session_state["conf_harm_results"]  = {
            "ticker":   ticker,
            "tf_label": tf_cfg["label"],
            "patterns": [
                {
                    "pattern_name": r.pattern_name,
                    "is_bullish":   r.is_bullish,
                    "d_price":      float(r.points[-1]),
                    "stop_loss":    float(r.stop_loss),
                    "points":       [float(p) for p in r.points],
                }
                for r in harm_results
            ],
        }
        st.session_state["conf_ticker"] = ticker

        render_education_panel(ew_phase, confluence, ticker)

    else:
        render_education_panel(None, None, ticker)
        st.info(
            "Configure the ticker and timeframe above, "
            "then press **Run Confluence Scan**."
        )


if __name__ == "__main__":
    main()