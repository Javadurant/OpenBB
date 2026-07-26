# pages/let_god_trade.py
# QuantEdge — Let God Trade: Execution + Notification + Session Intelligence
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# ARCHITECTURE:
#   This file contains ONLY:
#     — Global session clock renderer
#     — Execution panel (Alpaca / OMX simulation)
#     — Notification dispatch (Telegram / Gmail)
#     — Alpaca account + positions panel
#     — Order history audit log
#     — Its own main() entry point
#
#   ALL analysis functions (Elliott Wave, Harmonics, Ichimoku, Indicators,
#   PRZ, Macro, Sentiment, Institutional) are imported from:
#     pages/ai_trading_agent.py  (untouched — zero modifications)
#
#   Execution + notification engines imported from:
#     engine/execution/order_manager.py
#     engine/notifications/notifier.py
#     engine/features/market_sessions.py
#
# NO st.set_page_config() — called once only in app.py per project rule.
# <- NEW [let_god_trade]: Execution + notification + session intelligence page

import datetime
import logging
from translations import t, inject_rtl_css  # <- NEW [i18n]
import os
import sys
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import pandas as pd
import streamlit as st

logger = logging.getLogger("LetGodTrade")

# ── Resolve project root ────────────────────────────────────────────────────
_ROOT:  str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PAGES: str = os.path.abspath(os.path.join(os.path.dirname(__file__)))

for _p in (_ROOT, _PAGES):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Import all analysis functions from ai_trading_agent (untouched) ────────
try:
    from ai_trading_agent import (
        # Data fetching
        _fetch_ohlcv,
        _fetch_info,
        _fetch_macro_proxies,
        _fetch_institutional_proxy,
        # Analysis engines
        compute_zigzag,
        analyse_elliott_waves,
        scan_all_harmonic_patterns,
        compute_ichimoku,
        compute_all_indicators,
        compute_prz_confluence,
        compute_master_signal,
        classify_macro_regime,
        score_sentiment_via_groq,
        score_institutional,
        # TypedDicts
        HarmonicResult,
        WaveResult,
        IchimokuResult,
        PRZResult,
        MasterSignal,
        # Constants needed for renderers
        RSI_OVERBOUGHT,
        RSI_OVERSOLD,
        ICH_TENKAN,
        ICH_KIJUN,
        ICH_SENKOU_B,
        ICH_SHIFT,
        MACD_FAST,
        MACD_SLOW,
        MACD_SIGNAL,
        BB_PERIOD,
        BB_STD_DEV,
        MA_PERIODS,
        STOCH_K,
        STOCH_D,
        MIN_RR_RATIO,
        MACRO_QUADRANTS,
        CACHE_TTL,
        # Existing renderers (reused to avoid duplication)
        _render_scorecard,
        _render_prz,
        _render_harmonics,
        _render_elliott,
        _render_indicators,
        _render_macro,
        _render_institutional,
        _render_fundamentals,
        _build_chart,
    )
    _AGENT_AVAILABLE: bool = True
except ImportError as _agent_err:
    _AGENT_AVAILABLE = False
    logger.error(
        "Could not import from ai_trading_agent.py: %s — "
        "Ensure pages/ai_trading_agent.py exists and is syntactically valid.",
        _agent_err,
    )

# ── Import execution + notification engines ─────────────────────────────────
try:
    from engine.notifications.notifier import (
        NotificationConfig,
        SignalType,
        TradeAlert,
        dispatch_alert,
    )
    from engine.execution.order_manager import (
        BrokerType,
        ExecutionMode,
        OrderConfig,
        OrderSide,
        compute_position_size,
        execute_order,
        get_alpaca_account,
        get_alpaca_positions,
        get_usd_sek_rate,
        is_swedish_ticker,
        should_auto_execute,
        should_show_confirm_button,
    )
    from engine.features.market_sessions import (
        get_omx_context,
        get_propagation_hints,
        get_session_statuses,
    )
    _TRADING_MODULES_AVAILABLE: bool = True
except ImportError as _tm_err:
    _TRADING_MODULES_AVAILABLE = False
    logger.warning(
        "Trading modules unavailable: %s — "
        "Create engine/execution/, engine/notifications/, engine/features/ "
        "per the setup guide.",
        _tm_err,
    )

# ── Default execution constants ─────────────────────────────────────────────
EXEC_SUPERVISED_THRESHOLD_DEFAULT: int   = 50
EXEC_AUTONOMOUS_THRESHOLD_DEFAULT: int   = 80
EXEC_CAPITAL_USD_DEFAULT:          float = 10_000.0
EXEC_RISK_PCT_DEFAULT:             float = 0.02
EXEC_MAX_POSITION_PCT_DEFAULT:     float = 0.10
EXEC_MAX_POSITION_USD_DEFAULT:     float = 2_000.0

