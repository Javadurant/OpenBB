import streamlit as st
from typing import Dict, Union

from engine.evidence.schemas import EvidenceScore


def render_contribution_chart(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    Visualizes per-signal contribution to overall direction.

    UI-only:
    - No aggregation logic
    - No normalization
    - No mutation
    """

    if not evidence:
        return

    st.subheader("📐 Signal Contribution")

    labels = []
    values = []

    for name, ev in evidence.items():
        labels.append(name.capitalize())

        if isinstance(ev, EvidenceScore):
            values.append(ev.score)
        else:
            values.append(float(ev))

    st.bar_chart(
        data=dict(zip(labels, values)),
        use_container_width=True
    )
