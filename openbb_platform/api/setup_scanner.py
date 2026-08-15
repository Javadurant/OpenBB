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
# Trend-Based Fib Time: prior-leg duration ratios projected from the 3rd pivot.
TBF_TIME_RATIOS: Final = (0.618, 1.0, 1.618)
# Fib Circles: price-time radii (bars x ATR units) centred on the anchor pivot.
FIB_CIRCLE_RADII: Final = (21, 34, 55, 89, 144)
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

# v3.9.3: Structure Watch RECENCY gate (trading bars = trading days on the daily
# series). A completed harmonic PRZ (Point D) or a completed Elliott reversal is an
# ACTIONABLE manual-validation trigger only while it is FRESH: a reversal off a PRZ /
# correction low typically materialises within ~1-5 trading bars, and past that the
# structure is played out. Case that motivated this: Mycronic AB (MYCR.ST) bearish
# Gartley, Point D ~22 bars back, shown for a month under the old age<=90 gate -
# useless for manual validation. Configurable + testable, not mystical: one named
# constant, covered by tests; calibrate empirically against the trust ledger's
# resolved outcomes later. 5 is the tight/actionable end of the researched 1-5 window
# (raise toward 7 if the section prunes too hard in practice).
MAX_STRUCTURE_AGE_BARS: Final = 5

# v3.9 (user decision 2026-07-24): completed BULLISH structure now SCORES — the
# engine was asymmetric (bearish completion penalised via conflicts, bullish
# completion earned 0 points). This is the symmetric positive axis. Max 8 pts,
# SUPPORTS-ONLY: it never emits a conflict and NEVER changes the grade (grade
# stays purely conflict-gated, per the INVE-B safety fix). Split is user-set.
W_BULL_STRUCT:     Final = 8.0   # component max (structural tier, ~MA100/RSI)
W_BULL_HARMONIC:   Final = 4.0   # bullish harmonic PRZ support at/below price
W_BULL_ELLIOTT:    Final = 3.0   # Elliott bullish corrective-continuation (the edge)
W_BULL_CONFLUENCE: Final = 1.0   # bonus when 2+ bullish structural signals align

# -- Corporate-event gap risk (earnings / ex-dividend inside the target window) --
# Markets are closed ~17.5h/day: an earnings gap opens straight through a stop,
# and PEAD means the pre-earnings technical structure often does not survive the
# print. An ex-dividend drop is mechanical: on high-yield Swedish names a single
# dividend can consume most of a 1.5-ATR stop distance on its own.
EXDIV_CONFLICT_ATR:       Final = 0.5    # dividend >= 0.5 ATR inside window = conflict
EARNINGS_TIMING_CONF_CAP: Final = 0.60   # earnings in window: reliability <= "medium"

# -- v3.2 components (regime, volume, S/R, fib price, pitchfork, fundamentals) --
# Scores use DYNAMIC normalization: only components whose data exists enter the
# denominator, so a fund without volume is not silently penalised for it.
W_VOLUME:           Final = 4.0
W_SR:               Final = 4.0
W_FIBP:             Final = 3.0
W_PITCHFORK:        Final = 3.0
W_FUND:             Final = 4.0   # supports selection, can never rescue bad structure
W_REGIME:           Final = 4.0
VOL_BREAKOUT_MULT:  Final = 1.5   # breakout bar needs >= 1.5x 20-day average volume
SR_SUPPORT_ATR:     Final = 3.0   # pivot support within 3 ATR below = "support beneath"
SR_RESIST_NEAR_ATR: Final = 1.0   # pivot resistance within 1 ATR above = conflict
FIB_RETR:           Final = (0.382, 0.5, 0.618)
FIB_EXT:            Final = (1.272, 1.618)   # extensions of the last up-leg from its low
FIB_CLUSTER_ATR:    Final = 0.5   # levels within 0.5 ATR count as a cluster
PITCHFORK_MAX_AGE:  Final = 250   # P0 older than this (bars) = stale fork, not scored
LIQ_MIN_TURNOVER:   Final = 1_000_000.0   # 20d avg turnover below this = thin (curr. units)
LIQ_PENALTY:        Final = 3.0

# Exchange holiday calendars for target-date math (VERIFY ANNUALLY - these are
# configurable constants, not an astronomical calendar service). Crypto uses
# plain calendar days (trades 7d/week).
# -- v3.3 components (news, sector RS, spread, FX, OBV) ----------------------
W_NEWS:             Final = 3.0
W_SECTOR:           Final = 3.0
NEWS_FRESH_DAYS:    Final = 7      # items older than this decay; > 21d ignored
NEWS_STALE_DAYS:    Final = 21
# Deterministic financial-news lexicon (model-derived sentiment - honest,
# lower-confidence substitute while no licensed sentiment feed is configured).
NEWS_POSITIVE_WORDS: Final = frozenset({
    # English
    "beat", "beats", "raise", "raises", "raised", "upgrade", "upgraded",
    "record", "growth", "surge", "surges", "wins", "win", "contract",
    "buyback", "dividend increase", "outperform", "strong", "profit rise",
    "expands", "expansion", "partnership", "approval", "approved",
    # Swedish (Avanza/Placera coverage - v3.4)
    "höjer riktkurs", "slår förväntningar", "stark efterfrågan", "orderingång",
    "förvärv", "återköp", "höjer utdelning", "vinstlyft", "rekordkvartal",
    "uppgradering", "stororder", "höjer prognos"})
NEWS_NEGATIVE_WORDS: Final = frozenset({
    # English
    "miss", "misses", "cut", "cuts", "downgrade", "downgraded", "probe",
    "lawsuit", "investigation", "recall", "warning", "warns", "profit warning",
    "layoff", "layoffs", "fraud", "decline", "falls", "plunge", "plunges",
    "weak", "loss", "losses", "bankruptcy", "default", "strike", "slump",
    # Swedish (Avanza/Placera coverage - v3.4)
    "vinstvarning", "sänker riktkurs", "missar förväntningar",
    "svag efterfrågan", "stämning", "utredning", "marginalpress",
    "sänker prognos", "nedgradering", "varsel", "vd lämnar", "vd-byte",
    "skuldsättning"})
# Headlines containing these set an EVENT-RISK flag (report/guidance risk),
# independent of sentiment sign. Bilingual.
NEWS_EVENT_RISK_WORDS: Final = frozenset({
    "earnings", "quarterly report", "guidance", "profit warning",
    "rapport", "kvartalsrapport", "vinstvarning", "prognos", "utdelning",
    "dividend", "ex-dividend", "agm", "årsstämma", "kapitalmarknadsdag",
    "investor day"})
SPREAD_WIDE_PCT:    Final = 0.01   # >1% spread = wide, execution-risk penalty
SPREAD_PENALTY:     Final = 2.0
FX_VOL_PENALTY_AT:  Final = 8.0    # annualised FX vol above this (%) = penalty
FX_PENALTY:         Final = 2.0
OBV_SLOPE_BARS:     Final = 20
PRZ_TOUCH_BARS:     Final = 10     # PRZ touched within this many bars = fresh
PRZ_TOUCH_ATR:      Final = 1.0

SWEDISH_HOLIDAYS: Final = frozenset({
    date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 3), date(2026, 4, 6),
    date(2026, 5, 1), date(2026, 5, 14), date(2026, 6, 19),
    date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31),
    date(2027, 1, 1), date(2027, 1, 6), date(2027, 3, 26), date(2027, 3, 29),
    date(2027, 5, 6), date(2027, 6, 18), date(2027, 12, 24), date(2027, 12, 31),
})
US_HOLIDAYS: Final = frozenset({
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
})

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
    events:                dict           # earnings / ex-dividend window flags
    compliance:            dict           # per-signal component-consulted matrix
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