# ── Plotly / dark theme constants ────────────────────────────────────────────
_BG:          str = "#0D1117"
_GRID:        str = "#1C2333"
_TEXT:        str = "#E6EDF3"
_BULL_CANDLE: str = "#00FF88"
_BEAR_CANDLE: str = "#FF3333"

_SIGNAL_COLORS: Dict[str, str] = {
    "STRONG BUY":  "#00FF88",
    "BUY":         "#00CC66",
    "HOLD":        "#FFD700",
    "SELL":        "#FF8C00",
    "STRONG SELL": "#FF3333",
}

# ── Typed audit log entry ────────────────────────────────────────────────────
from typing import TypedDict

class ExecLogEntry(TypedDict):
    """Typed audit log entry for every order fired from this page."""
    timestamp:  str
    ticker:     str
    side:       str
    qty:        int
    price:      float
    total_usd:  float
    total_sek:  float
    broker:     str
    mode:       str
    order_id:   str
    score:      int
    notified:   Dict[str, bool]
    error:      str


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION CLOCK RENDERER
# ═══════════════════════════════════════════════════════════════════════════════
def _render_session_clock(ticker_ctx: str = "") -> None:
    """
    Renders the live 4-session market clock.
    Sydney → Tokyo → London → New York open/closed status,
    local time, countdown, and AI signal propagation hints.
    """
    if not _TRADING_MODULES_AVAILABLE:
        st.info("Market session clock unavailable — trading modules not imported.")
        return

    st.markdown("### 🕐 " + t("lgt_sessions"))
    statuses = get_session_statuses()

    cols = st.columns(4)
    for col, s in zip(cols, statuses):
        border_color = s.color if s.is_open else "#2A2A3E"
        bg_color     = f"{s.color}18" if s.is_open else "#0D1117"
        status_label = "● OPEN" if s.is_open else "○ CLOSED"
        status_color = s.color if s.is_open else "#444"
        lead_badge   = (
            " &nbsp;<span style='background:#00FF8833; color:#00FF88; "
            "padding:1px 6px; border-radius:3px; font-size:0.7rem;'>LEAD</span>"
            if s.is_session_lead else ""
        )
        if s.is_open and s.closes_in_min > 0:
            time_line = f"Closes in <b>{s.closes_in_min}m</b>"
        elif s.opens_in_min > 0:
            time_line = f"Opens in <b>{s.opens_in_min}m</b>"
        else:
            time_line = "—"
        indices_str = " · ".join(s.indices[:2])
        col.markdown(
            f"""
            <div style="background:{bg_color}; border:1px solid {border_color};
                        border-radius:10px; padding:14px 12px; min-height:130px;">
                <div style="font-size:0.78rem; font-weight:700; color:{s.color};
                            letter-spacing:1px;">{s.name}{lead_badge}</div>
                <div style="font-size:1.5rem; font-weight:900; color:{_TEXT};
                            margin:4px 0 2px 0;">{s.local_time}</div>
                <div style="font-size:0.75rem; color:{status_color}; font-weight:700;">
                    {status_label}</div>
                <div style="font-size:0.72rem; color:#666; margin-top:6px;">
                    {time_line}</div>
                <div style="font-size:0.68rem; color:#444; margin-top:4px;">
                    {indices_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    hints = get_propagation_hints(statuses)
    if hints:
        st.markdown("")
        for hint in hints:
            st.markdown(
                f"<div style='color:#888; font-size:0.82rem; padding:4px 0;'>"
                f"{hint}</div>",
                unsafe_allow_html=True,
            )

    if ticker_ctx.upper().endswith(".ST"):
        omx_ctx = get_omx_context(statuses)
        st.markdown(
            f"<div style='color:#FFD700; font-size:0.82rem; margin-top:4px;'>"
            f"🇸🇪 {omx_ctx}</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION PANEL
# ═══════════════════════════════════════════════════════════════════════════════
def _render_execution_panel(
    sig:          "MasterSignal",
    prz:          "PRZResult",
    exec_config:  "OrderConfig",
    notif_config: "NotificationConfig",
) -> None:
    """
    Execution panel — position sizing, confirm button (SUPERVISED),
    auto-fire (AUTONOMOUS), notification dispatch, audit log append.
    """
    if not _TRADING_MODULES_AVAILABLE:
        st.info("Execution panel unavailable — trading modules not imported.")
        return

    score  = sig["confluence_score"]
    ticker = sig["ticker"]
    signal = sig["signal"]

    if not prz or prz.get("entry", 0.0) < 1e-10:
        st.info("Execution panel waiting for valid PRZ data.")
        return

    entry_price = prz["entry"]
    stop_price  = prz["stop_loss"]
    is_sek      = is_swedish_ticker(ticker)
    fx_rate     = get_usd_sek_rate()
    ccy         = "SEK" if is_sek else "USD"
    fx_note     = "" if abs(fx_rate - 10.50) > 0.01 else " ⚠️ Fallback FX 10.50"

    st.markdown("### ⚙️ " + t("lgt_engine"))

    pos = compute_position_size(
        entry_price=entry_price,
        stop_loss=stop_price,
        config=exec_config,
        fx_rate=fx_rate,
        is_sek=is_sek,
    )

    mode_color   = "#00FF88" if exec_config.mode == ExecutionMode.AUTONOMOUS else "#FFD700"
    broker_label = exec_config.broker.value if not is_sek else "SIMULATED (OMX)"
    auto_fire    = should_auto_execute(score, exec_config)
    show_confirm = should_show_confirm_button(score, exec_config)

    st.markdown(
        f"""
        <div style="background:{mode_color}18; border:1px solid {mode_color};
                    border-radius:8px; padding:10px 16px; margin-bottom:12px;">
            <span style="color:{mode_color}; font-weight:700; font-size:1rem;">
                {exec_config.mode.value} MODE
            </span>
            <span style="color:#888; font-size:0.82rem;">
                &nbsp;·&nbsp; Broker: {broker_label}
                &nbsp;·&nbsp; Score: {score:+d}
                &nbsp;·&nbsp; Supervised ≥ {exec_config.supervised_threshold}
                &nbsp;·&nbsp; Autonomous ≥ {exec_config.autonomous_threshold}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ps_c1, ps_c2, ps_c3, ps_c4, ps_c5 = st.columns(5)
    ps_c1.metric("Shares",       str(pos["shares"]))
    ps_c2.metric(
        f"Cost ({ccy})",
        f"{pos['cost_sek']:,.0f}" if is_sek else f"${pos['cost_usd']:,.2f}",
    )
    ps_c3.metric("Cost (USD)",   f"${pos['cost_usd']:,.2f}")
    ps_c4.metric("Risk (USD)",   f"${pos['risk_usd']:,.2f}")
    ps_c5.metric("Capital Used", f"{pos['capital_used_pct']:.1f}%",
                 delta=f"FX {pos['fx_rate']:.4f}{fx_note}")

    if pos["shares"] < 1:
        st.warning(
            "Position size is 0 shares. "
            "Check capital, risk %, and stop-loss distance in sidebar settings."
        )
        return

    if signal in ("STRONG BUY", "BUY"):
        order_side = OrderSide.BUY
        side_label = "BUY"
        side_color = "#00FF88"
    elif signal in ("STRONG SELL", "SELL"):
        order_side = OrderSide.SELL
        side_label = "SELL"
        side_color = "#FF3333"
    else:
        st.markdown(
            "<div style='color:#888; font-size:0.85rem; padding:8px 0;'>"
            "Signal is HOLD — no execution triggered.</div>",
            unsafe_allow_html=True,
        )
        return

    # AUTONOMOUS path
    if auto_fire:
        exec_key = f"lgt_auto_fired_{ticker}_{score}"
        if not st.session_state.get(exec_key, False):
            st.session_state[exec_key] = True
            _fire_order(
                ticker=ticker, order_side=order_side,
                entry_price=entry_price, stop_price=stop_price,
                pos=pos, sig=sig, prz=prz,
                exec_config=exec_config, notif_config=notif_config,
                fx_rate=fx_rate, is_sek=is_sek, ccy=ccy,
                trigger="AUTONOMOUS",
            )
        else:
            st.markdown(
                f"<div style='color:#00FF88; font-size:0.82rem; padding:4px 0;'>"
                f"✅ Autonomous order already fired for {ticker} @ score {score:+d}</div>",
                unsafe_allow_html=True,
            )
        return

    # SUPERVISED path
    if show_confirm:
        st.markdown(
            f"""
            <div style="background:{side_color}18; border:1px solid {side_color};
                        border-radius:8px; padding:14px 18px; margin:10px 0;">
                <div style="color:{side_color}; font-weight:700; font-size:1.1rem;">
                    🎯 Signal Ready: {side_label} {pos['shares']} × {ticker}
                    @ {entry_price:.4f} {ccy}
                </div>
                <div style="color:#888; font-size:0.82rem; margin-top:4px;">
                    Score {score:+d} meets SUPERVISED threshold
                    ({exec_config.supervised_threshold}).
                    Click to execute and send notification.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        confirm_key = f"lgt_confirm_{ticker}_{score}_{side_label}"
        if st.button(
            f"✅ Execute {side_label} — {pos['shares']} shares",
            key=confirm_key,
            type="primary",
        ):
            _fire_order(
                ticker=ticker, order_side=order_side,
                entry_price=entry_price, stop_price=stop_price,
                pos=pos, sig=sig, prz=prz,
                exec_config=exec_config, notif_config=notif_config,
                fx_rate=fx_rate, is_sek=is_sek, ccy=ccy,
                trigger="SUPERVISED",
            )
    else:
        threshold = (
            exec_config.autonomous_threshold
            if exec_config.mode == ExecutionMode.AUTONOMOUS
            else exec_config.supervised_threshold
        )
        needed = threshold - score
        st.markdown(
            f"<div style='color:#555; font-size:0.82rem; padding:4px 0;'>"
            f"Score {score:+d} — need {needed} more points to trigger "
            f"(threshold: {threshold}).</div>",
            unsafe_allow_html=True,
        )


def _fire_order(
    ticker:       str,
    order_side:   "OrderSide",
    entry_price:  float,
    stop_price:   float,
    pos:          Dict[str, Any],
    sig:          "MasterSignal",
    prz:          "PRZResult",
    exec_config:  "OrderConfig",
    notif_config: "NotificationConfig",
    fx_rate:      float,
    is_sek:       bool,
    ccy:          str,
    trigger:      str,
) -> None:
    """
    Executes order, dispatches notifications, appends to audit log.
    Called from both AUTONOMOUS auto-path and SUPERVISED confirm button.
    """
    with st.spinner(f"Executing {order_side.value.upper()} {ticker}…"):
        order, _ = execute_order(
            ticker=ticker,
            side=order_side,
            entry_price=entry_price,
            stop_loss=stop_price,
            config=exec_config,
        )

    if order["success"]:
        st.success(
            f"✅ Order submitted · {order_side.value.upper()} "
            f"{order['qty']} × {ticker} @ {entry_price:.4f} {ccy} · "
            f"ID: {order['order_id']} · Broker: {order['broker']}"
        )
    else:
        st.error(f"❌ Order failed: {order['error']}")

    notif_results: Dict[str, bool] = {}
    if _TRADING_MODULES_AVAILABLE:
        signal_type = (
            SignalType.TRADE_OPENED if order["success"] else SignalType.ENTER_NOW
        )
        alert = TradeAlert(
            signal_type      = signal_type,
            ticker           = ticker,
            current_price    = entry_price,
            entry_low        = prz.get("price_zone_low",  entry_price * 0.999),
            entry_high       = prz.get("price_zone_high", entry_price * 1.001),
            target_1         = prz.get("target_1", 0.0),
            target_2         = prz.get("target_2", 0.0),
            target_3         = prz.get("target_3", 0.0),
            stop_loss        = stop_price,
            confluence_score = sig["confluence_score"],
            confidence_pct   = sig["confidence_pct"],
            rr_ratio         = prz.get("rr_ratio", 0.0),
            execution_mode   = trigger,
            currency         = ccy,
            extra_note       = (
                f"Order ID: {order['order_id']}"
                if order["success"]
                else f"FAILED: {order['error']}"
            ),
        )
        with st.spinner("Sending notifications…"):
            notif_results = dispatch_alert(notif_config, alert)

        for channel, delivered in notif_results.items():
            if delivered:
                st.success(f"📨 Notification delivered → {channel}")
            else:
                st.warning(f"⚠️ Notification failed → {channel}")

    log_entry: ExecLogEntry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ticker":    ticker,
        "side":      order_side.value,
        "qty":       order["qty"],
        "price":     order["price"] if order["price"] > 1e-10 else entry_price,
        "total_usd": order["total_usd"],
        "total_sek": order["total_sek"] if is_sek else 0.0,
        "broker":    order["broker"],
        "mode":      trigger,
        "order_id":  order["order_id"],
        "score":     sig["confluence_score"],
        "notified":  notif_results,
        "error":     order["error"],
    }
    if "lgt_exec_history" not in st.session_state:
        st.session_state["lgt_exec_history"] = []
    st.session_state["lgt_exec_history"].insert(0, log_entry)


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER HISTORY RENDERER
# ═══════════════════════════════════════════════════════════════════════════════
def _render_order_history() -> None:
    """Renders the session-scoped execution audit log."""
    history: List[ExecLogEntry] = st.session_state.get("lgt_exec_history", [])
    st.markdown("### 📝 Order History (this session)")
    if not history:
        st.markdown(
            "<div style='color:#444; font-size:0.85rem;'>"
            "No orders executed yet.</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    for e in history:
        notif_str = ", ".join(
            f"{ch}:{'✅' if ok else '❌'}"
            for ch, ok in e.get("notified", {}).items()
        ) or "—"
        cost_str = (
            f"{e['total_sek']:,.0f} SEK"
            if e.get("total_sek", 0.0) > 1e-10
            else f"${e.get('total_usd', 0.0):,.2f}"
        )
        rows.append({
            "Time":     e["timestamp"],
            "Ticker":   e["ticker"],
            "Side":     e["side"].upper(),
            "Qty":      e["qty"],
            "Price":    f"{e['price']:.4f}",
            "Total":    cost_str,
            "Score":    f"{e['score']:+d}",
            "Broker":   e["broker"],
            "Mode":     e["mode"],
            "Order ID": e["order_id"],
            "Notified": notif_str,
            "Error":    e["error"] or "—",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if st.button("🗑 Clear History", key="lgt_clear_history"):
        st.session_state["lgt_exec_history"] = []
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# ALPACA ACCOUNT RENDERER
# ═══════════════════════════════════════════════════════════════════════════════
def _render_alpaca_account(exec_config: "OrderConfig") -> None:
    """Renders live Alpaca equity, buying power, cash, and open positions."""
    if not _TRADING_MODULES_AVAILABLE:
        return

    st.markdown("### 💼 " + t("lgt_broker"))

    if not exec_config.alpaca_key:
        st.markdown(
            "<div style='color:#555; font-size:0.85rem;'>"
            "No Alpaca API key configured — simulation mode active. "
            "Enter your key in sidebar to connect paper or live account."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    with st.spinner("Fetching Alpaca account…"):
        acct     = get_alpaca_account(exec_config)
        pos_data = get_alpaca_positions(exec_config)

    if acct.get("error"):
        st.error(f"Alpaca account error: {acct['error']}")
        return

    acct_color = (
        "#FF3333" if exec_config.broker == BrokerType.ALPACA_LIVE else "#FFD700"
    )
    broker_label = (
        "🔴 LIVE ACCOUNT"
        if exec_config.broker == BrokerType.ALPACA_LIVE
        else "🟡 PAPER ACCOUNT"
    )
    st.markdown(
        f"<div style='color:{acct_color}; font-weight:700; font-size:0.9rem; "
        f"margin-bottom:8px;'>"
        f"{broker_label} · Status: {acct.get('status', 'unknown').upper()}"
        f"</div>",
        unsafe_allow_html=True,
    )

    ac1, ac2, ac3 = st.columns(3)
    ac1.metric("Equity",       f"${acct.get('equity',       0.0):,.2f}")
    ac2.metric("Buying Power", f"${acct.get('buying_power', 0.0):,.2f}")
    ac3.metric("Cash",         f"${acct.get('cash',         0.0):,.2f}")

    positions = pos_data.get("positions", [])
    if positions:
        st.markdown("**Open Positions**")
        pos_rows = [{
            "Symbol":    p.get("symbol", ""),
            "Qty":       p.get("qty", 0),
            "Avg Entry": f"${p.get('avg_entry',      0.0):.2f}",
            "Cur Price": f"${p.get('current_price',  0.0):.2f}",
            "Unreal P&L": f"${p.get('unrealized_pl', 0.0):+.2f}",
            "P&L %":     f"{p.get('unrealized_plpc', 0.0):+.2f}%",
            "Side":      p.get("side", "").upper(),
            "Value":     f"${p.get('market_value',   0.0):,.2f}",
        } for p in positions]
        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
    else:
        st.markdown(
            "<div style='color:#555; font-size:0.85rem;'>No open positions.</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR CONFIG BUILDER
# ═══════════════════════════════════════════════════════════════════════════════
def _build_exec_config_from_sidebar() -> Tuple["OrderConfig", "NotificationConfig"]:
    """
    Renders execution and notification config in sidebar.
    Reads secrets from st.secrets when available; falls back to user input.
    All session_state keys prefixed lgt_ to avoid collision with ai_trading_agent.
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='color:#00FF88; font-weight:700; font-size:0.85rem; "
        "letter-spacing:1px;'>⚙️ EXECUTION</div>",
        unsafe_allow_html=True,
    )

    mode_choice = st.sidebar.radio(
        "Execution Mode",
        options=["SUPERVISED", "AUTONOMOUS"],
        index=0,
        horizontal=True,
        key="lgt_exec_mode",
        help=(
            "SUPERVISED: confirm button appears when threshold reached.\n"
            "AUTONOMOUS: fires automatically at autonomous threshold."
        ),
    )
    exec_mode = (
        ExecutionMode.SUPERVISED
        if mode_choice == "SUPERVISED"
        else ExecutionMode.AUTONOMOUS
    )

    broker_choice = st.sidebar.selectbox(
        "Broker",
        options=["Alpaca Paper", "Alpaca Live", "Simulated (No API)"],
        index=0,
        key="lgt_broker",
    )
    broker_map = {
        "Alpaca Paper":       BrokerType.ALPACA_PAPER,
        "Alpaca Live":        BrokerType.ALPACA_LIVE,
        "Simulated (No API)": BrokerType.SIMULATED,
    }
    broker = broker_map[broker_choice]

    alpaca_key    = ""
    alpaca_secret = ""
    if broker in (BrokerType.ALPACA_PAPER, BrokerType.ALPACA_LIVE):
        try:
            alpaca_key    = st.secrets.get("ALPACA_KEY",    "")
            alpaca_secret = st.secrets.get("ALPACA_SECRET", "")
        except Exception:
            pass
        if not alpaca_key:
            alpaca_key = st.sidebar.text_input(
                "Alpaca API Key", type="password", value="", key="lgt_alpaca_key",
                help="alpaca.markets → Your Account → API Keys",
            )
        if not alpaca_secret:
            alpaca_secret = st.sidebar.text_input(
                "Alpaca Secret Key", type="password", value="", key="lgt_alpaca_secret",
            )

    sup_thresh = st.sidebar.slider(
        "Supervised Threshold",
        min_value=10, max_value=100,
        value=EXEC_SUPERVISED_THRESHOLD_DEFAULT,
        step=5, key="lgt_sup_thresh",
    )
    auto_thresh = st.sidebar.slider(
        "Autonomous Threshold",
        min_value=sup_thresh, max_value=150,
        value=EXEC_AUTONOMOUS_THRESHOLD_DEFAULT,
        step=5, key="lgt_auto_thresh",
    )

    st.sidebar.markdown(
        "<div style='color:#888; font-size:0.75rem; margin:6px 0 2px 0;'>"
        "Position Sizing</div>",
        unsafe_allow_html=True,
    )
    capital_usd = st.sidebar.number_input(
        "Capital (USD)",
        min_value=100.0, max_value=10_000_000.0,
        value=EXEC_CAPITAL_USD_DEFAULT, step=500.0, key="lgt_capital_usd",
    )
    capital_sek = st.sidebar.number_input(
        "Capital (SEK) — 0 = auto-convert",
        min_value=0.0, max_value=100_000_000.0,
        value=0.0, step=5000.0, key="lgt_capital_sek",
    )
    max_pos_pct = st.sidebar.slider(
        "Max Position % of Capital",
        min_value=1, max_value=50,
        value=int(EXEC_MAX_POSITION_PCT_DEFAULT * 100),
        step=1, key="lgt_max_pos_pct",
    ) / 100.0
    max_pos_usd = st.sidebar.number_input(
        "Max Position (USD hard cap)",
        min_value=100.0, max_value=500_000.0,
        value=EXEC_MAX_POSITION_USD_DEFAULT, step=100.0, key="lgt_max_pos_usd",
    )
    max_pos_sek = st.sidebar.number_input(
        "Max Position (SEK hard cap) — 0 = auto-convert",
        min_value=0.0, max_value=5_000_000.0,
        value=0.0, step=1000.0, key="lgt_max_pos_sek",
    )
    risk_pct = st.sidebar.slider(
        "Risk per Trade (%)",
        min_value=0.5, max_value=10.0,
        value=EXEC_RISK_PCT_DEFAULT * 100.0,
        step=0.5, key="lgt_risk_pct",
    ) / 100.0
    use_fixed = st.sidebar.checkbox(
        "Use Fixed Amount (vs risk-based)",
        value=False, key="lgt_use_fixed",
    )

    exec_config = OrderConfig(
        mode                 = exec_mode,
        broker               = broker,
        alpaca_key           = alpaca_key,
        alpaca_secret        = alpaca_secret,
        supervised_threshold = sup_thresh,
        autonomous_threshold = auto_thresh,
        capital_usd          = capital_usd,
        capital_sek          = capital_sek,
        max_position_pct     = max_pos_pct,
        max_position_usd     = max_pos_usd,
        max_position_sek     = max_pos_sek,
        risk_per_trade_pct   = risk_pct,
        use_fixed_amount     = use_fixed,
    )

    # ── Notifications ──────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='color:#00BFFF; font-weight:700; font-size:0.85rem; "
        "letter-spacing:1px;'>🔔 NOTIFICATIONS</div>",
        unsafe_allow_html=True,
    )

    notif_channels = st.sidebar.multiselect(
        "Active Channels",
        options=["telegram", "email"],
        default=["telegram"],
        key="lgt_notif_channels",
    )

    tg_token = tg_chat = em_from = em_pass = em_to = ""

    if "telegram" in notif_channels:
        st.sidebar.markdown(
            "<div style='color:#666; font-size:0.72rem;'>"
            "Telegram: create bot @BotFather · get ID @userinfobot</div>",
            unsafe_allow_html=True,
        )
        try:
            tg_token = st.secrets.get("TELEGRAM_TOKEN",   "")
            tg_chat  = st.secrets.get("TELEGRAM_CHAT_ID", "")
        except Exception:
            pass
        if not tg_token:
            tg_token = st.sidebar.text_input(
                "Telegram Bot Token", type="password", value="", key="lgt_tg_token",
            )
        if not tg_chat:
            tg_chat = st.sidebar.text_input(
                "Telegram Chat ID", value="", key="lgt_tg_chat",
            )

    if "email" in notif_channels:
        st.sidebar.markdown(
            "<div style='color:#666; font-size:0.72rem;'>"
            "Gmail: enable 2FA → App Password → myaccount.google.com/apppasswords"
            "</div>",
            unsafe_allow_html=True,
        )
        em_from = st.sidebar.text_input(
            "Gmail From", value="", key="lgt_em_from",
            placeholder="yourname@gmail.com",
        )
        em_pass = st.sidebar.text_input(
            "App Password", type="password", value="", key="lgt_em_pass",
        )
        em_to = st.sidebar.text_input(
            "Notify To", value="", key="lgt_em_to",
        )

    notif_config = NotificationConfig(
        telegram_token   = tg_token,
        telegram_chat_id = tg_chat,
        email_from       = em_from,
        email_password   = em_pass,
        email_to         = em_to,
        channels         = notif_channels,
    )

    return exec_config, notif_config


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    """
    Let God Trade — main entry point.
    Runs the full analysis pipeline (imported from ai_trading_agent.py)
    and adds execution, notifications, and session intelligence on top.

    Session state keys (all prefixed lgt_ to avoid collision):
      lgt_ticker            str   Last analysed ticker
      lgt_groq_key          str   Groq API key
      lgt_result            dict  Full analysis result bundle
      lgt_chart_data        dict  Chart render data
      lgt_exec_history      list  Audit log of all orders
      lgt_exec_mode         str   Execution mode widget
      lgt_broker            str   Broker widget
      lgt_alpaca_key        str   Alpaca API key
      lgt_alpaca_secret     str   Alpaca secret
      lgt_sup_thresh        int   Supervised threshold
      lgt_auto_thresh       int   Autonomous threshold
      lgt_capital_usd       float Capital USD
      lgt_capital_sek       float Capital SEK
      lgt_max_pos_pct       int   Max position % widget
      lgt_max_pos_usd       float Max position USD cap
      lgt_max_pos_sek       float Max position SEK cap
      lgt_risk_pct          float Risk per trade %
      lgt_use_fixed         bool  Fixed vs risk-based sizing
      lgt_notif_channels    list  Active notification channels
      lgt_tg_token          str   Telegram bot token
      lgt_tg_chat           str   Telegram chat ID
      lgt_em_from           str   Email from
      lgt_em_pass           str   Email password
      lgt_em_to             str   Email to
      lgt_auto_fired_{t}_{s} bool Autonomous order guard
    """
    if not _AGENT_AVAILABLE:
        st.error(
            "❌ Cannot import from `pages/ai_trading_agent.py`. "
            "Ensure that file exists and passes `python -m py_compile pages/ai_trading_agent.py`."
        )
        st.stop()
        return

    # ── Dark CSS ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .stApp { background-color: #0D1117; }
        .stMetric { background: #0D1117 !important; }
        .stMetricLabel { color: #888 !important; font-size: 0.78rem !important; }
        .stMetricValue { color: #E6EDF3 !important; }
        .stDataFrame { background: #0D1117; }
        div[data-testid="stSidebar"] { background-color: #0D1117; }
        hr { border-color: #1C2333; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar identity ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center; padding:10px 0 20px 0;">
                <div style="font-size:1.4rem; font-weight:900;
                            color:#00FF88; letter-spacing:3px;">Let God Trade</div>
                <div style="color:#555; font-size:0.72rem; margin-top:4px;">
                    Execution · Notifications · Sessions
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ticker = st.text_input(
            "Ticker Symbol",
            value=st.session_state.get("lgt_ticker", "AAPL"),
            placeholder="e.g. AAPL, TSLA, ERIC-B.ST",
            key="lgt_ticker_input",
        ).strip().upper()

        years = st.selectbox(
            "Data History",
            options=[1, 2, 3, 5],
            index=1,
            format_func=lambda x: f"{x} Year{'s' if x > 1 else ''}",
            key="lgt_years",
        )

        groq_key = st.text_input(
            "Groq API Key (optional)",
            type="password",
            value=st.session_state.get("lgt_groq_key", ""),
            key="lgt_groq_key_input",
        )

        analyse_btn = st.button(
            "🚀 Analyse + Execute",
            use_container_width=True,
            type="primary",
            key="lgt_analyse_btn",
        )

        if _TRADING_MODULES_AVAILABLE:
            exec_config, notif_config = _build_exec_config_from_sidebar()
        else:
            exec_config  = None
            notif_config = None
            st.sidebar.warning(
                "Trading modules not found. "
                "Run the setup commands to create engine/ subpackages."
            )

        st.sidebar.markdown("---")
        st.sidebar.markdown(
            """
            <div style="color:#333; font-size:0.7rem; line-height:1.6;">
                Analysis from ai_trading_agent.py<br/>
                <b style="color:#555;">New here</b><br/>
                Alpaca Paper / Live Execution<br/>
                OMX Stockholm Simulation<br/>
                Telegram + Email Alerts<br/>
                4-Session Global Clock<br/>
                Signal Propagation Hints<br/>
                Full Audit Log
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Session state init ─────────────────────────────────────────────────
    for key in ("lgt_result", "lgt_chart_data"):
        if key not in st.session_state:
            st.session_state[key] = None
    if "lgt_exec_history" not in st.session_state:
        st.session_state["lgt_exec_history"] = []

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin-bottom:24px;">
            <h1 style="color:#E6EDF3; font-size:1.8rem; font-weight:900;
                       letter-spacing:2px; margin:0;">
                Let <span style="color:#00FF88;">God</span> Trade
            </h1>
            <p style="color:#555; font-size:0.85rem; margin:4px 0 0 0;">
                Full analysis from QuantEdge · Alpaca execution ·
                Telegram alerts · Global session clock
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Session clock (always visible) ─────────────────────────────────────
    _render_session_clock(ticker_ctx=ticker)
    st.markdown("---")

    # ── Analysis trigger ───────────────────────────────────────────────────
    if analyse_btn and ticker:
        st.session_state["lgt_ticker"]   = ticker
        st.session_state["lgt_groq_key"] = groq_key

        with st.spinner(f"Fetching data for {ticker}…"):
            df    = _fetch_ohlcv(ticker, years=years)
            info  = _fetch_info(ticker)
            macro = _fetch_macro_proxies()
            inst  = _fetch_institutional_proxy(ticker)

        if df.empty:
            st.error(
                f"No price data returned for **{ticker}**. "
                "Check the ticker symbol and your internet connection."
            )
            st.session_state["lgt_result"]     = None
            st.session_state["lgt_chart_data"] = None
            return

        with st.spinner("Running analysis engines…"):
            close     = df["close"]
            swings    = compute_zigzag(close)
            ew_res    = analyse_elliott_waves(swings)
            harm_list = scan_all_harmonic_patterns(swings)
            ich       = compute_ichimoku(df)
            ind       = compute_all_indicators(df)
            prz       = compute_prz_confluence(df, swings, harm_list, ich, ind)
            sig       = compute_master_signal(ticker, df, info, macro, inst, groq_key)

        st.session_state["lgt_result"] = {
            "sig": sig, "ew_res": ew_res, "harm_list": harm_list,
            "ich": ich, "ind": ind, "prz": prz,
            "macro": macro, "info": info, "inst": inst, "swings": swings,
        }
        st.session_state["lgt_chart_data"] = {
            "df": df, "ticker": ticker, "ind": ind, "ich": ich,
            "swings": swings, "harmonics": harm_list, "prz": prz,
        }

    # ── Render ─────────────────────────────────────────────────────────────
    res = st.session_state.get("lgt_result")
    cd  = st.session_state.get("lgt_chart_data")

    if res is None:
        st.markdown(
            """
            <div style="border:1px solid #1C2333; border-radius:12px;
                        padding:60px 40px; text-align:center;
                        background:#0D1117; margin-top:40px;">
                <div style="font-size:4rem; margin-bottom:16px;">🙏</div>
                <div style="color:#E6EDF3; font-size:1.3rem; font-weight:700;">
                    Enter a ticker and click Analyse + Execute
                </div>
                <div style="color:#555; font-size:0.9rem; margin-top:8px;">
                    All analysis from QuantEdge AI Trading Agent ·
                    Execution and alerts powered here
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    sig       = res["sig"]
    ew_res    = res["ew_res"]
    harm_list = res["harm_list"]
    ich       = res["ich"]
    ind       = res["ind"]
    prz       = res["prz"]
    macro     = res["macro"]
    info      = res["info"]
    inst      = res["inst"]
    swings    = res["swings"]

    for w in sig.get("risk_warnings", []):
        st.warning(w)

    _render_scorecard(sig)
    st.markdown("---")

    # Execution panel first (primary purpose of this page)
    if _TRADING_MODULES_AVAILABLE and exec_config is not None:
        _render_execution_panel(sig, prz, exec_config, notif_config)
        st.markdown("---")

    # Chart
    if cd:
        fig = _build_chart(
            df        = cd["df"],
            ticker    = cd["ticker"],
            ind       = cd["ind"],
            ich       = cd["ich"],
            swings    = cd["swings"],
            harmonics = cd["harmonics"],
            prz       = cd["prz"],
        )
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

    _render_prz(prz)
    st.markdown("---")

    col_h, col_e = st.columns([3, 2])
    with col_h:
        _render_harmonics(harm_list)
    with col_e:
        _render_elliott(ew_res)
    st.markdown("---")

    _render_indicators(ind)
    st.markdown("---")

    col_m, col_i = st.columns([3, 2])
    with col_m:
        _render_macro(sig["macro_quadrant"], macro)
    with col_i:
        _render_institutional(inst)
    st.markdown("---")

    _render_fundamentals(info)
    st.markdown("---")

    if _TRADING_MODULES_AVAILABLE and exec_config is not None:
        _render_alpaca_account(exec_config)
        st.markdown("---")

    _render_order_history()

    st.markdown(
        """
        <div style="text-align:center; color:#333; font-size:0.72rem;
                    margin-top:40px; padding-bottom:20px;">
            Let God Trade · QuantEdge AI Trading Agent ·
            Research purposes only · Not financial advice ·
            Alpaca paper mode by default · Simulated for OMX Stockholm
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────
main()