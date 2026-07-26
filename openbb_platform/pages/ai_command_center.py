"""
pages/ai_command_center.py
═══════════════════════════════════════════════════════════════════════════════
AI COMMAND CENTER — The Bloomberg Launchpad for QuantEdge
═══════════════════════════════════════════════════════════════════════════════

COUNCIL VERDICT: "QuantEdge's unique advantage is AI signal generation.
Bloomberg wins on data. TradingView wins on charts. QuantEdge wins on DECISIONS."

This page answers the 3 questions every trader has when they sit down:
  1. What's happening in the market RIGHT NOW?
  2. What should I be watching?
  3. Is there anything I should do TODAY?

ARCHITECTURE:
  - Batch-scans a user's watchlist through TechnicalSignalEngine + FundamentalSignalEngine
  - Ranks stocks by AI conviction score (0-100)
  - Shows top signals with one-click deep analysis
  - Economic calendar with AI interpretation
  - Position sizing calculator (ATR + Fixed-Fractional + Kelly)
  - Trade journal with R-multiple tracking

NO NEW DEPENDENCIES — uses existing engines, yfinance, Groq, FRED.
"""
import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from translations import t, inject_rtl_css, fmt_number, fmt_currency, get_locale_profile
from technical_signal_engine import TechnicalSignalEngine
from fundamental_signal_engine import FundamentalSignalEngine

logger = logging.getLogger("CommandCenter")


# ─── CONSTANTS ────────────────────────────────────────────────────────────────

DEFAULT_WATCHLIST = ["ERIC-B.ST", "VOLV-B.ST", "SAND.ST", "ABB.ST", "HM-B.ST", "SEB-A.ST", "INVE-B.ST", "ASSA-B.ST", "HEXA-B.ST"]
NORDIC_WATCHLIST  = ["ERIC-B.ST", "VOLV-B.ST", "SAND.ST", "ABB.ST", "HM-B.ST", "SEB-A.ST", "INVE-B.ST", "ASSA-B.ST", "HEXA-B.ST"]
US_WATCHLIST      = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "SPY", "QQQ"]

# Session state keys (namespaced to avoid collision)
_WL_KEY    = "cc_watchlist"
_RESULTS   = "cc_scan_results"
_JOURNAL   = "cc_trade_journal"

SIGNAL_COLORS = {
    "STRONG BUY":  "#00E676",
    "BUY":         "#66BB6A",
    "HOLD":        "#FFB74D",
    "SELL":        "#EF5350",
    "STRONG SELL": "#D32F2F",
}


# ─── BATCH SCANNER ────────────────────────────────────────────────────────────

def _scan_single_ticker(ticker: str) -> Dict[str, Any]:
    """Scan one ticker through both signal engines. Returns result dict."""
    try:
        tech_engine = TechnicalSignalEngine()
        fund_engine = FundamentalSignalEngine()
        tech = tech_engine.generate(ticker)
        fund = fund_engine.generate(ticker)
        
        # <- FIXED [Council]: TechnicalSignal/FundamentalSignal are dataclasses, not dicts.
        # Use attribute access (tech.signal) not dict access (tech.get("signal"))
        tech_signal = getattr(tech, "signal", "HOLD")
        tech_conf   = getattr(tech, "score", 0)
        fund_signal = getattr(fund, "signal", "HOLD")
        fund_conf   = getattr(fund, "score", 0)
        
        # Extract evidence citations from book_evidence attribute
        tech_evidence = getattr(tech, "book_evidence", []) or []
        fund_evidence = getattr(fund, "book_evidence", []) or []
        if isinstance(tech_evidence, str):
            tech_evidence = [tech_evidence]
        if isinstance(fund_evidence, str):
            fund_evidence = [fund_evidence]
        
        # Combined conviction score (0-100)
        signal_weights = {"STRONG BUY": 100, "BUY": 75, "HOLD": 50, "SELL": 25, "STRONG SELL": 0}
        tech_score = signal_weights.get(tech_signal, 50) * (tech_conf / 100.0) if tech_conf else 50
        fund_score = signal_weights.get(fund_signal, 50) * (fund_conf / 100.0) if fund_conf else 50
        combined   = int(0.6 * tech_score + 0.4 * fund_score)  # 60% technical, 40% fundamental
        
        # Get current price
        try:
            info = yf.Ticker(ticker).fast_info
            price = getattr(info, "last_price", None) or getattr(info, "previous_close", 0)
            change_pct = getattr(info, "change_percent", 0) or 0
        except Exception:
            price, change_pct = 0, 0
        
        # Determine combined signal
        if combined >= 80:
            combined_signal = "STRONG BUY"
        elif combined >= 65:
            combined_signal = "BUY"
        elif combined >= 40:
            combined_signal = "HOLD"
        elif combined >= 20:
            combined_signal = "SELL"
        else:
            combined_signal = "STRONG SELL"
        
        return {
            "ticker": ticker,
            "price": round(price, 2) if price else 0,
            "change_pct": round(change_pct * 100, 2) if change_pct else 0,
            "tech_signal": tech_signal,
            "tech_confidence": tech_conf,
            "fund_signal": fund_signal,
            "fund_confidence": fund_conf,
            "combined_signal": combined_signal,
            "conviction": combined,
            "tech_evidence": tech_evidence[:2],
            "fund_evidence": fund_evidence[:2],
            "error": None,
        }
    except Exception as e:
        return {
            "ticker": ticker, "price": 0, "change_pct": 0,
            "tech_signal": "ERROR", "tech_confidence": 0,
            "fund_signal": "ERROR", "fund_confidence": 0,
            "combined_signal": "ERROR", "conviction": 0,
            "tech_evidence": [], "fund_evidence": [],
            "error": str(e),
        }


