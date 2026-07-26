"""
api/omnisearch_router.py
Omnisearch — multi-asset, multi-venue search & discovery.

Asset classes: equity, etf, fund, index, crypto, fx, commodity, bond
Venues:        Nasdaq Stockholm Main, First North, Spotlight, NYSE, NASDAQ,
               LSE, Xetra, Euronext, plus crypto exchanges and synthetic
               futures.

Symbology: ISIN where yfinance provides it. FIGI is reserved as a
provider_required field — slot exists for OpenFIGI integration.

NO INVENTED DATA. Every field returns null when the source has no value.
"""
from __future__ import annotations

import logging
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))
logger = logging.getLogger("omnisearch")
router = APIRouter(prefix="/api/omni", tags=["omnisearch"])

# ─────────────────────────────────────────────────────────────────────────
# In-memory LRU cache (60s TTL) — protects against rate limits without
# lying about staleness.
# ─────────────────────────────────────────────────────────────────────────
_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = 60.0           # seconds — default for live data (search, quotes, news)
_TTL_SYMBOLOGY = 86400.0  # 24h — FIGIs/ISINs are stable identifiers

def _cache_get(key: str, ttl: float = _TTL) -> Any:
    item = _CACHE.get(key)
    if not item: return None
    ts, value = item
    if time.time() - ts > ttl:
        _CACHE.pop(key, None); return None
    return value

def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)

def _safe(v: Any, default: Any = None) -> Any:
    if v is None: return default
    try:
        import math
        if hasattr(v, "item"): v = v.item()
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return default
        return v
    except Exception: return default

def _round(v: Any, n: int = 2, default: Any = None) -> Any:
    x = _safe(v, default)
    if isinstance(x, (int, float)):
        try: return round(x, n)
        except Exception: return default
    return default

# ═════════════════════════════════════════════════════════════════════════
# ASSET CLASSIFIER — turn a yfinance quote/ticker into our taxonomy
# ═════════════════════════════════════════════════════════════════════════
ASSET_CLASSES = {
    "equity":    "Stocks",
    "etf":       "ETFs",
    "fund":      "Mutual Funds",
    "index":     "Indices",
    "crypto":    "Cryptocurrencies",
    "fx":        "Forex",
    "commodity": "Commodities",
    "bond":      "Fixed Income",
    "future":    "Futures",
    "option":    "Options",
}

def classify_asset(symbol: str, yf_type: str = "", yf_quote: dict[str, Any] | None = None) -> str:
    """Classify a symbol into one of our asset classes. Pure function."""
    s = (symbol or "").upper()
    t = (yf_type or "").upper()
    q = yf_quote or {}
    qt = (q.get("quoteType") or "").upper()
    typ = qt or t  # prefer quoteType when present
    # ── direct from yfinance type ──
    if typ == "ETF":         return "etf"
    if typ == "MUTUALFUND":  return "fund"
    if typ == "INDEX":       return "index"
    if typ == "CRYPTOCURRENCY": return "crypto"
    if typ == "CURRENCY":    return "fx"
    if typ == "FUTURE":      return "future"
    if typ == "OPTION":      return "option"
    if typ == "EQUITY":      return "equity"
    # ── pattern-based fallback ──
    if s.endswith("=X"):                   return "fx"
    if s.endswith("=F"):                   return "commodity"
    if s.endswith("-USD") or s.endswith("-EUR") or s.endswith("-BTC"): return "crypto"
    if s.startswith("^"):                  return "index"
    return "equity"  # default

# ═════════════════════════════════════════════════════════════════════════
# VENUE RESOLVER — yfinance suffix → human-readable trading venue
# ═════════════════════════════════════════════════════════════════════════
VENUE_BY_SUFFIX = {
    "ST":    {"venue": "Nasdaq Stockholm",  "country": "SE", "currency": "SEK", "tier": "main"},
    "STO":   {"venue": "Nasdaq Stockholm",  "country": "SE", "currency": "SEK", "tier": "main"},
    "L":     {"venue": "London Stock Exchange", "country": "GB", "currency": "GBP", "tier": "main"},
    "DE":    {"venue": "Xetra",            "country": "DE", "currency": "EUR", "tier": "main"},
    "F":     {"venue": "Frankfurt",         "country": "DE", "currency": "EUR", "tier": "main"},
    "PA":    {"venue": "Euronext Paris",   "country": "FR", "currency": "EUR", "tier": "main"},
    "AS":    {"venue": "Euronext Amsterdam","country": "NL", "currency": "EUR", "tier": "main"},
    "BR":    {"venue": "Euronext Brussels", "country": "BE", "currency": "EUR", "tier": "main"},
    "MI":    {"venue": "Borsa Italiana",   "country": "IT", "currency": "EUR", "tier": "main"},
    "MC":    {"venue": "BME Madrid",       "country": "ES", "currency": "EUR", "tier": "main"},
    "OL":    {"venue": "Oslo Børs",        "country": "NO", "currency": "NOK", "tier": "main"},
    "CO":    {"venue": "Nasdaq Copenhagen", "country": "DK", "currency": "DKK", "tier": "main"},
    "HE":    {"venue": "Nasdaq Helsinki",  "country": "FI", "currency": "EUR", "tier": "main"},
    "SW":    {"venue": "SIX Swiss",        "country": "CH", "currency": "CHF", "tier": "main"},
    "TO":    {"venue": "Toronto Stock Exchange", "country": "CA", "currency": "CAD", "tier": "main"},
    "T":     {"venue": "Tokyo Stock Exchange",   "country": "JP", "currency": "JPY", "tier": "main"},
    "HK":    {"venue": "Hong Kong Exchange",     "country": "HK", "currency": "HKD", "tier": "main"},
    "AX":    {"venue": "ASX (Australia)",        "country": "AU", "currency": "AUD", "tier": "main"},
    "NS":    {"venue": "NSE India",              "country": "IN", "currency": "INR", "tier": "main"},
    "SS":    {"venue": "Shanghai Stock Exchange","country": "CN", "currency": "CNY", "tier": "main"},
    "SZ":    {"venue": "Shenzhen Stock Exchange","country": "CN", "currency": "CNY", "tier": "main"},
}

# Swedish growth markets — yfinance suffix is .ST for all of Main, First
# North, and Other. The actual segment + ISIN come from the Nasdaq Nordic
# screener via api/providers/nasdaq_nordic.py (cached on disk for 7 days).
# Tickers not found in that index keep segment_verified=False.

