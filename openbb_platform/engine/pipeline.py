# engine/pipeline.py
"""
PIPELINE ORCHESTRATOR v1.0
Responsibility: Orchestrates Multi-Timeframe Deep Analysis and Teacher Reporting.
Pattern: Async Pipeline — 
"""

import asyncio
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

# SIGNAL 5: CONFIGURATION - Extracted from hardcoding
from openbb import obb

# Corrected Imports based on project structure
try:
    from engine.analysis.harmonics import HarmonicEngine
    from engine.analysis.elliott import ElliottEngine
except ImportError as e:
    logging.error(f"Dependency Error: Analysis engines not found. {e}")
    # Fallback placeholders for isolated testing if engines are missing
    class HarmonicEngine: 
        def detect(self, df): return []
    class ElliottEngine: 
        def audit_report(self, sym, data): return {"status": "Missing Engine"}

# <- NEW [Elliott Wave Engine wiring]: computed deterministic 5-3 detector.
#    Sourced decisions (see CLAUDE.md -> "Elliott Wave Domain"):
#    PATH A pivots (engine's own high/low detect_pivots) and min_swing_pct = None.
try:
    from engine.structure import elliott_wave as ew
except ImportError as _ew_exc:
    logging.error(f"Computed Elliott engine unavailable: {_ew_exc}")
    ew = None  # type: ignore[assignment]

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AnalysisPipeline:
    """
    Orchestrates the retrieval of historical data and the execution of 
    harmonic and Elliott wave analysis across multiple timeframes.
    """
    
    def __init__(self):
        self.harmonics = HarmonicEngine()
        self.timeframes = ["1h", "4h", "1d", "1W", "1M"]
        # Default lookbacks: Intraday (2 years), Daily+ (10 years)
        self.lookback_intraday = 730
        self.lookback_standard = 3650

    async def fetch_data(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """
        Fetches OHLCV data with deep history and interval resampling.
        SIGNAL 2: ERROR HANDLING - Includes guard against empty datasets.
        """
        data_stack: Dict[str, pd.DataFrame] = {}
        
        async def fetch_single(tf: str) -> Tuple[str, Optional[pd.DataFrame]]:
            try:
                is_intraday = tf in ["1h", "4h"]
                days = self.lookback_intraday if is_intraday else self.lookback_standard
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                
                # yfinance specific: 4h isn't native, fetch 1h and resample
                fetch_tf = "1h" if tf == "4h" else tf
                
                # SIGNAL 3: RESOURCE MANAGEMENT - obb handles connection pooling internally
                res = obb.equity.price.historical(
                    symbol=symbol, 
                    interval=fetch_tf, 
                    provider="yfinance", 
                    start_date=start_date
                )
                
                if res is None or not hasattr(res, 'to_df'):
                    return tf, None
                
                df = res.to_df()
                
                if df is None or df.empty:
                    logging.warning(f"No data returned for {symbol} on {tf}")
                    return tf, None
                
                # Standardize column names to lowercase for the engine
                df.columns = [c.lower() for c in df.columns]
                
                # Handle 4h resampling
                if tf == "4h":
                    df = df.resample('4h').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna()
                
                return tf, df

            except Exception as e:
                logging.error(f"Pipeline fetch error for {symbol} ({tf}): {e}")
                return tf, None

        # Execute fetches concurrently
        results = await asyncio.gather(*(fetch_single(tf) for tf in self.timeframes))
        return {tf: df for tf, df in results if df is not None}

    # ── NEW [Elliott Wave Engine wiring] ────────────────────────────────────
    # Run + JSON-serialize the computed Elliott engine. Additive: the legacy
    # ElliottEngine call in run_deep_analysis is preserved untouched.

    @staticmethod
    def _count_to_dict(count: Any, source: str, as_of: str) -> Optional[Dict[str, Any]]:
        """Serialize a WaveCount to plain JSON-safe types. Carries source + as_of."""
        if count is None:
            return None
        return {
            "count_type": count.count_type.value,
            "direction": count.direction.value,
            "current_wave": count.current_wave,
            "status": count.status.value,
            "guideline_score": count.guideline_score,
            "guideline_matches": list(count.guideline_matches),
            "atypical_notes": list(count.atypical_notes),
            "ratios": dict(count.ratios),
            "invalidation_level": count.invalidation_level,
            "invalidation_reason": count.invalidation_reason,
            "targets": dict(count.targets),
            "legs": [
                {"name": leg.name, "start_index": leg.start_index,
                 "end_index": leg.end_index, "start_price": leg.start_price,
                 "end_price": leg.end_price, "length": leg.length}
                for leg in count.legs
            ],
            "rule_checks": [
                {"rule_id": rc.rule_id, "passed": rc.passed,
                 "detail": rc.detail, "source": rc.source}
                for rc in count.rule_checks
            ],
            "source": source,
            "as_of": as_of,
        }

    @classmethod
    def _elliott_to_dict(cls, result: Any) -> Dict[str, Any]:
        """Serialize an ElliottResult. Pivots and counts each carry source + as_of."""
        return {
            "chart_label": result.chart_label,
            "no_count_reason": result.no_count_reason,
            "source": result.source,
            "as_of": result.as_of,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "pivots": [
                {"index": p.index, "label": p.label, "price": p.price,
                 "is_high": p.is_high, "source": result.source,
                 "as_of": result.as_of}
                for p in result.pivots
            ],
            "preferred": cls._count_to_dict(result.preferred, result.source, result.as_of),
            "alternate": cls._count_to_dict(result.alternate, result.source, result.as_of),
        }

    def _run_elliott(self, symbol: str, timeframe: str,
                     df: pd.DataFrame) -> Dict[str, Any]:
        """Run the computed Elliott engine on one timeframe's OHLC.

        PATH A: uses the engine's own high/low pivots. min_swing_pct is omitted
        (-> None) per the sourced decision in CLAUDE.md. Never raises — degrades
        to a no-count payload so the report is always well-formed.
        """
        try:
            labels = [str(idx) for idx in df.index]
            as_of = labels[-1] if labels else ""
            result = ew.analyze(
                df["high"].to_numpy(dtype=float),
                df["low"].to_numpy(dtype=float),
                df["close"].to_numpy(dtype=float),
                labels,
                symbol=symbol, timeframe=timeframe, as_of=as_of,
            )
            return self._elliott_to_dict(result)
        except Exception as exc:  # noqa: BLE001 — report, never crash the pipeline
            logging.error("Computed Elliott failed for %s (%s): %s",
                          symbol, timeframe, exc)
            return {
                "chart_label": "Elliott: NO VALID COUNT — engine error",
                "no_count_reason": f"engine error: {exc}",
                "source": "", "as_of": "", "symbol": symbol,
                "timeframe": timeframe, "pivots": [],
                "preferred": None, "alternate": None,
            }

    # ── NEW [Harmonic detect/scan gap fix] ──────────────────────────────────
    # The report loop expected self.harmonics.detect(df), but HarmonicEngine only
    # exposes .scan(prices). That getattr fallback silently returned [] -> the
    # pipeline always reported "0 patterns". This wires scan() to the same pivot
    # basis HarmonicEngine.scan() documents (swings.find_pivots +
    # enforce_alternation), and adapts the typed PatternResult objects into the
    # plain dicts the report rows consume. Additive; never raises.
    def _detect_harmonics(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect harmonic patterns for the report. Returns a list of dicts with
        keys: name, type (BULLISH/BEARISH), points, stop_loss, prz (None — the
        pipeline does not compute a confluence PRZ; that lives in the API's
        compute_prz_confluence). Degrades to [] on any failure."""
        try:
            # Prefer the documented scan(prices) contract.
            if hasattr(self.harmonics, "scan"):
                from engine.structure.swings import find_pivots, enforce_alternation
                pivots = enforce_alternation(find_pivots(df))
                prices = [float(p) for p in pivots["close"].tolist()]
                results = self.harmonics.scan(prices)
                out: List[Dict[str, Any]] = []
                for r in results:
                    out.append({
                        "name": getattr(r, "pattern_name", "Harmonic"),
                        "type": "BULLISH" if getattr(r, "is_bullish", False) else "BEARISH",
                        "points": list(getattr(r, "points", ()) or ()),
                        "stop_loss": getattr(r, "stop_loss", None),
                        "prz": None,
                    })
                return out
            # Back-compat: a stub/placeholder engine that exposes detect(df).
            detect_func = getattr(self.harmonics, "detect", None)
            if callable(detect_func):
                return detect_func(df) or []
        except Exception as exc:  # noqa: BLE001 — report, never crash the pipeline
            logging.error("Harmonic detection failed: %s", exc)
        return []

    async def run_deep_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        Executes full engine suite and generates the 7-section Teacher Report.
        SIGNAL 6: TESTABILITY - Logic separated from I/O.
        """
        market_data = await self.fetch_data(symbol)
        
        if not market_data:
            return {
                "success": False, 
                "error": f"Ticker '{symbol}' unavailable. Check connectivity or symbol validity."
            }

        reports = {}

        for tf, df in market_data.items():
            # 1. Harmonic Detection  # <- FIXED: was getattr(...,'detect') which never
            # existed on HarmonicEngine (only .scan); now routed through _detect_harmonics.
            harmonic_patterns = self._detect_harmonics(df)
            
            # 2. Elliott Structure
            engine_elliott = ElliottEngine()
            audit_func = getattr(engine_elliott, 'audit_report', lambda s, d: {"status": "N/A"})
            elliott_data = audit_func(symbol, {"df": df})

            # 2b. Computed Elliott Wave (engine/structure/elliott_wave.py)  # <- NEW
            ew_result = self._run_elliott(symbol, tf, df) if ew is not None else None
            ew_label = (ew_result["chart_label"] if ew_result
                        else "Elliott: engine unavailable")

            # 3. Formulate the 7-Section Report (Production Schema)
            reports[tf] = {
                "section_1_detection": f"Detected {len(harmonic_patterns)} patterns. Elliott(legacy): {elliott_data.get('label', 'N/A')}. {ew_label}",  # <- NEW: computed label appended
                "elliott": ew_result,  # <- NEW: computed chart_label + preferred/alternate + pivots (each w/ source + as_of)
                "section_2_significance": f"Structural liquidity analysis for {tf} interval.",
                "section_3_prz": [p.get('prz', 'Calculating...') for p in harmonic_patterns],
                "section_4_projections": "Fibonacci targets: 0.382, 0.618, 1.000",
                "section_5_invalidation": "Invalidation based on X-point breach or structural shift.",
                "section_6_confluence": "Confluence: RSI Overbought/Oversold + Wave Count.",
                "section_7_summary": {
                    "symbol": symbol,
                    "timeframe": tf,
                    "primary_pattern": harmonic_patterns[0]['name'] if harmonic_patterns else "None",
                    "bias": "BULLISH" if any(p.get('type') == 'BULLISH' for p in harmonic_patterns) else "NEUTRAL"
                },
                "metadata": {
                    "data_points": len(df),
                    "last_close": df['close'].iloc[-1] if not df.empty else None
                }
            }

        return {
            "success": True,
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "results": reports
        }

async def run_pipeline(symbol: str) -> Dict[str, Any]:
    """Helper entry point for external callers."""
    engine = AnalysisPipeline()
    return await engine.run_deep_analysis(symbol)