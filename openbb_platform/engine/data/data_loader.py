# engine/data/data_loader.py
import pandas as pd
from openbb import obb
import datetime
import re
import logging

# FIX: Suppress yfinance and urllib3 noise at the logger level
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

def load_market_data(symbol: str, timeframe: str) -> pd.DataFrame:
    # 1. Pydantic-Compliant OpenBB v4 Intervals
    interval_map = {
        "1h": "1h", "4h": "1h", "1d": "1d", 
        "1w": "1W", "1wk": "1W", "weekly": "1W",
        "1m": "1M", "1mo": "1M", "monthly": "1M"
    }
    clean_interval = interval_map.get(timeframe.lower(), "1d")
    raw_symbol = symbol.upper().strip()

    # 2. Symbol Resolution
    alias_map = {
        "OMXS30": "^OMX", "XAUUSD": "GC=F", "GOLD": "GC=F", "EURUSD": "EURUSD=X",
        "BTC": "BTC-USD", "SPX": "^GSPC"
    }
    fetch_symbol = alias_map.get(raw_symbol, raw_symbol)

    # 3. Crypto Formatting
    if re.match(r"^[A-Z]{3,5}USD$", fetch_symbol) and "-" not in fetch_symbol:
        fetch_symbol = f"{fetch_symbol[:-3]}-USD"

    # 4. Dynamic Lookback Calculation (Increased for higher timeframes)
    lookback_days = 730 # Default 2 years
    if clean_interval == "1W": lookback_days = 1825 # 5 years
    if clean_interval == "1M": lookback_days = 3650 # 10 years

    try:
        res = obb.equity.price.historical(
            symbol=fetch_symbol, 
            interval=clean_interval, 
            provider="yfinance",
            start_date=(datetime.datetime.now() - datetime.timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        )
        
        df = res.to_df()
        if df is None or df.empty: return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()[~df.index.duplicated(keep='last')]

        if timeframe.lower() == "4h":
            df = df.resample('4h', label='right', closed='right').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()
            
        return df
    except Exception as e:
        logging.error(f"Data load error for {fetch_symbol} at {clean_interval}: {e}")
        return pd.DataFrame()