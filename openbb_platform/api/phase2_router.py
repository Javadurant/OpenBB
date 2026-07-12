"""
api/phase2_router.py
Phase 2 endpoints — Discover (screeners), Portfolio (watchlist), Market (regime), Sweden (OMX).
All call REAL engine functions, no stubs.
"""
from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.CRITICAL)
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("phase2_router")
router = APIRouter(tags=["phase2"])

# ── Helpers ──────────────────────────────────────────────────────────────
def _safe(value: Any, default: Any = None) -> Any:
    if value is None: return default
    try:
        import math
        if hasattr(value, "item"): value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)): return default
        return value
    except Exception: return default

def _round(value: Any, ndigits: int = 4, default: Any = None) -> Any:
    v = _safe(value, default)
    if isinstance(v, (int, float)):
        try: return round(v, ndigits)
        except Exception: return default
    return default

# ── Universe definitions ────────────────────────────────────────────────
UNIVERSE_US = [
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","AVGO","JPM","V",
    "WMT","UNH","XOM","JNJ","PG","ORCL","HD","MA","COST","NFLX",
    "ADBE","CRM","AMD","CSCO","PEP","TMUS","ABBV","KO","BAC","INTC",
]
UNIVERSE_OMX = [
    "VOLV-B.ST","ERIC-B.ST","HM-B.ST","INVE-B.ST","ATCO-A.ST","SAND.ST",
    "SEB-A.ST","EVO.ST","ABB.ST","ASSA-B.ST","TELIA.ST","SWED-A.ST",
    "NDA-SE.ST","ALFA.ST","SHB-A.ST","SKF-B.ST","SCA-B.ST","ELUX-B.ST",
]

# ═══════════════════════════════════════════════════════════════════════
# DISCOVER — Screeners & idea generators
# ═══════════════════════════════════════════════════════════════════════

class ScreenerRequest(BaseModel):
    universe: str = "US"   # "US" or "OMX"
    limit:    int = 20

@router.post("/api/discover/momentum")
def screener_momentum(req: ScreenerRequest) -> dict[str, Any]:
    """3-month momentum: return % return + trend label per ticker."""
    import yfinance as yf
    universe = UNIVERSE_OMX if req.universe == "OMX" else UNIVERSE_US
    rows: list[dict[str, Any]] = []
    for sym in universe[:req.limit]:
        try:
            h = yf.Ticker(sym).history(period="3mo")
            if len(h) < 5: continue
            ret = (float(h["Close"].iloc[-1]) / float(h["Close"].iloc[0]) - 1) * 100
            vol = float(h["Volume"].tail(20).mean()) if "Volume" in h else 0
            rows.append({
                "symbol": sym,
                "return_3m_pct": _round(ret, 2),
                "trend":         "up" if ret > 5 else ("down" if ret < -5 else "flat"),
                "last_price":    _round(float(h["Close"].iloc[-1]), 2),
                "avg_volume_20d": int(vol) if vol > 0 else None,
            })
        except Exception as e:
            logger.warning("momentum %s: %s", sym, e)
    rows.sort(key=lambda r: r["return_3m_pct"] or 0, reverse=True)
    return {"status": "ok", "screener": "momentum", "universe": req.universe, "count": len(rows), "results": rows}


@router.post("/api/discover/value")
def screener_value(req: ScreenerRequest) -> dict[str, Any]:
    """Value screener: low P/E + healthy ROE."""
    from pages.ai_trading_agent import _fetch_info
    universe = UNIVERSE_OMX if req.universe == "OMX" else UNIVERSE_US
    rows: list[dict[str, Any]] = []
    for sym in universe[:req.limit]:
        try:
            info = _fetch_info(sym)
            pe   = info.get("pe_ratio")
            roe  = info.get("roe")
            if pe is None or roe is None: continue
            if pe <= 0 or pe > 100:        continue
            score = (1.0 / pe) * 100 + (roe or 0) * 50
            rows.append({
                "symbol":    sym,
                "name":      info.get("name", sym),
                "pe_ratio":  _round(pe, 2),
                "roe":       _round(roe, 4),
                "margin":    _round(info.get("profit_margin"), 4),
                "div_yield": _round(info.get("dividend_yield"), 2),
                "value_score": _round(score, 2),
            })
        except Exception as e:
            logger.warning("value %s: %s", sym, e)
    rows.sort(key=lambda r: r["value_score"] or 0, reverse=True)
    return {"status": "ok", "screener": "value", "universe": req.universe, "count": len(rows), "results": rows}


@router.post("/api/discover/dividend")
def screener_dividend(req: ScreenerRequest) -> dict[str, Any]:
    """Dividend yield screener (yield > 2%)."""
    from pages.ai_trading_agent import _fetch_info
    universe = UNIVERSE_OMX if req.universe == "OMX" else UNIVERSE_US
    rows: list[dict[str, Any]] = []
    for sym in universe[:req.limit]:
        try:
            info = _fetch_info(sym)
            y = info.get("dividend_yield")
            if y is None or y < 2: continue
            rows.append({
                "symbol":    sym,
                "name":      info.get("name", sym),
                "div_yield": _round(y, 2),
                "payout_ratio": _round(info.get("payout_ratio"), 4),
                "pe_ratio":  _round(info.get("pe_ratio"), 2),
                "sector":    info.get("sector", "—"),
            })
        except Exception as e:
            logger.warning("div %s: %s", sym, e)
    rows.sort(key=lambda r: r["div_yield"] or 0, reverse=True)
    return {"status": "ok", "screener": "dividend", "universe": req.universe, "count": len(rows), "results": rows}


