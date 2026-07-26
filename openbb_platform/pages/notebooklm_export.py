"""Streamlit page for exporting analyses to NotebookLM"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import streamlit as st
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from translations import t, inject_rtl_css  # <- NEW [i18n]

# Add project root to path for relative imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from notebooklm_exporter import NotebookLMExporter
except ImportError as e:
    st.error(f"❌ Failed to import NotebookLMExporter: {e}")
    st.stop()

st.set_page_config(page_title="NotebookLM Export", page_icon="📊")
st.markdown("# 📊 Export to NotebookLM")

try:
    exporter = NotebookLMExporter()
except Exception as e:
    st.error(f"❌ Failed to initialize exporter: {e}")
    st.stop()

st.info("Generate markdown files to upload to NotebookLM for AI analysis and audio podcasts")

col1, col2 = st.columns(2)

# Weekly Digest
with col1:
    if st.button("📋 Create Weekly Digest"):
        try:
            sample_analyses: list[Dict[str, Any]] = [
                {
                    "type": "Elliott Wave", 
                    "symbol": "SPY", 
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": {"valid_structure": True, "target_1618": 542.5},
                },
                {
                    "type": "Harmonic Pattern",
                    "symbol": "QQQ",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": {"pattern": "Gartley", "ratio": 0.786},
                },
            ]
            path = exporter.export_weekly_digest(sample_analyses)
            st.success(f"✅ Created: {path.name}")
            st.info(f"📤 Next: Upload to https://notebooklm.google.com")
        except Exception as e:
            st.error(f"❌ Error creating weekly digest: {e}")

# Market Briefing
with col2:
    if st.button("📡 Create Market Briefing"):
        try:
            market_data: Dict[str, Dict[str, Any]] = {
                "^GSPC": {"name": "S&P 500", "current": 5300, "change": 0.5, "up": True},
                "^IXIC": {"name": "Nasdaq", "current": 16500, "change": 1.2, "up": True},
                "^VIX": {"name": "VIX", "current": 12.5, "change": -2.1, "up": False},
            }
            ai_summary = "Markets showing strength with technology sector leading gains. Volatility remains subdued."
            path = exporter.export_market_briefing(market_data, ai_summary)
            st.success(f"✅ Created: {path.name}")
            st.info(f"📤 Next: Upload to https://notebooklm.google.com")
        except Exception as e:
            st.error(f"❌ Error creating market briefing: {e}")

# Signal Report
st.divider()
if st.button("🎯 Create Signal Report"):
    try:
        signal_data: Dict[str, Any] = {
            "symbol": "SPY",
            "direction": "BUY",
            "confidence": 0.85,
            "entry": 535.50,
            "target": 560.00,
            "stop_loss": 520.00,
        }
        context = "Strong Elliott Wave confirmation on daily timeframe with harmonic support"
        path = exporter.export_signal_report("SPY", signal_data, context)
        st.success(f"✅ Created: {path.name}")
        st.info(f"📤 Next: Upload to https://notebooklm.google.com")
    except Exception as e:
        st.error(f"❌ Error creating signal report: {e}")

st.divider()
st.markdown("### 📌 About NotebookLM Export")
st.markdown("""
- Exports trading analyses in NotebookLM-compatible markdown
- Uploads to https://notebooklm.google.com for AI processing
- Generate Q&A, audio summaries, and research documents
- Combine multiple formats: Elliott Wave, Harmonics, Market Data, Trading Signals
""")
