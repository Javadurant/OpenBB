"""
api/phase2_router.py
Phase 2 endpoints — Discover (screeners), Portfolio (watchlist), Market (regime), Sweden (OMX).
All call REAL engine functions, no stubs.
"""
from __future__ import annotations

import hmac
import logging
import os as _os
import sys
import threading
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
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

# ── Universe coverage provenance (honest labelling) ─────────────────────
# SENTRIQ product rule: Setup of the Day must NEVER imply it scanned the
# whole market when it did not. SETUP_UNIVERSE above is a CURATED WATCHLIST,
# not a provider-discovered exchange/market universe. We label that truthfully
# with the project coverage taxonomy so the API (and UI) can state exactly how
# a winner was selected — "best of this curated list", never "best in market".
#   full_provider_market | full_exchange_market | broad_index_universe |
#   broad_provider_universe | curated_fallback | small_watchlist_fallback |
#   data_limited | provider_blocked | key_missing | plan_gated
UNIVERSE_SOURCE = "curated_watchlist"

def _coverage_label_for(discovered: int) -> str:
    """Honest coverage label from how many symbols a bucket draws from.
    These lists are hand-curated, so the ceiling is 'curated', never
    'full_*_market' — that claim requires provider-list verification."""
    if discovered == 0:
        return "data_limited"
    if discovered <= 15:
        return "small_watchlist_fallback"
    return "curated_fallback"

def _universe_counts() -> dict[str, dict[str, int]]:
    """Count SETUP_UNIVERSE symbols per (region, asset_class) — the honest
    'discovered' denominator, derived from the live universe so it can never
    drift out of sync with what is actually scanned."""
    counts: dict[str, dict[str, int]] = {}
    for _sym, _region, _ac in SETUP_UNIVERSE:
        counts.setdefault(_region, {}).setdefault(_ac, 0)
        counts[_region][_ac] += 1
    return counts

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
        import math
        import yfinance as yf
        for region, idx in (("Swedish", "^OMX"), ("International", "^GSPC")):
            try:
                h = yf.Ticker(idx).history(period="2y")
                # v3.9.3: drop NaN/inf Close bars before the MA. yfinance routinely
                # returns a NaN for the latest/partial index bar; left unfiltered it
                # makes sum()/c[-1] NaN, and `nan > nan` silently yields
                # risk_on=False - flipping a genuinely risk-on tape (e.g. ^GSPC
                # 7408 > MA200 7002) to risk-off and penalising every bullish setup.
                # Filter first so a transient trailing null bar is simply ignored.
                c = [v for v in (float(x) for x in h["Close"]) if math.isfinite(v)]
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


def _candidate_news(sym: str, asset_class: str, as_of: str,
                    name: Optional[str] = None) -> Optional[dict]:
    """News items for scanner-side sentiment (equities/ETFs only;
    yfinance source works for .ST symbols too, unlike FMP's thin Nordic feed).
    v3.7: tvremix wire news (.ST coverage incl. Dow Jones) + Bigdata.com
    licensed chunk sentiment join the chain; `name` improves Bigdata matching."""
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
    # v3.7: TradingView wire news via tvremix (live-verified 2026-07-22:
    # same-day Dow Jones Newswires for OMXSTO:VOLV_B). Deterministic .ST
    # mapping only; unmappable symbols degrade to None honestly.
    try:
        from .tvremix_client import fetch_tvremix_news
        tvn = fetch_tvremix_news(sym)
        if tvn is not None:
            items.extend(tvn["items"])
            sources.append(tvn["source"])
    except Exception:  # noqa: BLE001 - adapter is optional
        pass
    # v3.6: Polygon news with LICENSED per-ticker sentiment (live-verified
    # 2026-07-12; US coverage - .ST degrades to None honestly).
    try:
        from .polygon_news import fetch_polygon_news
        poly = fetch_polygon_news(sym)
        if poly is not None:
            items.extend(poly["items"])
            sources.append(poly["source"])
    except Exception:  # noqa: BLE001 - adapter is optional
        pass
    # v3.7: Bigdata.com search with LICENSED chunk sentiment (live-verified
    # 2026-07-22: premium MT Newswires + numeric sentiment; subscription
    # re-activated). Capability-gated so a paused subscription costs zero
    # per-candidate HTTP calls; company NAME queries match best.
    try:
        from .bigdata_client import bigdata_capabilities, fetch_bigdata_news
        if bigdata_capabilities().get("bigdata_working"):
            bq = name if (name and name != sym) else sym.split(".")[0].replace("-", " ")
            bd = fetch_bigdata_news(bq)
            if bd is not None:
                items.extend(bd["items"])
                sources.append(bd["source"])
    except Exception:  # noqa: BLE001 - adapter is optional
        pass
    # v3.4: FMP when the plan allows (2026-07-12 re-probe: HTTP 401 - the .env
    # value is a PLACEHOLDER; degrades to None), then yfinance fallback.
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
    # v3.7 honesty fix: only claim "lexicon/model-derived" when NO item carries
    # a licensed per-item sentiment label (Polygon insights / Bigdata chunks).
    # When licensed items are present the aggregate is genuinely mixed — say so,
    # so the source string matches the method news_sentiment() actually reports.
    has_licensed = any(it.get("sentiment") for it in unique)
    suffix = (" (mixed licensed + lexicon sentiment)" if has_licensed
              else " (lexicon sentiment, model-derived)")
    return {"items": unique,
            "source": " + ".join(sources) + suffix,
            "as_of": as_of}


