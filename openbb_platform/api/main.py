"""
api/main.py — FastAPI bridge: QuantEdge Python → SENTRIQ React
All 7 API keys wired via env_config.py + data_clients.py
"""
import sys
import os
import asyncio  # <- NEW [autoeval]: background ledger evaluator
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Path setup ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from env_config import cfg
from data_clients import fmp_get, av_get, tiingo_get, fred_get, ai_analyze
# <- FIXED [router-includes]: working tree reverted to a main.py missing these; re-added (additive, preserves inline handlers)
from .symbol_router import router as symbol_router
from .phase2_router import router as phase2_router
from .omnisearch_router import router as omnisearch_router
from .bonds_router import router as bonds_router
from .postmortem_router import router as postmortem_router
from .help_router import router as help_router  # <- NEW [HELP]: smart help + AI agent + ratings
from .backtest_router import router as backtest_router  # <- NEW [BACKTEST]: cached per-symbol Edge/Expectancy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SENTRIQ-API")

app = FastAPI(
    title="QuantEdge / SENTRIQ API",
    description="All 7 API keys unified. Every QuantEdge page available as REST.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "https://sentriq.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic models ───────────────────────────────────────────────────────
class SignalRequest(BaseModel):
    symbol: str
    timeframe: Optional[str] = "daily"

class AIRequest(BaseModel):
    query: str
    model: Optional[str] = "groq"

class StrategiesRequest(BaseModel):
    symbols: Optional[List[str]] = None

class ElliottRequest(BaseModel):
    symbol: str
    lookback: Optional[int] = 10

class SwedishRequest(BaseModel):
    symbol: str

class ScannerRequest(BaseModel):
    symbols: List[str]

class FMPRequest(BaseModel):
    endpoint: str
    params: Optional[Dict[str, Any]] = None

class FREDRequest(BaseModel):
    series_id: str
    start: Optional[str] = None
    end: Optional[str] = None

# ── Health ────────────────────────────────────────────────────────────────
# <- FIXED [router-includes]: mount the 5 routers so /api/symbol/* and /api/discover/* resolve (were 404)
app.include_router(symbol_router)
app.include_router(phase2_router)
app.include_router(omnisearch_router)
app.include_router(bonds_router)
app.include_router(postmortem_router)
app.include_router(help_router)  # <- NEW [HELP]
app.include_router(backtest_router)  # <- NEW [BACKTEST]: /api/symbol/{sym}/backtest (cached, async)


# <- NEW [autoeval]: trust-ledger background evaluator. Resolves PENDING setups
#    against subsequent daily bars so the published win-rate/expectancy stays
#    current without a manual ?evaluate=true call. Disable with LEDGER_AUTOEVAL=0.
_LEDGER_AUTOEVAL_INTERVAL_SEC = int(os.getenv("LEDGER_AUTOEVAL_INTERVAL_SEC", str(24 * 3600)))
_LEDGER_AUTOEVAL_WARMUP_SEC = int(os.getenv("LEDGER_AUTOEVAL_WARMUP_SEC", "25"))


async def _ledger_autoeval_loop() -> None:
    """Periodically resolve PENDING ledger entries (idempotent, look-ahead-safe)."""
    await asyncio.sleep(_LEDGER_AUTOEVAL_WARMUP_SEC)  # let server + providers warm
    while True:
        try:
            from .setup_ledger import evaluate_open_entries
            from .data_ingestion import service as _ingest
            res = await evaluate_open_entries(_ingest)
            logger.info("ledger auto-eval: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never let the loop die on a transient error
            logger.warning("ledger auto-eval iteration failed", exc_info=True)
        try:
            await asyncio.sleep(_LEDGER_AUTOEVAL_INTERVAL_SEC)
        except asyncio.CancelledError:
            raise


@app.on_event("startup")  # on_event is supported in this FastAPI; minimal/additive vs lifespan refactor
async def _start_ledger_autoeval() -> None:
    if os.getenv("LEDGER_AUTOEVAL", "1").strip().lower() in ("0", "false", "no", ""):
        logger.info("ledger auto-eval disabled via LEDGER_AUTOEVAL")
        return
    app.state.ledger_eval_task = asyncio.create_task(_ledger_autoeval_loop())
    logger.info("ledger auto-eval scheduled (warmup %ss, every %ss)",
                _LEDGER_AUTOEVAL_WARMUP_SEC, _LEDGER_AUTOEVAL_INTERVAL_SEC)


@app.on_event("shutdown")
async def _stop_ledger_autoeval() -> None:
    task = getattr(app.state, "ledger_eval_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# <- NEW [BACKTEST]: nightly pre-warm of the active basket so per-symbol Edge cards
#    are served from cache (compute is ~15-30s/symbol). Disable with BACKTEST_PREWARM=0.
@app.on_event("startup")
async def _start_backtest_prewarm() -> None:
    if os.getenv("BACKTEST_PREWARM", "1").strip().lower() in ("0", "false", "no", ""):
        logger.info("backtest pre-warm disabled via BACKTEST_PREWARM")
        return
    from .backtest_router import prewarm_loop
    app.state.backtest_prewarm_task = asyncio.create_task(prewarm_loop())
    logger.info("backtest pre-warm scheduled")


@app.on_event("shutdown")
async def _stop_backtest_prewarm() -> None:
    task = getattr(app.state, "backtest_prewarm_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


_STARTED_AT = __import__("time").time()


@app.get("/health")
@app.get("/api/health")
def health() -> Dict[str, Any]:
    import time as _t
    return {
        "status": "ok",
        "ok": True,
        "version": "3.3.0",
        "uptime_sec": int(_t.time() - _STARTED_AT),
        "keys": cfg.status(),
    }


@app.get("/api/ready")
def ready() -> Dict[str, Any]:
    """Readiness: are the modules behind Discover actually importable and are
    data providers configured? Never exposes secret values - booleans only.
    Local-dev reliability contract for the 'Failed to fetch' regression."""
    import os as _os
    import time as _t
    checks: Dict[str, Any] = {}
    try:
        from api import setup_scanner  # noqa: F401
        checks["scanner_importable"] = True
    except Exception as exc:  # noqa: BLE001
        checks["scanner_importable"] = False
        checks["scanner_error"] = str(exc)[:200]
    try:
        from api import setup_ledger as _sl
        checks["ledger_importable"] = True
        checks["ledger_file_exists"] = _os.path.exists(_sl._LEDGER_PATH)
    except Exception as exc:  # noqa: BLE001
        checks["ledger_importable"] = False
        checks["ledger_error"] = str(exc)[:200]
    try:
        from api.data_ingestion import service as _svc  # noqa: F401
        checks["data_ingestion_importable"] = True
    except Exception as exc:  # noqa: BLE001
        checks["data_ingestion_importable"] = False
        checks["ingestion_error"] = str(exc)[:200]
    checks["providers_configured"] = {
        "yfinance": True,                                  # no key needed
        "eodhd": bool(_os.getenv("EODHD_API_KEY", "").strip()),
        "fmp": bool(_os.getenv("FMP_API_KEY", "").strip()),
        "groq": bool(_os.getenv("GROQ_API_KEY", "").strip()),
    }
    # v3.5: FMP plan-gate capability (cached per process; booleans + HTTP
    # reason only, never the key). First call probes 3 tiny endpoints.
    try:
        from api.fmp_news import fmp_capabilities
        checks["fmp_capabilities"] = fmp_capabilities()
    except Exception as exc:  # noqa: BLE001
        checks["fmp_capabilities"] = {"error": str(exc)[:120]}
    git_commit = None
    try:
        import subprocess as _sp
        git_commit = _sp.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, timeout=3,
            cwd=_os.path.dirname(_os.path.dirname(__file__))).stdout.strip() or None
    except Exception:  # noqa: BLE001
        pass
    ok = bool(checks.get("scanner_importable") and checks.get("ledger_importable")
              and checks.get("data_ingestion_importable"))
    return {"ok": ok, "checks": checks, "uptime_sec": int(_t.time() - _STARTED_AT),
            "mode": _os.getenv("SENTRIQ_ENV", "dev"), "git_commit": git_commit,
            "version": "3.3.0"}

# ── Key status (never exposes values) ────────────────────────────────────
@app.get("/api/keys/status")
def keys_status() -> Dict[str, Any]:
    return {"status": "ok", "keys": cfg.status()}

# ── AI Insights (Groq / OpenAI / Anthropic with fallback) ─────────────────
@app.post("/api/ai_insights")
def api_ai_insights(request: AIRequest) -> Dict[str, Any]:
    try:
        result = ai_analyze(request.query, model=request.model or "groq")
        return {"status": "ok", "query": request.query, "insights": result}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# ── Market Data (yfinance + Tiingo fallback) ──────────────────────────────
@app.get("/api/market/{symbol}")
def api_market(symbol: str) -> Dict[str, Any]:
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="6mo")
        if not hist.empty:
            hist.columns = [c.lower() for c in hist.columns]
            recent = hist.tail(30).reset_index()
            return {"status": "ok", "symbol": symbol, "source": "yfinance",
                    "candles": recent.to_dict(orient="records")}
    except Exception:
        pass

    # Tiingo fallback
    if cfg.TIINGO_API_KEY:
        try:
            data = tiingo_get(f"/tiingo/daily/{symbol}/prices", startDate="2024-01-01")
            return {"status": "ok", "symbol": symbol, "source": "tiingo", "candles": data}
        except Exception as e:
            logger.warning(f"Tiingo fallback failed for {symbol}: {e}")

    raise HTTPException(status_code=404, detail=f"No data for {symbol}")

# ── FMP: Company profile, financials, analyst ratings ─────────────────────
@app.post("/api/fmp")
def api_fmp(request: FMPRequest) -> Dict[str, Any]:
    if not cfg.FMP_API_KEY:
        raise HTTPException(status_code=503, detail="FMP_API_KEY not configured")
    try:
        data = fmp_get(request.endpoint, **(request.params or {}))
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fmp/profile/{symbol}")
def api_fmp_profile(symbol: str) -> Dict[str, Any]:
    if not cfg.FMP_API_KEY:
        raise HTTPException(status_code=503, detail="FMP_API_KEY not configured")
    try:
        return {"status": "ok", "data": fmp_get(f"/v3/profile/{symbol}")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fmp/financials/{symbol}")
def api_fmp_financials(symbol: str) -> Dict[str, Any]:
    if not cfg.FMP_API_KEY:
        raise HTTPException(status_code=503, detail="FMP_API_KEY not configured")
    try:
        income = fmp_get(f"/v3/income-statement/{symbol}", limit=4)
        balance = fmp_get(f"/v3/balance-sheet-statement/{symbol}", limit=4)
        cashflow = fmp_get(f"/v3/cash-flow-statement/{symbol}", limit=4)
        return {"status": "ok", "income": income, "balance": balance, "cashflow": cashflow}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fmp/ratings/{symbol}")
def api_fmp_ratings(symbol: str) -> Dict[str, Any]:
    if not cfg.FMP_API_KEY:
        raise HTTPException(status_code=503, detail="FMP_API_KEY not configured")
    try:
        return {"status": "ok", "data": fmp_get(f"/v3/analyst-stock-recommendations/{symbol}")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Alpha Vantage: live quotes, technical indicators ──────────────────────
@app.get("/api/av/quote/{symbol}")
def api_av_quote(symbol: str) -> Dict[str, Any]:
    if not cfg.ALPHA_VANTAGE_API_KEY:
        raise HTTPException(status_code=503, detail="ALPHA_VANTAGE_API_KEY not configured")
    try:
        data = av_get(function="GLOBAL_QUOTE", symbol=symbol)
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/av/rsi/{symbol}")
def api_av_rsi(symbol: str, interval: str = "daily", period: int = 14) -> Dict[str, Any]:
    if not cfg.ALPHA_VANTAGE_API_KEY:
        raise HTTPException(status_code=503, detail="ALPHA_VANTAGE_API_KEY not configured")
    try:
        data = av_get(function="RSI", symbol=symbol, interval=interval,
                      time_period=period, series_type="close")
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── FRED: Economic data (GDP, inflation, rates, unemployment) ──────────────
@app.post("/api/fred")
def api_fred(request: FREDRequest) -> Dict[str, Any]:
    if not cfg.FRED_API_KEY:
        raise HTTPException(status_code=503, detail="FRED_API_KEY not configured")
    try:
        params: Dict[str, Any] = {"series_id": request.series_id}
        if request.start:
            params["observation_start"] = request.start
        if request.end:
            params["observation_end"] = request.end
        data = fred_get("series/observations", **params)
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fred/{series_id}")
def api_fred_series(series_id: str) -> Dict[str, Any]:
    if not cfg.FRED_API_KEY:
        raise HTTPException(status_code=503, detail="FRED_API_KEY not configured")
    try:
        return {"status": "ok", "data": fred_get("series/observations", series_id=series_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Tiingo: institutional-grade OHLCV + fundamentals ─────────────────────
@app.get("/api/tiingo/{symbol}")
def api_tiingo(symbol: str) -> Dict[str, Any]:
    if not cfg.TIINGO_API_KEY:
        raise HTTPException(status_code=503, detail="TIINGO_API_KEY not configured")
    try:
        data = tiingo_get(f"/tiingo/daily/{symbol}/prices",
                          startDate="2024-01-01", resampleFreq="daily")
        return {"status": "ok", "symbol": symbol, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Trading Signals ───────────────────────────────────────────────────────
@app.post("/api/signals")
def api_signals(request: SignalRequest) -> Dict[str, Any]:
    try:
        from pages.ai_trading_agent import get_signals
        result = get_signals(request.symbol, request.timeframe)
        return result
    except ImportError:
        return {"status": "ok", "symbol": request.symbol,
                "message": "Signal engine loading..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Elliott Wave ──────────────────────────────────────────────────────────
@app.post("/api/elliott")
def api_elliott(request: ElliottRequest) -> Dict[str, Any]:
    try:
        import yfinance as yf
        t = yf.Ticker(request.symbol)
        hist = t.history(period="1y")
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {request.symbol}")
        return {"status": "ok", "symbol": request.symbol.upper(),
                "message": "Elliott Wave analysis ready"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Swedish Analysis ──────────────────────────────────────────────────────
@app.post("/api/swedish")
def api_swedish(request: SwedishRequest) -> Dict[str, Any]:
    symbol = request.symbol
    if ".ST" not in symbol.upper():
        symbol = f"{symbol.upper()}.ST"
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="1mo")
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        close  = float(hist["Close"].iloc[-1])
        prev   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
        change = ((close / prev) - 1.0) * 100.0 if prev > 1e-10 else 0.0
        info   = t.info
        return {
            "status": "ok", "symbol": symbol, "currency": "SEK",
            "price": round(close, 2), "change_pct": round(change, 2),
            "name": info.get("longName", symbol),
            "sector": info.get("sector", "N/A"),
            "market": "OMX Stockholm",
            "isk_eligible": True, "kf_eligible": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Strategies ────────────────────────────────────────────────────────────
@app.post("/api/strategies")
def api_strategies(request: StrategiesRequest) -> Dict[str, Any]:
    try:
        from pages.trading_intelligence_hub_v2 import get_strategies
        return get_strategies(request.symbols)
    except ImportError:
        return {"status": "ok", "message": "Strategy engine loading..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Scanner ───────────────────────────────────────────────────────────────
@app.post("/api/scanner")
def api_scanner(request: ScannerRequest) -> Dict[str, Any]:
    import yfinance as yf
    results = []
    for sym in request.symbols[:20]:
        try:
            t = yf.Ticker(sym)
            h = t.history(period="3mo")
            if len(h) >= 2:
                ret = ((float(h["Close"].iloc[-1]) / float(h["Close"].iloc[0])) - 1) * 100
                results.append({"symbol": sym.upper(), "return_3m_pct": round(ret, 2),
                                 "trend": "up" if ret > 0 else "down"})
        except Exception:
            pass
    results.sort(key=lambda x: x["return_3m_pct"], reverse=True)
    return {"status": "ok", "count": len(results), "results": results}

# ── Harmonics ─────────────────────────────────────────────────────────────
@app.get("/api/harmonics/{symbol}")
def api_harmonics(symbol: str) -> Dict[str, Any]:
    return {"status": "ok", "symbol": symbol.upper(), "patterns": [],
            "message": "Harmonic scan complete"}

# ── Export to NotebookLM ──────────────────────────────────────────────────
@app.post("/api/export/notebooklm")
def export_notebooklm(request: dict) -> Dict[str, Any]:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from notebooklm_exporter import NotebookLMExporter
        exporter = NotebookLMExporter()
        path = exporter.export_weekly_digest(request.get("analyses", []))
        return {"status": "ok", "file": str(path),
                "url": "https://notebooklm.google.com",
                "message": f"Ready: {path.name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
