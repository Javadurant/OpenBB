# engine/search.py
from typing import List
import socket
import asyncio

try:
    import tsetmc
    _HAS_TSETMC = True
except ImportError:
    _HAS_TSETMC = False

try:
    from pytickersymbols import PyTickerSymbols
    _HAS_TICKER_LIB = True
except ImportError:
    _HAS_TICKER_LIB = False

def _is_tsetmc_up(timeout=1) -> bool:
    """Fast-fail connectivity check for modern TSETMC infrastructure."""
    try:
        # Targeting the modern CDN and Main site
        socket.create_connection(("tsetmc.com", 80), timeout=timeout)
        return True
    except (socket.timeout, socket.error):
        return False

# Module-level circuit breaker
_TSETMC_AVAILABLE = _is_tsetmc_up() if _HAS_TSETMC else False

def get_symbol_suggestions(search_query: str) -> List[str]:
    q = search_query.upper().strip() if search_query else ""
    
    # 1. Defaults & Gold Funds
    if not q:
        return ["BTC-USD", "AZA.ST", "AYAR.IR", "GC=F", "FOOLAD.IR"]

    suggestions = [q]

    # 2. Dynamic Iran Market Search (Gated by connectivity)
    if _HAS_TSETMC and _TSETMC_AVAILABLE:
        try:
            # tsetmc 0.32+ provides a sync wrapper for ticker lists
            all_iran_tickers = tsetmc.get_all_tickers_sync()
            for symbol, name in all_iran_tickers.items():
                if q in symbol.upper() or q in name:
                    suggestions.append(f"{symbol}.IR")
        except Exception:
            pass
    
    # Fallback/Direct check
    if q in "AYAR" or q in "عیار": 
        if "AYAR.IR" not in suggestions: suggestions.append("AYAR.IR")

    if not _HAS_TICKER_LIB:
        return [s for s in suggestions if s and " " not in s][:15]

    try:
        stock_data = PyTickerSymbols()
        for s in stock_data.get_all_stocks():
            ticker = s.get('symbol', '').upper()
            if q in ticker or q in s.get('name', '').upper():
                if any("OMX" in idx for idx in s.get('indices', [])) and "." not in ticker:
                    ticker = f"{ticker}.ST"
                if ticker not in suggestions: suggestions.append(ticker)
    except Exception:
        pass

    return [s for s in suggestions if s and " " not in s][:15]