def _usable_price(value: Any) -> Optional[float]:
    """Coerce one OHLCV field to a usable price, or report it unusable.

    Returns None for anything that cannot be a traded price: missing, boolean
    (float(True) would silently become 1.0), non-numeric, NaN/infinity, or
    non-positive. NOTHING is substituted, interpolated or clamped - an
    unusable input is reported as unusable so the caller can refuse rather
    than guess. Never raises."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0.0:
        return None
    return f


def _atr(highs: list, lows: list, closes: list, period: int = ATR_PERIOD) -> Optional[float]:
    """Average true range over the last `period` bars.

    Structurally invalid bars are SKIPPED, never repaired. This matters for
    NAV-style instruments: a provider that reports high=low=0.0 alongside a
    valid close collapses the true range to max(0, |0-c|, |0-c|) = c, so ATR
    converges on the ASSET PRICE itself and drives stop below zero. A bar is
    usable only when high, low and the previous close are all positive finite
    numbers and high >= low; a full `period` of valid true ranges is required,
    otherwise None. Refusing beats inventing a volatility estimate."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs = []
    for i in range(n - period, n):
        hi = _usable_price(highs[i])
        lo = _usable_price(lows[i])
        prev_close = _usable_price(closes[i - 1])
        if hi is None or lo is None or prev_close is None or hi < lo:
            continue
        trs.append(max(
            hi - lo,
            abs(hi - prev_close),
            abs(lo - prev_close),
        ))
    if len(trs) < period:
        return None
    return sum(trs) / len(trs)


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

def _add_trading_days(start: date, n: int, holidays: frozenset = frozenset(),
                      calendar_days: bool = False) -> date:
    """start + n trading days, skipping weekends AND exchange holidays.
    calendar_days=True (crypto, trades 7d/week) adds plain calendar days."""
    if calendar_days:
        return start + timedelta(days=n)
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            added += 1
    return d


def _volume_state(volumes: Optional[list], breakout: bool) -> Optional[dict]:
    """Volume confirmation: breakout expansion / 5-day trend vs 20-day average.
    Returns None when the provider supplied no usable volume (funds, NAV)."""
    if not volumes or len(volumes) < 25:
        return None
    v20 = sum(volumes[-21:-1]) / 20
    if v20 <= EPS:
        return None   # all-zero series: provider has no volume for this instrument
    last = volumes[-1]
    recent5 = sum(volumes[-5:]) / 5
    notes: list = []
    if breakout and last >= VOL_BREAKOUT_MULT * v20:
        earned = W_VOLUME
        notes.append(f"breakout on {last / v20:.1f}x average volume")
    elif recent5 > v20:
        earned = W_VOLUME * 0.75
        notes.append("5-day volume running above the 20-day average")
    elif last > v20:
        earned = W_VOLUME * 0.5
        notes.append("latest volume above the 20-day average")
    else:
        earned = 0.0
        notes.append("volume below average - no participation confirmation")
    return {"earned": earned, "avg_20d": v20, "last": last, "notes": notes}


def _support_resistance(pivots: list, price: float, atr: float,
                        target: float) -> Optional[dict]:
    """Nearest pivot support below / resistance above price, in ATR units.
    Support beneath the candles earns; near overhead resistance before the
    target is a conflict (the target must clear real structure)."""
    if len(pivots) < 2 or atr <= EPS:
        return None
    levels = [p for _, p in pivots]
    sups = [p for p in levels if p < price - EPS]
    ress = [p for p in levels if p > price + EPS]
    support = max(sups) if sups else None
    resistance = min(ress) if ress else None
    earned = 0.0
    conflict = None
    if support is not None and (price - support) / atr <= SR_SUPPORT_ATR:
        earned += W_SR / 2
    if resistance is None or resistance >= target - EPS:
        earned += W_SR / 2   # clean air to the target
    elif (resistance - price) / atr <= SR_RESIST_NEAR_ATR:
        conflict = (f"overhead pivot resistance ~{resistance:.2f} within "
                    f"{SR_RESIST_NEAR_ATR:.0f} ATR, before the target")
    return {"earned": earned, "support": support, "resistance": resistance,
            "support_dist_atr": round((price - support) / atr, 2) if support else None,
            "resistance_dist_atr": round((resistance - price) / atr, 2) if resistance else None,
            "conflict": conflict}


def _fib_price_levels(pivots: list, price: float, atr: float,
                      target: float) -> Optional[dict]:
    """Fibonacci PRICE tools from the most recent up-leg (pivot low -> high):
    retracements as support confluence, extensions as target clusters."""
    if len(pivots) < 2 or atr <= EPS:
        return None
    leg = None
    for i in range(len(pivots) - 1, 0, -1):
        lo_p, hi_p = pivots[i - 1][1], pivots[i][1]
        if hi_p > lo_p:
            leg = (lo_p, hi_p)
            break
    if leg is None:
        return None
    lo_p, hi_p = leg
    rng = hi_p - lo_p
    retr = {r: round(hi_p - r * rng, 2) for r in FIB_RETR}
    ext = {k: round(lo_p + k * rng, 2) for k in FIB_EXT}
    earned, notes = 0.0, []
    aligned = [k for k, v in ext.items() if abs(v - target) <= FIB_CLUSTER_ATR * atr]
    if aligned:
        earned += 2.0
        notes.append(f"target clusters with the {aligned[0]} fib extension ({ext[aligned[0]]})")
    beneath = [(r, v) for r, v in retr.items()
               if 0 < (price - v) <= 2 * FIB_CLUSTER_ATR * atr]
    if beneath:
        earned += 1.0
        notes.append(f"fib {beneath[0][0]} retracement support {beneath[0][1]} beneath price")
    return {"earned": min(earned, W_FIBP), "retracements": retr,
            "extensions": ext, "notes": notes}


def _pitchfork_state(pivots: list, price: float, atr: float,
                     last_idx: int) -> Optional[dict]:
    """Andrews Pitchfork from the last three pivots (P0 handle, P1/P2 tines):
    median line from P0 through midpoint(P1,P2), parallels through P1/P2.
    A fork whose handle is older than PITCHFORK_MAX_AGE bars is STALE and
    excluded from scoring (anchor-staleness requirement)."""
    if len(pivots) < 3 or atr <= EPS:
        return None
    (i0, p0), (i1, p1), (i2, p2) = pivots[-3], pivots[-2], pivots[-1]
    age = last_idx - i0
    mid_i, mid_p = (i1 + i2) / 2.0, (p1 + p2) / 2.0
    if mid_i - i0 < 1:
        return None
    if age > PITCHFORK_MAX_AGE:
        return {"stale": True, "age_bars": age}
    slope = (mid_p - p0) / (mid_i - i0)
    ml = p0 + slope * (last_idx - i0)
    half = abs(p1 - (p0 + slope * (i1 - i0)))
    upper, lower = ml + half, ml - half
    rising = slope > EPS
    earned, notes, conflict = 0.0, [], None
    if rising and price >= ml:
        earned = W_PITCHFORK
        notes.append("price holding above the median line of a rising pitchfork")
    elif rising and price >= lower:
        earned = W_PITCHFORK / 2
        notes.append("price in the lower half of a rising pitchfork (median-line magnet above)")
    elif price < lower:
        conflict = "price below the lower parallel of the pitchfork"
    return {"stale": False, "age_bars": age, "median": round(ml, 2),
            "upper": round(upper, 2), "lower": round(lower, 2),
            "slope_per_bar": round(slope, 4), "rising": rising,
            "earned": earned, "notes": notes, "conflict": conflict}


def _fundamentals_earned(f: dict) -> tuple:
    """Fundamental quality: up to W_FUND points (growth, profitability, sane
    valuation). Deliberately small - fundamentals SUPPORT a technical setup,
    they never rescue a broken structure."""
    earned, notes = 0.0, []
    rg, eg = f.get("revenue_growth"), f.get("earnings_growth")
    roe = f.get("roe")
    pe = f.get("pe_trailing") or f.get("pe_forward")
    if isinstance(rg, (int, float)) and math.isfinite(rg) and rg > 0:
        earned += 1.0; notes.append(f"revenue growth {rg * 100:.1f}%")
    if isinstance(eg, (int, float)) and math.isfinite(eg) and eg > 0:
        earned += 1.0; notes.append(f"earnings growth {eg * 100:.1f}%")
    if isinstance(roe, (int, float)) and math.isfinite(roe) and roe > 0.10:
        earned += 1.0; notes.append(f"ROE {roe * 100:.0f}%")
    if isinstance(pe, (int, float)) and math.isfinite(pe) and 0 < pe < 40:
        earned += 1.0; notes.append(f"P/E {pe:.1f}")
    return earned, notes