def _fetch_and_score(entry: tuple[str, str, str],
                     calibration: Optional[dict] = None,
                     regime_map: Optional[dict] = None,
                     news_enabled: bool = True) -> Optional[dict]:
    """Fetch 1y daily history for one (symbol, region, asset_class) and score it.

    news_enabled=False skips the per-candidate news chain (tvremix/Polygon/
    Bigdata/yfinance) — used by the broad market scan where scoring hundreds of
    symbols must not hammer the rate-limited news APIs. The news sub-score is
    supports-only and optional (excluded from the denominator when absent), so
    the grade reflects technical structure; news is fetched for finalists."""
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
            news_context=(_candidate_news(sym, asset_class,
                                          series.as_of.date().isoformat(),
                                          name=name)  # v3.7: name → Bigdata matching
                          if news_enabled else None),  # v3.8: skip in broad scan
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


def _error_envelope(code: str, message: str, source: str, rid: str, *,
                    status_code: int, retryable: bool, details: str):
    """THE project error shape. One construction site so no route can drift
    into a second, incompatible envelope."""
    from datetime import datetime as _dt, timezone as _tz
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={
        "ok": False,
        "error": {
            "code": code,
            "message": message[:300],
            "details": details,
            "retryable": retryable,
            "source": source,
            "timestamp": _dt.now(_tz.utc).isoformat(timespec="seconds"),
            "request_id": rid,
        },
    })


def _structured_error(code: str, exc: Exception, source: str, rid: str):
    """Local-dev reliability contract: routes must NEVER surface as a bare
    'Failed to fetch' — they return this JSON error envelope instead."""
    # Behaviour-identical delegation: same 503, same retryable=True, same fields.
    return _error_envelope(code, str(exc), source, rid, status_code=503,
                           retryable=True, details=type(exc).__name__)


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


# ── Authorised trust-ledger logging — the ONLY API write path ────────────────
# Scans are read-only. Persisting one is a deliberate MANUAL operator action:
# no scheduler, no frontend, no recovery script (governance decision 2026-08-06).
#
# LOOPBACK-ONLY, UNCONDITIONALLY. No remote escape hatch. Forwarding headers
# (X-Forwarded-For / X-Real-IP) are NEVER consulted — they are attacker-
# controlled. Only the real TCP peer (request.client.host) is trusted.
# ⚠ A reverse proxy in front makes the peer the PROXY, silently widening this
#   gate to the whole internet. Deploying behind a proxy INVALIDATES this
#   control and REQUIRES a new security review before it is enabled.
#
# ACCOUNTABILITY LIMIT: the credential is a SHARED SECRET. It authenticates
# "someone who holds the token", NOT an individual operator. There is no
# per-user identity, no signature, and no non-repudiation. Available audit
# fields are: request_id, peer (always loopback), written, not_written.
#
# TOKEN IN A HEADER, NEVER A QUERY PARAM: uvicorn's access log records the PATH
# (verified live: '"GET /api/health HTTP/1.1" 200 OK') but not headers, so a
# query token would be written to /tmp/sentriq_api.log and any proxy log.
_LEDGER_LOG_TOKEN_ENV = "SENTRIQ_LEDGER_LOG_TOKEN"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})

