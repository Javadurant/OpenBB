# pages/harmonics_ui.py
# <- FIXED [Gate 2c ERROR-B]: df.index = pd.to_datetime(df.index) before resample.
# <- FIXED [Gate 2c ERROR-C v2]: render_prz_zoom_chart add_vline() annotation
#    removed. plotly 6.6.0 _mean([str]) -> TypeError: int + str.
#    Label moved to separate fig.add_annotation() which does not call _mean().
# <- NEW [pattern-expand]: render_pattern_expanded() — full-size 850px pattern
#    chart with alternating cyan/green legs, arrowhead ratio callouts,
#    PRZ shading, stop loss line, direction banner.
#    Triggered by st.expander below each PRZ zoom chart in main().
# <- NEW [typography]: GLOBAL_TYPOGRAPHY_CSS defined after EXPAND_PATTERN_COLORS.
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
from typing import List, Dict, Any, Tuple

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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

try:
    from engine.pipeline import AnalysisPipeline
except ImportError:
    class AnalysisPipeline:
        """Placeholder for future pipeline integration."""
        def run(self, df: pd.DataFrame) -> pd.DataFrame:
            return df

logger = logging.getLogger("HarmonicsUI")

st.set_page_config(page_title="Harmonic Audit 2.0", layout="wide")

# ─── CONSTANTS ─────────────────────────────────────────────────────────────

PRZ_CANDLE_CONTEXT: int = 10
CONFLUENCE_THRESHOLD_PCT: float = 0.02

TF_CONFIG: Dict[str, Dict[str, Any]] = {
    "Hourly (10Y)": {
        "interval":     "1h",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": True,
        "label":        "Hourly",
    },
    "Four Hour (10Y)": {
        "interval":     "1h",
        "resample_4h":  True,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": True,
        "label":        "4-Hour",
    },
    "Daily (10Y)": {
        "interval":     "1d",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Daily",
    },
    "Weekly (10Y)": {
        "interval":     "1W",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Weekly",
    },
    "Monthly (10Y)": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "intraday_cap": False,
        "label":        "Monthly",
    },
    "Yearly (10Y)": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  True,
        "years":        10,
        "intraday_cap": False,
        "label":        "Yearly",
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

# <- NEW [pattern-expand]: expanded chart palette — blue/green theme.
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

# ─── GLOBAL TYPOGRAPHY — Times New Roman 16/22px, eye-comfort palette ──────
# <- NEW [typography]: inject at top of main(). No separate file needed.
# Body: 16px · Headlines: 22px · Font: Times New Roman
# Color: warm off-white palette — optimised for long reading sessions.
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


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """
    Converts a 6-character hex color string to a plotly-compatible rgba() string.
    plotly 6.6.0 rejects 8-char hex+alpha for fillcolor.

    Args:
        hex_color: 6-char hex string e.g. "#00BCD4".
        alpha:     Opacity 0.0-1.0.

    Returns:
        rgba() string e.g. "rgba(0,188,212,0.13)".
    """
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


POINT_LABELS_MAP: Dict[int, Dict[int, str]] = {
    4: {0: "A", 1: "B", 2: "C", 3: "D"},
    5: {0: "X", 1: "A", 2: "B", 3: "C", 4: "D"},
    6: {0: "0", 1: "X", 2: "A", 3: "B", 4: "C", 5: "D"},
}
SHARK_LABELS: Dict[int, str] = {0: "0", 1: "X", 2: "A", 3: "B", 4: "C"}

