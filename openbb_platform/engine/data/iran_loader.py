# engine/data/iran_loader.py
import pandas as pd
import logging
import http.client
import asyncio
import ssl

try:
    from tsetmc import Tsetmc # ← FIXED: Direct class import for v0.58.0 compatibility
    _HAS_TSETMC = True
except ImportError:
    _HAS_TSETMC = False

def _is_tsetmc_up(timeout=3) -> bool:
    """Refactored 2026: Uses HTTPS context and GET request to bypass strict TLS firewalls."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Host": "tsetmc.com" 
        }
        context = ssl._create_unverified_context()
        conn = http.client.HTTPSConnection("tsetmc.com", timeout=timeout, context=context)
        conn.request("GET", "/", headers=headers)
        res = conn.getresponse()
        return res.status < 400
    except Exception:
        return False

def load_iran_market_data(symbol: str, timeframe: str) -> pd.DataFrame:
    if not _HAS_TSETMC:
        logging.error(f"Cannot load {symbol}: tsetmc module not found.")
        return pd.DataFrame()

    if not _is_tsetmc_up():
        logging.warning(f"TSETMC Connectivity probe failed. Attempting direct library fetch for {symbol}...")

    clean_symbol = symbol.split('.')[0].upper()
    if clean_symbol in ["AYAR", "عیار"]:
        clean_symbol = "عیار"

    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def fetch():
            client = Tsetmc() # ← FIXED: Instance via direct import name
            return await client.get_price_history(clean_symbol)

        df = loop.run_until_complete(fetch())
        
        if df is None or df.empty:
            return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]
        if 'adj_close' in df.columns:
            df = df.rename(columns={'adj_close': 'close'})
        
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        df = df[required_cols]
        df.index = pd.to_datetime(df.index)
        
        if timeframe in ["1wk", "1W"]:
            df = df.resample('W-FRI').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
        elif timeframe in ["1mo", "1M"]:
            df = df.resample('ME').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
            
        return df.dropna()
    except Exception as e:
        logging.error(f"Iran Market Fetch Error ({symbol}): {str(e)}")
        return pd.DataFrame()