# Rate limit: stdlib only (no limiter dependency is installed). Counts EVERY
# attempt BEFORE credential validation, so invalid attempts are throttled too.
# STATE IS PER-PROCESS AND IN-MEMORY: it resets on restart and is not shared
# across workers. A brute-force speed bump, NOT a security boundary.
_LEDGER_LOG_RATE_MAX = 6
_LEDGER_LOG_RATE_WINDOW_SEC = 60.0
_LEDGER_LOG_HITS: list[float] = []
_LEDGER_LOG_LOCK = threading.Lock()


def _ledger_log_rate_ok() -> bool:
    now = _time.monotonic()
    with _LEDGER_LOG_LOCK:
        _LEDGER_LOG_HITS[:] = [t for t in _LEDGER_LOG_HITS
                               if now - t < _LEDGER_LOG_RATE_WINDOW_SEC]
        if len(_LEDGER_LOG_HITS) >= _LEDGER_LOG_RATE_MAX:
            return False
        _LEDGER_LOG_HITS.append(now)
        return True


def _env_file_mode_check() -> Optional[str]:
    """Policy gate: enabling logging requires .env at mode 600.

    Returns None when OK, else a refusal reason. FAIL-CLOSED: any OSError
    (permission denied, unreadable parent, race with deletion) refuses.
    NEVER returns or logs a filesystem path or an exception message — only the
    exception CLASS NAME, server-side. The caller maps the reason to a generic
    response so nothing about the filesystem reaches the client."""
    try:
        st = _os.stat(Path(__file__).resolve().parent.parent / ".env")
    except FileNotFoundError:
        return None                     # no .env; token came from the process env
    except OSError as exc:
        logger.warning("ledger logging: credential-file check failed (%s)",
                       type(exc).__name__)          # class name only
        return "env_check_failed"                   # FAIL CLOSED
    if st.st_mode & 0o077:
        return "insecure_env_permissions"
    return None


def _ledger_logging_authorised(token: Optional[str], peer: Optional[str]
                               ) -> tuple[bool, str]:
    """(authorised, reason). Never logs, echoes, or returns the token.
    peer=None (request.client absent) is treated as NOT loopback — fail closed."""
    if peer not in _LOOPBACK_HOSTS:
        return False, "remote_denied"
    expected = _os.getenv(_LEDGER_LOG_TOKEN_ENV, "").strip()
    if not expected:
        return False, "not_configured"
    env_reason = _env_file_mode_check()
    if env_reason:
        return False, env_reason
    if not token or not hmac.compare_digest(token, expected):
        return False, "forbidden"
    return True, "authorised"


# (status, client-facing message, retryable). Messages carry NO filesystem
# paths, NO exception text, and NO hint about which internal check failed.
_LEDGER_LOG_ERRORS = {
    "rate_limited":             (429, "too many logging attempts; retry later", True),
    "remote_denied":            (403, "ledger logging is loopback-only", False),
    "not_configured":           (503, "ledger logging is not configured on this server", False),
    "insecure_env_permissions": (503, "ledger logging is disabled by server policy", False),
    "env_check_failed":         (503, "ledger logging is disabled by server policy", False),
    "forbidden":                (403, "missing or invalid ledger-logging credential", False),
}


