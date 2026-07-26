"""
eodhd_client.py
===============
Layer 1 — EODHD API integration for Stockholm OMX data.
Council verdict: item 2, run in parallel with LlamaIndex setup.

Covers: OMX historical OHLCV, fundamentals, insider trades,
        Swedish company profiles, Nordic market data.

Place at: openbb_platform/eodhd_client.py

Usage:
    from eodhd_client import EODHDClient
    client = EODHDClient()

    df   = client.get_ohlcv("VOLV-B", exchange="ST")
    fund = client.get_fundamentals("VOLV-B", exchange="ST")
    ins  = client.get_insider_trades("VOLV-B", exchange="ST")
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
EODHD_API_KEY = os.getenv("EODHD_API_KEY", "").strip().strip('"').strip("'")
_BASE         = "https://eodhd.com/api"
_TIMEOUT      = 20


class EODHDClient:
    """
    EODHD API client with Stockholm OMX focus.
    Get API key at: https://eodhd.com/pricing (free trial available)
    Add to .env: EODHD_API_KEY=your_key
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._key = api_key or EODHD_API_KEY
        if not self._key:
            raise ValueError(
                "EODHD_API_KEY not set. "
                "Add it to your .env file. "
                "Get a free trial key at: https://eodhd.com/pricing"
            )

    def _get(self, endpoint: str, **params) -> dict:
        params.update({"api_token": self._key, "fmt": "json"})
        url  = f"{_BASE}/{endpoint}"
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ── OHLCV ──────────────────────────────────────────────────────────────
    def get_ohlcv(
        self,
        ticker:    str,
        exchange:  str = "ST",          # ST = Stockholm OMX
        period:    str = "d",           # d=daily, w=weekly, m=monthly
        start:     Optional[str] = None,
        end:       Optional[str] = None,
        lookback:  int = 365,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for an OMX Stockholm ticker.
        ticker:   e.g. "VOLV-B", "ERIC-B", "SEB-A"
        exchange: "ST" for OMX Stockholm (default)

        Returns DataFrame with columns: open, high, low, close, volume, adjusted_close
        """
        if start is None:
            start = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")
        if end is None:
            end   = datetime.now().strftime("%Y-%m-%d")

        symbol = f"{ticker}.{exchange}"
        data   = self._get(
            f"eod/{symbol}",
            from_=start, to=end, period=period,
        )

        if not data:
            logger.warning("No data returned for " + symbol)
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        return df

    # ── Fundamentals ────────────────────────────────────────────────────────
    def get_fundamentals(
        self,
        ticker:   str,
        exchange: str = "ST",
    ) -> dict:
        """
        Fetch fundamental data: company profile, financials, ratios.
        Returns structured dict with General, Highlights, Valuation sections.
        """
        symbol = f"{ticker}.{exchange}"
        return self._get(f"fundamentals/{symbol}")

    def get_profile(self, ticker: str, exchange: str = "ST") -> dict:
        """Quick access to company profile fields."""
        data    = self.get_fundamentals(ticker, exchange)
        general = data.get("General", {})
        hlights = data.get("Highlights", {})
        return {
            "name":        general.get("Name", ""),
            "description": general.get("Description", ""),
            "sector":      general.get("GicSector", ""),
            "industry":    general.get("GicIndustry", ""),
            "currency":    general.get("CurrencyCode", "SEK"),
            "exchange":    general.get("Exchange", "Stockholm"),
            "isin":        general.get("ISIN", ""),
            "market_cap":  hlights.get("MarketCapitalization", None),
            "pe_ratio":    hlights.get("PERatio", None),
            "eps":         hlights.get("DilutedEpsTTM", None),
            "dividend":    hlights.get("DividendShare", None),
            "yield":       hlights.get("DividendYield", None),
            "52w_high":    hlights.get("52WeekHigh", None),
            "52w_low":     hlights.get("52WeekLow", None),
            "revenue_ttm": hlights.get("RevenueTTM", None),
            "roe":         hlights.get("ReturnOnEquityTTM", None),
        }

    # ── Insider Trades ──────────────────────────────────────────────────────
    def get_insider_trades(
        self,
        ticker:   str,
        exchange: str = "ST",
        limit:    int = 50,
    ) -> pd.DataFrame:
        """
        Fetch insider trading data (buying/selling by executives and directors).
        Swedish insiders file with Finansinspektionen — EODHD aggregates this.
        """
        symbol = f"{ticker}.{exchange}"
        data   = self._get(f"insider-transactions", code=symbol, limit=limit)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date", ascending=False)
        return df

    # ── News ────────────────────────────────────────────────────────────────
    def get_news(
        self,
        ticker:   str,
        exchange: str = "ST",
        limit:    int = 20,
    ) -> list:
        """Fetch recent news articles for an OMX ticker."""
        symbol = f"{ticker}.{exchange}"
        return self._get(f"news", s=symbol, limit=limit)

    # ── Screener — OMX universe ─────────────────────────────────────────────
    def get_omx_universe(self, min_market_cap_mln: float = 500.0) -> pd.DataFrame:
        """
        Fetch all stocks listed on OMX Stockholm.
        Returns DataFrame of tickers, names, sectors, market caps.
        min_market_cap_mln: filter out micro-caps (in millions SEK)
        """
        data = self._get(f"exchange-symbol-list/ST")
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        # Filter by market cap if available
        if "market_capitalization" in df.columns:
            min_cap = min_market_cap_mln * 1_000_000
            df = df[df["market_capitalization"] >= min_cap]
        return df.sort_values("market_capitalization", ascending=False)

    # ── Dividends ───────────────────────────────────────────────────────────
    def get_dividends(
        self,
        ticker:   str,
        exchange: str = "ST",
    ) -> pd.DataFrame:
        """Fetch dividend history for an OMX ticker."""
        symbol = f"{ticker}.{exchange}"
        data   = self._get(f"div/{symbol}")
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date", ascending=False)

    # ── Bulk OHLCV — end of day for full OMX ───────────────────────────────
    def get_eod_bulk(
        self,
        exchange: str = "ST",
        date:     Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch end-of-day data for ALL stocks on OMX Stockholm in one call.
        Efficient for evening scan automation.
        date: YYYY-MM-DD (defaults to latest available)
        """
        params = {}
        if date:
            params["date"] = date
        data = self._get(f"eod-bulk-last-day/{exchange}", **params)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = [c.lower() for c in df.columns]
        return df


# ── Streamlit component ────────────────────────────────────────────────────
def render_omx_quote_ui(ticker: str) -> None:
    """Quick quote card for an OMX ticker. Use inside a Streamlit page."""
    try:
        import streamlit as st
    except ImportError:
        return

    try:
        client  = EODHDClient()
        profile = client.get_profile(ticker)
        df      = client.get_ohlcv(ticker, lookback=90)

        col1, col2, col3, col4 = st.columns(4)
        if not df.empty:
            last  = float(df["close"].iloc[-1])
            prev  = float(df["close"].iloc[-2]) if len(df) > 1 else last
            chg   = (last / prev - 1) * 100 if abs(prev) > 1e-10 else 0.0
            col1.metric("Price (SEK)", f"{last:.2f}", f"{chg:+.2f}%")
        col2.metric("P/E",      str(profile.get("pe_ratio", "N/A")))
        col3.metric("Yield",    f"{(profile.get('yield') or 0)*100:.1f}%")
        col4.metric("52W High", str(profile.get("52w_high", "N/A")))

        if not df.empty:
            import plotly.graph_objects as go
            fig = go.Figure(go.Candlestick(
                x=df.index, open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                name=ticker,
            ))
            fig.update_layout(
                template="plotly_dark",
                height=300,
                xaxis_rangeslider_visible=False,
                yaxis_side="right",
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error("EODHD error: " + str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = EODHDClient()

    print("=== Volvo B — last 30 days ===")
    df = client.get_ohlcv("VOLV-B", lookback=30)
    print(df.tail(5).to_string())

    print("\n=== Volvo B — Profile ===")
    profile = client.get_profile("VOLV-B")
    for k, v in profile.items():
        print(f"  {k}: {v}")

    print("\n=== OMX Universe (top 10 by market cap) ===")
    universe = client.get_omx_universe()
    print(universe.head(10)[["code", "name", "sector"]].to_string())