@router.post("/api/discover/quality")
def screener_quality(req: ScreenerRequest) -> dict[str, Any]:
    """Quality screener: ROE > 15% + positive growth + healthy margin."""
    from pages.ai_trading_agent import _fetch_info
    universe = UNIVERSE_OMX if req.universe == "OMX" else UNIVERSE_US
    rows: list[dict[str, Any]] = []
    for sym in universe[:req.limit]:
        try:
            info = _fetch_info(sym)
            roe  = info.get("roe") or 0
            mar  = info.get("profit_margin") or 0
            grow = info.get("revenue_growth") or 0
            if roe <= 0.15:  continue   # require ROE > 15%
            if mar <= 0:     continue
            quality_score = (roe * 100) + (mar * 200) + (grow * 100)
            rows.append({
                "symbol":   sym,
                "name":     info.get("name", sym),
                "roe":      _round(roe, 4),
                "margin":   _round(mar, 4),
                "rev_growth": _round(grow, 4),
                "quality_score": _round(quality_score, 2),
                "sector":   info.get("sector", "—"),
            })
        except Exception as e:
            logger.warning("quality %s: %s", sym, e)
    rows.sort(key=lambda r: r["quality_score"] or 0, reverse=True)
    return {"status": "ok", "screener": "quality", "universe": req.universe, "count": len(rows), "results": rows}


# ═══════════════════════════════════════════════════════════════════════
# PORTFOLIO — Watchlist with live prices + AI signal context
# ═══════════════════════════════════════════════════════════════════════

class WatchlistRequest(BaseModel):
    symbols: list[str]

@router.post("/api/portfolio/watchlist")
def portfolio_watchlist(req: WatchlistRequest) -> dict[str, Any]:
    """Live snapshot of a custom watchlist."""
    import yfinance as yf
    from pages.ai_trading_agent import _fetch_info
    rows: list[dict[str, Any]] = []
    for sym in req.symbols[:50]:
        try:
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            if h.empty: continue
            last = float(h["Close"].iloc[-1])
            prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else last
            chg  = (last/prev - 1) * 100 if prev > 1e-10 else 0
            info = _fetch_info(sym)
            rows.append({
                "symbol":   sym,
                "name":     info.get("name") or sym,
                "price":    _round(last, 2),
                "change_pct": _round(chg, 2),
                "sector":   info.get("sector", "—"),
                "market_cap": _safe(info.get("market_cap")),
                "pe_ratio": _round(info.get("pe_ratio"), 2),
                "div_yield": _round(info.get("dividend_yield"), 2),
                "currency": "SEK" if ".ST" in sym.upper() else "USD",
            })
        except Exception as e:
            logger.warning("watchlist %s: %s", sym, e)
    return {"status": "ok", "count": len(rows), "results": rows}


# ═══════════════════════════════════════════════════════════════════════
# MARKET — Macro regime, indices, breadth
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/market/overview")
def market_overview() -> dict[str, Any]:
    """Live snapshot of major US + global indices."""
    import yfinance as yf
    indices = {
        "^GSPC":  ("S&P 500",            "US"),
        "^IXIC":  ("NASDAQ Composite",   "US"),
        "^DJI":   ("Dow Jones",          "US"),
        "^RUT":   ("Russell 2000",       "US"),
        "^VIX":   ("VIX (volatility)",   "US"),
        "^OMX":   ("OMX Stockholm 30",   "SE"),
        "^FTSE":  ("FTSE 100",           "UK"),
        "^GDAXI": ("DAX",                "DE"),
        "^N225":  ("Nikkei 225",         "JP"),
    }
    rows: list[dict[str, Any]] = []
    for sym, (name, region) in indices.items():
        try:
            h = yf.Ticker(sym).history(period="5d")
            if h.empty: continue
            last = float(h["Close"].iloc[-1])
            prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else last
            chg  = (last/prev - 1) * 100 if prev > 1e-10 else 0
            rows.append({
                "symbol": sym, "name": name, "region": region,
                "price": _round(last, 2), "change_pct": _round(chg, 2),
            })
        except Exception as e:
            logger.warning("market overview %s: %s", sym, e)
    return {"status": "ok", "indices": rows}