def resolve_venue(symbol: str, asset_class: str, yf_quote: dict[str, Any] | None = None) -> dict[str, Any]:
    """Determine the regulatory venue + currency for a given symbol."""
    s = (symbol or "").upper()
    q = yf_quote or {}

    # Asset-class-specific venues
    if asset_class == "crypto":
        return {"venue": "Crypto Spot", "country": "GLOBAL", "currency": "USD", "tier": "crypto"}
    if asset_class == "fx":
        return {"venue": "FX Spot", "country": "GLOBAL", "currency": "USD", "tier": "fx"}
    if asset_class == "commodity":
        return {"venue": "CME/ICE Futures", "country": "US/GLOBAL", "currency": "USD", "tier": "commodity"}
    if asset_class == "bond":
        # Bond pseudo-tickers: US10Y, DE10Y, FR10Y, etc.
        if s.startswith("US"):
            return {"venue": "US Treasury (FRED)", "country": "US", "currency": "USD", "tier": "sovereign"}
        prefix = s[:2] if len(s) >= 2 else ""
        if prefix in _EUROZONE_CODES:
            return {"venue": f"{prefix} Sovereign (ECB)", "country": prefix, "currency": "EUR", "tier": "sovereign"}
        return {"venue": "Sovereign Bond", "country": "GLOBAL", "currency": "USD", "tier": "sovereign"}
    if asset_class == "index":
        # ^GSPC, ^OMX — venue-bound indices
        if s.startswith("^OMX"):  return {"venue": "Nasdaq Stockholm", "country": "SE", "currency": "SEK", "tier": "index"}
        if s.startswith("^FTSE"): return {"venue": "London Stock Exchange", "country": "GB", "currency": "GBP", "tier": "index"}
        if s.startswith("^GDAX"): return {"venue": "Xetra", "country": "DE", "currency": "EUR", "tier": "index"}
        if s.startswith("^N225"): return {"venue": "Tokyo Stock Exchange", "country": "JP", "currency": "JPY", "tier": "index"}
        return {"venue": "US Indices", "country": "US", "currency": "USD", "tier": "index"}

    # Exchange suffix lookup for stocks/etf/fund/bond
    if "." in s:
        suffix = s.split(".")[-1]
        if suffix in VENUE_BY_SUFFIX:
            v = dict(VENUE_BY_SUFFIX[suffix])
            # Swedish growth-market refinement via Nasdaq Nordic screener.
            if v["country"] == "SE" and asset_class == "equity":
                seg = "unknown"
                try:
                    from .providers.nasdaq_nordic import lookup_segment
                    seg, _ = lookup_segment(s)
                except Exception as e:
                    logger.warning("Nasdaq Nordic segment lookup failed for %s: %s", s, e)
                if seg == "first_north":
                    v["venue"] = "Nasdaq First North Growth Market"
                    v["tier"] = "first_north"
                    v["segment_verified"] = True
                elif seg == "main":
                    v["venue"] = "Nasdaq Stockholm Main"
                    v["tier"] = "main"
                    v["segment_verified"] = True
                elif seg == "other":
                    v["venue"] = "Nasdaq Stockholm (Other)"
                    v["tier"] = "other"
                    v["segment_verified"] = True
                else:
                    v["segment_verified"] = False  # honest about uncertainty
            return v

    # No suffix → most likely US
    exchange = (q.get("exchange") or "").upper()
    if exchange in ("NYSE", "NYQ"):  return {"venue": "NYSE",   "country": "US", "currency": "USD", "tier": "main"}
    if exchange in ("NMS", "NGM"):   return {"venue": "NASDAQ", "country": "US", "currency": "USD", "tier": "main"}
    if exchange == "ASE":            return {"venue": "NYSE American", "country": "US", "currency": "USD", "tier": "main"}
    if exchange == "PCX":            return {"venue": "NYSE Arca", "country": "US", "currency": "USD", "tier": "main"}
    return {"venue": "US Exchange", "country": "US", "currency": "USD", "tier": "main"}

# ═════════════════════════════════════════════════════════════════════════
# SHARE-CLASS DETECTOR — Swedish A/B/C class detection
# ═════════════════════════════════════════════════════════════════════════
SHARE_CLASS_RE = re.compile(r"-(?P<cls>[A-Z])(?:\.|$)")
def detect_share_class(symbol: str) -> str | None:
    """Return 'A', 'B', 'C', etc. for Swedish/Nordic share classes; else None."""
    m = SHARE_CLASS_RE.search(symbol.upper())
    if not m: return None
    cls = m.group("cls")
    # Heuristic: only valid for Nordic patterns (.ST, .OL, .CO, .HE)
    if not any(symbol.upper().endswith(suf) for suf in (".ST", ".OL", ".CO", ".HE")):
        return None
    return cls

