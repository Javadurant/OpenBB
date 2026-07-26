"""
home_buttons.py
===============
Drop-in module that fixes the app.py home page so buttons are CLICKABLE
and route to the relevant pages via st.switch_page().

USAGE in app.py — anywhere in the home section:

    from home_buttons import render_home_buttons
    render_home_buttons()

That replaces any static text descriptions of features with real buttons
that navigate to the pages when clicked.

Place at: openbb_platform/home_buttons.py
"""

from pathlib import Path

import streamlit as st


# ── Auto-discover available pages ─────────────────────────────────────────
def _list_pages() -> list:
    """Find all Python files in pages/ directory."""
    pages_dir = Path(__file__).parent / "pages"
    if not pages_dir.exists():
        return []
    return sorted([
        p for p in pages_dir.glob("*.py")
        if p.is_file() and not p.name.startswith("_")
    ])


# ── Pretty labels and descriptions for each page ──────────────────────────
_PAGE_META = {
    "two_signal_analysis":         ("🎯 Two-Signal Analysis",       "Get independent technical + fundamental buy/sell/hold signals on any stock."),
    "ai_trading_agent":            ("🤖 AI Trading Agent",          "Multi-engine technical analysis with Elliott Wave, harmonics, Ichimoku."),
    "trading_intelligence_hub_v2": ("🧠 Trading Intelligence Hub",  "18 trading skills — VCP, CANSLIM, breadth, market top, more."),
    "trading_intelligence_hub":    ("🧠 Trading Hub (legacy)",      "Original intelligence hub."),
    "analyst_intelligence_ui":     ("📊 Analyst Intelligence",      "Institutional analyst frameworks — 10 different lenses."),
    "analyst_prompts_ui":          ("✍️ Analyst Prompts",           "Pre-built prompt library for analyst-style questions."),
    "swedish_stock_analysis":      ("🇸🇪 Swedish Stocks",            "OMX Stockholm specific analysis — ISK/KF tax wrapper aware."),
    "let_god_trade":               ("⚡ Autonomous Execution",       "Live trading via Alpaca + Swedish paper sim. Use with extreme care."),
    "elliott_ui":                  ("🌊 Elliott Wave",              "Frost & Prechter wave structure detection."),
    "harmonics_ui":                ("📐 Harmonic Patterns",         "Carney Vol.1/2/3 harmonic patterns — Bat, Gartley, Crab, etc."),
    "confluence_ui":               ("🎯 Confluence Analysis",       "Multi-engine PRZ + indicator confluence."),
    "scanner_ui":                  ("🔍 Multi-Engine Scanner",      "Scan a universe with the full engine stack."),
    "chart_config":                ("📈 Chart Configuration",       "Customize charting defaults."),
}


def render_home_buttons() -> None:
    """
    Render clickable buttons for every page in pages/.
    Each button uses st.switch_page() to route to the page.
    Compatible with Streamlit 1.30+.
    """
    pages = _list_pages()
    if not pages:
        st.info("No pages found in pages/ directory yet.")
        return

    st.subheader("📂 Open a tool")

    # Three columns of buttons
    cols  = st.columns(3)
    for i, page_path in enumerate(pages):
        stem  = page_path.stem
        label, desc = _PAGE_META.get(stem, ("📄 " + stem.replace("_", " ").title(), ""))

        col = cols[i % 3]
        with col:
            with st.container(border=True):
                st.markdown("**" + label + "**")
                if desc:
                    st.caption(desc)
                # The button — when clicked, st.switch_page navigates
                if st.button(
                    "Open",
                    key="home_btn_" + stem,
                    use_container_width=True,
                ):
                    try:
                        st.switch_page("pages/" + page_path.name)
                    except Exception:
                        # Older Streamlit fallback — set query param
                        st.query_params["page"] = stem
                        st.rerun()


def render_home_quick_actions() -> None:
    """
    Three large primary action buttons at the top of the home page —
    the most common workflows.
    """
    st.subheader("⚡ Quick Actions")

    qa1, qa2, qa3 = st.columns(3)

    with qa1:
        with st.container(border=True):
            st.markdown("### 🎯 Analyze a stock")
            st.caption("Two-signal analysis: technical + fundamental")
            if st.button("Open Two-Signal", key="qa_two_signal", use_container_width=True, type="primary"):
                try:
                    st.switch_page("pages/two_signal_analysis.py")
                except Exception:
                    st.query_params["page"] = "two_signal_analysis"
                    st.rerun()

    with qa2:
        with st.container(border=True):
            st.markdown("### 🇸🇪 Swedish OMX")
            st.caption("Stockholm market analysis with ISK/KF support")
            swe_path = Path(__file__).parent / "pages" / "swedish_stock_analysis.py"
            if st.button("Open Swedish", key="qa_swedish", use_container_width=True, disabled=not swe_path.exists()):
                try:
                    st.switch_page("pages/swedish_stock_analysis.py")
                except Exception:
                    st.query_params["page"] = "swedish_stock_analysis"
                    st.rerun()

    with qa3:
        with st.container(border=True):
            st.markdown("### 🧠 Psychology")
            st.caption("Pre-trade ritual & post-trade debrief")
            psych_path = Path(__file__).parent / "psychology_engine.py"
            if psych_path.exists():
                st.success("Engine loaded")
            else:
                st.warning("Run setup first")
            st.caption("Use within Two-Signal Analysis →")


def render_home_stats() -> None:
    """Library and platform stats on home page."""
    project_root = Path(__file__).parent
    books_dir    = project_root / "trading_books"
    cache_dir    = project_root / ".index_cache"

    s1, s2, s3, s4 = st.columns(4)

    if books_dir.exists():
        n_pdf  = len(list(books_dir.rglob("*.pdf")))
        n_docx = len(list(books_dir.rglob("*.docx")))
        n_md   = len(list(books_dir.rglob("*.md")))
        s1.metric("📚 Library", str(n_pdf + n_docx + n_md), f"{n_pdf} PDF / {n_docx} DOCX")
    else:
        s1.metric("📚 Library", "0", "No books yet")

    s2.metric("🗂️ Index", "✅ Built" if cache_dir.exists() else "❌ Not built", "")

    pages_dir = project_root / "pages"
    n_pages   = len(list(pages_dir.glob("*.py"))) if pages_dir.exists() else 0
    s3.metric("📄 Pages", str(n_pages), "")

    api_count = sum(1 for k in [
        "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "FMP_API_KEY",  "ALPHA_VANTAGE_API_KEY",
        "TIINGO_API_KEY", "FRED_API_KEY", "EODHD_API_KEY",
    ] if (project_root / ".env").exists()
       and k in (project_root / ".env").read_text(errors="ignore"))
    s4.metric("🔑 API Keys", str(api_count), "configured")


if __name__ == "__main__":
    print("This module must be imported from app.py — not run directly.")
    print("Add to app.py:")
    print("  from home_buttons import render_home_buttons, render_home_quick_actions, render_home_stats")
    print("  render_home_quick_actions()")
    print("  render_home_stats()")
    print("  render_home_buttons()")
