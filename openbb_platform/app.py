# app.py
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import asyncio
import os
from plotly.subplots import make_subplots
from streamlit_searchbox import st_searchbox
from streamlit_lightweight_charts import renderLightweightCharts 

from engine.search import get_symbol_suggestions
from engine.pipeline import run_pipeline
from engine.copilot.engine import get_copilot_response, OPENAI_AVAILABLE, client as ai_client
from engine.backtest import run_backtest

st.set_page_config(page_title="OpenBB Workplace AI | 2026 Edition", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0B0E14; color: #E1E1E1; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #3b82f6; }
    .stSidebar { background-color: #0F1218 !important; border-right: 1px solid #1f2937; }
    .copilot-card { background-color: #161B22; border-radius: 10px; padding: 20px; border-left: 5px solid #3b82f6; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

def ensure_datetime_index(df: pd.DataFrame):
    if df is None or df.empty: return df
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex): df.index = pd.to_datetime(df.index)
    return df

def render_tv_chart(df: pd.DataFrame, plan: dict):
    chart_data = df.reset_index()
    chart_data.columns = [c.lower() for c in chart_data.columns]
    if 'date' in chart_data.columns: chart_data = chart_data.rename(columns={'date': 'time'})
    elif 'index' in chart_data.columns: chart_data = chart_data.rename(columns={'index': 'time'})
    chart_data['time'] = pd.to_datetime(chart_data['time']).apply(lambda x: int(x.timestamp())) 
    candles = chart_data[['time', 'open', 'high', 'low', 'close']].to_dict('records')
    volume = chart_data[['time', 'volume']].rename(columns={'volume': 'value'}).to_dict('records')
    chart_options = {"height": 600, "layout": {"background": {"type": 'solid', "color": '#0B0E14'}, "textColor": '#d1d4dc'}, "grid": {"vertLines": {"color": '#1f2937'}, "horzLines": {"color": '#1f2937'}}, "priceScale": {"borderColor": '#2b2b43'}, "timeScale": {"borderColor": '#2b2b43'}}
    series = [{"type": 'Candlestick', "data": candles, "options": {"upColor": '#26a69a', "downColor": '#ef5350'}}, {"type": 'Histogram', "data": volume, "options": {"color": 'rgba(38, 166, 154, 0.3)', "priceFormat": {"type": 'volume'}, "priceScaleId": ""}}]
    renderLightweightCharts(charts=[{"chart": chart_options, "series": series}])

def render_advanced_theory_chart(df: pd.DataFrame, plan: dict, active_patterns: list, show_ichimoku: bool, show_fibs: bool, osc_selection: list):
    df = ensure_datetime_index(df)
    rows = 1 + len(osc_selection)
    row_heights = [0.6] + [0.4 / len(osc_selection)] * len(osc_selection) if osc_selection else [1.0]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)

    if show_ichimoku and 'tenkan' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['tenkan'], line=dict(color='#ef4444', width=1), name="Tenkan-Sen"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['kijun'], line=dict(color='#3b82f6', width=1), name="Kijun-Sen"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_a'], line=dict(color='rgba(16, 185, 129, 0.5)'), name="Senkou A"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_b'], line=dict(color='rgba(239, 68, 68, 0.5)'), fill='tonexty', name="Senkou B"), row=1, col=1)

    elliott = plan.get("elliott_raw", {})
    if "wave_coords" in elliott:
        coords = elliott["wave_coords"]
        fig.add_trace(go.Scatter(x=[c['x'] for c in coords], y=[c['y'] for c in coords], mode='lines+markers+text', text=[f"({i})" for i in range(len(coords))], line=dict(color='#facc15', width=3, dash='dash'), name="Elliott Motive"), row=1, col=1)

    for p in plan.get("harmonics_raw", []):
        if p.get('name') in active_patterns:
            pts = p.get('points', [])
            if len(pts) >= 5:
                try:
                    p_x = [df.index[min(int(pt[0]), len(df)-1)] if isinstance(pt[0], (int, np.integer)) else pt[0] for pt in pts]
                    p_y = [pt[1] for pt in pts]
                    fig.add_trace(go.Scatter(x=[p_x[0], p_x[1], p_x[2], p_x[3], p_x[4], p_x[2], p_x[0]], y=[p_y[0], p_y[1], p_y[2], p_y[3], p_y[4], p_y[2], p_y[0]], fill="toself", fillcolor='rgba(59, 130, 246, 0.15)', line=dict(color='#3b82f6', width=2), name=p.get('name')), row=1, col=1)
                except Exception: pass

    if show_fibs and "fib_levels" in plan:
        for name, price in plan["fib_levels"].items(): fig.add_hline(y=price, line_dash="dot", line_color="rgba(128,128,128,0.5)", annotation_text=name, row=1, col=1)

    curr_row = 2
    if "RSI" in osc_selection and 'rsi' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], line=dict(color='#9333ea', width=2), name="RSI"), row=curr_row, col=1)
        curr_row += 1
    if "MACD" in osc_selection and 'macd' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['macd'], line=dict(color='#3b82f6'), name="MACD"), row=curr_row, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['macdh'], marker_color='rgba(128,128,128,0.3)', name="Histogram"), row=curr_row, col=1)
        curr_row += 1

    fig.update_layout(template="plotly_dark", height=850, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width='stretch') # ← FIXED: Streamlit 2026 syntax