# ═════════════════════════════════════════════════════════════════════════
# FUZZY RANKER — Levenshtein on name, token-prefix on ticker
# ═════════════════════════════════════════════════════════════════════════
def _levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein distance. Pure function. O(n*m)."""
    if a == b: return 0
    if not a:  return len(b)
    if not b:  return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(curr[j-1] + 1, prev[j] + 1, prev[j-1] + (0 if ca == cb else 1))
        prev = curr
    return prev[-1]

def rank_score(query: str, ticker: str, name: str, exchange: str = "") -> int:
    """Integer score 0-1000. Higher = better match. Pure function."""
    q   = (query   or "").upper().strip()
    tkr = (ticker  or "").upper()
    nm  = (name    or "").upper()
    if not q: return 0
    score = 0
    # Exact ticker match: huge boost
    if tkr == q:                    score += 1000
    elif tkr.startswith(q):         score += 600
    elif q in tkr:                  score += 300
    # Name token matching
    if nm.startswith(q):            score += 400
    elif q in nm:                   score += 200
    # Levenshtein on ticker (smaller distance = higher boost)
    if len(q) <= 8 and len(tkr) <= 12:
        d = _levenshtein(q, tkr)
        if d <= 2:   score += 80 - 30 * d
    # Penalize long names on short queries (ranks "Apple Inc" above "Apple Hospitality REIT")
    if len(q) <= 4 and len(nm) > 25: score -= 30
    return max(0, score)

# ═════════════════════════════════════════════════════════════════════════
# FAST PATH — recognized index / asset class typed by exact symbol
# ═════════════════════════════════════════════════════════════════════════
WELL_KNOWN_INDEX = {
    "^GSPC": "S&P 500",         "^IXIC": "NASDAQ Composite",
    "^DJI":  "Dow Jones",       "^RUT":  "Russell 2000",
    "^VIX":  "VIX",             "^OMX":  "OMX Stockholm 30",
    "^FTSE": "FTSE 100",        "^GDAXI": "DAX",
    "^N225": "Nikkei 225",      "^HSI":  "Hang Seng",
    "^STOXX50E": "Euro Stoxx 50",
}

# Common forex pairs
WELL_KNOWN_FX = {
    "EURUSD=X": "EUR/USD",     "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",     "USDSEK=X": "USD/SEK",
    "EURSEK=X": "EUR/SEK",     "AUDUSD=X": "AUD/USD",
    "USDCHF=X": "USD/CHF",     "USDCAD=X": "USD/CAD",
    "GBPJPY=X": "GBP/JPY",     "EURJPY=X": "EUR/JPY",
}

# Common commodities
WELL_KNOWN_COMMODITY = {
    "GC=F": "Gold Futures",     "SI=F": "Silver Futures",
    "CL=F": "WTI Crude Oil",    "BZ=F": "Brent Crude Oil",
    "NG=F": "Natural Gas",      "HG=F": "Copper",
    "ZC=F": "Corn",             "ZS=F": "Soybean",
    "ZW=F": "Wheat",            "PL=F": "Platinum",
}

# Common crypto. Display name = canonical short name shown in the UI.
# NOTE: Polygon migrated MATIC -> POL (Sept 2024); MATIC-USD is delisted on
# Yahoo, so the live spot ticker is POL-USD. Do not re-add MATIC-USD.
WELL_KNOWN_CRYPTO = {
    "BTC-USD": "Bitcoin",       "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",        "BNB-USD": "BNB",
    "XRP-USD": "XRP",           "ADA-USD": "Cardano",
    "DOGE-USD": "Dogecoin",     "AVAX-USD": "Avalanche",
    "DOT-USD": "Polkadot",      "POL-USD": "Polygon",
    "TRX-USD": "TRON",          "LINK-USD": "Chainlink",
    "TON-USD": "Toncoin",       "LTC-USD": "Litecoin",
    "BCH-USD": "Bitcoin Cash",  "SHIB-USD": "Shiba Inu",
}

# Search aliases: ticker -> alternative names/symbols a user might type.
# Used ONLY for matching (Layer B), never for display. Generalizable to any
# catalog; today only crypto needs it (users type "Binance Coin", "Ripple",
# "MATIC", etc.). Keep values UPPERCASE-insensitive — matching normalizes.
SEARCH_ALIASES: dict[str, list[str]] = {
    "BNB-USD":  ["Binance Coin", "Binance"],
    "XRP-USD":  ["Ripple"],
    "POL-USD":  ["MATIC", "Polygon Ecosystem Token"],
    "DOGE-USD": ["Doge"],
    "BCH-USD":  ["BCH"],
    "SHIB-USD": ["Shib"],
    "TON-USD":  ["Ton", "Open Network"],
}

# Words too generic to anchor a substring expansion on. Without this,
# "the" would match "The Open Network", "coin" every "...Coin", etc.
_ALIAS_STOPWORDS = {"THE", "AND", "FOR", "USD", "EUR", "INC", "ETF",
                    "COIN", "TOKEN", "OF", "TO", "A", "AN"}

def _norm_text(s: str) -> str:
    """Uppercase, replace any non-alphanumeric run with a single space, strip.
    Makes 'Binance Coin (BNB)' and 'binance-coin' comparable. Pure function."""
    return re.sub(r"[^A-Z0-9]+", " ", (s or "").upper()).strip()

def _alias_match(query: str, sym: str, name: str) -> str | None:
    """Return the best-matching searchable term (for ranking) if `query`
    matches `sym`, `name`, or any registered alias; else None. Token-order
    independent via normalization. Two match directions:
      • term == query, or term appears in query  → strong intent, always allowed
      • query is a word-prefix of a longer term  → expansion, gated by stopword
        list + len>=3 so 'the'/'coin' don't match everything."""
    nq = _norm_text(query)
    if not nq:
        return None
    # The bare base symbol (e.g. 'BNB' from 'BNB-USD') is always searchable.
    base = sym.split("-")[0].split("=")[0]
    terms = [sym, base, name, *SEARCH_ALIASES.get(sym, [])]
    expand_ok = len(nq) >= 3 and nq not in _ALIAS_STOPWORDS
    best: str | None = None
    for t in terms:
        nt = _norm_text(t)
        if not nt:
            continue
        # Exact match always; substring-in-query only for terms >=3 chars so a
        # 2-char base like 'PL' (Platinum) doesn't match 'Ri-PL-e'.
        hit = (nt == nq) or (len(nt) >= 3 and nt in nq)
        if not hit and expand_ok:
            hit = nt.startswith(nq + " ")  # e.g. 'Bitcoin' -> 'Bitcoin Cash'
        if hit and (best is None or len(nt) > len(_norm_text(best))):
            best = t
    return best

# Sovereign bond catalog. Pseudo-tickers — when clicked, the frontend
# routes to /api/bonds/treasuries/{tenor} or /api/bonds/eurozone/{country}/{tenor}
# rather than to a yfinance symbol page. Coverage tracks bonds_router.py.
WELL_KNOWN_BOND = {
    "US1M":  "US 1-Month Treasury Bill",
    "US3M":  "US 3-Month Treasury Bill",
    "US6M":  "US 6-Month Treasury Bill",
    "US1Y":  "US 1-Year Treasury",
    "US2Y":  "US 2-Year Treasury",
    "US5Y":  "US 5-Year Treasury",
    "US10Y": "US 10-Year Treasury",
    "US20Y": "US 20-Year Treasury",
    "US30Y": "US 30-Year Treasury",
    "DE10Y": "Germany 10-Year Bund",
    "FR10Y": "France 10-Year OAT",
    "IT10Y": "Italy 10-Year BTP",
    "ES10Y": "Spain 10-Year Bonos",
    "NL10Y": "Netherlands 10-Year",
    "BE10Y": "Belgium 10-Year",
    "AT10Y": "Austria 10-Year",
    "FI10Y": "Finland 10-Year",
    "IE10Y": "Ireland 10-Year",
    "PT10Y": "Portugal 10-Year",
    "GR10Y": "Greece 10-Year",
}

# Eurozone country codes — used for venue resolution of bond pseudo-tickers
_EUROZONE_CODES = {"AT","BE","CY","DE","EE","ES","FI","FR","GR","HR",
                   "IE","IT","LT","LU","LV","MT","NL","PT","SI","SK"}

# ═════════════════════════════════════════════════════════════════════════
# OMNISEARCH — primary endpoint
# ═════════════════════════════════════════════════════════════════════════
class OmniRequest(BaseModel):
    query:        str
    classes:      list[str] | None = None   # ["equity","etf","crypto",...]
    venues:       list[str] | None = None   # ["SE","US","GB",...] (countries)
    limit:        int = 20
    recent_boost: list[str] | None = None   # tickers to boost +100 in match_score (Item 8)

_RECENT_BOOST_POINTS = 100