@router.get("/api/market/regime")
def market_regime() -> dict[str, Any]:
    """Macro regime quadrant + raw proxy values."""
    from pages.ai_trading_agent import _fetch_macro_proxies, classify_macro_regime
    macro = _fetch_macro_proxies()
    quad, score = classify_macro_regime(macro)
    def g(key, attr="current"):
        v = macro.get(key, {})
        return v.get(attr) if isinstance(v, dict) else None
    return {
        "status": "ok",
        "regime": {
            "quadrant":  quad,
            "score":     _safe(score),
            "label": {
                "Q1": "Goldilocks (growth↑, inflation↓)",
                "Q2": "Reflation (growth↑, inflation↑)",
                "Q3": "Stagflation (growth↓, inflation↑)",
                "Q4": "Deflation (growth↓, inflation↓)",
            }.get(quad, quad),
        },
        "proxies": [
            {"key": "spy",   "name": "S&P 500",        "value": _round(g("^GSPC"), 2),     "chg_1y_pct": _round(g("^GSPC", "chg_1y"), 2),     "chg_1m_pct": _round(g("^GSPC", "chg_1m"), 2)},
            {"key": "vix",   "name": "VIX",            "value": _round(g("^VIX"), 2),       "chg_1y_pct": _round(g("^VIX", "chg_1y"), 2),       "chg_1m_pct": _round(g("^VIX", "chg_1m"), 2)},
            {"key": "tnx",   "name": "10Y Yield",      "value": _round(g("^TNX"), 2),       "chg_1y_pct": _round(g("^TNX", "chg_1y"), 2),       "chg_1m_pct": _round(g("^TNX", "chg_1m"), 2)},
            {"key": "dxy",   "name": "Dollar Index",   "value": _round(g("DX-Y.NYB"), 2),   "chg_1y_pct": _round(g("DX-Y.NYB", "chg_1y"), 2),   "chg_1m_pct": _round(g("DX-Y.NYB", "chg_1m"), 2)},
            {"key": "gold",  "name": "Gold",           "value": _round(g("GLD"), 2),        "chg_1y_pct": _round(g("GLD", "chg_1y"), 2),        "chg_1m_pct": _round(g("GLD", "chg_1m"), 2)},
            {"key": "oil",   "name": "WTI Oil",        "value": _round(g("CL=F"), 2),       "chg_1y_pct": _round(g("CL=F", "chg_1y"), 2),       "chg_1m_pct": _round(g("CL=F", "chg_1m"), 2)},
            {"key": "tlt",   "name": "20Y Bonds (TLT)","value": _round(g("TLT"), 2),        "chg_1y_pct": _round(g("TLT", "chg_1y"), 2),        "chg_1m_pct": _round(g("TLT", "chg_1m"), 2)},
            {"key": "hyg",   "name": "HY Bonds (HYG)", "value": _round(g("HYG"), 2),        "chg_1y_pct": _round(g("HYG", "chg_1y"), 2),        "chg_1m_pct": _round(g("HYG", "chg_1m"), 2)},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
# SWEDEN — OMX universe + ISK/KF context
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/sweden/universe")
def sweden_universe() -> dict[str, Any]:
    """Live OMX Stockholm watchlist."""
    import yfinance as yf
    from pages.ai_trading_agent import _fetch_info
    rows: list[dict[str, Any]] = []
    for sym in UNIVERSE_OMX:
        try:
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            if h.empty: continue
            last = float(h["Close"].iloc[-1])
            prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else last
            chg  = (last/prev - 1) * 100 if prev > 1e-10 else 0
            info = _fetch_info(sym)
            rows.append({
                "symbol": sym, "name": info.get("name") or sym,
                "price_sek": _round(last, 2), "change_pct": _round(chg, 2),
                "sector":   info.get("sector", "—"),
                "div_yield": _round(info.get("dividend_yield"), 2),
                "pe_ratio": _round(info.get("pe_ratio"), 2),
                "isk_eligible": True, "kf_eligible": True,
            })
        except Exception as e:
            logger.warning("sweden %s: %s", sym, e)
    return {"status": "ok", "market": "OMX Stockholm", "currency": "SEK", "count": len(rows), "results": rows}


@router.get("/api/sweden/account-rules")
def sweden_account_rules() -> dict[str, Any]:
    """ISK vs. KF tax rules summary (current Swedish tax rules)."""
    return {
        "status": "ok",
        "isk": {
            "name":  "Investeringssparkonto (ISK)",
            "tax_method": "Schablonskatt — flat tax on capital base",
            "tax_rate_pct_2025": 0.882,  # 0.882% for 2025 per Skatteverket
            "advantages": [
                "No need to declare individual trades",
                "Foreign dividends taxed at source (Sweden has tax treaty with US: 15%)",
                "Capital gains automatically tax-free at the account level",
            ],
            "disadvantages": [
                "Tax owed even in a losing year",
                "Cannot hold shares with pending corporate actions easily",
            ],
            "best_for": "Long-term passive holders with diversified ETF/equity portfolios",
        },
        "kf": {
            "name":  "Kapitalförsäkring (KF)",
            "tax_method": "Same schablonskatt rate as ISK, but held by insurer",
            "tax_rate_pct_2025": 0.882,
            "advantages": [
                "Foreign dividends taxed via insurer — typically reclaimed automatically",
                "No K4 tax form ever",
                "Can name beneficiaries directly",
            ],
            "disadvantages": [
                "Slightly higher fees from insurer",
                "Less flexibility moving holdings between providers",
            ],
            "best_for": "Holders of US/foreign dividend stocks; estate planning",
        },
        "ranking_for_us_dividend_stocks": "KF > ISK (foreign withholding tax handling)",
        "ranking_for_swedish_growth": "ISK ≈ KF (both fine; ISK has fewer fees)",
    }

# ═══════════════════════════════════════════════════════════════════════
# SETUP SCANNER — "setup-of-the-day" (LLM Council greenlit, May 21 2026)
# Expanded May 21: equities + ETFs + funds + crypto, in Swedish vs
# International boxes. Parallel fetch + 30-min TTL cache for click-speed.
# Decision-support, NOT advice. Honest "no A/B-grade setup today" path.
# ═══════════════════════════════════════════════════════════════════════
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from .setup_scanner import score_setup as _score_setup

# Tagged universes: (symbol, region, asset_class).
# region ∈ {"Swedish","International"}; asset_class ∈ {equity,etf,fund,crypto}.
# Swedish ETF/crypto coverage on the free yfinance feed is thin — the NaN-guard
# in the engine drops bad series, and the box honestly reports when none qualify.
SETUP_UNIVERSE: list[tuple[str, str, str]] = (
    # ── Swedish equities ──
    [(s, "Swedish", "equity") for s in (
        "VOLV-B.ST","ERIC-B.ST","HM-B.ST","INVE-B.ST","ATCO-A.ST","SAND.ST",
        "SEB-A.ST","EVO.ST","ABB.ST","ASSA-B.ST","SWED-A.ST","SKF-B.ST")] +
    # ── Swedish ETFs (Nasdaq Stockholm; many NaN on free feed — engine filters) ──
    [(s, "Swedish", "etf") for s in (
        "XACT-OMXS30.ST","XACT-NORDEN.ST","XACT-BEAR.ST","XACT-BULL.ST")] +  # <- verified live May21
    # <- Swedish crypto ETPs (Nasdaq Stockholm, verified live May21): the "wall" was a ticker bug
    [(s, "Swedish", "crypto") for s in (
        "BITCOIN-XBT.ST","ETHEREUM-XBT.ST","BITCOIN-XBTE.ST")] +
    # <- NEW [Phase3-Step2]: Swedish open-end funds via EODHD Morningstar 0P….ST codes
    #    (verified eodhd.com/exchange/ST). yfinance has no Swedish fund NAV, so these
    #    resolve through the EODHD Tier-2 provider — DORMANT until EODHD_API_KEY is set
    #    (until then they miss honestly and the cell stays empty, exactly as today).
    [(s, "Swedish", "fund") for s in (
        "0P0000ULAP.ST","0P0000YVZ3.ST","0P00000L4S.ST","0P0000XAIN.ST","0P0000RYCW.ST")] +
    # ── International equities ──
    [(s, "International", "equity") for s in (
        "AAPL","MSFT","NVDA","GOOGL","META","AMZN","AVGO","JPM","V","COST","NFLX","AMD")] +
    # ── International ETFs ──
    [(s, "International", "etf") for s in (
        "SPY","QQQ","VTI","VOO","IWM","DIA","ARKK","XLF","XLK","EEM")] +
    # ── International funds (mutual funds; daily NAV) ──
    [(s, "International", "fund") for s in (
        "VFIAX","FXAIX","VTSAX","FCNTX","SWPPX")] +
    # ── International crypto (24/7) ──
    [(s, "International", "crypto") for s in (
        "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","DOGE-USD")] +
    # ── Gold (v3): Swedish-accessible + international. All are indirect
    #    instruments (ETC/certificate/futures) — honestly labelled via _PROXY_META. ──
    [(s, "Swedish", "gold") for s in ("GULD.ST",)] +           # Handelsbanken certificate (SEK)
    [(s, "Swedish", "gold") for s in ("4GLD.DE",)] +           # Xetra-Gold ETC (EUR, PRIIPs OK)
    [(s, "International", "gold") for s in ("GLD","IAU","GC=F")] +
    # ── Oil (v3): Swedish-accessible + international ──
    [(s, "Swedish", "oil") for s in ("OLJA.ST",)] +            # Handelsbanken certificate (SEK)
    [(s, "Swedish", "oil") for s in ("CRUD.L",)] +             # WisdomTree WTI ETC (PRIIPs OK)
    [(s, "International", "oil") for s in ("USO","BNO","CL=F","BZ=F")] +
    # ── Copper (v3.1): Swedish-accessible + international ──
    [(s, "Swedish", "copper") for s in ("KOPPAR.ST",)] +       # Handelsbanken certificate (SEK)
    [(s, "Swedish", "copper") for s in ("COPA.L",)] +          # WisdomTree Copper ETC (PRIIPs OK)
    [(s, "International", "copper") for s in ("CPER","HG=F")] +
    # ── Silver (v3.1): Swedish-accessible + international ──
    [(s, "Swedish", "silver") for s in ("SILVER.ST",)] +       # Handelsbanken certificate (SEK)
    [(s, "Swedish", "silver") for s in ("PHAG.L",)] +          # WisdomTree Physical Silver (PRIIPs OK)
    [(s, "International", "silver") for s in ("SLV","SI=F")]
)

# v3: honest proxy labelling for indirect commodity/crypto exposure.
# A proxy is NEVER mislabelled as the direct commodity; the UI shows the note.
_PROXY_META: dict[str, str] = {
    "GULD.ST":  "Swedish-listed gold certificate (SEK) — tracks spot gold, ISK/KF-eligible",
    "4GLD.DE":  "Xetra-Gold ETC (EUR) — physically-backed proxy, accessible to Swedish investors",
    "GLD":      "US-listed gold ETF proxy (not spot gold)",
    "IAU":      "US-listed gold ETF proxy (not spot gold)",
    "GC=F":     "COMEX gold futures front month — futures proxy for spot gold",
    "OLJA.ST":  "Swedish-listed oil certificate (SEK) — tracks Brent, ISK/KF-eligible",
    "CRUD.L":   "WisdomTree WTI Crude ETC (LSE) — futures-based proxy, accessible to Swedish investors",
    "USO":      "US-listed WTI futures ETF proxy (roll costs apply; not spot oil)",
    "BNO":      "US-listed Brent futures ETF proxy (roll costs apply; not spot oil)",
    "CL=F":     "NYMEX WTI futures front month — futures proxy for spot oil",
    "BZ=F":     "ICE Brent futures front month — futures proxy for spot oil",
    "KOPPAR.ST": "Swedish-listed copper certificate (SEK) — tracks LME copper, ISK/KF-eligible",
    "COPA.L":   "WisdomTree Copper ETC (LSE, USD) — futures-based proxy, accessible to Swedish investors",
    "CPER":     "US-listed copper futures ETF proxy (roll costs apply; not spot copper)",
    "HG=F":     "COMEX copper futures front month — futures proxy for spot copper",
    "SILVER.ST": "Swedish-listed silver certificate (SEK) — tracks spot silver, ISK/KF-eligible",
    "PHAG.L":   "WisdomTree Physical Silver ETC (LSE, USD) — physically-backed proxy, accessible to Swedish investors",
    "SLV":      "US-listed silver ETF proxy (not spot silver)",
    "SI=F":     "COMEX silver futures front month — futures proxy for spot silver",
}

# <- NEW [Phase3-Step2]: display names for EODHD 0P fund codes (yfinance can't name them).
_FUND_NAME_OVERRIDES: dict[str, str] = {
    "0P0000ULAP.ST": "Spiltan Aktiefond Investmentbolag",
    "0P0000YVZ3.ST": "Länsförsäkringar Global Index",
    "0P00000L4S.ST": "Nordea Nordic Small Cap A",
    "0P0000XAIN.ST": "Nordea Global Passiv Tillväxt",
    "0P0000RYCW.ST": "Storebrand Emerging Markets A",
}

# Crypto needs no dividend/sector lookup; equities/ETFs/funds do.
_NO_INFO_CLASSES = frozenset({"crypto"})

# In-process TTL cache (EOD data changes once/day — 30 min cache is plenty).
_SETUP_CACHE: dict[str, Any] = {"key": None, "at": 0.0, "data": None}
_SETUP_TTL_SEC = 1800.0


def _market_regime_map() -> dict[str, Optional[dict]]:
    """Scan-level market-regime gate: OMXS30 for the Swedish box, S&P 500 for
    the International box, each vs its 200-day MA. The most common and
    best-tested systematic filter - bullish setups in a risk-off tape are
    DOWNGRADED (conflict + A-grade cap), never hidden. Best effort per index."""
    out: dict[str, Optional[dict]] = {}
    try:
        import yfinance as yf
        for region, idx in (("Swedish", "^OMX"), ("International", "^GSPC")):
            try:
                h = yf.Ticker(idx).history(period="2y")
                c = [float(x) for x in h["Close"]]
                if len(c) < 200:
                    out[region] = None
                    continue
                ma200 = sum(c[-200:]) / 200
                out[region] = {"index": idx, "close": round(c[-1], 2),
                               "ma200": round(ma200, 2),
                               "risk_on": c[-1] > ma200}
            except Exception as exc:  # noqa: BLE001
                logger.warning("market regime %s: %s", idx, exc)
                out[region] = None
    except Exception:  # noqa: BLE001
        out = {"Swedish": None, "International": None}
    return out


def _news_context(sym: str, limit: int = 8) -> Optional[dict]:
    """Recency-aware news context for a SELECTED setup (finalists only - never
    per-candidate, to respect rate limits). yfinance provides no sentiment, so
    sentiment is honestly 'not scored'; recency and volume of coverage are real."""
    try:
        from datetime import datetime, timezone
        import yfinance as yf
        items = yf.Ticker(sym).news or []
        now = datetime.now(timezone.utc)
        recent = []
        for it in items[:limit]:
            content = it.get("content") or it
            ts = content.get("pubDate") or content.get("providerPublishTime")
            title = (content.get("title") or "").strip()
            summary = (content.get("summary") or content.get("description") or "").strip()
            age_days = None
            try:
                if isinstance(ts, (int, float)):
                    age_days = (now - datetime.fromtimestamp(ts, timezone.utc)).days
                elif isinstance(ts, str):
                    age_days = (now - datetime.fromisoformat(ts.replace("Z", "+00:00"))).days
            except (ValueError, TypeError, OSError):
                pass
            if title:
                recent.append({"title": title[:120], "summary": summary[:240],
                               "age_days": age_days})
        last7 = sum(1 for r in recent if r["age_days"] is not None and r["age_days"] <= 7)
        return {"headlines": recent[:4], "count_7d": last7,
                "latest_age_days": (recent[0]["age_days"] if recent else None),
                "sentiment": "not scored (no licensed sentiment feed)"}
    except Exception as exc:  # noqa: BLE001
        logger.debug("news context %s: %s", sym, exc)
        return None


import threading as _threading

# v3.3: sector relative strength via global SPDR sector proxies. Swedish
# equities use the SAME global proxy (documented) - no Swedish sector ETF
# family exists on the free feed; the GICS-style sector names from yfinance
# map cleanly. Cached per process, guarded for the scan's thread pool.
_SECTOR_PROXY: dict[str, str] = {
    "Technology": "XLK", "Financial Services": "XLF", "Financials": "XLF",
    "Healthcare": "XLV", "Health Care": "XLV", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Basic Materials": "XLB",
    "Utilities": "XLU", "Communication Services": "XLC", "Real Estate": "XLRE",
}
_SECTOR_CACHE: dict[str, Optional[list]] = {}
_SECTOR_LOCK = _threading.Lock()


def _sector_closes(etf: str) -> Optional[list]:
    with _SECTOR_LOCK:
        if etf in _SECTOR_CACHE:
            return _SECTOR_CACHE[etf]
    closes = None
    try:
        import yfinance as yf
        h = yf.Ticker(etf).history(period="1y")
        if len(h) >= 130:
            closes = [float(x) for x in h["Close"]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("sector proxy %s: %s", etf, exc)
    with _SECTOR_LOCK:
        _SECTOR_CACHE[etf] = closes
    return closes


def _sector_context_for(sector: Optional[str], closes: list) -> Optional[dict]:
    """Relative performance vs the sector proxy over ~1m/3m/6m."""
    etf = _SECTOR_PROXY.get(sector or "")
    if not etf or len(closes) < 130:
        return None
    sc = _sector_closes(etf)
    if not sc or len(sc) < 130:
        return None

    def _rel(n: int) -> Optional[float]:
        if len(closes) <= n or len(sc) <= n:
            return None
        a = closes[-1] / closes[-1 - n] - 1
        s = sc[-1] / sc[-1 - n] - 1
        return round(a - s, 4)

    return {"proxy": f"{etf} (global SPDR sector proxy)", "sector": sector,
            "rel_1m": _rel(21), "rel_3m": _rel(63), "rel_6m": _rel(126)}


# v3.3: FX context for Swedish-accessible non-SEK instruments (unhedged).
_FX_CACHE: dict[str, Optional[dict]] = {}
_FX_LOCK = _threading.Lock()


def _fx_context_for(sym: str, region: str) -> Optional[dict]:
    if region != "Swedish" or sym.upper().endswith(".ST"):
        return None
    cur = "EUR" if sym.upper().endswith(".DE") else "USD"
    pair = "EURSEK=X" if cur == "EUR" else "USDSEK=X"
    with _FX_LOCK:
        if pair in _FX_CACHE:
            cached = _FX_CACHE[pair]
            return dict(cached, instrument_currency=cur) if cached else None
    ctx = None
    try:
        import yfinance as yf
        h = yf.Ticker(pair).history(period="1y")
        c = [float(x) for x in h["Close"]]
        if len(c) >= 70:
            rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            ctx = {"pair": pair.replace("=X", ""), "rate": round(c[-1], 4),
                   "trend_3m_pct": round((c[-1] / c[-63] - 1) * 100, 2) if len(c) > 63 else None,
                   "vol_ann_pct": round((var ** 0.5) * (252 ** 0.5) * 100, 1),
                   "reporting_currency": "SEK",
                   "note": ("unhedged: SEK return = instrument return + "
                            "FX change (not forecast)")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fx context %s: %s", pair, exc)
    with _FX_LOCK:
        _FX_CACHE[pair] = ctx
    return dict(ctx, instrument_currency=cur) if ctx else None


def _real_quote(sym: str) -> Optional[dict]:
    """Best-effort real bid/ask for a SELECTED finalist (yfinance info)."""
    try:
        import yfinance as yf
        i = yf.Ticker(sym).info or {}
        bid, ask = i.get("bid"), i.get("ask")
        if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) \
                and bid > 0 and ask >= bid:
            return {"bid": float(bid), "ask": float(ask)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("real quote %s: %s", sym, exc)
    return None


def _intraday_refine_top(top: dict) -> None:
    """Refine a SELECTED setup's target date into an intraday datetime using
    real yfinance 60m bars (60-day depth, verified available incl. .ST).
    Finalists only - never per-candidate. Mutates top['intraday'] in place."""
    sym = top.get("symbol")
    try:
        from .setup_scanner import refine_target_time_intraday
        dist = float(top["target"]) - float(top["entry"])
        tz0 = "Europe/Stockholm" if str(sym).upper().endswith(".ST") else \
            "exchange local" if top.get("asset_class") != "crypto" else "UTC (24/7)"
        # v3.5: USER-IMPORTED intraday export (sub-60m capable) takes precedence
        # over the yfinance 60m fallback (see api/tools/import_intraday.py).
        try:
            from .tools.import_intraday import load_intraday_reference
            ref = load_intraday_reference(sym)
        except Exception:  # noqa: BLE001
            ref = None
        if ref is not None:
            ih, il, ic, per_day = ref
            res = refine_target_time_intraday(
                top.get("base_case_target_date", ""), dist, ih, il, ic, per_day, tz0)
            res["intraday_source"] = "user-imported intraday export (intraday_reference/)"
            top["intraday"] = res
            if res.get("intraday_available"):
                return
        import yfinance as yf
        h = yf.Ticker(sym).history(period="60d", interval="60m")
        if h is None or len(h) < 30:
            top["intraday"] = {"intraday_available": False, "intraday_source": "yfinance 60m",
                               "fallback_reason": f"only {0 if h is None else len(h)} intraday bars returned"}
            return
        bars_per_day = 24.0 if top.get("asset_class") == "crypto" else \
            8.5 if str(sym).upper().endswith(".ST") else 7.0
        tz = "Europe/Stockholm" if str(sym).upper().endswith(".ST") else \
            "exchange local" if top.get("asset_class") != "crypto" else "UTC (24/7)"
        res = refine_target_time_intraday(
            top.get("base_case_target_date", ""), 
            float(top["target"]) - float(top["entry"]),
            [float(x) for x in h["High"]], [float(x) for x in h["Low"]],
            [float(x) for x in h["Close"]], bars_per_day, tz)
        res["intraday_source"] = "yfinance 60m bars (60-day depth)"
        top["intraday"] = res
    except Exception as exc:  # noqa: BLE001
        logger.warning("intraday refine %s: %s", sym, exc)
        top["intraday"] = {"intraday_available": False,
                           "intraday_source": "yfinance 60m",
                           "fallback_reason": f"fetch/refine error: {exc}"}


def _fetch_event_context(sym: str, asset_class: str) -> Optional[dict]:
    """Next earnings + ex-dividend dates via yfinance calendar (best effort).

    Feeds the scanner's corporate-event gap-risk checks: an earnings report or
    a chunky ex-dividend inside the target window is a conflict a stop cannot
    protect against. Crypto/commodity futures have neither - skipped. Any
    fetch/shape failure degrades to None (the scan never blocks on this)."""
    if asset_class not in ("equity", "etf", "fund"):
        return None
    try:
        from datetime import date as _d, datetime as _dt
        import yfinance as yf

        def _norm(v) -> Optional[_d]:
            if isinstance(v, _dt):
                return v.date()
            if isinstance(v, _d):
                return v
            return None

        t = yf.Ticker(sym)
        try:
            cal = t.calendar or {}
        except Exception:  # noqa: BLE001 - some tickers have no calendar
            cal = {}
        if not isinstance(cal, dict):
            cal = {}
        today = _d.today()
        out: dict = {}

        eds = cal.get("Earnings Date") or []
        if not isinstance(eds, (list, tuple)):
            eds = [eds]
        future = [d for d in (_norm(e) for e in eds) if d is not None and d >= today]
        if future:
            out["next_earnings_date"] = min(future).isoformat()

        xd = _norm(cal.get("Ex-Dividend Date"))
        if xd is not None and xd >= today:
            out["next_ex_dividend_date"] = xd.isoformat()
            try:
                divs = t.dividends
                if divs is not None and len(divs):
                    out["dividend_amount"] = float(divs.iloc[-1])
            except Exception:  # noqa: BLE001 - amount is optional
                pass
        return out or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("event context skipped for %s: %s", sym, exc)
        return None


def _candidate_news(sym: str, asset_class: str, as_of: str) -> Optional[dict]:
    """News items for scanner-side lexicon sentiment (equities/ETFs only;
    yfinance source works for .ST symbols too, unlike FMP's thin Nordic feed)."""
    if asset_class not in ("equity", "etf"):
        return None
    items: list[dict] = []
    sources: list[str] = []
    # v3.5: manually imported Avanza/Placera items FIRST (only real Swedish
    # coverage available; FMP has no .ST news, Bigdata is paused).
    try:
        from .tools.import_avanza_placera_news import load_avanza_news
        av = load_avanza_news(sym)
        if av:
            items.extend(av)
            sources.append("Avanza/Placera manual-copy")
    except Exception:  # noqa: BLE001 - optional source
        pass
    # v3.4: FMP when the plan allows (verified plan-gated 402/403 on 2026-07-11;
    # degrades to None), then yfinance fallback.
    try:
        from .fmp_news import fetch_fmp_news
        fmp = fetch_fmp_news(sym)
        if fmp is not None:
            items.extend(fmp["items"])
            sources.append("FMP stock_news")
    except Exception:  # noqa: BLE001 - adapter is optional
        pass
    if not items:
        nc = _news_context(sym)
        if nc and nc.get("headlines"):
            items.extend(nc["headlines"])
            sources.append("yfinance news")
    if not items:
        return None
    # dedup across sources on normalized title
    seen: set = set()
    unique = []
    for it in items:
        k = (it.get("title") or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            unique.append(it)
    return {"items": unique,
            "source": " + ".join(sources) + " (lexicon sentiment, model-derived)",
            "as_of": as_of}


def _fetch_and_score(entry: tuple[str, str, str],
                     calibration: Optional[dict] = None,
                     regime_map: Optional[dict] = None) -> Optional[dict]:
    """Fetch 1y daily history for one (symbol, region, asset_class) and score it."""
    import asyncio
    from .data_ingestion import service as _ingest, DataMissingException  # <- NEW [Phase3-Step1]: ingestion backbone
    sym, region, asset_class = entry
    try:
        # <- NEW [Phase3-Step1]: fetch via DataIngestionService — alias resolution
        #     (e.g. BITCOIN-ZERO.ST -> BITCOIN-XBT.ST), provider cascade
        #     (yfinance -> scraper -> Riksbank), NaN + staleness guards, provenance.
        try:
            # v3: 1100 days (~3y) so monthly RSI (needs ~15 monthly bars) is computable.
            series = asyncio.run(_ingest.get_series(sym, asset_class, lookback_days=1100))
        except DataMissingException:
            return None
        if len(series.points) < 60:
            return None
        closes = series.closes
        highs  = [p.high for p in series.points]
        lows   = [p.low for p in series.points]

        # v3 (Investor AB fix): consult the deep harmonic engine for every
        # candidate so conflicting patterns PENALISE the ranking, not just
        # decorate the symbol page. Cheap: ZigZag + ratio checks, no extra I/O.
        from .setup_scanner import build_technical_context as _build_ctx, _atr as _atr_fn
        _atr_v = _atr_fn(highs, lows, closes)
        tech_ctx = _build_ctx(highs, lows, closes, _atr_v, symbol=sym) if _atr_v else None

        name = sym
        div_yield = None
        sector = None
        fundamentals = None
        if asset_class not in _NO_INFO_CLASSES:
            try:
                from pages.ai_trading_agent import _fetch_info
                info = _fetch_info(sym)
                name = info.get("name", sym)
                div_yield = info.get("dividend_yield")
                sector = info.get("sector")
                # v3.2: fundamentals sub-score (small, supports-only weight)
                fund = {k: info.get(k) for k in
                        ("pe_trailing", "pe_forward", "roe",
                         "revenue_growth", "earnings_growth")}
                if any(v is not None for v in fund.values()):
                    fundamentals = fund
            except Exception:
                pass

        name = _FUND_NAME_OVERRIDES.get(sym, name)  # <- NEW [Phase3-Step2]: friendly fund name
        r = _score_setup(
            sym, region, closes, highs, lows,
            name=name, dividend_yield=div_yield, sector=sector,
            asset_class=asset_class,
            as_of=series.as_of.date(),           # v3: timing dates anchored to data date
            technical_context=tech_ctx,          # v3: harmonic conflicts enter the score
            proxy_note=_PROXY_META.get(sym),     # v3: honest proxy labelling
            calibration=calibration,             # v3: ledger-based timing calibration
            event_context=_fetch_event_context(sym, asset_class),  # earnings/ex-div gap risk
            volumes=series.volumes,              # v3.2: real volume ingestion
            market_regime=(regime_map or {}).get(region),   # v3.2: index regime gate
            fundamentals=fundamentals,           # v3.2: fundamentals sub-score
            # v3.3: news sentiment (lexicon), sector RS, FX context
            news_context=_candidate_news(sym, asset_class, series.as_of.date().isoformat()),
            sector_context=_sector_context_for(sector, closes),
            fx_context=_fx_context_for(sym, region),
        )
        if r is not None:
            # <- NEW [Phase3-Step1]: stamp provenance (council mandate: source + as_of on every series)
            r["source"] = series.source
            r["as_of"] = series.as_of.date().isoformat()
            # v3.2: FX exposure flag for Swedish-accessible non-SEK proxies
            if region == "Swedish" and not sym.upper().endswith(".ST"):
                r["fx_note"] = ("Priced in a foreign currency — SEK investors "
                                "carry FX exposure on top of the instrument's move.")
            resolved = series.meta.get("resolved", sym)
            if resolved != sym:
                r["resolved_symbol"] = resolved
        return r
    except Exception as e:
        logger.warning("setup-scan %s: %s", sym, e)
        return None


def _structured_error(code: str, exc: Exception, source: str, rid: str):
    """Local-dev reliability contract: routes must NEVER surface as a bare
    'Failed to fetch' — they return this JSON error envelope instead."""
    from datetime import datetime as _dt, timezone as _tz
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={
        "ok": False,
        "error": {
            "code": code,
            "message": str(exc)[:300],
            "details": type(exc).__name__,
            "retryable": True,
            "source": source,
            "timestamp": _dt.now(_tz.utc).isoformat(timespec="seconds"),
            "request_id": rid,
        },
    })


@router.get("/api/discover/setup-of-the-day")
def setup_of_the_day(refresh: bool = False):
    """Reliability wrapper: structured JSON errors + stale-cache fallback.
    A live-scan failure serves the last good scan (flagged stale) before it
    ever serves an error - the Setup of the Day section must never go blank."""
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:12]
    try:
        return _setup_of_the_day_impl(refresh)
    except Exception as exc:  # noqa: BLE001 - contract: never crash unstructured
        logger.exception("setup-of-the-day failed [request_id=%s]", rid)
        if _SETUP_CACHE.get("data") is not None:
            stale = dict(_SETUP_CACHE["data"])
            stale["cached"] = True
            stale["stale"] = True
            stale["stale_reason"] = (f"live scan failed ({type(exc).__name__}); "
                                     "serving last successful scan")
            stale["request_id"] = rid
            return stale
        return _structured_error("SETUP_SCAN_FAILED", exc, "setup_scanner", rid)


def _setup_of_the_day_impl(refresh: bool = False) -> dict[str, Any]:
    """
    The Setup Scanner — best-qualifying setup per (region × asset class).

    Returns two boxes — Swedish and International — each broken into
    equity / etf / fund / crypto, with the top-scored setup per class
    (A/B/C grade), or an honest "no setup" note when none qualify.

    Query params:
        refresh : bypass the 30-min cache (default False)

    Decision-support, not advice. Every level computed from live OHLCV;
    target is an ATR time WINDOW, never a hard date. v1 = "as of last close".
    """
    cache_key = "setup_v3.2"
    now = _time.time()
    if (not refresh and _SETUP_CACHE["data"] is not None
            and _SETUP_CACHE["key"] == cache_key
            and (now - _SETUP_CACHE["at"]) < _SETUP_TTL_SEC):
        cached = dict(_SETUP_CACHE["data"])
        cached["cached"] = True
        cached["cache_age_sec"] = int(now - _SETUP_CACHE["at"])
        return cached

    # v3: ledger-based timing calibration, computed once per scan (pure file read).
    try:
        from .setup_ledger import timing_calibration as _timing_calib
        calibration = _timing_calib()
    except Exception:  # noqa: BLE001 - calibration is an enhancement, never a blocker
        logger.warning("timing calibration unavailable", exc_info=True)
        calibration = None

    # v3.2: scan-level market-regime gate (OMXS30 / S&P 500 vs 200-day MA).
    regime_map = _market_regime_map()

    # Parallel fetch+score across the whole tagged universe.
    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_fetch_and_score, e, calibration, regime_map): e
                for e in SETUP_UNIVERSE}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                scored.append(r)

    # Group into boxes[region][asset_class] → best by (direct-before-proxy, score).
    classes = ("equity", "etf", "fund", "crypto",
               "gold", "oil", "copper", "silver")   # v3: + gold/oil; v3.1: + copper/silver
    boxes: dict[str, Any] = {}
    for region in ("Swedish", "International"):
        boxes[region] = {}
        for ac in classes:
            members = [s for s in scored if s.get("region") == region and s.get("asset_class") == ac]
            # Direct Swedish-listed instruments beat proxies at selection time;
            # within each tier, highest score wins; symbol breaks exact ties so
            # selection is deterministic run-to-run (audit: reproducibility).
            members.sort(key=lambda r: (bool(r.get("proxy")), -r.get("score", 0),
                                        r.get("symbol", "")))
            top = members[0] if members else None
            has_quality = bool(top and top.get("grade") in ("A", "B"))
            if not members:
                msg = f"No {ac} data on the free feed for {region} today (v2: real-time Nordic feed)."
            elif has_quality:
                msg = f"{top['symbol']} — {top.get('classification', 'grade ' + top['grade'])}"
            else:
                msg = (f"No A/B-grade {region} {ac} today — best available is "
                       f"{top.get('classification', 'grade ' + top['grade'])} "
                       f"({top['symbol']}). Shown honestly, not hidden.")
            # v3: retain a ranking log for every candidate (debuggability mandate).
            candidates = [{
                "rank": i + 1,
                "symbol": m["symbol"],
                "score": m.get("score"),
                "grade": m.get("grade"),
                "classification": m.get("classification"),
                "proxy": bool(m.get("proxy")),
                "reason_not_selected": None if i == 0 else (
                    f"outranked by {members[0]['symbol']} "
                    f"({members[0].get('score')} vs {m.get('score')}"
                    + ("; proxy ranked after direct instrument" if m.get("proxy") and not members[0].get("proxy") else "")
                    + ")"),
                "biggest_strength": m.get("strongest_supporting"),
                "biggest_weakness": m.get("strongest_opposing"),
            } for i, m in enumerate(members)]
            # v3.3: finalist refinement (SELECTED setup only - rate-limit safe):
            # intraday target-time, real bid/ask spread, FX-adjusted display.
            if top is not None:
                _intraday_refine_top(top)
                q = _real_quote(top["symbol"])
                if q is not None:
                    from .setup_scanner import _spread_model as _sm
                    real = _sm(top.get("last_price", 0.0), top.get("atr_14", 0.0),
                               top.get("liquidity_turnover_20d"),
                               top.get("asset_class", "equity"),
                               bool(top.get("proxy")), bid=q["bid"], ask=q["ask"])
                    if real is not None:
                        top["spread"] = real   # real quote refines the proxy estimate
                fxc = top.get("fx")
                if fxc and fxc.get("rate") and top.get("target"):
                    fxc["fx_adjusted_target_sek"] = round(top["target"] * fxc["rate"], 2)
                    fxc["fx_adjusted_invalidation_sek"] = round(
                        (top.get("invalidation") or 0) * fxc["rate"], 2)
            boxes[region][ac] = {
                "top_setup":   top,
                "has_quality": has_quality,
                "message":     msg,
                "scanned":     len(members),
                "candidates":  candidates,
            }

    # <- NEW [Phase3-Step3]: log surfaced top setups to the trust ledger.
    #    Single-threaded post-assembly (avoids concurrent-write races);
    #    idempotent per date:symbol:grade; never breaks the scan.
    try:
        from .setup_ledger import log_setup as _log_setup
        for _region in boxes:
            for _ac in boxes[_region]:
                _top = boxes[_region][_ac].get("top_setup")
                if _top:
                    _log_setup(_top)
    except Exception:  # noqa: BLE001
        logger.warning("ledger logging skipped", exc_info=True)

    result = {
        "status":      "ok",
        "as_of":       "latest close (crypto: 24/7)",
        "cached":      False,
        "market_regime": regime_map,   # v3.2: scan-level index regime
        "boxes":       boxes,
        "total_scored": len(scored),
    }
    _SETUP_CACHE.update(key=cache_key, at=now, data=result)
    return result


@router.get("/api/discover/ledger")
async def discover_ledger(evaluate: bool = False):  # <- NEW [Phase3-Step3]: trust ledger
    """Honest hit-rate track record for surfaced setups: win-rate by grade with
    sample size + methodology + disclaimer. Pass ?evaluate=true to resolve
    newly-matured PENDING entries against subsequent price action first.
    Reliability wrapper: structured JSON errors, isolated from setup-of-the-day."""
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:12]
    try:
        from .setup_ledger import (aggregate as _aggregate,
                                   evaluate_open_entries as _evaluate,
                                   timing_calibration as _timing_calib)
        if evaluate:
            from .data_ingestion import service as _ingest
            try:
                await _evaluate(_ingest)
            except Exception:  # noqa: BLE001 - never let evaluation break the read
                logger.warning("ledger evaluation failed", exc_info=True)
        result = _aggregate()
        try:
            result["timing_calibration"] = _timing_calib()  # v3: time-to-target calibration
        except Exception:  # noqa: BLE001
            logger.warning("timing calibration failed", exc_info=True)
        return result
    except Exception as exc:  # noqa: BLE001 - contract: never crash unstructured
        logger.exception("discover/ledger failed [request_id=%s]", rid)
        return _structured_error("LEDGER_READ_FAILED", exc, "setup_ledger", rid)


@router.get("/api/ai/providers")
async def ai_providers_status() -> dict:  # <- NEW [provider-layer]: live LLM provider status
    """Status of the multi-provider LLM layer: which providers are keyed/ready,
    the fallback order, and the current default (no secrets exposed)."""
    try:
        import ai_providers
        return ai_providers.provider_status()
    except Exception as exc:  # noqa: BLE001 - never break on a status read
        logger.warning("ai providers status failed: %s", exc)
        return {"available": [], "count": 0, "error": str(exc)}