@router.post("/api/discover/setup-of-the-day/log")
def setup_of_the_day_log(
    request: Request,
    x_sentriq_ledger_token: Optional[str] = Header(default=None),
):
    """Persist the CURRENT scan's top setups to the LIVE trust ledger.

    Deliberate, authorised, manual. Idempotent per date:symbol:grade -
    setup_ledger.log_setup() re-checks the key under its write lock, so a
    repeated call on the same day writes nothing. Reuses the warm cache so it
    never forces a second full scan."""
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:12]

    # Rate limit FIRST: every attempt counts, valid or not.
    if not _ledger_log_rate_ok():
        status, msg, retry = _LEDGER_LOG_ERRORS["rate_limited"]
        return _error_envelope("LEDGER_LOGGING_RATE_LIMITED", msg, "setup_ledger",
                               rid, status_code=status, retryable=retry,
                               details="rate_limited")
    peer = getattr(getattr(request, "client", None), "host", None)
    ok, reason = _ledger_logging_authorised(x_sentriq_ledger_token, peer)
    if not ok:
        status, msg, retry = _LEDGER_LOG_ERRORS[reason]
        logger.warning("ledger logging refused [reason=%s peer=%s request_id=%s]",
                       reason, peer, rid)          # never the token
        return _error_envelope("LEDGER_LOGGING_" + reason.upper(), msg,
                               "setup_ledger", rid, status_code=status,
                               retryable=retry, details=reason)

    scan = _setup_of_the_day_impl(refresh=False)   # warm cache when available
    if scan.get("status") != "ok":
        return _error_envelope("SCAN_UNAVAILABLE", "no usable scan to log",
                               "setup_scanner", rid, status_code=502,
                               retryable=True, details="scan_status_not_ok")

    from .setup_ledger import log_setup as _log_setup
    written = not_written = candidates = 0
    for _region, _classes in (scan.get("boxes") or {}).items():
        for _ac, _box in _classes.items():
            _top = _box.get("top_setup")
            if not _top:
                continue
            candidates += 1
            if _log_setup(_top):          # path=None -> live ledger, deliberately
                written += 1
            else:
                not_written += 1
    logger.info("ledger logging [request_id=%s peer=%s candidates=%d written=%d "
                "not_written=%d]", rid, peer, candidates, written, not_written)
    return {
        "status": "ok",
        "request_id": rid,
        "ledger_logging": {
            "logged": written > 0,
            "candidates": candidates,
            "written": written,
            # CONSERVATIVE: log_setup() returns False for duplicate key, invalid
            # fields, OR a caught OSError/ValueError/TypeError. It cannot
            # distinguish them without changing its return contract, so this
            # MUST NOT be reported as a duplicate count.
            "not_written": not_written,
            "not_written_note": "duplicate, invalid, or write error - not distinguishable",
            "idempotency_key": "date:symbol:grade",
            "scan_cached": bool(scan.get("cached")),
            "identity_note": "shared credential; not attributable to an individual",
        },
    }


_CONFLICTED_TTL_SEC = 1800.0  # match the setup-of-the-day 30-min cadence


@router.get("/api/discover/conflicted-scan")
def conflicted_scan(refresh: bool = False, limit: int = 50):
    """Conflicted Buy Setup market scanner (v3.7): market-wide discovery via
    the TradingView screener (sweden/america/crypto) with Bigdata licensed
    sentiment overlay. Conviction = TV Recommend.All linearly mapped to
    0-100 (user decision 2026-07-22). Unfiltered universe, honestly labelled.
    Internal signal generation only — see redistribution_note (TRUTH 3)."""
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:12]
    try:
        # Shared _CACHE from omnisearch_router — single cache layer, no forks.
        from .omnisearch_router import _cache_get, _cache_set
        from .tvremix_scanner import conflicted_buy_scan
        limit = max(1, min(int(limit), 200))
        cache_key = f"conflicted_scan:v3.7:{limit}"
        if not refresh:
            cached = _cache_get(cache_key, ttl=_CONFLICTED_TTL_SEC)
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                return out
        result = conflicted_buy_scan(limit=limit)
        result["cached"] = False
        _cache_set(cache_key, result)
        return result
    except Exception as exc:  # noqa: BLE001 - contract: never crash unstructured
        logger.exception("conflicted-scan failed [request_id=%s]", rid)
        return _structured_error("CONFLICTED_SCAN_FAILED", exc, "tvremix_scanner", rid)


_BROAD_TTL_SEC = 3600.0  # broad scan is expensive — cache 1h


