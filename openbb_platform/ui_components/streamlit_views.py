# engine/explainability/streamlit_views.py
import streamlit as st
from typing import Dict, Any
from engine.explainability.scenario_breakdown import scenario_contributions

def render_scenario_breakdown(evidence: Dict[str, Any]) -> None:
    st.subheader("Scenario Contribution Breakdown")
    rows = scenario_contributions(evidence)
    if not rows:
        st.info("No contributable signals available.")
        return

    # FIX: Replaced use_container_width=True with width="stretch" per 2026 API requirements
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "signal": st.column_config.TextColumn("Signal"),
            "score": st.column_config.NumberColumn("Score", format="%.2f"),
            "confidence": st.column_config.NumberColumn(
                "Confidence", format="%.2f"
            ),
            "contribution": st.column_config.NumberColumn(
                "Directional Contribution", format="%.2f"
            ),
        },
    )