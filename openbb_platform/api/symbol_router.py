"""
api/symbol_router.py — calls REAL engine functions in pages/ai_trading_agent.py
Returns structured JSON for: technical, fundamental, psychological, AI, risk.

EVERY function is the SAME function the Streamlit pages use.
Zero quality loss vs. the original QuantEdge terminal.
"""
from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Suppress Streamlit context warnings when calling functions outside Streamlit
warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.CRITICAL)

# Path setup
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger("symbol_router")
router = APIRouter(prefix="/api/symbol", tags=["symbol"])

# ── Lazy imports of the real engines ─────────────────────────────────────
def _import_engines():
    """Lazy import — keeps router file fast to load."""
    from pages.ai_trading_agent import (
        _fetch_info,
        _fetch_institutional_proxy,
        _fetch_macro_proxies,
        _fetch_ohlcv,
        _fetch_ohlcv_tf,
        analyse_elliott_waves,
        classify_macro_regime,
        compute_all_indicators,
        compute_ichimoku,
        compute_prz_confluence,
        compute_zigzag,
        scan_all_harmonic_patterns,
        harmonic_near_miss,
        compute_proximity_readouts,
        compute_andrews_pitchfork,
        score_institutional,
        score_sentiment_via_groq,
    )
    return locals()

# ── Helpers ──────────────────────────────────────────────────────────────
def _safe(value: Any, default: Any = None) -> Any:
    """Convert pandas/numpy values to JSON-safe primitives."""
    if value is None: return default
    try:
        import math
        if hasattr(value, "item"): value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return default
        return value
    except Exception:
        return default

def _round(value: Any, ndigits: int = 4, default: Any = None) -> Any:
    v = _safe(value, default)
    if isinstance(v, (int, float)):
        try: return round(v, ndigits)
        except Exception: return default
    return default

# <- NEW [Elliott Wave Engine wiring]: computed deterministic 5-3 detector runner.
#    Sourced decisions (see openbb_platform/CLAUDE.md -> "Elliott Wave Domain"):
#    PATH A pivots (engine's own high/low detect_pivots) + min_swing_pct = None.
#    Additive — does NOT replace the legacy analyse_elliott_waves payload.
def _computed_elliott_payload(symbol: str, df: Any,
                              x_labels: Optional[List[str]] = None,
                              timeframe: str = "1d") -> Dict[str, Any]:
    """Run engine/structure/elliott_wave.analyze on full high/low/close and return
    a JSON-safe dict: chart_label + preferred/alternate + pivots + legs, each
    carrying source + as_of. ``x_labels`` (one per df row, e.g. chart-aligned
    date strings) is used as the engine's labels so pivots and leg endpoints map
    1:1 onto the chart's time axis for drawing. Never raises — degrades to a
    well-formed no-count payload."""
    no_count = {
        "chart_label": "Elliott: NO VALID COUNT — engine error",
        "no_count_reason": "", "source": "", "as_of": "",
        "pivots": [], "preferred": None, "alternate": None, "developing": None,
        "signal": {"bias": "NONE", "kind": "none", "tradeable": False,
                   "stop": None, "rationale": "No completed count."},
    }
    eng_labels = x_labels if x_labels is not None else [str(idx) for idx in df.index]
    try:
        from engine.structure import elliott_wave as ew
    except ImportError as exc:
        logger.error("computed Elliott engine unavailable: %s", exc)
        return {**no_count, "chart_label": "Elliott: engine unavailable",
                "no_count_reason": str(exc)}

    def _lbl(i: int) -> Optional[str]:
        return eng_labels[i] if 0 <= i < len(eng_labels) else None

    def _count(c: Any, source: str, as_of: str) -> Optional[Dict[str, Any]]:
        if c is None:
            return None
        return {
            "count_type": c.count_type.value, "direction": c.direction.value,
            "current_wave": c.current_wave, "status": c.status.value,
            "guideline_score": c.guideline_score,
            "guideline_matches": list(c.guideline_matches),
            "atypical_notes": list(c.atypical_notes), "ratios": dict(c.ratios),
            "invalidation_level": c.invalidation_level,
            "invalidation_reason": c.invalidation_reason, "targets": dict(c.targets),
            "legs": [{"name": l.name, "start_index": l.start_index,
                      "end_index": l.end_index, "start_price": l.start_price,
                      "end_price": l.end_price, "length": l.length,
                      "start_label": _lbl(l.start_index),   # <- chart-aligned X for drawing
                      "end_label": _lbl(l.end_index)}
                     for l in c.legs],
            "rule_checks": [{"rule_id": rc.rule_id, "passed": rc.passed,
                             "detail": rc.detail, "source": rc.source}
                            for rc in c.rule_checks],
            "source": source, "as_of": as_of,
        }

    try:
        as_of = eng_labels[-1] if eng_labels else ""
        res = ew.analyze(
            df["high"].to_numpy(dtype=float), df["low"].to_numpy(dtype=float),
            df["close"].to_numpy(dtype=float), eng_labels,
            symbol=symbol, timeframe=timeframe, as_of=as_of,
        )  # min_swing_pct omitted -> None (sourced decision)
        return {
            "chart_label": res.chart_label, "no_count_reason": res.no_count_reason,
            "source": res.source, "as_of": res.as_of,
            "pivots": [{"index": p.index, "label": p.label, "price": p.price,
                        "is_high": p.is_high, "source": res.source, "as_of": res.as_of}
                       for p in res.pivots],
            "preferred": _count(res.preferred, res.source, res.as_of),
            "alternate": _count(res.alternate, res.source, res.as_of),
            "developing": res.developing,   # <- NEW: nearest/in-progress projection to the last bar
            "signal": ew.signal_for_count(res.preferred),   # <- NEW: backtest-gated trade signal
        }
    except Exception as exc:  # noqa: BLE001 — report, never break the endpoint
        logger.exception("computed Elliott failed for %s", symbol)
        return {**no_count, "no_count_reason": f"engine error: {exc}"}


def _ew_cite_phrase(block: Dict[str, Any]) -> str:
    """One-line citation of the COMPUTED preferred (+ alternate) count for the
    AI narrative / Ask layer. Uses engine output only — never the .docx."""
    pref = (block or {}).get("preferred")
    if not pref:
        reason = (block or {}).get("no_count_reason") or "insufficient structure"
        return f"no valid Elliott count ({reason})"
    try:
        txt = (f"{pref['count_type']} {pref['current_wave']} ({pref['status']}), "
               f"{pref['guideline_score']} guideline(s) satisfied, invalidation "
               f"{float(pref['invalidation_level']):.2f}")
    except Exception:  # noqa: BLE001
        txt = f"{pref.get('count_type', 'count')} {pref.get('current_wave', '')}"
    alt = (block or {}).get("alternate")
    if alt:
        txt += f"; alternate {alt.get('count_type')} (score {alt.get('guideline_score')})"
    return txt


# <- NEW: infer trading currency from the symbol suffix (Yahoo exchange suffix) or info.
_CCY_BY_SUFFIX = {
    "ST": "SEK", "OL": "NOK", "CO": "DKK", "HE": "EUR", "IC": "ISK",
    "DE": "EUR", "F": "EUR", "PA": "EUR", "AS": "EUR", "BR": "EUR", "MI": "EUR",
    "MC": "EUR", "LS": "EUR", "VI": "EUR", "L": "GBP", "IL": "GBP", "SW": "CHF",
    "TO": "CAD", "V": "CAD", "HK": "HKD", "T": "JPY", "AX": "AUD", "NZ": "NZD",
    "SI": "SGD", "KS": "KRW", "KQ": "KRW", "TW": "TWD", "BO": "INR", "NS": "INR",
    "SA": "BRL", "MX": "MXN", "JO": "ZAR", "TA": "ILS", "SR": "SAR", "AD": "AED",
}


def _currency_for(symbol: str, info: dict) -> str:
    """Trading currency: prefer provider info, else infer from the .SUFFIX, else USD."""
    c = (info or {}).get("currency")
    if c:
        return str(c).upper()
    if "." in symbol:
        return _CCY_BY_SUFFIX.get(symbol.rsplit(".", 1)[-1].upper(), "USD")
    return "USD"


# ── Request models ───────────────────────────────────────────────────────
class SymbolRequest(BaseModel):
    symbol: str
    years:  int | None = 2

# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/{symbol}/overview")
def overview(symbol: str) -> dict[str, Any]:
    """One-shot: price, change, sector, market cap, basic identity."""
    try:
        eng = _import_engines()
        df   = eng["_fetch_ohlcv"](symbol, years=1)
        info = eng["_fetch_info"](symbol)
        if df.empty: raise HTTPException(404, f"No data for {symbol}")
        close = df["close"]
        last  = float(close.iloc[-1])
        prev  = float(close.iloc[-2]) if len(close) > 1 else last
        chg_pct = ((last / prev) - 1.0) * 100.0 if prev > 1e-10 else 0.0
        return {
            "status":      "ok",
            "symbol":      symbol.upper(),
            "name":        info.get("name") or symbol,
            "sector":      info.get("sector",   "—"),
            "industry":    info.get("industry", "—"),
            "country":     info.get("country",  "—"),
            "currency":    _currency_for(symbol, info),   # <- FIXED: infer ccy (e.g. .ST -> SEK), not hardcoded USD
            "exchange":    info.get("exchange", "—"),
            "price":       _round(last, 2),
            "change_pct":  _round(chg_pct, 2),
            "market_cap":  _safe(info.get("market_cap")),
            "high_52w":    _safe(info.get("52w_high")),
            "low_52w":     _safe(info.get("52w_low")),
            "beta":        _safe(info.get("beta")),
            "shares_out":  _safe(info.get("shares_out")),
            "summary":     (info.get("description") or "")[:4000],  # <- FIXED: full About (was cut at 500)
            "candles":     [
                {"date": str(idx)[:10], "open": _round(row["open"]), "high": _round(row["high"]),
                 "low": _round(row["low"]), "close": _round(row["close"]), "volume": _safe(row["volume"])}
                for idx, row in df.tail(120).iterrows()
            ],
        }
    except HTTPException: raise
    except Exception as e:
        logger.exception("overview %s", symbol)
        raise HTTPException(500, f"overview error: {e}")


@router.get("/{symbol}/technical")
def technical(symbol: str) -> dict[str, Any]:
    """Technical analysis: harmonics + Elliott Wave + Ichimoku + indicators + PRZ."""
    try:
        eng = _import_engines()
        df = eng["_fetch_ohlcv"](symbol, years=2)
        if df.empty: raise HTTPException(404, f"No data for {symbol}")
        close = df["close"]
        last_price = float(close.iloc[-1])

        # Real engine calls
        swings    = eng["compute_zigzag"](close)
        elliott   = eng["analyse_elliott_waves"](swings)
        elliott_computed = _computed_elliott_payload(  # <- NEW: computed 5-3 engine (chart-aligned dates)
            symbol, df, x_labels=[str(i)[:10] for i in df.index], timeframe="daily")
        harmonics = eng["scan_all_harmonic_patterns"](swings)
        ichimoku  = eng["compute_ichimoku"](df)
        indicators= eng["compute_all_indicators"](df)
        prz       = eng["compute_prz_confluence"](df, swings, harmonics, ichimoku, indicators)

        # <- NEW [PROX]: SEPARATE 'nearest-to / leaning' readout for the non-harmonic engines
        prox = eng["compute_proximity_readouts"](
            last_price,
            indicators.get("rsi_val"), indicators.get("macd_val"),
            indicators.get("macd_sig"), indicators.get("macd_hist"),
            indicators.get("bb_upper"), indicators.get("bb_lower"),
            ichimoku.get("price_vs_cloud", "UNKNOWN"), ichimoku.get("cloud_top"),
            ichimoku.get("cloud_bot"), ichimoku.get("tk_cross", "NEUTRAL"),
            elliott.get("wave_phase", "NONE"),
        )
        pf = eng["compute_andrews_pitchfork"](swings, df)
        if pf:
            _pos = pf["position"]
            _lean = ("bullish" if _pos in ("above upper rail", "upper half")
                     else "bearish" if _pos in ("below lower rail", "lower half") else "neutral")
            prox.append({
                "name": "Andrews Pitchfork", "state": _pos, "lean": _lean, "to": "median line",
                "note": f"Price {pf['last_price']:.2f} is in the {_pos}; median line at {pf['median']:.2f}, "
                        f"rails {pf['lower']:.2f}\u2013{pf['upper']:.2f}.",
            })

        # Strip non-JSON-safe pandas series before returning
        def clean(d: dict) -> dict:
            out = {}
            for k, v in (d or {}).items():
                if k == "series" or k == "swings_idx": continue
                out[k] = _safe(v)
            return out

        return {
            "status":     "ok",
            "symbol":     symbol.upper(),
            "last_price": _round(last_price, 2),
            "harmonics":  [clean(p) for p in harmonics[:10]],
            "elliott":    {**clean(elliott),                       # legacy fields preserved (wave_phase, conf_pts, …)
                           "chart_label": elliott_computed["chart_label"],  # <- NEW: computed label for chart overlay
                           "computed": elliott_computed},          # <- NEW: full computed block (preferred/alternate/pivots)
            "ichimoku":   {k: _safe(v) for k, v in (ichimoku or {}).items() if k != "series"},
            "indicators": {
                "rsi":          _round(indicators.get("rsi_val"), 2),
                "macd":         _round(indicators.get("macd_val"), 4),
                "macd_signal":  _round(indicators.get("macd_sig"), 4),
                "macd_hist":    _round(indicators.get("macd_hist"), 4),
                "bb_upper":     _round(indicators.get("bb_upper"), 2),
                "bb_lower":     _round(indicators.get("bb_lower"), 2),
                "conf_pts":     _safe(indicators.get("conf_pts"), 0),
            },
            "prz":        clean(prz),
            "proximity":  prox,                 # <- NEW [PROX]: nearest-to / leaning per engine
            "pitchfork":  pf,                   # <- NEW [PROX]: Andrews Pitchfork levels (or null)
            "swings_count": len(swings),
        }
    except HTTPException: raise
    except Exception as e:
        logger.exception("technical %s", symbol)
        raise HTTPException(500, f"technical error: {e}")