@router.get("/api/discover/broad-scan")
def broad_scan_endpoint(region: str = "Swedish", depth: int = 200, refresh: bool = False):
    """Broad market scan (v3.8) — grades the top-`depth` most-liquid names of the
    FULL discovered exchange universe (946 ST / 18k US), not the ~12-name curated
    watchlist. Liquidity comes from ONE tvremix screener call (no per-symbol
    probe); grades A/B/C come from SENTRIQ's own setup_scanner. Surfaces real
    Grade A (HIGHEST CONVICTION) / Grade B (SOLID ALIGNMENT). Cached 1h."""
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:12]
    try:
        from .omnisearch_router import _cache_get, _cache_set
        from .broad_scan import broad_scan as _bscan
        region = "Swedish" if str(region).lower().startswith("swed") else "International"
        depth = max(10, min(int(depth), 250))
        cache_key = f"broad_scan:v1:{region}:{depth}"
        if not refresh:
            cached = _cache_get(cache_key, ttl=_BROAD_TTL_SEC)
            if cached is not None:
                return {**cached, "cached": True}
        # Reuse the SOTD scan-level context: regime gate + ledger timing calibration.
        regime_map = _market_regime_map()
        calibration = None
        try:
            from .setup_ledger import timing_calibration as _timing_calib
            calibration = _timing_calib()
        except Exception:  # noqa: BLE001 - calibration is an enhancement, never a blocker
            logger.warning("broad-scan timing calibration unavailable", exc_info=True)
        result = _bscan(region, score_fn=_fetch_and_score, regime_map=regime_map,
                        calibration=calibration, depth=depth)
        result["cached"] = False
        _cache_set(cache_key, result)
        return result
    except Exception as exc:  # noqa: BLE001 - contract: never crash unstructured
        logger.exception("broad-scan failed [request_id=%s]", rid)
        return _structured_error("BROAD_SCAN_FAILED", exc, "broad_scan", rid)


def _json_safe(obj):
    """Recursively replace non-JSON-compliant floats (nan / +-inf) with None.
    json.dumps rejects them, so ONE bad computed value (e.g. a 0/0 ratio on some
    thinly-traded symbol now that EODHD opened the full 18k/945 universe) would
    500 the WHOLE endpoint. Applied to scanner payloads before caching/return so
    a single degenerate float can never take the section down again."""
    if isinstance(obj, float):
        # nan != nan; inf/-inf are outside JSON's range
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


_GRADE_RANK_SOTD = {"A": 0, "B": 1, "C": 2}