def news_sentiment(items: list) -> dict:
    """Deterministic lexicon sentiment over headline+summary text.
    items: [{"title": str, "summary": str?, "age_days": int?}, ...].
    Recency-weighted: fresh (<= NEWS_FRESH_DAYS) full weight, linear decay to
    NEWS_STALE_DAYS, older ignored. Honest provenance: method is
    'lexicon (model-derived)' - lower confidence than a licensed feed."""
    total_w, weighted = 0.0, 0.0
    scored = 0
    licensed_n = 0
    for it in items or []:
        age = it.get("age_days")
        if age is None or age > NEWS_STALE_DAYS:
            continue
        w = 1.0 if age <= NEWS_FRESH_DAYS else \
            max(0.0, 1.0 - (age - NEWS_FRESH_DAYS) / (NEWS_STALE_DAYS - NEWS_FRESH_DAYS))
        # v3.6: LICENSED per-item sentiment (e.g. Polygon insights) beats the
        # lexicon when present - it's per-ticker and professionally labelled.
        lic = it.get("sentiment")
        if lic in ("positive", "negative", "neutral"):
            s = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}[lic]
            licensed_n += 1
        else:
            text = ((it.get("title") or "") + " " + (it.get("summary") or "")).lower()
            pos = sum(1 for wrd in NEWS_POSITIVE_WORDS if wrd in text)
            neg = sum(1 for wrd in NEWS_NEGATIVE_WORDS if wrd in text)
            if pos == 0 and neg == 0:
                continue
            s = (pos - neg) / max(1, pos + neg)
        weighted += w * s
        total_w += w
        scored += 1
    event_risk = any(
        w in ((it.get("title") or "") + " " + (it.get("summary") or "")).lower()
        for it in (items or [])
        for w in NEWS_EVENT_RISK_WORDS
        if (it.get("age_days") is not None and it["age_days"] <= NEWS_STALE_DAYS))
    if scored == 0:
        return {"score": 0.0, "label": "neutral/none", "n_scored": 0,
                "n_licensed": 0,
                "method": "lexicon (model-derived)", "confidence": "none",
                "event_risk": event_risk}
    s = weighted / total_w
    label = "positive" if s > 0.2 else "negative" if s < -0.2 else "neutral"
    if licensed_n == scored:
        method, conf = "licensed per-ticker sentiment", "high"
    elif licensed_n > 0:
        method, conf = "mixed: licensed + lexicon", "medium"
    else:
        method, conf = "lexicon (model-derived)", "low"
    return {"score": round(s, 2), "label": label, "n_scored": scored,
            "n_licensed": licensed_n, "method": method, "confidence": conf,
            "event_risk": event_risk}


def _news_component(news_context: Optional[dict]) -> Optional[dict]:
    """news_score: recency + relevance + model-derived sentiment. Neutral or
    missing news = component not counted (Data-Limited, never punished)."""
    if not news_context or not news_context.get("items"):
        return None
    senti = news_sentiment(news_context["items"])
    if senti["n_scored"] == 0:
        return None
    frac = (senti["score"] + 1.0) / 2.0            # -1..1 -> 0..1
    earned = round(W_NEWS * frac, 2)
    conflict = None
    if senti["label"] == "negative":
        conflict = (f"recent news flow is negative "
                    f"({senti['n_scored']} scored items, lexicon-derived)")
    return {"earned": earned, "sentiment": senti, "conflict": conflict,
            "source": news_context.get("source", "?"),
            "as_of": news_context.get("as_of")}


def _sector_component(sector_context: Optional[dict]) -> Optional[dict]:
    """Sector relative strength: asset return minus sector-proxy return over
    ~1m/3m/6m windows. Outperforming most windows earns; lagging earns 0."""
    if not sector_context:
        return None
    rels = [sector_context.get(k) for k in ("rel_1m", "rel_3m", "rel_6m")]
    rels = [r for r in rels if isinstance(r, (int, float)) and math.isfinite(r)]
    if not rels:
        return None
    wins = sum(1 for r in rels if r > 0)
    earned = W_SECTOR * wins / len(rels)
    label = ("sector leader" if wins == len(rels)
             else "mixed vs sector" if wins > 0 else "sector laggard")
    return {"earned": round(earned, 2), "windows": len(rels), "wins": wins,
            "label": label, "proxy": sector_context.get("proxy"),
            "rel_1m": sector_context.get("rel_1m"),
            "rel_3m": sector_context.get("rel_3m"),
            "rel_6m": sector_context.get("rel_6m")}


def _spread_model(price: float, atr: float, turnover_20d: Optional[float],
                  asset_class: str, is_proxy: bool,
                  bid: Optional[float] = None,
                  ask: Optional[float] = None) -> Optional[dict]:
    """Execution-cost model. Real bid/ask when supplied (yfinance quote);
    otherwise a documented turnover/volatility proxy estimate."""
    if price <= EPS:
        return None
    if (isinstance(bid, (int, float)) and isinstance(ask, (int, float))
            and bid > EPS and ask > bid - EPS and ask > EPS):
        spread = max(0.0, ask - bid)
        pct = spread / ((bid + ask) / 2)
        source, model = "real bid/ask", "quote"
    elif turnover_20d is not None and turnover_20d > EPS:
        # Proxy: thin turnover widens spread; volatility widens it further.
        base_bps = 5.0 if turnover_20d >= 50e6 else \
            10.0 if turnover_20d >= 10e6 else \
            25.0 if turnover_20d >= 1e6 else 60.0
        vol_addon = min(20.0, (atr / price) * 100 * 2) if atr > EPS else 0.0
        proxy_addon = 10.0 if is_proxy else 0.0
        pct = (base_bps + vol_addon + proxy_addon) / 10_000
        spread = pct * price
        source, model = "turnover/volatility proxy estimate", "proxy"
        bid = ask = None
    else:
        return None
    wide = pct >= SPREAD_WIDE_PCT
    return {"bid": bid, "ask": ask, "spread": round(spread, 4),
            "spread_pct": round(pct * 100, 3), "spread_source": source,
            "spread_model_type": model, "wide": wide,
            "execution_risk": "high" if wide else
            "moderate" if pct >= SPREAD_WIDE_PCT / 2 else "low"}


