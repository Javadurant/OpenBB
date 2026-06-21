import streamlit as st
import pandas as pd
from typing import Dict, Union
from engine.evidence.schemas import EvidenceScore


def render_scenario_breakdown(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    UI-only breakdown of raw evidence signals.
    """
    st.subheader("🔍 Evidence Breakdown")

    if not evidence:
        st.info("No evidence available.")
        return

    for name, ev in evidence.items():
        with st.expander(name.capitalize()):
            if isinstance(ev, EvidenceScore):
                st.metric("Score", round(ev.score, 3))
                st.metric("Confidence", round(ev.confidence, 3))
            else:
                st.metric("Score", round(float(ev), 3))
                st.caption("Confidence: n/a")


def render_contribution_chart(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    Visualizes signal contributions.
    Missing signals are displayed as 0.0 (explicit).
    """
    st.subheader("📊 Signal Contribution")

    expected_signals = [
        "momentum",
        "trend",
        "volatility",
        "structure",
    ]

    data = {}
    for name in expected_signals:
        ev = evidence.get(name)
        if isinstance(ev, EvidenceScore):
            data[name] = ev.score
        elif isinstance(ev, (int, float)):
            data[name] = float(ev)
        else:
            data[name] = 0.0

    df = pd.DataFrame.from_dict(
        data,
        orient="index",
        columns=["Score"],
    )

    st.bar_chart(df, width="stretch")


def render_confidence_calibration(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    Displays per-signal confidence calibration.
    """
    st.subheader("🎯 Signal Confidence")

    rows = []
    for name, ev in evidence.items():
        if isinstance(ev, EvidenceScore):
            rows.append({
                "Signal": name,
                "Confidence": round(ev.confidence, 3),
            })

    if not rows:
        st.info("No confidence data available.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch")


def render_decision_summary(
    evidence: Dict[str, Union[EvidenceScore, float]]
) -> None:
    """
    High-level decision summary.
    UI ONLY — no trading logic.
    """
    st.subheader("🧠 Decision Summary")

    if not evidence:
        st.info("No evidence available.")
        return

    total_score = 0.0
    total_weight = 0

    for ev in evidence.values():
        if isinstance(ev, EvidenceScore):
            total_score += ev.score
            total_weight += 1

    if total_weight == 0:
        st.info("Insufficient data for decision.")
        return

    avg_score = total_score / total_weight

    if avg_score > 0.25:
        decision = "Bullish Bias"
        color = "🟢"
    elif avg_score < -0.25:
        decision = "Bearish Bias"
        color = "🔴"
    else:
        decision = "Neutral / Uncertain"
        color = "🟡"

    st.metric("System Bias", f"{color} {decision}")
    st.caption(f"Aggregate evidence score: {round(avg_score, 3)}")
