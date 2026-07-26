"""
pages/swedish_stock_analysis.py
================================
Swedish Stock Market Analysis — OMX Stockholm
Institutional-grade analysis for Nordic investors.

Features:
  - Live OMX Stockholm data via yfinance (.ST tickers)
  - ISK / KF / Aktie & Fondkonto tax wrapper context
  - Riksbank rate context
  - Groq LLaMA 3.3 70B AI analysis (same model as all other pages)
  - Graceful handling of missing/invalid GROQ_API_KEY
  - Same dark cockpit UX as the rest of the platform
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from translations import t, inject_rtl_css  # <- NEW [i18n]
import yfinance as yf
from dotenv import load_dotenv

# ── Load environment ──────────────────────────────────────────────────────
# load_dotenv() reads .env from the project root (openbb_platform/.env)
load_dotenv()

# ── GROQ key — strip whitespace and quotes to avoid silent failures ───────
_raw_key: str = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
GROQ_API_KEY: Optional[str] = _raw_key if _raw_key.startswith("gsk_") else None

logger = logging.getLogger(__name__)

# ── OMXS30 constituent tickers (Yahoo Finance .ST suffix) ─────────────────
OMXS30_STOCKS: Dict[str, str] = {
    "VOLV-B.ST":  "Volvo B",
    "ABB.ST":     "ABB",
    "ERIC-B.ST":  "Ericsson B",
    "ATCO-A.ST":  "Atlas Copco A",
    "ALFA.ST":    "Alfa Laval",
    "SAND.ST":    "Sandvik",
    "HM-B.ST":    "H&M B",
    "INVE-B.ST":  "Investor B",
    "SEB-A.ST":   "SEB A",
    "SWED-A.ST":  "Swedbank A",
    "SHB-A.ST":   "Handelsbanken A",
    "NDA-SE.ST":  "Nordea",
    "SSAB-A.ST":  "SSAB A",
    "SKF-B.ST":   "SKF B",
    "ASSA-B.ST":  "Assa Abloy B",
}

# Extra popular Swedish stocks beyond OMXS30
EXTRA_STOCKS: Dict[str, str] = {
    "BOLL.ST":    "Boliden",
    "TELIA.ST":   "Telia",
    "SINCH.ST":   "Sinch",
    "EVO.ST":     "Evolution",
    "NIBE-B.ST":  "Nibe B",
}

ALL_STOCKS: Dict[str, str] = {**OMXS30_STOCKS, **EXTRA_STOCKS}

# ── Shared CSS (same as rest of platform) ─────────────────────────────────
_CSS = """
<style>
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],
[data-testid="block-container"],section.main,.main .block-container {
    background-color:#000d1a !important;
}
html,body,[class*="css"],.stApp {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important;
}
h1,h2,h3,h4 {
    font-family:'Times New Roman',Times,serif !important;
    font-weight:bold !important; color:#F5ECD7 !important;
}
</style>
"""


# ── Data fetchers ─────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def fetch_stock_data(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a Swedish stock via yfinance."""
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty:
            return None
        hist.columns = [c.lower() for c in hist.columns]
        return hist
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {ticker}: {e}")
        return None


@st.cache_data(ttl=120)
def fetch_quote(ticker: str) -> Dict[str, Any]:
    """Fetch current quote for a Swedish stock."""
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) < 2:
            return {}
        close  = float(hist["Close"].iloc[-1])
        prev   = float(hist["Close"].iloc[-2])
        change = ((close / prev) - 1.0) * 100.0 if prev > 1e-10 else 0.0
        vol    = int(hist["Volume"].iloc[-1])
        high52 = float(hist["Close"].rolling(min(len(hist), 52)).max().iloc[-1])
        low52  = float(hist["Close"].rolling(min(len(hist), 52)).min().iloc[-1])
        return {
            "price":    close,
            "prev":     prev,
            "change":   change,
            "volume":   vol,
            "high_52w": high52,
            "low_52w":  low52,
        }
    except Exception as e:
        logger.warning(f"Quote fetch failed for {ticker}: {e}")
        return {}


@st.cache_data(ttl=300)
def fetch_omxs30_pulse() -> List[Dict[str, Any]]:
    """Fetch live pulse for all OMXS30 stocks."""
    results = []
    for ticker, name in OMXS30_STOCKS.items():
        q = fetch_quote(ticker)
        if q:
            results.append({"ticker": ticker, "name": name, **q})
    results.sort(key=lambda x: x.get("change", 0), reverse=True)
    return results