def _obv_state(closes: list, volumes: Optional[list]) -> Optional[dict]:
    """On-Balance Volume terminal state: slope over OBV_SLOPE_BARS bars."""
    if not volumes or len(volumes) != len(closes) or len(closes) < OBV_SLOPE_BARS + 2:
        return None
    if sum(volumes[-OBV_SLOPE_BARS:]) <= EPS:
        return None
    obv, series = 0.0, [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
        series.append(obv)
    window = series[-OBV_SLOPE_BARS:]
    rising = window[-1] > window[0]
    denom = abs(window[0]) if abs(window[0]) > EPS else 1.0
    return {"obv": round(series[-1], 0), "rising": rising,
            "slope_pct": round((window[-1] - window[0]) / denom * 100, 2)}


def _prz_touch_volume(harmonics: list, highs: list, lows: list,
                      volumes: Optional[list], atr: float) -> Optional[dict]:
    """Volume behaviour at the freshest harmonic PRZ touch: expansion at a
    bullish D = confirmation; expansion at a bearish D near price = rejection."""
    if not harmonics or not volumes or len(volumes) < 25 or atr <= EPS:
        return None
    v20 = sum(volumes[-21:-1]) / 20
    if v20 <= EPS:
        return None
    for h in harmonics:
        d = h.get("d_price")
        if d is None or h.get("age_bars", 999) > 90:
            continue
        for i in range(len(highs) - 1, max(0, len(highs) - 1 - PRZ_TOUCH_BARS), -1):
            if lows[i] - PRZ_TOUCH_ATR * atr <= d <= highs[i] + PRZ_TOUCH_ATR * atr:
                ratio = volumes[i] / v20
                return {"pattern": h.get("name"), "bullish": h.get("bullish"),
                        "touch_bar_age": len(highs) - 1 - i,
                        "volume_ratio": round(ratio, 2),
                        "confirmed": ratio >= VOL_BREAKOUT_MULT and bool(h.get("bullish")),
                        "rejection": ratio >= VOL_BREAKOUT_MULT and not h.get("bullish")}
    return None


def refine_target_time_intraday(base_date_iso: str, dist_to_target: float,
                                intra_highs: list, intra_lows: list,
                                intra_closes: list, bars_per_day: float,
                                tz_label: str = "exchange local") -> dict:
    """Refine the daily base-case target DATE into a target DATETIME using real
    intraday bars: hourly ATR + realised median per-bar speed estimate how far
    into the target day the remaining distance completes. Never fabricates
    sub-daily precision without intraday data - the caller falls back."""
    n = len(intra_closes)
    if n < 30 or bars_per_day <= 0:
        return {"intraday_available": False,
                "fallback_reason": f"insufficient intraday bars ({n})"}
    moves = [abs(intra_closes[i] - intra_closes[i - 1]) for i in range(1, n)]
    med = _median(moves)
    if med <= EPS:
        return {"intraday_available": False,
                "fallback_reason": "flat intraday series (no measurable speed)"}
    intra_atr = _atr(intra_highs, intra_lows, intra_closes)
    # Bars needed on the final day ~ residual distance after full prior days.
    bars_needed = dist_to_target / med
    residual_bars = bars_needed % bars_per_day
    hour_offset = max(1, min(int(round(residual_bars)), int(bars_per_day)))
    return {
        "intraday_available": True,
        "intraday_resolution": "60m",
        "intraday_bars": n,
        "intraday_atr": round(intra_atr, 4) if intra_atr else None,
        "intraday_median_bar_move": round(med, 4),
        "expected_target_datetime": (
            f"{base_date_iso} ~{hour_offset} trading hour(s) after the open "
            f"({tz_label}; intraday estimate)"),
        "target_time_basis": "intraday realised speed (60m bars)",
        "target_time_confidence": "medium" if n >= 200 else "low",
    }


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


def _tbft_candidates(pivots: list, last_idx: int) -> list:
    """Trend-Based Fib Time: from the last three ZigZag pivots (A, B, C),
    project TBF_TIME_RATIOS of the prior leg's DURATION (B-A bars) forward
    from C. Returns [(ratio, days_ahead), ...] with days_ahead > 0."""
    if len(pivots) < 3:
        return []
    a_i = pivots[-3][0]
    b_i = pivots[-2][0]
    c_i = pivots[-1][0]
    leg = max(1, b_i - a_i)
    out = []
    for ratio in TBF_TIME_RATIOS:
        d_ahead = c_i + round(ratio * leg) - last_idx
        if d_ahead > 0:
            out.append((ratio, d_ahead))
    return out


def _fib_circle_candidates(bars_since_pivot: int, price_dist_atr: float) -> list:
    """Fib Circles: price-time geometry centred on the anchor pivot, with time
    in bars and price in ATR units. A circle of radius R crosses the TARGET
    price level sqrt(R^2 - y^2) bars from the pivot (y = |target - pivot| in
    ATR). Returns [(radius, days_ahead), ...]. Chart geometry converted into
    a testable confluence check - no fake visual precision."""
    out = []
    for radius in FIB_CIRCLE_RADII:
        if radius <= price_dist_atr:
            continue
        x = (radius ** 2 - price_dist_atr ** 2) ** 0.5
        d_ahead = round(x) - bars_since_pivot
        if d_ahead > 0:
            out.append((radius, d_ahead))
    return out


def _time_to_target(closes: list, lows: list, atr: float, entry: float,
                    target: float, boll: Optional[dict],
                    as_of: Optional[date],
                    calibration: Optional[dict] = None,
                    highs: Optional[list] = None,
                    holidays: frozenset = frozenset(),
                    calendar_days: bool = False) -> dict:
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

    # Ledger-based calibration (WIN-only, first-touch): rescale the base case
    # by the historically-observed median actual/expected speed ratio.
    calib_err = None
    calibrated = False
    if calibration and calibration.get("reliable"):
        factor = float(calibration.get("speed_factor", 1.0))
        expected = max(1, round(expected * factor))
        calib_err = calibration.get("median_abs_pct_error")
        calibrated = True
        reasons.append(
            f"ledger calibration (n={calibration.get('n_samples')}): base case "
            f"scaled x{factor} from historical target-hit speed")

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

    # Trend-Based Fib Time: prior-leg duration ratios projected from pivot C.
    tbft_hit = None
    pivots3 = zigzag_pivots(highs, lows, atr, max_pivots=6) if highs else []
    for _ratio, d_ahead in _tbft_candidates(pivots3, len(closes) - 1):
        if snap_lo <= d_ahead <= snap_hi:
            confluence.append(
                f"Trend-Based Fib Time {_ratio} of prior leg -> ~{d_ahead} trading days ahead")
            tbft_hit = d_ahead
            break

    # Fib Circles: price-time geometry from the anchor pivot.
    circle_hit = None
    y_atr = abs(target - lows[anchor]) / atr if atr > EPS else 0.0
    for _radius, d_ahead in _fib_circle_candidates(bars_since, y_atr):
        if snap_lo <= d_ahead <= snap_hi:
            confluence.append(
                f"Fib circle radius {_radius} (price-time) -> ~{d_ahead} trading days ahead")
            circle_hit = d_ahead
            break

    hits = [h for h in (fib_hit, kijun_hit, tenkan_hit, tbft_hit, circle_hit)
            if h is not None]
    if hits:
        expected = min(hits, key=lambda d: abs(d - expected))
        reasons.append("timing confluence nudged base case")

    earliest = min(earliest, expected)
    latest = max(latest, expected)

    agree = min(base_legacy, days_by_speed) / max(1, max(base_legacy, days_by_speed))
    conf = 0.35 + 0.25 * agree + 0.15 * len(hits) + (0.05 if calibrated else 0.0)
    conf = max(0.1, min(0.85, conf))  # daily-data ceiling: never claim >0.85
    reliability = "high" if conf >= 0.65 else "medium" if conf >= 0.45 else "low"

    today = as_of or date.today()

    def _d(n: int) -> str:
        return _add_trading_days(today, n, holidays, calendar_days).isoformat()

    return {
        "min_trading_days": earliest,
        "expected_trading_days": expected,
        "max_trading_days": latest,
        "earliest_target_date": _d(earliest),
        "base_case_target_date": _d(expected),
        "latest_target_date": _d(latest),
        "expected_target_date": _d(expected),
        "expected_target_time": ("end of day (crypto trades 24/7)" if calendar_days
                                 else "market close (end-of-day estimate; daily data only)"),
        "timing_confidence": round(conf, 2),
        "timing_reliability": reliability,
        "timing_reasoning": "; ".join(reasons),
        "timing_confluence_sources": confluence,
        "historical_calibration_error": calib_err,
        "timing_tools_checked": {
            "fib_time_zones": True,
            "trend_based_fib_time": len(pivots3) >= 3,
            "fib_circles": True,
            "ichimoku_time_numbers": True,
            "ledger_calibration": calibrated,
        },
        "time_window_days": f"{earliest}-{latest} trading days",
    }


def _event_flags(event_context: Optional[dict], start: date,
                 latest_iso: str, atr: float) -> tuple:
    """Corporate-event gap-risk checks against the [start, latest_target_date]
    window. Returns (event_conflicts, events_summary). Pure date math - the
    router supplies the calendar data; missing/garbage input degrades silently.

    Levels caveat baked into the summary: the price feed is dividend-ADJUSTED
    (verified 2026-07-08: INVE-B.ST raw 337.1 vs adjusted 333.5), so displayed
    levels are adjusted terms and diverge from broker quotes around ex-dates."""
    conflicts: list = []
    summary: dict = {"earnings_in_window": False, "ex_dividend_in_window": False}
    if not event_context:
        return conflicts, summary
    try:
        end = date.fromisoformat(latest_iso)
    except (ValueError, TypeError):
        return conflicts, summary

    def _parse(v) -> Optional[date]:
        try:
            return date.fromisoformat(str(v)[:10])
        except (ValueError, TypeError):
            return None

    ed = _parse(event_context.get("next_earnings_date"))
    if ed is not None:
        summary["next_earnings_date"] = ed.isoformat()
        if start <= ed <= end:
            summary["earnings_in_window"] = True
            conflicts.append(
                f"earnings report {ed.isoformat()} inside the target window - "
                "overnight gap risk a stop cannot protect against (PEAD: the "
                "pre-earnings structure often does not survive the print)")

    xd = _parse(event_context.get("next_ex_dividend_date"))
    if xd is not None:
        summary["next_ex_dividend_date"] = xd.isoformat()
        amt = event_context.get("dividend_amount")
        if isinstance(amt, (int, float)) and math.isfinite(amt) and amt > 0:
            summary["dividend_amount"] = round(float(amt), 4)
            if atr > EPS:
                summary["dividend_atr_ratio"] = round(float(amt) / atr, 2)
        if start <= xd <= end:
            summary["ex_dividend_in_window"] = True
            ratio = summary.get("dividend_atr_ratio")
            if ratio is not None and ratio >= EXDIV_CONFLICT_ATR:
                conflicts.append(
                    f"ex-dividend {xd.isoformat()} inside the target window - "
                    f"the ~{summary['dividend_amount']} dividend is {ratio:.1f} ATR, "
                    f"a mechanical drop against a {STOP_ATR_MULT} ATR stop")
    return conflicts, summary


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


def _elliott_context(highs: list, lows: list, closes: list,
                     symbol: str = "SCAN") -> Optional[dict]:
    """Run the computed Elliott engine (Frost & Prechter rule set) on the daily
    series. Returns the preferred count's terminal state or None. Never raises."""
    try:
        from engine.structure import elliott_wave as ew
    except Exception:  # noqa: BLE001 - engine optional at scan time
        return None
    try:
        labels = [str(i) for i in range(len(closes))]
        res = ew.analyze(highs, lows, closes, labels,
                         symbol=symbol, timeframe="1d",
                         as_of=labels[-1] if labels else "")
        pref = res.preferred
        if pref is None:
            return None

        last_i = len(closes) - 1
        def _ser(count) -> dict:
            # v3.9.3: bars since the terminal labelled leg ended (Wave C / Wave 5).
            # Feeds the Structure Watch recency gate so a correction that bottomed
            # weeks ago is not surfaced as a live reversal-buy trigger. None only if
            # a valid count somehow carries no legs (defensive; fail-open downstream).
            end_bar = count.legs[-1].end_index if getattr(count, "legs", None) else None
            age = (last_i - end_bar) if end_bar is not None else None
            return {
                "structure": count.count_type.value,
                "current_wave": count.current_wave,
                "status": count.status.value,
                "direction": count.direction.value,
                "invalidation": float(count.invalidation_level),
                "guideline_score": int(getattr(count, "guideline_score", 0)),
                "age_bars": age,
            }

        out = _ser(pref)
        # v3.3: surface the ALTERNATE count (ranked lower by guideline score) so
        # the scanner can price count-uncertainty instead of hiding it.
        alt = getattr(res, "alternate", None)
        if alt is not None:
            out["alternate"] = _ser(alt)
            out["preferred_reason"] = (
                f"preferred satisfies {out['guideline_score']} guidelines vs "
                f"{out['alternate']['guideline_score']} for the alternate")
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("elliott context skipped: %s", exc)
        return None


def build_technical_context(highs: list, lows: list, closes: list,
                            atr: float, symbol: str = "SCAN") -> Optional[dict]:
    """Run the deep harmonic + Elliott engines (best effort).
    Returns {"harmonics": [{name, bullish, d_price, age_bars}, ...],
             "elliott": {structure, current_wave, status, direction,
                         invalidation} | absent}
    or None when the engines are unavailable. Never raises."""
    try:
        from engine.analysis.harmonics import HarmonicEngine
    except Exception:  # noqa: BLE001 - engine optional at scan time
        return None
    try:
        # Pivot-basis PARITY with the symbol page: prefer the same
        # engine.structure.swings pivots the pipeline uses for its harmonic
        # report (find_pivots + enforce_alternation); ATR-ZigZag is the
        # fallback when the engine module is unavailable.
        pivots: list = []
        basis = "zigzag-atr"
        try:
            import pandas as pd
            from engine.structure.swings import enforce_alternation, find_pivots
            _df = pd.DataFrame({"high": highs, "low": lows, "close": closes})
            _pv = enforce_alternation(find_pivots(_df))
            if _pv is not None and len(_pv) >= 4:
                pivots = list(zip((int(i) for i in _pv.index),
                                  (float(x) for x in _pv["close"])))[-12:]
                basis = "engine-swings"
        except Exception:  # noqa: BLE001 - parity is best-effort
            pivots = []
        if not pivots:
            pivots = zigzag_pivots(highs, lows, atr)
        if len(pivots) < 4:
            return {"harmonics": [], "pivot_basis": basis}
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
        ctx: dict = {"harmonics": out, "pivot_basis": basis}
        ell = _elliott_context(highs, lows, closes, symbol)
        if ell is not None:
            ctx["elliott"] = ell
        return ctx
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
        direction = str(ell.get("direction", "")).upper()
        structure = ell.get("structure", "count")
        wave = ell.get("current_wave", "")
        done = "COMPLETE" in status  # covers COMPLETE and COMPLETING
        if direction == "BEARISH":
            if done:
                # A finished bearish correction = downside structure exhausted.
                supports.append(
                    f"Elliott bearish {structure} {status.lower()} - "
                    "downside structure exhausted (needs price confirmation)")
            else:
                conflicts.append(
                    f"Elliott preferred count is a bearish {structure} "
                    f"({wave} {status.lower()}) - structure argues against a buy")
        elif direction == "BULLISH":
            if done:
                conflicts.append(
                    f"Elliott bullish {structure} marked {status} - upside "
                    "structure exhausted; correction risk elevated")
            elif "5" in wave:
                conflicts.append(
                    f"Elliott bullish impulse in late-stage {wave} - "
                    "limited structure left before completion")
            else:
                supports.append(
                    f"Elliott bullish {structure} in progress ({wave})")
        elif done:
            # Direction unknown (e.g. context supplied externally): a completed
            # structure of unknown direction still demands fresh evidence.
            conflicts.append(
                f"Elliott {structure} marked COMPLETE - "
                "prior structure exhausted; fresh trend evidence required")
    return conflicts, supports, stale


def _bullish_structure(ctx: Optional[dict], price: float, atr: float,
                       extended_atr: float) -> Optional[dict]:
    """v3.9 — SCORE completed bullish structure so strong technical confirmation
    actively RAISES conviction, symmetric to the bearish conflicts in
    _context_conflicts (which subtract). Reads the SAME harmonic/Elliott context
    and reuses the SAME proximity gates (NEAR_PRZ_ATR, PULLBACK_ATR_MULT) — no
    new thresholds are invented.

    SUPPORTS-ONLY (user decision 2026-07-24): this never emits a conflict and
    never changes the grade — grade stays purely conflict-gated (INVE-B safety).
    It only lifts the 0-100 conviction score / ranking. Max W_BULL_STRUCT (8):
      · bullish harmonic PRZ at/below price within 1.5 ATR  -> W_BULL_HARMONIC (4)
      · Elliott bullish corrective-continuation (in-progress, not a late wave-5)
        -> W_BULL_ELLIOTT (3)   [the documented positive edge; reversals excluded]
      · 2+ independent bullish structural signals aligning  -> W_BULL_CONFLUENCE (1)

    Returns None when no bullish structural signal is present, so the component
    is absent from the dynamic denominator (never a zero that penalises)."""
    if not ctx or atr <= EPS:
        return None
    signals: list = []
    harmonic_pts = 0.0
    elliott_pts = 0.0

    # -- bullish harmonic PRZ at/below price (mirror of the bearish conflict gate)
    for h in ctx.get("harmonics", []):
        if h.get("age_bars", 0) > 90 or not h.get("bullish"):
            continue
        d_price = h.get("d_price")
        if d_price is None or d_price > price:
            continue  # PRZ must be at/below price to be buy-side support
        dist_atr = abs(price - d_price) / atr
        if dist_atr <= NEAR_PRZ_ATR and W_BULL_HARMONIC > harmonic_pts:
            harmonic_pts = W_BULL_HARMONIC
            signals.append(
                f"completed bullish {h.get('name', 'harmonic')} PRZ support "
                f"{dist_atr:.1f} ATR below price (buy-side reversal zone)")

    # -- Elliott bullish corrective-continuation (same read as _context_conflicts;
    #    only the CONTINUATION case scores — completed/late-5 stay conflicts, a
    #    completed bearish count stays a 'needs confirmation' narrative support)
    ell = ctx.get("elliott")
    if isinstance(ell, dict):
        status = str(ell.get("status", "")).upper()
        direction = str(ell.get("direction", "")).upper()
        wave = str(ell.get("current_wave", ""))
        structure = ell.get("structure", "count")
        if direction == "BULLISH" and "COMPLETE" not in status and "5" not in wave:
            elliott_pts = W_BULL_ELLIOTT
            signals.append(
                f"Elliott bullish {structure} in progress ({wave}) — trend "
                "structure resuming (corrective-continuation)")

    if harmonic_pts <= 0 and elliott_pts <= 0:
        return None  # nothing bullish-structural to score

    # -- confluence: 2+ independent bullish signals near price (a pullback landing
    #    INTO bullish structure counts, but adds no separate points — entry_zone
    #    already scores the pullback, so this only contributes to the bonus)
    structural = (1 if harmonic_pts > 0 else 0) + (1 if elliott_pts > 0 else 0)
    if (0 <= extended_atr <= PULLBACK_ATR_MULT) and structural >= 1:
        structural += 1
    confluence_pts = W_BULL_CONFLUENCE if structural >= 2 else 0.0
    if confluence_pts > 0:
        signals.append("bullish structural confluence — multiple aligned signals near price")

    earned = min(W_BULL_STRUCT, harmonic_pts + elliott_pts + confluence_pts)
    return {
        "earned": round(earned, 2),
        "max": W_BULL_STRUCT,
        "signals": signals,
        "harmonic_pts": round(harmonic_pts, 2),
        "elliott_pts": round(elliott_pts, 2),
        "confluence_pts": round(confluence_pts, 2),
    }


def _structure_flags(ctx: Optional[dict], price: float, atr: float) -> dict:
    """v3.9.1 — compact, immediately-scannable structure flags for the SOTD UI:
      · bearish_harmonic: the nearest COMPLETED (≤NEAR_PRZ_ATR=1.5) or NEAR-miss
        (≤FAR_PRZ_ATR=3.0) bearish harmonic. A completed bearish PRZ near price is
        a buy-VALIDITY red flag (and is already a scored conflict); a near-miss is
        an early warning that a bearish pattern is approaching completion.
      · elliott_buy: whether a BUY-signalling Elliott pattern has COMPLETED — a
        finished bearish correction = downside exhausted = reversal buy — or is an
        in-progress corrective-continuation (completed=False).
    Read-only over build_technical_context; mirrors _context_conflicts gates so the
    flags never disagree with the scored conflicts. Never raises."""
    out: dict = {"bearish_harmonic": None, "elliott_buy": None}
    if not ctx or atr <= EPS:
        return out
    best = None
    for h in ctx.get("harmonics", []):
        # v3.9.3: RECENCY gate. A bearish PRZ is a live buy-validity flag only while
        # Point D is fresh (<= MAX_STRUCTURE_AGE_BARS trading bars). A month-old
        # completed pattern is played out, not an active Structure Watch trigger.
        # (Was age<=90 - kept a 22-bar-old Mycronic Gartley on the list for a month.)
        if h.get("bullish") or h.get("age_bars", 0) > MAX_STRUCTURE_AGE_BARS:
            continue
        d = h.get("d_price")
        if d is None:
            continue
        dist = abs(price - d) / atr
        if dist <= FAR_PRZ_ATR and (best is None or dist < best["dist_atr"]):
            best = {"name": h.get("name", "harmonic"), "dist_atr": round(dist, 2),
                    "status": "completed" if dist <= NEAR_PRZ_ATR else "near",
                    "d_price": round(float(d), 2),
                    "age_bars": int(h.get("age_bars", 0)),
                    "scored_conflict": dist <= NEAR_PRZ_ATR}
    out["bearish_harmonic"] = best
    ell = ctx.get("elliott")
    if isinstance(ell, dict):
        status = str(ell.get("status", "")).upper()
        direction = str(ell.get("direction", "")).upper()
        structure = ell.get("structure", "count")
        wave = str(ell.get("current_wave", ""))
        done = "COMPLETE" in status
        age = ell.get("age_bars")
        # v3.9.3: a completed correction is a live reversal-buy trigger only if it
        # bottomed recently (<= MAX_STRUCTURE_AGE_BARS). Fail-open when age is
        # unknown (None) so a plumbing gap never silently empties the section.
        stale_completion = age is not None and age > MAX_STRUCTURE_AGE_BARS
        if direction == "BEARISH" and done and not stale_completion:
            out["elliott_buy"] = {
                "structure": structure, "wave": wave, "status": status,
                "kind": "reversal", "completed": True,
                "age_bars": (int(age) if age is not None else None),
                "signal": (f"{structure} correction complete — downside exhausted "
                           "(reversal buy)")}
        elif direction == "BULLISH" and not done and "5" not in wave:
            # In-progress continuation is inherently current; not gated on age.
            out["elliott_buy"] = {
                "structure": structure, "wave": wave, "status": status,
                "kind": "continuation", "completed": False,
                "age_bars": (int(age) if age is not None else None),
                "signal": f"bullish {structure} in progress ({wave}) — continuation buy"}
    return out


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
                proxy_note: Optional[str] = None,
                calibration: Optional[dict] = None,
                event_context: Optional[dict] = None,
                volumes: Optional[list] = None,
                market_regime: Optional[dict] = None,
                fundamentals: Optional[dict] = None,
                news_context: Optional[dict] = None,
                sector_context: Optional[dict] = None,
                fx_context: Optional[dict] = None,
                spread_quote: Optional[dict] = None):
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

    # -- levels + timing (computed BEFORE conflicts so corporate-event windows
    #    can feed the score; ATR risk model unchanged, explicit invalidation) --
    entry = round(price, 2)
    stop = round(entry - STOP_ATR_MULT * atr, 2)
    risk = entry - stop
    target = round(entry + REWARD_RISK * risk, 2)

    # -- geometry gate: levels that are not strictly ordered are not a setup.
    #    A long setup requires 0 < stop < entry < target. Malformed provider
    #    OHLCV (e.g. high=low=0.0 on a NAV series) inflates ATR toward the
    #    asset price and pushes stop to or below zero, which would otherwise
    #    be published and logged as a tradeable level. Refuse here, before the
    #    setup becomes ledger-eligible. No threshold is invented and no level
    #    is repaired - the setup is simply not emitted. --
    if not all(math.isfinite(v) for v in (entry, stop, target)):
        return None
    if not (0.0 < stop < entry < target):
        return None

    # Exchange calendar for target-date math (crypto trades 7 days/week).
    if asset_class == "crypto":
        cal_days, hols = True, frozenset()
    elif symbol.upper().endswith(".ST"):
        cal_days, hols = False, SWEDISH_HOLIDAYS
    else:
        cal_days, hols = False, US_HOLIDAYS

    timing = _time_to_target(closes, lows, atr, entry, target, boll, as_of,
                             calibration=calibration, highs=highs,
                             holidays=hols, calendar_days=cal_days)

    # -- shared structural pivots for S/R, fib price clusters and pitchfork --
    pivots = zigzag_pivots(highs, lows, atr, max_pivots=12)
    sr = _support_resistance(pivots, price, atr, target)
    fibp = _fib_price_levels(pivots, price, atr, target)
    pf = _pitchfork_state(pivots, price, atr, len(closes) - 1)
    vol_state = _volume_state(volumes, breakout)
    # v3.3 components
    obv = _obv_state(closes, volumes)
    prz_vol = _prz_touch_volume((technical_context or {}).get("harmonics", []),
                                highs, lows, volumes, atr)
    news_comp = _news_component(news_context)
    sector_comp = _sector_component(sector_context)

    # -- corporate-event gap risk (earnings / ex-dividend inside the window) --
    event_conflicts, events_summary = _event_flags(
        event_context, as_of or date.today(),
        timing["latest_target_date"], atr)
    if events_summary.get("earnings_in_window"):
        # An earnings gap can render the whole window moot: cap reliability.
        tc = min(timing["timing_confidence"], EARNINGS_TIMING_CONF_CAP)
        timing["timing_confidence"] = round(tc, 2)
        timing["timing_reliability"] = "medium" if tc >= 0.45 else "low"
        timing["timing_reasoning"] += (
            "; earnings inside the window caps timing reliability (gap risk)")

    # -- sub-scores: DYNAMIC normalization. Each component enters the ledger
    #    with (earned, max); the final score is 100 * sum(earned)/sum(max) over
    #    the components whose data EXISTS, so instruments without volume or
    #    fundamentals are compared fairly, never silently penalised. --
    sub: dict = {}
    sub_max: dict = {}

    def _comp(name_: str, earned_: float, max_: float) -> None:
        sub[name_] = earned_
        sub_max[name_] = max_

    _comp("trend_alignment", aligned * W_ALIGNMENT, 3 * W_ALIGNMENT)
    if 0 <= extended_atr <= PULLBACK_ATR_MULT:
        entry_earned = W_ENTRY_PULLBACK
    elif PULLBACK_ATR_MULT < extended_atr <= EXTENDED_ATR_MULT:
        entry_earned = W_ENTRY_MID
    elif extended_atr > EXTENDED_ATR_MULT:
        entry_earned = 0.0
    else:
        entry_earned = W_ENTRY_BELOW
    _comp("entry_zone", entry_earned, W_ENTRY_PULLBACK)
    _comp("daily_rsi",
          W_RSI_BAND if RSI_ENTRY_LOW <= rsi <= RSI_ENTRY_HIGH
          else (1.0 if rsi > RSI_ENTRY_HIGH else 0.0),
          W_RSI_BAND)
    _comp("ma100",
          W_MA100 if (above_ma100 and ma100_rising)
          else (W_MA100 / 2 if above_ma100 else 0.0),
          W_MA100)
    ichi_earned = 0.0
    if ichi:
        if ichi["tenkan_above_kijun"]:
            ichi_earned += W_ICHI_TK
        if ichi["cloud_green"]:
            ichi_earned += W_ICHI_CLOUD
        if ichi["price_above_cloud"]:
            ichi_earned += W_ICHI_PRICE
    _comp("ichimoku", ichi_earned, W_ICHI_TK + W_ICHI_CLOUD + W_ICHI_PRICE)
    _comp("macd", W_MACD if (macd and macd["hist"] > 0) else 0.0, W_MACD)
    _comp("bollinger",
          W_BOLL if (boll and not boll["squeeze"] and 0.35 <= boll["pct_b"] <= 0.9)
          else 0.0,
          W_BOLL)
    # v3.2 components - only enter the denominator when their data exists
    if vol_state is not None:
        _comp("volume", vol_state["earned"], W_VOLUME)
    if sr is not None:
        _comp("support_resistance", sr["earned"], W_SR)
    if fibp is not None:
        _comp("fib_price", fibp["earned"], W_FIBP)
    if pf is not None and not pf.get("stale"):
        _comp("pitchfork", pf["earned"], W_PITCHFORK)
    fund_notes: list = []
    if fundamentals:
        fund_earned, fund_notes = _fundamentals_earned(fundamentals)
        _comp("fundamentals", fund_earned, W_FUND)
    if market_regime is not None:
        _comp("market_regime",
              W_REGIME if market_regime.get("risk_on") else 0.0, W_REGIME)
    if news_comp is not None:
        _comp("news", news_comp["earned"], W_NEWS)
    if sector_comp is not None:
        _comp("sector_relative_strength", sector_comp["earned"], W_SECTOR)
    # bonus: displayed in sub_scores, excluded from normalization
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
        if ichi["chikou_free"]:
            supports.append("Chikou span clear of price (26 bars back)")
        # Hunting-dog stance: a flat Tenkan hugging price while above the Kijun
        # is the dog standing at support waiting for the hunter to catch up.
        if (ichi["tenkan_flat"] and ichi["tenkan_above_kijun"]
                and abs(price - ichi["tenkan"]) <= 0.5 * atr):
            supports.append(
                "flat Tenkan at price with Tenkan above Kijun - "
                "support holding while Kijun catches up")
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
    # v3.9: completed BULLISH structure SCORES (symmetric positive axis to the
    # bearish conflicts above). Supports-only, max 8 — never a conflict, never
    # changes the grade. Absent -> None -> excluded from the dynamic denominator.
    bull_struct = _bullish_structure(technical_context, price, atr, extended_atr)
    if bull_struct is not None:
        _comp("bullish_structure", bull_struct["earned"], W_BULL_STRUCT)
        supports.extend(bull_struct["signals"])
    # v3.9.1: scannable structure flags for the UI (nearest bearish harmonic —
    # completed/near-miss — and any completed Elliott buy). Display-only; the
    # scored conflicts above already reflect the completed-bearish case.
    struct_flags = _structure_flags(technical_context, price, atr)
    conflicts.extend(event_conflicts)   # earnings / ex-dividend gap risk

    # v3.2 structural evidence -> supports / conflicts
    if sr is not None:
        if sr["conflict"]:
            conflicts.append(sr["conflict"])
        elif sr["support"] is not None and sr["support_dist_atr"] is not None \
                and sr["support_dist_atr"] <= SR_SUPPORT_ATR:
            supports.append(f"pivot support ~{sr['support']:.2f} "
                            f"({sr['support_dist_atr']} ATR) beneath price")
    if fibp is not None:
        supports.extend(fibp["notes"])
    if pf is not None and not pf.get("stale"):
        if pf.get("conflict"):
            conflicts.append(pf["conflict"])
        else:
            supports.extend(pf.get("notes", []))
    if vol_state is not None and vol_state["earned"] >= W_VOLUME * 0.75:
        supports.extend(vol_state["notes"])
    if fund_notes:
        supports.append("fundamentals: " + ", ".join(fund_notes))
    if market_regime is not None and not market_regime.get("risk_on"):
        conflicts.append(
            f"market regime risk-off: {market_regime.get('index', 'index')} below "
            "its 200-day MA - bullish setups fight the tape")
    # v3.3 evidence
    if obv is not None:
        if obv["rising"]:
            supports.append("OBV rising (accumulation)")
        elif aligned >= 2:
            conflicts.append("OBV falling while price trends up (distribution divergence)")
    if prz_vol is not None:
        if prz_vol.get("confirmed"):
            supports.append(
                f"bullish {prz_vol['pattern']} PRZ touch on "
                f"{prz_vol['volume_ratio']}x volume (confirmation)")
        elif prz_vol.get("rejection"):
            conflicts.append(
                f"bearish {prz_vol['pattern']} PRZ touch on "
                f"{prz_vol['volume_ratio']}x volume (rejection risk)")
    if news_comp is not None:
        if news_comp["conflict"]:
            conflicts.append(news_comp["conflict"])
        elif news_comp["sentiment"]["label"] == "positive":
            supports.append(
                f"news flow positive ({news_comp['sentiment']['n_scored']} items, "
                "lexicon-derived)")
    if sector_comp is not None:
        if sector_comp["label"] == "sector leader":
            supports.append(f"outperforming sector proxy {sector_comp['proxy']} "
                            "on all measured windows")
        elif sector_comp["label"] == "sector laggard":
            conflicts.append(f"lagging sector proxy {sector_comp['proxy']} "
                             "on all measured windows")
    ell_ctx = (technical_context or {}).get("elliott") or {}
    ell_alt = ell_ctx.get("alternate")
    uncertainty_flags: list = []
    if ell_alt and ell_alt.get("direction") != ell_ctx.get("direction"):
        # v3.4 DEMOTION (backtest-evidenced, 2026-07-11, n=504): this fired in
        # 83% of entries and saturated the Conflicted label, making the
        # conflict count non-monotone (2-conflict bucket hit 28.4% vs 37.0% at
        # 3+). An alternate count with opposite direction is NORMAL Elliott
        # ambiguity, not hard contra-evidence - the engine always publishes an
        # alternate when one is valid. Demoted to an informational uncertainty
        # flag: fully visible (field + debug), never scored, never counted.
        # A hard bearish PREFERRED count still penalizes via _context_conflicts.
        uncertainty_flags.append(
            f"Elliott alternate count ({ell_alt.get('direction', '?').lower()} "
            f"{ell_alt.get('structure', '')}) contradicts the preferred count - "
            "count uncertainty (informational, not scored)")

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

    # Liquidity screen: 20-day average turnover (price x volume, instrument
    # currency). Thin instruments can show clean bars but be expensive to trade.
    turnover_20d = None
    if vol_state is not None and len(closes) >= 21:
        turnover_20d = sum(c * v for c, v in zip(closes[-20:], volumes[-20:])) / 20
        pen["liquidity_penalty"] = LIQ_PENALTY if turnover_20d < LIQ_MIN_TURNOVER else 0.0

    # v3.3: execution-cost (spread) model - real bid/ask when supplied, else proxy.
    spread = _spread_model(price, atr, turnover_20d, asset_class,
                           bool(proxy_note),
                           bid=(spread_quote or {}).get("bid"),
                           ask=(spread_quote or {}).get("ask"))
    if spread is not None and spread["wide"]:
        pen["spread_penalty"] = SPREAD_PENALTY
        conflicts.append(
            f"wide spread ~{spread['spread_pct']}% ({spread['spread_source']}) - "
            "execution cost eats into the 2:1 reward:risk")

    # v3.3: FX risk on non-reporting-currency instruments (unhedged exposure).
    if fx_context is not None:
        fx_vol = fx_context.get("vol_ann_pct")
        if isinstance(fx_vol, (int, float)) and fx_vol >= FX_VOL_PENALTY_AT:
            pen["fx_risk_penalty"] = FX_PENALTY
            conflicts.append(
                f"elevated FX volatility ({fx_context.get('pair')} "
                f"~{fx_vol:.0f}% ann.) on an unhedged non-SEK instrument")

    # Dynamic normalization: score over the components whose data exists.
    raw = sum(v for k, v in sub.items() if k in sub_max)
    raw_max = sum(sub_max.values())
    base_score = 100.0 * raw / raw_max if raw_max > EPS else 0.0
    bonus = sub["monthly_rsi_reversal_bonus"]
    score = max(0.0, min(100.0, base_score + bonus - sum(pen.values())))

    # -- grade (stricter than v2: MA100 + zero-conflict gate for A) --
    entry_ok = (extended_atr <= EXTENDED_ATR_MULT) and (RSI_ENTRY_LOW <= rsi <= RSI_ENTRY_HIGH)
    if (aligned == 3 and entry_ok and 0 <= extended_atr <= PULLBACK_ATR_MULT
            and above_ma100 and len(conflicts) == 0):
        grade = "A"
    elif aligned >= 2 and entry_ok and len(conflicts) <= 1:
        grade = "B"
    else:
        grade = "C"
    # A risk-off tape caps the grade: no A-grade buys against the index regime.
    if market_regime is not None and not market_regime.get("risk_on") and grade == "A":
        grade = "B"

    classification, setup_type, risk_level = _classify(
        aligned=aligned, extended_atr=extended_atr, monthly_rsi=monthly_rsi,
        long_term_up=long_term_up, above_ma100=above_ma100,
        n_conflicts=len(conflicts), data_limited=data_limited, grade=grade,
        breakout=breakout, ichi=ichi, boll=boll)

    # A window that spans an earnings report is never better than Elevated risk.
    if events_summary.get("earnings_in_window") and risk_level == "Moderate":
        risk_level = "Elevated"

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
        sub_scores_max={k: round(v, 1) for k, v in sub_max.items()},
        penalties={k: round(v, 1) for k, v in pen.items()},
        market_regime=market_regime,
        volume=({k: (round(v, 1) if isinstance(v, float) else v)
                 for k, v in vol_state.items()} if vol_state else None),
        support_resistance=sr,
        fib_price_levels=fibp,
        pitchfork=pf,
        fundamentals_notes=fund_notes or None,
        liquidity_turnover_20d=(round(turnover_20d) if turnover_20d is not None else None),
        # v3.3
        news=({"score": news_comp["earned"], "max": W_NEWS,
               "sentiment": news_comp["sentiment"], "source": news_comp["source"],
               "as_of": news_comp["as_of"],
               "top_items": (news_context or {}).get("items", [])[:4]}
              if news_comp else None),
        bullish_structure=bull_struct,   # v3.9: scored bullish harmonic/Elliott confluence
        structure_flags=struct_flags,    # v3.9.1: scannable bearish-harmonic + Elliott-buy flags
        sector_relative_strength=sector_comp,
        spread=spread,
        fx=fx_context,
        obv=obv,
        prz_volume=prz_vol,
        elliott_preferred=({k: v for k, v in ell_ctx.items() if k != "alternate"}
                           if ell_ctx else None),
        elliott_alternates=([ell_alt] if ell_alt else []),
        uncertainty_flags=uncertainty_flags,   # v3.4: visible, never scored
        intraday={"intraday_available": False,
                  "fallback_reason": "intraday refinement runs for selected "
                                     "finalists only (see router)"},
        conflicts=conflicts, supports=supports,
        strongest_supporting=strongest_sup, strongest_opposing=strongest_opp,
        data_quality={"daily_bars": len(closes),
                      "monthly_rsi_available": monthly_rsi is not None,
                      "weekly_rsi_available": weekly_rsi is not None},
        events=events_summary,
        technical_context_used=technical_context is not None,
        # Per-signal compliance matrix: which required components were actually
        # consulted for THIS signal. Honest False for known-unimplemented parts
        # (prompt-compliance mandate: never imply an input that was not used).
        compliance={
            "trend_daily_weekly_monthly": True,
            "daily_rsi": True,
            "weekly_rsi": weekly_rsi is not None,
            "monthly_rsi": monthly_rsi is not None,
            "ma100": ma100 is not None,
            "ichimoku_state": ichi is not None,
            "ichimoku_time_numbers": True,
            "tenkan_kijun_flattening": ichi is not None,
            "kijun_catchup_risk": ichi is not None,
            "chikou_proxy": ichi is not None,
            "macd": macd is not None,
            "bollinger": boll is not None,
            "atr": True,
            "fib_time_zones": True,
            "trend_based_fib_time": timing["timing_tools_checked"]["trend_based_fib_time"],
            "fib_circles": True,
            "harmonics_consulted": technical_context is not None,
            "elliott_consulted": bool(technical_context and technical_context.get("elliott")),
            "bullish_structure_in_score": bull_struct is not None,   # v3.9
            "earnings_calendar": bool(event_context and event_context.get("next_earnings_date")),
            "dividend_calendar": bool(event_context and event_context.get("next_ex_dividend_date")),
            "ledger_timing_calibration": bool(calibration and calibration.get("reliable")),
            "tax_note_excluded_from_score": True,
            # v3.2: dynamic - True when this signal actually consulted the data
            "volume": vol_state is not None,
            "andrews_pitchfork": pf is not None and not pf.get("stale", False),
            "support_resistance_levels": sr is not None,
            "fib_price_clusters": fibp is not None,
            "fundamentals_in_score": bool(fundamentals),
            "market_regime_filter": market_regime is not None,
            "holiday_calendar": not cal_days,
            "crypto_calendar_days": cal_days,
            "liquidity_screen": turnover_20d is not None,
            # v3.3: dynamic
            "news_in_score": news_comp is not None,
            # v3.6: True when licensed per-item sentiment (Polygon) was scored
            "news_sentiment_licensed": bool(
                news_comp and news_comp["sentiment"].get("n_licensed", 0) > 0),
            "sector_relative_strength": sector_comp is not None,
            "spread_model": spread is not None,
            "spread_real_quote": bool(spread and spread["spread_model_type"] == "quote"),
            "fx_context": fx_context is not None,
            "obv": obv is not None,
            "prz_touch_volume": prz_vol is not None,
            "elliott_alternates": bool(ell_alt),
        },
        debug={
            "raw_score": round(base_score, 1),
            "raw_points": round(raw, 1),
            "raw_points_max": round(raw_max, 1),
            "pivot_count": len(pivots),
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

    if asset_class in ("gold", "oil", "copper", "silver"):
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