PATTERN_CONTEXT: Dict[str, Dict[str, str]] = {
    "Standard AB=CD": {
        "structure": "Four-point symmetric price structure where CD mirrors AB in length.",
        "market_meaning": (
            "The AB=CD completion point (D) marks a high-probability reversal zone. "
            "Price has completed a measured corrective move. Market participants "
            "who entered at A are now in profit and may exit, creating resistance "
            "or support at D depending on direction."
        ),
        "smart_money": (
            "Institutional orders frequently cluster at the D completion. A bullish "
            "AB=CD completing at support often shows absorption candles — narrow "
            "spread bars on above-average volume as smart money accumulates against "
            "retail selling. Look for a bullish engulfing or hammer confirmation "
            "before entry."
        ),
        "invalidation": "Pattern invalidated if price closes beyond the stop level.",
    },
    "Reciprocal AB=CD": {
        "structure": "Extended AB=CD where C moves beyond A, creating a deeper structure.",
        "market_meaning": (
            "Signals a more aggressive corrective move than standard AB=CD. "
            "The deeper C leg indicates stronger momentum in the correction. "
            "D completion at the reciprocal level represents exhaustion of that move."
        ),
        "smart_money": (
            "The extended C leg often shakes out weak hands before the reversal. "
            "Smart money uses this liquidity sweep to build positions. "
            "High-volume rejection wicks at D are the primary confirmation signal."
        ),
        "invalidation": "Pattern invalidated if price closes beyond the stop level.",
    },
    "Gartley": {
        "structure": (
            "Five-point XABCD. B retraces XA at 0.618 (+/-1.9%). "
            "C retraces AB at 0.382 or 0.886. D completes at 0.786 XA. "
            "Source: Carney [CV1] pp.92-98."
        ),
        "market_meaning": (
            "The Gartley is a retracement pattern within a larger trend. "
            "D completes at 0.786 of the primary XA leg — a deep retracement "
            "suggesting the primary trend is pausing, not reversing."
        ),
        "smart_money": (
            "Smart money uses Gartley D zones to reload positions in the primary trend. "
            "A bullish candle at D with a volume spike signals institutional participation. "
            "The 0.786 level is a known order cluster for algorithmic systems."
        ),
        "invalidation": "Breach of X point on a closing basis invalidates the pattern.",
    },
    "Bat": {
        "structure": (
            "Five-point XABCD. B retraces XA at 0.382-0.500. "
            "C retraces AB at 0.382 or 0.886. D completes at 0.886 XA. "
            "Source: Carney [CV2] pp.67-72."
        ),
        "market_meaning": (
            "The Bat 0.886 D completion reflects maximum stress on the prior trend. "
            "The risk-reward at the Bat D is among the highest of all patterns."
        ),
        "smart_money": (
            "The 0.886 level is a high-conviction accumulation or distribution zone. "
            "Watch for volume contraction at D followed by volume expansion on the "
            "reversal candle."
        ),
        "invalidation": "Any close beyond X point invalidates.",
    },
    "Alternate Bat": {
        "structure": (
            "Five-point XABCD. B retraces XA at 0.382 MAX. "
            "C retraces AB at 0.382 or 0.886. D completes at 0.886-1.130 XA. "
            "Source: Carney [CV3] Chapter 5."
        ),
        "market_meaning": (
            "D at 0.886-1.130 of XA signals a measured extension move at exhaustion."
        ),
        "smart_money": (
            "Extension completions at 1.130 XA attract counter-trend institutional orders."
        ),
        "invalidation": "Continued extension beyond the 1.130 XA completion zone.",
    },
    "Butterfly": {
        "structure": (
            "Five-point XABCD. B retraces XA at 0.786 (+/-2.4%). "
            "C retraces AB at 0.382 or 0.886. D extends to 1.270 or 1.414 XA. "
            "CD/BC: 1.618-2.240. Source: Carney [CV1] pp.128-133."
        ),
        "market_meaning": (
            "The Butterfly signals price has exhausted a directional push and is "
            "vulnerable to a sharp reversal back toward the X-A origin zone."
        ),
        "smart_money": (
            "The 1.270 and 1.414 extension levels are well-known program-trading "
            "triggers. The reversal often develops as a sharp momentum shift."
        ),
        "invalidation": "Extension beyond 1.414 XA without reversal structure.",
    },
    "Crab": {
        "structure": (
            "Five-point XABCD. B retraces XA at 0.382-0.618. "
            "C retraces AB at 0.382 or 0.886. D extends to 1.618 XA. "
            "CD/BC: 2.618-3.618. Source: Carney [CV1] pp.152-157."
        ),
        "market_meaning": (
            "The 1.618 XA extension at D is a mathematically significant exhaustion "
            "point. The reversal from Crab D tends to be sharp and impulsive."
        ),
        "smart_money": (
            "Large institutions place standing limit orders at the 1.618 extension. "
            "A single high-volume rejection candle at D is the primary signal."
        ),
        "invalidation": "Close beyond 1.618 XA extension.",
    },
    "Deep Crab": {
        "structure": (
            "Variant Crab. B retraces XA at 0.886 (+5% upper). "
            "C retraces AB at 0.382 or 0.886. D extends to 1.618 XA. "
            "CD/BC: 2.000-3.618. Source: Carney [CV3] Chapter 6."
        ),
        "market_meaning": (
            "The Deep Crab combines the extreme B retracement with the extreme "
            "D extension. Dual extremity makes it rare and the signal stronger."
        ),
        "smart_money": (
            "The deep B creates a false breakdown that triggers retail stop losses "
            "before the extension to D. Smart money uses this stop-hunt to build."
        ),
        "invalidation": "Close beyond 1.618 XA extension without reversal candle.",
    },
    "Shark": {
        "structure": (
            "Five-point 0XABC (no D). B extends XA at 1.130-1.618. "
            "C completes at 0.886 or 1.130 of 0X leg. C extends AB at 1.618-2.240. "
            "Source: Carney [CV3] Chapter 8."
        ),
        "market_meaning": (
            "The Shark C point represents counter-trend exhaustion. "
            "Often the precursor to a 5-0 pattern forming next."
        ),
        "smart_money": (
            "Watch for volume exhaustion at C: declining volume on the final push "
            "signals smart money is no longer participating."
        ),
        "invalidation": "Extension of C beyond 1.130 of the 0X leg on close.",
    },
    "5-0": {
        "structure": (
            "Six-point 0XABCD. B extends XA at 1.130-1.618. "
            "C extends AB at 1.618-2.240. D retraces BC at exactly 0.500 (+/-1%). "
            "Reciprocal AB=CD: CD/AB 0.900-1.100. Source: Carney [CV3] Chapter 8."
        ),
        "market_meaning": (
            "The 5-0 most often appears at major trend inflection points and "
            "signals a high-probability reversal."
        ),
        "smart_money": (
            "The convergence of the Reciprocal AB=CD and 50% retracement creates "
            "a high-density order cluster recognised by algorithmic systems."
        ),
        "invalidation": "Price closing through D and continuing in the BC direction.",
    },
}