@router.post("/search")
def omni_search(req: OmniRequest) -> dict[str, Any]:
    """Universal search across all asset classes and venues.

    `recent_boost` is a list of tickers (e.g. from a client's
    localStorage recently-viewed history) that get +100 added to
    match_score so the user's familiar symbols rank above generic hits.
    """
    q = (req.query or "").strip()
    if not q:
        return {"status":"ok", "query":q, "count":0, "results":[]}

    boost_set = {s.strip().upper() for s in (req.recent_boost or []) if isinstance(s, str) and s.strip()}
    cache_key = (
        f"search:{q.upper()}:{','.join(sorted(req.classes or []))}:"
        f"{','.join(sorted(req.venues or []))}:{req.limit}:"
        f"boost={','.join(sorted(boost_set))}"
    )
    if (cached := _cache_get(cache_key)) is not None:
        return cached

    import yfinance as yf
    raw_results: list[dict[str, Any]] = []

    # ── Layer A: yfinance.Search (handles equity/etf/index/crypto/fx most cases) ──
    try:
        s = yf.Search(q, max_results=15)
        for hit in (s.quotes or []):
            sym = hit.get("symbol")
            if not sym: continue
            asset_class = classify_asset(sym, "", hit)
            venue       = resolve_venue(sym, asset_class, hit)
            share_cls   = detect_share_class(sym)
            name        = hit.get("longname") or hit.get("shortname") or sym
            raw_results.append({
                "ticker":      sym,
                "name":        name,
                "asset_class": asset_class,
                "venue":       venue["venue"],
                "country":     venue["country"],
                "currency":    venue["currency"],
                "tier":        venue["tier"],
                "share_class": share_cls,
                "exchange_raw":(hit.get("exchDisp") or hit.get("exchange") or "").upper(),
                "_hit_source": "yf_search",
            })
    except Exception as e:
        logger.warning("yf.Search %s failed: %s", q, e)

    # ── Layer B: well-known catalog match (indices, fx, crypto, commodity by
    #    name OR alias). `_alias_match` is token-order independent and covers
    #    common names ("Binance Coin" -> BNB-USD, "Ripple" -> XRP-USD). ──
    for catalog, asset_class in [
        (WELL_KNOWN_INDEX,     "index"),
        (WELL_KNOWN_FX,        "fx"),
        (WELL_KNOWN_COMMODITY, "commodity"),
        (WELL_KNOWN_CRYPTO,    "crypto"),
        (WELL_KNOWN_BOND,      "bond"),
    ]:
        for sym, name in catalog.items():
            matched_term = _alias_match(q, sym, name)
            if matched_term is not None:
                if any(r["ticker"] == sym for r in raw_results): continue  # skip dupes
                venue = resolve_venue(sym, asset_class, None)
                raw_results.append({
                    "ticker":      sym, "name":        name,
                    "asset_class": asset_class,
                    "venue":       venue["venue"], "country": venue["country"],
                    "currency":    venue["currency"], "tier":    venue["tier"],
                    "share_class": None, "exchange_raw": "",
                    "_hit_source": "catalog",
                    # Rank against the matched alias so "Binance Coin" scores
                    # like a name hit even though the display name is "BNB".
                    "_rank_name":  matched_term,
                })

    # ── Layer C: filter by classes / venues if requested ──
    if req.classes:
        cset = set(c.lower() for c in req.classes)
        raw_results = [r for r in raw_results if r["asset_class"] in cset]
    if req.venues:
        vset = set(v.upper() for v in req.venues)
        raw_results = [r for r in raw_results if r["country"].upper() in vset]

    # ── Layer D: rank ──
    for r in raw_results:
        score = rank_score(q, r["ticker"], r.get("_rank_name") or r["name"], r["exchange_raw"])
        # A catalog hit is an alias-confirmed match — never let it score 0 and
        # tie with yfinance noise (e.g. exact paste "Binance Coin (BNB)").
        if r.get("_hit_source") == "catalog":
            score = max(score, 120)
        if r["ticker"].upper() in boost_set:
            score += _RECENT_BOOST_POINTS  # Item 8: recently-viewed boost
        r["match_score"] = score
    raw_results.sort(key=lambda r: r["match_score"], reverse=True)
    raw_results = raw_results[:req.limit]

    # ── Strip internal fields ──
    for r in raw_results:
        r.pop("exchange_raw", None)
        r.pop("_hit_source",  None)
        r.pop("_rank_name",   None)

    # ── Group by class for UI categorized rendering ──
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in raw_results:
        groups.setdefault(r["asset_class"], []).append(r)

    out = {
        "status":      "ok",
        "query":       q,
        "count":       len(raw_results),
        "groups":      [{"asset_class": ac, "label": ASSET_CLASSES.get(ac, ac.title()),
                         "count": len(items), "results": items} for ac, items in groups.items()],
        "results":     raw_results,  # flat list for non-grouped consumers
    }
    _cache_set(cache_key, out)
    return out

# ═════════════════════════════════════════════════════════════════════════
# QUOTES — batched live price + 24h change for search-result overlay (Item 6)
# ═════════════════════════════════════════════════════════════════════════
class QuotesRequest(BaseModel):
    symbols: list[str]

_QUOTES_TTL = 30.0  # seconds — price freshness vs yfinance rate-limit balance
_QUOTES_MAX_BATCH = 50  # cap per request to bound yf.download time

