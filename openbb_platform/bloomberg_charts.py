"""
bloomberg_charts.py
═══════════════════════════════════════════════════════════════════════════════
Bloomberg-Grade Chart Library for QuantEdge

COUNCIL MANDATE: "Charts need multi-timeframe, on-chart pattern overlays,
synchronized multi-panel layout, and trade level annotations."

FUNCTIONS:
  1. create_institutional_chart()  — Multi-panel: price + volume + RSI + MACD
  2. add_harmonic_overlay()        — Draw XABCD pattern shape on candlestick chart
  3. add_elliott_overlay()         — Draw wave labels (1-2-3-4-5) on chart
  4. add_trade_levels()            — Entry zone + stop-loss + target levels
  5. create_multi_timeframe()      — Daily + Weekly + Monthly side by side

ALL FUNCTIONS:
  - Use dark Bloomberg theme (#000d1a background)
  - Japanese candlestick style (green #089981 / red #F23645)
  - Y-axis on right side
  - No rangeslider
  - Crosshair cursor (spike lines)
  - ScrollZoom enabled
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any

# ─── STYLE CONSTANTS ──────────────────────────────────────────────────────────

BG_COLOR       = "#000d1a"
GRID_COLOR     = "rgba(255,255,255,0.04)"
TEXT_COLOR     = "#8a9ab0"
TITLE_COLOR    = "#E8E0D0"
CANDLE_UP      = "#089981"
CANDLE_DOWN    = "#F23645"
EMA_COLORS     = {"9": "#FFD700", "21": "#00BFFF", "55": "#FF6B6B"}
SMA_COLORS     = {"20": "#FFD700", "50": "#00BFFF", "200": "#FF6B6B"}
VOLUME_UP      = "rgba(8,153,129,0.4)"
VOLUME_DOWN    = "rgba(242,54,69,0.4)"
RSI_COLOR      = "#AB47BC"
MACD_LINE      = "#00E5FF"
MACD_SIGNAL    = "#FF6B6B"
MACD_HIST_UP   = "rgba(8,153,129,0.6)"
MACD_HIST_DOWN = "rgba(242,54,69,0.6)"

# Harmonic pattern colors
HP_BULLISH     = "#00E676"
HP_BEARISH     = "#FF5252"
HP_LINE        = "rgba(255,215,0,0.8)"
HP_FILL        = "rgba(255,215,0,0.05)"

# Elliott wave colors
EW_IMPULSE     = "#00E5FF"
EW_CORRECTIVE  = "#FFB74D"

# Trade level colors
ENTRY_COLOR    = "#00E5FF"
STOP_COLOR     = "#FF5252"
TARGET_COLOR   = "#00E676"
ZONE_ALPHA     = 0.08


def _base_layout(title: str = "", height: int = 600) -> Dict:
    """Base layout settings for all Bloomberg-grade charts."""
    return dict(
        template="plotly_dark",
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        font=dict(family="'Times New Roman', serif", color=TEXT_COLOR, size=11),
        title=dict(text=title, font=dict(color=TITLE_COLOR, size=16)),
        height=height,
        margin=dict(l=10, r=60, t=50 if title else 20, b=30),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=TEXT_COLOR),
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
        ),
        hovermode="x unified",
    )


def _axis_style(side: str = "right") -> Dict:
    """Standard axis style for Bloomberg look."""
    return dict(
        gridcolor=GRID_COLOR,
        zeroline=False,
        side=side,
        showspikes=True,
        spikemode="across",
        spikethickness=0.5,
        spikecolor="rgba(255,255,255,0.15)",
        spikedash="solid",
    )



# ═══════════════════════════════════════════════════════════════════════════════
# 1. INSTITUTIONAL MULTI-PANEL CHART
#    Price (candlestick + EMAs) + Volume + RSI + MACD — synchronized panels
# ═══════════════════════════════════════════════════════════════════════════════

def create_institutional_chart(
    df: pd.DataFrame,
    ticker: str,
    show_ema: bool = True,
    show_bb: bool = False,
    show_volume: bool = True,
    show_rsi: bool = True,
    show_macd: bool = True,
    ema_periods: List[int] = None,
    rsi_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> go.Figure:
    """
    Creates a Bloomberg-grade multi-panel chart with synchronized x-axis.
    
    Panels (top to bottom):
      1. Price — Japanese candlesticks + EMA 9/21/55 + optional Bollinger Bands
      2. Volume — Color-coded bars (green up, red down)
      3. RSI — 14-period with 70/30 bands
      4. MACD — 12/26/9 with histogram
    
    All panels share x-axis for synchronized scrolling/zooming.
    """
    if ema_periods is None:
        ema_periods = [9, 21, 55]

    # Determine panel count and row heights
    panels = 1  # price always
    row_heights = [0.55]
    if show_volume:
        panels += 1
        row_heights.append(0.12)
    if show_rsi:
        panels += 1
        row_heights.append(0.15)
    if show_macd:
        panels += 1
        row_heights.append(0.18)

    fig = make_subplots(
        rows=panels, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
    )

    # ── Panel 1: Price (Candlesticks + EMAs + BB) ─────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing_line_color=CANDLE_UP, increasing_fillcolor=CANDLE_UP,
        decreasing_line_color=CANDLE_DOWN, decreasing_fillcolor=CANDLE_DOWN,
        name=ticker, showlegend=False,
    ), row=1, col=1)

    # EMAs
    if show_ema:
        for p in ema_periods:
            ema = df["close"].ewm(span=p, adjust=False).mean()
            color = EMA_COLORS.get(str(p), "#FFFFFF")
            fig.add_trace(go.Scatter(
                x=df.index, y=ema, mode="lines",
                line=dict(color=color, width=1.2),
                name=f"EMA {p}", showlegend=True,
            ), row=1, col=1)

    # Bollinger Bands
    if show_bb:
        sma = df["close"].rolling(bb_period).mean()
        std = df["close"].rolling(bb_period).std()
        upper = sma + bb_std * std
        lower = sma - bb_std * std
        fig.add_trace(go.Scatter(x=df.index, y=upper, mode="lines",
            line=dict(color="rgba(171,71,188,0.5)", width=1, dash="dot"),
            name=f"BB Upper", showlegend=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=lower, mode="lines",
            line=dict(color="rgba(171,71,188,0.5)", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(171,71,188,0.05)",
            name=f"BB Lower", showlegend=True), row=1, col=1)

    # ── Panel 2: Volume ───────────────────────────────────────────────────
    current_row = 2
    if show_volume:
        colors = [VOLUME_UP if c >= o else VOLUME_DOWN
                  for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], marker_color=colors,
            name="Volume", showlegend=False,
        ), row=current_row, col=1)
        current_row += 1

    # ── Panel 3: RSI ──────────────────────────────────────────────────────
    if show_rsi:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        fig.add_trace(go.Scatter(
            x=df.index, y=rsi, mode="lines",
            line=dict(color=RSI_COLOR, width=1.5),
            name=f"RSI({rsi_period})", showlegend=True,
        ), row=current_row, col=1)

        # 70/30 bands
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,82,82,0.4)",
                      line_width=0.8, row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,230,118,0.4)",
                      line_width=0.8, row=current_row, col=1)
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(255,82,82,0.05)",
                      line_width=0, row=current_row, col=1)
        fig.add_hrect(y0=0, y1=30, fillcolor="rgba(0,230,118,0.05)",
                      line_width=0, row=current_row, col=1)
        current_row += 1

    # ── Panel 4: MACD ─────────────────────────────────────────────────────
    if show_macd:
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        hist_colors = [MACD_HIST_UP if v >= 0 else MACD_HIST_DOWN for v in histogram]
        fig.add_trace(go.Bar(
            x=df.index, y=histogram, marker_color=hist_colors,
            name="MACD Hist", showlegend=False,
        ), row=current_row, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=macd_line, mode="lines",
            line=dict(color=MACD_LINE, width=1.3),
            name="MACD", showlegend=True,
        ), row=current_row, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=signal_line, mode="lines",
            line=dict(color=MACD_SIGNAL, width=1.3),
            name="Signal", showlegend=True,
        ), row=current_row, col=1)

    # ── Layout ────────────────────────────────────────────────────────────
    layout = _base_layout(f"{ticker} — Institutional Chart", height=700)
    layout["xaxis"] = dict(rangeslider_visible=False, **_axis_style())
    for i in range(1, panels + 1):
        layout[f"yaxis{i if i > 1 else ''}"] = _axis_style("right")

    fig.update_layout(**layout)
    return fig



# ═══════════════════════════════════════════════════════════════════════════════
# 2. HARMONIC PATTERN OVERLAY
#    Draws XABCD shape directly on a price chart with labeled points
# ═══════════════════════════════════════════════════════════════════════════════

def add_harmonic_overlay(
    fig: go.Figure,
    pattern_name: str,
    points: List[float],
    point_dates: List,
    is_bullish: bool,
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """
    Draws a harmonic pattern (XABCD) shape on an existing chart figure.
    
    Args:
        fig:          Existing Plotly figure (typically from create_institutional_chart)
        pattern_name: e.g. "Gartley", "Bat", "Butterfly"
        points:       List of 4-6 price values [X, A, B, C, D] or [A, B, C, D]
        point_dates:  Corresponding datetime indices
        is_bullish:   True = bullish pattern (green), False = bearish (red)
        row, col:     Subplot position
    """
    color = HP_BULLISH if is_bullish else HP_BEARISH
    direction = "Bullish" if is_bullish else "Bearish"
    labels = ["X", "A", "B", "C", "D"][:len(points)]

    # Draw connecting lines
    fig.add_trace(go.Scatter(
        x=list(point_dates),
        y=list(points),
        mode="lines+markers+text",
        line=dict(color=color, width=2, dash="solid"),
        marker=dict(size=10, color=color, symbol="diamond",
                    line=dict(color="white", width=1)),
        text=labels,
        textposition="top center",
        textfont=dict(color=color, size=12, family="monospace"),
        name=f"{direction} {pattern_name}",
        showlegend=True,
    ), row=row, col=col)

    # Fill the pattern shape (XAB triangle + BCD triangle)
    if len(points) >= 5:
        # XAB triangle
        fig.add_trace(go.Scatter(
            x=[point_dates[0], point_dates[1], point_dates[2], point_dates[0]],
            y=[points[0], points[1], points[2], points[0]],
            fill="toself", fillcolor=f"rgba({','.join(['0','230','118'] if is_bullish else ['255','82','82'])},0.06)",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ), row=row, col=col)
        # BCD triangle
        fig.add_trace(go.Scatter(
            x=[point_dates[2], point_dates[3], point_dates[4], point_dates[2]],
            y=[points[2], points[3], points[4], points[2]],
            fill="toself", fillcolor=f"rgba({','.join(['0','230','118'] if is_bullish else ['255','82','82'])},0.06)",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ), row=row, col=col)

    # PRZ level annotation at D point
    if len(points) >= 5:
        fig.add_annotation(
            x=point_dates[-1], y=points[-1],
            text=f"PRZ: {points[-1]:.2f}",
            showarrow=True, arrowhead=2,
            arrowcolor=color, arrowwidth=1.5,
            font=dict(color=color, size=10),
            bgcolor="rgba(0,13,26,0.9)",
            bordercolor=color, borderwidth=1,
            row=row, col=col,
        )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ELLIOTT WAVE OVERLAY
#    Draws wave labels (1-2-3-4-5) on price chart
# ═══════════════════════════════════════════════════════════════════════════════

def add_elliott_overlay(
    fig: go.Figure,
    wave_points: List[float],
    wave_dates: List,
    is_bullish: bool,
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """
    Draws Elliott Wave labels on an existing chart.
    
    Args:
        wave_points: [start, W1, W2, W3, W4, W5] — 6 price values
        wave_dates:  Corresponding datetime indices
        is_bullish:  True = bullish impulse, False = bearish
    """
    color = EW_IMPULSE
    labels = ["0", "1", "2", "3", "4", "5"][:len(wave_points)]

    # Draw impulse lines
    fig.add_trace(go.Scatter(
        x=list(wave_dates),
        y=list(wave_points),
        mode="lines+markers+text",
        line=dict(color=color, width=2.5),
        marker=dict(size=8, color=color, symbol="circle",
                    line=dict(color="white", width=1)),
        text=labels,
        textposition=["bottom center" if i % 2 == 0 else "top center"
                      for i in range(len(labels))],
        textfont=dict(color=color, size=14, family="monospace"),
        name="Elliott Impulse",
        showlegend=True,
    ), row=row, col=col)

    # Wave 3 target annotation (longest wave)
    if len(wave_points) >= 4:
        w3_end = wave_points[3]
        fig.add_annotation(
            x=wave_dates[3], y=w3_end,
            text=f"W3: {w3_end:.2f}",
            showarrow=True, arrowhead=2,
            arrowcolor=EW_IMPULSE, arrowwidth=1.5,
            font=dict(color=EW_IMPULSE, size=10),
            bgcolor="rgba(0,13,26,0.9)",
            bordercolor=EW_IMPULSE, borderwidth=1,
            row=row, col=col,
        )

    return fig



# ═══════════════════════════════════════════════════════════════════════════════
# 4. TRADE LEVEL ANNOTATIONS
#    Entry zone + stop-loss + target levels drawn on chart
# ═══════════════════════════════════════════════════════════════════════════════

def add_trade_levels(
    fig: go.Figure,
    entry_price: float,
    stop_loss: float,
    targets: List[float] = None,
    entry_zone: float = 0,
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """
    Draws trade level annotations on chart: entry zone, stop-loss, target levels.
    Bloomberg-style horizontal lines with labels.
    """
    if targets is None:
        targets = []

    # Entry level
    fig.add_hline(
        y=entry_price, line_dash="solid", line_color=ENTRY_COLOR,
        line_width=1.5, row=row, col=col,
        annotation_text=f"ENTRY {entry_price:.2f}",
        annotation_position="right",
        annotation_font=dict(color=ENTRY_COLOR, size=10),
    )

    # Entry zone (if provided)
    if entry_zone > 0:
        fig.add_hrect(
            y0=entry_price - entry_zone, y1=entry_price + entry_zone,
            fillcolor=f"rgba(0,229,255,{ZONE_ALPHA})",
            line_width=0, row=row, col=col,
        )

    # Stop-loss
    fig.add_hline(
        y=stop_loss, line_dash="dash", line_color=STOP_COLOR,
        line_width=1.5, row=row, col=col,
        annotation_text=f"STOP {stop_loss:.2f}",
        annotation_position="right",
        annotation_font=dict(color=STOP_COLOR, size=10),
    )

    # Risk zone (entry to stop)
    fig.add_hrect(
        y0=min(entry_price, stop_loss), y1=max(entry_price, stop_loss),
        fillcolor=f"rgba(255,82,82,{ZONE_ALPHA})",
        line_width=0, row=row, col=col,
    )

    # Target levels
    target_labels = ["T1", "T2", "T3"]
    for i, tp in enumerate(targets[:3]):
        label = target_labels[i] if i < len(target_labels) else f"T{i+1}"
        fig.add_hline(
            y=tp, line_dash="dot", line_color=TARGET_COLOR,
            line_width=1.2, row=row, col=col,
            annotation_text=f"{label} {tp:.2f}",
            annotation_position="right",
            annotation_font=dict(color=TARGET_COLOR, size=10),
        )

    # Profit zone (entry to first target)
    if targets:
        fig.add_hrect(
            y0=min(entry_price, targets[0]), y1=max(entry_price, targets[0]),
            fillcolor=f"rgba(0,230,118,{ZONE_ALPHA})",
            line_width=0, row=row, col=col,
        )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MULTI-TIMEFRAME CHART
#    Daily + Weekly + Monthly side-by-side — Bloomberg's most iconic view
# ═══════════════════════════════════════════════════════════════════════════════

def create_multi_timeframe(
    ticker: str,
    show_ema: bool = True,
    ema_periods: List[int] = None,
) -> go.Figure:
    """
    Creates a Bloomberg-style multi-timeframe chart: Daily + Weekly + Monthly.
    All three synchronized with the same candlestick style.
    
    Fetches data via yfinance internally.
    """
    import yfinance as yf

    if ema_periods is None:
        ema_periods = [9, 21, 55]

    # Fetch data for all three timeframes
    timeframes = {
        "Daily":   {"period": "6mo", "interval": "1d"},
        "Weekly":  {"period": "2y",  "interval": "1wk"},
        "Monthly": {"period": "5y",  "interval": "1mo"},
    }

    fig = make_subplots(
        rows=1, cols=3,
        shared_yaxes=False,
        horizontal_spacing=0.03,
        subplot_titles=list(timeframes.keys()),
    )

    for i, (tf_name, params) in enumerate(timeframes.items(), 1):
        try:
            df = yf.download(ticker, period=params["period"],
                           interval=params["interval"], progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]

            if df.empty:
                continue

            # Candlesticks
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                increasing_line_color=CANDLE_UP, increasing_fillcolor=CANDLE_UP,
                decreasing_line_color=CANDLE_DOWN, decreasing_fillcolor=CANDLE_DOWN,
                name=tf_name, showlegend=False,
            ), row=1, col=i)

            # EMAs
            if show_ema:
                for p in ema_periods:
                    if len(df) >= p:
                        ema = df["close"].ewm(span=p, adjust=False).mean()
                        color = EMA_COLORS.get(str(p), "#FFFFFF")
                        fig.add_trace(go.Scatter(
                            x=df.index, y=ema, mode="lines",
                            line=dict(color=color, width=1),
                            name=f"EMA {p}" if i == 1 else None,
                            showlegend=(i == 1),
                        ), row=1, col=i)

        except Exception:
            continue

    # Layout
    layout = _base_layout(f"{ticker} — Multi-Timeframe Analysis", height=450)
    for i in range(1, 4):
        xkey = f"xaxis{i}" if i > 1 else "xaxis"
        ykey = f"yaxis{i}" if i > 1 else "yaxis"
        layout[xkey] = dict(rangeslider_visible=False, **_axis_style())
        layout[ykey] = _axis_style("right")

    fig.update_layout(**layout)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SUPPORT/RESISTANCE LEVELS
#    Automatic detection + visualization
# ═══════════════════════════════════════════════════════════════════════════════

def add_support_resistance(
    fig: go.Figure,
    df: pd.DataFrame,
    lookback: int = 60,
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """
    Detects and draws key support/resistance levels on chart.
    Uses rolling window highs/lows with cluster merging.
    """
    if len(df) < lookback:
        return fig

    recent = df.tail(lookback)
    high_val = float(recent["high"].max())
    low_val = float(recent["low"].min())

    # Key levels: recent high, low, midpoint, and 61.8% retracement
    range_size = high_val - low_val
    mid = low_val + 0.5 * range_size
    fib_618 = low_val + 0.618 * range_size
    fib_382 = low_val + 0.382 * range_size

    levels = [
        (high_val, "Resistance", "rgba(255,82,82,0.3)"),
        (fib_618, "61.8% Fib", "rgba(255,215,0,0.25)"),
        (mid, "Midpoint", "rgba(138,154,176,0.2)"),
        (fib_382, "38.2% Fib", "rgba(255,215,0,0.25)"),
        (low_val, "Support", "rgba(0,230,118,0.3)"),
    ]

    for price, label, color in levels:
        fig.add_hline(
            y=price, line_dash="dot", line_color=color.replace("0.3", "0.6").replace("0.25", "0.5").replace("0.2", "0.4"),
            line_width=0.8, row=row, col=col,
            annotation_text=f"{label}: {price:.2f}",
            annotation_position="left",
            annotation_font=dict(color=TEXT_COLOR, size=9),
            annotation_bgcolor="rgba(0,13,26,0.8)",
        )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# PLOTLY CONFIG — standard for all Bloomberg charts
# ═══════════════════════════════════════════════════════════════════════════════

BLOOMBERG_PLOTLY_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
    "displaylogo": False,
    "doubleClick": "reset+autosize",
    "toImageButtonOptions": {"format": "png", "scale": 2},
}