# ─── DATA FETCH ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_ohlcv(ticker: str, tf_key: str) -> pd.DataFrame:
    """
    Fetches OHLCV data from OpenBB yfinance provider.
    Ensures DatetimeIndex before all resample operations.

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

    # <- FIXED [Gate 2c ERROR-B]: ensure DatetimeIndex before resample.
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


# ─── POINT MAPPING UTILITY ─────────────────────────────────────────────────

def map_pattern_to_dates(
    result: PatternResult,
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
) -> Tuple[List[Any], List[float]]:
    """
    Maps each pattern price point to its nearest pivot date.

    Args:
        result:        PatternResult from HarmonicEngine.scan().
        pivot_prices:  Array of alternating pivot close prices.
        pivot_indices: DatetimeIndex aligned with pivot_prices.

    Returns:
        Tuple of (list of dates, list of prices).
    """
    x_dates:  List[Any]   = []
    y_prices: List[float] = []

    for price in result.points:
        diffs       = np.abs(pivot_prices - float(price))
        nearest_idx = int(np.argmin(diffs))
        nearest_idx = min(nearest_idx, len(pivot_indices) - 1)
        x_dates.append(pivot_indices[nearest_idx])
        y_prices.append(float(price))

    return x_dates, y_prices


# ─── CHART: FULL PRICE + ALL PATTERN OVERLAYS ──────────────────────────────

def render_harmonic_chart(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    results: List[PatternResult],
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
) -> go.Figure:
    """
    Renders a full-history TradingView-style candlestick chart with all
    detected harmonic patterns overlaid as annotated zigzag traces.

    Args:
        df:            Full OHLCV DataFrame.
        ticker:        Symbol string.
        tf_label:      Timeframe label.
        results:       All PatternResult objects from scan.
        pivot_prices:  Alternating pivot close prices.
        pivot_indices: DatetimeIndex for pivots.

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
    ))

    for result in results:
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

        fig.add_trace(go.Scatter(
            x=x_dates,
            y=y_prices,
            mode="lines+markers+text",
            line=dict(color=color, width=1.5, dash="dot"),
            marker=dict(size=9, color=color, symbol="circle"),
            text=[labels.get(i, str(i)) for i in range(n)],
            textposition="top center",
            textfont=dict(color=color, size=10),
            name=f"{direction} {result.pattern_name}",
            showlegend=True,
        ))

        fig.add_hline(
            y=float(result.stop_loss),
            line_dash="dash",
            line_color=color,
            opacity=0.45,
            annotation_text=f"SL: ${float(result.stop_loss):,.2f}",
            annotation_position="right",
            annotation_font_color=color,
        )

    fig.update_layout(
        template="plotly_dark",
        height=580,
        margin=dict(l=10, r=90, t=50, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(128,128,128,0.08)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(128,128,128,0.08)",
            fixedrange=False,
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        legend=dict(
            bgcolor="rgba(14,17,23,0.85)",
            bordercolor="rgba(128,128,128,0.3)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=10),
        ),
        title=dict(
            text=f"{ticker} — Full Harmonic Scan ({tf_label})",
            font=dict(color="#e0e0e0", size=15),
        ),
    )
    return fig


# ─── CHART: PRZ ZOOM ───────────────────────────────────────────────────────

def render_prz_zoom_chart(
    df: pd.DataFrame,
    result: PatternResult,
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
    pattern_index: int,
) -> go.Figure:
    """
    Renders a dedicated zoom chart centered on a single harmonic pattern PRZ.
    Shows PRZ_CANDLE_CONTEXT candles before and after the pattern.

    Args:
        df:            Full OHLCV DataFrame.
        result:        Single PatternResult to visualize.
        pivot_prices:  Alternating pivot close prices.
        pivot_indices: DatetimeIndex for pivots.
        pattern_index: Index in results list for chart title numbering.

    Returns:
        Plotly Figure.
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

    # ── CANDLE WINDOW EXTRACTION ────────────────────────────────────────
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

    # ── BASE CANDLESTICK ────────────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_window.index,
        open=df_window["open"],
        high=df_window["high"],
        low=df_window["low"],
        close=df_window["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name="Price",
        showlegend=False,
    ))

    # ── PATTERN ZIGZAG WITH FULL DATE + PRICE LABELS ────────────────────
    point_text: List[str] = []
    for i in range(n):
        lbl  = labels.get(i, str(i))
        date = pd.Timestamp(x_dates[i]).strftime("%Y-%m-%d")
        px   = y_prices[i]
        point_text.append(f"<b>{lbl}</b><br>{date}<br>${px:,.2f}")

    fig.add_trace(go.Scatter(
        x=x_dates,
        y=y_prices,
        mode="lines+markers+text",
        line=dict(color=color, width=2.5),
        marker=dict(
            size=14,
            color=color,
            symbol="circle",
            line=dict(color="#0e1117", width=2),
        ),
        text=point_text,
        textposition="top center",
        textfont=dict(color=color, size=11, family="monospace"),
        name=f"{direction} {result.pattern_name}",
        showlegend=True,
    ))

    # ── RATIO ANNOTATIONS ON EACH LEG MIDPOINT ─────────────────────────
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
            x=mid_ts,
            y=mid_y,
            text=f"{ratio:.3f}",
            showarrow=False,
            font=dict(color=color, size=10, family="monospace"),
            bgcolor="rgba(14,17,23,0.80)",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
        )

    # ── PRZ SHADING BOX AT D COMPLETION ────────────────────────────────
    d_price: float  = y_prices[-1]
    prz_half: float = d_price * 0.005

    fig.add_hrect(
        y0=d_price - prz_half,
        y1=d_price + prz_half,
        fillcolor=hex_to_rgba(color, 0.13),
        line_color=color,
        line_width=1,
        line_dash="dot",
        annotation_text=f"PRZ: ${d_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(color=color, size=11),
    )

    # ── STOP LOSS LINE ──────────────────────────────────────────────────
    sl_price: float = float(result.stop_loss)
    fig.add_hline(
        y=sl_price,
        line_dash="dash",
        line_color="#FF4444",
        line_width=1.8,
        annotation_text=f"Stop Loss: ${sl_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(color="#FF4444", size=11),
    )

    # ── D POINT VERTICAL MARKER ─────────────────────────────────────────
    # <- FIXED [Gate 2c ERROR-C v2]: annotation removed from add_vline().
    d_date_str: str = pd.Timestamp(x_dates[-1]).strftime("%Y-%m-%d")

    fig.add_vline(
        x=d_date_str,
        line_dash="dot",
        line_color=color,
        line_width=1.2,
        opacity=0.6,
    )
    fig.add_annotation(
        x=d_date_str,
        y=1.0,
        yref="paper",
        text="D — PRZ",
        showarrow=False,
        font=dict(color=color, size=10),
        bgcolor="rgba(14,17,23,0.80)",
        bordercolor=color,
        borderwidth=1,
        borderpad=3,
        xanchor="center",
    )

    fig.update_layout(
        template="plotly_dark",
        height=540,
        margin=dict(l=10, r=140, t=65, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(128,128,128,0.08)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(128,128,128,0.08)",
            fixedrange=False,
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        legend=dict(
            bgcolor="rgba(14,17,23,0.85)",
            bordercolor="rgba(128,128,128,0.3)",
            borderwidth=1,
            font=dict(color="#e0e0e0", size=10),
        ),
        title=dict(
            text=(
                f"Pattern {pattern_index + 1}: {direction} "
                f"{result.pattern_name} — PRZ Zoom "
                f"(+/-{PRZ_CANDLE_CONTEXT} candles)"
            ),
            font=dict(color=color, size=14),
        ),
    )
    return fig


# ─── CHART: PATTERN EXPANDED ───────────────────────────────────────────────

def render_pattern_expanded(
    df: pd.DataFrame,
    result: PatternResult,
    pivot_prices: np.ndarray,
    pivot_indices: pd.DatetimeIndex,
    pattern_index: int,
) -> go.Figure:
    """
    Renders a full-size 850px expanded harmonic pattern chart for use inside
    st.expander. Designed for maximum clarity and detail.

    Features:
      - Candlestick base spanning full pattern range + 20 candles each side
      - Bold pattern zigzag alternating cyan/green per leg (even/odd)
      - Each pivot: large 20px marker + letter label + exact date + price
        with arrowhead callout annotation
      - Ratio annotation on each leg midpoint with arrowhead callout
      - PRZ shading box at D completion (+-0.5% of D price)
      - Stop loss horizontal line in red
      - D-point vertical line (annotation via add_annotation, not add_vline
        annotation parameter — plotly 6.6.0 safe)
      - Direction and pattern name banner top-left

    Args:
        df:            Full OHLCV DataFrame.
        result:        Single PatternResult to visualize.
        pivot_prices:  Alternating pivot close prices.
        pivot_indices: DatetimeIndex for pivots.
        pattern_index: Index for title numbering.

    Returns:
        Plotly Figure — height 850px.
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

    # ── CANDLE WINDOW (20 candles each side) ────────────────────────────
    expanded_context   = 20
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

    window_start = max(0, first_pos - expanded_context)
    window_end   = min(len(df_reset) - 1, last_pos + expanded_context)
    df_window    = (
        df_reset.iloc[window_start: window_end + 1].set_index(date_col)
    )

    fig = go.Figure()

    # ── CANDLESTICK BASE ────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df_window.index,
        open=df_window["open"],
        high=df_window["high"],
        low=df_window["low"],
        close=df_window["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name="Price",
        showlegend=False,
        opacity=0.35,
    ))

    # ── PATTERN LEGS — alternating cyan/green ───────────────────────────
    for seg_idx in range(n - 1):
        seg_color = (
            EXPAND_PATTERN_COLORS["leg_primary"]
            if seg_idx % 2 == 0
            else EXPAND_PATTERN_COLORS["leg_secondary"]
        )
        fig.add_trace(go.Scatter(
            x=[x_dates[seg_idx], x_dates[seg_idx + 1]],
            y=[y_prices[seg_idx], y_prices[seg_idx + 1]],
            mode="lines",
            line=dict(color=seg_color, width=4.0),
            showlegend=False,
            hoverinfo="skip",
        ))

    # ── PIVOT MARKERS + FULL LABELS WITH ARROWHEAD CALLOUTS ─────────────
    for i in range(n):
        lbl      = labels.get(i, str(i))
        px       = y_prices[i]
        xd       = x_dates[i]
        date_str = pd.Timestamp(xd).strftime("%Y-%m-%d")

        pt_color = (
            EXPAND_PATTERN_COLORS["leg_primary"]
            if i % 2 == 0
            else EXPAND_PATTERN_COLORS["leg_secondary"]
        )

        fig.add_trace(go.Scatter(
            x=[xd],
            y=[px],
            mode="markers",
            marker=dict(
                size=20,
                color=pt_color,
                symbol="circle",
                line=dict(
                    color=EXPAND_PATTERN_COLORS["marker_border"],
                    width=3,
                ),
            ),
            showlegend=False,
            hovertemplate=(
                f"<b>Point {lbl}</b><br>"
                f"Price: ${px:,.2f}<br>"
                f"Date: {date_str}<extra></extra>"
            ),
        ))

        # Letter label inside marker
        fig.add_annotation(
            x=xd,
            y=px,
            text=f"<b>{lbl}</b>",
            showarrow=False,
            font=dict(color="#FFFFFF", size=12, family="monospace"),
            bgcolor="rgba(0,0,0,0)",
        )

        # Price + date callout with arrowhead
        ax_offset = 55 if i % 2 == 0 else -55
        ay_offset = -45 if i % 2 == 0 else 45
        fig.add_annotation(
            x=xd,
            y=px,
            text=(
                f"<b>{lbl}</b>  ${px:,.2f}<br>"
                f"<span style='font-size:9px;color:{pt_color}'>"
                f"{date_str}</span>"
            ),
            showarrow=True,
            arrowhead=2,
            arrowsize=1.2,
            arrowwidth=1.8,
            arrowcolor=pt_color,
            ax=ax_offset,
            ay=ay_offset,
            font=dict(color=pt_color, size=11, family="monospace"),
            bgcolor=EXPAND_PATTERN_COLORS["label_bg"],
            bordercolor=pt_color,
            borderwidth=1,
            borderpad=5,
        )

    # ── RATIO ANNOTATIONS — arrowhead callout on each leg midpoint ───────
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

        r_color = (
            EXPAND_PATTERN_COLORS["leg_primary"]
            if idx % 2 == 0
            else EXPAND_PATTERN_COLORS["leg_secondary"]
        )

        fig.add_annotation(
            x=mid_ts,
            y=mid_y,
            text=f"<b>{ratio:.3f}</b>",
            showarrow=True,
            arrowhead=1,
            arrowsize=0.8,
            arrowwidth=1.2,
            arrowcolor=r_color,
            ax=50,
            ay=0,
            font=dict(
                color=EXPAND_PATTERN_COLORS["ratio_label"],
                size=12,
                family="monospace",
            ),
            bgcolor=EXPAND_PATTERN_COLORS["label_bg"],
            bordercolor=EXPAND_PATTERN_COLORS["ratio_label"],
            borderwidth=1,
            borderpad=4,
        )

    # ── PRZ SHADING BOX ─────────────────────────────────────────────────
    d_price: float  = y_prices[-1]
    prz_half: float = d_price * 0.005

    fig.add_hrect(
        y0=d_price - prz_half,
        y1=d_price + prz_half,
        fillcolor=EXPAND_PATTERN_COLORS["prz_fill"],
        line_color=EXPAND_PATTERN_COLORS["prz_border"],
        line_width=1.5,
        line_dash="dot",
        annotation_text=f"PRZ  ${d_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(
            color=EXPAND_PATTERN_COLORS["prz_border"],
            size=12,
            family="monospace",
        ),
    )

    # ── STOP LOSS LINE ──────────────────────────────────────────────────
    sl_price: float = float(result.stop_loss)
    fig.add_hline(
        y=sl_price,
        line_dash="dash",
        line_color=EXPAND_PATTERN_COLORS["sl_line"],
        line_width=2.0,
        annotation_text=f"Stop Loss  ${sl_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(
            color=EXPAND_PATTERN_COLORS["sl_line"],
            size=12,
            family="monospace",
        ),
    )

    # ── D POINT VERTICAL MARKER (annotation-safe) ───────────────────────
    d_date_str: str = pd.Timestamp(x_dates[-1]).strftime("%Y-%m-%d")

    fig.add_vline(
        x=d_date_str,
        line_dash="dot",
        line_color=EXPAND_PATTERN_COLORS["d_vline"],
        line_width=2.0,
        opacity=0.7,
    )
    fig.add_annotation(
        x=d_date_str,
        y=1.0,
        yref="paper",
        text="D — Completion",
        showarrow=False,
        font=dict(
            color=EXPAND_PATTERN_COLORS["d_vline"],
            size=11,
            family="monospace",
        ),
        bgcolor=EXPAND_PATTERN_COLORS["label_bg"],
        bordercolor=EXPAND_PATTERN_COLORS["d_vline"],
        borderwidth=1,
        borderpad=4,
        xanchor="center",
    )

    # ── DIRECTION BANNER ────────────────────────────────────────────────
    dir_color = (
        EXPAND_PATTERN_COLORS["leg_secondary"]
        if result.is_bullish
        else EXPAND_PATTERN_COLORS["sl_line"]
    )
    fig.add_annotation(
        text=(
            f"{direction.upper()} {result.pattern_name.upper()}"
            f"  —  PRZ: ${d_price:,.2f}"
        ),
        xref="paper", yref="paper",
        x=0.01, y=0.99,
        showarrow=False,
        font=dict(color=dir_color, size=14, family="monospace"),
        bgcolor=EXPAND_PATTERN_COLORS["label_bg"],
        bordercolor=dir_color,
        borderwidth=1,
        borderpad=7,
    )

    fig.update_layout(
        template="plotly_dark",
        height=850,
        margin=dict(l=10, r=160, t=65, b=10),
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
                f"Pattern {pattern_index + 1}: {direction} "
                f"{result.pattern_name} — Full Shape View — "
                f"Click and drag to zoom"
            ),
            font=dict(
                color=EXPAND_PATTERN_COLORS["prz_border"],
                size=15,
                family="monospace",
            ),
        ),
    )
    return fig