with st.sidebar:
    st.image("https://openbb.co/logo.png", width=150)
    ai_status = '<span class="status-tag online">AI ONLINE</span>' if ai_client else '<span class="status-tag offline">AI OFFLINE</span>'
    st.markdown(f"**Workplace Pro** {ai_status}", unsafe_allow_html=True)
    selected_symbol = st_searchbox(get_symbol_suggestions, label="Symbol Search", key="global_search")
    if selected_symbol: st.session_state.current_symbol = selected_symbol
    elif "current_symbol" not in st.session_state: st.session_state.current_symbol = "BTC-USD"
    symbol = st.session_state.current_symbol
    tf_display = st.selectbox("Interval", ["1h", "4h", "Daily", "Weekly", "Monthly"], index=2)
    tf_map = {"1h": "1h", "4h": "4h", "Daily": "1d", "Weekly": "1W", "Monthly": "1M"}
    st.divider()
    page_view = st.radio("Navigation", ["Market Dashboard", "Advanced Analysis", "Research Copilot", "Backtest Report"])
    with st.expander("Chart Settings", expanded=True):
        osc_selection = st.multiselect("Indicators", ["RSI", "MACD", "Volume"], default=["RSI", "MACD", "Volume"])
        show_ichimoku = st.checkbox("Ichimoku Cloud", value=True)
        show_fibs = st.checkbox("Fibonacci Retracements", value=True)
    execute_analysis = st.button("🔄 Sync Market Data", width='stretch', type="primary") # ← FIXED: 2026 syntax

@st.cache_data(ttl=300)
def cached_pipeline(sym, tf):
    try: 
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(run_pipeline(symbol=sym, timeframe=tf))
    except Exception as e: return {"success": False, "error": f"Connectivity/Engine Failure: {str(e)}"}

results = cached_pipeline(symbol, tf_map[tf_display]) if (execute_analysis or "current_symbol" in st.session_state) else {}

if results and results.get("success") and "results" in results:
    timeframes_results = results.get("results", {})
    target_tf = tf_map[tf_display]
    
    if target_tf not in timeframes_results:
        st.error(f"No specific data available for {symbol} on {tf_display} interval.")
        st.stop()
        
    report_data = timeframes_results[target_tf]
    df_current = report_data.get("df")
    
    if page_view == "Market Dashboard":
        st.subheader(f"Institutional Workspace: {symbol} ({tf_display})")
        col_m, col_s = st.columns([3, 1])
        with col_m:
            if df_current is not None and not df_current.empty: # ← ADDED: Defensive check
                render_tv_chart(df_current, report_data)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Bias", report_data['section_7_summary']['bias'])
            m2.metric("Symbol", report_data['section_7_summary']['symbol'])
            m3.metric("Status", "VERIFIED")
            m4.metric("Engine", "SV-GRADE")
        with col_s:
            st.write("### Alpha Signal")
            st.info(report_data['section_1_detection'])
            st.write("### Significance")
            st.markdown(f"> {report_data['section_2_significance']}")

    elif page_view == "Advanced Analysis":
        st.subheader(f"Geometric Market Theory: {symbol} ({tf_display})")
        if df_current is not None and not df_current.empty: # ← ADDED: Defensive check
            pattern_names = [p['name'] for p in report_data.get('harmonics_raw', [])]
            render_advanced_theory_chart(df_current, report_data, pattern_names, show_ichimoku, show_fibs, osc_selection)
        st.write(report_data['section_1_detection'])
        st.write("PRZ Levels:", report_data['section_3_prz'])
        st.write("Invalidation:", report_data['section_5_invalidation'])

    elif page_view == "Research Copilot":
        st.subheader("Interactive Alpha Copilot")
        if not os.getenv("OPENAI_API_KEY"):
            st.error("⚠️ OPENAI_API_KEY is missing. Please set it in your environment to enable Copilot.")
            st.stop()
        if "chat_history" not in st.session_state: st.session_state.chat_history = []
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.write(msg["content"])
        if prompt := st.chat_input("Ask about reversal points..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.write(prompt)
            context_payload = {"symbol": symbol, "timeframe": tf_display, "report": report_data}
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                async def run_ai():
                    accumulated = ""
                    try:
                        async for chunk in get_copilot_response(prompt, context_payload, st.session_state.chat_history[:-1]):
                            accumulated += chunk
                            response_placeholder.markdown(f'<div class="copilot-card">{accumulated}▌</div>', unsafe_allow_html=True)
                        response_placeholder.markdown(f'<div class="copilot-card">{accumulated}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        error_msg = f"AI Engine Exception: {str(e)}"
                        response_placeholder.error(error_msg); accumulated = error_msg
                    return accumulated
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    full_response = new_loop.run_until_complete(run_ai())
                    new_loop.close()
                except Exception as e: full_response = f"Critical Runtime Error: {str(e)}"; st.error(full_response)
                st.session_state.chat_history.append({"role": "assistant", "content": full_response})

    elif page_view == "Backtest Report":
        st.subheader(f"Strategy Simulation: {symbol}")
        st.warning("Backtest requires raw OHLCV data. Multi-TF reports current.")
else:
    if results and "error" in results: st.error(results["error"])
    st.markdown("## 👋 Welcome to the OpenBB AI Workplace\nSearch a ticker in the sidebar to begin analysis.")