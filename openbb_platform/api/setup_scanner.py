"""
api/setup_scanner.py
====================
Setup Scanner engine v3 - the "setup-of-the-day" core.

DECISION PROVENANCE (LLM Council, May 21, 2026):
  Build "Setup Scanner" (decision-support), NOT "Trade Finder" (advice).
  - Return the BEST-QUALIFYING setup per (region, asset class) as of latest data.
  - Gate the message by an honest confidence grade (A / B / C / none).
  - Never promise a hard target date - use ATR-based time WINDOWS.
  - Attach a one-line ISK-vs-KF note (domicile + dividend + asset-class driven).
  - When nothing clears the bar, say "no A-grade setup today".

v3 (July 8, 2026 - Investor AB / INVE-B.ST regression response):
  - Transparent sub_scores + conflict / stale / data-quality penalties.
  - Multi-timeframe RSI (daily/weekly/monthly). Daily RSI 58.5 is an entry-band
    value, NOT oversold; only monthly RSI <= MONTHLY_RSI_OVERSOLD counts toward
    an oversold-reversal classification.
  - Strategic filters: 100-day MA, Ichimoku Tenkan/Kijun/cloud state, flat-Kijun
    "magnet" logic (Kijun is the hunter, Tenkan the hunting dog: Tenkan either
    fetches price back toward Kijun, or stands at support/resistance and waits
    for the Kijun to catch up - both are measured, testable states here).
  - MACD + Bollinger regime; honest 12-label setup classification.
  - Time-to-target v2: earliest/base/latest windows from ATR + historical speed
    + volatility regime, cross-checked against Fib Time Zones and configurable
    Ichimoku time numbers. Daily data only -> every target "time" is an
    end-of-day / market-close estimate. No intraday precision is pretended.
  - Optional technical_context (harmonic/Elliott findings) feeds the conflict
    penalty so the card cannot silently contradict the symbol page again.
  - Tax-wrapper (ISK/KF) note remains informational ONLY - never scored.

Pure functions, no side effects. All thresholds are NAMED CONSTANTS.
No float == comparisons. No hardcoded price levels.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any, Final, Optional, TypedDict

logger = logging.getLogger("setup_scanner")

# -- Moving averages / oscillators ------------------------------------------
SMA_FAST_D:        Final = 20
SMA_SLOW_D:        Final = 50
SMA_TREND_D:       Final = 100   # strategic filter: price above 100-day MA
SMA_FAST_W:        Final = 10
SMA_SLOW_W:        Final = 30
SMA_FAST_M:        Final = 10
RSI_PERIOD:        Final = 14
ATR_PERIOD:        Final = 14
MACD_FAST:         Final = 12
MACD_SLOW:         Final = 26
MACD_SIG:          Final = 9
BB_PERIOD:         Final = 20
BB_MULT:           Final = 2.0

RSI_ENTRY_LOW:     Final = 40.0
RSI_ENTRY_HIGH:    Final = 68.0
MONTHLY_RSI_OVERSOLD: Final = 35.0   # "near/below 30" band with tolerance
EXTENDED_ATR_MULT: Final = 3.0
PULLBACK_ATR_MULT: Final = 1.2
STOP_ATR_MULT:     Final = 1.5
REWARD_RISK:       Final = 2.0
TIME_WINDOW_MULT:  Final = 3
EPS:               Final = 1e-9

# -- Ichimoku (strategy constants - configurable, never hidden magic) --------
TENKAN_PERIOD:     Final = 9
KIJUN_PERIOD:      Final = 26
SPAN_B_PERIOD:     Final = 52
FLAT_WINDOW:       Final = 5      # bars over which a flat Tenkan/Kijun is judged
FLAT_BAND_ATR:     Final = 0.25   # range < 0.25 ATR over FLAT_WINDOW = "flat"
KIJUN_MAGNET_ATR:  Final = 2.0    # price > 2 ATR above a flat Kijun = catch-up risk

# Custom Ichimoku TIME numbers (hunter / hunting-dog timing model).
# Kijun-Sen is the hunter; Tenkan-Sen is the hunting dog. The dog either
# fetches price back toward the Kijun, or stands beside price at
# support/resistance and waits for the Kijun to catch up. Counted in BARS
# from a significant pivot, these are used ONLY as timing-confluence
# candidates: they may nudge and grade the ATR/speed-derived window
# (within TIMING_SNAP_TOL), they never invent a window on their own.
# Treat as a configurable timing model to be backtested - not a guarantee.
TENKAN_TIME_NUMBERS: Final = (
    9, 18, 27, 36, 45, 54, 63, 72, 81, 90, 99, 108, 117, 126, 135, 144, 153,
    162, 171, 180, 189, 198, 207, 216, 225, 234, 243, 252, 261, 270, 279, 288,
    297, 306, 315, 324, 333, 342, 351, 369, 378, 387, 396, 405)
KIJUN_TIME_NUMBERS: Final = (
    26, 52, 77, 103, 129, 155, 181, 207, 233, 259, 285, 311, 337, 363, 389,
    415, 441, 467, 493, 519, 545)
SPECIAL_TIME_NUMBERS: Final = (35, 52, 442)   # 26 * 17 = 442

# Standard Fibonacci time-zone steps (bars from anchor pivot).
FIB_TIME_STEPS: Final = (3, 5, 8, 13, 21, 34, 55, 89, 144)
TIMING_SNAP_TOL: Final = 0.25    # a confluence day may nudge base by <= 25%

# -- Scoring weights (documented; raw max = 100 before penalties) ------------
W_ALIGNMENT:       Final = 18.0  # x3 timeframes = 54
W_ENTRY_PULLBACK:  Final = 12.0
W_ENTRY_MID:       Final = 5.0
W_ENTRY_BELOW:     Final = 2.0
W_RSI_BAND:        Final = 8.0
W_MA100:           Final = 8.0
W_ICHI_TK:         Final = 4.0
W_ICHI_CLOUD:      Final = 3.0
W_ICHI_PRICE:      Final = 3.0
W_MACD:            Final = 4.0
W_BOLL:            Final = 4.0
B_MONTHLY_OVERSOLD: Final = 8.0  # bonus (long-term uptrend required); capped at 100
CONFLICT_UNIT:     Final = 6.0   # penalty per conflicting signal
CONFLICT_CAP:      Final = 30.0
STALE_UNIT:        Final = 4.0   # penalty per stale technical-context signal
DQ_PENALTY_NO_MONTHLY: Final = 8.0   # monthly RSI not computable
DQ_PENALTY_THIN:       Final = 4.0   # < 250 daily bars
CONFLICTED_AT:     Final = 3     # >= this many conflicts => "Conflicted Buy Setup"
NEAR_PRZ_ATR:      Final = 1.5   # bearish pattern D within this many ATR = conflict
FAR_PRZ_ATR:       Final = 3.0   # bullish pattern D beyond this = irrelevant, not support

DIVIDEND_KF_THRESHOLD: Final = 2.0
TAX_FREE_FLOOR_2026:   Final = 300_000

CLASSIFICATIONS: Final = (
    "Strong Buy Setup", "Buy Setup", "Early Buy Setup", "Pullback Buy Setup",
    "Breakout Buy Setup", "Reversal Buy Setup", "Momentum Continuation Buy Setup",
    "Mean-Reversion Buy Setup", "Watchlist Buy Setup", "High-Risk Buy Setup",
    "Conflicted Buy Setup", "Data-Limited Buy Setup")


class SetupResult(TypedDict, total=False):
    # -- legacy v2 fields (kept for backward compatibility) --
    symbol:             str
    name:               str
    region:             str
    asset_class:        str
    grade:              str
    score:              float
    last_price:         float
    daily_trend:        str
    weekly_trend:       str
    monthly_trend:      str
    timeframes_aligned: int
    rsi_14:             float
    atr_14:             float
    extended_atr:       float
    entry:              float
    stop:               float
    target:             float
    reward_risk:        float
    time_window_days:   str
    isk_kf_note:        str
    dividend_yield:     Optional[float]
    why:                str
    sector:             Optional[str]
    # -- v3 fields --
    classification:     str            # one of CLASSIFICATIONS
    setup_type:         str            # detailed regime label
    confidence:         float          # 0-100, = final score
    risk_level:         str            # Low / Moderate / Elevated / High
    invalidation:       float          # alias of stop (explicit naming)
    weekly_rsi:         Optional[float]
    monthly_rsi:        Optional[float]
    sub_scores:         dict
    penalties:          dict
    conflicts:          list
    supports:           list
    strongest_supporting: str
    strongest_opposing: str
    expected_target_date:  str
    expected_target_time:  str
    earliest_target_date:  str
    base_case_target_date: str
    latest_target_date:    str
    min_trading_days:      int
    expected_trading_days: int
    max_trading_days:      int
    timing_confidence:     float       # 0-1
    timing_reliability:    str         # high / medium / low
    timing_reasoning:      str
    timing_confluence_sources: list
    data_quality:          dict
    technical_context_used: bool
    debug:                 dict


# ============================================================================
# Basic indicator helpers (unchanged from v2)
# ============================================================================

def _rsi(closes: list, period: int = RSI_PERIOD) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(closes) - period, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains += delta
        else:
            losses += -delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss < EPS:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(highs: list, lows: list, closes: list, period: int = ATR_PERIOD) -> Optional[float]:
    n = len(closes)
    if n < period + 1:
        return None
    trs = []
    for i in range(n - period, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else None


def _sma(values: list, period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _trend_label(price: float, fast_ma: Optional[float], slow_ma: Optional[float],
                 fast_prev: Optional[float]) -> str:
    if fast_ma is None or slow_ma is None or fast_prev is None:
        return "flat"
    rising = (fast_ma - fast_prev) > EPS
    falling = (fast_prev - fast_ma) > EPS
    if price > fast_ma and fast_ma > slow_ma and rising:
        return "up"
    if price < fast_ma and fast_ma < slow_ma and falling:
        return "down"
    return "flat"


def _resample_weekly(dc: list, dh: list, dl: list):
    wc, wh, wl = [], [], []
    for i in range(0, len(dc), 5):
        cc = dc[i:i + 5]; ch = dh[i:i + 5]; cl = dl[i:i + 5]
        if not cc:
            continue
        wc.append(cc[-1]); wh.append(max(ch)); wl.append(min(cl))
    return wc, wh, wl


def _resample_monthly(dc: list) -> list:
    mc = []
    for i in range(0, len(dc), 21):
        chunk = dc[i:i + 21]
        if chunk:
            mc.append(chunk[-1])
    return mc


def _finite(xs: list) -> bool:
    """True only if every value is a finite real number (guards NaN from thin feeds)."""
    for x in xs:
        if x is None or not math.isfinite(x):
            return False
    return True


# ============================================================================
# v3 indicator helpers
# ============================================================================

def _ema_series(vals: list, period: int) -> Optional[list]:
    if len(vals) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(vals[:period]) / period
    out = [e]
    for v in vals[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _macd_state(closes: list) -> Optional[dict]:
    """MACD(12,26,9) terminal state: histogram sign + zero-line position."""
    if len(closes) < MACD_SLOW + MACD_SIG + 5:
        return None
    fast = _ema_series(closes, MACD_FAST)
    slow = _ema_series(closes, MACD_SLOW)
    if not fast or not slow:
        return None
    macd_line = [a - b for a, b in zip(fast[-len(slow):], slow)]
    sig = _ema_series(macd_line, MACD_SIG)
    if not sig:
        return None
    hist = macd_line[-1] - sig[-1]
    return {"macd": macd_line[-1], "signal": sig[-1], "hist": hist,
            "above_zero": macd_line[-1] > 0}


def _bollinger_state(closes: list) -> Optional[dict]:
    """Bollinger(20,2): %B position + squeeze flag (width in bottom quartile of 40d)."""
    if len(closes) < BB_PERIOD + 40:
        return None

    def _width(i_end: int) -> float:
        w = closes[i_end - BB_PERIOD + 1:i_end + 1]
        mu = sum(w) / BB_PERIOD
        sd = (sum((x - mu) ** 2 for x in w) / BB_PERIOD) ** 0.5
        return (2 * BB_MULT * sd / mu) if mu > EPS else 0.0

    last = len(closes) - 1
    cur = _width(last)
    hist = sorted(_width(last - i) for i in range(40))
    squeeze = cur <= hist[len(hist) // 4]
    w = closes[-BB_PERIOD:]
    mu = sum(w) / BB_PERIOD
    sd = (sum((x - mu) ** 2 for x in w) / BB_PERIOD) ** 0.5
    band = 2 * BB_MULT * sd
    pct_b = (closes[-1] - (mu - BB_MULT * sd)) / band if band > EPS else 0.5
    return {"width": cur, "squeeze": squeeze, "pct_b": pct_b}


def _ichimoku_state(highs: list, lows: list, closes: list, atr: float) -> Optional[dict]:
    """Ichimoku terminal state incl. flat-Tenkan/Kijun magnet logic.

    Kijun = the hunter, Tenkan = the hunting dog: a flat Kijun below price is a
    price/time magnet (catch-up risk); Tenkan hugging price at support is the
    dog waiting for the hunter. Both are surfaced as measurable flags.
    """
    n = len(closes)
    if n < SPAN_B_PERIOD + KIJUN_PERIOD + FLAT_WINDOW + 1:
        return None

    def mid(i_end: int, p: int) -> float:
        seg_h = highs[i_end - p + 1:i_end + 1]
        seg_l = lows[i_end - p + 1:i_end + 1]
        return (max(seg_h) + min(seg_l)) / 2.0

    last = n - 1
    tenkan = mid(last, TENKAN_PERIOD)
    kijun = mid(last, KIJUN_PERIOD)
    # Cloud AT today's bar = spans computed KIJUN_PERIOD bars ago.
    shift = last - KIJUN_PERIOD
    span_a = (mid(shift, TENKAN_PERIOD) + mid(shift, KIJUN_PERIOD)) / 2.0
    span_b = mid(shift, SPAN_B_PERIOD)
    # Forward (projected) cloud colour from today's values.
    fwd_a = (tenkan + kijun) / 2.0
    fwd_b = mid(last, SPAN_B_PERIOD)
    price = closes[-1]
    cloud_top, cloud_bot = max(span_a, span_b), min(span_a, span_b)

    kijun_win = [mid(last - i, KIJUN_PERIOD) for i in range(FLAT_WINDOW)]
    tenkan_win = [mid(last - i, TENKAN_PERIOD) for i in range(FLAT_WINDOW)]
    kijun_flat = (max(kijun_win) - min(kijun_win)) < FLAT_BAND_ATR * atr
    tenkan_flat = (max(tenkan_win) - min(tenkan_win)) < FLAT_BAND_ATR * atr
    kijun_dist_atr = (price - kijun) / atr if atr > EPS else 0.0
    # Chikou proxy: today's close vs close KIJUN_PERIOD bars ago.
    chikou_free = closes[-1] > closes[-1 - KIJUN_PERIOD]

    return {
        "tenkan": tenkan, "kijun": kijun,
        "span_a": span_a, "span_b": span_b,
        "tenkan_above_kijun": tenkan > kijun,
        "cloud_green": fwd_a > fwd_b,
        "price_above_cloud": price > cloud_top,
        "price_in_cloud": cloud_bot <= price <= cloud_top,
        "kijun_flat": kijun_flat, "tenkan_flat": tenkan_flat,
        "kijun_dist_atr": kijun_dist_atr,
        "kijun_catchup_risk": kijun_flat and kijun_dist_atr > KIJUN_MAGNET_ATR,
        "chikou_free": chikou_free,
    }


# ============================================================================
# Timing model v2 - earliest / base / latest windows with confluence grading
# ============================================================================

def _add_trading_days(start: date, n: int) -> date:
    """start + n weekdays (holiday calendars are a documented v4 refinement)."""
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _pivot_low_index(lows: list, lookback: int = 180) -> int:
    """Index of the most significant recent swing low (timing anchor)."""
    seg = lows[-lookback:] if len(lows) > lookback else lows
    off = len(lows) - len(seg)
    return off + min(range(len(seg)), key=lambda i: seg[i])


def _median(xs: list) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _time_to_target(closes: list, lows: list, atr: float, entry: float,
                    target: float, boll: Optional[dict],
                    as_of: Optional[date]) -> dict:
    """Estimate trading-day windows to target from ATR distance + realised speed,
    then cross-check against Fib Time Zones and Ichimoku time numbers counted
    from the anchor pivot. Confluence NUDGES the base case (<= TIMING_SNAP_TOL)
    and raises timing confidence; it never fabricates a window."""
    dist = max(EPS, target - entry)
    dist_atr = dist / atr
    base_legacy = max(1, math.ceil(dist_atr) * TIME_WINDOW_MULT)

    moves = [abs(closes[i] - closes[i - 1])
             for i in range(max(1, len(closes) - 60), len(closes))]
    med_speed = _median(moves)
    fast_speed = sorted(moves)[int(len(moves) * 0.75)] if moves else atr

    days_by_speed = math.ceil(dist / med_speed) if med_speed > EPS else base_legacy
    expected = max(1, round((base_legacy + days_by_speed) / 2))
    earliest = max(1, math.ceil(dist / fast_speed) if fast_speed > EPS else 1)
    latest = expected * 2
    reasons = [
        f"target is {dist_atr:.1f} ATR away; ATR pace suggests ~{base_legacy}d,"
        f" realised median daily speed suggests ~{days_by_speed}d",
    ]
    if boll and boll.get("squeeze"):
        latest = math.ceil(latest * 1.5)
        reasons.append("Bollinger squeeze regime - moves can stall before expansion, window widened")

    confluence: list = []
    anchor = _pivot_low_index(lows)
    bars_since = (len(closes) - 1) - anchor
    snap_lo = max(1, round(expected * (1 - TIMING_SNAP_TOL)))
    snap_hi = round(expected * (1 + TIMING_SNAP_TOL))

    def _check(numbers, label):
        for k in numbers:
            d_ahead = k - bars_since
            if snap_lo <= d_ahead <= snap_hi:
                confluence.append(f"{label} {k} bars from pivot -> ~{d_ahead} trading days ahead")
                return d_ahead
        return None

    fib_hit = _check(FIB_TIME_STEPS, "Fib time zone")
    kijun_hit = _check(KIJUN_TIME_NUMBERS + SPECIAL_TIME_NUMBERS, "Kijun time number")
    tenkan_hit = _check(TENKAN_TIME_NUMBERS, "Tenkan time number")
    hits = [h for h in (fib_hit, kijun_hit, tenkan_hit) if h is not None]
    if hits:
        expected = min(hits, key=lambda d: abs(d - expected))
        reasons.append("timing confluence nudged base case")

    earliest = min(earliest, expected)
    latest = max(latest, expected)

    agree = min(base_legacy, days_by_speed) / max(1, max(base_legacy, days_by_speed))
    conf = 0.35 + 0.25 * agree + 0.15 * len(hits)
    conf = max(0.1, min(0.85, conf))  # daily-data ceiling: never claim >0.85
    reliability = "high" if conf >= 0.65 else "medium" if conf >= 0.45 else "low"

    today = as_of or date.today()
    return {
        "min_trading_days": earliest,
        "expected_trading_days": expected,
        "max_trading_days": latest,
        "earliest_target_date": _add_trading_days(today, earliest).isoformat(),
        "base_case_target_date": _add_trading_days(today, expected).isoformat(),
        "latest_target_date": _add_trading_days(today, latest).isoformat(),
        "expected_target_date": _add_trading_days(today, expected).isoformat(),
        "expected_target_time": "market close (end-of-day estimate; daily data only)",
        "timing_confidence": round(conf, 2),
        "timing_reliability": reliability,
        "timing_reasoning": "; ".join(reasons),
        "timing_confluence_sources": confluence,
        "time_window_days": f"{earliest}-{latest} trading days",
    }


# ============================================================================
# Technical context (harmonic / Elliott) - the Investor AB fix
# ============================================================================

def zigzag_pivots(highs: list, lows: list, atr: float,
                  threshold_atr: float = 2.0, max_pivots: int = 12) -> list:
    """Lightweight ATR-threshold ZigZag over daily bars.
    Returns [(index, price), ...] alternating swing highs/lows, oldest first."""
    if not highs or atr <= EPS:
        return []
    thr = threshold_atr * atr
    pivots: list = []
    direction = 1  # +1 hunting a swing high, -1 hunting a swing low
    ext_i, ext_p = 0, highs[0]
    for i in range(1, len(highs)):
        if direction > 0:
            if highs[i] > ext_p:
                ext_i, ext_p = i, highs[i]
            elif ext_p - lows[i] > thr:
                pivots.append((ext_i, ext_p))
                direction, ext_i, ext_p = -1, i, lows[i]
        else:
            if lows[i] < ext_p:
                ext_i, ext_p = i, lows[i]
            elif highs[i] - ext_p > thr:
                pivots.append((ext_i, ext_p))
                direction, ext_i, ext_p = 1, i, highs[i]
    pivots.append((ext_i, ext_p))
    return pivots[-max_pivots:]


def build_technical_context(highs: list, lows: list, closes: list,
                            atr: float) -> Optional[dict]:
    """Run the deep harmonic engine over ZigZag pivots (best effort).
    Returns {"harmonics": [{name, bullish, d_price, d_index, age_bars}, ...]}
    or None when the engine is unavailable. Never raises."""
    try:
        from engine.analysis.harmonics import HarmonicEngine
    except Exception:  # noqa: BLE001 - engine optional at scan time
        return None
    try:
        pivots = zigzag_pivots(highs, lows, atr)
        if len(pivots) < 4:
            return {"harmonics": []}
        prices = [p for _, p in pivots]
        idxs = [i for i, _ in pivots]
        found = HarmonicEngine().scan(prices)
        out = []
        for pat in found:
            d_price = pat.points[-1]
            # D equals one of the pivot prices - use its LAST occurrence for age
            matches = [j for j, p in enumerate(prices) if abs(p - d_price) < EPS]
            d_idx = idxs[matches[-1]] if matches else idxs[-1]
            out.append({
                "name": pat.pattern_name,
                "bullish": bool(pat.is_bullish),
                "d_price": float(d_price),
                "age_bars": (len(closes) - 1) - d_idx,
            })
        return {"harmonics": out}
    except Exception as exc:  # noqa: BLE001
        logger.warning("technical context failed: %s", exc)
        return None


def _context_conflicts(ctx: Optional[dict], price: float, atr: float):
    """Translate deep-engine findings into conflicts / supports / stale count.
    Rules (Investor AB case): a bearish pattern completing NEAR price penalises
    a bullish setup; a bullish PRZ far BELOW price is NOT support; played-out
    (old) patterns count as stale, not as signal."""
    conflicts: list = []
    supports: list = []
    stale = 0
    if not ctx:
        return conflicts, supports, stale
    for h in ctx.get("harmonics", []):
        dist_atr = abs(price - h["d_price"]) / atr if atr > EPS else 99.0
        aged = h.get("age_bars", 0) > 90
        if aged:
            stale += 1
            continue
        if not h["bullish"] and dist_atr <= NEAR_PRZ_ATR:
            conflicts.append(f"bearish {h['name']} completing within {dist_atr:.1f} ATR of price")
        elif h["bullish"] and dist_atr <= NEAR_PRZ_ATR and h["d_price"] <= price:
            supports.append(f"bullish {h['name']} PRZ support {dist_atr:.1f} ATR below price")
        elif h["bullish"] and (price - h["d_price"]) / max(EPS, atr) > FAR_PRZ_ATR:
            stale += 1  # far-below bullish PRZ: irrelevant to a buy at current price
    ell = ctx.get("elliott")
    if isinstance(ell, dict):
        status = str(ell.get("status", "")).upper()
        if "COMPLETE" in status:
            conflicts.append(
                f"Elliott {ell.get('structure', 'count')} marked COMPLETE - "
                "prior structure exhausted; fresh trend evidence required")
    return conflicts, supports, stale


# ============================================================================
# Classification - honest 12-label regime mapping (priority order matters)
# ============================================================================

def _classify(*, aligned: int, extended_atr: float, monthly_rsi: Optional[float],
              long_term_up: bool, above_ma100: bool, n_conflicts: int,
              data_limited: bool, grade: str, breakout: bool,
              ichi: Optional[dict], boll: Optional[dict]) -> tuple:
    """Return (classification, setup_type, risk_level). The setup is ALWAYS
    classified - mixed evidence changes the label, never removes the pick."""
    ichi_bull = bool(ichi and ichi.get("tenkan_above_kijun") and ichi.get("cloud_green"))

    if data_limited and grade == "C":
        cls, typ = "Data-Limited Buy Setup", "Data-Limited"
    elif n_conflicts >= CONFLICTED_AT:
        cls, typ = "Conflicted Buy Setup", "High-Risk Conflicted Setup"
    elif monthly_rsi is not None and monthly_rsi <= MONTHLY_RSI_OVERSOLD and long_term_up:
        cls, typ = "Reversal Buy Setup", "Oversold Long-Term Uptrend Reversal"
    elif not above_ma100:
        if boll and boll.get("pct_b", 0.5) < 0.15:
            cls, typ = "Mean-Reversion Buy Setup", "Bollinger Mean Reversion"
        else:
            cls, typ = "High-Risk Buy Setup", "Below 100-day MA (no continuation basis)"
    elif breakout and aligned >= 2:
        cls, typ = "Breakout Buy Setup", "Breakout Continuation"
    elif aligned == 3 and 0 <= extended_atr <= PULLBACK_ATR_MULT:
        cls = "Strong Buy Setup" if (grade == "A" and ichi_bull) else "Pullback Buy Setup"
        typ = "Trend Continuation Pullback"
    elif aligned == 3:
        cls, typ = "Momentum Continuation Buy Setup", "Ichimoku Trend Continuation" \
            if ichi_bull else "Momentum Continuation"
    elif aligned == 2 and grade == "B":
        cls, typ = "Buy Setup", "Trend Continuation (2/3 timeframes)"
    elif aligned >= 1 and n_conflicts <= 1:
        cls, typ = "Early Buy Setup", "Early Setup (partial alignment)"
    else:
        cls, typ = "Watchlist Buy Setup", "Watchlist (weak alignment)"

    if grade == "C" and cls not in ("Conflicted Buy Setup", "Data-Limited Buy Setup",
                                    "High-Risk Buy Setup", "Mean-Reversion Buy Setup"):
        cls = "Watchlist Buy Setup"

    if n_conflicts >= CONFLICTED_AT or not above_ma100:
        risk = "High"
    elif n_conflicts == 2 or extended_atr > EXTENDED_ATR_MULT:
        risk = "Elevated"
    elif grade == "A" and n_conflicts == 0:
        risk = "Moderate"   # never "Low/risk-free" - this is still a market position
    else:
        risk = "Moderate-High" if grade == "C" else "Moderate"
    return cls, typ, risk


# ============================================================================
# Main scorer
# ============================================================================

def score_setup(symbol, region, closes, highs, lows, *,
                name=None, dividend_yield=None, sector=None, asset_class="equity",
                as_of: Optional[date] = None,
                technical_context: Optional[dict] = None,
                proxy_note: Optional[str] = None):
    """Score a single instrument into a SetupResult, or None if data insufficient.

    region is a display bucket ('Swedish' | 'International').
    asset_class is one of 'equity' | 'etf' | 'fund' | 'crypto' | 'gold' | 'oil'.
    technical_context: optional deep-engine findings (harmonics / Elliott) -
    conflicting evidence PENALISES the score, it is never averaged away.
    dividend_yield feeds ONLY the informational ISK/KF note - never the score.
    """
    if len(closes) < SMA_SLOW_D + 5:
        return None
    if not (_finite(closes) and _finite(highs) and _finite(lows)):
        return None
    price = closes[-1]
    if price <= EPS:
        return None

    # -- trend structure (daily / weekly / monthly) --
    sma_fast_d = _sma(closes, SMA_FAST_D)
    sma_slow_d = _sma(closes, SMA_SLOW_D)
    sma_fast_d_prev = _sma(closes[:-1], SMA_FAST_D)
    daily_trend = _trend_label(price, sma_fast_d, sma_slow_d, sma_fast_d_prev)

    wc, wh, wl = _resample_weekly(closes, highs, lows)
    sma_fast_w = _sma(wc, SMA_FAST_W)
    sma_slow_w = _sma(wc, SMA_SLOW_W)
    sma_fast_w_prev = _sma(wc[:-1], SMA_FAST_W)
    weekly_trend = _trend_label(wc[-1] if wc else price, sma_fast_w, sma_slow_w, sma_fast_w_prev)

    mc = _resample_monthly(closes)
    sma_fast_m = _sma(mc, SMA_FAST_M)
    sma_fast_m_prev = _sma(mc[:-1], SMA_FAST_M)
    monthly_trend = "flat"
    if sma_fast_m is not None and sma_fast_m_prev is not None:
        mlast = mc[-1] if mc else price
        if mlast > sma_fast_m and (sma_fast_m - sma_fast_m_prev) > EPS:
            monthly_trend = "up"
        elif mlast < sma_fast_m and (sma_fast_m_prev - sma_fast_m) > EPS:
            monthly_trend = "down"

    aligned = sum(1 for t in (daily_trend, weekly_trend, monthly_trend) if t == "up")
    long_term_up = weekly_trend == "up" or monthly_trend == "up"

    # -- oscillators & regime --
    rsi = _rsi(closes) or 50.0
    weekly_rsi = _rsi(wc)
    monthly_rsi = _rsi(mc)          # needs ~15 monthly bars (~315 daily)
    atr = _atr(highs, lows, closes)
    if atr is None or atr <= EPS:
        return None
    if sma_fast_d is None:
        return None
    extended_atr = (price - sma_fast_d) / atr

    ma100 = _sma(closes, SMA_TREND_D)
    ma100_prev = _sma(closes[:-1], SMA_TREND_D)
    above_ma100 = ma100 is not None and price > ma100
    ma100_rising = (ma100 is not None and ma100_prev is not None
                    and (ma100 - ma100_prev) > EPS)

    ichi = _ichimoku_state(highs, lows, closes, atr)
    macd = _macd_state(closes)
    boll = _bollinger_state(closes)
    breakout = len(closes) > 61 and price > max(closes[-61:-1])

    # -- sub-scores (each named; raw max = 100) --
    sub: dict = {}
    sub["trend_alignment"] = aligned * W_ALIGNMENT
    if 0 <= extended_atr <= PULLBACK_ATR_MULT:
        sub["entry_zone"] = W_ENTRY_PULLBACK
    elif PULLBACK_ATR_MULT < extended_atr <= EXTENDED_ATR_MULT:
        sub["entry_zone"] = W_ENTRY_MID
    elif extended_atr > EXTENDED_ATR_MULT:
        sub["entry_zone"] = 0.0
    else:
        sub["entry_zone"] = W_ENTRY_BELOW
    sub["daily_rsi"] = W_RSI_BAND if RSI_ENTRY_LOW <= rsi <= RSI_ENTRY_HIGH else \
        (1.0 if rsi > RSI_ENTRY_HIGH else 0.0)
    sub["ma100"] = W_MA100 if (above_ma100 and ma100_rising) else \
        (W_MA100 / 2 if above_ma100 else 0.0)
    sub["ichimoku"] = 0.0
    if ichi:
        if ichi["tenkan_above_kijun"]:
            sub["ichimoku"] += W_ICHI_TK
        if ichi["cloud_green"]:
            sub["ichimoku"] += W_ICHI_CLOUD
        if ichi["price_above_cloud"]:
            sub["ichimoku"] += W_ICHI_PRICE
    sub["macd"] = W_MACD if (macd and macd["hist"] > 0) else 0.0
    sub["bollinger"] = W_BOLL if (boll and not boll["squeeze"]
                                  and 0.35 <= boll["pct_b"] <= 0.9) else 0.0
    sub["monthly_rsi_reversal_bonus"] = (
        B_MONTHLY_OVERSOLD
        if (monthly_rsi is not None and monthly_rsi <= MONTHLY_RSI_OVERSOLD
            and long_term_up) else 0.0)

    # -- conflicts (each is evidence AGAINST the bullish read) --
    conflicts: list = []
    supports: list = []
    if ichi:
        if not ichi["tenkan_above_kijun"]:
            conflicts.append("Tenkan-Sen below Kijun-Sen (bearish Ichimoku cross state)")
        else:
            supports.append("Tenkan-Sen above Kijun-Sen")
        if not ichi["cloud_green"]:
            conflicts.append("Ichimoku forward cloud is red")
        if not ichi["price_above_cloud"] and not ichi["price_in_cloud"]:
            conflicts.append("price below the Ichimoku cloud")
        elif ichi["price_above_cloud"]:
            supports.append("price above the Ichimoku cloud")
        if ichi["kijun_catchup_risk"]:
            conflicts.append(
                f"flat Kijun {ichi['kijun_dist_atr']:.1f} ATR below price - "
                "mean-reversion magnet (Kijun catch-up risk)")
    if macd and macd["hist"] < 0 and aligned >= 2:
        conflicts.append("MACD histogram falling while trend is up (momentum fading)")
    elif macd and macd["hist"] > 0:
        supports.append("MACD momentum positive")
    if not above_ma100:
        conflicts.append("price below the 100-day moving average")
    else:
        supports.append("price above the 100-day moving average")
    if monthly_trend == "down":
        conflicts.append("monthly trend is down")
    if weekly_trend == "down":
        conflicts.append("weekly trend is down")
    if rsi > RSI_ENTRY_HIGH:
        conflicts.append(f"daily RSI {rsi:.0f} above entry band (chase risk)")
    if aligned >= 1:
        supports.append(f"{aligned}/3 timeframes trending up")

    ctx_conf, ctx_sup, stale_count = _context_conflicts(technical_context, price, atr)
    conflicts.extend(ctx_conf)
    supports.extend(ctx_sup)

    # -- penalties --
    pen: dict = {}
    pen["conflict_penalty"] = min(CONFLICT_CAP, CONFLICT_UNIT * len(conflicts))
    pen["stale_signal_penalty"] = STALE_UNIT * stale_count
    dq = 0.0
    data_limited = False
    if monthly_rsi is None:
        dq += DQ_PENALTY_NO_MONTHLY
        data_limited = True
    if len(closes) < 250:
        dq += DQ_PENALTY_THIN
    pen["data_quality_penalty"] = dq

    raw = sum(sub.values())
    score = max(0.0, min(100.0, raw - sum(pen.values())))

    # -- grade (stricter than v2: MA100 + zero-conflict gate for A) --
    entry_ok = (extended_atr <= EXTENDED_ATR_MULT) and (RSI_ENTRY_LOW <= rsi <= RSI_ENTRY_HIGH)
    if (aligned == 3 and entry_ok and 0 <= extended_atr <= PULLBACK_ATR_MULT
            and above_ma100 and len(conflicts) == 0):
        grade = "A"
    elif aligned >= 2 and entry_ok and len(conflicts) <= 1:
        grade = "B"
    else:
        grade = "C"

    classification, setup_type, risk_level = _classify(
        aligned=aligned, extended_atr=extended_atr, monthly_rsi=monthly_rsi,
        long_term_up=long_term_up, above_ma100=above_ma100,
        n_conflicts=len(conflicts), data_limited=data_limited, grade=grade,
        breakout=breakout, ichi=ichi, boll=boll)

    # -- levels (ATR risk model, unchanged maths, explicit invalidation) --
    entry = round(price, 2)
    stop = round(entry - STOP_ATR_MULT * atr, 2)
    risk = entry - stop
    target = round(entry + REWARD_RISK * risk, 2)

    timing = _time_to_target(closes, lows, atr, entry, target, boll, as_of)

    strongest_sup = "; ".join(supports[:3]) if supports else "none - weak setup"
    strongest_opp = "; ".join(conflicts[:3]) if conflicts else "no material opposing signals detected"

    tf_words = [w for w, t in (("daily", daily_trend), ("weekly", weekly_trend),
                               ("monthly", monthly_trend)) if t == "up"]
    tf_str = ", ".join(tf_words) if tf_words else "no"
    why = (
        f"{name or symbol}: {classification} ({setup_type}). Bullish alignment on "
        f"{tf_str} timeframe(s) ({aligned}/3); daily RSI {rsi:.0f}"
        + (f", monthly RSI {monthly_rsi:.0f}" if monthly_rsi is not None else "")
        + f". At {entry}, invalidation {stop} (1.5 ATR) targets {target} "
        f"({REWARD_RISK:.0f}:1) in ~{timing['time_window_days']} "
        f"(base case {timing['base_case_target_date']}, market-close estimate). "
        f"Opposing: {strongest_opp}. This is analysis, not advice."
    )

    result = SetupResult(
        symbol=symbol, name=name or symbol, region=region, asset_class=asset_class,
        grade=grade, score=round(score, 1), last_price=entry,
        daily_trend=daily_trend, weekly_trend=weekly_trend, monthly_trend=monthly_trend,
        timeframes_aligned=aligned, rsi_14=round(rsi, 1), atr_14=round(atr, 2),
        extended_atr=round(extended_atr, 2),
        entry=entry, stop=stop, target=target, reward_risk=float(REWARD_RISK),
        isk_kf_note=_isk_kf_note(region, dividend_yield, asset_class),
        dividend_yield=dividend_yield, sector=sector, why=why,
        # v3
        classification=classification, setup_type=setup_type,
        confidence=round(score, 1), risk_level=risk_level,
        invalidation=stop,
        weekly_rsi=round(weekly_rsi, 1) if weekly_rsi is not None else None,
        monthly_rsi=round(monthly_rsi, 1) if monthly_rsi is not None else None,
        sub_scores={k: round(v, 1) for k, v in sub.items()},
        penalties={k: round(v, 1) for k, v in pen.items()},
        conflicts=conflicts, supports=supports,
        strongest_supporting=strongest_sup, strongest_opposing=strongest_opp,
        data_quality={"daily_bars": len(closes),
                      "monthly_rsi_available": monthly_rsi is not None,
                      "weekly_rsi_available": weekly_rsi is not None},
        technical_context_used=technical_context is not None,
        debug={
            "raw_score": round(raw, 1),
            "ichimoku": {k: (round(v, 3) if isinstance(v, float) else v)
                         for k, v in ichi.items()} if ichi else None,
            "macd": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in macd.items()} if macd else None,
            "bollinger": {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in boll.items()} if boll else None,
            "ma100": round(ma100, 2) if ma100 is not None else None,
            "breakout_60d": breakout,
            "stale_context_signals": stale_count,
        },
        **timing,
    )
    if proxy_note:
        result["proxy"] = True            # type: ignore[typeddict-unknown-key]
        result["proxy_note"] = proxy_note  # type: ignore[typeddict-unknown-key]
    return result


def _isk_kf_note(region: str, dividend_yield: Optional[float], asset_class: str = "equity") -> str:
    """One-line ISK vs KF guidance, driven by domicile + dividend yield + asset class.
    INFORMATIONAL ONLY - never enters the setup score or ranking.
    Grounded in 2026 Swedish tax rules (researched May 21, 2026)."""
    floor = f"{TAX_FREE_FLOOR_2026:,}".replace(",", " ")

    if asset_class == "crypto":
        if region == "Swedish":
            return (
                "This is a Stockholm-listed crypto ETP - wrapper-eligible, so it CAN sit in an "
                "ISK or KF (unlike spot crypto). ISK is fine for a SEK-traded ETP. "
                f"(First {floor} kr across ISK+KF is tax-free in 2026.)"
            )
        return (
            "Spot crypto can't be held in an ISK/KF - only Stockholm-listed crypto ETPs "
            "(e.g. BITCOIN-XBT.ST) are wrapper-eligible. Held directly, gains are taxed as "
            "capital income (30%). For tax-wrapped exposure, use a Swedish crypto ETP in an ISK."
        )

    if asset_class in ("gold", "oil"):
        if region == "Swedish":
            return (
                f"Stockholm-listed commodity certificates/ETCs are ISK/KF-eligible. "
                f"(First {floor} kr across ISK+KF is tax-free in 2026.)"
            )
        return (
            "Foreign-listed commodity ETFs/ETCs and futures-based products vary in wrapper "
            "eligibility - US-listed ETFs are generally NOT ISK-purchasable for EU retail "
            "(PRIIPs); use a European ETC or a Swedish certificate for wrapped exposure."
        )

    if region == "Swedish":
        wrap = "voting rights" if asset_class == "equity" else "simple flat-tax treatment"
        return (
            f"ISK is fine - Swedish {asset_class}, no foreign withholding, and you keep {wrap}. "
            f"(First {floor} kr across ISK+KF is tax-free in 2026.)"
        )

    dy = dividend_yield or 0.0
    if asset_class == "fund":
        return (
            f"ISK or KF both work for funds - distributions are handled fund-internally, "
            f"so withholding rarely reaches you directly. (First {floor} kr tax-free in 2026.)"
        )
    if dy >= DIVIDEND_KF_THRESHOLD:
        return (
            f"KF recommended - foreign {asset_class} ({dy:.1f}% yield); the KF auto-reclaims the "
            f"~15% dividend withholding, an ISK only credits it up to your Swedish tax. "
            f"(First {floor} kr tax-free in 2026.)"
        )
    return (
        f"ISK or KF both fine - minimal dividend ({dy:.1f}%), so withholding barely matters; "
        f"ISK keeps it simple. (First {floor} kr tax-free in 2026.)"
    )