# ─── PATTERN CARD ──────────────────────────────────────────────────────────

def render_pattern_card(
    result: PatternResult,
    x_dates: List[Any],
) -> None:
    """
    Renders a full analysis card for a single PatternResult.

    Args:
        result:  PatternResult from HarmonicEngine.scan().
        x_dates: Dates corresponding to each pattern point.
    """
    direction  = "Bullish" if result.is_bullish else "Bearish"
    context    = PATTERN_CONTEXT.get(result.pattern_name, {})
    n          = len(result.points)
    labels_map = (
        SHARK_LABELS
        if result.pattern_name == "Shark"
        else POINT_LABELS_MAP.get(n, {i: str(i) for i in range(n)})
    )

    with st.expander(
        f"{direction} {result.pattern_name} — "
        f"D: ${float(result.points[-1]):,.2f} — "
        f"SL: ${float(result.stop_loss):,.2f}",
        expanded=False,
    ):
        col_pts, col_analysis = st.columns([1, 2])

        with col_pts:
            st.markdown("**Pattern Points**")
            for i in range(n):
                lbl   = labels_map.get(i, str(i))
                price = float(result.points[i])
                date  = (
                    pd.Timestamp(x_dates[i]).strftime("%Y-%m-%d")
                    if i < len(x_dates) else "—"
                )
                st.metric(
                    label=f"Point {lbl}  ({date})",
                    value=f"${price:,.2f}",
                )

            st.markdown("---")
            st.markdown("**Risk Level**")
            st.error(f"Stop Loss: ${float(result.stop_loss):,.2f}")
            direction_color = "green" if result.is_bullish else "red"
            st.markdown(f"**Direction:** :{direction_color}[{direction}]")

        with col_analysis:
            st.markdown("**Structure**")
            st.caption(context.get("structure", "See reference file."))

            st.markdown("**What This Pattern Means**")
            st.info(
                context.get("market_meaning", "No interpretation available.")
            )

            st.markdown("**Smart Money Behaviour at This Level**")
            st.warning(
                context.get("smart_money", "No smart money context available.")
            )

            st.markdown("**Invalidation Condition**")
            st.error(
                context.get("invalidation", "See stop loss level above.")
            )


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point for the Harmonic Pattern Audit UI page."""
    # <- NEW [typography]: inject global font CSS on every render
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    st.title(t("ha_title"))
    st.markdown("---")

    st.sidebar.header("Data Configuration")

    ticker: str = st.sidebar.text_input(
        "Ticker Symbol", value="SPY"
    ).upper().strip()

    tf_key: str = st.sidebar.selectbox(
        "Analysis Window",
        list(TF_CONFIG.keys()),
        index=2,
    )
    tf_cfg = TF_CONFIG[tf_key]

    if tf_cfg["intraday_cap"]:
        st.sidebar.caption(
            "Note: yfinance limits 1H and 4H data to approximately "
            "730 days regardless of the 10Y window selected."
        )

    pivot_order: int = st.sidebar.slider(
        "Pivot Sensitivity (order)",
        min_value=2,
        max_value=20,
        value=3 if tf_cfg["intraday_cap"] else 5,
        help=(
            "Lower = more pivots (shorter patterns). "
            "Higher = fewer pivots (macro patterns only)."
        ),
    )

    if st.sidebar.button("Run Detection Scan"):

        engine = HarmonicEngine()

        with st.spinner(f"Fetching {ticker} [{tf_cfg['label']}] data..."):
            try:
                df = fetch_ohlcv(ticker, tf_key)
            except Exception as e:
                logger.error(
                    f"Data fetch failed {ticker} {tf_key}: {e}",
                    exc_info=True,
                )
                st.error(f"Data Fetch Error: {str(e)}")
                st.stop()

        if df.empty:
            st.error(
                f"No data returned for {ticker}. "
                "Verify the ticker symbol and timeframe."
            )
            st.stop()

        with st.spinner("Extracting and enforcing alternating pivots..."):
            try:
                raw_pivots    = find_pivots(df, order=pivot_order)
                alt_pivots    = enforce_alternation(raw_pivots)
                piv_prices: np.ndarray        = alt_pivots["close"].values
                piv_indices: pd.DatetimeIndex = alt_pivots.index

                st.sidebar.caption(
                    f"Raw pivots: {len(raw_pivots)} | "
                    f"Alternating: {len(alt_pivots)}"
                )
            except Exception as e:
                logger.error(f"Pivot extraction failed: {e}", exc_info=True)
                st.error(f"Pivot Extraction Error: {str(e)}")
                st.stop()

        if len(piv_prices) < 6:
            st.warning(
                f"Only {len(piv_prices)} alternating pivots found for "
                f"{ticker} on {tf_cfg['label']}. "
                "Lower pivot sensitivity or select a longer window."
            )
            st.stop()

        with st.spinner("Running harmonic scan..."):
            try:
                results: List[PatternResult] = engine.scan(list(piv_prices))
            except Exception as e:
                logger.error(f"Scan failed: {e}", exc_info=True)
                st.error(f"Detection Engine Failed: {str(e)}")
                st.stop()

        st.success(
            f"{len(results)} pattern(s) detected in {ticker} "
            f"[{tf_cfg['label']}] "
            f"({len(alt_pivots)} alternating pivots scanned)."
        )

        st.subheader(
            f"{ticker} — Full Pattern Overview ({tf_cfg['label']})"
        )

        if results:
            overview_fig = render_harmonic_chart(
                df, ticker, tf_cfg["label"],
                results, piv_prices, piv_indices,
            )
            st.plotly_chart(overview_fig, width="stretch")
        else:
            fig_clean = go.Figure(data=[go.Candlestick(
                x=df.index,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                increasing_line_color="#089981",
                decreasing_line_color="#F23645",
                name=ticker,
            )])
            fig_clean.update_layout(
                template="plotly_dark",
                height=480,
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                xaxis=dict(rangeslider_visible=False, type="date"),
                yaxis=dict(side="right"),
                title=dict(
                    text=f"{ticker} — No Patterns Detected",
                    font=dict(color="#e0e0e0"),
                ),
            )
            st.plotly_chart(fig_clean, width="stretch")
            st.info(
                "No harmonic patterns detected. "
                "Try lowering pivot sensitivity or selecting a longer window."
            )

        if results:
            st.markdown("---")
            st.subheader("Pattern Detail — PRZ Zoom & Full Shape")

            for idx, result in enumerate(results):
                x_dates_r, _ = map_pattern_to_dates(
                    result, piv_prices, piv_indices
                )

                # PRZ zoom chart (10 candles each side)
                prz_fig = render_prz_zoom_chart(
                    df, result, piv_prices, piv_indices, idx
                )
                st.plotly_chart(prz_fig, width="stretch")

                # <- NEW [pattern-expand]: full-shape expanded chart.
                with st.expander(
                    f"Expand Full Pattern Shape — "
                    f"{'Bullish' if result.is_bullish else 'Bearish'} "
                    f"{result.pattern_name} — Click for high-quality view",
                    expanded=False,
                ):
                    st.caption(
                        "Complete pattern shape with ratio annotations at each "
                        "leg, PRZ zone shading, and stop loss level. "
                        "Use the Plotly toolbar (top-right) to zoom, pan, and save."
                    )
                    expanded_fig = render_pattern_expanded(
                        df, result, piv_prices, piv_indices, idx
                    )
                    st.plotly_chart(expanded_fig, width="stretch")

                render_pattern_card(result, x_dates_r)

                if idx < len(results) - 1:
                    st.markdown("---")

        serialisable_results: List[Dict[str, Any]] = []
        for r in results:
            x_dates_r, _ = map_pattern_to_dates(r, piv_prices, piv_indices)
            serialisable_results.append({
                "pattern_name": r.pattern_name,
                "points":       [float(p) for p in r.points],
                "is_bullish":   r.is_bullish,
                "stop_loss":    float(r.stop_loss),
                "d_price":      float(r.points[-1]),
                "x_dates":      [str(d) for d in x_dates_r],
            })

        st.session_state["harm_latest_results"] = {
            "ticker":    ticker,
            "tf_label":  tf_cfg["label"],
            "patterns":  serialisable_results,
            "piv_count": len(alt_pivots),
        }

    else:
        st.info(
            "Configure the ticker and analysis window in the sidebar, "
            "then press **Run Detection Scan**."
        )


if __name__ == "__main__":
    main()