# ── Chart renderer ────────────────────────────────────────────────────────

def render_candlestick(df: pd.DataFrame, ticker: str, name: str) -> go.Figure:
    """Dark-theme candlestick chart — same style as rest of platform."""
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name=ticker,
    )])
    # Add 20-day EMA
    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    fig.add_trace(go.Scatter(
        x=df.index, y=ema20,
        line=dict(color="rgba(0,229,255,0.6)", width=1.5),
        name="EMA 20", hovertemplate="%{y:.2f} SEK",
    ))
    fig.update_layout(
        template="plotly_dark",
        height=420,
        title=dict(text=f"{name} ({ticker})", font=dict(color="#F5ECD7", size=15)),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(rangeslider_visible=False, gridcolor="rgba(128,128,128,0.1)"),
        yaxis=dict(side="right", gridcolor="rgba(128,128,128,0.1)", title="SEK"),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#E8E0D0")),
    )
    return fig


# ── Groq AI analysis ──────────────────────────────────────────────────────

def run_groq_analysis(
    ticker: str,
    name: str,
    quote: Dict[str, Any],
    df: Optional[pd.DataFrame],
    account_type: str,
) -> str:
    """
    Run Groq LLaMA 3.3 70B analysis on a Swedish stock.
    Returns the analysis string or a clear error message.
    """
    # ── Guard: key missing ────────────────────────────────────────────────
    if not GROQ_API_KEY:
        return (
            "⚠️ **GROQ_API_KEY not set or invalid.**\n\n"
            "**To fix this:**\n"
            "1. Go to https://console.groq.com/keys\n"
            "2. Create a new API key (free)\n"
            "3. Open `openbb_platform/.env`\n"
            "4. Set: `GROQ_API_KEY=gsk_YOUR_NEW_KEY_HERE`\n"
            "   (no quotes, no spaces around the `=`)\n"
            "5. Restart the app: `python -m streamlit run app.py`\n\n"
            "The key must start with `gsk_` to be valid."
        )

    # ── Build context ─────────────────────────────────────────────────────
    price   = quote.get("price", 0)
    change  = quote.get("change", 0)
    h52     = quote.get("high_52w", 0)
    l52     = quote.get("low_52w", 0)

    # Technical summary from recent data
    tech_context = ""
    if df is not None and len(df) >= 20:
        ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1])
        ret_1m = float(((df["close"].iloc[-1] / df["close"].iloc[-21]) - 1) * 100) if len(df) >= 21 else 0.0
        tech_context = (
            f"EMA20: {ema20:.2f} SEK, EMA50: {ema50:.2f} SEK, "
            f"1M return: {ret_1m:+.1f}%, "
            f"Price vs EMA20: {'above' if price > ema20 else 'below'}"
        )

    prompt = f"""You are an institutional Swedish equity analyst specialising in OMX Stockholm.
Analyse the following stock for a Swedish retail investor:

Stock: {name} ({ticker})
Market: OMX Stockholm (Sweden)
Currency: SEK
Account type: {account_type}

Current data:
- Price: {price:.2f} SEK
- Daily change: {change:+.2f}%
- 52-week range: {l52:.2f} – {h52:.2f} SEK
- Technical: {tech_context if tech_context else 'Limited data'}

Provide a concise institutional analysis covering:
1. **Technical outlook** — trend, key support/resistance levels in SEK
2. **Fundamental context** — sector position on OMX Stockholm
3. **{account_type} tax considerations** — specific implications for Swedish investors
4. **Key risks** — 2-3 specific risks for this stock
5. **Trading verdict** — BULLISH / NEUTRAL / BEARISH with one-sentence rationale

Keep the analysis factual, concise, and actionable. All prices in SEK."""

    try:
        from groq import Groq
        client   = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "invalid_api_key" in err.lower() or "authentication" in err.lower():
            return (
                "⚠️ **GROQ_API_KEY is invalid or expired.**\n\n"
                "Your current key is not accepted by Groq.\n\n"
                "**Fix:**\n"
                "1. Go to https://console.groq.com/keys\n"
                "2. Revoke the old key and create a new one\n"
                "3. Update `GROQ_API_KEY` in your `.env` file\n"
                "4. Restart: `python -m streamlit run app.py`"
            )
        return f"⚠️ AI analysis error: {err}"


