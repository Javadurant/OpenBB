"""
pages/trading_toolkit.py
═══════════════════════════════════════════════════════════════════════════════
TRADING TOOLKIT — Surfaces 5 Hidden Engines

COUNCIL MANDATE: "5 engines exist as code with NO user-facing pages.
Build UI for all 5: backtest, risk, portfolio optimizer, predictions, alerts."

TAB 1: 📈 Backtester       — engine/backtest.py → equity curve, win rate, drawdown
TAB 2: 🛡️ Risk Dashboard   — engine/risk/ → dynamic SL/TP, position sizing, exposure check
TAB 3: ⚖️ Portfolio Optimizer — engine/portfolio_optimizer.py → Black-Litterman weights
TAB 4: 🔮 Predictions      — engine/prediction/ → direction, probability, confidence
TAB 5: 🔔 Alerts Setup     — engine/notifications/ → Telegram + Gmail dispatch config

NO NEW DEPENDENCIES — uses only existing engines, yfinance, Groq.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from translations import t, inject_rtl_css, fmt_number, fmt_currency, get_locale_profile

logger = logging.getLogger("TradingToolkit")


def main():
    inject_rtl_css()

    st.markdown("""
    <div style="background:linear-gradient(135deg,#001020 0%,#002040 100%);
                border:1px solid rgba(0,229,255,0.15);border-radius:12px;
                padding:24px 28px;margin-bottom:20px;">
        <h1 style="margin:0;font-size:26px;color:#E8E0D0;font-family:serif;">
            🛠️ Trading Toolkit</h1>
        <p style="margin:4px 0 0;color:#5a7a9a;font-size:13px;">
            Backtest · Risk · Optimize · Predict · Alert — Five institutional engines, one page</p>
    </div>
    """, unsafe_allow_html=True)

    tab_bt, tab_risk, tab_port, tab_pred, tab_alert = st.tabs([
        f"📈 {t('tt_backtester')}", f"🛡️ {t('tt_risk_dashboard')}", f"⚖️ {t('tt_portfolio')}",
        f"🔮 {t('tt_predictions')}", f"🔔 {t('tt_alerts')}"
    ])

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1: BACKTESTER
    # ═══════════════════════════════════════════════════════════════════════
    with tab_bt:
        st.markdown("### 📈 " + t("tt_backtester") + "")
        st.caption("Run your signal engine against historical data. See equity curve, win rate, max drawdown.")

        bt_c1, bt_c2, bt_c3 = st.columns(3)
        bt_ticker = bt_c1.text_input("Ticker", value="ERIC-B.ST", key="tt_bt_ticker")
        bt_period = bt_c2.selectbox("Period", ["3mo", "6mo", "1y", "2y", "5y"], index=2, key="tt_bt_period")
        bt_capital = bt_c3.number_input("Starting Capital ($)", value=10000.0, step=1000.0, key="tt_bt_cap")

        if st.button("🚀 Run Backtest", type="primary", key="tt_bt_run", use_container_width=True):
            with st.spinner(f"Backtesting {bt_ticker} over {bt_period}..."):
                try:
                    df = yf.download(bt_ticker, period=bt_period, interval="1d", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [c.lower() for c in df.columns]

                    if df.empty or len(df) < 20:
                        st.error(f"Insufficient data for {bt_ticker}")
                    else:
                        from technical_signal_engine import TechnicalSignalEngine
                        tech = TechnicalSignalEngine()
                        sig = tech.generate(bt_ticker)
                        sig_dict = {"signal": getattr(sig, "signal", "HOLD")}

                        from engine.backtest import run_backtest
                        result = run_backtest(df, sig_dict, initial_cap=bt_capital)

                        # Display metrics
                        st.markdown("#### Results")
                        if isinstance(result.get("results"), pd.DataFrame) and not result["results"].empty:
                            st.dataframe(result["results"], use_container_width=True, hide_index=True)

                        # Equity curve chart
                        eq = result.get("equity_curve", [])
                        if eq:
                            import plotly.graph_objects as go
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                y=eq, mode="lines", name="Equity",
                                line=dict(color="#00E5FF", width=2),
                            ))
                            fig.update_layout(
                                template="plotly_dark",
                                title=f"Equity Curve — {bt_ticker}",
                                yaxis_title="Equity ($)",
                                xaxis_title="Bar",
                                height=350,
                                margin=dict(l=40, r=20, t=40, b=30),
                                paper_bgcolor="#000d1a",
                                plot_bgcolor="#000d1a",
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        # Trade log
                        trades = result.get("trade_log", [])
                        if trades:
                            st.markdown(f"**{len(trades)} trades executed**")
                            st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)

                except Exception as e:
                    st.error(f"Backtest error: {e}")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2: RISK DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════
    with tab_risk:
        st.markdown("### 🛡️ " + t("tt_risk_dashboard") + "")
        st.caption("Dynamic stop-loss/take-profit from ATR + harmonic PRZ. Institutional position sizing.")

        rk_ticker = st.text_input("Ticker", value="ERIC-B.ST", key="tt_rk_ticker")

        if st.button("🛡️ Analyze Risk", type="primary", key="tt_rk_run", use_container_width=True):
            with st.spinner(f"Computing risk parameters for {rk_ticker}..."):
                try:
                    df = yf.download(rk_ticker, period="6mo", interval="1d", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [c.lower() for c in df.columns]

                    if df.empty:
                        st.error("No data")
                    else:
                        from engine.risk.risk_management import get_dynamic_risk_params, calculate_position_size
                        last_price = float(df["close"].iloc[-1])

                        # Dynamic risk params for both directions
                        buy_params = get_dynamic_risk_params(df, "BUY")
                        sell_params = get_dynamic_risk_params(df, "SELL")

                        st.markdown("#### Long (BUY) Risk Parameters")
                        rc1, rc2, rc3, rc4 = st.columns(4)
                        rc1.metric("Entry", fmt_currency(buy_params["entry"]))
                        rc2.metric("Stop Loss", fmt_currency(buy_params["stop_loss"]))
                        rc3.metric("Take Profit", fmt_currency(buy_params["take_profit"]))
                        prz = buy_params.get("harmonic_prz")
                        rc4.metric("Harmonic PRZ", fmt_currency(prz) if prz else "None")

                        rr_long = abs(buy_params["take_profit"] - last_price) / abs(last_price - buy_params["stop_loss"]) if abs(last_price - buy_params["stop_loss"]) > 0.001 else 0
                        rr_color = "#00E676" if rr_long >= 2.0 else "#FFB74D" if rr_long >= 1.0 else "#EF5350"
                        st.markdown(f"**Risk/Reward:** <span style='color:{rr_color};font-size:22px;'>{rr_long:.1f}R</span>", unsafe_allow_html=True)

                        st.markdown("---")
                        st.markdown("#### Short (SELL) Risk Parameters")
                        sc1, sc2, sc3, sc4 = st.columns(4)
                        sc1.metric("Entry", fmt_currency(sell_params["entry"]))
                        sc2.metric("Stop Loss", fmt_currency(sell_params["stop_loss"]))
                        sc3.metric("Take Profit", fmt_currency(sell_params["take_profit"]))
                        prz_s = sell_params.get("harmonic_prz")
                        sc4.metric("Harmonic PRZ", fmt_currency(prz_s) if prz_s else "None")

                        st.markdown("---")
                        st.markdown("#### Position Sizing")
                        ps_c1, ps_c2 = st.columns(2)
                        acct = ps_c1.number_input("Account Size", value=100000.0, step=1000.0, key="tt_rk_acct")
                        risk_pct = ps_c2.number_input("Risk %", value=0.02, step=0.005, format="%.3f", key="tt_rk_risk")

                        pos = calculate_position_size(acct, risk_pct, last_price, buy_params["stop_loss"])
                        pm1, pm2, pm3, pm4 = st.columns(4)
                        pm1.metric("Units", f"{pos['units']:.0f}")
                        pm2.metric("Risk Amount", fmt_currency(pos["total_risk_cash"]))
                        pm3.metric("Position Value", fmt_currency(pos["position_value"]))
                        pm4.metric("Risk/Share", fmt_currency(pos["risk_per_share"]))

                except Exception as e:
                    st.error(f"Risk analysis error: {e}")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3: PORTFOLIO OPTIMIZER
    # ═══════════════════════════════════════════════════════════════════════
    with tab_port:
        st.markdown("### ⚖️ " + t("tt_portfolio") + "")
        st.caption("Black-Litterman inspired. Blends inverse volatility with institutional alpha scores.")

        port_tickers = st.text_input(
            "Tickers (comma-separated)",
            value="ERIC-B.ST, VOLV-B.ST, SAND.ST, ABB.ST, SEB-A.ST",
            key="tt_port_tickers",
        )

        if st.button("⚖️ Optimize Portfolio", type="primary", key="tt_port_run", use_container_width=True):
            with st.spinner("Optimizing portfolio weights..."):
                try:
                    tickers = [t.strip().upper() for t in port_tickers.split(",") if t.strip()]
                    if len(tickers) < 2:
                        st.error("Need at least 2 tickers.")
                    else:
                        from engine.portfolio_optimizer import PortfolioOptimizer, get_portfolio_summary
                        from technical_signal_engine import TechnicalSignalEngine

                        tech_engine = TechnicalSignalEngine()
                        assets_data = {}

                        for tk in tickers:
                            try:
                                df = yf.download(tk, period="1y", interval="1d", progress=False)
                                if isinstance(df.columns, pd.MultiIndex):
                                    df.columns = df.columns.get_level_values(0)
                                if df.empty or len(df) < 30:
                                    continue
                                returns = df["Close"].pct_change().dropna()
                                sig = tech_engine.generate(tk)
                                score = getattr(sig, "score", 50) / 100.0
                                assets_data[tk] = {"score": score, "returns": returns}
                            except Exception:
                                continue

                        if len(assets_data) < 2:
                            st.error("Insufficient data for optimization.")
                        else:
                            optimizer = PortfolioOptimizer(max_exposure_per_asset=0.30, total_gross_limit=1.0)
                            weights_df = optimizer.calculate_weights(assets_data)

                            if not weights_df.empty:
                                compliant = optimizer.check_compliance(weights_df)
                                status = "✅ COMPLIANT" if compliant else "❌ VIOLATION"
                                st.markdown(f"**Compliance:** {status}")
                                st.markdown(f"**Summary:** {get_portfolio_summary(weights_df)}")

                                st.dataframe(weights_df, use_container_width=True, hide_index=True)

                                # Pie chart
                                import plotly.express as px
                                fig = px.pie(
                                    weights_df, values="Optimal_Weight", names="Symbol",
                                    title="Optimal Portfolio Allocation",
                                    color_discrete_sequence=["#00E5FF", "#00E676", "#FFB74D", "#EF5350", "#AB47BC", "#42A5F5"],
                                )
                                fig.update_layout(
                                    template="plotly_dark",
                                    paper_bgcolor="#000d1a",
                                    plot_bgcolor="#000d1a",
                                    height=350,
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.warning("Optimizer returned no weights.")

                except Exception as e:
                    st.error(f"Portfolio optimization error: {e}")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4: PREDICTIONS
    # ═══════════════════════════════════════════════════════════════════════
    with tab_pred:
        st.markdown("### 🔮 " + t("tt_predictions") + "")
        st.caption("Direction probability from technicals + harmonics + RSI. ML-validated scenarios.")

        pr_ticker = st.text_input("Ticker", value="ERIC-B.ST", key="tt_pr_ticker")

        if st.button("🔮 Generate Prediction", type="primary", key="tt_pr_run", use_container_width=True):
            with st.spinner(f"Generating prediction for {pr_ticker}..."):
                try:
                    df = yf.download(pr_ticker, period="6mo", interval="1d", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [c.lower() for c in df.columns]

                    if df.empty:
                        st.error("No data")
                    else:
                        # Compute RSI for prediction input
                        delta = df["close"].diff()
                        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
                        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
                        rs = gain / loss.replace(0, np.nan)
                        rsi = 100 - (100 / (1 + rs))
                        current_rsi = float(rsi.iloc[-1]) if not rsi.empty else 50.0

                        # Get technical signal for bias
                        from technical_signal_engine import TechnicalSignalEngine
                        sig = TechnicalSignalEngine().generate(pr_ticker)
                        tech_signal = getattr(sig, "signal", "HOLD")
                        bias_map = {"STRONG BUY": "BULLISH", "BUY": "BULLISH",
                                    "SELL": "BEARISH", "STRONG SELL": "BEARISH"}
                        bias = bias_map.get(tech_signal, "NEUTRAL")

                        # Get harmonic patterns
                        from engine.structure.swings import find_pivots, enforce_alternation
                        from engine.analysis.harmonics import HarmonicEngine
                        pivots = find_pivots(df, order=2)
                        alt = enforce_alternation(pivots)
                        piv_prices = alt["close"].values.astype(float)
                        h_engine = HarmonicEngine()
                        harmonics = h_engine.scan(list(piv_prices))
                        h_data = [{"is_bullish": h.is_bullish, "terminal_confirmed": True} for h in harmonics]

                        from engine.prediction.engine import predict_scenarios
                        pred = predict_scenarios({
                            "close": float(df["close"].iloc[-1]),
                            "rsi": current_rsi,
                            "bias": bias,
                            "harmonics": h_data,
                        })

                        # Display prediction
                        dir_color = "#00E676" if pred.direction == "bullish" else "#EF5350" if pred.direction == "bearish" else "#FFB74D"
                        conf_color = "#00E676" if pred.confidence == "high" else "#FFB74D" if pred.confidence == "medium" else "#EF5350"

                        pc1, pc2, pc3 = st.columns(3)
                        pc1.markdown(f"<div style='text-align:center;'>"
                                    f"<div style='color:#5a7a9a;font-size:11px;'>DIRECTION</div>"
                                    f"<div style='color:{dir_color};font-size:28px;font-weight:bold;'>"
                                    f"{pred.direction.upper()}</div></div>", unsafe_allow_html=True)
                        pc2.markdown(f"<div style='text-align:center;'>"
                                    f"<div style='color:#5a7a9a;font-size:11px;'>PROBABILITY</div>"
                                    f"<div style='color:{dir_color};font-size:28px;font-weight:bold;'>"
                                    f"{pred.probability:.0%}</div></div>", unsafe_allow_html=True)
                        pc3.markdown(f"<div style='text-align:center;'>"
                                    f"<div style='color:#5a7a9a;font-size:11px;'>CONFIDENCE</div>"
                                    f"<div style='color:{conf_color};font-size:28px;font-weight:bold;'>"
                                    f"{pred.confidence.upper()}</div></div>", unsafe_allow_html=True)

                        st.markdown("---")
                        st.markdown(f"**Analysis:** {pred.explanation}")

                        # Context info
                        st.markdown(f"**Inputs:** RSI={current_rsi:.1f} · Bias={bias} · "
                                   f"Harmonics={len(harmonics)} patterns · "
                                   f"Price={fmt_currency(float(df['close'].iloc[-1]))}")

                except Exception as e:
                    st.error(f"Prediction error: {e}")


    # ═══════════════════════════════════════════════════════════════════════
    # TAB 5: ALERTS SETUP
    # ═══════════════════════════════════════════════════════════════════════
    with tab_alert:
        st.markdown("### 🔔 " + t("tt_alerts") + "")
        st.caption("Configure Telegram + Gmail alerts for trade signals. Real-time delivery.")

        st.markdown("#### 📱 Telegram Configuration")
        tg_token = st.text_input("Bot Token (from @BotFather)", type="password", key="tt_tg_token")
        tg_chat = st.text_input("Chat ID (from @userinfobot)", key="tt_tg_chat")

        st.markdown("#### 📧 Email Configuration (Gmail)")
        em_from = st.text_input("Gmail Address", key="tt_em_from")
        em_pass = st.text_input("App Password (16-char, from myaccount.google.com/apppasswords)",
                                type="password", key="tt_em_pass")
        em_to = st.text_input("Send alerts to", key="tt_em_to")

        st.markdown("#### ⚙️ Active Channels")
        use_tg = st.checkbox("Telegram", value=True, key="tt_use_tg")
        use_em = st.checkbox("Gmail", value=False, key="tt_use_em")

        st.markdown("---")
        st.markdown("#### 🧪 Send Test Alert")

        if st.button("📤 Send Test Alert NOW", key="tt_alert_test"):
            try:
                from engine.notifications.notifier import (
                    NotificationConfig, TradeAlert, SignalType, dispatch_alert
                )

                channels = []
                if use_tg:
                    channels.append("telegram")
                if use_em:
                    channels.append("email")

                if not channels:
                    st.warning("Enable at least one channel.")
                else:
                    config = NotificationConfig(
                        telegram_token=tg_token,
                        telegram_chat_id=tg_chat,
                        email_from=em_from,
                        email_password=em_pass,
                        email_to=em_to,
                        channels=channels,
                    )

                    test_alert = TradeAlert(
                        signal_type=SignalType.ENTER_NOW,
                        ticker="TEST-ALERT",
                        current_price=100.00,
                        entry_low=99.50,
                        entry_high=100.50,
                        target_1=105.00,
                        target_2=110.00,
                        target_3=115.00,
                        stop_loss=97.00,
                        confluence_score=85,
                        confidence_pct=78.5,
                        rr_ratio=2.5,
                        execution_mode="SUPERVISED",
                        extra_note="Test alert from Trading Toolkit",
                    )

                    results = dispatch_alert(config, test_alert)

                    for channel, success in results.items():
                        if success:
                            st.success(f"✅ {channel.title()} alert delivered!")
                        else:
                            st.error(f"❌ {channel.title()} delivery failed. Check credentials.")

                    if not results:
                        st.warning("No channels were active or configured.")

            except Exception as e:
                st.error(f"Alert error: {e}")

        # Info about alert types
        st.markdown("---")
        st.markdown("#### 📋 Supported Alert Types")
        st.markdown("""
        | Signal | Description |
        |---|---|
        | 🚀 ENTER NOW | New trade entry signal |
        | 🔻 EXIT NOW | Close position signal |
        | ✅ TRADE OPENED | Confirmation of execution |
        | 🔒 TRADE CLOSED | Position closed |
        | ⚠️ RISK WARNING | Stop-loss approach or exposure alert |
        """)

        st.info("💡 These alerts are dispatched automatically by the Let God Trade page "
                "when autonomous execution is active. You can also trigger them manually from here.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
main()
