# engine/ui/charts.py
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

# ==========================================================
# Multi‑Timeframe Candlestick Renderer (UI‑ONLY)
# ==========================================================

TIMEFRAME_MAP = {
    "30m": "30T",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1M": "1M",
}

def _resample_ohlcv(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    rule = TIMEFRAME_MAP[tf]
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample(rule).agg(ohlc).dropna()

def render_candlestick_chart(df: pd.DataFrame, timeframe: str):
    tf_df = _resample_ohlcv(df, timeframe)
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=tf_df.index,
                open=tf_df["open"],
                high=tf_df["high"],
                low=tf_df["low"],
                close=tf_df["close"],
                increasing_line_color="#00c853",
                decreasing_line_color="#ff1744",
                name="Price",
            )
        ]
    )
    fig.update_layout(
        height=420,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        showlegend=False,
    )
    # FIX: Replaced use_container_width=True with width="stretch" per 2026 API requirements
    st.plotly_chart(fig, width="stretch")

def render_multi_timeframe_charts(df: pd.DataFrame):
    st.subheader("📊 Market Structure — Multi‑Timeframe")
    tabs = st.tabs(["30m", "1h", "4h", "1D", "1W", "1M"])
    for tab, tf in zip(tabs, ["30m", "1h", "4h", "1d", "1w", "1M"]):
        with tab:
            render_candlestick_chart(df, tf)