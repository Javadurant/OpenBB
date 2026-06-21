import streamlit as st
from typing import Dict, Union

from engine.evidence.schemas import EvidenceScore


def render_confidence_calibration(
    evidence: Dict[str, Union[EvidenceScore, float]],
    probability: float
) -> None:
    """
    UI-only confidence calibration view.

    Displays:
    - System probability
    - Evidence dispersion
    - Alignment signal (agreement vs conflict)

    No recomputation.
    No mutation.
    """

    if not evidence:
        return

    scores = []
    for ev in evidence.values():
        if isinstance(ev, EvidenceScore):
            scores.append(ev.score)
        else:
            scores.append(float(ev))

    if not scores:
        return

    dispersion = max(scores) - min(scores)

    st.subheader("🎯 Confidence Calibration")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Model Probability",
            value=round(probability, 2)
        )

    with col2:
        st.metric(
            label="Evidence Dispersion",
            value=round(dispersion, 2)
        )

    if dispersion > 0.8:
        st.warning("High signal disagreement detected")
    elif dispersion < 0.3:
        st.success("Strong signal agreement")
    else:
        st.info("Moderate signal alignment")
