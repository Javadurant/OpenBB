"""
trade_thesis_generator.py
=========================
Layer 2 — Trade Thesis Generator.
Council verdict: item 3 — the core decision loop. Build this before automating anything.

Input:  ticker + timeframe + optional context
Output: structured bull case / bear case / key levels /
        invalidation point / confidence rating / psychology check

Place at: openbb_platform/trade_thesis_generator.py

Usage:
    from trade_thesis_generator import TradeThesisGenerator
    gen = TradeThesisGenerator()
    thesis = gen.generate("VOLV-B.ST", timeframe="swing")
    print(thesis["summary"])
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
GROQ_KEY      = os.getenv("GROQ_API_KEY",      "").strip().strip('"').strip("'")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
FMP_KEY       = os.getenv("FMP_API_KEY",        "").strip().strip('"').strip("'")
EODHD_KEY     = os.getenv("EODHD_API_KEY",      "").strip().strip('"').strip("'")
GROQ_MODEL    = "llama-3.3-70b-versatile"
_TIMEOUT      = 20


@dataclass
class TradeThesis:
    ticker:          str
    timeframe:       str
    generated_at:    str = field(default_factory=lambda: datetime.now().isoformat())

    # Core thesis components
    bull_case:        str = ""
    bear_case:        str = ""
    key_levels:       dict = field(default_factory=dict)
    invalidation:     str = ""
    confidence:       int = 0   # 0–100
    confidence_label: str = ""  # "High" / "Moderate" / "Low"

    # Supporting data
    technical_summary: str = ""
    fundamental_summary: str = ""
    recent_news:       list = field(default_factory=list)

    # Psychology
    psychology_note:  str = ""

    # Full text
    summary:          str = ""
    raw_ai_response:  str = ""

    def to_dict(self) -> dict:
        return {
            "ticker":           self.ticker,
            "timeframe":        self.timeframe,
            "generated_at":     self.generated_at,
            "confidence":       self.confidence,
            "confidence_label": self.confidence_label,
            "bull_case":        self.bull_case,
            "bear_case":        self.bear_case,
            "key_levels":       self.key_levels,
            "invalidation":     self.invalidation,
            "technical":        self.technical_summary,
            "fundamental":      self.fundamental_summary,
            "psychology_note":  self.psychology_note,
            "summary":          self.summary,
        }


class TradeThesisGenerator:
    """
    Generates a structured trade thesis for any ticker.
    Data sources: yfinance (always), EODHD (if key), FMP (if key).
    AI: Groq (free) → Anthropic fallback.
    """

    def generate(
        self,
        ticker:    str,
        timeframe: str = "swing",     # "intraday" / "swing" / "position"
        context:   Optional[str] = None,
    ) -> TradeThesis:
        """
        Generate a complete trade thesis.
        ticker: e.g. "AAPL", "VOLV-B.ST", "ERIC-B.ST"
        timeframe: "intraday" (1-5 days), "swing" (1-4 weeks), "position" (1-6 months)
        context: optional additional context from the user
        """
        thesis = TradeThesis(ticker=ticker, timeframe=timeframe)

        # ── Step 1: Fetch market data ──────────────────────────────────────
        price_data    = self._fetch_price_data(ticker)
        tech_summary  = self._build_technical_summary(ticker, price_data)
        fund_summary  = self._fetch_fundamentals(ticker)
        news          = self._fetch_news(ticker)

        thesis.technical_summary   = tech_summary
        thesis.fundamental_summary = fund_summary
        thesis.recent_news         = news[:5]

        # ── Step 2: Build AI prompt ────────────────────────────────────────
        prompt = self._build_prompt(
            ticker, timeframe, tech_summary, fund_summary, news, context
        )

        # ── Step 3: Get AI analysis ────────────────────────────────────────
        ai_response = self._call_ai(prompt)
        thesis.raw_ai_response = ai_response

        # ── Step 4: Parse structured output ───────────────────────────────
        parsed = self._parse_response(ai_response)
        thesis.bull_case        = parsed.get("bull_case", "")
        thesis.bear_case        = parsed.get("bear_case", "")
        thesis.key_levels       = parsed.get("key_levels", {})
        thesis.invalidation     = parsed.get("invalidation", "")
        thesis.confidence       = parsed.get("confidence", 50)
        thesis.confidence_label = self._confidence_label(thesis.confidence)

        # ── Step 5: Psychology note ────────────────────────────────────────
        thesis.psychology_note  = self._psychology_note(thesis.confidence)

        # ── Step 6: Build summary ──────────────────────────────────────────
        thesis.summary = self._build_summary(thesis)

        return thesis

    # ── Data fetching ──────────────────────────────────────────────────────

    def _fetch_price_data(self, ticker: str) -> pd.DataFrame:
        """Fetch price data via yfinance (always available, no key needed)."""
        try:
            import yfinance as yf
            t    = yf.Ticker(ticker)
            hist = t.history(period="6mo")
            if hist.empty:
                return pd.DataFrame()
            hist.columns = [c.lower() for c in hist.columns]
            return hist
        except Exception as e:
            logger.warning("yfinance error for " + ticker + ": " + str(e))
            return pd.DataFrame()

    def _build_technical_summary(self, ticker: str, df: pd.DataFrame) -> str:
        """Compute key technical indicators and return a text summary."""
        if df.empty or len(df) < 20:
            return "Insufficient price data for technical analysis."

        close  = df["close"]
        vol    = df["volume"] if "volume" in df.columns else None
        latest = float(close.iloc[-1])

        # Moving averages
        ma20   = float(close.rolling(20).mean().iloc[-1])
        ma50   = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50  else None
        ma200  = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        # RSI (14)
        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss.replace(0, 1e-10)
        rsi    = float(100 - 100 / (1 + rs.iloc[-1]))

        # ATR (14)
        if all(c in df.columns for c in ["high", "low", "close"]):
            hl  = df["high"] - df["low"]
            hpc = abs(df["high"] - df["close"].shift())
            lpc = abs(df["low"]  - df["close"].shift())
            tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
        else:
            atr = None

        # 52-week range
        hi52 = float(close.rolling(252).max().iloc[-1]) if len(close) >= 252 else float(close.max())
        lo52 = float(close.rolling(252).min().iloc[-1]) if len(close) >= 252 else float(close.min())
        pct_from_high = (latest / hi52 - 1) * 100 if hi52 > 1e-10 else 0

        # Trend
        if ma50 and latest > ma50 > ma200 if ma200 else latest > ma50:
            trend = "Uptrend (price above MA50" + (" above MA200" if ma200 and ma50 > ma200 else "") + ")"
        elif ma50 and latest < ma50:
            trend = "Downtrend (price below MA50)"
        else:
            trend = "Sideways / consolidating"

        # Volume trend (recent 10 vs prior 50)
        vol_note = ""
        if vol is not None and len(vol) >= 50:
            avg_recent = float(vol.iloc[-10:].mean())
            avg_prior  = float(vol.iloc[-50:-10].mean())
            if avg_recent > avg_prior * 1.2:
                vol_note = " Volume expanding (bullish confirmation)."
            elif avg_recent < avg_prior * 0.8:
                vol_note = " Volume contracting (VCP or distribution — context-dependent)."

        lines = [
            f"Price: {latest:.2f}",
            f"MA20: {ma20:.2f}  |  MA50: {ma50:.2f if ma50 else 'N/A'}  |  MA200: {ma200:.2f if ma200 else 'N/A'}",
            f"RSI(14): {rsi:.1f}  |  ATR(14): {atr:.2f if atr else 'N/A'}",
            f"52W High: {hi52:.2f}  ({pct_from_high:.1f}% from high)  |  52W Low: {lo52:.2f}",
            f"Trend: {trend}.{vol_note}",
        ]
        return "\n".join(lines)

    def _fetch_fundamentals(self, ticker: str) -> str:
        """Fetch fundamentals from FMP or EODHD."""
        # Try FMP first (works for US tickers)
        if FMP_KEY and ".ST" not in ticker.upper():
            try:
                resp  = requests.get(
                    f"https://financialmodelingprep.com/api/v3/profile/{ticker}",
                    params={"apikey": FMP_KEY}, timeout=_TIMEOUT
                )
                data  = resp.json()
                if data and isinstance(data, list):
                    p = data[0]
                    return (
                        f"Market cap: {p.get('mktCap',0)/1e9:.1f}B  |  "
                        f"P/E: {p.get('pe','N/A')}  |  "
                        f"Sector: {p.get('sector','N/A')}  |  "
                        f"Beta: {p.get('beta','N/A')}  |  "
                        f"Description: {p.get('description','')[:200]}"
                    )
            except Exception:
                pass

        # Try EODHD for Swedish tickers
        if EODHD_KEY:
            try:
                from eodhd_client import EODHDClient
                client = EODHDClient(api_key=EODHD_KEY)
                base, exch = ticker.split(".") if "." in ticker else (ticker, "ST")
                profile = client.get_profile(base, exch)
                return (
                    f"Name: {profile.get('name','')}  |  "
                    f"Sector: {profile.get('sector','N/A')}  |  "
                    f"P/E: {profile.get('pe_ratio','N/A')}  |  "
                    f"Yield: {(profile.get('yield') or 0)*100:.1f}%  |  "
                    f"ROE: {profile.get('roe','N/A')}"
                )
            except Exception:
                pass

        return "Fundamental data not available (no FMP/EODHD key configured)."

    def _fetch_news(self, ticker: str) -> list:
        """Fetch recent news headlines."""
        if FMP_KEY:
            try:
                resp = requests.get(
                    f"https://financialmodelingprep.com/api/v3/stock_news",
                    params={"tickers": ticker, "limit": 5, "apikey": FMP_KEY},
                    timeout=_TIMEOUT,
                )
                data = resp.json()
                if data and isinstance(data, list):
                    return [
                        {"headline": n.get("title", ""), "date": n.get("publishedDate", "")}
                        for n in data[:5]
                    ]
            except Exception:
                pass
        return []

    # ── AI call ────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        ticker:       str,
        timeframe:    str,
        tech:         str,
        fund:         str,
        news:         list,
        context:      Optional[str],
    ) -> str:
        news_text = "\n".join(
            "- " + n["headline"] for n in news
        ) if news else "No recent news available."

        context_text = "\nAdditional context from trader: " + context if context else ""

        return f"""You are analyzing {ticker} for a {timeframe} trade.
