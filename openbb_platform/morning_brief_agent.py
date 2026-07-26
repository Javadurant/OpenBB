"""
morning_brief_agent.py
======================
Layer 5 — Morning Brief Agent (council: build after items 1–4 are stable).
Automated pre-market summary: news, watchlist, earnings calendar, movers.

Council requirement: Groq retry + fallback — never silently fail.

Place at: openbb_platform/morning_brief_agent.py

Usage:
    from morning_brief_agent import MorningBriefAgent
    agent = MorningBriefAgent(watchlist=["VOLV-B.ST", "ERIC-B.ST", "AAPL"])
    brief = agent.generate()
    print(brief["summary"])

Schedule with cron or Prefect at 07:30 Stockholm time:
    crontab: 30 7 * * 1-5 cd /path/to/project && python morning_brief_agent.py
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

GROQ_KEY      = os.getenv("GROQ_API_KEY",      "").strip().strip('"').strip("'")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
FMP_KEY       = os.getenv("FMP_API_KEY",        "").strip().strip('"').strip("'")
GROQ_MODEL    = "llama-3.3-70b-versatile"


class MorningBriefAgent:
    """
    Generates a structured pre-market morning brief.
    Five sections: macro, watchlist, earnings today, OMX movers, psychology prompt.
    """

    def __init__(
        self,
        watchlist:    Optional[list] = None,
        max_retries:  int = 3,
        retry_delay:  int = 10,
    ) -> None:
        self._watchlist   = watchlist or []
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def generate(self) -> dict:
        """
        Generate the full morning brief.
        Returns dict with sections + a final summary.
        Never raises — always returns something, even if degraded.
        """
        date_str = datetime.now().strftime("%A %d %B %Y")
        brief    = {
            "date":        date_str,
            "macro":       self._fetch_macro(),
            "watchlist":   self._scan_watchlist(),
            "earnings":    self._fetch_earnings_today(),
            "omx_movers":  self._fetch_omx_movers(),
            "psychology":  self._morning_psychology(),
            "summary":     "",
        }
        brief["summary"] = self._synthesize(brief)
        return brief

    # ── Section fetchers ───────────────────────────────────────────────────

    def _fetch_macro(self) -> dict:
        """Key macro data: futures, VIX, USD/SEK, yields."""
        data = {}
        try:
            import yfinance as yf
            tickers = {
                "SP500_futures": "ES=F",
                "NDX_futures":   "NQ=F",
                "VIX":           "^VIX",
                "USD_SEK":       "USDSEK=X",
                "US10Y_yield":   "^TNX",
                "Crude_oil":     "CL=F",
                "Gold":          "GC=F",
            }
            for label, sym in tickers.items():
                try:
                    t    = yf.Ticker(sym)
                    hist = t.history(period="2d")
                    if not hist.empty:
                        last  = float(hist["Close"].iloc[-1])
                        prev  = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
                        chg   = (last / prev - 1) * 100 if abs(prev) > 1e-10 else 0.0
                        data[label] = {"price": round(last, 3), "change_pct": round(chg, 2)}
                except Exception:
                    pass
        except ImportError:
            data["error"] = "yfinance not installed"
        return data

    def _scan_watchlist(self) -> list:
        """Quick price + change for each watchlist ticker."""
        results = []
        if not self._watchlist:
            return results
        try:
            import yfinance as yf
            for ticker in self._watchlist[:20]:
                try:
                    t    = yf.Ticker(ticker)
                    hist = t.history(period="2d")
                    if not hist.empty:
                        last  = float(hist["Close"].iloc[-1])
                        prev  = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
                        vol   = float(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
                        chg   = (last / prev - 1) * 100 if abs(prev) > 1e-10 else 0.0
                        results.append({
                            "ticker":     ticker,
                            "price":      round(last, 2),
                            "change_pct": round(chg, 2),
                            "volume":     int(vol),
                        })
                except Exception:
                    pass
        except ImportError:
            pass
        return sorted(results, key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    def _fetch_earnings_today(self) -> list:
        """Fetch earnings calendar for today from FMP."""
        if not FMP_KEY:
            return []
        import requests
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            resp = requests.get(
                "https://financialmodelingprep.com/api/v3/earning_calendar",
                params={"from": today, "to": today, "apikey": FMP_KEY},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return [
                    {
                        "ticker": e.get("symbol", ""),
                        "time":   e.get("time", ""),
                        "eps_est": e.get("epsEstimated", None),
                        "rev_est": e.get("revenueEstimated", None),
                    }
                    for e in data[:15]
                ]
        except Exception as e:
            logger.warning("Earnings fetch failed: " + str(e))
        return []

    def _fetch_omx_movers(self) -> dict:
        """Top 5 gainers and losers on OMX Stockholm."""
        if not os.getenv("EODHD_API_KEY"):
            return {"note": "EODHD_API_KEY required for OMX movers"}
        try:
            from eodhd_client import EODHDClient
            client  = EODHDClient()
            df      = client.get_eod_bulk(exchange="ST")
            if df.empty:
                return {}
            df["change_pct"] = ((df["close"] - df["open"]) / df["open"].replace(0, 1e-10)) * 100
            gainers = df.nlargest(5, "change_pct")[["code", "close", "change_pct"]].to_dict("records")
            losers  = df.nsmallest(5, "change_pct")[["code", "close", "change_pct"]].to_dict("records")
            return {"gainers": gainers, "losers": losers}
        except Exception as e:
            logger.warning("OMX movers failed: " + str(e))
            return {}

    def _morning_psychology(self) -> str:
        """One grounding question from the psychology engine."""
        try:
            from psychology_engine import PsychologyEngine
            return PsychologyEngine().morning_psychology_check()
        except Exception:
            return "What is your edge today? If you cannot state it clearly, do not trade. (Douglas)"

    # ── AI synthesis with retry + fallback ────────────────────────────────

    def _synthesize(self, brief: dict) -> str:
        """
        Use AI to write the 5-point morning briefing from the raw data.
        Retry on rate limits. Never fail silently.
        """
        macro     = brief.get("macro", {})
        watchlist = brief.get("watchlist", [])
        earnings  = brief.get("earnings", [])
        movers    = brief.get("omx_movers", {})
        psych     = brief.get("psychology", "")

        # Build prompt
        macro_text = ", ".join(
            k.replace("_", " ") + ": " + str(v.get("price", "?")) +
            " (" + str(v.get("change_pct", 0)) + "%)"
            for k, v in macro.items()
            if isinstance(v, dict)
        ) or "No macro data available."

        watchlist_text = ", ".join(
            t["ticker"] + " " + str(t.get("change_pct", 0)) + "%"
            for t in watchlist[:10]
        ) or "No watchlist data."

        earnings_text = ", ".join(
            e["ticker"] + " (" + (e.get("time") or "TBD") + ")"
            for e in earnings[:8]
        ) or "No earnings today."

        prompt = (
            "You are preparing a pre-market briefing for a professional trader. "
            "Stockholm time. Date: " + brief["date"] + "\n\n"
            "DATA:\n"
            "Macro: " + macro_text + "\n"
            "Watchlist: " + watchlist_text + "\n"
            "Earnings today: " + earnings_text + "\n"
            "Psychology: " + psych + "\n\n"
            "Write a 5-point briefing. Each point is one sharp sentence. "
            "Point 5 is always the psychology prompt. "
            "Be direct. No fluff. Focus on what matters for today's trading session."
        )

        # Try Groq with retry
        if GROQ_KEY:
            for attempt in range(1, self._max_retries + 1):
                try:
                    import requests as req
                    resp = req.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": "Bearer " + GROQ_KEY,
                            "Content-Type":  "application/json",
                        },
                        json={
                            "model":       GROQ_MODEL,
                            "messages":    [{"role": "user", "content": prompt}],
                            "max_tokens":  512,
                            "temperature": 0.3,
                        },
                        timeout=20,
                    )
                    if resp.status_code == 429:
                        # Rate limited — wait and retry
                        logger.warning(
                            "Groq rate limited (attempt " + str(attempt) + "/" +
                            str(self._max_retries) + "). Waiting " +
                            str(self._retry_delay) + "s..."
                        )
                        time.sleep(self._retry_delay)
                        continue
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"]
                except Exception as e:
                    if attempt < self._max_retries:
                        time.sleep(self._retry_delay)
                    else:
                        logger.error("Groq synthesis failed after retries: " + str(e))

        # Anthropic fallback
        if ANTHROPIC_KEY:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                msg    = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text
            except Exception as e:
                logger.error("Anthropic synthesis failed: " + str(e))

        # Static fallback — never silently fail
        return self._static_brief(brief)

    def _static_brief(self, brief: dict) -> str:
        """
        Deterministic fallback brief when all AI calls fail.
        Always returns something useful.
        """
        macro     = brief.get("macro", {})
        watchlist = brief.get("watchlist", [])
        earnings  = brief.get("earnings", [])
        psych     = brief.get("psychology", "")

        vix    = macro.get("VIX", {}).get("price", "N/A")
        usdsek = macro.get("USD_SEK", {}).get("price", "N/A")
        sp_chg = macro.get("SP500_futures", {}).get("change_pct", 0)

        mover  = watchlist[0] if watchlist else None
        mover_text = (
            mover["ticker"] + " leading at " + str(mover["change_pct"]) + "%"
            if mover else "no watchlist data"
        )

        earn_text = (
            ", ".join(e["ticker"] for e in earnings[:5]) or "none"
        )

        lines = [
            "1. S&P 500 futures: " + ("up" if sp_chg >= 0 else "down") + " " + str(abs(sp_chg)) + "% pre-market.",
            "2. VIX: " + str(vix) + ". USD/SEK: " + str(usdsek) + ".",
            "3. Watchlist: " + mover_text + ".",
            "4. Earnings today: " + earn_text + ".",
            "5. " + psych,
        ]
        return "\n".join(lines)


# ── Streamlit component ────────────────────────────────────────────────────
def render_morning_brief_ui(watchlist: Optional[list] = None) -> None:
    """Render the morning brief in a Streamlit page."""
    try:
        import streamlit as st
    except ImportError:
        return

    st.header("🌅 Morning Brief")

    if st.button("Generate Morning Brief", type="primary"):
        with st.spinner("Fetching market data..."):
            agent = MorningBriefAgent(watchlist=watchlist or [])
            brief = agent.generate()

        st.subheader(brief["date"])
        st.markdown(brief["summary"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**📊 Macro**")
            for k, v in brief["macro"].items():
                if isinstance(v, dict):
                    chg = v.get("change_pct", 0)
                    col = "🟢" if chg >= 0 else "🔴"
                    st.caption(col + " " + k.replace("_", " ") +
                               ": " + str(v.get("price", "")) +
                               " (" + str(chg) + "%)")

        with col2:
            st.markdown("**👁️ Watchlist**")
            for t in brief["watchlist"][:8]:
                chg = t.get("change_pct", 0)
                col = "🟢" if chg >= 0 else "🔴"
                st.caption(col + " " + t["ticker"] +
                           ": " + str(t.get("price", "")) +
                           " (" + str(chg) + "%)")

        if brief["earnings"]:
            st.markdown("**📅 Earnings Today**")
            for e in brief["earnings"][:8]:
                st.caption("• " + e["ticker"] +
                           " — " + (e.get("time") or "TBD"))

        st.info("🧠 " + brief["psychology"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = MorningBriefAgent(
        watchlist=["VOLV-B.ST", "ERIC-B.ST", "SEB-A.ST", "AAPL", "NVDA"]
    )
    brief = agent.generate()
    print("=== MORNING BRIEF — " + brief["date"] + " ===\n")
    print(brief["summary"])
    print("\n=== MACRO ===")
    for k, v in brief["macro"].items():
        print("  " + k + ": " + str(v))
