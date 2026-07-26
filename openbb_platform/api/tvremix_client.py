# api/tvremix_client.py
"""
tvremix MCP bridge client — TradingView data inside the SENTRIQ backend.

Protocol (live-verified 2026-07-22 against https://tvremix.xyz/api/mcp/v1):
  - Stateless MCP-over-HTTP: one JSON-RPC 2.0 POST per call, no session id.
  - Auth: "Authorization: Bearer <TVREMIX_API_KEY>" (env; never logged).
  - The server REQUIRES an Accept header including application/json —
    omitting it returns JSON-RPC error -32600 "Not Acceptable".
  - tools/call responses carry the payload twice: result.structuredContent
    (parsed) and result.content[0].text (JSON string). Payload envelope is
    {"success": true, "data": {...}} or {"success": false, "error": "..."}.
  - Symbols use TV format EXCHANGE:TICKER (OMXSTO:VOLV_B, CRYPTO:BTCUSD).
    Bare tickers are NOT reliably covered (live probe: get_news("AAPL")
    -> success:false), so mapping is deterministic-only via to_tv_symbol().
  - Verified live: get_quote OMXSTO:VOLV_B = 347.8 SEK; get_news returned
    same-day Dow Jones Newswires items for VOLV_B; run_screener works for
    markets "sweden", "america", "crypto".

REDISTRIBUTION GATE (project TRUTH 3): tvremix is a third-party TradingView
wrapper. Do NOT surface raw TV price quotes to end users through the SENTRIQ
UI until tvremix's redistribution terms are verified. Internal signal
generation / informational analytics context is the intended use here.

Key is read at call time via os.getenv, never logged, never returned, and
never included in exception text (errors reduce to "HTTP <code>" or the
exception class name).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("tvremix")

_MCP_URL = "https://tvremix.xyz/api/mcp/v1"
_PROBE_TIMEOUT_S = 10
_CALL_TIMEOUT_S = 20
_SCREENER_TIMEOUT_S = 40
# Escalating retries for screener calls: live-observed 2026-07-22 that
# back-to-back scans trip a per-minute burst limit (exact budget unpublished).
_RETRY_BACKOFFS_S = (2.0, 20.0, 40.0)
_MAX_NEWS_ITEMS = 10
_CAPS_CACHE: dict = {}


def tvremix_key_present() -> bool:
    """Placeholder-aware presence check (polygon_news idiom)."""
    v = os.getenv("TVREMIX_API_KEY", "").strip()
    return bool(v) and v != "PASTE" and not (v.startswith("{") and v.endswith("}"))


def to_tv_symbol(symbol: str) -> Optional[str]:
    """Deterministic yfinance→TradingView symbol mapping.

    Only mappings PROVEN against the live endpoint are implemented:
      - "VOLV-B.ST" -> "OMXSTO:VOLV_B" (Nasdaq Stockholm)
      - anything already in EXCHANGE:TICKER form passes through unchanged.
    Everything else returns None (honest limitation — bare US tickers are
    not reliably covered per the live get_news("AAPL") probe, and other
    exchange prefixes are unverified; extend only with verified mappings).
    """
    s = (symbol or "").strip()
    if not s:
        return None
    if ":" in s:
        return s
    if s.upper().endswith(".ST"):
        base = s[:-3].replace("-", "_").upper()
        return f"OMXSTO:{base}"
    return None


# Screener markets whose rows map cleanly back to yfinance tickers. NGM /
# Spotlight / OTC / pink-sheet prefixes are deliberately NOT mapped — they are
# not the Nasdaq Stockholm / NYSE-NASDAQ main-market universe the broad scan
# grades, so they are dropped honestly rather than mis-joined.
_TV_US_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX", "BATS", "ARCA", "NYSEARCA"})


def from_tv_symbol(tv_symbol: str) -> Optional[str]:
    """Inverse of to_tv_symbol: TradingView EXCHANGE:TICKER -> yfinance ticker.

    Proven inverses only:
      - "OMXSTO:VOLV_B" -> "VOLV-B.ST"  (Nasdaq Stockholm; '_'->'-', add .ST)
      - "NASDAQ:AAPL" / "NYSE:JPM" / "AMEX:X" -> "AAPL" / "JPM" / "X"
    Any other exchange prefix (NGM, OMXSTOCK OTC, CRYPTO, forex, no-colon) -> None,
    so unmappable rows are excluded from the broad scan rather than guessed.
    """
    s = (tv_symbol or "").strip()
    if ":" not in s:
        return None
    exch, _, base = s.partition(":")
    exch = exch.upper()
    base = base.strip()
    if not base:
        return None
    if exch == "OMXSTO":
        return f"{base.replace('_', '-').upper()}.ST"
    if exch in _TV_US_EXCHANGES:
        return base.upper()
    return None


def _rpc(method: str, params: Optional[dict], timeout: float) -> dict:
    """One JSON-RPC POST. Raises on transport errors; caller reduces them."""
    key = os.getenv("TVREMIX_API_KEY", "").strip()
    envelope: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        envelope["params"] = params
    req = urllib.request.Request(
        _MCP_URL,
        data=json.dumps(envelope).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Mandatory: server 406s ("Not Acceptable") without this header.
            "Accept": "application/json, text/event-stream",
            "User-Agent": "sentriq-backend",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_tool(name: str, arguments: dict, timeout: float = _CALL_TIMEOUT_S) -> Optional[dict]:
    """tools/call wrapper. Returns the payload's "data" dict, or None on ANY
    failure (transport, JSON-RPC error, success:false). Never raises."""
    try:
        resp = _rpc("tools/call", {"name": name, "arguments": arguments}, timeout)
    except urllib.error.HTTPError as e:
        logger.debug("tvremix %s failed: HTTP %s", name, e.code)
        return None
    except Exception as exc:  # noqa: BLE001 - degrade, never crash a scan
        logger.debug("tvremix %s failed: %s", name, type(exc).__name__)
        return None
    err = resp.get("error")
    if err is not None:
        msg = err.get("message", "") if isinstance(err, dict) else err
        logger.debug("tvremix %s rpc error: %s", name, str(msg)[:160])
        return None
    result = resp.get("result") or {}
    payload = result.get("structuredContent")
    if payload is None:
        try:
            payload = json.loads(result["content"][0]["text"])
        except Exception:  # noqa: BLE001
            logger.debug("tvremix %s: unparseable result", name)
            return None
    if not isinstance(payload, dict):  # contract: never raise on odd payloads
        logger.debug("tvremix %s: non-dict payload", name)
        return None
    if payload.get("success") is not True:
        logger.debug("tvremix %s: %s", name, str(payload.get("error", "unknown"))[:160])
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


# ── public data functions (all return None on failure, never raise) ────────

def get_quote(symbol: str) -> Optional[dict]:
    """Quote dict: name, description, price, change_percent, change_abs,
    volume, market_cap, pe_ratio, sector, industry. INTERNAL USE — see the
    redistribution gate in the module docstring before any UI exposure."""
    if not tvremix_key_present():
        return None
    return _call_tool("get_quote", {"symbol": symbol})


def get_quotes_batch(symbols: list) -> Optional[dict]:
    if not tvremix_key_present() or not symbols:
        return None
    return _call_tool("get_quotes_batch", {"symbols": list(symbols)})


def get_technicals_rating(symbol: str, interval: str = "1D") -> Optional[dict]:
    """Rating dict: summary {recommendation, value in [-1, 1]}, oscillators,
    moving_averages, price, change, volume."""
    if not tvremix_key_present():
        return None
    return _call_tool("get_technicals_rating",
                      {"symbol": symbol, "interval": interval})


def get_full_technicals(symbol: str, timeframes: Optional[list] = None) -> Optional[dict]:
    if not tvremix_key_present():
        return None
    args: dict[str, Any] = {"symbol": symbol}
    if timeframes:
        args["timeframes"] = list(timeframes)
    return _call_tool("get_full_technicals", args)


def run_screener(market: str = "america", *, limit: int = 50,
                 sort_by: str = "volume", sort_order: str = "desc",
                 filters: Optional[dict] = None,
                 columns: Optional[list] = None,
                 symbol_types: Optional[list] = None,
                 filter_preset: Optional[str] = None) -> Optional[list]:
    """Market-wide screener rows (verified markets: sweden, america, crypto).
    Rows include symbol, description, type, close, volume, Recommend.All,
    recommendation, RSI, sector, currency, earnings dates. Returns the raw
    results list — NO filtering is applied here (user decision 2026-07-22:
    unfiltered, honestly labelled; thresholds are user-supplied only)."""
    if not tvremix_key_present():
        return None
    args: dict[str, Any] = {"market": market, "limit": limit,
                            "sort_by": sort_by, "sort_order": sort_order}
    if filters:
        args["filters"] = filters
    if columns:
        args["columns"] = list(columns)
    if symbol_types:
        args["symbol_types"] = list(symbol_types)
    if filter_preset:
        args["filter_preset"] = filter_preset
    data = _call_tool("run_screener", args, timeout=_SCREENER_TIMEOUT_S)
    for backoff in _RETRY_BACKOFFS_S:
        if data is not None:
            break
        time.sleep(backoff)
        data = _call_tool("run_screener", args, timeout=_SCREENER_TIMEOUT_S)
    if data is None:
        return None
    results = data.get("results")
    return results if isinstance(results, list) else None


# ── scanner news-chain adapter (shape-compatible with _candidate_news) ─────

def parse_tvremix_news_items(headlines: list, now: Optional[datetime] = None) -> list:
    """Pure normalizer: tvremix get_news headlines → scanner item shape
    {title, age_days, url, publisher}. tvremix headlines carry no summary
    field and no sentiment labels, so the scanner's lexicon path applies.
    Fixture-testable, no network."""
    now = now or datetime.now(timezone.utc)
    items: list[dict] = []
    for h in headlines or []:
        if not isinstance(h, dict):
            continue
        title = (h.get("title") or "").strip()
        if not title:
            continue
        age_days = None
        pub = h.get("published")
        if isinstance(pub, str) and pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = max(0, (now - dt).days)
            except ValueError:
                pass
        item: dict[str, Any] = {"title": title[:160], "age_days": age_days}
        link = h.get("link")
        if isinstance(link, str) and link:
            item["url"] = link[:300]
        provider = h.get("provider")
        if isinstance(provider, str) and provider:
            item["publisher"] = provider[:60]
        items.append(item)
        if len(items) >= _MAX_NEWS_ITEMS:
            break
    return items


def fetch_tvremix_news(symbol: str, limit: int = _MAX_NEWS_ITEMS) -> Optional[dict]:
    """News for the scanner chain: {"items", "source", "as_of"} or None.
    Only deterministically mappable symbols (.ST / EXCHANGE:TICKER) are
    queried — everything else returns None honestly (see to_tv_symbol)."""
    if not tvremix_key_present():
        return None
    tv_sym = to_tv_symbol(symbol)
    if tv_sym is None:
        return None
    data = _call_tool("get_news", {"symbol": tv_sym, "limit": limit})
    if data is None:
        return None
    items = parse_tvremix_news_items(data.get("headlines") or [])
    if not items:
        return None
    return {
        "items": items,
        "source": f"TradingView news via tvremix ({len(items)} wire items)",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }


# ── /api/ready capability probe (client-module idiom) ──────────────────────

def tvremix_capabilities(force: bool = False) -> dict:
    """One cheap authenticated MCP initialize handshake. Booleans + HTTP
    reason only, never the key. Cached for the process lifetime."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    if not tvremix_key_present():
        _CAPS_CACHE = {"tvremix_key_present": False, "tvremix_working": False,
                       "tvremix_reason": "TVREMIX_API_KEY not set (or placeholder)"}
        return _CAPS_CACHE
    try:
        resp = _rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "sentriq-backend", "version": "1.0"},
        }, timeout=_PROBE_TIMEOUT_S)
        server = (resp.get("result") or {}).get("serverInfo") or {}
        if server.get("name"):
            _CAPS_CACHE = {"tvremix_key_present": True, "tvremix_working": True,
                           "tvremix_reason": None}
        else:
            _CAPS_CACHE = {"tvremix_key_present": True, "tvremix_working": False,
                           "tvremix_reason": "initialize returned no serverInfo"}
    except urllib.error.HTTPError as e:
        _CAPS_CACHE = {"tvremix_key_present": True, "tvremix_working": False,
                       "tvremix_reason": f"HTTP {e.code}"}
    except Exception as exc:  # noqa: BLE001
        _CAPS_CACHE = {"tvremix_key_present": True, "tvremix_working": False,
                       "tvremix_reason": type(exc).__name__}
    return _CAPS_CACHE