@router.get("/{symbol}/chart")
def chart(symbol: str, tf: str = "daily") -> dict[str, Any]:
    """Multi-timeframe candles + harmonic patterns (pivot dates + concise outcome),  # <- NEW [H-MTF]
    plus the nearest near-miss when none confirm. tf in {daily, weekly, monthly}."""
    try:
        eng = _import_engines()
        timeframe = (tf or "daily").lower()
        if timeframe not in ("daily", "weekly", "monthly", "hourly"):   # <- H-MTF-2: + hourly
            timeframe = "daily"
        df = eng["_fetch_ohlcv_tf"](symbol, timeframe)
        if df is None or df.empty:
            raise HTTPException(404, f"No {timeframe} data for {symbol}")
        close      = df["close"]
        last_price = float(close.iloc[-1])
        idx_list   = list(df.index)

        def _d2s(i: Any) -> Optional[str]:
            try:
                return str(idx_list[int(i)])[:10]
            except Exception:
                return None

        swings    = eng["compute_zigzag"](close)
        harmonics = eng["scan_all_harmonic_patterns"](swings)
        found     = [h for h in harmonics if h.get("found")]

        def _outcome(h: dict) -> str:
            d   = h.get("direction")
            prz = f'{h.get("prz_low")}\u2013{h.get("prz_high")}'
            if d == "bullish":
                return f"Watch PRZ {prz} for a bullish (long) reversal."
            if d == "bearish":
                return f"Watch PRZ {prz} for a bearish (short) reversal."
            return f"Watch PRZ {prz} for a reversal."

        # <- NEW [DRAW]: index->price map from swings so harmonic polylines are drawable
        swing_price = {int(s[0]): float(s[1]) for s in swings}
        hres = []
        for h in found:
            pid   = h.get("pivot_idx") or []
            dates = [_d2s(i) for i in pid] if pid else []
            prices = [swing_price.get(int(i)) for i in pid] if pid else []  # <- NEW [DRAW]
            hres.append({
                **{k: _safe(v) for k, v in h.items() if k not in ("series", "swings_idx", "pivot_idx")},
                "pivot_dates": dates,
                "pivot_prices": prices,   # <- NEW [DRAW]: per-pivot prices for the on-chart polyline
                "from_date":   dates[0]  if dates else None,
                "to_date":     dates[-1] if dates else None,
                "outcome":     _outcome(h),
            })

        near = None
        if not found:
            nm = eng["harmonic_near_miss"](swings)
            if nm:
                pid = nm.get("pivot_idx") or []
                nmd = [_d2s(i) for i in pid] if pid else []
                nmp = [swing_price.get(int(i)) for i in pid] if pid else []  # <- NEW [DRAW]
                near = {
                    **{k: _safe(v) for k, v in nm.items() if k != "pivot_idx"},
                    "pivot_dates": nmd,    # <- NEW [DRAW]: drawable near-miss polyline X
                    "pivot_prices": nmp,   # <- NEW [DRAW]: drawable near-miss polyline Y
                    "from_date": nmd[0]  if nmd else None,
                    "to_date":   nmd[-1] if nmd else None,
                }

        recent  = df.tail(500)
        # <- H-MTF-2: hourly emits a full ISO timestamp (chart needs intraday time); D/W/M stay yyyy-mm-dd
        def _cdate(i: Any) -> str:
            try:
                return i.isoformat() if timeframe == "hourly" else str(i)[:10]
            except Exception:
                return str(i)[:10]
        candles = [
            {"date": _cdate(i), "open": _round(r["open"]), "high": _round(r["high"]),
             "low": _round(r["low"]), "close": _round(r["close"]), "volume": _safe(r["volume"])}
            for i, r in recent.iterrows()
        ]

        # <- NEW [PF-DRAW]: tf-aware Andrews Pitchfork drawable lines (match the displayed timeframe)
        pf = eng["compute_andrews_pitchfork"](swings, df)
        pf_draw = None
        if pf and pf.get("lines_idx"):
            def _mkline(line: list) -> list:
                return [{"date": _cdate(idx_list[int(x)]), "value": v} for x, v in line]
            li = pf["lines_idx"]
            pf_draw = {"median": _mkline(li["median"]), "rail1": _mkline(li["rail1"]),
                       "rail2": _mkline(li["rail2"]), "position": pf.get("position")}

        # <- NEW [DRAW]: tf-aware computed Elliott so wave overlays follow the timeframe switch.
        #    Labels are chart-aligned (_cdate) so pivots/legs map onto the candle time axis.
        elliott_chart = _computed_elliott_payload(
            symbol, df, x_labels=[_cdate(i) for i in idx_list], timeframe=timeframe)

        return {
            "status":       "ok",
            "symbol":       symbol.upper(),
            "timeframe":    timeframe,
            "last_price":   _round(last_price, 2),
            "candles":      candles,
            "harmonics":    hres,
            "near_miss":    near,
            "pitchfork":    pf_draw,            # <- NEW [PF-DRAW]: drawable pitchfork lines (or null)
            # <- NEW [DRAW]: same shape as /technical's elliott — chart_label + nested computed block
            "elliott":      {"chart_label": elliott_chart["chart_label"], "computed": elliott_chart},
            "swings_count": len(swings),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chart %s", symbol)
        raise HTTPException(500, f"chart error: {e}")


@router.get("/{symbol}/fundamental")
def fundamental(symbol: str) -> dict[str, Any]:
    """Fundamentals using the engine's normalized info schema."""
    try:
        eng = _import_engines()
        info = eng["_fetch_info"](symbol)
        if not info or not info.get("name"):
            raise HTTPException(404, f"No fundamentals for {symbol}")
        return {
            "status":     "ok",
            "symbol":     symbol.upper(),
            "name":       info.get("name"),
            "valuation":  {
                "pe_trailing":     _safe(info.get("pe_ratio")),
                "pe_forward":      _safe(info.get("forward_pe")),
                "beta":            _safe(info.get("beta")),
                "market_cap":      _safe(info.get("market_cap")),
            },
            "profitability": {
                "profit_margin":   _safe(info.get("profit_margin")),
                "roe":             _safe(info.get("roe")),
                "ebitda":          _safe(info.get("ebitda")),
                "free_cashflow":   _safe(info.get("free_cashflow")),
            },
            "growth": {
                "revenue_growth":  _safe(info.get("revenue_growth")),
                "earnings_growth": _safe(info.get("earnings_growth")),
            },
            "balance_sheet": {
                "total_cash":      _safe(info.get("total_cash")),
                "total_debt":      _safe(info.get("total_debt")),
                "shares_out":      _safe(info.get("shares_out")),
            },
            "dividend": {
                "yield":           _safe(info.get("dividend_yield")),
                "payout_ratio":    _safe(info.get("payout_ratio")),
            },
            "analyst": {
                "recommendation":  info.get("recommendation") or "—",
                "target_mean":     _safe(info.get("target_mean")),
                "short_ratio":     _safe(info.get("short_ratio")),
            },
            "description":         (info.get("description") or "")[:1500],
        }
    except HTTPException: raise
    except Exception as e:
        logger.exception("fundamental %s", symbol)
        raise HTTPException(500, f"fundamental error: {e}")


@router.get("/{symbol}/psychology")
def psychology(symbol: str) -> dict[str, Any]:
    """Sentiment + macro regime + institutional flow."""
    try:
        eng = _import_engines()
        info = eng["_fetch_info"](symbol)
        company_name = info.get("name") or symbol
        macro = eng["_fetch_macro_proxies"]()
        quad, macro_score = eng["classify_macro_regime"](macro)
        inst = eng["_fetch_institutional_proxy"](symbol)
        inst_score = eng["score_institutional"](inst)
        # Sentiment via Groq (optional — only if API key present)
        sentiment = None
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                s_score, s_pts = eng["score_sentiment_via_groq"](symbol, company_name, groq_key)
                sentiment = {"score": _round(s_score, 2), "points": _safe(s_pts)}
            except Exception as e:
                logger.warning("groq sentiment %s: %s", symbol, e)
                sentiment = {"score": None, "error": "Groq sentiment unavailable"}
        return {
            "status":  "ok", "symbol": symbol.upper(),
            "macro":   {
                "regime":      quad,
                "score":       _safe(macro_score),
                "spy_trend":   _round(macro.get("spy_trend_pct"), 2),
                "vix_level":   _round(macro.get("vix"), 2),
                "yield_curve": _round(macro.get("yield_spread"), 2),
                "dollar":      _round(macro.get("dxy"), 2),
            },
            "sentiment":     sentiment,
            "institutional": {
                "score":     _safe(inst_score),
                "ownership": _round(inst.get("inst_pct"), 2),
                "insider":   _round(inst.get("insider_pct"), 2),
                "short":     _round(inst.get("short_pct"), 2),
            },
        }
    except Exception as e:
        logger.exception("psychology %s", symbol)
        raise HTTPException(500, f"psychology error: {e}")


@router.get("/{symbol}/ai-narrative")
def ai_narrative(symbol: str) -> dict[str, Any]:
    """One-paragraph plain-English summary via Groq, synthesizing all engines."""
    try:
        eng = _import_engines()
        # FIXED [H-CONSISTENCY]: match the Technical tab's 2-year window. A 1-year
        # window silently dropped any harmonic whose X pivot was >1y old (e.g.
        # VOLV-B.ST Bearish Deep Crab, X=2025-05-13), so the Overview narrative said
        # "no harmonic patterns" while the Technical tab listed two. Same df here ->
        # the narrative now sees the SAME harmonics / RSI / trend as /technical.
        df    = eng["_fetch_ohlcv"](symbol, years=2)
        info  = eng["_fetch_info"](symbol)
        if df.empty: raise HTTPException(404, f"No data for {symbol}")
        close = df["close"]
        swings    = eng["compute_zigzag"](close)
        elliott   = eng["analyse_elliott_waves"](swings)
        harmonics = eng["scan_all_harmonic_patterns"](swings)
        ichi      = eng["compute_ichimoku"](df)
        ind       = eng["compute_all_indicators"](df)

        # Build a compact prompt from real engine outputs
        company = info.get("name") or symbol
        last    = float(close.iloc[-1])
        wave    = elliott.get("wave_phase", "—")
        # <- NEW [EW]: cite the COMPUTED preferred/alternate counts (engine, EWI-sourced),
        #    not the legacy .docx phase. Legacy phase kept parenthetically for continuity.
        ew_cited = _ew_cite_phrase(_computed_elliott_payload(symbol, df))

        # <- FIXED [H-CONSISTENCY]: surface harmonics the way /chart does — confirmed
        #    patterns as name + direction + PRZ, and when NONE confirm, the nearest
        #    near-miss (user: "even if nearest harmonic pattern is found I want it in
        #    the overview"). The narrative must never claim "no harmonic patterns"
        #    when one is listed below.
        def _hfmt(h: dict) -> str:
            d  = (h.get("direction") or "").strip()
            lo, hi = h.get("prz_low"), h.get("prz_high")
            prz = (f"{lo:g}–{hi:g}"
                   if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else "n/a")
            return f"{h.get('pattern')}{(' ' + d) if d else ''} (PRZ {prz})"
        found_harmonics = [h for h in harmonics if h.get("found")] if harmonics else []
        h_count = len(found_harmonics)
        if found_harmonics:
            h_first = found_harmonics[0].get("pattern")
            harm_summary = f"{h_count} confirmed: " + "; ".join(_hfmt(h) for h in found_harmonics[:3])
        else:
            h_first = None
            nm = eng["harmonic_near_miss"](swings)
            if nm:
                lo, hi = nm.get("prz_low"), nm.get("prz_high")
                prz = (f"{lo:g}–{hi:g}"
                       if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else "n/a")
                d = (nm.get("direction") or "").strip()
                harm_summary = (f"0 confirmed; nearest near-miss {nm.get('pattern')}"
                                f"{(' ' + d) if d else ''} (projected PRZ {prz}, miss {nm.get('miss')})")
            else:
                harm_summary = "0 confirmed; no near-miss within tolerance"
        rsi     = ind.get("rsi_val")
        rsi_str = f"{rsi:.1f}" if rsi is not None else "—"   # pre-format for both narrative branches
        trend   = ichi.get("trend", "—")

        # Use Groq via the existing data_clients.ai_analyze
        groq_key = os.getenv("GROQ_API_KEY", "")
        if not groq_key:
            return {"status": "ok", "symbol": symbol.upper(),
                    "narrative": (f"{company} ({symbol.upper()}) trades at ${last:.2f}. "
                                  f"Trend: {trend}. Elliott (computed, EWI): {ew_cited} "
                                  f"(legacy phase: {wave}). "
                                  f"Harmonic patterns — {harm_summary}. "
                                  f"RSI: {rsi_str}. "
                                  "(Configure GROQ_API_KEY for AI narrative)"),
                    "ai_powered": False,
                    "harmonic_summary": harm_summary, "harmonic_count": h_count}

        from data_clients import ai_analyze
        prompt = (f"Write ONE paragraph (max 4 sentences) for {company} ({symbol}) at "
                  f"${last:.2f}. Trend (Ichimoku): {trend}. "
                  f"Elliott Wave (computed per Elliott Wave Principle rules): {ew_cited}. "
                  f"Cite this computed wave count; do not invent a different one. "
                  f"Harmonic patterns — {harm_summary}. "
                  f"State the harmonic finding exactly as given (name, direction, PRZ); "
                  f"if a near-miss is listed, report it as the nearest harmonic pattern. "
                  f"NEVER claim there are no harmonic patterns when one is listed above. "
                  f"RSI: {rsi_str}. Be specific, professional, no hedging.")
        try:
            narrative = ai_analyze(prompt, model="groq")
        except Exception as e:
            narrative = f"AI narrative unavailable: {e}"
        return {"status": "ok", "symbol": symbol.upper(),
                "narrative": narrative, "ai_powered": True,
                "harmonic_summary": harm_summary, "harmonic_count": h_count}
    except HTTPException: raise
    except Exception as e:
        logger.exception("ai_narrative %s", symbol)
        raise HTTPException(500, f"ai_narrative error: {e}")


@router.get("/{symbol}/risk")
def risk(symbol: str) -> dict[str, Any]:
    """Risk: volatility, drawdown, suggested stops, position sizing context."""
    try:
        eng = _import_engines()
        df = eng["_fetch_ohlcv"](symbol, years=1)
        if df.empty: raise HTTPException(404, f"No data for {symbol}")
        close = df["close"]
        # 20-day annualized volatility
        returns = close.pct_change().dropna()
        vol_20d = float(returns.tail(20).std() * (252 ** 0.5)) if len(returns) >= 20 else None
        # Max drawdown over last year
        rolling_max = close.cummax()
        drawdown    = (close - rolling_max) / rolling_max
        max_dd      = float(drawdown.min())
        # ATR-based stop
        high, low = df["high"], df["low"]
        prev_close = close.shift(1)
        tr = (high - low).combine((high - prev_close).abs(), max).combine((low - prev_close).abs(), max)
        atr_14 = float(tr.tail(14).mean())
        last   = float(close.iloc[-1])
        return {
            "status": "ok", "symbol": symbol.upper(),
            "last_price":         _round(last, 2),
            "volatility_20d_ann": _round(vol_20d, 4),
            "max_drawdown_1y":    _round(max_dd, 4),
            "atr_14":             _round(atr_14, 2),
            "suggested_stops": {
                "atr_2x":  _round(last - 2 * atr_14, 2),
                "atr_3x":  _round(last - 3 * atr_14, 2),
                "pct_5":   _round(last * 0.95, 2),
                "pct_10":  _round(last * 0.90, 2),
            },
            "suggested_targets": {
                "rr_1to1": _round(last + 2 * atr_14, 2),
                "rr_1to2": _round(last + 4 * atr_14, 2),
                "rr_1to3": _round(last + 6 * atr_14, 2),
            },
        }
    except HTTPException: raise
    except Exception as e:
        logger.exception("risk %s", symbol)
        raise HTTPException(500, f"risk error: {e}")


# ── Search by company name ──────────────────────────────────────────────
@router.get("/search/{query}")
def search(query: str) -> dict[str, Any]:
    """Resolve a company name OR ticker. yfinance.Search primary, ticker info fallback."""
    results: list[dict[str, Any]] = []
    # 1) yfinance.Search — best for company names ("Apple" → AAPL)
    try:
        import yfinance as yf
        s = yf.Search(query, max_results=10)
        for q in (s.quotes or []):
            sym = q.get("symbol")
            if not sym: continue
            name = q.get("longname") or q.get("shortname") or sym
            results.append({
                "ticker":   sym,
                "name":     name,
                "exchange": q.get("exchDisp") or q.get("exchange") or "—",
                "type":     q.get("typeDisp") or q.get("quoteType") or "EQUITY",
                "currency": q.get("currency") or "",
                "source":   "yfinance",
            })
    except Exception as e:
        logger.warning("yfinance.Search %s: %s", query, e)
    # 2) Direct ticker fallback if name-search returned nothing
    if not results:
        try:
            import yfinance as yf
            t = yf.Ticker(query.upper())
            info = t.info or {}
            if info.get("symbol"):
                results.append({
                    "ticker":   info.get("symbol"),
                    "name":     info.get("longName") or info.get("shortName"),
                    "exchange": info.get("exchange"),
                    "type":     info.get("quoteType","EQUITY"),
                    "currency": info.get("currency",""),
                    "source":   "yfinance-direct",
                })
        except Exception as e:
            logger.warning("yfinance direct %s: %s", query, e)
    return {"status": "ok", "query": query, "count": len(results), "results": results}


# ═══════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL FRAMEWORKS — 10 Investor Lenses (Phase 1 Deliverable #1)
# Added May 15, 2026 — wires the AITab "Institutional Frameworks" buttons.
# ═══════════════════════════════════════════════════════════════════════════
import re as _re_fw

from .institutional_frameworks import (
    INSTITUTIONAL_FRAMEWORKS,
    build_framework_prompt,
    get_framework,
    list_frameworks,
)


@router.get("/frameworks")
def frameworks_list() -> dict[str, Any]:
    """List all 10 institutional frameworks (for the AITab buttons)."""
    out = []
    for key, fw in INSTITUTIONAL_FRAMEWORKS.items():
        out.append({
            "key":           key,
            "display_name":  fw["display_name"],
            "key_lens":      fw["key_lens"],
            "horizon":       fw["horizon"],
            "key_principle": fw.get("key_principle", ""),
            "source_book":   fw.get("source_book", ""),
            "source_url":    fw.get("source_url", ""),
        })
    return {"status": "ok", "count": len(out), "frameworks": out}


@router.get("/{symbol}/framework/{name}")
def framework_analysis(symbol: str, name: str) -> dict[str, Any]:
    """
    Analyze a symbol through a specific institutional investor's published lens.

    Path params:
        symbol : ticker (yfinance-style, e.g. AAPL or VOLV-B.ST)
        name   : framework key (must be in INSTITUTIONAL_FRAMEWORKS whitelist)

    Returns:
        { status, symbol, framework, display_name, key_lens, horizon,
          verdict, score, thesis, key_risk, ai_powered }
    """
    # ── 1) Validate framework (whitelist — prevents prompt injection) ──────
    if name not in list_frameworks():
        raise HTTPException(
            status_code=404,
            detail=f"Unknown framework: '{name}'. Valid: {list_frameworks()}",
        )

    fw = get_framework(name)

    try:
        # ── 2) Pull live facts from existing engines ────────────────────
        eng    = _import_engines()
        df     = eng["_fetch_ohlcv"](symbol, years=1)
        info   = eng["_fetch_info"](symbol)
        if df.empty:
            raise HTTPException(404, f"No data for {symbol}")

        close   = df["close"]
        price   = float(close.iloc[-1])
        company = info.get("name") or symbol.upper()

        ind = eng["compute_all_indicators"](df) or {}
        ich = eng["compute_ichimoku"](df) or {}

        # ── 3) Build framework-grounded fact sheet ──────────────────────
        # All facts come from real engine outputs — none invented.
        facts: dict[str, str] = {}

        # Valuation facts (from yfinance .info via _fetch_info)
        pe    = info.get("pe_trailing") or info.get("pe_forward")
        roe   = info.get("roe")
        mcap  = info.get("market_cap")
        rev_g = info.get("revenue_growth")
        eps_g = info.get("earnings_growth")
        fcf   = info.get("free_cashflow")
        beta  = info.get("beta")
        div   = info.get("dividend_yield")

        if pe is not None:
            facts["P/E"] = f"{pe:.1f}"
        if roe is not None:
            facts["ROE"] = f"{roe * 100:.0f}%" if abs(roe) < 5 else f"{roe:.1f}"
        if mcap:
            facts["Market Cap"] = f"${mcap / 1e9:.1f}B"
        if rev_g is not None:
            facts["Revenue Growth"] = f"{rev_g * 100:.1f}%"
        if eps_g is not None:
            facts["Earnings Growth"] = f"{eps_g * 100:.1f}%"
        if fcf:
            facts["Free Cash Flow"] = f"${fcf / 1e9:.1f}B"
        if beta is not None:
            facts["Beta"] = f"{beta:.2f}"
        if div is not None:
            facts["Dividend Yield"] = f"{div:.2f}%" if div < 1 else f"{div / 100:.2f}%"

        # Technical facts (from engines)
        rsi = ind.get("rsi_val")
        if rsi is not None:
            label = "overbought" if rsi >= 70 else ("oversold" if rsi <= 30 else "neutral")
            facts["RSI(14)"] = f"{rsi:.1f} ({label})"
        trend = ich.get("trend") or ich.get("price_vs_cloud")
        if trend:
            facts["Ichimoku Trend"] = str(trend)

        # Sector context
        sector = info.get("sector")
        if sector:
            facts["Sector"] = str(sector)

        # ── 4) Submit to Groq via existing ai_analyze ───────────────────
        prompt = build_framework_prompt(
            name=name,
            company_name=str(company),
            ticker=symbol.upper(),
            price=price,
            facts=facts,
        )

        ai_powered = False
        raw = ""
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from data_clients import ai_analyze
                raw = ai_analyze(prompt, model="groq", max_tokens=512)
                ai_powered = True
            except Exception as e:
                logger.warning("framework_analysis groq error %s/%s: %s", symbol, name, e)
                raw = ""

        # ── 5) Parse the structured response ────────────────────────────
        def _grab(pattern: str, default: str = "") -> str:
            m = _re_fw.search(pattern, raw, _re_fw.IGNORECASE | _re_fw.DOTALL)
            return m.group(1).strip() if m else default

        verdict_raw = _grab(r"VERDICT:\s*(BUY|HOLD|SELL|AVOID)").upper() or "HOLD"
        if verdict_raw not in {"BUY", "HOLD", "SELL", "AVOID"}:
            verdict_raw = "HOLD"

        score_str = _grab(r"SCORE:\s*(\d{1,3})")
        try:
            score_val = max(0, min(100, int(score_str))) if score_str else 50
        except ValueError:
            score_val = 50

        thesis = _grab(r"THESIS:\s*(.+?)(?=KEY_RISK:|$)", default="").strip() or (
            f"AI narrative unavailable. {fw['display_name']}'s lens applied to "
            f"{company} ({symbol.upper()}) at ${price:.2f}: "
            f"{fw['key_lens']}. Configure GROQ_API_KEY for full analysis."
        )
        key_risk = _grab(r"KEY_RISK:\s*(.+?)$", default="").strip() or "—"

        return {
            "status":        "ok",
            "symbol":        symbol.upper(),
            "framework":     name,
            "display_name":  fw["display_name"],
            "key_lens":      fw["key_lens"],
            "horizon":       fw["horizon"],
            "verdict":       verdict_raw,
            "score":         score_val,
            "thesis":        thesis,
            "key_risk":      key_risk,
            "ai_powered":    ai_powered,
            "facts_used":    facts,
            # Phase 2 Deliverable B: framework citations
            "key_principle": fw.get("key_principle", ""),
            "source_book":   fw.get("source_book", ""),
            "source_url":    fw.get("source_url", ""),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("framework_analysis %s/%s", symbol, name)
        raise HTTPException(500, f"framework error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# AI CHAIRMAN — synthesizes all 10 investor verdicts into ONE dated/priced call.
# Pattern: LLM Council (Karpathy) — members deliberate, the Chairman decides.
# ═══════════════════════════════════════════════════════════════════════════
def _symbol_facts(symbol: str) -> tuple[str, float, dict]:
    """Fetch once and build the shared fact sheet used by every council member."""
    eng = _import_engines()
    df = eng["_fetch_ohlcv"](symbol, years=1)
    info = eng["_fetch_info"](symbol)
    if df is None or df.empty:
        raise HTTPException(404, f"No data for {symbol}")
    price = float(df["close"].iloc[-1])
    company = info.get("name") or symbol.upper()
    ind = eng["compute_all_indicators"](df) or {}
    ich = eng["compute_ichimoku"](df) or {}
    facts: dict[str, str] = {}
    pe = info.get("pe_trailing") or info.get("pe_forward")
    for k, v, f in (("P/E", pe, lambda x: f"{x:.1f}"),
                    ("ROE", info.get("roe"), lambda x: f"{x*100:.0f}%" if abs(x) < 5 else f"{x:.1f}"),
                    ("Market Cap", info.get("market_cap"), lambda x: f"${x/1e9:.1f}B"),
                    ("Revenue Growth", info.get("revenue_growth"), lambda x: f"{x*100:.1f}%"),
                    ("Earnings Growth", info.get("earnings_growth"), lambda x: f"{x*100:.1f}%"),
                    ("Beta", info.get("beta"), lambda x: f"{x:.2f}")):
        if v is not None:
            try: facts[k] = f(v)
            except Exception: pass
    rsi = ind.get("rsi_val")
    if rsi is not None:
        facts["RSI(14)"] = f"{rsi:.1f}"
    if ich.get("trend"):
        facts["Ichimoku Trend"] = str(ich.get("trend"))
    if info.get("sector"):
        facts["Sector"] = str(info.get("sector"))
    return str(company), price, facts


def _parse_fw(raw: str) -> tuple[str, int, str]:
    """Parse a member response into (verdict, score, thesis)."""
    def g(p, d=""):
        m = _re_fw.search(p, raw, _re_fw.IGNORECASE | _re_fw.DOTALL)
        return m.group(1).strip() if m else d
    v = (g(r"VERDICT:\s*(BUY|HOLD|SELL|AVOID)").upper() or "HOLD")
    try: s = max(0, min(100, int(g(r"SCORE:\s*(\d{1,3})") or "50")))
    except ValueError: s = 50
    return v, s, (g(r"THESIS:\s*(.+?)(?=KEY_RISK:|$)") or "")


# Minimum reward:risk a directional trade must clear before it can ship.
# Below this, the Risk gate VETOES the trade -> stance downgrades to WATCH.
_MIN_RR = 1.5


def _psych_read(final: str, tally: dict) -> str:
    """One-line crowd/psychology read derived from the board spread."""
    return (f"Board lean {final}: BUY {tally['BUY']} / SELL {tally['SELL']} / "
            f"HOLD {tally['HOLD']}, avg conviction {tally['avg_score']}/100.")


def _advisor_plan(verdict: str, score: int, price: float, atr: float,
                  horizon: str, liq_shares: Optional[int]) -> dict[str, Any]:
    """Per-advisor trade line so EACH of the 10 advisors states an exact entry price,
    a target, a stop, a holding timeframe, and the volume their conviction implies
    (user demand: 'specify what volume their opinion is based on and the timeframe for
    buying and selling … the target must be specified'). Honest: this is the trade the
    advisor's framework + conviction score imply, not a promise. Target distance and
    R:R scale with THAT advisor's own score, so a low-conviction BUY targets less."""
    v = (verdict or "HOLD").upper()
    if v == "HOLD" or atr <= 0 or price <= 0:
        return {"stance": "HOLD", "entry": None, "stop": None, "target": None,
                "expected_rr": None, "horizon": horizon or "—",
                "size_lean": "No position — stands aside."}
    long = v == "BUY"
    move = atr * (2 + 4 * score / 100)            # target distance ~ advisor conviction
    rr   = round(1 + 2 * score / 100, 2)
    if long:
        entry, stop, target = round(price, 2), round(price - 2 * atr, 2), round(price + move, 2)
    else:                                          # SELL / AVOID -> short side, mirrored
        entry, stop, target = round(price, 2), round(price + 2 * atr, 2), round(price - move, 2)
    pct = max(10, min(100, int(round(score))))     # conviction-weighted volume lean
    if liq_shares:
        size_lean = (f"conviction {score}/100 → up to ~{int(liq_shares * pct / 100):,} sh "
                     f"({pct}% of liquidity cap)")
    else:
        size_lean = f"conviction {score}/100 → {pct}% of max position"
    return {"stance": ("BUY" if long else "SELL"), "entry": entry, "stop": stop,
            "target": target, "expected_rr": rr, "horizon": horizon or "swing",
            "size_lean": size_lean}


def _trade_ticket(symbol: str, price: float, final: str, conviction: int,
                  tally: dict) -> dict[str, Any]:
    """Turn the Chairman's directional call into an executable trade ticket.

    Honest by construction:
      * entry/stop are ATR(14)-based (same engine as /risk).
      * expected move (hence R:R) scales with board conviction:
            R:R = 1 + 2 * conviction/100   (range 1.0 .. 3.0)
        so low-conviction setups genuinely fail the gate.
      * SIZE is a *basis* (per-share risk + sizing formula), never a fabricated
        share count — the server cannot know the user's account size.
      * Risk VETO: if final is BUY/SELL and R:R < _MIN_RR, stance becomes WATCH
        and entry is the conditional price where R:R first clears the gate.
    """
    try:
        eng = _import_engines()
        df = eng["_fetch_ohlcv"](symbol, years=1)
        if df.empty:
            return {"available": False, "reason": "no OHLCV"}
        high, low, close = df["high"], df["low"], df["close"]
        prev = close.shift(1)
        tr = (high - low).combine((high - prev).abs(), max).combine((low - prev).abs(), max)
        atr = float(tr.tail(14).mean())
        last = float(close.iloc[-1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("trade_ticket %s: %s", symbol, exc)
        return {"available": False, "reason": "ticket data unavailable"}

    atr_pct = (atr / last * 100) if last else 0.0
    rr = round(1 + 2 * conviction / 100, 2)            # conviction-linked R:R
    expected_move = atr * (2 + 4 * conviction / 100)   # move / 2ATR == rr
    per_share_risk = round(2 * atr, 2)

    # <- NEW [TICKET-DATES]: a concrete entry date + an estimated target/exit date,
    #    so the AI Analysis states an exact sell-by date (user demand) rather than a
    #    vague "1–3 weeks". target_date is the midpoint of the swing horizon and is
    #    labelled an estimate — ATR-projected moves have no guaranteed hit date.
    from datetime import datetime, timedelta, timezone
    _today = datetime.now(timezone.utc).date()
    target_days = 14                                   # midpoint of the ~1–3 week swing horizon
    entry_date  = _today.isoformat()
    target_date = (_today + timedelta(days=target_days)).isoformat()

    # <- NEW [TICKET-VOLUME]: a concrete share count is ALWAYS shown via the liquidity
    #    ceiling (1% of 20-day average $ volume). The server can't know account size,
    #    so risk-based sizing stays a formula, but this gives a precise fillable volume.
    liq_shares, liq_note = None, "Liquidity volume unavailable."
    try:
        if "volume" in df.columns:
            advol = float((close * df["volume"]).tail(20).mean())   # 20-day avg $ volume
            if advol > 0 and last > 0:
                cap = 0.01 * advol
                liq_shares = int(cap // last)
                liq_note = (f"≤ {liq_shares:,} shares (~${cap:,.0f}) stays within 1% of 20-day "
                            f"avg $ volume — fillable without moving the tape.")
    except Exception:  # noqa: BLE001
        pass

    if final == "HOLD":  # no trade
        return {
            "available": True, "stance": "HOLD", "direction": "HOLD",
            "entry": None, "stop": None, "target": None, "expected_rr": None,
            "timeframe": "—", "per_share_risk": None,
            "entry_date": entry_date, "target_date": None, "target_days": None,
            "liquidity_max_shares": None,
            "liquidity_note": "No position — liquidity sizing not applicable.",
            "size_basis": "No trade: board is balanced. No position to size.",
            "psychology_read": _psych_read(final, tally),
            "risk_read": f"ATR(14) ${round(atr, 2)} (~{atr_pct:.1f}% of price).",
            "vetoed": False, "min_rr": _MIN_RR, "watch_trigger": None,
            "method": "HOLD = stand aside; no directional ticket.",
        }

    long = final == "BUY"
    if long:
        entry, stop = round(last, 2), round(last - 2 * atr, 2)
        target = round(last + expected_move, 2)
    else:  # SELL (short) — mirror
        entry, stop = round(last, 2), round(last + 2 * atr, 2)
        target = round(last - expected_move, 2)

    vetoed = rr < _MIN_RR
    # Conditional entry where R:R first clears the gate (same stop & target):
    #   e* = (target + k·stop) / (1 + k)
    watch_entry = round((target + _MIN_RR * stop) / (1 + _MIN_RR), 2)
    stance = "WATCH" if vetoed else final

    return {
        "available": True,
        "stance": stance,                       # executable stance (may be WATCH)
        "direction": final,                     # board's directional bias
        "entry": watch_entry if vetoed else entry,
        "entry_window": ("conditional — only if price reaches this level (R:R gate)"
                         if vetoed else "market / next session"),
        "target": target,
        "target_window": "swing horizon (see timeframe)",
        "target_date": target_date,             # <- NEW: estimated sell-by date
        "target_days": target_days,
        "entry_date": entry_date,               # <- NEW: trade-on date
        "stop": stop,
        "stop_reason": "2×ATR(14) beyond entry — structure invalidation",
        "timeframe": "swing · ~1–3 weeks",
        "expected_rr": rr,
        "per_share_risk": per_share_risk,
        "liquidity_max_shares": liq_shares,     # <- NEW: concrete fillable volume
        "liquidity_note": liq_note,
        "size_basis": (f"Liquidity ceiling: {liq_note} "
                       f"Risk-based: per-share risk ${per_share_risk}; "
                       f"shares = floor(0.01 × account ÷ ${per_share_risk}) at 1% account risk "
                       f"(provide account size for the exact risk-based figure)."),
        "psychology_read": _psych_read(final, tally),
        "risk_read": (f"ATR(14) ${round(atr, 2)} (~{atr_pct:.1f}% of price); "
                      f"2×ATR stop ${stop}; R:R {rr} vs gate {_MIN_RR}."),
        "vetoed": vetoed,
        "min_rr": _MIN_RR,
        "watch_trigger": watch_entry if vetoed else None,
        "method": ("R:R = 1 + 2·conviction/100; entry = last; stop = 2×ATR(14); "
                   "target = entry ± ATR·(2 + 4·conviction/100). "
                   "Veto -> WATCH when R:R < gate."),
    }


@router.get("/{symbol}/chairman")
def chairman(symbol: str) -> dict[str, Any]:
    """AI Chairman: runs all 10 institutional lenses, then issues ONE final,
    timestamped, priced BUY / SELL / HOLD by synthesizing the board's verdicts.
    Members run in parallel. Falls back to a transparent majority vote with no GROQ key.
    """
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    try:
        company, price, facts = _symbol_facts(symbol)
        names = list_frameworks()
        groq_key = os.getenv("GROQ_API_KEY", "")

        # <- NEW [ADVISOR-PLAN]: ATR(14) + a liquidity ceiling, computed ONCE and shared
        #    by every advisor's per-line plan (entry/stop/target/volume). Best-effort —
        #    if it fails, advisors still return verdict + thesis (plan degrades to HOLD).
        _atr, _liq_shares = 0.0, None
        try:
            _eng = _import_engines()
            _df = _eng["_fetch_ohlcv"](symbol, years=1)
            if not _df.empty:
                _h, _l, _c = _df["high"], _df["low"], _df["close"]
                _p = _c.shift(1)
                _tr = (_h - _l).combine((_h - _p).abs(), max).combine((_l - _p).abs(), max)
                _atr = float(_tr.tail(14).mean())
                if "volume" in _df.columns:
                    _av = float((_c * _df["volume"]).tail(20).mean())
                    _last = float(_c.iloc[-1])
                    if _av > 0 and _last > 0:
                        _liq_shares = int((0.01 * _av) // _last)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chairman atr/liq %s: %s", symbol, exc)

        def _one(name: str) -> dict:
            fw = get_framework(name)
            verdict, score, thesis = "HOLD", 50, ""
            if groq_key:
                try:
                    from data_clients import ai_analyze
                    raw = ai_analyze(build_framework_prompt(
                        name=name, company_name=company, ticker=symbol.upper(),
                        price=price, facts=facts), model="groq", max_tokens=320)
                    verdict, score, thesis = _parse_fw(raw)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("chairman member %s/%s: %s", symbol, name, exc)
            horizon = fw.get("horizon", "—")
            return {"key": name, "display_name": fw["display_name"], "verdict": verdict,
                    "score": score, "thesis": thesis.strip()[:280],
                    "horizon": horizon,
                    "plan": _advisor_plan(verdict, score, price, _atr, horizon, _liq_shares)}

        with ThreadPoolExecutor(max_workers=10) as ex:
            board = list(ex.map(_one, names))

        # Tally — AVOID counts with SELL (both = do-not-own).
        buys = sum(1 for b in board if b["verdict"] == "BUY")
        sells = sum(1 for b in board if b["verdict"] in ("SELL", "AVOID"))
        holds = sum(1 for b in board if b["verdict"] == "HOLD")
        avg_score = round(sum(b["score"] for b in board) / len(board), 1) if board else 50.0
        tally = {"BUY": buys, "SELL": sells, "HOLD": holds, "avg_score": avg_score}

        final, conviction, rationale = _chair_synthesis(
            company, symbol, price, board, tally, groq_key)

        # Executable trade ticket (entry/stop/target/R:R/size-basis) + risk veto.
        ticket = _trade_ticket(symbol, price, final, conviction, tally)

        now = datetime.now(timezone.utc)
        return {
            "status": "ok", "symbol": symbol.upper(), "company": company,
            "price": _round(price, 4), "decision_at_utc": now.isoformat(timespec="seconds"),
            "decision_date": now.strftime("%Y-%m-%d"), "decision_time": now.strftime("%H:%M:%S UTC"),
            "final_signal": final, "conviction": conviction, "rationale": rationale,
            "ticket": ticket,
            "tally": tally, "board": board, "members": len(board),
            "ai_powered": bool(groq_key),
            "disclaimer": ("Synthesis of 10 published investor frameworks applied to live "
                           "facts. Educational, not financial advice. Markets carry risk."),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chairman %s", symbol)
        raise HTTPException(500, f"chairman error: {e}")


def _chair_synthesis(company: str, symbol: str, price: float, board: list,
                     tally: dict, groq_key: str) -> tuple[str, int, str]:
    """Chairman's final call. AI synthesis when GROQ is set; else a transparent
    majority vote (BUY if buys lead, SELL if sells lead, else HOLD)."""
    if groq_key:
        try:
            from data_clients import ai_analyze
            lines = "\n".join(f"- {b['display_name']}: {b['verdict']} (score {b['score']}) — "
                              f"{b['thesis'][:160]}" for b in board)
            prompt = (
                f"You are the Investment Committee CHAIRMAN. Ten legendary investors have each "
                f"issued a verdict on {company} ({symbol.upper()}) at ${price:.2f}.\n\n"
                f"BOARD VERDICTS:\n{lines}\n\n"
                f"Tally — BUY:{tally['BUY']} SELL/AVOID:{tally['SELL']} HOLD:{tally['HOLD']}, "
                f"avg conviction {tally['avg_score']}/100.\n\n"
                f"Weigh agreement, conviction, and which lenses matter most for THIS company. "
                f"Resolve disagreement professionally. Reply EXACTLY:\n"
                f"FINAL: BUY | SELL | HOLD\nCONVICTION: <0-100>\n"
                f"RATIONALE: <2-3 sentences citing the decisive members>")
            raw = ai_analyze(prompt, model="groq", max_tokens=400)
            def g(p, d=""):
                m = _re_fw.search(p, raw, _re_fw.IGNORECASE | _re_fw.DOTALL)
                return m.group(1).strip() if m else d
            final = (g(r"FINAL:\s*(BUY|SELL|HOLD)").upper() or "")
            if final in ("BUY", "SELL", "HOLD"):
                try: conv = max(0, min(100, int(g(r"CONVICTION:\s*(\d{1,3})") or "60")))
                except ValueError: conv = 60
                rat = g(r"RATIONALE:\s*(.+?)$") or "Chairman synthesis of the board."
                return final, conv, rat.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("chairman synthesis %s: %s", symbol, exc)
    # Deterministic fallback (no AI): majority vote.
    b, s, h = tally["BUY"], tally["SELL"], tally["HOLD"]
    final = "BUY" if b > s and b >= h else "SELL" if s > b and s >= h else "HOLD"
    conv = int(round(100 * max(b, s, h) / max(1, (b + s + h))))
    return final, conv, (f"Majority vote of the board (BUY {b} / SELL {s} / HOLD {h}). "
                         f"Configure GROQ_API_KEY for full Chairman synthesis.")


@router.get("/{symbol}/whatif")
def whatif(symbol: str, days: int = 7,
           qty: float | None = None, notional: float | None = None) -> dict[str, Any]:
    """What-if mode: the USER fixes size and horizon ('buy X of SYMBOL, hold N days');
    the engine scores THAT trade rather than choosing one.

    Honest technicals — no fabricated numbers:
      * drift  = mean daily return over the last 60 sessions (capped ±0.5%/day).
      * band   = ATR(14) · √days  (a 1-sigma horizon move).
      * exits  = base (drift only), bull (+band), bear (−band).
      * verdict from edge vs band; right-size check vs 20-day $ liquidity.
    """
    try:
        days = max(1, min(int(days), 365))
        eng = _import_engines()
        df = eng["_fetch_ohlcv"](symbol, years=1)
        if df.empty:
            raise HTTPException(404, f"No data for {symbol}")
        high, low, close = df["high"], df["low"], df["close"]
        last = float(close.iloc[-1])
        prev = close.shift(1)
        tr = (high - low).combine((high - prev).abs(), max).combine((low - prev).abs(), max)
        atr = float(tr.tail(14).mean())

        rets = close.pct_change().dropna()
        drift = float(rets.tail(60).mean()) if len(rets) >= 20 else 0.0
        drift = max(-0.005, min(0.005, drift))          # cap extrapolation
        sma20 = float(close.tail(20).mean())
        sma50 = float(close.tail(50).mean()) if len(close) >= 50 else sma20
        trend = "uptrend" if sma20 > sma50 else "downtrend"

        band = atr * (days ** 0.5)
        base_exit = last * ((1 + drift) ** days)
        bull_exit = base_exit + band
        bear_exit = base_exit - band

        # Resolve quantity from qty or notional.
        if qty is None and notional is not None and last > 0:
            qty = float(int(notional // last))
        pos_notional = round(qty * last, 2) if qty else None

        def pnl(exit_px: float):
            return round(qty * (exit_px - last), 2) if qty else None

        edge = base_exit - last
        downside = max(1e-9, last - bear_exit)
        expected_rr = round(edge / downside, 2)

        if edge > 0 and edge >= 0.5 * band:
            verdict = "FAVORABLE"
        elif edge < 0:
            verdict = "UNFAVORABLE"
        else:
            verdict = "MARGINAL"

        # Right-size vs liquidity (1% of 20-day average dollar volume).
        right_size = None
        if "volume" in df.columns and qty:
            adv = float((close * df["volume"]).tail(20).mean())
            cap = 0.01 * adv
            if pos_notional and pos_notional > cap:
                right_size = (f"Large vs liquidity: ${pos_notional:,.0f} exceeds 1% of 20-day "
                              f"$ volume (${cap:,.0f}). Consider ≤ {int(cap // last)} shares.")
            else:
                right_size = "Within 1% of 20-day $ liquidity — size is fine."

        pct = lambda p: round((p / last - 1) * 100, 1)
        why = (f"{symbol.upper()} is in a {trend} (SMA20 {'>' if sma20 > sma50 else '<'} SMA50). "
               f"60-day drift {drift*100:.2f}%/day over {days} days gives a base exit ${base_exit:.2f} "
               f"({pct(base_exit):+}%). The {days}-day 1σ band is ±${band:.2f} (ATR·√days). "
               f"Edge vs downside ⇒ R:R {expected_rr}.")

        return {
            "status": "ok", "symbol": symbol.upper(),
            "proposed": {"qty": qty, "notional": pos_notional, "hold_days": days},
            "current_price": _round(last, 2),
            "verdict": verdict,
            "expected_exit": {
                "base": _round(base_exit, 2), "bull": _round(bull_exit, 2), "bear": _round(bear_exit, 2),
                "base_pct": pct(base_exit), "bull_pct": pct(bull_exit), "bear_pct": pct(bear_exit),
            },
            "expected_pnl": {"base": pnl(base_exit), "bull": pnl(bull_exit), "bear": pnl(bear_exit)},
            "expected_rr": expected_rr,
            "right_size": right_size,
            "trend": trend, "atr_14": _round(atr, 2), "band": _round(band, 2),
            "why": why,
            "method": ("drift = capped 60d mean daily return; band = ATR(14)·√days; "
                       "exits = base·(drift) ± band. Scores the user's fixed trade."),
            "disclaimer": "Probabilistic scenario from technicals. Educational, not advice.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("whatif %s", symbol)
        raise HTTPException(500, f"whatif error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# NEWS — Phase 2 Deliverable A (May 17, 2026)
# Provider-abstracted news for the symbol page. yfinance by default,
# Polygon when POLYGON_API_KEY is set.
# ═══════════════════════════════════════════════════════════════════════════
from .news_provider import (
    active_provider_name as _active_news_provider,
    get_news_provider    as _get_news_provider,
)


@router.get("/news/provider")
def news_provider_info() -> dict[str, Any]:
    """Diagnostic — which news provider is currently active + which keys are present."""
    return {
        "status":   "ok",
        "provider": _active_news_provider(),
        "polygon_configured": bool(os.getenv("POLYGON_API_KEY", "").strip()),
        "finnhub_configured": bool(os.getenv("FINNHUB_API_KEY", "").strip()),
        "chain":    ["polygon", "finnhub", "yfinance"],
    }


@router.get("/{symbol}/news")
def symbol_news(symbol: str, limit: int = 10) -> dict[str, Any]:
    """
    Get recent news headlines for a symbol.

    Path params:
        symbol : ticker (yfinance-style, e.g. AAPL or VOLV-B.ST)

    Query params:
        limit  : 1-50 (default 10)

    Returns:
        { status, symbol, provider, count, news: [NewsItem...] }
        where NewsItem = { id, title, summary, published, source, url,
                           thumbnail?, tickers[] }
    """
    # Defensive input validation (Gurpreet S. — XSS / injection prevention)
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")

    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    try:
        provider = _get_news_provider()
        items = provider.fetch(sym, limit)
        return {
            "status":   "ok",
            "symbol":   sym,
            "provider": provider.name,
            "count":    len(items),
            "news":     items,
        }
    except Exception as e:
        logger.exception("symbol_news failure for %s", sym)
        raise HTTPException(500, f"news fetch error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-SOURCE NEWS AGGREGATOR — Phase 3 Deliverable A (May 19, 2026)
# Free MT Newswires equivalent. Combines GDELT (no key) + yfinance (no key)
# + Polygon (when key set) + Finnhub (when key set) + AlphaVantage (gated).
# ═══════════════════════════════════════════════════════════════════════════
from .news_aggregator import (
    MultiSourceNewsAggregator as _MultiAgg,
    aggregator_active_providers as _agg_providers,
)

# Singleton — providers are stateless, init once at first request
_AGG_INSTANCE: Optional[_MultiAgg] = None


def _get_aggregator() -> _MultiAgg:
    global _AGG_INSTANCE
    if _AGG_INSTANCE is None:
        _AGG_INSTANCE = _MultiAgg()
    return _AGG_INSTANCE


@router.get("/news/multi/providers")
def news_multi_providers() -> dict[str, Any]:
    """Diagnostic: list active providers in the multi-source aggregator."""
    return {
        "status":    "ok",
        "active":    _agg_providers(),
        "polygon":   bool(os.getenv("POLYGON_API_KEY", "").strip()),
        "finnhub":   bool(os.getenv("FINNHUB_API_KEY", "").strip()),
        "av_gated":  os.getenv("AV_INCLUDE", "").strip().lower() in ("1", "true", "yes"),
        "yfinance":  True,  # always-on
        "gdelt":     True,  # always-on
    }


@router.get("/{symbol}/news/multi")
def symbol_news_multi(symbol: str, limit: int = 15) -> dict[str, Any]:
    """
    Multi-source news for a symbol.

    Fans out across ALL configured free providers in parallel, then dedupes
    by URL and sorts by published_utc descending.

    Path params:
        symbol : ticker (yfinance-style)

    Query params:
        limit  : 1-50 (default 15)

    Returns:
        { status, symbol, count, providers[], counts{}, news[] }
    """
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")

    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    try:
        agg = _get_aggregator()
        result = agg.fetch(sym, limit)
        return {
            "status":    "ok",
            "symbol":    sym,
            "count":     len(result["items"]),
            "providers": result["providers"],
            "counts":    result["counts"],
            "news":      result["items"],
        }
    except Exception as e:
        logger.exception("symbol_news_multi %s", sym)
        raise HTTPException(500, f"multi-source news error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# SEC EDGAR FILINGS — Phase 2 Deliverable C (May 19, 2026)
# Free MT Newswires equivalent for material events + insider trades.
# Zero API key, official SEC source. Caches CIK map in-process.
# ═══════════════════════════════════════════════════════════════════════════
from .sec_edgar_provider import (
    fetch_recent_filings as _fetch_filings,
    lookup_cik           as _lookup_cik,
)


@router.get("/{symbol}/filings")
def symbol_filings(symbol: str, limit: int = 15, form_type: Optional[str] = None) -> dict[str, Any]:
    """
    Recent SEC EDGAR filings for a symbol.

    Path params:
        symbol : ticker (US listings only — SEC is US-jurisdiction)

    Query params:
        limit     : 1-50 (default 15)
        form_type : optional filter (e.g. '8-K', '4', '10-Q')

    Returns:
        { status, symbol, cik, count, filings: [SECFiling...] }

    Free, official, no API key required. Live from data.sec.gov.
    """
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")

    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    cik = _lookup_cik(sym)
    if cik is None:
        # Non-US ticker or unknown — return empty cleanly
        return {
            "status":   "ok",
            "symbol":   sym,
            "cik":      None,
            "count":    0,
            "filings":  [],
            "note":     "SEC EDGAR only covers US-listed companies; ticker not found.",
        }

    try:
        if form_type:
            forms = [form_type.upper().strip()]
        else:
            forms = None
        filings = _fetch_filings(sym, form_types=forms, limit=limit)
        return {
            "status":  "ok",
            "symbol":  sym,
            "cik":     cik,
            "count":   len(filings),
            "filings": filings,
        }
    except Exception as e:
        logger.exception("symbol_filings failure for %s", sym)
        raise HTTPException(500, f"SEC EDGAR error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# QUOTE — Phase 2 Deliverable C extension (May 19, 2026)
# Lightweight quote endpoint that auto-prefers Polygon over yfinance when
# POLYGON_API_KEY is set. Used for high-frequency widgets that don't need
# the full /overview payload.
# ═══════════════════════════════════════════════════════════════════════════
from .polygon_ohlcv_provider import (
    fetch_polygon_prev_close as _polygon_prev,
    polygon_available        as _polygon_ready,
)


@router.get("/{symbol}/quote")
def symbol_quote(symbol: str) -> dict[str, Any]:
    """
    Lightweight previous-day quote.

    Strategy:
        1. If POLYGON_API_KEY is set → Polygon /v2/aggs/.../prev (production-grade)
        2. Otherwise → yfinance fast_info (free fallback)

    Returns:
        { status, symbol, source, price, open, high, low, volume, change_pct, vwap?, trades? }
    """
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")
    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    # Try Polygon first when key is set
    if _polygon_ready():
        bar = _polygon_prev(sym)
        if bar is not None:
            return {
                "status":     "ok",
                "symbol":     sym,
                "source":     "polygon",
                "price":      bar["close"],
                "open":       bar["open"],
                "high":       bar["high"],
                "low":        bar["low"],
                "volume":     bar["volume"],
                "vwap":       bar["vwap"],
                "trades":     bar["trades"],
                "change_pct": _round(bar["change_pct"], 2),
            }
        # Polygon configured but failed → fall through

    # yfinance fallback
    try:
        import yfinance as yf
        tk = yf.Ticker(sym)
        fi = tk.fast_info
        price = float(getattr(fi, "last_price", 0) or 0)
        prev_close = float(getattr(fi, "previous_close", 0) or 0)
        change_pct = ((price / prev_close) - 1.0) * 100.0 if prev_close > 1e-10 else 0.0
        return {
            "status":     "ok",
            "symbol":     sym,
            "source":     "yfinance",
            "price":      _round(price, 2),
            "open":       _round(float(getattr(fi, "open", 0) or 0), 2),
            "high":       _round(float(getattr(fi, "day_high", 0) or 0), 2),
            "low":        _round(float(getattr(fi, "day_low", 0) or 0), 2),
            "volume":     int(getattr(fi, "last_volume", 0) or 0),
            "change_pct": _round(change_pct, 2),
        }
    except Exception as e:
        logger.exception("symbol_quote yfinance failure for %s", sym)
        raise HTTPException(500, f"quote error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL FLOW — Phase 2 Deliverable D (May 19, 2026)
# Grounded in /mnt/project/Institutional_Flow_Tracker.md skill.
# FMP was the skill's preferred path but returns 403 with user's key.
# yfinance has the same data class FREE — top institutions, mutual funds,
# insider transactions, roster — with QoQ change tracking.
# ═══════════════════════════════════════════════════════════════════════════
from .institutional_flow_provider import (
    fetch_institutional_flow as _fetch_inst_flow,
)


@router.get("/{symbol}/institutional")
def symbol_institutional(symbol: str) -> dict[str, Any]:
    """
    Institutional flow analysis for a symbol — free, yfinance-backed.

    Path params:
        symbol : ticker (US listings work best; international has spotty coverage)

    Returns:
        {
          status, symbol, provider, signal, signal_reasoning, reliability_grade,
          summary: { insidersPercentHeld, institutionsPercentHeld,
                     institutionsFloatPercentHeld, institutionsCount },
          top_institutions: [ {holder, pct_held, shares, value, pct_change, date_reported} ],
          top_mutual_funds: [ ... same shape ],
          insider_roster:   [ {name, position, most_recent_transaction,
                              latest_transaction_date, shares_owned_directly} ],
          recent_transactions: [ {insider, position, transaction, start_date,
                                  shares, value, ownership, text} ],
          insider_net_6m:   { Purchases, Sales, Net Shares Purchased (Sold), ... }
        }

    Signal follows the Institutional_Flow_Tracker skill's framework:
        STRONG BULLISH  : top institutions +15% QoQ (smart money accumulating)
        MODERATE BULLISH: top institutions +5-15%
        NEUTRAL         : top institutions ±5%
        MODERATE BEARISH: top institutions -5 to -15%
        STRONG BEARISH  : top institutions -15% (smart money distributing)

    Reliability grade (A/B/C) per skill's data quality framework.
    """
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")

    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    try:
        result = _fetch_inst_flow(sym)
        if result.get("status") != "ok":
            raise HTTPException(404, result.get("message", "institutional flow data unavailable"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("symbol_institutional failure for %s", sym)
        raise HTTPException(500, f"institutional flow error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# FMP — Phase 2 Deliverable E (May 20, 2026)
# FMP /stable/ tier migration. Replaces dead v3 endpoints with the post-2025
# spec. Free-tier coverage: quote, profile, key-metrics, ratios, ratings,
# analyst grades, earnings, dividends. ~250 calls/day free.
# ═══════════════════════════════════════════════════════════════════════════
from .fmp_provider import (
    fetch_aggregate    as _fmp_aggregate,
    fmp_available      as _fmp_available,
)


@router.get("/{symbol}/fmp")
def symbol_fmp(symbol: str) -> dict[str, Any]:
    """
    FMP /stable/ tier aggregate fetch — quote + profile + fundamentals + analyst signals.

    Free-tier endpoints exposed:
        quote          : real-time price, P/E, EPS, day/year range, market cap
        profile        : exchange, sector, industry, employees, beta, IPO date
        key_metrics    : 43 TTM metrics (ROE, ROA, EV/EBITDA, FCF yield, Graham number)
        ratios         : margin ratios, debt/equity, dividend payout, current ratio
        rating         : composite analyst rating (A-F) + per-component scores
        recent_grades  : last 6 analyst rating actions (Buy/Sell/Hold changes)
        earnings       : next 5 earnings dates with EPS estimates + actuals
        dividends      : last 5 dividend payments with dates + amounts

    Returns provider="fmp-stable" when FMP_API_KEY is set, status="unavailable" otherwise.
    """
    if not symbol or not symbol.strip():
        raise HTTPException(400, "symbol is required")
    sym = symbol.strip().upper()
    if not _re_fw.match(r"^[A-Z0-9.\-]{1,20}$", sym):
        raise HTTPException(400, f"invalid symbol format: '{symbol}'")

    try:
        return _fmp_aggregate(sym)
    except Exception as e:
        logger.exception("symbol_fmp failure for %s", sym)
        raise HTTPException(500, f"FMP error: {e}")
