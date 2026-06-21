# engine/pipeline.py
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
from openbb import obb
from engine.analysis.harmonics import HarmonicEngine 
from engine.analysis.elliott import ElliottEngine

class AnalysisPipeline:
    """NEW: Orchestrates Multi-Timeframe Deep Analysis and Teacher Reporting."""
    
    def __init__(self):
        self.harmonics = HarmonicEngine()
        self.timeframes = ["1h", "4h", "1d", "1W", "1M"]

    async def fetch_data(self, symbol: str) -> Dict[str, Any]:
        """Fetches OHLCV data with deep history and interval resampling."""
        data_stack = {}
        
        async def fetch_single(tf: str):
            try:
                is_intraday = tf in ["1h", "4h"]
                days_lookback = 730 if is_intraday else 3650 # ← FIXED: 10yr for daily per user request
                start_date = (datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')
                
                fetch_tf = "1h" if tf == "4h" else tf
                res = obb.equity.price.historical(symbol=symbol, interval=fetch_tf, provider="yfinance", start_date=start_date)
                
                # Check for empty response before conversion
                if res is None or not hasattr(res, 'to_df'):
                    return tf, None
                
                df = res.to_df()
                if df is None or df.empty: # ← ADDED: Guard against empty datasets (e.g., AYAR.IR)
                    return tf, None
                
                if tf == "4h":
                    # ← FIXED: Using '4h' (lowercase) to avoid Pandas FutureWarning
                    df = df.resample('4h').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna()
                
                return tf, df
            except Exception as e:
                print(f"Error fetching {tf}: {e}")
                return tf, None

        results = await asyncio.gather(*(fetch_single(tf) for tf in self.timeframes))
        data_stack = {tf: df for tf, df in results if df is not None}
        return data_stack

    async def run_deep_analysis(self, symbol: str) -> Dict[str, Any]:
        """Executes full engine suite and generates the 7-section Teacher Report."""
        market_data = await self.fetch_data(symbol)
        if not market_data:
            return {"success": False, "error": f"Ticker '{symbol}' not found or delisted (e.g. yfinance 404)."}

        reports = {}

        for tf, df in market_data.items():
            # 1. Harmonic Detection
            harmonic_patterns = self.harmonics.detect(df)
            
            # 2. Elliott Structure
            engine_elliott = ElliottEngine(symbol=symbol, timeframe=tf)
            elliott_data = engine_elliott.analyze(df) if hasattr(engine_elliott, 'analyze') else {"status": "Inconclusive"}

            # 3. Formulate the 7-Section Report
            report = {
                "df": df,
                "section_1_detection": f"Detected {len(harmonic_patterns)} patterns. Elliott Wave: {elliott_data.get('label', 'N/A')}",
                "section_2_significance": f"Patterns represent structural liquidity zones on {tf} interval.",
                "section_3_prz": [p.get('prz', 'Calculating...') for p in harmonic_patterns],
                "section_4_projections": "Targeting 0.382/0.618 Fib levels based on structure.",
                "section_5_invalidation": "Invalidated on price breach of structure X-points.",
                "section_6_confluence": "Cross-reference with RSI and Ichimoku Cloud boundaries.",
                "section_7_summary": {
                    "symbol": symbol,
                    "timeframe": tf,
                    "primary_pattern": harmonic_patterns[0]['name'] if harmonic_patterns else "None",
                    "bias": "BULLISH" if any(p['type'] == 'BULLISH' for p in harmonic_patterns) else "NEUTRAL"
                },
                "harmonics_raw": harmonic_patterns,
                "elliott_raw": elliott_data
            }
            reports[tf] = report

        return {
            "success": True,
            "symbol": symbol,
            "timeframes_analyzed": list(market_data.keys()),
            "results": reports
        }

async def run_pipeline(symbol: str, timeframe: str = "1d") -> Dict[str, Any]:
    engine = AnalysisPipeline()
    return await engine.run_deep_analysis(symbol)