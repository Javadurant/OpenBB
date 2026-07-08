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
    [(s, "International", "oil") for s in ("USO","BNO","CL=F","BZ=F")]
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


def _fetch_and_score(entry: tuple[str, str, str],
                     calibration: Optional[dict] = None) -> Optional[dict]:
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
        if asset_class not in _NO_INFO_CLASSES:
            try:
                from pages.ai_trading_agent import _fetch_info
                info = _fetch_info(sym)
                name = info.get("name", sym)
                div_yield = info.get("dividend_yield")
                sector = info.get("sector")
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
        )
        if r is not None:
            # <- NEW [Phase3-Step1]: stamp provenance (council mandate: source + as_of on every series)
            r["source"] = series.source
            r["as_of"] = series.as_of.date().isoformat()
            resolved = series.meta.get("resolved", sym)
            if resolved != sym:
                r["resolved_symbol"] = resolved
        return r
    except Exception as e:
        logger.warning("setup-scan %s: %s", sym, e)
        return None


@router.get("/api/discover/setup-of-the-day")
def setup_of_the_day(refresh: bool = False) -> dict[str, Any]:
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
    cache_key = "setup_v3"
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

    # Parallel fetch+score across the whole tagged universe.
    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_fetch_and_score, e, calibration): e for e in SETUP_UNIVERSE}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                scored.append(r)

    # Group into boxes[region][asset_class] → best by (direct-before-proxy, score).
    classes = ("equity", "etf", "fund", "crypto", "gold", "oil")   # v3: + gold/oil
    boxes: dict[str, Any] = {}
    for region in ("Swedish", "International"):
        boxes[region] = {}
        for ac in classes:
            members = [s for s in scored if s.get("region") == region and s.get("asset_class") == ac]
            # Direct Swedish-listed instruments beat proxies at selection time;
            # within each tier, highest score wins.
            members.sort(key=lambda r: (bool(r.get("proxy")), -r.get("score", 0)))
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
        "boxes":       boxes,
        "total_scored": len(scored),
    }
    _SETUP_CACHE.update(key=cache_key, at=now, data=result)
    return result


@router.get("/api/discover/ledger")
async def discover_ledger(evaluate: bool = False) -> dict[str, Any]:  # <- NEW [Phase3-Step3]: trust ledger
    """Honest hit-rate track record for surfaced setups: win-rate by grade with
    sample size + methodology + disclaimer. Pass ?evaluate=true to resolve
    newly-matured PENDING entries against subsequent price action first."""
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