# ── Main page ─────────────────────────────────────────────────────────────

def page_swedish_stock_analysis() -> None:
    """
    Swedish Stock Analysis page — full OMX Stockholm coverage.
    ISK/KF-optimised for Swedish retail investors.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown("""
<div style="background:linear-gradient(135deg,#000d1a,#001a0d);
            border:1px solid rgba(0,210,200,0.25);border-radius:12px;
            padding:24px 32px;margin-bottom:20px;">
  <div style="display:flex;align-items:center;gap:16px;">
    <span style="font-size:40px;">🇸🇪</span>
    <div>
      <h1 style="margin:0;font-size:26px;color:#F5ECD7;">Swedish Stock Analysis</h1>
      <p style="margin:4px 0 0;font-size:14px;color:#00D2C8;font-family:monospace;">
        OMX STOCKHOLM · LIVE DATA · ISK &amp; KF OPTIMISED · GROQ AI
      </p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── GROQ key warning banner ────────────────────────────────────────────
    if not GROQ_API_KEY:
        st.warning(
            "⚠️ **GROQ_API_KEY missing or invalid.** "
            "Market data and charts work without it, but AI analysis is disabled. "
            "Get a free key at [console.groq.com/keys](https://console.groq.com/keys) "
            "and add it to your `.env` file as `GROQ_API_KEY=gsk_...`",
            icon="⚠️",
        )

    # ── Market pulse strip ─────────────────────────────────────────────────
    st.subheader("📊 " + t("swe_market_pulse"))
    with st.spinner("Loading live OMX Stockholm data..."):
        pulse = fetch_omxs30_pulse()

    if pulse:
        # Show top 5 gainers and losers
        cols = st.columns(5)
        for i, stock in enumerate(pulse[:5]):
            chg  = stock.get("change", 0)
            col  = cols[i % 5]
            color = "#00FF88" if chg >= 0 else "#FF4444"
            arrow = "▲" if chg >= 0 else "▼"
            col.markdown(
                f"<div style='background:#080f1a;border:1px solid rgba(255,255,255,0.08);"
                f"border-radius:8px;padding:10px;text-align:center;'>"
                f"<div style='font-family:monospace;font-size:11px;color:#6a7a8a;'>{stock['name']}</div>"
                f"<div style='font-family:monospace;font-size:15px;font-weight:bold;color:#F5ECD7;'>"
                f"{stock.get('price',0):.2f} <span style='font-size:10px;color:#6a7a8a;'>SEK</span></div>"
                f"<div style='font-family:monospace;font-size:13px;color:{color};'>"
                f"{arrow} {chg:+.2f}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Market data loading — try refreshing in a moment.")

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # ── Stock selector ─────────────────────────────────────────────────────
    col_l, col_r = st.columns([2, 1])

    with col_l:
        st.subheader("🔍 " + t("swe_individual"))
        ticker_labels = {v: k for k, v in ALL_STOCKS.items()}
        selected_name = st.selectbox(
            "Select Swedish Stock",
            options=list(ticker_labels.keys()),
            index=0,
        )
        selected_ticker = ticker_labels[selected_name]

    with col_r:
        st.subheader("💰 " + t("swe_account_type"))
        account_type = st.selectbox(
            "Swedish account wrapper",
            options=[
                "ISK (Investeringssparkonto)",
                "KF (Kapitalförsäkring)",
                "Aktie & Fondkonto",
            ],
            help=(
                "ISK: Flat annual tax on balance — ideal for dividends and growth.\n"
                "KF: Insurance wrapper — same flat tax but allows beneficiary.\n"
                "Aktie & Fondkonto: Standard account — 30% capital gains tax."
            ),
        )

    period = st.select_slider(
        "Chart period",
        options=["1mo", "3mo", "6mo", "1y", "2y"],
        value="6mo",
    )

    # ── Fetch data ─────────────────────────────────────────────────────────
    with st.spinner(f"Loading {selected_name} ({selected_ticker})..."):
        df    = fetch_stock_data(selected_ticker, period)
        quote = fetch_quote(selected_ticker)

    if df is None or df.empty:
        st.error(
            f"Could not load data for {selected_ticker}. "
            "The ticker may be temporarily unavailable. Try another stock."
        )
        return

    # ── Metrics row ───────────────────────────────────────────────────────
    price  = quote.get("price", 0)
    change = quote.get("change", 0)
    h52    = quote.get("high_52w", 0)
    l52    = quote.get("low_52w", 0)
    vol    = quote.get("volume", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Price (SEK)",      f"{price:,.2f}",  f"{change:+.2f}%")
    m2.metric("52W High (SEK)",   f"{h52:,.2f}")
    m3.metric("52W Low (SEK)",    f"{l52:,.2f}")
    m4.metric("Volume",           f"{vol:,}")

    # ── Chart ─────────────────────────────────────────────────────────────
    st.plotly_chart(
        render_candlestick(df, selected_ticker, selected_name),
        use_container_width=True,
    )

    # ── ISK / KF context ──────────────────────────────────────────────────
    with st.expander("💰 Swedish Tax Wrapper Guide (ISK / KF / Aktie & Fondkonto)"):
        st.markdown("""
**ISK (Investeringssparkonto)**
- Tax is calculated as a flat rate on the account balance × government lending rate + 1%
- Dividends and capital gains are NOT taxed separately — all included in the schablonintäkt
- Ideal for: dividend stocks, high-growth stocks, frequent trading
- Annual schablonintäkt 2024: ~1.5% of account value

**KF (Kapitalförsäkring)**
- Same flat-rate tax mechanism as ISK
- Difference: KF is an insurance policy — allows beneficiary designation
- Slightly higher admin fees than ISK
- Cannot be used as collateral for loans

**Aktie & Fondkonto (Standard account)**
- Capital gains: 30% tax when you sell
- Dividends: 30% withholding tax (with foreign credit available)
- Loss deduction: 70% of capital losses deductible against other income
- Best for: long-term buy-and-hold where you rarely sell

**Recommendation for most Swedish retail investors:** ISK is the most tax-efficient
wrapper for active investors. KF adds beneficiary protection. Standard account only
makes sense if you never plan to sell.
""")

    # ── AI Analysis ───────────────────────────────────────────────────────
    st.subheader("🤖 " + t("swe_ai_analysis"))

    if not GROQ_API_KEY:
        st.info(
            "AI analysis requires a valid GROQ_API_KEY. "
            "Get a free key at https://console.groq.com/keys — "
            "it takes 30 seconds."
        )
    else:
        if st.button(f"🚀 Analyse {selected_name}", type="primary"):
            with st.spinner(f"Analysing {selected_name} with Groq LLaMA 3.3 70B..."):
                analysis = run_groq_analysis(
                    selected_ticker, selected_name,
                    quote, df, account_type,
                )
            st.markdown(analysis)

    # ── OMXS30 full table ─────────────────────────────────────────────────
    st.subheader("📋 " + t("swe_full_overview"))
    with st.spinner("Building market table..."):
        rows = []
        for ticker, name in OMXS30_STOCKS.items():
            q = fetch_quote(ticker)
            if q:
                chg = q.get("change", 0)
                rows.append({
                    "Name":         name,
                    "Ticker":       ticker,
                    "Price (SEK)":  f"{q.get('price', 0):,.2f}",
                    "Change":       f"{chg:+.2f}%",
                    "52W High":     f"{q.get('high_52w', 0):,.2f}",
                    "52W Low":      f"{q.get('low_52w', 0):,.2f}",
                    "Trend":        "📈" if chg >= 0 else "📉",
                })

    if rows:
        table_df = pd.DataFrame(rows)
        st.dataframe(table_df, use_container_width=True, hide_index=True)
    else:
        st.info("Market table loading...")

    # ── Footer ─────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:20px;padding:10px 16px;"
        f"background:rgba(255,82,82,0.05);border:1px solid rgba(255,82,82,0.12);"
        f"border-radius:6px;'>"
        f"<p style='color:rgba(255,255,255,0.28);font-size:10px;"
        f"font-family:monospace;margin:0;'>"
        f"⚠ Data via yfinance. Analysis via Groq LLaMA 3.3 70B. "
        f"For educational purposes only. Not financial advice. "
        f"Tax information is general guidance — consult Skatteverket for your specific situation. "
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        f"</p></div>",
        unsafe_allow_html=True,
    )


# ── Called directly when navigated to via st.navigation ──────────────────
page_swedish_stock_analysis()
