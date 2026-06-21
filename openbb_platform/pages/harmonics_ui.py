# app/pages/harmonics_ui.py
# ← NEW: Harmonic Patterns Analysis UI

import streamlit as st
import pandas as pd
from engine.harmonics import HarmonicEngine
from engine.pipeline import AnalysisPipeline

st.set_page_config(page_title="Harmonic Audit 2.0", layout="wide")

def render_teacher_report(symbol, timeframe, pattern_data):
    """Formats findings into the 7-section ANALYSIS_TEACHER_PROMPT structure."""
    st.markdown(f"## 🏛️ ANALYSIS REPORT: {pattern_data['name']} detected on {symbol}")
    
    with st.container():
        st.markdown("### SECTION 1 — WHAT WAS DETECTED")
        st.write(f"A **{pattern_data['type']} {pattern_data['name']}** pattern completed on **{symbol}** [**{timeframe}**].")
        st.code(f"""
        Pivots: {pattern_data['pivots']}
        Ratios: {pattern_data['ratios']}
        Status: PRZ Reached
        """)

        st.markdown("### SECTION 2 — WHY THIS PATTERN MATTERS")
        st.write("This pattern represents a structural exhaustion point where harmonic ratios converge. "
                 "The quality is rated as **STRONG** due to primary ratio alignment in the Potential Reversal Zone.")

        st.markdown("### SECTION 3 — THE POTENTIAL REVERSAL ZONE (PRZ)")
        st.info(f"The PRZ is defined by the 0.786 D-Point of XA and the 1.618 BC projection. Boundary: {pattern_data['prz']}")

        st.markdown("### SECTION 4 — WHAT WILL HAPPEN NEXT")
        st.write("Primary Scenario: Bullish reversal from PRZ. Target 1: 0.382 AD Retracement. Target 2: 0.618 AD Retracement.")

        st.markdown("### SECTION 5 — WHAT INVALIDATES THIS ANALYSIS")
        st.warning(f"Analysis invalidated if price closes below the X-point at {pattern_data['stop_loss']}.")

        st.markdown("### SECTION 6 — CONFLUENCE AND CONTEXT")
        st.write("Check RSI for bullish divergence. Pattern aligns with daily support level.")

        st.markdown("### SECTION 7 — THE TRADER'S SUMMARY")
        st.markdown(f"""
        ```
        ┌─ PATTERN SUMMARY ─────────────────────────────────────────────────────────
        │ Pattern     : {pattern_data['name']} | {pattern_data['type']} | STRONG
        │ Completion  : {pattern_data['prz_mid']}
        │ Stop Loss   : {pattern_data['stop_loss']}
        │ Target 1    : {pattern_data['t1']}
        │ Confidence  : HIGH
        └────────────────────────────────────────────────────────────────────────────
        ```
        """)

# --- UI LOGIC ---
st.sidebar.header("Audit Configuration")
symbol = st.sidebar.text_input("Symbol", value="BTCUSD")
timeframe = st.sidebar.selectbox("Timeframe", ["1H", "4H", "D", "W", "M"])

if st.sidebar.button("Run Deep Analysis"):
    pipeline = AnalysisPipeline()
    with st.spinner("Processing multi-timeframe ratios..."):
        # Simulated data flow from Engine
        engine = HarmonicEngine()
        # In production: df = pipeline.fetch_data(symbol, timeframe)
        # For UI demonstration, we assume detection occurred:
        mock_pattern = {
            "name": "GARTLEY", "type": "Bullish", "pivots": "X-A-B-C-D",
            "ratios": "B/XA: 0.618, D/XA: 0.786", "prz": "42,100 - 42,350",
            "prz_mid": "42,225", "stop_loss": "41,900", "t1": "44,500"
        }
        render_teacher_report(symbol, timeframe, mock_pattern)