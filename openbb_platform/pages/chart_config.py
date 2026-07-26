# ui_components/chart_config.py
# Shared TradingView-quality chart configuration for all pages.
# Centralises Japanese candlestick style, zoom/pan behaviour,
# spike lines (crosshair), scrollZoom, and modebar settings.
# Import this module in every page file.

from typing import Any, Dict, Optional
import plotly.graph_objects as go

# ─── JAPANESE CANDLESTICK STYLE ────────────────────────────────────────────
# Authentic Japanese candle: body + wick same color.
# Increasing: #089981 (TradingView green)
# Decreasing: #F23645 (TradingView red)
# Applied to every go.Candlestick() call in the project.

CANDLESTICK_STYLE: Dict[str, Any] = {
    "increasing_line_color":  "#089981",
    "increasing_fillcolor":   "#089981",
    "decreasing_line_color":  "#F23645",
    "decreasing_fillcolor":   "#F23645",
    "line_width":             1,
    "whiskerwidth":           0,
}

# ─── PLOTLY CHART CONFIG ───────────────────────────────────────────────────
# Passed as config= to st.plotly_chart().
# scrollZoom=True  : mousewheel zooms on chart (like TradingView)
# displayModeBar   : always visible (not hidden on mouseout)
# modeBarButtons   : full set including zoom, pan, reset, save
# toImageButtonOptions: high-res PNG export

PLOTLY_CONFIG: Dict[str, Any] = {
    "scrollZoom": True,
    "displayModeBar": True,
    "modeBarButtonsToAdd": [
        "drawline",
        "drawopenpath",
        "eraseshape",
    ],
    "modeBarButtonsToRemove": [],
    "displaylogo": False,
    "toImageButtonOptions": {
        "format": "png",
        "scale": 2,
        "height": None,
        "width": None,
    },
    "doubleClick": "reset+autosize",
}


def get_plotly_config() -> Dict[str, Any]:
    """
    Returns the Plotly config dict for use in st.plotly_chart(config=...).
    All charts in the project must use this config to enable:
      - Scroll wheel zoom (horizontal + vertical independently)
      - Double-click to reset zoom
      - Full modebar with zoom/pan/lasso/box/reset/save
      - High-res PNG export

    Returns:
        Dict suitable for plotly config parameter.
    """
    return dict(PLOTLY_CONFIG)


# ─── AXIS DEFAULTS ─────────────────────────────────────────────────────────

def get_xaxis_config(
    show_ticklabels: bool = True,
    axis_type: str = "date",
) -> Dict[str, Any]:
    """
    Returns the standard x-axis configuration for all charts.

    Features:
      - rangeslider REMOVED (confirmed across project)
      - Spike line enabled — the TradingView vertical crosshair
      - Ultra-subtle grid lines
      - showspikes=True required for crosshair effect

    Args:
        show_ticklabels: Whether to show tick labels (False for sub-panels).
        axis_type:       Plotly axis type string ("date", "-", "linear").

    Returns:
        Dict for xaxis parameter in fig.update_layout().
    """
    return {
        "rangeslider_visible": False,
        "type":                axis_type,
        "gridcolor":           "rgba(128,128,128,0.06)",
        "gridwidth":           1,
        "showgrid":            True,
        "zeroline":            False,
        "showspikes":          True,
        "spikecolor":          "rgba(200,200,200,0.55)",
        "spikethickness":      1,
        "spikedash":           "dot",
        "spikemode":           "across",
        "showticklabels":      show_ticklabels,
        "tickfont":            {"color": "#8a8a8a", "size": 10},
    }


