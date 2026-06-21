import streamlit as st
from typing import Dict, Union

from engine.evidence.schemas import EvidenceScore


def render_decision_summary(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    UI-only Decision Summary.

    PURPOSE:
    - Provide a single, deterministic, human-readable interpretation layer
    - Zero impact on trading logic or pipeline outputs

    GUARANTEES:
    - Read-only
    - No aggregation side effects
    - No signal mutation
    """

    st.subheader("🧠 Decision Summary")

    if not evidence:
        st.info("No evidence available to summarize.")
        return

    # Normalize scores
    scores: Dict[str, float] = {}
    confidences: Dict[str, float] = {}

    for name, ev in evidence.items():
        if isinstance(ev, EvidenceScore):
            scores[name] = float(ev.score)
            confidences[name] = float(ev.confidence)
        elif isinstance(ev, (int, float)):
            scores[name] = float(ev)
            confidences[name] = 0.0

    if not scores:
        st.info("No usable signals found.")
        return

    # Dominant signal by absolute contribution
    dominant_signal = max(scores.items(), key=lambda x: abs(x[1]))[0]
    dominant_score = scores[dominant_signal]
    dominant_conf = confidences.get(dominant_signal, 0.0)

    # Net directional bias
    net_score = sum(scores.values())

    if net_score > 0:
        bias = "Bullish"
    elif net_score < 0:
        bias = "Bearish"
    else:
        bias = "Neutral"

    # Confidence-weighted overview (mean, UI-only)
    avg_confidence = (
        sum(confidences.values()) / max(len(confidences), 1)
        if confidences
        else 0.0
    )

    # Render
    col1, col2, col3 = st.columns(3)

    col1.metric("Net Bias", bias)
    col2.metric("Dominant Signal", dominant_signal.capitalize())
    col3.metric("Avg Confidence", round(avg_confidence, 3))

    with st.expander("Details"):
        st.markdown(
            f"""
- **Dominant contribution:** `{dominant_signal}`  
- **Dominant score:** `{round(dominant_score, 3)}`  
- **Dominant confidence:** `{round(dominant_conf, 3)}`  
- **Net score (sum):** `{round(net_score, 3)}`
"""
        )

    st.caption(
        "UI-only explanatory layer. No trading logic, execution, or risk decisions are made here."
    )