@router.post("/quotes")
def quotes(req: QuotesRequest) -> dict[str, Any]:
    """
    Batched last-price + 24h change for a list of yfinance-resolvable
    symbols. Used by OmniSearch to overlay live prices on search results.

    Pseudo-tickers (e.g. bond US10Y / DE10Y from /api/bonds) are accepted
    in the request but resolve to price=null. Frontend should render them
    as a non-error empty slot.

    Cached 30s. Cache key is the sorted symbol set, so any two requests
    with the same symbols (regardless of order) share the cache entry.
    """
    raw = req.symbols or []
    symbols = list(dict.fromkeys(  # dedupe, preserve order
        s.strip().upper() for s in raw if isinstance(s, str) and s.strip()
    ))
    if not symbols:
        return {"status": "ok", "count": 0, "quotes": []}
    if len(symbols) > _QUOTES_MAX_BATCH:
        raise HTTPException(400, f"Maximum {_QUOTES_MAX_BATCH} symbols per request")

    cache_key = f"quotes:{','.join(sorted(symbols))}"
    cached = _cache_get(cache_key, ttl=_QUOTES_TTL)
    if cached is not None:
        return cached

    # <- FIXED: only send Yahoo-resolvable tickers to yfinance. Yahoo symbols use
    # letters/digits and . - ^ = (never "_"). Malformed entries (e.g. a stale
    # "VOLV_B" from a saved alert/recent) would 404-spam the logs — skip them and
    # return a null-price slot instead (frontend already renders these gracefully).
    def _yf_ok(s: str) -> bool:
        return bool(s) and "_" not in s and all(ch.isalnum() or ch in ".-^=" for ch in s)

    yf_symbols = [s for s in symbols if _yf_ok(s)]
    yf_set = set(yf_symbols)
    skipped = [s for s in symbols if s not in yf_set]
    if skipped:
        logger.info("quotes: skipped %d non-Yahoo symbol(s): %s", len(skipped), skipped)

    df = None
    if yf_symbols:
        try:
            import yfinance as yf
            df = yf.download(
                tickers=yf_symbols,
                period="5d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            logger.warning("yf.download batch failed for %s: %s", yf_symbols, e)

    now_ts = int(time.time())
    results: list[dict[str, Any]] = []
    for sym in symbols:
        price: float | None = None
        change_pct: float | None = None
        if df is not None and not df.empty and sym in yf_set:
            try:
                # When 1 symbol, df has direct columns (no MultiIndex).
                # When >=2 symbols, df has MultiIndex with ticker at level 0.
                if len(yf_symbols) == 1:
                    closes_series = df.get("Close")
                else:
                    sub = df.get(sym)
                    closes_series = sub["Close"] if sub is not None else None
                if closes_series is not None:
                    closes = [float(v) for v in closes_series.dropna().values]
                    if closes:
                        price = closes[-1]
                    if len(closes) >= 2 and abs(closes[-2]) > 1e-10:
                        change_pct = (closes[-1] / closes[-2] - 1.0) * 100.0
            except Exception as e:
                logger.info("quote slot %s: %s", sym, e)
        # Currency from existing venue resolver — consistent with search rows.
        try:
            ac = classify_asset(sym)
            ccy = resolve_venue(sym, ac, None).get("currency", "USD")
        except Exception:
            ccy = "USD"
        results.append({
            "symbol":     sym,
            "price":      _round(price, 4),
            "change_pct": _round(change_pct, 2),
            "currency":   ccy,
            "ts":         now_ts,
        })

    out = {"status": "ok", "count": len(results), "quotes": results}
    _cache_set(cache_key, out)
    return out

# ═════════════════════════════════════════════════════════════════════════
# ENRICHMENT — symbology resolution + extended metadata
# ═════════════════════════════════════════════════════════════════════════
@router.get("/symbology/{symbol}")
def symbology(symbol: str) -> dict[str, Any]:
    """Resolve a symbol to ISIN, FIGI, CUSIP, and primary venue.

    FIGI is fetched from OpenFIGI (https://api.openfigi.com) when an ISIN is
    available. Set OPENFIGI_API_KEY in .env to raise the rate limit.
    CUSIP remains provider_required (no free source).
    """
    cache_key = f"symbology:{symbol.upper()}"
    if (cached := _cache_get(cache_key, ttl=_TTL_SYMBOLOGY)) is not None:
        return cached

    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
        try:
            isin = t.isin
            if isin == "-": isin = None
        except Exception:
            isin = None
        asset_class = classify_asset(symbol, info.get("quoteType",""), info)
        venue       = resolve_venue(symbol, asset_class, info)

        # Nasdaq Nordic backfill + ISIN authority resolution.
        # yfinance returns "-" for most Nordic tickers AND occasionally
        # returns the WRONG ISIN for cross-listed/foreign-issued securities
        # (e.g. KAMBI.ST → yfinance reports PLCTHQM00018 [Polish prefix],
        # but the authoritative Nasdaq Nordic source is MT0000780107
        # [Maltese — Kambi is incorporated in Malta]).
        #
        # Council fix (2026-05-11): for any Nordic-suffix ticker we PREFER
        # the Nasdaq Nordic screener ISIN over yfinance's. We keep the
        # original yfinance ISIN in `isin_yfinance` for audit + provenance.
        # This is purely additive — no existing field shape changes.
        nn_segment: str | None = None       # <- NEW Item 2: segment for top-level field
        isin_yfinance: str | None = isin    # <- FIX: audit-trail of yfinance's claim
        isin_source: str = "yfinance"       # <- FIX: provenance for the chosen ISIN
        if symbol.upper().endswith((".ST", ".CO", ".IC")):
            try:
                from .providers.nasdaq_nordic import lookup_segment
                nn_segment, nn_isin = lookup_segment(symbol)
                if nn_segment == "unknown":  # don't surface "unknown" — looks broken
                    nn_segment = None
                if nn_isin:                  # FIX: Nordic is AUTHORITATIVE — prefer it
                    isin = nn_isin
                    isin_source = "nasdaq_nordic"
            except Exception as e:
                logger.warning("Nasdaq Nordic backfill failed for %s: %s", symbol, e)

        # FIGI lookup via OpenFIGI when we have an ISIN. Cached 24h since FIGIs are stable.
        figi: str | None = None
        figi_status = "provider_required"
        if isin:
            figi_cache_key = f"figi:{isin.upper()}"
            cached_figi = _cache_get(figi_cache_key, ttl=_TTL_SYMBOLOGY)
            if cached_figi is not None:
                figi = cached_figi or None  # empty string sentinel → None
                figi_status = "ok" if figi else "not_found"
            else:
                try:
                    from .providers.openfigi import isin_to_figi_sync
                    figi = isin_to_figi_sync(isin)
                except Exception as e:
                    logger.warning("OpenFIGI provider error for %s/%s: %s", symbol, isin, e)
                    figi = None
                # Cache both hits and misses so we don't hammer OpenFIGI; misses
                # use empty-string sentinel so a None return means "no entry yet".
                _cache_set(figi_cache_key, figi or "")
                figi_status = "ok" if figi else "not_found"

        out = {
            "status":      "ok",
            "symbol":      symbol.upper(),
            "name":        info.get("longName") or info.get("shortName") or symbol,
            "asset_class": asset_class,
            "share_class": detect_share_class(symbol),
            "isin":        isin,
            "figi":        figi,
            "figi_status": figi_status,
            "cusip":       None,            # provider_required — no free source
            "venue":       venue,
            "currency":    info.get("currency") or venue["currency"],
            "exchange_raw":info.get("exchange"),
            "segment":     nn_segment,                                        # <- NEW Item 2: "main" | "first_north" | "other" | None
            "segment_source": "nasdaq_nordic" if nn_segment else None,        # <- NEW Item 2: provenance for the badge tooltip
            "isin_yfinance": isin_yfinance if isin_yfinance != isin else None, # <- FIX: yfinance's ISIN claim when it differs from authoritative
            "isin_source": isin_source,                                       # <- FIX: "nasdaq_nordic" | "yfinance"
        }
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.exception("symbology %s", symbol)
        raise HTTPException(500, f"symbology error: {e}")

@router.get("/asset/{symbol}/dividends")
def asset_dividends(symbol: str) -> dict[str, Any]:
    """Last 5 dividend events with ex-date and amount."""
    cache_key = f"div:{symbol.upper()}"
    if (cached := _cache_get(cache_key)) is not None: return cached
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        divs = t.dividends
        events: list[dict[str, Any]] = []
        if divs is not None and len(divs) > 0:
            tail = divs.tail(8)
            for ts, amt in tail.items():
                events.append({"ex_date": str(ts)[:10], "amount": _round(float(amt), 4)})
        out = {"status": "ok", "symbol": symbol.upper(), "count": len(events), "events": events}
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("dividends %s: %s", symbol, e)
        return {"status": "ok", "symbol": symbol.upper(), "count": 0, "events": [], "error": str(e)[:200]}

# ─────────────────────────────────────────────────────────────────────────
# News helpers — shared by asset / macro / sector endpoints (Item 7)
# ─────────────────────────────────────────────────────────────────────────
import hashlib
from datetime import datetime, timezone


def _pub_to_unix(pub: Any) -> int:
    """Normalize yfinance pubDate (ISO string) or providerPublishTime
    (unix int) to a unix timestamp. Returns 0 when unparseable.
    """
    if pub is None: return 0
    if isinstance(pub, (int, float)):
        try: return int(pub)
        except Exception: return 0
    if isinstance(pub, str):
        try:
            s = pub.rstrip("Z")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return 0
    return 0

def _pub_to_iso(pub: Any) -> str | None:
    """Emit a consistent ISO 8601 UTC string. Falls back to raw input."""
    if pub is None: return None
    if isinstance(pub, str): return pub
    if isinstance(pub, (int, float)):
        try:
            return datetime.fromtimestamp(int(pub), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return str(pub)
    return None

def _fetch_news_for_symbol(symbol: str, max_items: int = 15) -> list[dict[str, Any]]:
    """Fetch normalized news items for a single yfinance ticker. Never raises."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        raw = (t.news or [])[:max_items]
    except Exception as e:
        logger.warning("yfinance news fetch failed for %s: %s", symbol, e)
        return []
    out: list[dict[str, Any]] = []
    for n in raw:
        content = n.get("content") or n  # newer yfinance wraps in 'content'
        title = content.get("title") or n.get("title")
        link  = ((content.get("clickThroughUrl") or {}).get("url")
                 or (content.get("canonicalUrl") or {}).get("url")
                 or n.get("link"))
        pub   = content.get("pubDate") or n.get("providerPublishTime")
        provider = (content.get("provider") or {}).get("displayName") or n.get("publisher")
        if not title: continue
        out.append({
            "title":     title,
            "url":       link,
            "published": _pub_to_iso(pub),
            "_ts":       _pub_to_unix(pub),
            "provider":  provider or "—",
            "source_symbol": symbol.upper(),
        })
    return out

# ── Title-similarity clustering (Item 7) ─────────────────────────────────
# Yahoo Finance frequently surfaces 4-6 different syndications of the same
# story (Reuters → MarketWatch → Yahoo → Insider Monkey → ...). URL-dedup
# misses these because each republisher gets a unique URL. Title-shingle
# Jaccard catches them: any pair with similarity >= threshold is a single
# story. We expose the cluster size + provider list to the UI so users can
# see a single headline ("3 sources") instead of 3 near-identical rows.

_TITLE_STOPWORDS: set[str] = {
    "a","an","the","and","or","but","of","in","on","at","to","for","with",
    "by","from","as","is","are","was","were","be","been","being","has","have",
    "had","do","does","did","this","that","these","those","it","its","s",
    "after","before","over","under","new","up","down","could","would","may",
    "might","also","still","just","not","no",
}

def _normalize_title(t: str) -> str:
    """Lowercased, ASCII-fold-ish, alphanumeric-only token stream."""
    if not t:
        return ""
    out: list[str] = []
    cur: list[str] = []
    for ch in t.lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return " ".join(w for w in out if w not in _TITLE_STOPWORDS and len(w) > 1)

def _title_shingles(t: str) -> set[str]:
    """Bigram shingles of the normalized title."""
    words = _normalize_title(t).split()
    if len(words) < 2:
        return set(words)
    return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}

def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two sets. Returns 0.0 when both empty."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0

def _cluster_near_duplicates(
    items: list[dict[str, Any]],
    threshold: float = 0.55,
) -> list[dict[str, Any]]:
    """Greedy cluster. First-seen item wins. Adds cluster metadata.

    Each output item gets:
        cluster_size      — total items in the cluster (1 if unique)
        cluster_providers — distinct provider names
        cluster_urls      — all URLs in the cluster (caller may show "more sources")

    Items are NOT mutated in place; a copy is taken before annotating.
    Threshold 0.55 on bigrams is empirically right for English news headlines:
    catches republications and minor edits, leaves genuinely different stories
    apart.
    """
    if not items:
        return []
    clusters: list[dict[str, Any]] = []   # one entry per cluster
    cluster_shingles: list[set[str]] = []  # parallel array of representative shingles

    for it in items:
        sh = _title_shingles(it.get("title", ""))
        # Find the first existing cluster whose representative is similar enough
        joined = False
        for idx, rep_sh in enumerate(cluster_shingles):
            if _jaccard(sh, rep_sh) >= threshold:
                clusters[idx]["__members"].append(it)
                joined = True
                break
        if not joined:
            seed = dict(it)              # shallow copy so we don't mutate caller
            seed["__members"] = [it]
            clusters.append(seed)
            cluster_shingles.append(sh)

    # Materialize: representative item with cluster metadata
    out: list[dict[str, Any]] = []
    for c in clusters:
        members = c.pop("__members")
        providers = []
        urls = []
        seen_p: set[str] = set()
        seen_u: set[str] = set()
        for m in members:
            p = m.get("provider")
            if p and p not in seen_p:
                providers.append(p); seen_p.add(p)
            u = m.get("url")
            if u and u not in seen_u:
                urls.append(u); seen_u.add(u)
        c["cluster_size"]      = len(members)
        c["cluster_providers"] = providers
        c["cluster_urls"]      = urls
        out.append(c)
    return out

def _dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by SHA-1 of URL (or title fallback). Keeps first occurrence."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = item.get("url") or item.get("title") or ""
        if not key: continue
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()
        if h in seen: continue
        seen.add(h)
        out.append(item)
    return out

def _strip_internal(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove internal sort fields before serializing to clients."""
    for item in items:
        item.pop("_ts", None)
    return items

@router.get("/asset/{symbol}/news")
def asset_news(symbol: str) -> dict[str, Any]:
    """Recent news headlines for a single symbol (yfinance, deduped by URL)."""
    cache_key = f"news:{symbol.upper()}"
    if (cached := _cache_get(cache_key)) is not None: return cached
    try:
        items = _fetch_news_for_symbol(symbol, max_items=20)
        items = _dedupe_news(items)                         # pass 1: URL hash
        items.sort(key=lambda x: x.get("_ts") or 0, reverse=True)
        items = _cluster_near_duplicates(items)             # pass 2: title shingles
        items = _strip_internal(items)
        out = {"status":"ok", "symbol": symbol.upper(),
               "count": len(items), "items": items, "deduped": True}
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        logger.warning("news %s: %s", symbol, e)
        return {"status":"ok", "symbol": symbol.upper(), "count": 0, "items": [], "error": str(e)[:200]}

# Macro proxies — yfinance tickers whose news streams pick up FOMC,
# rates, central bank, USD, gold, and broad-market headlines. Aggregating
# across these covers most macro topics without a paid wire feed.
_MACRO_PROXIES: list[str] = [
    "^GSPC",   # S&P 500 — broadest market headlines
    "^DJI",    # Dow — overlaps but catches different syndications
    "^IXIC",   # NASDAQ Composite
    "TLT",     # 20Y+ Treasury ETF — surfaces FOMC/rate news
    "GLD",     # Gold ETF — inflation / safe-haven
    "UUP",     # USD Bullish Index ETF — DXY proxy
]

# SPDR sector ETFs — one ticker per GICS sector. Yahoo aggregates
# sector-level news on the ETF's news feed.
_SECTOR_ETFS: dict[str, tuple[str, str]] = {
    "financials":             ("XLF",  "Financials"),
    "energy":                 ("XLE",  "Energy"),
    "technology":             ("XLK",  "Technology"),
    "healthcare":             ("XLV",  "Health Care"),
    "consumer_discretionary": ("XLY",  "Consumer Discretionary"),
    "consumer_staples":       ("XLP",  "Consumer Staples"),
    "industrials":            ("XLI",  "Industrials"),
    "materials":              ("XLB",  "Materials"),
    "utilities":              ("XLU",  "Utilities"),
    "real_estate":            ("XLRE", "Real Estate"),
    "communications":         ("XLC",  "Communication Services"),
}

@router.get("/news/macro")
def news_macro(limit: int = 25) -> dict[str, Any]:
    """Aggregate macro headlines from major-index and macro-sensitive ETFs.

    Pulls news for ^GSPC, ^DJI, ^IXIC, TLT, GLD, UUP; dedupes by URL hash;
    sorts newest first. Each item carries `source_symbol` so consumers know
    which proxy surfaced it. Cached 60s.
    """
    if limit < 1 or limit > 100:
        raise HTTPException(400, "limit must be 1..100")
    cache_key = f"news:macro:{limit}"
    if (cached := _cache_get(cache_key)) is not None: return cached

    aggregated: list[dict[str, Any]] = []
    proxies_hit: list[str] = []
    for sym in _MACRO_PROXIES:
        items = _fetch_news_for_symbol(sym, max_items=10)
        if items: proxies_hit.append(sym)
        aggregated.extend(items)

    deduped = _dedupe_news(aggregated)
    deduped.sort(key=lambda x: x.get("_ts") or 0, reverse=True)
    clustered = _cluster_near_duplicates(deduped)         # Item 7: title-shingle dedup
    final = _strip_internal(clustered[:limit])

    out = {
        "status":          "ok",
        "scope":           "macro",
        "proxies":         _MACRO_PROXIES,
        "proxies_hit":     proxies_hit,
        "count":           len(final),
        "raw_count":       len(aggregated),
        "url_deduped_count": len(deduped),
        "clustered_count": len(clustered),
        "items":           final,
        "deduped":         True,
    }
    _cache_set(cache_key, out)
    return out

@router.get("/news/sector/{sector}")
def news_sector(sector: str, limit: int = 25) -> dict[str, Any]:
    """Sector-wide news, sourced from the matching SPDR sector ETF.

    Sector key ∈ {financials, energy, technology, healthcare,
    consumer_discretionary, consumer_staples, industrials, materials,
    utilities, real_estate, communications}. Deduped by URL hash.
    """
    s = (sector or "").lower().strip()
    if s not in _SECTOR_ETFS:
        raise HTTPException(
            400,
            f"Unknown sector {sector!r}. Valid: {sorted(_SECTOR_ETFS.keys())}",
        )
    if limit < 1 or limit > 100:
        raise HTTPException(400, "limit must be 1..100")
    etf, label = _SECTOR_ETFS[s]
    cache_key = f"news:sector:{s}:{limit}"
    if (cached := _cache_get(cache_key)) is not None: return cached

    items = _fetch_news_for_symbol(etf, max_items=limit * 2)
    items = _dedupe_news(items)
    items.sort(key=lambda x: x.get("_ts") or 0, reverse=True)
    clustered = _cluster_near_duplicates(items)             # Item 7: title-shingle dedup
    final = _strip_internal(clustered[:limit])

    out = {
        "status":            "ok",
        "scope":             "sector",
        "sector":            s,
        "label":             label,
        "proxy":             etf,
        "count":             len(final),
        "raw_count":         len(items),
        "clustered_count":   len(clustered),
        "items":             final,
        "deduped":           True,
    }
    _cache_set(cache_key, out)
    return out

@router.get("/asset/{symbol}/esg")
def asset_esg(symbol: str) -> dict[str, Any]:
    """
    ESG ratings.

    Resolution order:
      1. Configured ESG provider (ESG_PROVIDER env var) — paid slot for
         MSCI ESG / Sustainalytics / Refinitiv. Currently a stub; real
         client lives in api/providers/esg.py.
      2. yfinance.sustainability — best-effort, Yahoo coverage has
         degraded but still works for some US large-caps.
      3. provider_required marker when both sources are empty.

    NEVER fabricates a score, percentile, controversy level, or rating.
    """
    sym_u = symbol.upper()
    cache_key = f"esg:{sym_u}"
    if (cached := _cache_get(cache_key)) is not None: return cached

    sources: list[str] = []
    out: dict[str, Any] = {
        "status":            "ok",
        "symbol":            sym_u,
        "available":         False,
        "total":             None,
        "environment":       None,
        "social":            None,
        "governance":        None,
        "controversy":       None,
        "percentile":        None,
        "rating":            None,
        "as_of":             None,
        "sources":           sources,
        "provider_required": None,
    }

    # ── Layer 1: configured paid provider ─────────────────────────────
    try:
        from .providers.esg import configured_provider, lookup_esg
        provider = configured_provider()
        if provider is not None:
            data = lookup_esg(sym_u)
            if data:
                for k, v in data.items():
                    if v is not None and k in out:
                        out[k] = v
                sources.append(provider.lower().replace(" ", "_"))
                out["available"] = True
    except Exception as e:
        logger.warning("ESG provider lookup failed for %s: %s", sym_u, e)

    # ── Layer 2: yfinance.sustainability fallback ─────────────────────
    if not out["available"]:
        try:
            import yfinance as yf
            t = yf.Ticker(symbol)
            s = None
            try: s = t.sustainability
            except Exception: pass
            if s is not None and len(s) > 0:
                rec = s.iloc[:, 0].to_dict() if hasattr(s, "iloc") else {}
                out.update({
                    "available":   True,
                    "total":       _safe(rec.get("totalEsg")),
                    "environment": _safe(rec.get("environmentScore")),
                    "social":      _safe(rec.get("socialScore")),
                    "governance":  _safe(rec.get("governanceScore")),
                    "controversy": _safe(rec.get("highestControversy")),
                    "percentile":  _safe(rec.get("percentile")),
                })
                sources.append("yfinance")
        except Exception as e:
            logger.warning("yfinance ESG fallback failed for %s: %s", sym_u, e)

    # ── Layer 3: honest gap marker ────────────────────────────────────
    if not out["available"]:
        out["provider_required"] = "MSCI ESG / Sustainalytics / Refinitiv ESG"
        out["note"] = (
            "Yahoo no longer reliably exposes ESG. Set ESG_PROVIDER + "
            "ESG_API_KEY for paid coverage."
        )

    out["sources"] = sources
    _cache_set(cache_key, out)
    return out

@router.get("/asset/{symbol}/fundamentals-extended")
def asset_fundamentals_extended(symbol: str) -> dict[str, Any]:
    """Extra fundamentals beyond the standard symbol page."""
    cache_key = f"fundx:{symbol.upper()}"
    if (cached := _cache_get(cache_key)) is not None: return cached
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.info or {}
        out = {
            "status": "ok", "symbol": symbol.upper(),
            "fund_data": {  # for ETFs/mutual funds
                "expense_ratio":   _safe(info.get("annualReportExpenseRatio")),
                "yield":           _safe(info.get("yield")),
                "category":        info.get("category"),
                "fund_family":     info.get("fundFamily"),
                "ytd_return":      _safe(info.get("ytdReturn")),
                "three_year_avg":  _safe(info.get("threeYearAverageReturn")),
                "five_year_avg":   _safe(info.get("fiveYearAverageReturn")),
                "total_assets":    _safe(info.get("totalAssets")),
            },
            "options_summary": {
                "options_available":  bool(t.options),
                "expirations_count":  len(t.options or ()),
            },
        }
        _cache_set(cache_key, out)
        return out
    except Exception as e:
        return {"status":"ok", "symbol": symbol.upper(), "error": str(e)[:200]}

# ═════════════════════════════════════════════════════════════════════════
# LOOKUP-BY-ISIN — UCITS / mutual fund coverage (Item 3)
# ═════════════════════════════════════════════════════════════════════════
def _valid_isin_shape(isin: str) -> bool:
    s = (isin or "").strip().upper()
    return len(s) == 12 and s.isalnum()

@router.post("/lookup/by-isin/{isin}")
def lookup_by_isin(isin: str) -> dict[str, Any]:
    """
    Resolve an instrument by ISIN.

    Resolution order:
      1. yfinance.Search(isin) → Ticker.info — covers many UCITS, ETFs,
         and equities via Yahoo's symbology.
      2. Configured fund-data provider (FUNDS_PROVIDER env var) — paid
         slot for FundsLibrary / FE fundinfo / Morningstar Direct.
         Currently a stub; real client lives in
         api/providers/funds_library.py.
      3. OpenFIGI for FIGI enrichment (composes with Item 1).

    NEVER fabricates NAV, returns, AUM, or expense ratios. When no source
    has the fund, returns available=False and provider_required points
    at the recommended paid feed.
    """
    isin_u = (isin or "").strip().upper()
    if not _valid_isin_shape(isin_u):
        raise HTTPException(400, "ISIN must be 12 alphanumeric characters")

    cache_key = f"by_isin:{isin_u}"
    if (cached := _cache_get(cache_key, ttl=_TTL_SYMBOLOGY)) is not None:
        return cached

    sources: list[str] = []
    out: dict[str, Any] = {
        "status":            "ok",
        "isin":              isin_u,
        "available":         False,
        "ticker":            None,
        "name":              None,
        "asset_class":       None,
        "currency":          None,
        "nav":               None,            # last close / navPrice fallback
        "ytd_return":        None,
        "three_year_return": None,
        "five_year_return":  None,
        "expense_ratio":     None,
        "total_assets":      None,
        "fund_family":       None,
        "category":          None,
        "figi":              None,
        "figi_status":       "provider_required",
        "sources":           sources,
        "provider_required": None,
    }

    # ── Layer 1: yfinance ─────────────────────────────────────────────
    try:
        import yfinance as yf
        # yf.Ticker(isin) works directly for many ISINs — Yahoo resolves
        # the ISIN to its primary listing and returns ticker info.
        t = yf.Ticker(isin_u)
        info = t.info or {}
        # If Ticker(ISIN) didn't resolve, fall back to Search.
        if not info.get("symbol") and not info.get("longName"):
            s = yf.Search(isin_u, max_results=3)
            hits = s.quotes or []
            if hits:
                resolved_sym = hits[0].get("symbol")
                if resolved_sym:
                    t = yf.Ticker(resolved_sym)
                    info = t.info or {}
        sym = info.get("symbol")
        if sym and (info.get("longName") or info.get("shortName")):
            qt = (info.get("quoteType") or "").lower()
            out.update({
                "available":         True,
                "ticker":            sym,
                "name":              info.get("longName") or info.get("shortName"),
                "asset_class":       classify_asset(sym, info.get("quoteType",""), info),
                "currency":          info.get("currency"),
                "nav":               _round(info.get("navPrice") or info.get("previousClose"), 4),
                "ytd_return":        _safe(info.get("ytdReturn")),
                "three_year_return": _safe(info.get("threeYearAverageReturn")),
                "five_year_return":  _safe(info.get("fiveYearAverageReturn")),
                "expense_ratio":     _safe(info.get("annualReportExpenseRatio")),
                "total_assets":      _safe(info.get("totalAssets")),
                "fund_family":       info.get("fundFamily"),
                "category":          info.get("category"),
            })
            sources.append("yfinance")
    except Exception as e:
        logger.warning("yfinance ISIN lookup failed for %s: %s", isin_u, e)

    # ── Layer 2: paid fund provider (slot, currently a stub) ──────────
    try:
        from .providers.funds_library import configured_provider, lookup_fund_by_isin
        provider = configured_provider()
        if provider is not None:
            data = lookup_fund_by_isin(isin_u)
            if data:
                for k, v in data.items():
                    if v is not None and k in out:
                        out[k] = v
                sources.append(provider.lower().replace(" ", "_"))
                out["available"] = True
        if not out["available"]:
            # Surface the gap honestly
            out["provider_required"] = "FundsLibrary or FE fundinfo (UCITS coverage)"
    except Exception as e:
        logger.warning("Fund provider lookup failed for %s: %s", isin_u, e)

    # ── Layer 3: OpenFIGI (composes with Item 1) ──────────────────────
    try:
        from .providers.openfigi import isin_to_figi_sync
        figi_cache_key = f"figi:{isin_u}"
        cached_figi = _cache_get(figi_cache_key, ttl=_TTL_SYMBOLOGY)
        if cached_figi is not None:
            figi = cached_figi or None
        else:
            figi = isin_to_figi_sync(isin_u)
            _cache_set(figi_cache_key, figi or "")
        if figi:
            out["figi"] = figi
            out["figi_status"] = "ok"
            sources.append("openfigi")
        else:
            out["figi_status"] = "not_found"
    except Exception as e:
        logger.warning("OpenFIGI lookup failed for ISIN %s: %s", isin_u, e)

    out["sources"] = sources
    _cache_set(cache_key, out)
    return out

# ═════════════════════════════════════════════════════════════════════════
# CATEGORY DISCOVERY — browse-by-asset-class endpoints
# ═════════════════════════════════════════════════════════════════════════
@router.get("/category/{asset_class}")
def browse_category(asset_class: str, limit: int = 20) -> dict[str, Any]:
    """Browse a curated catalog for an asset class (no query)."""
    a = asset_class.lower()
    if a not in ASSET_CLASSES:
        raise HTTPException(400, f"Unknown asset class. Valid: {list(ASSET_CLASSES.keys())}")
    catalog: list[dict[str, Any]] = []
    if a == "index":
        for sym, name in WELL_KNOWN_INDEX.items():
            v = resolve_venue(sym, "index", None)
            catalog.append({"ticker": sym, "name": name, "asset_class": "index", **{
                "venue": v["venue"], "country": v["country"], "currency": v["currency"], "tier": v["tier"]
            }})
    elif a == "fx":
        for sym, name in WELL_KNOWN_FX.items():
            v = resolve_venue(sym, "fx", None)
            catalog.append({"ticker": sym, "name": name, "asset_class": "fx", **{
                "venue": v["venue"], "country": v["country"], "currency": v["currency"], "tier": v["tier"]
            }})
    elif a == "commodity":
        for sym, name in WELL_KNOWN_COMMODITY.items():
            v = resolve_venue(sym, "commodity", None)
            catalog.append({"ticker": sym, "name": name, "asset_class": "commodity", **{
                "venue": v["venue"], "country": v["country"], "currency": v["currency"], "tier": v["tier"]
            }})
    elif a == "crypto":
        for sym, name in WELL_KNOWN_CRYPTO.items():
            v = resolve_venue(sym, "crypto", None)
            catalog.append({"ticker": sym, "name": name, "asset_class": "crypto", **{
                "venue": v["venue"], "country": v["country"], "currency": v["currency"], "tier": v["tier"]
            }})
    elif a == "bond":
        for sym, name in WELL_KNOWN_BOND.items():
            v = resolve_venue(sym, "bond", None)
            catalog.append({"ticker": sym, "name": name, "asset_class": "bond", **{
                "venue": v["venue"], "country": v["country"], "currency": v["currency"], "tier": v["tier"]
            }})
    return {"status": "ok", "asset_class": a, "count": len(catalog), "results": catalog[:limit]}