def get_yaxis_config(
    fixed_range: bool = False,
    title_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns the standard y-axis configuration for all charts.

    Features:
      - Side RIGHT (confirmed standard across project)
      - Spike line enabled — the TradingView horizontal crosshair
      - Ultra-subtle grid lines
      - showspikes=True required for crosshair effect

    Args:
        fixed_range:  If True, y-axis zoom is locked (for indicator panels).
        title_text:   Optional axis title text.

    Returns:
        Dict for yaxis parameter in fig.update_layout().
    """
    cfg: Dict[str, Any] = {
        "side":           "right",
        "gridcolor":      "rgba(128,128,128,0.06)",
        "gridwidth":      1,
        "showgrid":       True,
        "zeroline":       False,
        "fixedrange":     fixed_range,
        "showspikes":     True,
        "spikecolor":     "rgba(200,200,200,0.55)",
        "spikethickness": 1,
        "spikedash":      "dot",
        "spikemode":      "across",
        "tickfont":       {"color": "#8a8a8a", "size": 10},
    }
    if title_text is not None:
        cfg["title"] = {
            "text": title_text,
            "font": {"color": "rgba(0,229,255,0.55)", "size": 9},
        }
    return cfg


# ─── LAYOUT DEFAULTS ───────────────────────────────────────────────────────

def get_base_layout(
    height: int = 480,
    title_text: str = "",
    title_color: str = "#e0e0e0",
    title_size: int = 14,
    paper_bgcolor: str = "#0e1117",
    plot_bgcolor: str = "#0e1117",
    margin_r: int = 90,
    show_legend: bool = True,
) -> Dict[str, Any]:
    """
    Returns the base layout dict for all charts in the project.

    Features:
      - hovermode="x unified" — TradingView-style unified tooltip
      - dragmode="zoom"       — default interaction is zoom not pan
      - spike lines on both axes (set in axis configs)
      - Dark background matching existing terminal theme
      - Legend positioned at top-left in horizontal orientation
        for main charts, hidden for sub-panels

    Args:
        height:        Chart height in pixels.
        title_text:    Chart title string.
        title_color:   Title font color hex.
        title_size:    Title font size.
        paper_bgcolor: Outer background color.
        plot_bgcolor:  Inner plot area background color.
        margin_r:      Right margin for axis annotations.
        show_legend:   Whether to show the legend.

    Returns:
        Dict for fig.update_layout(**dict).
    """
    layout: Dict[str, Any] = {
        "template":   "plotly_dark",
        "height":     height,
        "hovermode":  "x unified",
        "dragmode":   "zoom",
        "margin":     {"l": 10, "r": margin_r, "t": 50, "b": 10},
        "paper_bgcolor": paper_bgcolor,
        "plot_bgcolor":  plot_bgcolor,
        "showlegend":    show_legend,
        "hoverdistance": 25,
        "spikedistance": -1,
    }

    if title_text:
        layout["title"] = {
            "text": title_text,
            "font": {
                "color":  title_color,
                "size":   title_size,
                "family": "monospace",
            },
        }

    if show_legend:
        layout["legend"] = {
            "bgcolor":      "rgba(14,17,23,0.85)",
            "bordercolor":  "rgba(128,128,128,0.30)",
            "borderwidth":  1,
            "font":         {"color": "#e0e0e0", "size": 9},
            "orientation":  "h",
            "yanchor":      "bottom",
            "y":            1.01,
            "xanchor":      "left",
            "x":            0,
        }

    return layout


def apply_chart_defaults(
    fig: go.Figure,
    height: int = 480,
    title_text: str = "",
    title_color: str = "#e0e0e0",
    title_size: int = 14,
    paper_bgcolor: str = "#0e1117",
    plot_bgcolor: str = "#0e1117",
    margin_r: int = 90,
    show_legend: bool = True,
    xaxis_show_ticklabels: bool = True,
    yaxis_fixed_range: bool = False,
    yaxis_title: Optional[str] = None,
) -> go.Figure:
    """
    Applies the full TradingView-quality chart defaults to a Plotly figure.
    Call this AFTER all traces have been added and AFTER any custom
    update_layout() calls in the render functions — or as a base call
    that the render function then extends with pattern-specific annotations.

    This is the single function that enforces:
      - Spike lines (crosshair)
      - hovermode="x unified"
      - dragmode="zoom"
      - Japanese candlestick axis styling
      - Dark background
      - Legend positioning

    Args:
        fig:                      Plotly Figure to modify in-place.
        height:                   Chart height pixels.
        title_text:               Chart title.
        title_color:              Title color hex.
        title_size:               Title font size.
        paper_bgcolor:            Outer background.
        plot_bgcolor:             Inner background.
        margin_r:                 Right margin px.
        show_legend:              Show legend toggle.
        xaxis_show_ticklabels:    Show x-axis tick labels.
        yaxis_fixed_range:        Lock y-axis zoom.
        yaxis_title:              Optional y-axis label.

    Returns:
        The same go.Figure with defaults applied (mutated in-place).
    """
    layout = get_base_layout(
        height=height,
        title_text=title_text,
        title_color=title_color,
        title_size=title_size,
        paper_bgcolor=paper_bgcolor,
        plot_bgcolor=plot_bgcolor,
        margin_r=margin_r,
        show_legend=show_legend,
    )

    layout["xaxis"] = get_xaxis_config(
        show_ticklabels=xaxis_show_ticklabels,
        axis_type="date",
    )
    layout["yaxis"] = get_yaxis_config(
        fixed_range=yaxis_fixed_range,
        title_text=yaxis_title,
    )

    fig.update_layout(**layout)
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
    Shows PRZ_CANDLE_CONTEXT (10) candles before and after the pattern.
    Japanese candlestick base (mandatory).

    Features:
      - Candlestick window 10 candles each side
      - Pattern zigzag with point labels + date + price
      - Ratio annotation on each leg midpoint
      - PRZ shading box at D completion
      - Stop loss horizontal line
      - D-point vertical marker (annotation-safe — no add_vline annotation)

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

    # ── CANDLE WINDOW ───────────────────────────────────────────────────
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

    # ── JAPANESE CANDLESTICK BASE (mandatory) ───────────────────────────
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

    # ── PATTERN ZIGZAG WITH LABELS ───────────────────────────────────────
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
            size=14, color=color, symbol="circle",
            line=dict(color="#000d1a", width=2),
        ),
        text=point_text,
        textposition="top center",
        textfont=dict(color=color, size=11, family="monospace"),
        name=f"{direction} {result.pattern_name}",
        showlegend=True,
    ))

    # ── RATIO ANNOTATIONS ON EACH LEG MIDPOINT ──────────────────────────
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
            bgcolor="rgba(0,13,26,0.85)",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
        )

    # ── PRZ SHADING BOX ─────────────────────────────────────────────────
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

    # ── STOP LOSS LINE ───────────────────────────────────────────────────
    sl_price: float = float(result.stop_loss)
    fig.add_hline(
        y=sl_price,
        line_dash="dash",
        line_color="#FF5252",
        line_width=1.8,
        annotation_text=f"Stop Loss: ${sl_price:,.2f}",
        annotation_position="right",
        annotation_font=dict(color="#FF5252", size=11),
    )

    # ── D POINT VERTICAL MARKER (annotation-safe) ───────────────────────
    # add_vline() WITHOUT annotation params — plotly 6.6.0 fix confirmed.
    # Label via separate add_annotation() which does not call _mean().
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
        font=dict(color=color, size=10, family="monospace"),
        bgcolor="rgba(0,13,26,0.85)",
        bordercolor=color,
        borderwidth=1,
        borderpad=3,
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
                f"(±{PRZ_CANDLE_CONTEXT} candles)"
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
    Renders a full-size 750px expanded Elliott Wave chart for the scanner page.
    Japanese candlestick base (mandatory, low opacity for context).

    Features:
      - Motive legs (0→1, 2→3) in cyan, corrective (1→2, 3→4) in green
      - Each pivot: large marker + wave label + arrowhead callout date+price
      - Fibonacci retracement grid on W1 range with angled callout lines
      - W3 target zone shaded (1.618 + 2.618)
      - W4 support level (0.382 × W3)
      - Invalidation line in red
      - W2 retrace annotation
      - Phase banner top-left

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

    # ── JAPANESE CANDLESTICK BASE (mandatory, low opacity) ──────────────
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
        opacity=0.28,
    ))

    # ── WAVE LEGS — alternating cyan/green ──────────────────────────────
    for seg in range(len(x_ew) - 1):
        seg_color = (
            EW_COLORS["motive"]
            if seg % 2 == 0
            else EW_COLORS["corrective"]
        )
        fig.add_trace(go.Scatter(
            x=[x_ew[seg], x_ew[seg + 1]],
            y=[y_ew[seg], y_ew[seg + 1]],
            mode="lines",
            line=dict(color=seg_color, width=3.5),
            showlegend=False,
            hoverinfo="skip",
        ))

    # ── PIVOT MARKERS + ARROWHEAD CALLOUTS ──────────────────────────────
    for i in range(len(x_ew)):
        lbl      = wave_labels[i]
        px       = y_ew[i]
        xd       = x_ew[i]
        date_str = pd.Timestamp(xd).strftime("%Y-%m-%d")
        pt_color = (
            EW_COLORS["motive"]
            if i % 2 == 0
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

        # Letter label inside marker
        fig.add_annotation(
            x=xd, y=px,
            text=f"<b>{lbl}</b>",
            showarrow=False,
            font=dict(color="#FFFFFF", size=11, family="monospace"),
            bgcolor="rgba(0,0,0,0)",
        )

        # Price + date callout with arrowhead
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

    # ── FIBONACCI RETRACEMENT GRID (W1 range) ───────────────────────────
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

        # Angled callout line from W1 toward W2 at this fib level
        if len(x_ew) >= 3:
            fig.add_shape(
                type="line",
                x0=x_ew[1], y0=float(pts[1]),
                x1=x_ew[2], y1=fib_px,
                line=dict(color=lc, width=0.8, dash="dot"),
                opacity=0.30,
            )

    # ── W4 SUPPORT LEVEL (0.382 × W3) ───────────────────────────────────
    w4s: float = wave["wave4_support"]
    fig.add_hline(
        y=w4s, line_dash="dashdot",
        line_color=EW_COLORS["fib_618"], line_width=1.5,
        annotation_text=f"  W4 Support (0.382×W3)  ${w4s:,.2f}",
        annotation_position="right",
        annotation_font=dict(
            color=EW_COLORS["fib_618"], size=10, family="monospace"
        ),
    )

    # ── W3 TARGET ZONE ───────────────────────────────────────────────────
    t1618: float = wave["targets"]["target_1618"]
    t2618: float = wave["targets"]["target_2618"]

    fig.add_hrect(
        y0=min(t1618, t2618), y1=max(t1618, t2618),
        fillcolor=EW_COLORS["target_zone"], line_width=0,
    )
    for t_val, t_lbl in [(t1618, "W3×1.618"), (t2618, "W3×2.618")]:
        fig.add_hline(
            y=t_val, line_dash="dash",
            line_color=EW_COLORS["target_line"], line_width=2.0,
            annotation_text=f"  {t_lbl}  ${t_val:,.2f}",
            annotation_position="right",
            annotation_font=dict(
                color=EW_COLORS["target_line"], size=11, family="monospace"
            ),
        )

    # ── INVALIDATION LINE ────────────────────────────────────────────────
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

    # ── W2 RETRACE ANNOTATION ────────────────────────────────────────────
    w2_ratio: float = wave["w2"].get("ratio", 0.0)
    w2_ideal: bool  = wave["w2"].get("is_ideal", False)
    w2_lbl: str     = (
        f"W2 Retrace: {w2_ratio:.3f}  (Ideal 0.500–0.618)"
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

    # ── PHASE BANNER ─────────────────────────────────────────────────────
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
    Renders the complete live analysis panel.
    All values computed from live fetched data — no hardcoded levels.

    Sections:
      1. Current Price Summary
      2. Elliott Wave Status
      3. Harmonic Pattern Signals
      4. Indicator Readings (EMA/SMA crosses, RSI, MACD, EWO)
      5. Volume Profile Levels
      6. Market Structure Status
      7. Forward Projections

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
    price_change:  float = current_close - prev_close
    change_pct:    float = (
        (price_change / prev_close * 100.0)
        if abs(prev_close) > 1e-10 else 0.0
    )
    current_date: str = pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d %H:%M")

    # ── SECTION 1 — CURRENT PRICE ────────────────────────────────────────
    st.markdown("#### Current Price")
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

    # ── SECTION 2 — ELLIOTT WAVE STATUS ─────────────────────────────────
    st.markdown("#### Elliott Wave Status")

    if wave is not None:
        col_ew1, col_ew2, col_ew3, col_ew4 = st.columns(4)

        direction_str: str = "Bullish" if wave["is_bullish"] else "Bearish"
        w4_status: str = (
            "Complete — W5 Watch"
            if wave["w4"]["is_valid"]
            else "W2/W4 Active"
        )
        w2_str: str = (
            f"{wave['w2']['ratio']:.3f} (Ideal)"
            if wave["w2"]["is_ideal"]
            else f"{wave['w2']['ratio']:.3f}"
        )

        with col_ew1:
            st.metric(label="Direction",    value=direction_str)
            st.metric(label="W2 Retrace",   value=w2_str)
        with col_ew2:
            st.metric(label="Phase",        value=w4_status)
            st.metric(
                label="Invalidation",
                value=f"${wave['invalidation']:,.2f}",
            )
        with col_ew3:
            t1618: float = wave["targets"]["target_1618"]
            dist_1618: float = (
                (t1618 / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )
            st.metric(
                label="W3 Target ×1.618",
                value=f"${t1618:,.2f}",
                delta=f"{dist_1618:+.1f}% from current",
            )
        with col_ew4:
            t2618: float = wave["targets"]["target_2618"]
            dist_2618: float = (
                (t2618 / current_close - 1.0) * 100.0
                if current_close > 1e-10 else 0.0
            )
            st.metric(
                label="W3 Target ×2.618",
                value=f"${t2618:,.2f}",
                delta=f"{dist_2618:+.1f}% from current",
            )

        if wave["w4"]["is_valid"]:
            st.success("Rule 3 PASS — W4 has not entered W1 territory.")
        else:
            st.error(
                f"Rule 3 VIOLATION — W4 overlapped W1 by "
                f"${wave['w4']['overlap_depth']:.2f}. "
                "Structure may be a diagonal."
            )

        st.info(
            f"W4 Support Level (0.382 × W3): "
            f"**${wave['wave4_support']:,.2f}**"
        )

    else:
        st.warning(
            "No valid Elliott Wave impulse detected in the 90-day window. "
            "Try lowering pivot sensitivity."
        )

    st.markdown("---")

    # ── SECTION 3 — HARMONIC PATTERN SIGNALS ────────────────────────────
    st.markdown("#### Harmonic Pattern Signals")

    if len(harm_results) > 0:

        def _d_date_key(r: PatternResult) -> pd.Timestamp:
            """Sort key: most recent D-point date."""
            xd, _ = map_pattern_to_dates(r, piv_prices, piv_indices)
            return pd.Timestamp(xd[-1]) if xd else pd.Timestamp.min

        sorted_results = sorted(
            harm_results, key=_d_date_key, reverse=True
        )

        for r in sorted_results[:6]:
            xd, yd    = map_pattern_to_dates(r, piv_prices, piv_indices)
            d_price   = float(yd[-1]) if yd else 0.0
            d_date    = (
                pd.Timestamp(xd[-1]).strftime("%Y-%m-%d")
                if xd else "—"
            )
            direction = "Bullish" if r.is_bullish else "Bearish"
            dc        = "green" if r.is_bullish else "red"
            dist_pct  = (
                abs(d_price - current_close) / current_close * 100.0
                if current_close > 1e-10 else 0.0
            )

            col_h1, col_h2, col_h3, col_h4 = st.columns(4)
            with col_h1:
                st.markdown(
                    f":{dc}[**{direction} {r.pattern_name}**]"
                )
                st.caption(f"D date: {d_date}")
            with col_h2:
                st.metric(label="PRZ (D price)", value=f"${d_price:,.2f}")
            with col_h3:
                st.metric(
                    label="Distance from current",
                    value=f"{dist_pct:.2f}%",
                )
            with col_h4:
                st.metric(
                    label="Stop Loss",
                    value=f"${float(r.stop_loss):,.2f}",
                )
    else:
        st.info(
            "No harmonic patterns detected in the 90-day window. "
            "Try lowering pivot sensitivity."
        )

    st.markdown("---")

    # ── SECTION 4 — INDICATOR READINGS ──────────────────────────────────
    st.markdown("#### Indicator Readings")

    col_i1, col_i2, col_i3 = st.columns(3)

    with col_i1:
        st.markdown("**Moving Averages**")

        for period, key in [
            (9,   "ema_9"),
            (21,  "ema_21"),
            (55,  "ema_55"),
            (20,  "sma_20"),
            (50,  "sma_50"),
            (200, "sma_200"),
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

        # EMA 9/21 cross signal
        e9_cur  = float(indicators["ema_9"].iloc[-1])
        e21_cur = float(indicators["ema_21"].iloc[-1])
        e9_prv  = float(indicators["ema_9"].iloc[-2])  if len(df) > 1 else e9_cur
        e21_prv = float(indicators["ema_21"].iloc[-2]) if len(df) > 1 else e21_cur

        if e9_prv <= e21_prv and e9_cur > e21_cur:
            st.markdown(
                ":green[**EMA 9/21 BULLISH CROSS — just formed**]"
            )
        elif e9_prv >= e21_prv and e9_cur < e21_cur:
            st.markdown(
                ":red[**EMA 9/21 BEARISH CROSS — just formed**]"
            )
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
            ewo_dir: str   = "Rising" if ewo_cur > ewo_prv else "Falling"
            ewo_tc:  str   = "green"  if ewo_cur >= 0.0 else "red"

            st.metric(
                label=f"EWO (SMA{EWO_FAST}/SMA{EWO_SLOW})",
                value=f"{ewo_cur:,.4f}",
                delta=ewo_dir,
            )
            st.markdown(
                f":{ewo_tc}[EWO "
                f"{'Positive — bullish momentum' if ewo_cur >= 0.0 else 'Negative — bearish momentum'}"
                f"]"
            )

            # EWO wave phase interpretation
            ewo_abs_max: float = float(ewo_clean.abs().max())
            ewo_peak_v:  float = float(
                ewo_clean.iloc[int(ewo_clean.abs().values.argmax())]
            )
            if (
                ewo_abs_max > 1e-10
                and abs(ewo_cur) < abs(ewo_peak_v) * 0.50
                and ewo_peak_v > 0.0
            ):
                st.caption(
                    "EWO declining from peak — "
                    "possible W4 or W5 territory."
                )
            elif ewo_abs_max > 1e-10 and abs(ewo_cur) >= abs(ewo_peak_v) * 0.90:
                st.caption(
                    "EWO near peak — possible Wave 3 in progress."
                )

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

        st.metric(
            label=f"MACD Line ({MACD_FAST}/{MACD_SLOW})",
            value=f"{macd_cur:,.4f}",
        )
        st.metric(
            label=f"Signal Line ({MACD_SIGNAL})",
            value=f"{signal_cur:,.4f}",
        )
        st.metric(
            label="Histogram",
            value=f"{hist_cur:,.4f}",
            delta=f"{hist_cur - hist_prv:+.4f}",
        )

        if macd_prv <= signal_prv and macd_cur > signal_cur:
            st.markdown(
                ":green[**MACD BULLISH CROSS — just formed**]"
            )
        elif macd_prv >= signal_prv and macd_cur < signal_cur:
            st.markdown(
                ":red[**MACD BEARISH CROSS — just formed**]"
            )
        elif macd_cur > signal_cur:
            st.markdown(":green[MACD above Signal (bullish)]")
        else:
            st.markdown(":red[MACD below Signal (bearish)]")

        hist_tc: str  = "green" if hist_cur >= 0.0 else "red"
        expanding_str = (
            "Expanding"
            if abs(hist_cur) > abs(hist_prv)
            else "Contracting"
        )
        st.markdown(f":{hist_tc}[Histogram {expanding_str}]")

    st.markdown("---")

    # ── SECTION 5 — VOLUME PROFILE ───────────────────────────────────────
    st.markdown("#### Volume Profile — 90-Day Fixed Range")

    if vp is not None and vp["total_volume"] > 1e-10:
        col_vp1, col_vp2, col_vp3, col_vp4 = st.columns(4)

        poc_dist: float = (
            abs(current_close - vp["poc"]) / current_close * 100.0
            if current_close > 1e-10 else 0.0
        )
        in_va: bool = vp["val"] <= current_close <= vp["vah"]

        with col_vp1:
            st.metric(
                label="POC (Point of Control)",
                value=f"${vp['poc']:,.2f}",
                delta=f"{poc_dist:.2f}% from current",
            )
        with col_vp2:
            st.metric(
                label="VAH (Value Area High 70%)",
                value=f"${vp['vah']:,.2f}",
            )
        with col_vp3:
            st.metric(
                label="VAL (Value Area Low 70%)",
                value=f"${vp['val']:,.2f}",
            )
        with col_vp4:
            va_status: str = (
                "Inside Value Area"
                if in_va
                else "Outside Value Area"
            )
            va_tc: str = "green" if in_va else "red"
            st.metric(label="Current vs Value Area", value=va_status)
            st.markdown(
                f":{va_tc}[Price is **{va_status}** "
                f"(VAL ${vp['val']:,.2f} — VAH ${vp['vah']:,.2f})]"
            )

        st.caption(
            f"Volume Profile: {VP_NUM_BINS} bins · "
            f"Value Area = {VP_VALUE_AREA_PCT * 100:.0f}% · "
            f"Total Volume: {vp['total_volume']:,.0f}"
        )
    else:
        st.info("Volume Profile not available (insufficient volume data).")

    st.markdown("---")

    # ── SECTION 6 — MARKET STRUCTURE ─────────────────────────────────────
    st.markdown("#### Market Structure")

    if ms is not None:
        trend_tc: str = (
            "green" if ms["current_trend"] == "bullish"
            else "red" if ms["current_trend"] == "bearish"
            else "blue"
        )
        st.markdown(
            f"**Current Trend:** :{trend_tc}[{ms['current_trend'].upper()}]  "
            f"| Swing Points: **{len(ms['swing_points'])}**  "
            f"| Structure Events: **{len(ms['structure_events'])}**"
        )

        if ms["structure_events"]:
            last_evt = ms["structure_events"][-1]
            evt_tc: str = (
                "green"
                if last_evt["direction"] == "bullish"
                else "red"
            )
            st.markdown(
                f"**Most Recent:** :{evt_tc}["
                f"**{last_evt['event_type']}** "
                f"({last_evt['direction'].upper()})] "
                f"at ${last_evt['price']:,.2f} on "
                f"{pd.Timestamp(last_evt['date']).strftime('%Y-%m-%d')} — "
                f"broke level ${last_evt['level']:,.2f}"
            )

        if ms["swing_points"]:
            recent_swings = sorted(
                ms["swing_points"],
                key=lambda s: s["index"],
                reverse=True,
            )[:4]
            sw_cols = st.columns(len(recent_swings))
            for sw_col, sp in zip(sw_cols, recent_swings):
                sp_tc: str = (
                    "green"
                    if sp["label"] in ("HH", "HL")
                    else "red"
                )
                with sw_col:
                    st.metric(
                        label=f":{sp_tc}[{sp['label']}]",
                        value=f"${sp['price']:,.2f}",
                    )
                    st.caption(
                        pd.Timestamp(sp["date"]).strftime("%Y-%m-%d")
                    )
    else:
        st.info("Market Structure analysis not available.")

    st.markdown("---")

    # ── SECTION 7 — FORWARD PROJECTIONS ─────────────────────────────────
    st.markdown("#### Forward Projections")

    col_fwd1, col_fwd2 = st.columns(2)

    with col_fwd1:
        st.markdown("**Elliott Wave Projections**")
        if wave is not None:
            projections = [
                ("W3 Target (1.618×W1)",  wave["targets"]["target_1618"], "Target"),
                ("W3 Target (2.618×W1)",  wave["targets"]["target_2618"], "Target"),
                ("W4 Support (0.382×W3)", wave["wave4_support"],          "Support"),
                ("Invalidation Level",    wave["invalidation"],           "Risk"),
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
                harm_results, key=_d_date_key, reverse=True
            )[:4]
            for r in display_results:
                xd, yd  = map_pattern_to_dates(r, piv_prices, piv_indices)
                d_price = float(yd[-1]) if yd else 0.0
                dist    = (
                    (d_price / current_close - 1.0) * 100.0
                    if current_close > 1e-10 else 0.0
                )
                dc      = "green" if r.is_bullish else "red"
                dir_str = "Bull" if r.is_bullish else "Bear"
                st.markdown(
                    f":{dc}[**{dir_str} {r.pattern_name}**] "
                    f"PRZ: ${d_price:,.2f} "
                    f"({dist:+.1f}%) · SL: ${float(r.stop_loss):,.2f}"
                )
        else:
            st.caption("No harmonic patterns detected.")

    # Bollinger Band context
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

        col_bb1, col_bb2, col_bb3 = st.columns(3)
        with col_bb1:
            st.metric(
                label=f"BB Upper ({BB_PERIOD})",
                value=f"${bb_upper_val:,.2f}",
            )
        with col_bb2:
            st.metric(
                label=f"BB Mid ({BB_PERIOD})",
                value=f"${bb_mid_val:,.2f}",
            )
        with col_bb3:
            st.metric(
                label=f"BB Lower ({BB_PERIOD})",
                value=f"${bb_lower_val:,.2f}",
            )
        st.markdown(bb_msg)
        st.caption(
            f"Band Width: ${bb_upper_val - bb_lower_val:,.2f}"
        )


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Main entry point for the 3-Month Scanner page.
    Orchestrates all data fetching, computation, and rendering.
    All values computed from live data — nothing hardcoded.
    """
    st.title("3-Month Scanner")
    st.caption(
        "Japanese candlesticks · Elliott Wave · Harmonic Patterns · "
        "EWO · Volume Profile · Market Structure · "
        "EMA/SMA/BB/RSI/MACD"
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
        index=2,   # Default: Daily
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

    show_ema: bool = st.sidebar.checkbox("EMA 9/21/55",       value=True)
    show_sma: bool = st.sidebar.checkbox("SMA 20/50/200",     value=True)
    show_bb:  bool = st.sidebar.checkbox("Bollinger Bands",   value=True)
    show_ew:  bool = st.sidebar.checkbox("Elliott Wave",      value=True)
    show_hp:  bool = st.sidebar.checkbox("Harmonic Patterns", value=True)
    show_vp:  bool = st.sidebar.checkbox("Volume Profile",    value=True)
    show_ms:  bool = st.sidebar.checkbox("Market Structure",  value=True)

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
        return

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
            return

    if df.empty:
        st.error(
            f"No data returned for {ticker} on {tf_cfg['label']}. "
            "Verify the ticker symbol."
        )
        return

    if len(df) < max(EWO_SLOW, BB_PERIOD, SMA_PERIODS[-1]) + 5:
        st.warning(
            f"Only {len(df)} candles available for {ticker} on "
            f"{tf_cfg['label']}. Some indicators may be incomplete. "
            "Consider switching to a shorter timeframe."
        )

    # ── INDICATORS ───────────────────────────────────────────────────────
    with st.spinner("Computing indicators..."):
        indicators: Dict[str, pd.Series] = compute_indicators(df)

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
    wave_phase: str

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
        st.metric(
            label=f"{ticker} Current",
            value=f"${current_close:,.2f}",
        )
    with col_s2:
        st.metric(label="Timeframe", value=tf_cfg["label"])
    with col_s3:
        st.metric(label="EW Phase",  value=wave_phase)
    with col_s4:
        st.metric(
            label="Patterns Detected",
            value=str(len(harm_results)),
        )

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
        f"Elliott Wave Oscillator — SMA({EWO_FAST}) − SMA({EWO_SLOW})"
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
        st.caption(
            f"Most recent: "
            f"{'Bullish' if harm_results[-1].is_bullish else 'Bearish'} "
            f"{harm_results[-1].pattern_name} · "
            f"±{PRZ_CANDLE_CONTEXT} candles"
        )
        st.plotly_chart(
            render_prz_zoom_chart(
                df,
                harm_results[-1],
                piv_prices,
                piv_indices,
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