The trader has 10+ years of profitable live trading experience. Be direct and specific.

TECHNICAL DATA:
{tech}

FUNDAMENTAL DATA:
{fund}

RECENT NEWS:
{news_text}
{context_text}

Produce a structured trade thesis. Respond ONLY in valid JSON:
{{
  "bull_case": "2-3 sentence bull case. Be specific about catalysts and price targets.",
  "bear_case": "2-3 sentence bear case. Be specific about risks and failure modes.",
  "key_levels": {{
    "support_1": "price",
    "support_2": "price",
    "resistance_1": "price",
    "resistance_2": "price",
    "target": "price if long"
  }},
  "invalidation": "The exact price or event that makes this thesis wrong.",
  "confidence": <integer 0-100>,
  "reasoning": "One sentence explaining the confidence score."
}}

No preamble. No markdown. Valid JSON only."""

    def _call_ai(self, prompt: str) -> str:
        """Call Groq (free) → Anthropic fallback."""
        # Groq primary
        if GROQ_KEY:
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": "Bearer " + GROQ_KEY,
                             "Content-Type":  "application/json"},
                    json={
                        "model":       GROQ_MODEL,
                        "messages":    [{"role": "user", "content": prompt}],
                        "max_tokens":  1024,
                        "temperature": 0.1,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("Groq failed: " + str(e))

        # Anthropic fallback
        if ANTHROPIC_KEY:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                msg = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text
            except Exception as e:
                logger.error("Anthropic failed: " + str(e))

        return '{"error": "No AI API available"}'

    def _parse_response(self, raw: str) -> dict:
        """Parse JSON response from AI."""
        try:
            # Strip markdown fences if present
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("Could not parse AI JSON response")
            return {
                "bull_case":    raw[:300],
                "bear_case":    "Parse error — see raw response",
                "key_levels":   {},
                "invalidation": "N/A",
                "confidence":   50,
            }

    def _confidence_label(self, score: int) -> str:
        if score >= 70:  return "High"
        if score >= 50:  return "Moderate"
        return "Low"

    def _psychology_note(self, confidence: int) -> str:
        if confidence >= 80:
            return (
                "High confidence setup. Beware of overconfidence — "
                "size correctly per your R-multiple system regardless of confidence. (Van Tharp)"
            )
        elif confidence >= 60:
            return (
                "Moderate confidence. This is a valid setup but not a fat pitch. "
                "Stick to standard position size. Do not add to the position unless the thesis confirms. (Elder)"
            )
        else:
            return (
                "Low confidence. Douglas: trading low-conviction setups is how you leak equity over time. "
                "Consider passing and waiting for a higher-quality entry."
            )

    def _build_summary(self, t: TradeThesis) -> str:
        levels = t.key_levels
        sup1   = levels.get("support_1", "N/A")
        res1   = levels.get("resistance_1", "N/A")
        target = levels.get("target", "N/A")

        return (
            f"=== TRADE THESIS: {t.ticker} ({t.timeframe.upper()}) ===\n"
            f"Confidence: {t.confidence}/100 ({t.confidence_label})\n\n"
            f"BULL: {t.bull_case}\n\n"
            f"BEAR: {t.bear_case}\n\n"
            f"LEVELS — Support: {sup1}  |  Resistance: {res1}  |  Target: {target}\n"
            f"INVALIDATION: {t.invalidation}\n\n"
            f"PSYCHOLOGY: {t.psychology_note}\n"
        )


# ── Streamlit component ────────────────────────────────────────────────────
def render_thesis_ui() -> None:
    """Full Streamlit UI for the Trade Thesis Generator."""
    try:
        import streamlit as st
    except ImportError:
        return

    st.header("🎯 Trade Thesis Generator")

    col1, col2 = st.columns([3, 1])
    ticker     = col1.text_input("Ticker", value="VOLV-B.ST",
                                 placeholder="e.g. VOLV-B.ST, ERIC-B.ST, AAPL").upper().strip()
    timeframe  = col2.selectbox("Timeframe", ["swing", "position", "intraday"])
    context    = st.text_area("Additional context (optional)",
                              placeholder="E.g. earnings next week, watching for break above 200-day MA")

    if st.button("Generate Thesis", type="primary"):
        if not ticker:
            st.warning("Enter a ticker symbol.")
            return
        with st.spinner("Fetching data and generating thesis..."):
            gen    = TradeThesisGenerator()
            thesis = gen.generate(ticker, timeframe, context or None)

        conf_color = "green" if thesis.confidence >= 70 else "orange" if thesis.confidence >= 50 else "red"

        col_a, col_b = st.columns(2)
        col_a.metric("Confidence", f"{thesis.confidence}/100", thesis.confidence_label)

        # Levels
        if thesis.key_levels:
            lv = thesis.key_levels
            col_b.markdown(
                f"**Support:** {lv.get('support_1','—')} / {lv.get('support_2','—')}  \n"
                f"**Resistance:** {lv.get('resistance_1','—')} / {lv.get('resistance_2','—')}  \n"
                f"**Target:** {lv.get('target','—')}"
            )

        tab_bull, tab_bear, tab_tech, tab_psych = st.tabs(
            ["🟢 Bull Case", "🔴 Bear Case", "📊 Technicals", "🧠 Psychology"]
        )
        with tab_bull:
            st.markdown(thesis.bull_case or "N/A")
        with tab_bear:
            st.markdown(thesis.bear_case or "N/A")
            st.error("**Invalidation:** " + (thesis.invalidation or "N/A"))
        with tab_tech:
            st.code(thesis.technical_summary)
            if thesis.fundamental_summary:
                st.caption(thesis.fundamental_summary)
        with tab_psych:
            st.info(thesis.psychology_note)

        if thesis.recent_news:
            st.markdown("**Recent News:**")
            for n in thesis.recent_news:
                st.caption("• " + n.get("headline", ""))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gen    = TradeThesisGenerator()
    thesis = gen.generate("VOLV-B.ST", timeframe="swing")
    print(thesis.summary)
    print("\nKey levels:", json.dumps(thesis.key_levels, indent=2))