def _member_sort_key(r: dict):
    """Setup-of-the-Day per-box selection order (v3.8):
      1. direct instruments before proxies,
      2. GRADE (A > B > C) — a cleaner Grade-B 'solid alignment' (≤1 conflict)
         is preferred over a higher-SCORE but more-conflicted Grade-C, because
         the grade encodes conflict count (the INVE-B safety fix),
      3. higher score within a grade,
      4. symbol, so selection is deterministic run-to-run (audit reproducibility).
    """
    return (bool(r.get("proxy")), _GRADE_RANK_SOTD.get(r.get("grade"), 9),
            -(r.get("score") or 0.0), r.get("symbol", ""))


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
    cache_key = "setup_v3.9"  # v3.9: bullish-structure scoring (harmonic/Elliott raise conviction)
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

    # v3.8: EQUITY boxes now rank the BROAD liquid universe (not the ~12-name
    # watchlist) — the fix for "best of 12" vs "best in market". ONE bulk tvremix
    # screener call per region supplies liquidity (NO 946-symbol probe); the
    # discovered exchange universe is turnover-ranked and the top tranche is
    # graded by the SAME setup_scanner. Equity is scored news-DISABLED for
    # breadth speed (news is small/supports-only and re-attached to the winner
    # in the finalist block); non-equity keeps the curated news path. Degrades to
    # curated-only if the broad universe is unavailable — never blocks the scan.
    _SOTD_BROAD_DEPTH = 200  # per region; the real Grade-A/B often live in the liquid tail
    scan_entries: list[tuple[str, str, str]] = list(SETUP_UNIVERSE)
    equity_universe_meta: dict[str, dict] = {}
    try:
        from .broad_scan import broad_equity_entries as _broad_eq
        _seen_eq = {(s, r) for (s, r, a) in scan_entries if a == "equity"}
        for _reg in ("Swedish", "International"):
            _ents, _meta = _broad_eq(_reg, depth=_SOTD_BROAD_DEPTH)
            equity_universe_meta[_reg] = _meta
            for _e in _ents:
                if (_e[0], _e[1]) not in _seen_eq:
                    scan_entries.append(_e)
                    _seen_eq.add((_e[0], _e[1]))
    except Exception:  # noqa: BLE001 - broad universe is an enhancement, never a blocker
        logger.warning("SOTD broad equity universe unavailable; equity = curated only",
                       exc_info=True)

    # Parallel fetch+score. Equity → news DISABLED (breadth); other classes → news on.
    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_fetch_and_score, e, calibration, regime_map,
                            e[2] != "equity"): e
                for e in scan_entries}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                scored.append(r)

    # Group into boxes[region][asset_class] → best by (direct-before-proxy, score).
    classes = ("equity", "etf", "fund", "crypto",
               "gold", "oil", "copper", "silver")   # v3: + gold/oil; v3.1: + copper/silver
    universe_counts = _universe_counts()   # honest 'discovered' denominator per bucket
    boxes: dict[str, Any] = {}
    for region in ("Swedish", "International"):
        boxes[region] = {}
        for ac in classes:
            members = [s for s in scored if s.get("region") == region and s.get("asset_class") == ac]
            members.sort(key=_member_sort_key)  # v3.8: grade-first (see helper docstring)
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
            } for i, m in enumerate(members[:15])]  # v3.8: cap display list (equity pool is now broad)
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
                # v3.7: TradingView 1D rating for the SELECTED setup only.
                # INFORMATIONAL ONLY (user decision 2026-07-22): never enters
                # the score, grade, conflicts count or classification. Raw TV
                # quote fields are deliberately NOT surfaced (TRUTH 3 gate).
                try:
                    from .tvremix_client import get_technicals_rating, to_tv_symbol
                    _tvs = to_tv_symbol(top["symbol"])
                    _tvr = get_technicals_rating(_tvs) if _tvs else None
                    _summ = (_tvr or {}).get("summary") or {}
                    if _summ.get("recommendation"):
                        _rec = str(_summ["recommendation"])
                        top["tv_rating"] = {
                            "recommendation": _rec,
                            "value": _summ.get("value"),
                            "interval": "1D",
                            "source": "TradingView via tvremix",
                            "in_score": False,
                            "note": ("informational only — not part of the setup "
                                     "score (user decision 2026-07-22)"),
                        }
                        if _rec in ("Buy", "Strong Buy"):
                            top.setdefault("supports", []).append(
                                f"TradingView 1D rating: {_rec} (informational, not scored)")
                        elif _rec in ("Sell", "Strong Sell"):
                            top.setdefault("uncertainty_flags", []).append(
                                f"TradingView 1D rating {_rec} disagrees "
                                "(informational, not scored)")
                except Exception:  # noqa: BLE001 - enrichment never breaks the scan
                    pass
                # v3.8: equity winners are graded news-DISABLED (breadth). Attach
                # news to the SELECTED equity setup for DISPLAY only — score/max
                # are None so it is never folded into the scored denominator; the
                # grade already stands. Keeps the news-provenance chip working.
                if top.get("asset_class") == "equity" and not top.get("news"):
                    try:
                        _nc = _candidate_news(top["symbol"], "equity",
                                              top.get("as_of") or "", name=top.get("name"))
                        if _nc and _nc.get("items"):
                            from .setup_scanner import news_sentiment as _news_senti
                            top["news"] = {
                                "score": None, "max": None,
                                "sentiment": _news_senti(_nc["items"]),
                                "source": _nc["source"], "as_of": _nc["as_of"],
                                "top_items": _nc["items"][:4],
                            }
                    except Exception:  # noqa: BLE001 - display enrichment never breaks the scan
                        pass
            _discovered = universe_counts.get(region, {}).get(ac, 0)
            _usrc = UNIVERSE_SOURCE          # honest: curated watchlist, not full market
            _cov = _coverage_label_for(_discovered)
            # v3.8: equity boxes now rank the broad liquid universe — label them so,
            # never as "curated". Non-equity boxes keep the curated labelling.
            if ac == "equity" and region in equity_universe_meta:
                _m = equity_universe_meta[region]
                _discovered = _m.get("discovered") or _discovered
                _usrc = "broad_liquid_universe"
                _cov = (f"top {_m.get('shortlisted', 0)} most-liquid of "
                        f"{_m.get('discovered', 0)} discovered {_m.get('exchange', '')} "
                        f"equities · liquidity via TradingView screener, grade via "
                        f"setup_scanner ({_m.get('discovery_label', '')})")
            boxes[region][ac] = {
                "top_setup":   top,
                "has_quality": has_quality,
                "message":     msg,
                "scanned":     len(members),          # symbols that returned usable data
                "discovered":  _discovered,           # equity: broad universe; else curated bucket
                "excluded":    max(_discovered - len(members), 0),  # dropped: no/insufficient/stale data
                "universe_source": _usrc,
                "coverage_label":  _cov,
                "candidates":  candidates,
            }

    # EMERGENCY CONTAINMENT (2026-08-06): the implicit trust-ledger write that
    # lived here is DELETED. A GET must never mutate financial records, and this
    # one did so unauthenticated from any browser tab — observed appending 5 rows
    # at 03:34 UTC and 10 rows at 16:43 local the same day. The write also
    # completed BEFORE uvicorn emitted its access-log line, so the access log
    # could not detect it. An authorised replacement path is prepared but NOT
    # applied; it awaits human policy approval (token owner, rotation,
    # revocation, cadence, rate limit).

    # v3.6: cross-reference each equity box against the FULL provider exchange
    # list (EODHD), so the UI can state "N of M" honestly — a curated subset of
    # a full_exchange_market universe, never "the whole market". Cached daily;
    # any discovery failure degrades to a labelled note and never breaks the scan.
    try:
        from .universe_registry import discover_exchange as _disc, EXCHANGE_META as _EXM
        for _region, _exch in (("Swedish", "ST"), ("International", "US")):
            _u = _disc(_exch)
            _eq = boxes.get(_region, {}).get("equity")
            if _eq is None:
                continue
            _disc_n = _u.get("discovered")
            _eq_disc = sum(1 for s in _u.get("symbols", []) if s.get("asset_class") == "equity")
            _eq["exchange_universe"] = {
                "exchange": _exch,
                "exchange_name": _EXM.get(_exch, {}).get("name"),
                "provider": _u.get("source_provider"),
                "discovery_coverage_label": _u.get("coverage_label"),
                "exchange_equities": _eq_disc or None,
                "scanned_of_exchange": (
                    f"{_eq.get('scanned')} of {_eq_disc} {_EXM.get(_exch, {}).get('name')} "
                    "equities scanned (v3.8: top liquid tranche of the full exchange, "
                    "grade-ranked by setup_scanner)"
                    if _eq_disc else None),
            }
    except Exception:  # noqa: BLE001 - cross-reference is an enhancement, never a blocker
        logger.warning("exchange cross-reference skipped", exc_info=True)

    # v3.9.2: Structure Watch — aggregate EVERY scanned setup carrying a bearish
    # harmonic (completed/near-miss) or a COMPLETED Elliott buy, so the UI renders a
    # dedicated, scannable sub-section for manual buy-signal validation. Read-only;
    # separate from the scored boxes (weight stays 8, no scoring change).
    # v3.9.3: recency contract. The authoritative age gate lives in
    # setup_scanner._structure_flags (MAX_STRUCTURE_AGE_BARS), which nulls a stale
    # harmonic PRZ / Elliott completion at source. This is a defensive SECONDARY
    # filter so a month-old pattern (the Mycronic AB case, Point D ~22 bars back)
    # can never reach the payload even if a flag is ever produced without the source
    # gate. Fail-open on a missing age so a plumbing gap never empties the section.
    from .setup_scanner import MAX_STRUCTURE_AGE_BARS as _MAX_SW_AGE

    def _fresh(flag: Optional[dict]) -> bool:
        if not flag:
            return True
        a = flag.get("age_bars")
        return a is None or a <= _MAX_SW_AGE

    _structure_watch: list[dict] = []
    for r in scored:
        sf = r.get("structure_flags") or {}
        bh = sf.get("bearish_harmonic")
        eb = sf.get("elliott_buy")
        eb = eb if (eb and eb.get("completed")) else None
        bh = bh if _fresh(bh) else None
        eb = eb if _fresh(eb) else None
        if bh or eb:
            _structure_watch.append({
                "symbol": r.get("symbol"), "name": r.get("name"),
                "region": r.get("region"), "asset_class": r.get("asset_class"),
                "grade": r.get("grade"), "score": r.get("score"),
                "classification": r.get("classification"),
                "last_price": r.get("last_price"),
                "bearish_harmonic": bh, "elliott_buy": eb,
            })
    # bearish-harmonic (buy-validity risk) first, then completed Elliott buys; by score.
    _structure_watch.sort(key=lambda w: (0 if w["bearish_harmonic"] else 1,
                                         -(w.get("score") or 0.0), w.get("symbol") or ""))
    _structure_watch = _structure_watch[:80]   # bound payload

    result = {
        "status":      "ok",
        "as_of":       "latest close (crypto: 24/7)",
        "cached":      False,
        "market_regime": regime_map,   # v3.2: scan-level index regime
        "boxes":       boxes,
        "structure_watch": _structure_watch,   # v3.9.2: scannable bearish-harmonic + Elliott-buy flags
        "structure_watch_counts": {
            "bearish_harmonic": sum(1 for w in _structure_watch if w["bearish_harmonic"]),
            "elliott_buy": sum(1 for w in _structure_watch if w["elliott_buy"]),
        },
        "structure_watch_max_age_bars": _MAX_SW_AGE,   # v3.9.3: recency window (trading bars)
        "total_scored": len(scored),
        # ── Honest universe coverage (v3.8: equity is now broad) ──
        "universe_source": "broad_liquid_equity + curated_multi_asset",
        "universe_total":  len(scan_entries),        # instruments actually in this scan pool
        "coverage_note": (
            "v3.8: Setup of the Day EQUITY boxes rank the BROAD liquid universe "
            "(top-N most-liquid of the full discovered exchange, graded by the "
            "SAME setup_scanner) — the equity winner is the best liquid equity in "
            "the market, not best-of-12. Selection is grade-first (a Grade-B "
            "'solid alignment' beats a higher-score but more-conflicted Grade-C). "
            "ETF / fund / crypto / commodity boxes remain a curated watchlist "
            "until their provider discovery is wired."
        ),
    }
    # v3.8 robustness: a total data-provider outage (e.g. yfinance throttled by a
    # heavy broad scan) can score ~nothing. NEVER overwrite a good cached scan
    # with an empty one, and never blank the section — keep serving the last good
    # scan, flagged stale, so a transient provider blip is invisible to the user.
    if len(scored) == 0 and _SETUP_CACHE.get("data") is not None:
        stale = dict(_SETUP_CACHE["data"])
        stale["cached"] = True
        stale["stale"] = True
        stale["stale_reason"] = ("live scan scored 0 (data provider "
                                 "throttled/unavailable) — serving last good scan")
        return stale
    result = _json_safe(result)   # v3.9.1: nan/inf → None so a bad float can't 500 the endpoint
    _SETUP_CACHE.update(key=cache_key, at=now, data=result)
    return result