def batch_scan(tickers: List[str]) -> List[Dict[str, Any]]:
    """Parallel-scan multiple tickers through both engines."""
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_scan_single_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            results.append(future.result())
    # Sort by conviction (highest first)
    results.sort(key=lambda x: x["conviction"], reverse=True)
    return results


# ─── POSITION SIZING CALCULATOR ───────────────────────────────────────────────

def calc_position_size(
    account_size: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
) -> Dict[str, Any]:
    """Fixed-fractional position sizing. Returns shares, risk amount, R-value."""
    risk_amount = account_size * (risk_pct / 100.0)
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share < 0.001:
        return {"shares": 0, "risk_amount": risk_amount, "risk_per_share": 0, "position_value": 0, "r_value": 0}
    shares = int(risk_amount / risk_per_share)
    position_value = shares * entry_price
    # R-value: how many R's is the target?
    return {
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "position_value": round(position_value, 2),
        "pct_of_account": round((position_value / account_size) * 100, 2) if account_size > 0 else 0,
    }


# ─── MAIN UI ──────────────────────────────────────────────────────────────────

def main():
    inject_rtl_css()

    # ── HEADER ────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:linear-gradient(135deg,#000d1a 0%,#001a33 100%);
                border:1px solid rgba(0,229,255,0.15);border-radius:12px;
                padding:28px 32px;margin-bottom:24px;">
        <div style="display:flex;align-items:center;gap:16px;">
            <div style="font-size:36px;">🎯</div>
            <div>
                <h1 style="margin:0;font-size:28px;color:#E8E0D0;font-family:serif;">
                    AI Command Center</h1>
                <p style="margin:4px 0 0;color:#5a7a9a;font-size:14px;">
                    Scout · Screen · Size · Execute · Track — Your complete trading workflow</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── WATCHLIST MANAGEMENT ──────────────────────────────────────────────
    if _WL_KEY not in st.session_state:
        st.session_state[_WL_KEY] = DEFAULT_WATCHLIST.copy()
    if _JOURNAL not in st.session_state:
        st.session_state[_JOURNAL] = []

    with st.sidebar:
        st.markdown("### 📋 Watchlist")
        wl_text = st.text_area(
            "Edit watchlist (one ticker per line)",
            value="\n".join(st.session_state[_WL_KEY]),
            height=150,
            key="cc_wl_edit",
        )
        if st.button("💾 Save Watchlist", key="cc_save_wl"):
            new_wl = [t.strip().upper() for t in wl_text.split("\n") if t.strip()]
            st.session_state[_WL_KEY] = new_wl
            st.rerun()

        st.markdown("---")
        st.markdown("##### Quick Add")
        col_us, col_se = st.columns(2)
        if col_us.button("🇺🇸 US Core", key="cc_us"):
            st.session_state[_WL_KEY] = US_WATCHLIST.copy()
            st.rerun()
        if col_se.button("🇸🇪 Nordic", key="cc_se"):
            st.session_state[_WL_KEY] = NORDIC_WATCHLIST.copy()
            st.rerun()


    # ── TAB LAYOUT ────────────────────────────────────────────────────────
    tab_signals, tab_intel, tab_chart, tab_sizer, tab_journal, tab_calendar = st.tabs([
        f"🎯 {t('cc_scan_all')}", f"🏦 {t('cc_bloomberg')}", "📊 Bloomberg Chart",
        f"📐 {t('cc_position_sizer')}", f"📓 {t('cc_trade_journal')}", f"📅 {t('cc_econ_calendar')}"
    ])

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1: AI SIGNALS — Batch scan watchlist
    # ═══════════════════════════════════════════════════════════════════════
    with tab_signals:
        wl = st.session_state[_WL_KEY]
        st.markdown(f"**Watchlist:** {', '.join(wl)} ({len(wl)} stocks)")

        if st.button("⚡ SCAN ALL SIGNALS", type="primary", key="cc_scan", use_container_width=True):
            with st.spinner(f"Scanning {len(wl)} stocks through dual AI engines..."):
                results = batch_scan(wl)
                st.session_state[_RESULTS] = results

        if _RESULTS in st.session_state and st.session_state[_RESULTS]:
            results = st.session_state[_RESULTS]

            # Top signals banner
            top3 = [r for r in results if r["conviction"] >= 60][:3]
            if top3:
                st.markdown("### 🏆 " + t("cc_top_signals") + "")
                cols = st.columns(len(top3))
                for i, sig in enumerate(top3):
                    color = SIGNAL_COLORS.get(sig["combined_signal"], "#FFB74D")
                    with cols[i]:
                        st.markdown(f"""
                        <div style="background:rgba(0,20,40,0.8);border:1px solid {color};
                                    border-radius:10px;padding:16px;text-align:center;">
                            <div style="font-size:24px;font-weight:bold;color:{color};">
                                {sig['ticker']}</div>
                            <div style="font-size:32px;font-weight:bold;color:#E8E0D0;">
                                {sig['conviction']}/100</div>
                            <div style="font-size:14px;color:{color};margin-top:4px;">
                                {sig['combined_signal']}</div>
                            <div style="font-size:12px;color:#5a7a9a;margin-top:8px;">
                                {fmt_currency(sig['price'])} · {sig['change_pct']:+.1f}%</div>
                        </div>
                        """, unsafe_allow_html=True)

            # Full results table
            st.markdown("### 📊 Full Scan Results")
            for r in results:
                if r.get("error"):
                    st.warning(f"⚠️ {r['ticker']}: {r['error']}")
                    continue

                color = SIGNAL_COLORS.get(r["combined_signal"], "#FFB74D")
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 3])
                    c1.markdown(f"**{r['ticker']}**")
                    c1.caption(f"{fmt_currency(r['price'])} ({r['change_pct']:+.1f}%)")
                    c2.metric("Technical", r["tech_signal"], f"{r['tech_confidence']}%")
                    c3.metric("Fundamental", r["fund_signal"], f"{r['fund_confidence']}%")
                    c4.metric("Conviction", f"{r['conviction']}/100")
                    c5.markdown(f"<span style='color:{color};font-weight:bold;font-size:18px;'>"
                                f"{r['combined_signal']}</span>", unsafe_allow_html=True)
                    # Evidence
                    if r["tech_evidence"]:
                        c5.caption(" · ".join(r["tech_evidence"][:2]))
                    st.divider()
        else:
            st.info("Click **⚡ SCAN ALL SIGNALS** to analyze your watchlist with dual AI engines.")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2: BLOOMBERG INTELLIGENCE — FMP + yfinance + Groq AI synthesis
    # ═══════════════════════════════════════════════════════════════════════
    with tab_intel:
        st.markdown("### 🏦 Bloomberg Intelligence")
        st.caption("Analyst grades · Price targets · Earnings history · Insider activity · Institutional flow · AI Brief")

        intel_ticker = st.text_input("Ticker for deep intelligence", value="AAPL", key="cc_intel_ticker")

        if st.button("🔍 Run Full Intelligence Scan", type="primary", key="cc_intel_scan", use_container_width=True):
            with st.spinner(f"Fetching Bloomberg-grade data for {intel_ticker}..."):
                from fmp_enrichment import FMPEnrichment
                enrich = FMPEnrichment()
                data = enrich.full_enrichment(intel_ticker)
                st.session_state["cc_intel_data"] = data

        if "cc_intel_data" in st.session_state:
            data = st.session_state["cc_intel_data"]
            signals = data.get("signals", {})
            profile = data.get("profile", {})

            # ── Company header ────────────────────────────────────────
            if profile:
                mc = profile.get("marketCap", 0)
                mc_str = f"${mc/1e9:.1f}B" if mc > 1e9 else f"${mc/1e6:.0f}M"
                st.markdown(f"""
                <div style="background:rgba(0,20,40,0.8);border:1px solid rgba(0,229,255,0.2);
                            border-radius:10px;padding:16px;margin-bottom:16px;">
                    <div style="font-size:22px;font-weight:bold;color:#E8E0D0;">
                        {profile.get('companyName', data['ticker'])} ({data['ticker']})</div>
                    <div style="color:#5a7a9a;font-size:13px;">
                        {profile.get('sector', '')} · {profile.get('industry', '')} · Mkt Cap: {mc_str}</div>
                </div>
                """, unsafe_allow_html=True)

            # ── Signal cards row ──────────────────────────────────────
            sc1, sc2, sc3, sc4 = st.columns(4)

            # Analyst sentiment
            sent = signals.get("analyst_sentiment", "N/A")
            sent_color = "#00E676" if sent == "BULLISH" else "#EF5350" if sent == "BEARISH" else "#FFB74D"
            sc1.markdown(f"<div style='text-align:center;'><div style='color:#5a7a9a;font-size:11px;'>ANALYST SENTIMENT</div>"
                        f"<div style='color:{sent_color};font-size:20px;font-weight:bold;'>{sent}</div>"
                        f"<div style='color:#5a7a9a;font-size:11px;'>↑{signals.get('recent_upgrades',0)} ↓{signals.get('recent_downgrades',0)}</div></div>",
                        unsafe_allow_html=True)

            # Price target upside
            upside = signals.get("target_upside_pct", 0)
            up_color = "#00E676" if upside > 10 else "#EF5350" if upside < -10 else "#FFB74D"
            sc2.markdown(f"<div style='text-align:center;'><div style='color:#5a7a9a;font-size:11px;'>TARGET UPSIDE</div>"
                        f"<div style='color:{up_color};font-size:20px;font-weight:bold;'>{upside:+.1f}%</div>"
                        f"<div style='color:#5a7a9a;font-size:11px;'>Consensus: ${signals.get('target_consensus',0):.0f}</div></div>",
                        unsafe_allow_html=True)

            # Valuation
            val = signals.get("valuation", "N/A")
            val_color = "#00E676" if val == "CHEAP" else "#EF5350" if val == "EXPENSIVE" else "#FFB74D"
            sc3.markdown(f"<div style='text-align:center;'><div style='color:#5a7a9a;font-size:11px;'>VALUATION</div>"
                        f"<div style='color:{val_color};font-size:20px;font-weight:bold;'>{val}</div>"
                        f"<div style='color:#5a7a9a;font-size:11px;'>P/E: {signals.get('pe_ratio','?')} · ROE: {signals.get('roe','?')}%</div></div>",
                        unsafe_allow_html=True)

            # Earnings surprise
            beats = signals.get("consecutive_beats", 0)
            beats_color = "#00E676" if beats >= 3 else "#FFB74D"
            sc4.markdown(f"<div style='text-align:center;'><div style='color:#5a7a9a;font-size:11px;'>EARNINGS STREAK</div>"
                        f"<div style='color:{beats_color};font-size:20px;font-weight:bold;'>{beats}/4 BEATS</div>"
                        f"<div style='color:#5a7a9a;font-size:11px;'>Avg surprise: {signals.get('avg_eps_surprise_pct','?')}%</div></div>",
                        unsafe_allow_html=True)

            st.markdown("---")

            # ── Detailed sections ─────────────────────────────────────
            col_left, col_right = st.columns(2)

            with col_left:
                # Analyst grades
                grades = data.get("grades", [])
                if grades:
                    st.markdown("**📊 Recent Analyst Grades**")
                    for g in grades[:8]:
                        grade = g.get("newGrade", "?")
                        company = g.get("gradingCompany", "?")
                        date = g.get("date", "?")[:10]
                        g_color = "#00E676" if "buy" in grade.lower() or "outperform" in grade.lower() else \
                                  "#EF5350" if "sell" in grade.lower() or "underperform" in grade.lower() else "#FFB74D"
                        st.markdown(f"<span style='color:{g_color};'>●</span> {date} — **{company}**: {grade}",
                                   unsafe_allow_html=True)

                # Price target
                pt = data.get("price_target", {})
                if pt:
                    st.markdown("**🎯 Analyst Price Targets**")
                    st.markdown(f"High: **${pt.get('targetHigh',0):.0f}** · "
                               f"Consensus: **${pt.get('targetConsensus',0):.0f}** · "
                               f"Low: **${pt.get('targetLow',0):.0f}**")

            with col_right:
                # Institutional holders
                inst_df = data.get("institutional", pd.DataFrame())
                if not inst_df.empty:
                    st.markdown("**🏦 Top Institutional Holders**")
                    display_cols = [c for c in inst_df.columns if c in ["Holder", "Shares", "Value", "% Out"]]
                    if display_cols:
                        st.dataframe(inst_df[display_cols].head(8), use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(inst_df.head(8), use_container_width=True, hide_index=True)

                # Insider activity
                ins_df = data.get("insider", pd.DataFrame())
                if not ins_df.empty:
                    st.markdown("**👤 Recent Insider Transactions**")
                    display_cols = [c for c in ins_df.columns if c in ["Insider Trading", "Transaction", "Value", "Shares"]]
                    if display_cols:
                        st.dataframe(ins_df[display_cols].head(8), use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(ins_df.head(8), use_container_width=True, hide_index=True)

            # ── Earnings history ──────────────────────────────────────
            earnings = data.get("earnings_history", [])
            if earnings:
                st.markdown("**📈 Earnings History (EPS Actual vs Estimated)**")
                eps_data = []
                for e in earnings[:8]:
                    actual = e.get("epsActual")
                    estimated = e.get("epsEstimated")
                    surprise = ""
                    if actual is not None and estimated is not None and estimated != 0:
                        s = ((actual - estimated) / abs(estimated)) * 100
                        surprise = f"{s:+.1f}%"
                    eps_data.append({
                        "Date": e.get("date", "?")[:10],
                        "EPS Actual": actual,
                        "EPS Estimated": estimated,
                        "Surprise": surprise,
                    })
                st.dataframe(pd.DataFrame(eps_data), use_container_width=True, hide_index=True)

            # ── News headlines ────────────────────────────────────────
            news = data.get("news", [])
            if news:
                st.markdown("**📰 Latest Headlines**")
                for n in news[:5]:
                    title = n.get("title", "?")
                    link = n.get("link", "#")
                    publisher = n.get("publisher", "?")
                    st.markdown(f"• [{title}]({link}) — *{publisher}*")

            # ── AI Intelligence Brief ─────────────────────────────────
            st.markdown("---")
            st.markdown("### 🧠 AI Intelligence Brief")
            if st.button("Generate AI Brief (Groq LLaMA 3.3 70B)", key="cc_ai_brief"):
                with st.spinner("Generating Bloomberg-grade intelligence brief..."):
                    from fmp_enrichment import FMPEnrichment
                    enrich = FMPEnrichment()
                    brief = enrich.ai_intelligence_brief(data["ticker"], data)
                    st.markdown(brief)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: BLOOMBERG CHART — Multi-panel + Multi-timeframe + Overlays
    # ═══════════════════════════════════════════════════════════════════════
    with tab_chart:
        st.markdown("### 📊 Bloomberg-Grade Chart")
        st.caption("Multi-panel (Price+Volume+RSI+MACD) · Multi-timeframe (D/W/M) · Pattern overlays · Trade levels")

        ch_ticker = st.text_input("Ticker", value="ERIC-B.ST", key="cc_ch_ticker")
        ch_period = st.selectbox("Period", ["3mo", "6mo", "1y", "2y"], index=1, key="cc_ch_period")

        ch_c1, ch_c2, ch_c3, ch_c4 = st.columns(4)
        ch_ema = ch_c1.checkbox("EMA 9/21/55", value=True, key="cc_ch_ema")
        ch_bb = ch_c2.checkbox("Bollinger Bands", value=False, key="cc_ch_bb")
        ch_sr = ch_c3.checkbox("Support/Resistance", value=True, key="cc_ch_sr")
        ch_patterns = ch_c4.checkbox("Pattern Overlays", value=True, key="cc_ch_pat")

        if st.button("📊 Generate Bloomberg Chart", type="primary", key="cc_ch_gen", use_container_width=True):
            with st.spinner(f"Rendering institutional chart for {ch_ticker}..."):
                try:
                    import yfinance as _yf
                    from bloomberg_charts import (
                        create_institutional_chart, add_harmonic_overlay,
                        add_elliott_overlay, add_support_resistance,
                        add_trade_levels, create_multi_timeframe,
                        BLOOMBERG_PLOTLY_CONFIG,
                    )

                    df = _yf.download(ch_ticker, period=ch_period, interval="1d", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [c.lower() for c in df.columns]

                    if df.empty:
                        st.error(f"No data for {ch_ticker}")
                    else:
                        # 1. Institutional multi-panel chart
                        fig = create_institutional_chart(
                            df, ch_ticker, show_ema=ch_ema, show_bb=ch_bb,
                            show_volume=True, show_rsi=True, show_macd=True,
                        )

                        # 2. Add support/resistance levels
                        if ch_sr:
                            fig = add_support_resistance(fig, df)

                        # 3. Add pattern overlays (harmonics + Elliott)
                        if ch_patterns:
                            try:
                                from engine.structure.swings import find_pivots, enforce_alternation
                                from engine.analysis.harmonics import HarmonicEngine
                                from engine.analysis.elliott import discover_impulses

                                raw = find_pivots(df, order=2)
                                alt = enforce_alternation(raw)
                                piv_prices = alt["close"].values.astype(float)
                                piv_dates = alt.index

                                # Harmonic overlays
                                h_engine = HarmonicEngine()
                                h_results = h_engine.scan(list(piv_prices))
                                for h in h_results[:3]:  # max 3 patterns on chart
                                    pts = list(h.points)
                                    n_pts = len(pts)
                                    # Find dates for pattern points
                                    if n_pts <= len(piv_dates):
                                        pt_dates = list(piv_dates[:n_pts])
                                        fig = add_harmonic_overlay(
                                            fig, h.pattern_name, pts, pt_dates, h.is_bullish
                                        )

                                # Elliott overlays
                                waves = discover_impulses(list(piv_prices), min_wave1_pct=0.01)
                                for w in waves[:2]:  # max 2 wave structures on chart
                                    si = w["start_index"]
                                    w_pts = piv_prices[si:si+6]
                                    w_dates = piv_dates[si:si+6]
                                    if len(w_pts) >= 5:
                                        fig = add_elliott_overlay(
                                            fig, list(w_pts[:6]), list(w_dates[:6]), w["is_bullish"]
                                        )

                                if h_results:
                                    st.success(f"✅ {len(h_results)} harmonic pattern(s) overlaid on chart")
                                if waves:
                                    st.success(f"✅ {len(waves)} Elliott wave structure(s) overlaid on chart")
                            except Exception as e:
                                st.caption(f"Pattern overlay: {e}")

                        st.plotly_chart(fig, use_container_width=True, config=BLOOMBERG_PLOTLY_CONFIG)

                        # 4. Multi-timeframe view
                        st.markdown("---")
                        st.markdown("### 📐 Multi-Timeframe View (Daily · Weekly · Monthly)")
                        with st.spinner("Loading multi-timeframe data..."):
                            mtf_fig = create_multi_timeframe(ch_ticker, show_ema=ch_ema)
                            st.plotly_chart(mtf_fig, use_container_width=True, config=BLOOMBERG_PLOTLY_CONFIG)

                except Exception as e:
                    st.error(f"Chart error: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: POSITION SIZER — ATR + Fixed-Fractional + Kelly
    # ═══════════════════════════════════════════════════════════════════════
    with tab_sizer:
        st.markdown("### 📐 Position Sizing Calculator")
        st.caption("Institutional-grade sizing: never risk more than you can afford to lose.")

        profile = get_locale_profile()
        cur_symbol = profile["currency_symbol"]

        sc1, sc2 = st.columns(2)
        account = sc1.number_input(f"Account Size ({cur_symbol})", value=100000.0, step=1000.0, key="cc_acct")
        risk_pct = sc2.number_input("Risk per Trade (%)", value=1.0, min_value=0.1, max_value=10.0, step=0.1, key="cc_risk")

        sc3, sc4 = st.columns(2)
        entry = sc3.number_input("Entry Price", value=150.0, step=0.01, key="cc_entry")
        stop = sc4.number_input("Stop-Loss Price", value=145.0, step=0.01, key="cc_stop")

        target = st.number_input("Target Price (optional — for R:R calc)", value=0.0, step=0.01, key="cc_target")

        if st.button("📐 Calculate Position Size", key="cc_calc_size"):
            if entry <= 0 or stop <= 0:
                st.error("Entry and stop prices must be positive.")
            elif abs(entry - stop) < 0.001:
                st.error("Entry and stop prices must be different.")
            else:
                result = calc_position_size(account, risk_pct, entry, stop)
                
                st.markdown("---")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Shares", f"{result['shares']:,}")
                m2.metric("Risk Amount", fmt_currency(result["risk_amount"]))
                m3.metric("Position Value", fmt_currency(result["position_value"]))
                m4.metric("% of Account", f"{result['pct_of_account']:.1f}%")

                # Risk/Reward ratio
                if target > 0 and result["risk_per_share"] > 0:
                    reward_per_share = abs(target - entry)
                    rr_ratio = reward_per_share / result["risk_per_share"]
                    potential_profit = result["shares"] * reward_per_share

                    r1, r2, r3 = st.columns(3)
                    rr_color = "#00E676" if rr_ratio >= 2.0 else "#FFB74D" if rr_ratio >= 1.0 else "#EF5350"
                    r1.markdown(f"**Risk/Reward:** <span style='color:{rr_color};font-size:24px;'>"
                                f"{rr_ratio:.1f}R</span>", unsafe_allow_html=True)
                    r2.metric("Potential Profit", fmt_currency(potential_profit))
                    r3.metric("Risk per Share", fmt_currency(result["risk_per_share"]))

                    if rr_ratio < 2.0:
                        st.warning("⚠️ Van Tharp: 'The trade should offer at least 2R. Below 2R, the math doesn't favor you.'")
                    else:
                        st.success(f"✅ {rr_ratio:.1f}R meets the minimum 2R threshold. Risk is defined.")

                # The 3-5-7 rule check
                if result["pct_of_account"] > 5:
                    st.warning(f"⚠️ Position is {result['pct_of_account']:.1f}% of account — exceeds the 5% exposure rule.")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: TRADE JOURNAL — Log, Track, Review
    # ═══════════════════════════════════════════════════════════════════════
    with tab_journal:
        st.markdown("### 📓 Trade Journal")
        st.caption("Track every trade. Compute R-multiples. Learn from results.")

        # Trade entry form
        with st.expander("➕ Log New Trade", expanded=False):
            jc1, jc2, jc3 = st.columns(3)
            j_ticker = jc1.text_input("Ticker", key="cc_j_ticker")
            j_dir = jc2.selectbox("Direction", ["Long", "Short"], key="cc_j_dir")
            j_date = jc3.date_input("Date", key="cc_j_date")

            jc4, jc5, jc6 = st.columns(3)
            j_entry = jc4.number_input("Entry Price", value=0.0, step=0.01, key="cc_j_entry")
            j_exit = jc5.number_input("Exit Price (0 if open)", value=0.0, step=0.01, key="cc_j_exit")
            j_shares = jc6.number_input("Shares", value=0, step=1, key="cc_j_shares")

            jc7, jc8 = st.columns(2)
            j_stop = jc7.number_input("Initial Stop", value=0.0, step=0.01, key="cc_j_stop")
            j_setup = jc8.text_input("Setup Type", placeholder="e.g. Breakout, Pullback, Harmonic", key="cc_j_setup")
            j_notes = st.text_area("Notes / Lessons", key="cc_j_notes", height=80)

            if st.button("📝 Save Trade", key="cc_j_save"):
                if j_ticker and j_entry > 0 and j_shares > 0:
                    # Calculate R-multiple
                    risk_per_share = abs(j_entry - j_stop) if j_stop > 0 else 0
                    if j_exit > 0 and risk_per_share > 0:
                        if j_dir == "Long":
                            pnl = (j_exit - j_entry) * j_shares
                        else:
                            pnl = (j_entry - j_exit) * j_shares
                        r_multiple = round(pnl / (risk_per_share * j_shares), 2) if risk_per_share > 0 else 0
                    else:
                        pnl = 0
                        r_multiple = 0

                    trade = {
                        "date": str(j_date),
                        "ticker": j_ticker.upper(),
                        "direction": j_dir,
                        "entry": j_entry,
                        "exit": j_exit,
                        "shares": j_shares,
                        "stop": j_stop,
                        "setup": j_setup,
                        "notes": j_notes,
                        "pnl": round(pnl, 2),
                        "r_multiple": r_multiple,
                    }
                    st.session_state[_JOURNAL].append(trade)
                    st.success(f"✅ Trade logged: {j_ticker} {j_dir} — P&L: {fmt_currency(pnl)} ({r_multiple}R)")
                else:
                    st.warning("Fill in ticker, entry price, and shares.")

        # Display journal
        journal = st.session_state.get(_JOURNAL, [])
        if journal:
            df_j = pd.DataFrame(journal)

            # Stats
            closed = df_j[df_j["exit"] > 0]
            if len(closed) > 0:
                wins = closed[closed["pnl"] > 0]
                losses = closed[closed["pnl"] <= 0]
                win_rate = (len(wins) / len(closed)) * 100
                avg_r = closed["r_multiple"].mean()
                total_pnl = closed["pnl"].sum()
                expectancy = avg_r  # simplified expectancy

                sm1, sm2, sm3, sm4 = st.columns(4)
                sm1.metric("Total Trades", len(closed))
                sm2.metric("Win Rate", f"{win_rate:.0f}%")
                sm3.metric("Avg R-Multiple", f"{avg_r:.2f}R")
                sm4.metric("Total P&L", fmt_currency(total_pnl))

                if avg_r < 0:
                    st.error("❌ Negative expectancy. Review your trade selection and risk management.")
                elif avg_r >= 1.0:
                    st.success(f"✅ Positive expectancy ({avg_r:.2f}R). Your edge is working.")

            # Table
            st.dataframe(df_j[["date", "ticker", "direction", "entry", "exit", "shares",
                               "pnl", "r_multiple", "setup"]].sort_values("date", ascending=False),
                        use_container_width=True, hide_index=True)

            # Export
            csv = df_j.to_csv(index=False)
            st.download_button("📥 Export Journal CSV", csv, "trade_journal.csv", "text/csv")
        else:
            st.info("No trades logged yet. Use the form above to start tracking.")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: ECONOMIC CALENDAR — FRED + AI interpretation
    # ═══════════════════════════════════════════════════════════════════════
    with tab_calendar:
        st.markdown("### 📅 Key Economic Indicators")
        st.caption("Live macro data from FRED — the same source Bloomberg uses.")

        # Key FRED series that move markets
        FRED_SERIES = {
            "T10Y2Y":   {"name": "10Y-2Y Yield Spread",  "impact": "HIGH",   "desc": "Yield curve — inversion signals recession"},
            "DFF":      {"name": "Fed Funds Rate",        "impact": "HIGH",   "desc": "Federal Reserve target rate"},
            "CPIAUCSL": {"name": "CPI (Inflation)",       "impact": "HIGH",   "desc": "Consumer Price Index — inflation gauge"},
            "UNRATE":   {"name": "Unemployment Rate",     "impact": "HIGH",   "desc": "U.S. unemployment — labor market health"},
            "VIXCLS":   {"name": "VIX (Fear Index)",      "impact": "MEDIUM", "desc": "CBOE Volatility Index — market fear gauge"},
            "DTWEXBGS": {"name": "USD Index (Broad)",     "impact": "MEDIUM", "desc": "Trade-weighted USD — currency strength"},
            "M2SL":     {"name": "M2 Money Supply",       "impact": "MEDIUM", "desc": "Broad money supply — liquidity indicator"},
            "GDP":      {"name": "Real GDP",              "impact": "HIGH",   "desc": "Gross Domestic Product — economic growth"},
        }

        if st.button("📊 Load Economic Data", key="cc_econ"):
            with st.spinner("Fetching FRED data..."):
                try:
                    from data_clients import fred_get
                    
                    for series_id, meta in FRED_SERIES.items():
                        try:
                            # <- FIXED [Council]: FRED needs series/observations endpoint, not raw series_id
                            raw = fred_get("series/observations",
                                           series_id=series_id,
                                           sort_order="desc",
                                           limit="2")
                            observations = raw.get("observations", []) if isinstance(raw, dict) else []
                            
                            if observations and len(observations) >= 1:
                                val = float(observations[0].get("value", 0))
                                prev = float(observations[1].get("value", val)) if len(observations) > 1 else val

                                change = float(val) - float(prev) if prev else 0
                                impact_color = "#EF5350" if meta["impact"] == "HIGH" else "#FFB74D"

                                c1, c2, c3 = st.columns([3, 2, 2])
                                c1.markdown(f"**{meta['name']}**")
                                c1.caption(meta["desc"])
                                c2.metric("Current", f"{float(val):.2f}", f"{change:+.2f}")
                                c3.markdown(f"<span style='color:{impact_color};font-weight:bold;'>"
                                            f"Impact: {meta['impact']}</span>", unsafe_allow_html=True)
                                st.divider()
                        except Exception as e:
                            st.caption(f"⚠️ {meta['name']}: {e}")
                except ImportError:
                    st.error("FRED client not available. Check data_clients.py and FRED_API_KEY in .env")
        else:
            st.info("Click **📊 Load Economic Data** to fetch live macro indicators from FRED.")

        # AI Market Regime Summary — DUAL: Global + Swedish
        st.markdown("---")
        st.markdown("### 🧠 AI Market Regime Analysis")
        
        col_global, col_swedish = st.columns(2)
        
        with col_global:
            st.markdown("#### 🌍 Global Markets")
            if st.button("Generate Global Regime", key="cc_regime_global"):
                with st.spinner("Analyzing global markets via Groq..."):
                    try:
                        from data_clients import groq_client
                        response = groq_client().chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {"role": "system", "content": (
                                    "You are a senior global macro strategist. Analyze the current "
                                    "international market regime. Cover: (1) US markets risk-on/off, "
                                    "(2) Fed policy direction, (3) VIX regime, (4) USD strength, "
                                    "(5) EU/Asia macro picture, (6) Key events this week. "
                                    "Be specific and actionable. 200 words max."
                                )},
                                {"role": "user", "content": "What is the current global market regime and what should international traders focus on this week?"},
                            ],
                            temperature=0.7,
                            max_tokens=500,
                        )
                        st.markdown(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"Groq error: {e}")
        
        with col_swedish:
            st.markdown("#### 🇸🇪 Swedish / OMX Market")
            if st.button("Generate Swedish Regime", key="cc_regime_swedish"):
                with st.spinner("Analyzing OMX Stockholm via Groq..."):
                    try:
                        from data_clients import groq_client
                        response = groq_client().chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {"role": "system", "content": (
                                    "You are a senior Nordic equity strategist specializing in "
                                    "OMX Stockholm and Scandinavian markets. Analyze the current "
                                    "Swedish market regime. Cover: (1) OMX30 trend status, "
                                    "(2) Riksbank policy direction and SEK outlook, "
                                    "(3) Key Swedish sectors (industrials: Volvo, Sandvik, Atlas Copco; "
                                    "financials: SEB, Handelsbanken; tech: Ericsson, Hexagon), "
                                    "(4) Nordic housing market impact on banks, "
                                    "(5) Export-dependent companies vs SEK weakness/strength, "
                                    "(6) Key OMX events this week. "
                                    "Be specific and actionable. 200 words max."
                                )},
                                {"role": "user", "content": "What is the current OMX Stockholm regime and what should Swedish market traders focus on this week?"},
                            ],
                            temperature=0.7,
                            max_tokens=500,
                        )
                        st.markdown(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"Groq error: {e}")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

main()
