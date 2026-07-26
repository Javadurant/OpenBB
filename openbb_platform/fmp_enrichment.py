"""
fmp_enrichment.py
═══════════════════════════════════════════════════════════════════════════════
Bloomberg-Grade Data Enrichment for QuantEdge

COUNCIL VERDICT: "Use all 7 FMP stable endpoints + yfinance for gaps.
Build complete enrichment module. Integrate into Command Center.
AI synthesis via Groq ties it all together."

DATA LAYERS (Bloomberg equivalent):
  1. ANALYST CONSENSUS  — FMP /grades + /analyst-estimates + /price-target-consensus
  2. EARNINGS INTEL     — FMP /earnings-calendar + /earnings (history + surprise)
  3. VALUATION CONTEXT  — FMP /ratios + /profile
  4. INSTITUTIONAL FLOW — yfinance .institutional_holders (13F proxy)
  5. INSIDER ACTIVITY   — yfinance .insider_transactions
  6. NEWS HEADLINES     — yfinance .news
  7. AI SYNTHESIS       — Groq LLaMA 3.3 70B combines all into actionable brief

SOURCES:
  - FMP stable API (7 working endpoints on free tier)
  - yfinance (institutional, insider, news — free, no key needed)
  - Groq LLaMA 3.3 70B (AI synthesis — free tier)
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger("FMPEnrichment")


class FMPEnrichment:
    """
    Bloomberg-equivalent data enrichment layer.
    Combines FMP stable API + yfinance + Groq AI.
    """

    def __init__(self) -> None:
        self._fmp_available = True
        self._yf_available = True

    # ─── FMP STABLE ENDPOINTS (7 working) ─────────────────────────────────

    def analyst_grades(self, ticker: str, limit: int = 20) -> List[Dict]:
        """FMP /stable/grades — analyst upgrades, downgrades, initiations."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/grades", symbol=ticker, limit=str(limit))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"FMP grades failed for {ticker}: {e}")
            return []

    def analyst_estimates(self, ticker: str) -> List[Dict]:
        """FMP /stable/analyst-estimates — EPS and revenue forecasts."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/analyst-estimates", symbol=ticker, limit="4", period="annual")
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"FMP estimates failed for {ticker}: {e}")
            return []

    def price_target_consensus(self, ticker: str) -> Dict:
        """FMP /stable/price-target-consensus — analyst consensus target."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/price-target-consensus", symbol=ticker)
            if isinstance(data, list) and data:
                return data[0]
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"FMP price target failed for {ticker}: {e}")
            return {}

    def earnings_calendar(self, days_ahead: int = 30) -> List[Dict]:
        """FMP /stable/earnings-calendar — upcoming earnings dates."""
        try:
            from data_clients import fmp_get
            today = datetime.now().strftime("%Y-%m-%d")
            future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            data = fmp_get("/earnings-calendar", **{"from": today, "to": future})
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"FMP earnings calendar failed: {e}")
            return []

    def earnings_history(self, ticker: str) -> List[Dict]:
        """FMP /stable/earnings — historical EPS actual vs estimated."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/earnings", symbol=ticker)
            return data[:12] if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"FMP earnings history failed for {ticker}: {e}")
            return []

    def financial_ratios(self, ticker: str) -> Dict:
        """FMP /stable/ratios — P/E, P/B, ROE, D/E, current ratio, etc."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/ratios", symbol=ticker, limit="1", period="annual")
            if isinstance(data, list) and data:
                return data[0]
            return {}
        except Exception as e:
            logger.warning(f"FMP ratios failed for {ticker}: {e}")
            return {}

    def company_profile(self, ticker: str) -> Dict:
        """FMP /stable/profile — market cap, sector, description."""
        try:
            from data_clients import fmp_get
            data = fmp_get("/profile", symbol=ticker)
            if isinstance(data, list) and data:
                return data[0]
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"FMP profile failed for {ticker}: {e}")
            return {}

    # ─── YFINANCE FALLBACKS (gaps FMP free tier doesn't cover) ────────────

    def institutional_holders(self, ticker: str) -> pd.DataFrame:
        """yfinance .institutional_holders — 13F institutional ownership proxy."""
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            holders = tk.institutional_holders
            if holders is not None and not holders.empty:
                return holders.head(15)
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"yfinance institutional holders failed for {ticker}: {e}")
            return pd.DataFrame()

    def insider_transactions(self, ticker: str) -> pd.DataFrame:
        """yfinance .insider_transactions — recent insider buys/sells."""
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            insiders = tk.insider_transactions
            if insiders is not None and not insiders.empty:
                return insiders.head(15)
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"yfinance insider transactions failed for {ticker}: {e}")
            return pd.DataFrame()

    def stock_news(self, ticker: str) -> List[Dict]:
        """yfinance .news — recent headlines for a ticker."""
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            news = tk.news
            if news:
                return news[:10]
            return []
        except Exception as e:
            logger.warning(f"yfinance news failed for {ticker}: {e}")
            return []

    # ─── FULL ENRICHMENT (all layers combined) ────────────────────────────

    def full_enrichment(self, ticker: str) -> Dict[str, Any]:
        """
        Fetches ALL Bloomberg-equivalent data layers for a single ticker.
        Returns a dict with all enrichment data.
        """
        result = {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "profile": self.company_profile(ticker),
            "ratios": self.financial_ratios(ticker),
            "grades": self.analyst_grades(ticker, limit=10),
            "estimates": self.analyst_estimates(ticker),
            "price_target": self.price_target_consensus(ticker),
            "earnings_history": self.earnings_history(ticker),
            "institutional": self.institutional_holders(ticker),
            "insider": self.insider_transactions(ticker),
            "news": self.stock_news(ticker),
        }

        # Compute derived signals
        result["signals"] = self._derive_signals(result)

        return result

    def _derive_signals(self, data: Dict) -> Dict[str, Any]:
        """Compute actionable signals from raw enrichment data."""
        signals = {}

        # 1. Analyst sentiment from grades
        grades = data.get("grades", [])
        if grades:
            recent = grades[:10]
            upgrades = sum(1 for g in recent if "upgrade" in g.get("newGrade", "").lower() or
                          "buy" in g.get("newGrade", "").lower())
            downgrades = sum(1 for g in recent if "downgrade" in g.get("newGrade", "").lower() or
                            "sell" in g.get("newGrade", "").lower())
            signals["analyst_sentiment"] = "BULLISH" if upgrades > downgrades else \
                                            "BEARISH" if downgrades > upgrades else "NEUTRAL"
            signals["recent_upgrades"] = upgrades
            signals["recent_downgrades"] = downgrades

        # 2. Price target upside/downside
        pt = data.get("price_target", {})
        profile = data.get("profile", {})
        current_price = profile.get("price", 0)
        target = pt.get("targetConsensus", 0)
        if current_price and target:
            upside = ((target - current_price) / current_price) * 100
            signals["target_upside_pct"] = round(upside, 1)
            signals["target_consensus"] = target

        # 3. Earnings surprise trend
        earnings = data.get("earnings_history", [])
        if earnings:
            surprises = []
            for e in earnings[:4]:
                actual = e.get("epsActual")
                estimated = e.get("epsEstimated")
                if actual is not None and estimated is not None and estimated != 0:
                    surprise_pct = ((actual - estimated) / abs(estimated)) * 100
                    surprises.append(surprise_pct)
            if surprises:
                avg_surprise = sum(surprises) / len(surprises)
                signals["avg_eps_surprise_pct"] = round(avg_surprise, 1)
                signals["consecutive_beats"] = sum(1 for s in surprises if s > 0)

        # 4. Insider activity
        insider_df = data.get("insider", pd.DataFrame())
        if not insider_df.empty and "Transaction" in insider_df.columns:
            buys = insider_df["Transaction"].str.contains("Purchase|Buy", case=False, na=False).sum()
            sells = insider_df["Transaction"].str.contains("Sale|Sell", case=False, na=False).sum()
            signals["insider_buys"] = int(buys)
            signals["insider_sells"] = int(sells)
            signals["insider_signal"] = "BULLISH" if buys > sells else \
                                         "BEARISH" if sells > buys else "NEUTRAL"

        # 5. Valuation from ratios
        ratios = data.get("ratios", {})
        pe = ratios.get("priceEarningsRatio")
        pb = ratios.get("priceToBookRatio")
        roe = ratios.get("returnOnEquity")
        de = ratios.get("debtEquityRatio")
        if pe is not None:
            signals["pe_ratio"] = round(pe, 1)
            signals["valuation"] = "CHEAP" if pe < 15 else "FAIR" if pe < 25 else "EXPENSIVE"
        if roe is not None:
            signals["roe"] = round(roe * 100, 1) if roe < 1 else round(roe, 1)
        if de is not None:
            signals["debt_equity"] = round(de, 2)

        return signals


    # ─── AI SYNTHESIS (Groq LLaMA 3.3 70B) ────────────────────────────────

    def ai_intelligence_brief(self, ticker: str, enrichment: Optional[Dict] = None) -> str:
        """
        Bloomberg Intelligence equivalent — AI-powered synthesis of all data.
        Produces an actionable brief like a senior equity analyst would.
        """
        if enrichment is None:
            enrichment = self.full_enrichment(ticker)

        signals = enrichment.get("signals", {})
        profile = enrichment.get("profile", {})
        pt = enrichment.get("price_target", {})
        grades = enrichment.get("grades", [])[:5]
        earnings = enrichment.get("earnings_history", [])[:4]

        # Build context for Groq
        context_parts = [f"TICKER: {ticker}"]

        if profile:
            context_parts.append(f"COMPANY: {profile.get('companyName', ticker)}")
            context_parts.append(f"SECTOR: {profile.get('sector', 'Unknown')}")
            context_parts.append(f"MARKET CAP: ${profile.get('marketCap', 0):,.0f}")
            context_parts.append(f"CURRENT PRICE: ${profile.get('price', 0):.2f}")

        if signals:
            for k, v in signals.items():
                context_parts.append(f"{k.upper()}: {v}")

        if pt:
            context_parts.append(f"TARGET HIGH: ${pt.get('targetHigh', 0):.2f}")
            context_parts.append(f"TARGET LOW: ${pt.get('targetLow', 0):.2f}")
            context_parts.append(f"TARGET CONSENSUS: ${pt.get('targetConsensus', 0):.2f}")

        if grades:
            grade_lines = [f"  {g.get('date', '?')}: {g.get('gradingCompany', '?')} → {g.get('newGrade', '?')}"
                          for g in grades]
            context_parts.append("RECENT ANALYST GRADES:\n" + "\n".join(grade_lines))

        if earnings:
            eps_lines = [f"  {e.get('date', '?')}: EPS actual={e.get('epsActual', '?')} vs est={e.get('epsEstimated', '?')}"
                        for e in earnings]
            context_parts.append("EARNINGS HISTORY:\n" + "\n".join(eps_lines))

        context = "\n".join(context_parts)

        try:
            from data_clients import groq_client
            response = groq_client().chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": (
                        "You are a senior equity analyst at a Bloomberg-grade institution. "
                        "Produce a concise intelligence brief (250 words max) covering:\n"
                        "1. THESIS — Is this stock a buy, hold, or sell right now and why?\n"
                        "2. CATALYST — What's the next event that could move the stock?\n"
                        "3. RISK — What's the biggest risk the consensus is ignoring?\n"
                        "4. ACTION — One specific, actionable recommendation.\n\n"
                        "Be direct. No hedging. Use the data provided."
                    )},
                    {"role": "user", "content": f"Produce intelligence brief for:\n\n{context}"},
                ],
                temperature=0.5,
                max_tokens=600,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq AI brief failed for {ticker}: {e}")
            return f"AI brief unavailable: {e}"
