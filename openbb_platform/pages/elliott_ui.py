# pages/elliott_ui.py
# <- FIXED [Gate 2c ERROR-B]: fetch_ohlcv resample_1y branch.
#    df.index = pd.to_datetime(df.index) applied before df.resample("YE")
#    and df.resample("4h") to ensure DatetimeIndex.
#    OpenBB .to_df() may return a plain Index — resample() requires DatetimeIndex.

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import logging
from translations import t, inject_rtl_css  # <- NEW [i18n]
import datetime
import sys
import os
from typing import Dict, Any, List

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
    from engine.structure.swings import find_pivots
except ImportError as e:
    st.error(f"Critical Import Error: Swings engine failed. {e}")
    st.stop()

try:
    from openbb import obb
except ImportError as e:
    st.error(f"Critical Import Error: OpenBB failed. {e}")
    st.stop()

logger = logging.getLogger("ElliottUI")

st.set_page_config(page_title="Elliott Wave Terminal", layout="wide")

# ─── CONSTANTS ─────────────────────────────────────────────────────────────

# Fibonacci retracement levels — user-confirmed 2026-03-18.
# Source: Frost & Prechter Elliott Wave Principle.
FIB_RETRACEMENT_LEVELS: List[float] = [0.236, 0.382, 0.500, 0.618, 0.786]

FIB_COLORS: Dict[float, str] = {
    0.236: "rgba(255,255,255,0.25)",
    0.382: "rgba(255,165,0,0.45)",
    0.500: "rgba(255,255,0,0.45)",
    0.618: "rgba(0,255,136,0.55)",
    0.786: "rgba(255,80,80,0.55)",
}

# TF_CONFIG — interval strings confirmed valid for OpenBB 4.7.1 yfinance.
# Valid enum: ['1m','2m','5m','15m','30m','60m','90m','1h','1d','5d','1W','1M','1Q']
TF_CONFIG: Dict[str, Dict[str, Any]] = {
    "1H": {
        "interval":     "1h",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        None,
        "start_days":   59,
        "intraday_cap": True,
        "label":        "1-Hour",
    },
    "4H": {
        "interval":     "1h",
        "resample_4h":  True,
        "resample_1y":  False,
        "years":        None,
        "start_days":   59,
        "intraday_cap": True,
        "label":        "4-Hour",
    },
    "1D": {
        "interval":     "1d",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "start_days":   None,
        "intraday_cap": False,
        "label":        "Daily",
    },
    "1W": {
        "interval":     "1W",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "start_days":   None,
        "intraday_cap": False,
        "label":        "Weekly",
    },
    "1M": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  False,
        "years":        10,
        "start_days":   None,
        "intraday_cap": False,
        "label":        "Monthly",
    },
    "1Y": {
        "interval":     "1M",
        "resample_4h":  False,
        "resample_1y":  True,
        "years":        10,
        "start_days":   None,
        "intraday_cap": False,
        "label":        "Yearly",
    },
}

WAVE_COLORS: Dict[str, str] = {
    "motive":     "#00E5FF",
    "corrective": "#FF6B6B",
    "target":     "rgba(0,229,255,0.12)",
    "fib_box":    "rgba(255,215,0,0.07)",
}


# ─── DATA FETCH ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_ohlcv(ticker: str, tf_key: str) -> pd.DataFrame:
    """
    Fetches OHLCV data from OpenBB yfinance provider.
    Applies 4H or Yearly resampling in pandas where required.
    Ensures DatetimeIndex before any resample operation.

    Args:
        ticker: Equity symbol string.
        tf_key: Key from TF_CONFIG.

    Returns:
        pd.DataFrame with OHLCV columns and DatetimeIndex.
    """
    cfg = TF_CONFIG[tf_key]

    if cfg["start_days"] is not None:
        start_date = (
            datetime.date.today()
            - datetime.timedelta(days=cfg["start_days"])
        ).strftime("%Y-%m-%d")
    else:
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
    # OpenBB .to_df() may return a plain Index. pandas resample() requires
    # DatetimeIndex. pd.to_datetime() is idempotent on existing DatetimeIndex.
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


# ─── CHART RENDERERS ───────────────────────────────────────────────────────

