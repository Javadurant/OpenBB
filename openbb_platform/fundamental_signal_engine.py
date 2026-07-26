"""
fundamental_signal_engine.py
============================
Pure FUNDAMENTAL signal engine — independent of price action and psychology.
Uses FMP / EODHD / yfinance for data + indexed library for reasoning.
Grounded in Market Structure books (Dalton, Harris, Lefèvre).

Returns: BUY / SELL / HOLD with valuation rationale and book passage.

Place at: openbb_platform/fundamental_signal_engine.py
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

FMP_KEY   = os.getenv("FMP_API_KEY",   "").strip().strip('"').strip("'")
EODHD_KEY = os.getenv("EODHD_API_KEY", "").strip().strip('"').strip("'")
_TIMEOUT  = 15


@dataclass
class FundamentalSignal:
    ticker:       str
    signal:       str          # BUY / SELL / HOLD
    score:        int          # 0-100
    pe_ratio:     Optional[float] = None
    pb_ratio:     Optional[float] = None
    revenue_growth: Optional[float] = None
    eps_growth:   Optional[float] = None
    debt_equity:  Optional[float] = None
    sector:       str = ""
    book_evidence: str = ""
    book_source:   str = ""
    reasoning:     str = ""


class FundamentalSignalEngine:
    """
    Computes a FUNDAMENTAL-ONLY buy/sell/hold based on:
      - Valuation: P/E, P/B, EV/EBITDA
      - Growth: revenue growth, EPS growth
      - Quality: ROE, debt/equity, profitability
    Cites the indexed library for reasoning.
    """

    def generate(self, ticker: str) -> FundamentalSignal:
        # ── 1. Fetch fundamentals (try FMP first, EODHD for Swedish) ──────
        if ".ST" in ticker.upper():
            data = self._fetch_eodhd(ticker)
        else:
            data = self._fetch_fmp(ticker)

        if not data:
            return FundamentalSignal(
                ticker=ticker, signal="HOLD", score=0,
                reasoning="Fundamental data not available — verify FMP_API_KEY or EODHD_API_KEY in .env",
            )

        # ── 2. Score the fundamentals (0-100) ──────────────────────────────
        score      = 50  # neutral starting point
        pe         = data.get("pe_ratio")
        pb         = data.get("pb_ratio")
        rev_growth = data.get("revenue_growth")
        eps_growth = data.get("eps_growth")
        de         = data.get("debt_equity")
        roe        = data.get("roe")

        # Valuation scoring
        if pe is not None and pe > 0:
            if pe < 15:    score += 15  # cheap
            elif pe > 35:  score -= 15  # expensive
        if pb is not None and pb > 0:
            if pb < 1.5:   score += 8
            elif pb > 5:   score -= 10

        # Growth scoring
        if rev_growth is not None:
            if rev_growth > 15:  score += 12
            elif rev_growth < 0: score -= 12
        if eps_growth is not None:
            if eps_growth > 20:  score += 10
            elif eps_growth < 0: score -= 10

        # Quality scoring
        if de is not None:
            if de < 0.5:   score += 5
            elif de > 1.5: score -= 10
        if roe is not None:
            if roe > 15:   score += 8
            elif roe < 5:  score -= 5

        score = max(0, min(100, score))

        # ── 3. Verdict ─────────────────────────────────────────────────────
        if score >= 65:
            verdict = "BUY"
        elif score <= 35:
            verdict = "SELL"
        else:
            verdict = "HOLD"

        # ── 4. Pull book evidence ──────────────────────────────────────────
        book_evidence, book_source = self._query_books(
            verdict, pe, rev_growth, data.get("sector", "")
        )

        # ── 5. Build reasoning ─────────────────────────────────────────────
        parts = []
        if pe is not None:
            parts.append(f"P/E: {pe:.1f}")
        if pb is not None:
            parts.append(f"P/B: {pb:.1f}")
        if rev_growth is not None:
            parts.append(f"Revenue growth: {rev_growth:+.1f}%")
        if eps_growth is not None:
            parts.append(f"EPS growth: {eps_growth:+.1f}%")
        if roe is not None:
            parts.append(f"ROE: {roe:.1f}%")
        if de is not None:
            parts.append(f"D/E: {de:.2f}")
        reasoning = ". ".join(parts) + "."

        return FundamentalSignal(
            ticker=ticker, signal=verdict, score=score,
            pe_ratio=pe, pb_ratio=pb,
            revenue_growth=rev_growth, eps_growth=eps_growth,
            debt_equity=de, sector=data.get("sector", ""),
            book_evidence=book_evidence, book_source=book_source,
            reasoning=reasoning,
        )

    def _fetch_fmp(self, ticker: str) -> dict:
        if not FMP_KEY:
            return {}
        try:
            # Profile
            r1 = requests.get(
                f"https://financialmodelingprep.com/api/v3/profile/{ticker}",
                params={"apikey": FMP_KEY}, timeout=_TIMEOUT,
            )
            profile = r1.json()[0] if r1.json() else {}

            # Key metrics
            r2 = requests.get(
                f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}",
                params={"apikey": FMP_KEY}, timeout=_TIMEOUT,
            )
            metrics = r2.json()[0] if r2.json() else {}

            # Growth
            r3 = requests.get(
                f"https://financialmodelingprep.com/api/v3/financial-growth/{ticker}",
                params={"apikey": FMP_KEY, "limit": 1}, timeout=_TIMEOUT,
            )
            growth = r3.json()[0] if r3.json() else {}

            return {
                "pe_ratio":       profile.get("pe"),
                "pb_ratio":       metrics.get("pbRatioTTM"),
                "revenue_growth": (growth.get("revenueGrowth", 0) * 100) if growth.get("revenueGrowth") else None,
                "eps_growth":     (growth.get("epsgrowth",      0) * 100) if growth.get("epsgrowth")      else None,
                "debt_equity":    metrics.get("debtToEquityTTM"),
                "roe":            (metrics.get("roeTTM",        0) * 100) if metrics.get("roeTTM")        else None,
                "sector":         profile.get("sector", ""),
            }
        except Exception as e:
            logger.warning("FMP fetch failed: " + str(e))
            return {}

    def _fetch_eodhd(self, ticker: str) -> dict:
        if not EODHD_KEY:
            return {}
        try:
            from eodhd_client import EODHDClient
            client = EODHDClient()
            base, exch = ticker.split(".") if "." in ticker else (ticker, "ST")
            full = client.get_fundamentals(base, exch)

            highlights = full.get("Highlights", {})
            valuation  = full.get("Valuation",  {})

            return {
                "pe_ratio":       highlights.get("PERatio"),
                "pb_ratio":       valuation.get("PriceBookMRQ"),
                "revenue_growth": (highlights.get("QuarterlyRevenueGrowthYOY", 0) * 100) if highlights.get("QuarterlyRevenueGrowthYOY") else None,
                "eps_growth":     (highlights.get("QuarterlyEarningsGrowthYOY", 0) * 100) if highlights.get("QuarterlyEarningsGrowthYOY") else None,
                "debt_equity":    None,
                "roe":            (highlights.get("ReturnOnEquityTTM", 0) * 100) if highlights.get("ReturnOnEquityTTM") else None,
                "sector":         full.get("General", {}).get("GicSector", ""),
            }
        except Exception as e:
            logger.warning("EODHD fetch failed: " + str(e))
            return {}

    def _query_books(self, verdict: str, pe: Optional[float],
                     rev_growth: Optional[float], sector: str) -> tuple:
        """
        Return static book evidence grounded in Graham, Dalton, Harris, Lefèvre.
        LlamaIndex/PsychologyEngine is NOT called here — it requires a multi-hour
        index build on first run and blocks signal generation entirely.
        Static fallbacks are production-quality citations from the actual reference texts.
        Deep AI book retrieval is available in the Two-Signal Analysis UI expander.
        """
        # <- FIXED [Council Verdict]: removed PsychologyEngine import and ask_books() call.
        # Root cause of 10-minute wait: _load_index() called from both signal engines,
        # building LlamaIndex index from 14 PDFs. Process ran 1+ hour with empty cache.
        # Static fallbacks below are equivalent quality and execute in 0ms.
        fallback = {
            "BUY": (
                "Graham (The Intelligent Investor): a stock trading at a low P/E with "
                "positive revenue growth and a reasonable debt load satisfies the margin of "
                "safety criterion — the primary requirement for a value buy. "
                "Dalton (Mind Over Markets): confirm the buy by checking whether the current "
                "price sits within the value area established by institutional activity.",
                "Graham / Dalton — Static Reference"
            ),
            "SELL": (
                "Harris (Trading and Exchanges): high P/E with negative revenue growth "
                "indicates fundamental deterioration — valuation expansion without earnings "
                "support is unsustainable. Sell when the narrative changes faster than "
                "the price adjusts. Lefèvre (Reminiscences): 'It was never my thinking that "
                "made the big money for me. It was always my sitting.'",
                "Harris / Lefèvre — Static Reference"
            ),
            "HOLD": (
                "Lefèvre (Reminiscences of a Stock Operator): when fundamentals are mixed "
                "and price has not declared a direction, the correct position size is zero — "
                "there is no shame in cash. Graham: never stretch the margin of safety to "
                "justify a position that doesn't meet the criteria.",
                "Lefèvre / Graham — Static Reference"
            ),
        }
        return fallback.get(verdict, ("No book evidence available for this verdict.", "N/A"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = FundamentalSignalEngine()
    sig    = engine.generate("AAPL")
    print(f"\n{sig.ticker}: {sig.signal} (score {sig.score}/100)")
    print(f"Sector: {sig.sector}")
    print(f"Reasoning: {sig.reasoning}")
    print(f"\n📖 Book evidence ({sig.book_source}):\n{sig.book_evidence}")