@router.get("/api/discover/universe-coverage")
def universe_coverage(refresh: bool = False):
    """Honest provider-universe discovery report.

    Proves SENTRIQ actively discovers the BROAD provider-covered market and
    labels coverage truthfully. For each wired exchange it shows how many
    instruments EODHD lists (full_exchange_market) by asset class, versus the
    curated watchlist the scanner currently ranks. Rate-safe: EODHD lists are
    cached daily (pass ?refresh=true to force). No secrets are exposed.
    """
    try:
        from .universe_registry import discover_exchange, EXCHANGE_META
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"registry unavailable: {type(exc).__name__}"}
    curated = _universe_counts()
    region_of = {"ST": "Swedish", "US": "International"}
    exchanges: dict[str, Any] = {}
    for exch in ("ST", "US"):
        u = discover_exchange(exch, force=refresh)
        by_class: dict[str, int] = {}
        for s in u.get("symbols", []):
            by_class[s["asset_class"]] = by_class.get(s["asset_class"], 0) + 1
        region = region_of[exch]
        exchanges[exch] = {
            "exchange_name": EXCHANGE_META.get(exch, {}).get("name"),
            "region": region,
            "source_provider": u.get("source_provider"),
            "coverage_label": u.get("coverage_label"),
            "discovered": u.get("discovered"),
            "by_asset_class": by_class,
            "curated_scanned": curated.get(region, {}),
            "cached": u.get("cached"),
            "error": u.get("error"),
        }
    return {
        "status": "ok",
        "note": ("full_exchange_market discovery is live via EODHD; the scanner "
                 "still ranks a curated subset. Broad-scan uses a liquidity "
                 "shortlist (EODHD bulk EOD is plan-gated HTTP 423, so shortlist "
                 "liquidity is probed per-symbol at scan time)."),
        "curated_universe_total": len(SETUP_UNIVERSE),
        "exchanges": exchanges,
    }


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