def render_price_chart(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
) -> go.Figure:
    """
    Renders a TradingView-style dark candlestick chart.
    Timeframe label shown in chart title.

    Args:
        df:       OHLCV DataFrame.
        ticker:   Symbol string.
        tf_label: Timeframe label for chart title.

    Returns:
        Plotly Figure.
    """
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name=ticker,
        showlegend=False,
    )])
    fig.update_layout(
        template="plotly_dark",
        height=480,
        margin=dict(l=10, r=80, t=40, b=10),
        xaxis=dict(
            rangeslider_visible=False,
            gridcolor="rgba(128,128,128,0.1)",
            type="date",
        ),
        yaxis=dict(
            side="right",
            gridcolor="rgba(128,128,128,0.1)",
            fixedrange=False,
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        title=dict(
            text=f"{ticker} — Price ({tf_label})",
            font=dict(color="#e0e0e0", size=14),
        ),
    )
    return fig


def render_wave_chart(
    df: pd.DataFrame,
    ticker: str,
    tf_label: str,
    pts: np.ndarray,
    pivot_dates: pd.DatetimeIndex,
    w2_result: Dict[str, Any],
    w4_result: Dict[str, Any],
    targets: Dict[str, float],
    impulse_result: Dict[str, Any],
) -> go.Figure:
    """
    Renders a dedicated Elliott Wave annotation chart.
    Draws wave zigzag, Fibonacci retracement grid (0.236/0.382/0.500/0.618/0.786),
    Wave 3 target zone, invalidation level, and phase annotation.

    Args:
        df:            Full OHLCV DataFrame.
        ticker:        Symbol string.
        tf_label:      Timeframe label.
        pts:           Array of 5 pivot close prices.
        pivot_dates:   DatetimeIndex aligned with pts.
        w2_result:     Output of validate_wave_2().
        w4_result:     Output of validate_wave_4().
        targets:       Output of project_wave_3().
        impulse_result:Output of ElliottEngine.validate_impulse().

    Returns:
        Plotly Figure.
    """
    is_bullish: bool = float(pts[1]) > float(pts[0])

    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name=ticker,
        showlegend=False,
        opacity=0.45,
    )])

    # ── WAVE ZIGZAG LINE ────────────────────────────────────────────────
    wave_labels = ["0", "1", "2", "3", "4"]
    wave_prices = [float(p) for p in pts[:5]]
    x_dates: List[Any] = []
    for i in range(len(wave_prices)):
        if i < len(pivot_dates):
            x_dates.append(pivot_dates[i])
        else:
            x_dates.append(pivot_dates[-1])

    fig.add_trace(go.Scatter(
        x=x_dates,
        y=wave_prices,
        mode="lines+markers+text",
        line=dict(
            color=WAVE_COLORS["motive"] if is_bullish else WAVE_COLORS["corrective"],
            width=2.5,
        ),
        marker=dict(size=12, color=WAVE_COLORS["motive"], symbol="circle"),
        text=wave_labels,
        textposition="top center",
        textfont=dict(color="#FFFFFF", size=13, family="monospace"),
        name="Wave Structure",
        showlegend=True,
    ))

    # ── FIBONACCI RETRACEMENT GRID ON W1 LEG ───────────────────────────
    # Levels: 0.236/0.382/0.500/0.618/0.786 user-confirmed.
    # Source: Frost & Prechter Elliott Wave Principle.
    w1_high:  float = max(float(pts[0]), float(pts[1]))
    w1_low:   float = min(float(pts[0]), float(pts[1]))
    w1_range: float = w1_high - w1_low

    for level in FIB_RETRACEMENT_LEVELS:
        fib_price: float = w1_high - (w1_range * level)
        fig.add_hline(
            y=fib_price,
            line_dash="dot",
            line_color=FIB_COLORS.get(level, "rgba(255,255,255,0.3)"),
            line_width=1.2,
            annotation_text=f"  {level:.3f}  ${fib_price:,.2f}",
            annotation_position="right",
            annotation_font=dict(
                color=FIB_COLORS.get(level, "rgba(255,255,255,0.6)"),
                size=10,
            ),
        )

    # ── FIBONACCI BOX (W1 RANGE) ────────────────────────────────────────
    if len(x_dates) >= 2:
        fig.add_vrect(
            x0=x_dates[0],
            x1=x_dates[1],
            fillcolor=WAVE_COLORS["fib_box"],
            line_width=0,
            annotation_text="W1 Fib Zone",
            annotation_position="top left",
            annotation_font=dict(color="rgba(255,215,0,0.6)", size=9),
        )

    # ── WAVE 3 TARGET ZONE ──────────────────────────────────────────────
    # Targets: 1.618 x W1 (primary) and 2.618 x W1 (secondary).
    # Source: WAVE_3_GUIDELINES [PF] pp.29-33.
    target_low:  float = targets["target_1618"]
    target_high: float = targets["target_2618"]

    fig.add_hrect(
        y0=min(target_low, target_high),
        y1=max(target_low, target_high),
        fillcolor=WAVE_COLORS["target"],
        line_width=0,
        annotation_text="W3 Target Zone",
        annotation_position="right",
        annotation_font=dict(color="#00E5FF", size=10),
    )

    for val, lbl in [
        (target_low,  "W3 x1.618"),
        (target_high, "W3 x2.618"),
    ]:
        fig.add_hline(
            y=val,
            line_dash="dash",
            line_color="#00E5FF",
            line_width=1.5,
            annotation_text=f"  {lbl}  ${val:,.2f}",
            annotation_position="right",
            annotation_font=dict(color="#00E5FF", size=10),
        )

    # ── INVALIDATION LINE ───────────────────────────────────────────────
    invalidation: float = float(pts[0])
    fig.add_hline(
        y=invalidation,
        line_dash="dash",
        line_color="#FF4444",
        line_width=1.8,
        annotation_text=f"  Invalidation  ${invalidation:,.2f}",
        annotation_position="right",
        annotation_font=dict(color="#FF4444", size=10),
    )

    # ── PHASE ANNOTATION ────────────────────────────────────────────────
    if w4_result["is_valid"]:
        phase_text  = "Phase: W4 complete — watching for W5 launch"
        phase_color = "#00E5FF"
    elif not impulse_result.get("valid", True):
        phase_text  = f"Phase: {impulse_result.get('reason', 'Structure invalid')}"
        phase_color = "#FF6B6B"
    else:
        phase_text  = "Phase: Motive impulse — W2/W4 in correction"
        phase_color = "#FFD700"

    fig.add_annotation(
        text=phase_text,
        xref="paper", yref="paper",
        x=0.01, y=0.97,
        showarrow=False,
        font=dict(color=phase_color, size=12, family="monospace"),
        bgcolor="rgba(14,17,23,0.85)",
        bordercolor=phase_color,
        borderwidth=1,
        borderpad=6,
    )

    if not w4_result["is_valid"]:
        fig.add_annotation(
            text=f"RULE 3 VIOLATION — Overlap: ${w4_result['overlap_depth']:.2f}",
            xref="paper", yref="paper",
            x=0.01, y=0.89,
            showarrow=False,
            font=dict(color="#FF4444", size=11, family="monospace"),
            bgcolor="rgba(255,68,68,0.12)",
            bordercolor="#FF4444",
            borderwidth=1,
            borderpad=5,
        )

    fig.update_layout(
        template="plotly_dark",
        height=650,
        margin=dict(l=10, r=140, t=50, b=10),
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
            text=f"{ticker} — Elliott Wave Structure ({tf_label})",
            font=dict(color="#e0e0e0", size=15),
        ),
    )
    return fig


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point for the Elliott Wave UI page."""
    st.title(t("ew_title"))
    st.markdown("---")

    st.sidebar.header("Elliott Configuration")

    symbol: str = st.sidebar.text_input(
        "Ticker Symbol", value="AAPL"
    ).upper().strip()

    tf_key: str = st.sidebar.selectbox(
        "Timeframe",
        list(TF_CONFIG.keys()),
        index=2,
    )
    tf_label: str = TF_CONFIG[tf_key]["label"]

    if TF_CONFIG[tf_key]["intraday_cap"]:
        st.sidebar.caption(
            "Note: yfinance limits 1H and 4H data to approximately "
            "730 days regardless of window requested."
        )

    lookback: int = st.sidebar.slider(
        "Pivot Scan Depth", min_value=5, max_value=20, value=10
    )

    pivot_order: int = st.sidebar.slider(
        "Pivot Sensitivity (order)",
        min_value=2,
        max_value=15,
        value=3 if TF_CONFIG[tf_key]["intraday_cap"] else 5,
    )

    if st.sidebar.button("Execute Elliott Analysis"):

        with st.spinner(f"Fetching {symbol} [{tf_label}] data..."):
            try:
                df = fetch_ohlcv(symbol, tf_key)
            except Exception as e:
                logger.error(
                    f"Fetch failed {symbol} {tf_key}: {e}", exc_info=True
                )
                st.error(f"Data Fetch Error: {str(e)}")
                st.stop()

        if df.empty:
            st.error(
                f"No data returned for {symbol} on {tf_label}. "
                "Verify the ticker and timeframe."
            )
            st.stop()

        with st.spinner("Extracting pivot structure..."):
            try:
                pivots   = find_pivots(df, order=pivot_order)
                p_prices = pivots["close"].values
                p_dates  = pivots.index
            except Exception as e:
                logger.error(f"Pivot extraction failed: {e}", exc_info=True)
                st.error(f"Pivot Extraction Error: {str(e)}")
                st.stop()

        if len(p_prices) < 6:
            st.warning(
                f"Only {len(p_prices)} pivots detected for {symbol} "
                f"on {tf_label}. Lower pivot sensitivity or choose a "
                "longer timeframe."
            )
            st.stop()

        engine = ElliottEngine()

        st.header(f"Wave Audit: {symbol} — {tf_label}")

        price_col, info_col = st.columns([3, 1])

        with price_col:
            st.subheader("Price Chart")
            st.plotly_chart(
                render_price_chart(df, symbol, tf_label),
                width="stretch",
            )

        found_valid: bool = False

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

            if len(p_prices) >= 6:
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
            else:
                impulse_result = {"valid": True, "reason": "5-point only"}

            with price_col:
                st.subheader("Elliott Wave Structure Chart")
                wave_fig = render_wave_chart(
                    df, symbol, tf_label,
                    pts, pt_dates,
                    w2, w4, targets, impulse_result,
                )
                st.plotly_chart(wave_fig, width="stretch")

            with info_col:
                st.subheader("Rule Audit")

                st.success(f"Rule 1: PASS — W2 retrace {w2['ratio']:.3f}")
                if w2["is_ideal"]:
                    st.caption("Ideal 0.500-0.618 zone per [PF] p.28.")
                else:
                    st.caption("Valid retrace — outside ideal zone.")

                if impulse_result["valid"]:
                    st.success("Rule 2: PASS — W3 not shortest.")
                else:
                    if "Rule 2" in impulse_result.get("reason", ""):
                        st.error(f"Rule 2: FAIL — {impulse_result['reason']}")
                    else:
                        st.success("Rule 2: PASS — W3 confirmed.")

                if w4["is_valid"]:
                    st.success("Rule 3: PASS — No W4/W1 overlap.")
                else:
                    st.error(
                        f"Rule 3: VIOLATION — "
                        f"${w4['overlap_depth']:.2f} overlap"
                    )
                    if w4["is_diagonal"]:
                        st.info("Potential Leading Diagonal.")

                st.markdown("---")
                st.markdown("**Wave 3 Targets**")
                st.metric("1.618 Extension", f"${targets['target_1618']:,.2f}")
                st.metric("2.618 Extension", f"${targets['target_2618']:,.2f}")

                st.markdown("---")
                st.markdown("**Fib Retracement (W1)**")
                w1_high = max(float(pts[0]), float(pts[1]))
                w1_low  = min(float(pts[0]), float(pts[1]))
                w1_rng  = w1_high - w1_low
                for lvl in FIB_RETRACEMENT_LEVELS:
                    fib_px = w1_high - (w1_rng * lvl)
                    st.caption(f"{lvl:.3f} -> ${fib_px:,.2f}")

                st.markdown("---")
                st.error(
                    f"**Invalidation: ${float(pts[0]):,.2f}**\n"
                    "Close below this level voids motive structure."
                )

                # Wave 4 support: 0.382 x Wave 3 length per [PF] p.34
                wave3_length: float  = abs(float(pts[3]) - float(pts[2]))
                wave4_support: float = float(pts[3]) - (0.382 * wave3_length)

                phase = (
                    "Correction (W4)"
                    if not w4["is_valid"]
                    else "Extension (W3)"
                )
                st.markdown("---")
                st.markdown("**Trader Summary**")
                st.code(
                    f"Symbol    : {symbol}\n"
                    f"TF        : {tf_label}\n"
                    f"Phase     : {phase}\n"
                    f"W4 Support: ${wave4_support:,.2f} (0.382 x W3)\n"
                    f"W3 Target : ${targets['target_1618']:,.2f}\n"
                    f"Invalid   : ${float(pts[0]):,.2f}\n"
                    f"Status    : "
                    + (
                        "W5 LAUNCH WATCH"
                        if w4["is_valid"]
                        else "DIAGONAL ALERT"
                    )
                )

            st.session_state["ew_latest_scan"] = {
                "ticker":         symbol,
                "tf_key":         tf_key,
                "tf_label":       tf_label,
                "pts":            [float(p) for p in pts],
                "pt_dates":       [str(d) for d in pt_dates],
                "w2_ratio":       w2["ratio"],
                "w2_is_ideal":    w2["is_ideal"],
                "w4_valid":       w4["is_valid"],
                "w4_overlap":     w4["overlap_depth"],
                "target_1618":    targets["target_1618"],
                "target_2618":    targets["target_2618"],
                "invalidation":   float(pts[0]),
                "wave4_support":  wave4_support,
                "impulse_valid":  impulse_result["valid"],
                "impulse_reason": impulse_result.get("reason", ""),
                "is_bullish":     float(pts[1]) > float(pts[0]),
            }

            found_valid = True
            break

        if not found_valid:
            st.warning(
                f"No valid impulse structure detected for {symbol} "
                f"on {tf_label} within {lookback} pivots. "
                "Try lowering pivot sensitivity or increasing scan depth."
            )

    else:
        st.info(
            "Select symbol and timeframe in the sidebar, "
            "then press **Execute Elliott Analysis**."
        )


if __name__ == "__main__":
    main()