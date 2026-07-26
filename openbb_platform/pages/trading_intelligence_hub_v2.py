# pages/trading_intelligence_hub_v2.py
# Trading Intelligence Hub V2 — 18 New Skills Integrated
#
# SKILLS INTEGRATED (one tab per skill):
#   1.  vcp-screener                → VCP Screener
#   2.  pead-screener               → PEAD Screener
#   3.  macro-regime-detector       → Macro Regime
#   4.  ftd-detector                → FTD Detector
#   5.  exposure-coach              → Exposure Coach
#   6.  institutional-flow-tracker  → Institutional Flow
#   7.  kanchi-dividend-sop         → Kanchi Dividend SOP
#   8.  position-sizer              → Position Sizer
#   9.  sector-analyst              → Sector Analyst
#  10.  scenario-analyzer           → Scenario Analyzer
#  11.  backtest-expert             → Backtest Expert
#  12.  finviz-screener             → FinViz Screener
#  13.  pair-trade-screener         → Pair Trade
#  14.  downtrend-duration-analyzer → Downtrend Analyzer
#  15.  signal-postmortem           → Signal Postmortem
#  16.  strategy-pivot-designer     → Strategy Pivot
#  17.  kanchi-dividend-review-monitor → Kanchi Monitor
#  18.  trader-memory-core          → Trader Memory
#
# Total platform skills: 13 (Hub V1) + 18 (Hub V2) = 31 skills
#
# UI: identical dark theme — plotly_dark, yaxis right, rangeslider=False,
#     hovermode='x unified', scrollZoom=True, spike lines.
# DATA: yfinance (primary). AI: Groq LLaMA 3.3-70B streaming.
# NO st.set_page_config() — called once in app.py.

import datetime
import logging
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from translations import t, inject_rtl_css  # <- NEW [i18n]
import yfinance as yf

_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from openbb import obb as _obb
    _OBB_AVAILABLE: bool = True
except ImportError:
    _OBB_AVAILABLE = False

try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE: bool = True
except ImportError:
    _GROQ_AVAILABLE = False

logger = logging.getLogger("HubV2")

# ─── MODULE CONSTANTS ──────────────────────────────────────────────────────
GROQ_MODEL: str = "llama-3.3-70b-versatile"
MAX_TOKENS:  int = 4096
CACHE_TTL:   int = 300

# VCP Minervini thresholds (from skill doc)
VCP_TREND_SCORE_MIN:        float = 85.0
VCP_CONTRACTION_RATIO:      float = 0.70
VCP_MIN_CONTRACTIONS:       int   = 2
VCP_BREAKOUT_VOLUME_RATIO:  float = 1.5

# FTD O'Neil thresholds (from skill doc)
FTD_CORRECTION_PCT:         float = 3.0   # 3%+ decline triggers state
FTD_RALLY_ATTEMPT_DAYS:     int   = 4     # Day 4+ eligible for FTD

# Position sizer thresholds (from skill doc)
POSITION_RISK_DEFAULT_PCT:  float = 1.0
POSITION_MAX_PCT_DEFAULT:   float = 10.0
KELLY_HALF_FRACTION:        float = 0.5   # Use half-Kelly per skill doc

# Macro regime component weights (from skill doc)
MACRO_REGIME_WEIGHTS: Dict[str, float] = {
    "concentration":    0.25,   # RSP/SPY
    "yield_curve":      0.20,
    "credit":           0.15,   # HYG/LQD
    "size_factor":      0.15,   # IWM/SPY
    "equity_bond":      0.15,   # SPY/TLT
    "sector_rotation":  0.10,   # XLY/XLP
}

# Macro regime ETF proxies
MACRO_ETFS: Dict[str, str] = {
    "RSP":  "Equal Weight S&P",
    "SPY":  "S&P 500",
    "IWM":  "Russell 2000",
    "HYG":  "High Yield Bonds",
    "LQD":  "Investment Grade",
    "TLT":  "20Y Treasury",
    "XLY":  "Consumer Discret.",
    "XLP":  "Consumer Staples",
}

# Sector ETF universe (for sector analyst)
SECTOR_ETFS: Dict[str, str] = {
    "XLK": "Technology",    "XLV": "Healthcare",
    "XLF": "Financials",   "XLI": "Industrials",
    "XLY": "Consumer Discret.", "XLP": "Consumer Staples",
    "XLE": "Energy",        "XLU": "Utilities",
    "XLB": "Materials",    "XLRE": "Real Estate",
    "XLC": "Comm. Services",
}

# Statistical arbitrage pairs (from methodology doc)
STAT_ARB_PAIRS: List[Tuple[str, str, str]] = [
    ("AAPL",  "MSFT",  "Tech Mega-Cap"),
    ("XOM",   "CVX",   "Integrated Oil"),
    ("JPM",   "BAC",   "US Banks"),
    ("KO",    "PEP",   "Beverages"),
    ("GLD",   "SLV",   "Precious Metals"),
    ("TLT",   "IEF",   "Treasury Duration"),
    ("SPY",   "QQQ",   "Broad vs Growth"),
    ("IWM",   "SPY",   "Small vs Large Cap"),
]

# Dividend universe for Kanchi SOP
KANCHI_DIVIDEND_UNIVERSE: List[str] = [
    "JNJ", "PG", "KO", "PEP", "MCD", "MO", "O", "VZ",
    "XOM", "CVX", "ABT", "ABBV", "T", "WMT", "NEE", "D",
    "SO", "DUK", "APD", "EMR", "MMM", "WPC", "MAIN", "ARCC",
]

# TV plotly config
TV_CONFIG: Dict[str, Any] = {
    "scrollZoom": True, "displayModeBar": True,
    "displaylogo": False, "doubleClick": "reset+autosize",
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

# ─── GLOBAL CSS ────────────────────────────────────────────────────────────
HUB_V2_CSS: str = """
<style>
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],
[data-testid="block-container"],section.main,.main .block-container {
    background-color:#000d1a !important;
}
[data-testid="stSidebar"],[data-testid="stSidebar"]>div,
[data-testid="stSidebarContent"] {
    background-color:#0a1222 !important;
    border-right:1px solid rgba(0,229,255,0.08) !important;
}
html,body,[class*="css"],.stApp {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important; line-height:1.75 !important;
}
p,span,li,td,th,label,div {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important; line-height:1.75 !important;
}
h1,h2,h3,h4,h5,h6,
.stMarkdown h1,.stMarkdown h2,.stMarkdown h3,.stMarkdown h4 {
    font-family:'Times New Roman',Times,serif !important;
    font-size:22px !important; font-weight:bold !important;
    color:#F5ECD7 !important; line-height:1.4 !important; margin-bottom:0.5em !important;
}
[data-testid="stMetricLabel"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:14px !important; color:#B0A898 !important;
}
[data-testid="stMetricValue"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:20px !important; font-weight:bold !important; color:#F5ECD7 !important;
}
[data-testid="stMetricDelta"] {
    font-family:'Times New Roman',Times,serif !important; font-size:14px !important;
}
[data-testid="stButton"] button,.stButton button {
    font-family:'Times New Roman',Times,serif !important; font-size:16px !important;
    background-color:#0d2233 !important; color:#E8E0D0 !important;
    border:1px solid rgba(0,229,255,0.25) !important;
}
[data-testid="stButton"] button[kind="primary"] {
    background-color:rgba(0,229,255,0.15) !important; color:#00E5FF !important;
    border:1px solid rgba(0,229,255,0.45) !important;
}
[data-testid="stTabs"] button,.stTabs [role="tab"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:14px !important; color:#E8E0D0 !important; background-color:transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color:#00E5FF !important; border-bottom-color:#00E5FF !important;
}
[data-testid="stAlert"],.stAlert,.stInfo,.stSuccess,.stWarning,.stError {
    background-color:#0d1f33 !important; border-radius:6px !important;
}
[data-testid="stTextInput"] input,[data-testid="stSelectbox"] div,
[data-testid="stNumberInput"] input,textarea {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
    border-color:rgba(0,229,255,0.20) !important;
    font-family:'Times New Roman',Times,serif !important;
}
[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label,
[data-testid="stSlider"] label,[data-testid="stCheckbox"] label,
[data-testid="stMultiSelect"] label {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
[data-testid="stExpander"] {
    background-color:#080f1a !important;
    border:1px solid rgba(0,229,255,0.10) !important; border-radius:6px !important;
}
[data-testid="stExpander"] summary {
    color:#C8C0B0 !important; font-family:'Times New Roman',Times,serif !important;
}
code,pre,.monospace {
    font-family:'Courier New',Courier,monospace !important;
    font-size:13px !important; background-color:#080f1a !important; color:#A8E0C8 !important;
}
strong,b { font-family:'Times New Roman',Times,serif !important; color:#F5ECD7 !important; }
hr { border-color:rgba(232,224,208,0.15) !important; }
::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:#000d1a; }
::-webkit-scrollbar-thumb { background:#3a3028; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#5a4a38; }
[data-testid="stMarkdownContainer"] { color:#E8E0D0 !important; }
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,[data-testid="stSidebar"] div {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
</style>
"""

# ─── SYSTEM PROMPTS ────────────────────────────────────────────────────────
SYS_VCP: str = """You are Mark Minervini's methodology specialist with 20+ years applying the VCP (Volatility Contraction Pattern) in live markets. You identify Stage 2 uptrend stocks forming tight bases near pivot breakout points.
TASK: Analyze the provided stock for VCP pattern quality and provide actionable entry guidance.
MANDATORY OUTPUT STRUCTURE:
VCP QUALITY SCORE: [0-100] | Rating: [Textbook/Strong/Good/Developing/Weak]
EXECUTION STATE: [Pre-breakout/Breakout/Extended/Overextended/Damaged]
STAGE 2 TREND TEMPLATE: Price vs 200MA/150MA/50MA/30MA — 7-point check
VOLATILITY CONTRACTION ANALYSIS:
- T1 depth (first contraction): [%]
- T2 depth (second contraction): [%]
- T3 depth (if applicable): [%]
- Contraction ratio T2/T1: [value] — target < 0.70
PIVOT PRICE: $[X] — specific breakout level from tightest area
STOP-LOSS: $[X] — below tightest handle or prior pivot low
RISK%: [%] from pivot to stop
VOLUME DRY-UP: [YES/NO] — volume decreasing during contraction
BREAKOUT VOLUME REQUIREMENT: [N]x average needed for confirmation
ENTRY GUIDANCE: [Specific entry condition with price trigger]
RATING RATIONALE: [Why this scores as it does — reference VCP criteria]
ALL PRICE LEVELS DERIVED FROM LIVE DATA PROVIDED. Never invent levels."""

SYS_PEAD: str = """You are a PEAD (Post-Earnings Announcement Drift) specialist. You analyze stocks that have gapped up on earnings for the high-probability weekly red candle pullback → breakout pattern.
TASK: Assess PEAD setup quality and determine stage classification.
MANDATORY OUTPUT STRUCTURE:
PEAD STAGE: [MONITORING / SIGNAL_READY / BREAKOUT / EXPIRED]
COMPOSITE SCORE: [0-100] | Setup Rating: [Strong/Good/Developing/Weak]
EARNINGS GAP ANALYSIS:
- Gap size: [%] — initial earnings reaction
- Gap quality: [Clean/Partial fill/Full fill]
- Post-gap trend: [Holding/Fading/Extended]
WEEKLY CANDLE PATTERN:
- Red candle location: [x weeks from earnings]
- Red candle depth: [%] correction from post-earnings high
- Red candle high: $[X] — breakout trigger level
BREAKOUT SETUP:
- Entry trigger: Above $[X] (red candle high)
- Stop-loss: $[X] (red candle low or weekly low)
- Target: $[X] (1.5-2.0x measured move from base)
- Risk/Reward: [N:1]
MONITORING WINDOW: [N weeks remaining before pattern expires]
ENTRY GUIDANCE: [Specific conditions for entry]
DERIVE ALL LEVELS FROM LIVE DATA PROVIDED."""

SYS_MACRO_REGIME: str = """You are a macro regime specialist applying cross-asset ratio analysis to detect structural 1-2 year regime transitions. You use monthly-frequency signals: RSP/SPY concentration, yield curve, credit conditions, size factor, equity-bond relationship, and sector rotation.
TASK: Identify the current macro regime and provide strategic portfolio positioning.
MANDATORY OUTPUT STRUCTURE:
CURRENT REGIME: [Concentration / Broadening / Contraction / Inflationary / Transitional]
REGIME CONFIDENCE: [High/Medium/Low]
TRANSITION PROBABILITY: [%] — probability of regime shift in next 3-6 months
6-COMPONENT ANALYSIS:
1. CONCENTRATION (RSP/SPY ratio): [value, trend] → [Concentration/Broadening]
2. YIELD CURVE (10Y-2Y spread): [value] bps → [Steep/Flat/Inverted] → [implication]
3. CREDIT CONDITIONS (HYG/LQD): [value, trend] → [Risk-On/Risk-Off]
4. SIZE FACTOR (IWM/SPY): [value, trend] → [Small-cap/Large-cap leadership]
5. EQUITY-BOND (SPY/TLT): [value, trend] → [Regime implication]
6. SECTOR ROTATION (XLY/XLP): [value, trend] → [Cyclical/Defensive]
REGIME CHARACTERISTICS: [What this regime means for markets]
PORTFOLIO POSTURE: [Specific strategic allocation for this regime]
TRANSITION INDICATORS: [What signals would confirm a regime change]
1-2 YEAR OUTLOOK: [What comes next based on current regime dynamics]
ALL RATIO VALUES FROM LIVE DATA PROVIDED."""

SYS_FTD: str = """You are William O'Neil's Follow-Through Day methodology specialist, applying the IBD system for market bottom confirmation after corrections.
TASK: Determine the current FTD state and provide re-entry timing guidance.
MANDATORY OUTPUT STRUCTURE:
FTD STATE: [NO_SIGNAL / CORRECTION / RALLY_ATTEMPT / FTD_WINDOW / FTD_CONFIRMED / RALLY_FAILED / FTD_INVALIDATED]
FTD QUALITY SCORE: [0-100]
EXPOSURE GUIDANCE: [0-25% / 25-50% / 50-75% / 75-100%]
STATE MACHINE DETAILS:
- Correction start: [date/price] — [%] decline from peak
- Rally attempt day 1: [date] — must close above prior day low
- Current rally day: [Day N]
- FTD qualification: [Day 4+ with >1.25% gain on higher volume]
KEY LEVELS:
- Swing low (must not be undercut): $[X]
- FTD day low (invalidation level): $[X]
- Prior distribution high (resistance): $[X]
POST-FTD HEALTH:
- Distribution days (last 25 sessions): [N]
- Power Trend status: [ACTIVE/INACTIVE]
RE-ENTRY GUIDANCE: [Specific conditions and initial position size]
ALL PRICES AND DATES FROM LIVE DATA PROVIDED. Never fabricate state transitions."""

SYS_EXPOSURE_COACH: str = """You are an exposure management specialist applying the multi-signal synthesis framework. You synthesize breadth, uptrend ratio, macro regime, top risk, FTD state, sector rotation, and institutional flow into a unified capital deployment decision.
TASK: Generate a Market Posture Summary with exposure ceiling and action recommendation.
MANDATORY OUTPUT STRUCTURE:
MARKET POSTURE SUMMARY
═══════════════════════════════
EXPOSURE CEILING: [0-100]%
BIAS: [GROWTH / VALUE / NEUTRAL]
PARTICIPATION: [BROAD / NARROW / FRAGILE]
RECOMMENDATION: [NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY]
CONFIDENCE: [HIGH / MEDIUM / LOW]
═══════════════════════════════
COMPONENT SIGNAL TABLE:
| Signal | Score | Weight | Contribution | Status |
[8 rows: Breadth, Uptrend, Regime, Top Risk, FTD, Theme, Sector, Institutional]
RATIONALE: [2-3 sentences integrating all signals]
PRACTICAL GUIDANCE:
- New positions: [YES/NO with conditions]
- Position sizing: [% of normal size]
- Sector bias: [specific sectors to overweight/underweight]
- Hedge guidance: [if REDUCE_ONLY or CASH_PRIORITY]
NEXT REVIEW: [What trigger would change this posture]
SAFETY FIRST: Always default to lower exposure when signals conflict."""

SYS_INSTITUTIONAL: str = """You are a 13F filing analyst specializing in institutional money flow detection. You analyze SEC quarterly filings to identify smart money accumulation and distribution patterns with data quality assessment.
TASK: Deliver an institutional ownership analysis report.
MANDATORY OUTPUT STRUCTURE:
SIGNAL STRENGTH: [Strong Bullish / Bullish / Neutral / Bearish / Strong Bearish]
DATA QUALITY GRADE: [A / B / C] — based on coverage ratio and holder match
OWNERSHIP SUMMARY:
- Current institutional ownership: [%]
- Quarter-over-quarter change: [±%]
- Number of institutions: [N] ([±N] vs prior quarter)
TOP HOLDERS ANALYSIS:
| Rank | Institution | Shares | QoQ Change | Signal |
[Top 5 with quality classification]
NEW BUYERS: [List with share count]
MAJOR SELLERS: [List with share count — flag if quality holders]
CONCENTRATION RISK: [Top 10 holders = [%] of institutional total]
SIGNAL INTERPRETATION: [Bullish/Bearish rationale with specific evidence]
INVESTMENT IMPLICATIONS: [How to use this data with technical analysis]
⚠️ DATA LAG NOTE: 13F data reflects positions ~45 days ago. Use as confirming indicator.
ALL DATA FROM PROVIDED QUARTERLY FILINGS. Note data quality limitations explicitly."""

SYS_KANCHI_SOP: str = """You are a Kanchi-style dividend investing specialist, applying the 5-step Japanese dividend methodology adapted for US equities. You prioritize safety and dividend sustainability over yield.
TASK: Apply the full 5-step Kanchi SOP to the provided stock universe.
MANDATORY OUTPUT STRUCTURE:
STEP 1 — YIELD FILTER (≥3.5%):
| Ticker | Yield | Status | Notes |
[PASS / FAIL / DEEP-DIVE-REQUIRED (>8% yield trap flag)]
STEP 2 — GROWTH & SAFETY:
| Ticker | EPS Trend | Div Trend | Payout% | FCF Payout | Safety Score |
[PASS / FAIL / HOLD-FOR-REVIEW]
STEP 3 — VALUATION (sector-adjusted):
- Financials: P/E × P/B
- REITs: P/FFO or P/AFFO
- Asset-light: P/E + P/FCF
| Ticker | Method | Current | Target | Verdict |
STEP 4 — ONE-OFF EVENT FILTER:
| Ticker | One-Off Flags | Clean? | Evidence |
[Identify non-recurring items in earnings]
STEP 5 — BUY ON WEAKNESS ENTRY PLAN:
- Yield trigger: 5Y average yield + 0.5pp → target entry yield
- Valuation trigger: target multiple reached
| Ticker | Entry Yield | Current Yield | Distance | Limit Order Plan |
SOP SUMMARY TABLE: [All tickers with final verdict PASS/HOLD/FAIL]
ONE-PAGE MEMO: For each PASS stock — thesis, invalidation, limit order split plan
ALL DATA FROM LIVE YFINANCE. Flag N/A data explicitly."""

SYS_POSITION_SIZER: str = """You are a risk management specialist applying three position sizing methodologies: Fixed Fractional (1% rule), ATR-Based volatility scaling, and Kelly Criterion (half-Kelly in practice).
TASK: Calculate and compare position sizes for the provided trade setup.
MANDATORY OUTPUT STRUCTURE:
POSITION SIZING ANALYSIS
Entry: $[X] | Stop: $[X] | Risk/Share: $[X]

METHOD 1 — FIXED FRACTIONAL (1% risk):
- Dollar risk: $[X] (1% of $[account])
- Shares: [N] | Position value: $[X]
- Position % of account: [%]

METHOD 2 — ATR-BASED ([N]x ATR):
- ATR([period]): $[X]
- Stop distance ([N]×ATR): $[X]
- Shares: [N] | Position value: $[X]

METHOD 3 — KELLY CRITERION (half-Kelly):
- Win rate: [%] | Avg win: [%] | Avg loss: [%]
- Full Kelly: [%] of account
- Half-Kelly applied: [%] of account
- Shares: [N] | Position value: $[X]

PORTFOLIO CONSTRAINTS:
- Max position (10%): [shares] — [BINDING/not binding]
- Max sector ([%]): [shares] — [BINDING/not binding]

FINAL RECOMMENDED SHARES: [N] — [Method] — [Binding constraint if any]
PORTFOLIO HEAT CHECK: Open risk with this trade = [%] of account

KEY PRINCIPLES: Survival first. Round down. Strictest constraint wins.
ALL CALCULATIONS FROM PROVIDED INPUTS. Never round up shares."""

SYS_SECTOR_ANALYST: str = """You are a sector rotation specialist applying Monty's sector uptrend ratio data and the classical market cycle framework to rank sectors and identify rotation opportunities.
TASK: Deliver a comprehensive sector rotation analysis with cycle phase estimation and positioning recommendations.
MANDATORY OUTPUT STRUCTURE:
MARKET CYCLE PHASE: [Early Recovery / Mid Expansion / Late Cycle / Recession]
CYCLE CONFIDENCE: [%] — strength of confirming signals
RISK REGIME: [CYCLICAL / DEFENSIVE / BALANCED] — score and direction
SECTOR RANKING (by uptrend ratio and momentum):
| Rank | Sector | ETF | 1M Ret | 3M Ret | vs MA50 | vs MA200 | Signal |
[11 sectors ranked from strongest to weakest]
CYCLICAL vs DEFENSIVE:
- Cyclical avg return: [%] | Defensive avg: [%]
- Spread: [%] → [Risk-On/Risk-Off indicator]
OVERBOUGHT SECTORS (>2 std dev above norm): [List with flag]
OVERSOLD SECTORS (<2 std dev below norm): [List with opportunity flag]
SCENARIO ANALYSIS (2-3 scenarios, sum to 100%):
1. [Most likely — X%]: [Rotation implication, 3-month outlook]
2. [Alternative — Y%]: [Different rotation path]
3. [Contrarian — Z%]: [Low probability but technically plausible]
POSITIONING RECOMMENDATIONS:
- Overweight: [2-3 sectors with rationale]
- Underweight: [2-3 sectors with rationale]
- Tactical opportunity: [Specific short-term trade]
ALL DATA FROM LIVE SECTOR ETF PRICES. Reference specific return figures."""

SYS_SCENARIO: str = """You are a senior fund manager with 20+ years of experience building 18-month investment scenarios from macro events. You provide first-principles analysis with explicit probability distribution.
TASK: Build comprehensive Base/Bull/Bear scenarios for the provided headline/topic.
MANDATORY OUTPUT STRUCTURE:
EVENT TYPE: [Monetary Policy / Geopolitical / Technology / Commodity / Corporate]
RELATED NEWS: [List 3-5 related recent developments]
18-MONTH SCENARIOS (must sum to 100%):

BASE CASE ([X]%):
- Timeline: 0-6M: [developments] | 6-12M: [developments] | 12-18M: [outcomes]
- Key assumption: [what must hold for this scenario]
- GDP/Inflation/Rate implications: [specific]

BULL CASE ([Y]%):
[Same structure — optimistic outcome]

BEAR CASE ([Z]%):
[Same structure — pessimistic outcome]

SECTOR IMPACT MAP (1st/2nd/3rd order):
| Order | Sector | Direction | Mechanism |
[1st = direct, 2nd = supply chain, 3rd = macro/regulatory]

POSITIVE IMPACT STOCKS (3-5 US-listed):
| Ticker | Company | Rationale | Historical analog |

NEGATIVE IMPACT STOCKS (3-5 US-listed):
| Ticker | Company | Rationale | Historical analog |

MONITORING CHECKLIST: [3-5 data points to watch that would shift probabilities]
PROBABILITY REVISION TRIGGER: [Specific event that would change case allocation]
ALL OUTPUT IN ENGLISH. Probabilities must sum to 100%."""

SYS_BACKTEST: str = """You are a systematic trading strategy evaluation expert applying the 'beat ideas to death' backtesting philosophy. You score strategies across 5 dimensions and deliver Deploy/Refine/Abandon verdicts.
TASK: Evaluate the provided strategy/idea against rigorous backtesting criteria.
MANDATORY OUTPUT STRUCTURE:
STRATEGY EVALUATION REPORT

EDGE HYPOTHESIS: [One sentence — what is the testable edge?]

5-DIMENSION SCORING (0-100 each):
1. SAMPLE SIZE (weight 20%): [Score] — [N] trades over [Y] years
   - Minimum: 30 trades | Preferred: 100+ | High confidence: 200+
   - Verdict: [Sufficient/Borderline/Insufficient]

2. EXPECTANCY (weight 25%): [Score] — Win rate [%] × Avg win [%] - Loss rate × Avg loss [%]
   - Expectancy per trade: [$X]
   - R-multiple: [Win:Loss ratio]

3. RISK MANAGEMENT (weight 20%): [Score] — Max drawdown [%], drawdown duration [N days]
   - Recovery factor: [Annual return / Max drawdown]

4. ROBUSTNESS (weight 20%): [Score] — Parameter sensitivity, out-of-sample vs in-sample
   - OOS/IS ratio: [value — <0.5 = concerning]
   - Year-by-year: [positive in [N]/[Y] years]

5. EXECUTION REALISM (weight 15%): [Score] — Slippage model, fill assumptions
   - Realistic slippage applied: [YES/NO]
   - Commission structure: [$/trade or bps]

COMPOSITE SCORE: [0-100]

RED FLAGS DETECTED: [List specific concerns]
STRESS TEST RESULTS: [Parameter sensitivity summary]

VERDICT: [DEPLOY / REFINE / ABANDON]
[Deploy: >70 composite, no critical red flags]
[Refine: Core logic sound, specific weaknesses]
[Abandon: Fundamental edge issue, overfitting, execution failure]

ACTION PLAN: [Specific next steps — never invent domain values]"""

SYS_FINVIZ: str = """You are a FinViz screener specialist who translates natural-language stock screening requests into structured filter criteria and provides specific actionable screening guidance.
TASK: Interpret the user's screening request, build a precise filter set, and provide results analysis.
MANDATORY OUTPUT STRUCTURE:
SCREENING INTERPRETATION:
- Universe: [US equities / sector / market cap]
- Core filters: [list with value]
- Technical filters: [list]
- Fundamental filters: [list]

FINVIZ FILTER CODES:
[Table: Filter | Code | Value | Meaning]

SCREENING URL STRUCTURE:
Base: https://finviz.com/screener.ashx?v=111&f=
Filters: [comma-separated codes]

RESULTS ANALYSIS (based on live data provided):
- Stocks meeting criteria from universe: [N]
- Top 5 by [primary sort criterion]:
  | Ticker | Key Metrics | Why it qualifies |

ITERATIVE REFINEMENT SUGGESTIONS:
- To tighten: [add these filters]
- To broaden: [remove these filters]
- View recommendation: [overview/valuation/technical]

RECIPE CLASSIFICATION: [Momentum/Value/Growth/Income/Turnaround]
ALL FILTER CODES FROM FINVIZ DOCUMENTATION. Never invent non-existent filters."""

SYS_PAIR_TRADE: str = """You are a statistical arbitrage specialist applying the pairs trading methodology: cointegration testing, z-score mean reversion, and half-life estimation. You identify mispriced spreads with defined entry/exit rules.
TASK: Analyze the provided pair for trading opportunity.
MANDATORY OUTPUT STRUCTURE:
PAIR ANALYSIS: [Ticker A] vs [Ticker B] — [Pair Category]

COINTEGRATION:
- Correlation (1Y daily returns): [value — >0.75 required]
- Spread behavior: [Mean-reverting/Trending/Unstable]
- Estimated half-life: [N days — target 5-30 days]

CURRENT SPREAD POSITION:
- Spread (A-ratio×B): [value]
- Z-score: [value] (std devs from mean)
- Z-score signal: [ENTRY_LONG_A/ENTRY_LONG_B/NEUTRAL/EXIT]

TRADE SIGNAL:
- Direction: [LONG A / SHORT B] or [LONG B / SHORT A] or NEUTRAL
- Signal strength: [Strong/Moderate/Weak] (|Z-score| [value])

ENTRY RULES:
- Enter when |Z-score| > 2.0 — current: [value — SIGNAL/NO SIGNAL]
- Exit when Z-score → 0 (expected: [N days])
- Stop-loss: Z-score > 3.5 (spread breakdown)

POSITION SIZING:
- Dollar-neutral: $[X] long, $[X] short
- Risk estimate: [%] of position if stop triggered

RISK FACTORS: [Pair-specific risks — fundamental decoupling, corporate events]
ALL Z-SCORES AND RATIOS FROM LIVE PRICE DATA PROVIDED."""

SYS_DOWNTREND: str = """You are a market correction duration analyst applying statistical peak-to-trough methodology across sectors and market cap tiers.
TASK: Analyze historical downtrend durations for the specified universe and provide realistic holding period expectations.
MANDATORY OUTPUT STRUCTURE:
DOWNTREND DURATION ANALYSIS

UNIVERSE: [Sector/Market cap specified]
ANALYSIS PERIOD: [N years] — [start date to end date]

SUMMARY STATISTICS:
| Metric | Value |
| Median duration | [N] trading days |
| Mean duration | [N] trading days |
| P25 (short correction) | [N] days |
| P75 (extended correction) | [N] days |
| P90 (prolonged correction) | [N] days |

BY MARKET CAP:
| Tier | Count | Median | Mean | Implication |
| Mega (>$200B) | ... |
| Large ($10-200B) | ... |
| Mid ($2-10B) | ... |
| Small (<$2B) | ... |

KEY INSIGHTS:
1. [Largest caps recover fastest — quantify]
2. [Current sector vs historical median]
3. [% of corrections resolved within 40 days]

STRATEGY IMPLICATIONS:
- Mean reversion holding period: [N days — P50 for target sector/cap]
- Stop-loss timeout: [P75 days — exit if correction extends beyond]
- Position sizing: [Adjust for longer-duration corrections in smaller caps]

ALL STATISTICS FROM LIVE PRICE HISTORY PROVIDED."""

SYS_POSTMORTEM: str = """You are a trading signal quality analyst who performs systematic post-trade outcome attribution to improve future signal quality.
TASK: Analyze the provided signal outcomes and generate actionable feedback.
MANDATORY OUTPUT STRUCTURE:
SIGNAL POSTMORTEM REPORT

SIGNALS ANALYZED: [N] | Period: [date range]

OUTCOME CLASSIFICATION:
| Category | Count | % | Avg Return |
| TRUE_POSITIVE | N | % | +[%] |
| FALSE_POSITIVE | N | % | -[%] |
| MISSED_OPPORTUNITY | N | % | +[%] (not taken) |
| REGIME_MISMATCH | N | % | [%] |

BY SOURCE SKILL:
| Skill | Signals | Win Rate | Avg Return | Grade | Suggested Weight |

REGIME CONTEXT:
- Signals in RISK_ON: [win rate] — [N] signals
- Signals in RISK_OFF: [win rate] — [N] signals
- Mismatch rate: [%] signals failed due to regime shift

FALSE POSITIVE PATTERNS:
[Identify systematic failure modes — sector, timing, market regime]

WEIGHT ADJUSTMENT RECOMMENDATIONS:
| Skill | Current Weight | Suggested Weight | Reason |
[Note: minimum 20 signals per skill for adjustment validity]

SKILL IMPROVEMENT BACKLOG:
| Priority | Skill | Issue | Suggested Action |

OVERALL EDGE ASSESSMENT: [Is the combined signal set generating positive expectancy?]
ALL RETURN CALCULATIONS FROM PROVIDED PRICE DATA. Note sample size limitations."""

SYS_PIVOT: str = """You are a strategy design architect who diagnoses backtest stagnation and generates structurally different strategy pivot proposals.
TASK: Analyze the stagnation pattern and propose 3 structurally distinct pivots.
MANDATORY OUTPUT STRUCTURE:
STAGNATION DIAGNOSIS

ITERATION HISTORY SUMMARY:
- Iterations analyzed: [N]
- Performance plateau start: [iteration N]
- Plateau severity: [score range, [%] improvement over last N iterations]

STAGNATION TRIGGERS DETECTED:
[List from: PLATEAU / OVERFITTING / COST_DEFEAT / TAIL_RISK]

PIVOT PROPOSALS (3 structurally distinct):

PIVOT 1 — ASSUMPTION INVERSION:
- Original assumption: [what the strategy assumed]
- Inverted assumption: [what the pivot assumes instead]
- New strategy skeleton: [brief description]
- Quality potential: [0-100] | Novelty: [High/Medium/Low]
- Export ready: [YES/NO]

PIVOT 2 — ARCHETYPE SWITCH:
- Original archetype: [Momentum/Mean-reversion/Breakout/etc.]
- New archetype: [different approach]
- Strategy skeleton: [brief description]
- Quality potential: [0-100] | Novelty: [High/Medium/Low]
- Export ready: [YES/NO]

PIVOT 3 — OBJECTIVE REFRAME:
- Original objective: [what was being optimized]
- Reframed objective: [different optimization target]
- Strategy skeleton: [brief description]
- Quality potential: [0-100] | Novelty: [High/Medium/Low]
- Export ready: [YES/NO]

RECOMMENDED NEXT STEP: [Which pivot to prototype first and why]
TIME ALLOCATION: 20% generating ideas, 80% breaking them."""

SYS_KANCHI_MONITOR: str = """You are a dividend portfolio risk monitoring specialist applying the Kanchi T1-T5 trigger system for systematic anomaly detection and review queueing.
TASK: Analyze the provided portfolio for T1-T5 triggers and classify each position as OK/WARN/REVIEW.
MANDATORY OUTPUT STRUCTURE:
DIVIDEND PORTFOLIO MONITOR REPORT

PORTFOLIO SUMMARY:
- Positions analyzed: [N]
- OK: [N] | WARN: [N] | REVIEW: [N]
- Review queue items requiring immediate action: [N]

TRIGGER MATRIX RESULTS:
| Ticker | T1(Cut) | T2(Cover) | T3(Credit) | T4(SEC) | T5(Decline) | Status |
[For each holding — OK/WARN/REVIEW per trigger]

REVIEW QUEUE (IMMEDIATE ACTION REQUIRED):
For each REVIEW position:
- Ticker: [X]
- Trigger(s) fired: [T1/T2/T3/T4/T5]
- Evidence: [specific data point that triggered]
- Failure mode suspected: [dividend cut / coverage deterioration / governance]
- Required manual checks: [specific actions before any trade]

WARN POSITIONS (MONITOR CLOSELY):
[Brief summary — no immediate action but add to next check cycle]

OK POSITIONS: [Confirmation — no anomalies detected]

NON-NEGOTIABLE RULE: NEVER recommend auto-sell based on machine triggers alone.
Always escalate REVIEW items to human confirmation first.

NEXT CADENCE: [Daily/Weekly/Quarterly items scheduled]"""

SYS_TRADER_MEMORY: str = """You are a systematic investment thesis manager applying the lifecycle tracking framework: IDEA → ENTRY_READY → ACTIVE → CLOSED with full postmortem.
TASK: Process the provided thesis information and generate structured thesis documentation.
MANDATORY OUTPUT STRUCTURE:
THESIS TRACKER REPORT

THESIS REGISTRATION:
- Thesis ID: [generated from ticker + type + date]
- Ticker: [X] | Type: [dividend_income/growth_momentum/mean_reversion/earnings_drift/pivot_breakout]
- Status: [IDEA/ENTRY_READY/ACTIVE/CLOSED]
- Created: [date]

THESIS DETAILS:
- Setup type: [VCP/PEAD/FTD/Kanchi/Edge/etc.]
- Catalyst: [specific trigger]
- Target entry: $[X] | Target exit: $[X] | Stop: $[X]
- Expected holding: [N days/weeks]

MONITORING SCHEDULE:
- Review cadence: [Daily/Weekly/Quarterly]
- T1-T5 triggers (if dividend): [applicable triggers]
- Next review date: [calculated]

LIFECYCLE HISTORY:
| Date | Status | Event | Notes |

POSITION SIZING (if ENTRY_READY):
- Method: [Fixed Fractional/ATR/Kelly]
- Shares: [N] | Value: $[X] | Risk: $[X]

POSTMORTEM (if CLOSED):
- Entry: $[X] → Exit: $[X]
- P&L: [%] over [N days]
- MAE (max adverse excursion): [%]
- MFE (max favorable excursion): [%]
- Lessons learned: [specific, actionable]

FORWARD-ONLY: Status cannot regress. IDEA→ENTRY_READY→ACTIVE→CLOSED only."""

# ─── CHART UTILITIES (identical to hub v1) ────────────────────────────────
def _tv_xaxis(**kw: Any) -> Dict[str, Any]:
    """Returns TradingView-quality x-axis config."""
    b: Dict[str, Any] = {
        "rangeslider_visible": False, "type": "date",
        "gridcolor": "rgba(128,128,128,0.06)", "showgrid": True, "zeroline": False,
        "showspikes": True, "spikecolor": "rgba(200,200,200,0.55)",
        "spikethickness": 1, "spikedash": "dot", "spikemode": "across",
        "tickfont": {"color": "#8a8a8a", "size": 10},
    }
    b.update(kw)
    return b

def _tv_yaxis(**kw: Any) -> Dict[str, Any]:
    """Returns TradingView-quality y-axis config. Side=right always."""
    b: Dict[str, Any] = {
        "side": "right", "gridcolor": "rgba(128,128,128,0.06)",
        "showgrid": True, "zeroline": False, "fixedrange": False,
        "showspikes": True, "spikecolor": "rgba(200,200,200,0.55)",
        "spikethickness": 1, "spikedash": "dot", "spikemode": "across",
        "tickfont": {"color": "#8a8a8a", "size": 10},
    }
    b.update(kw)
    return b

def _tv_layout(height: int = 480, title: str = "", **kw: Any) -> Dict[str, Any]:
    """Returns base TradingView-quality layout."""
    layout: Dict[str, Any] = {
        "template": "plotly_dark", "height": height,
        "hovermode": "x unified", "dragmode": "zoom",
        "margin": {"l": 10, "r": 100, "t": 50, "b": 10},
        "paper_bgcolor": "#000d1a", "plot_bgcolor": "#000d1a",
        "hoverdistance": 25, "spikedistance": -1, "showlegend": True,
        "legend": {
            "bgcolor": "rgba(14,17,23,0.85)",
            "bordercolor": "rgba(128,128,128,0.30)", "borderwidth": 1,
            "font": {"color": "#e0e0e0", "size": 9},
            "orientation": "h", "yanchor": "bottom", "y": 1.01,
            "xanchor": "left", "x": 0,
        },
    }
    if title:
        layout["title"] = {"text": title, "font": {"color": "#00E5FF", "size": 13, "family": "monospace"}}
    layout.update(kw)
    return layout

# ─── DATA UTILITIES ───────────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL)
def _fetch_info(ticker: str) -> Dict[str, Any]:
    """Fetches stock fundamentals via yfinance."""
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        if not info or len(info) < 5:
            return {}
        return {
            "name":             info.get("longName") or info.get("shortName") or ticker,
            "sector":           info.get("sector", "Unknown"),
            "industry":         info.get("industry", "Unknown"),
            "currency":         info.get("currency", "USD"),
            "market_cap":       info.get("marketCap"),
            "current_price":    info.get("currentPrice") or info.get("regularMarketPrice"),
            "52w_high":         info.get("fiftyTwoWeekHigh"),
            "52w_low":          info.get("fiftyTwoWeekLow"),
            "pe_ratio":         info.get("trailingPE"),
            "forward_pe":       info.get("forwardPE"),
            "pb_ratio":         info.get("priceToBook"),
            "ev_ebitda":        info.get("enterpriseToEbitda"),
            "peg_ratio":        info.get("pegRatio"),
            "debt_to_equity":   info.get("debtToEquity"),
            "current_ratio":    info.get("currentRatio"),
            "dividend_yield":   info.get("dividendYield"),
            "dividend_rate":    info.get("dividendRate"),
            "payout_ratio":     info.get("payoutRatio"),
            "five_yr_avg_div":  info.get("fiveYearAvgDividendYield"),
            "revenue_growth":   info.get("revenueGrowth"),
            "earnings_growth":  info.get("earningsGrowth"),
            "profit_margin":    info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "roe":              info.get("returnOnEquity"),
            "roa":              info.get("returnOnAssets"),
            "total_revenue":    info.get("totalRevenue"),
            "ebitda":           info.get("ebitda"),
            "total_debt":       info.get("totalDebt"),
            "total_cash":       info.get("totalCash"),
            "free_cashflow":    info.get("freeCashflow"),
            "beta":             info.get("beta"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "short_ratio":      info.get("shortRatio"),
            "recommendation":   info.get("recommendationKey"),
            "target_mean_price": info.get("targetMeanPrice"),
            "analyst_count":    info.get("numberOfAnalystOpinions"),
            "description":      (info.get("longBusinessSummary") or "")[:400],
        }
    except Exception as e:
        logger.error(f"_fetch_info [{ticker}]: {e}")
        return {}

@st.cache_data(ttl=CACHE_TTL)
def _fetch_history(ticker: str, years: int = 2) -> pd.DataFrame:
    """Fetches OHLCV price history via yfinance (OpenBB fallback)."""
    start_str = (datetime.date.today() - datetime.timedelta(days=365 * years)).strftime("%Y-%m-%d")
    if _OBB_AVAILABLE:
        try:
            res = _obb.equity.price.historical(ticker, start_date=start_str, provider="yfinance")
            df  = res.to_df()
            if not df.empty:
                df.index = pd.to_datetime(df.index)
                return df
        except Exception:
            pass
    try:
        t  = yf.Ticker(ticker)
        df = t.history(start=start_str, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        df.index   = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.error(f"_fetch_history [{ticker}]: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def _fetch_sector_data() -> Dict[str, Any]:
    """Fetches sector ETF data for rotation analysis."""
    result: Dict[str, Any] = {}
    for etf, name in SECTOR_ETFS.items():
        try:
            t  = yf.Ticker(etf)
            df = t.history(period="1y", auto_adjust=True)
            if df.empty or len(df) < 50:
                continue
            cur    = float(df["Close"].iloc[-1])
            ma50   = float(df["Close"].rolling(50).mean().iloc[-1])
            ma200  = float(df["Close"].rolling(200).mean().iloc[-1]) if len(df) >= 200 else float("nan")
            m1_ret = (cur / float(df["Close"].iloc[-21]) - 1.0) * 100.0 if len(df) >= 21 else 0.0
            m3_ret = (cur / float(df["Close"].iloc[-63]) - 1.0) * 100.0 if len(df) >= 63 else 0.0
            result[etf] = {
                "sector": name, "price": cur, "ma50": ma50, "ma200": ma200,
                "1m_return": m1_ret, "3m_return": m3_ret,
                "above_ma50": cur > ma50,
                "above_ma200": cur > ma200 if not math.isnan(ma200) else False,
            }
        except Exception as e:
            logger.debug(f"Sector [{etf}]: {e}")
    return result

# ─── NUMERIC HELPERS ──────────────────────────────────────────────────────
def _flt(v: Any, fmt: str = ".2f", suffix: str = "") -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):{fmt}}{suffix}"
    except (TypeError, ValueError):
        return "N/A"

def _pct(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100.0:.1f}%"
    except (TypeError, ValueError):
        return "N/A"

def _bn(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if abs(f) >= 1e12:
            return f"${f / 1e12:.1f}T"
        if abs(f) >= 1e9:
            return f"${f / 1e9:.1f}B"
        if abs(f) >= 1e6:
            return f"${f / 1e6:.1f}M"
        return f"${f:.0f}"
    except (TypeError, ValueError):
        return "N/A"

# ─── GROQ STREAMING ───────────────────────────────────────────────────────
def _stream(
    api_key:       str,
    system_prompt: str,
    user_content:  str,
    placeholder:   st.delta_generator.DeltaGenerator,
    max_tokens:    int = MAX_TOKENS,
) -> str:
    """Streams Groq response into an st.empty() placeholder."""
    if not _GROQ_AVAILABLE:
        raise RuntimeError("groq package not installed. Run: pip install groq")
    client = _Groq(api_key=api_key)
    full: str = ""
    try:
        stream = client.chat.completions.create(
            model=GROQ_MODEL, max_tokens=max_tokens, stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta is not None:
                full += delta
                placeholder.markdown(full + "▌")
        placeholder.markdown(full)
        return full
    except Exception as e:
        err = str(e)
        if "401" in err or "authentication" in err.lower():
            raise RuntimeError("Invalid GROQ_API_KEY.")
        if "429" in err or "rate" in err.lower():
            raise RuntimeError("Groq rate limit. Wait 60 seconds.")
        raise RuntimeError(f"Groq API error: {e}")

# ─── SHARED UI HELPERS ────────────────────────────────────────────────────
def _tab_header(skill_name: str, color: str, title: str, description: str) -> None:
    """Renders the standard skill card header."""
    st.markdown(
        f"""<div style='background:linear-gradient(135deg,rgba(0,10,26,0.97) 0%,#000d1a 100%);
                    border-left:5px solid {color};border-radius:8px;
                    padding:18px 24px;margin-bottom:18px;'>
            <p style='color:{color};font-family:monospace;font-size:10px;
                      letter-spacing:2px;margin:0 0 7px 0;'>
                ◆ SKILL: {skill_name.upper()} · LIVE DATA · {GROQ_MODEL.upper()}
            </p>
            <h3 style='color:#F5ECD7;font-family:"Times New Roman",serif;
                       font-size:19px;margin:0 0 7px 0;'>{title}</h3>
            <p style='color:#8898A8;font-size:13px;margin:0;
                      font-family:"Times New Roman",serif;line-height:1.7;'>{description}</p>
        </div>""",
        unsafe_allow_html=True,
    )

def _analysis_footer(skill_name: str) -> None:
    """Renders the standard analysis disclaimer footer."""
    st.markdown(
        f"""<div style='background:rgba(255,82,82,0.06);border:1px solid rgba(255,82,82,0.18);
                    border-radius:4px;padding:10px 16px;margin-top:14px;'>
            <p style='color:rgba(255,255,255,0.35);font-size:10px;font-family:monospace;margin:0;'>
                ⚠ Analysis by {GROQ_MODEL} via skill [{skill_name}] using live yfinance data as of
                {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} UTC. Not financial advice.
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

def _compute_indicators(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Computes EMA9/21/55, SMA200, RSI21, MACD, BB20 from OHLCV."""
    close = df["close"]
    ind: Dict[str, pd.Series] = {}
    ind["ema_9"]    = close.ewm(span=9,   adjust=False).mean()
    ind["ema_21"]   = close.ewm(span=21,  adjust=False).mean()
    ind["ema_55"]   = close.ewm(span=55,  adjust=False).mean()
    ind["sma_200"]  = close.rolling(200).mean()
    bb_mid          = close.rolling(20).mean()
    bb_std          = close.rolling(20).std(ddof=0)
    ind["bb_upper"] = bb_mid + 2.0 * bb_std
    ind["bb_lower"] = bb_mid - 2.0 * bb_std
    delta    = close.diff()
    gain     = delta.clip(lower=0.0)
    loss     = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(com=20, adjust=False).mean()
    avg_loss = loss.ewm(com=20, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0.0, float("nan"))
    ind["rsi_21"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    ind["macd_line"]   = macd
    ind["signal_line"] = signal
    ind["histogram"]   = macd - signal
    # ATR
    if "high" in df.columns and "low" in df.columns:
        hi    = df["high"]
        lo    = df["low"]
        tr    = pd.DataFrame({
            "hl":  hi - lo,
            "hc":  (hi - close.shift(1)).abs(),
            "lc":  (lo - close.shift(1)).abs(),
        }).max(axis=1)
        ind["atr_14"] = tr.ewm(span=14, adjust=False).mean()
    return ind

def _price_chart(
    df: pd.DataFrame,
    ticker: str,
    title: str = "",
    indicators: Optional[Dict[str, pd.Series]] = None,
    height: int = 440,
) -> go.Figure:
    """Renders TradingView-quality candlestick chart."""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#089981", increasing_fillcolor="#089981",
        decreasing_line_color="#F23645", decreasing_fillcolor="#F23645",
        name=ticker, showlegend=False,
    ))
    if indicators:
        cmap = {
            "ema_9":   ("#00E5FF", 1.8), "ema_21":   ("#00FF88", 1.5),
            "ema_55":  ("#FFD700", 1.4), "sma_200":  ("rgba(255,215,0,0.45)", 1.2),
            "bb_upper": ("#6495ED", 0.9), "bb_lower": ("#6495ED", 0.9),
        }
        for key, series in indicators.items():
            if key in cmap:
                color, width = cmap[key]
                dash = "dot" if key.startswith("bb_") else "solid"
                opacity = 0.7 if key.startswith("bb_") else 1.0
                fig.add_trace(go.Scatter(
                    x=df.index, y=series, mode="lines",
                    line=dict(color=color, width=width, dash=dash),
                    name=key.upper(), showlegend=True, opacity=opacity,
                ))
    layout = _tv_layout(height=height, title=title or f"{ticker} Price Chart")
    layout["xaxis"] = _tv_xaxis()
    layout["yaxis"] = _tv_yaxis()
    fig.update_layout(**layout)
    return fig

# ─── VCP SCREENER HELPERS ──────────────────────────────────────────────────
def _compute_vcp_score(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes VCP pattern quality score from price history.
    Based on Minervini's Volatility Contraction Pattern methodology.
    """
    if df.empty or len(df) < 100:
        return {"score": 0.0, "valid": False, "reason": "Insufficient data"}

    close = df["close"]
    hi    = df["high"] if "high" in df.columns else close
    lo    = df["low"]  if "low"  in df.columns else close

    cur     = float(close.iloc[-1])
    ma50    = float(close.rolling(50).mean().iloc[-1])
    ma150   = float(close.rolling(150).mean().iloc[-1]) if len(close) >= 150 else float("nan")
    ma200   = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float("nan")

    # Stage 2 trend template (7-point Minervini check)
    trend_pts = 0
    if cur > ma50:                                       trend_pts += 1
    if cur > ma150 or math.isnan(ma150):                trend_pts += 1
    if cur > ma200 or math.isnan(ma200):                trend_pts += 1
    if not math.isnan(ma200) and ma50 > ma200:          trend_pts += 1
    if not math.isnan(ma150) and ma150 > ma200:         trend_pts += 1
    period_hi = float(hi.tail(252).max())
    period_lo = float(lo.tail(252).min())
    if period_hi > 0 and (cur / period_hi) >= 0.75:     trend_pts += 1
    if period_lo > 0 and (cur / period_lo) >= 1.25:     trend_pts += 1
    trend_score = (trend_pts / 7.0) * 100.0

    # Volatility contraction: measure last 4 corrective swings
    recent  = close.tail(60)
    lookback_high = float(recent.max())
    lookback_low  = float(recent.min())
    mid     = float(recent.iloc[len(recent) // 2])
    depth_1 = (lookback_high - mid) / lookback_high * 100.0 if lookback_high > 0 else 0.0
    depth_2 = (mid - lookback_low) / mid * 100.0 if mid > 0 else 0.0
    contraction_valid = depth_2 < depth_1 * VCP_CONTRACTION_RATIO if depth_1 > 1e-10 else False

    # Volume dry-up: last 10 days vs prior 30 days
    if "volume" in df.columns and len(df) >= 40:
        vol_recent = float(df["volume"].tail(10).mean())
        vol_prior  = float(df["volume"].tail(40).head(30).mean())
        vol_dryup  = vol_recent < vol_prior * 0.75 if vol_prior > 1e-10 else False
    else:
        vol_dryup = False

    # Composite score
    score = (
        trend_score * 0.50
        + (50.0 if contraction_valid else 0.0) * 0.30
        + (50.0 if vol_dryup else 0.0) * 0.20
    )

    return {
        "score":         round(score, 1),
        "valid":         score >= VCP_TREND_SCORE_MIN * 0.75,
        "trend_score":   round(trend_score, 1),
        "trend_pts":     trend_pts,
        "depth_1_pct":   round(depth_1, 2),
        "depth_2_pct":   round(depth_2, 2),
        "contraction":   contraction_valid,
        "volume_dryup":  vol_dryup,
        "cur":           cur,
        "ma50":          ma50,
        "period_hi":     period_hi,
    }

# ─── Z-SCORE HELPER (pairs trading) ───────────────────────────────────────
def _compute_zscore(series_a: pd.Series, series_b: pd.Series) -> Dict[str, Any]:
    """
    Computes spread z-score for a pair of price series.
    Float safety: guarded division throughout.
    """
    aligned = pd.DataFrame({"a": series_a, "b": series_b}).dropna()
    if len(aligned) < 30:
        return {"zscore": 0.0, "spread_mean": 0.0, "spread_std": 0.0, "signal": "INSUFFICIENT"}
    ratio = float(aligned["a"].mean()) / float(aligned["b"].mean()) if float(aligned["b"].mean()) > 1e-10 else 1.0
    spread = aligned["a"] - ratio * aligned["b"]
    s_mean = float(spread.mean())
    s_std  = float(spread.std(ddof=1))
    zscore = (float(spread.iloc[-1]) - s_mean) / s_std if s_std > 1e-10 else 0.0
    corr   = float(aligned["a"].pct_change().corr(aligned["b"].pct_change()))
    if zscore > 2.0:
        signal = "SHORT_A_LONG_B"
    elif zscore < -2.0:
        signal = "LONG_A_SHORT_B"
    elif abs(zscore) < 0.5:
        signal = "NEUTRAL_EXIT"
    else:
        signal = "NEUTRAL"
    return {
        "zscore":      round(zscore, 3),
        "spread_mean": round(s_mean, 4),
        "spread_std":  round(s_std, 4),
        "signal":      signal,
        "correlation": round(corr, 3),
        "ratio":       round(ratio, 4),
        "n_obs":       len(aligned),
    }

# ═══════════════════════════════════════════════════════════════════════════
# TAB RENDERERS — 18 NEW SKILLS
# ═══════════════════════════════════════════════════════════════════════════

def _tab_vcp_screener(api_key: str) -> None:
    """Skill: vcp-screener — Minervini VCP pattern detection."""
    _tab_header(
        "vcp-screener", "#9333EA",
        "VCP Screener — Minervini Volatility Contraction Pattern",
        "Screens for Stage 2 uptrend stocks with volatility contraction near pivot breakout points. "
        "Applies the 7-point Trend Template, contraction ratio analysis (T1/T2/T3), "
        "and volume dry-up detection. Grades: Textbook(90+) / Strong(80-89) / Good(70-79).",
    )
    with st.form("vcp_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.text_input("Ticker Symbol", value="NVDA").upper().strip()
        with c2:
            lookback_yr = st.selectbox("Lookback Period", ["1 Year", "2 Years"], index=0)
        with c3:
            context = st.text_area("Additional Context",
                placeholder="e.g. Market in uptrend, sector leading.",
                height=70)
        submitted = st.form_submit_button("🔬 Run VCP Analysis", type="primary")

    if not submitted:
        return

    years = 2 if "2" in lookback_yr else 1
    with st.spinner(f"Fetching {ticker} price history…"):
        df   = _fetch_history(ticker, years=years)
        info = _fetch_info(ticker)

    if df.empty:
        st.error(f"No price data for {ticker}.")
        return

    vcp = _compute_vcp_score(df)
    ind = _compute_indicators(df)

    st.plotly_chart(
        _price_chart(df.tail(252), ticker,
                     title=f"{ticker} — VCP Analysis | Trend Template",
                     indicators={k: ind[k].tail(252) for k in ["ema_21","ema_55","sma_200"]}),
        use_container_width=True, config=TV_CONFIG,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        score_color = "#00FF88" if vcp["score"] >= 80 else "#FFD700" if vcp["score"] >= 60 else "#FF5252"
        st.metric("VCP Score", f"{vcp['score']:.0f}/100")
    with c2:
        st.metric("Trend Template", f"{vcp['trend_pts']}/7 pts")
    with c3:
        st.metric("T1 Depth", f"{vcp['depth_1_pct']:.1f}%")
    with c4:
        st.metric("T2 Depth", f"{vcp['depth_2_pct']:.1f}% {'✓' if vcp['contraction'] else '✗'}")

    user_content = (
        f"VCP ANALYSIS DATA — {ticker} | {info.get('name', ticker)}\n"
        f"Lookback: {years} year(s) | Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"VCP COMPOSITE SCORE: {vcp['score']:.0f}/100\n"
        f"TREND TEMPLATE: {vcp['trend_pts']}/7 points (Stage 2 score: {vcp['trend_score']:.0f}%)\n\n"
        f"PRICE LEVELS:\n"
        f"  Current: ${vcp['cur']:.2f} | MA50: ${vcp['ma50']:.2f} | "
        f"52W High: ${vcp['period_hi']:.2f}\n"
        f"  vs MA50: {'ABOVE ↑' if vcp['cur'] > vcp['ma50'] else 'BELOW ↓'}\n\n"
        f"VOLATILITY CONTRACTION:\n"
        f"  T1 depth (first swing): {vcp['depth_1_pct']:.1f}%\n"
        f"  T2 depth (second swing): {vcp['depth_2_pct']:.1f}%\n"
        f"  Contraction valid (T2/T1 < 0.70): {'YES ✓' if vcp['contraction'] else 'NO ✗'}\n"
        f"  Volume dry-up detected: {'YES ✓' if vcp['volume_dryup'] else 'NO ✗'}\n\n"
        f"TECHNICALS:\n"
        f"  RSI(21): {float(ind['rsi_21'].iloc[-1]):.1f}\n"
        f"  EMA21: ${float(ind['ema_21'].iloc[-1]):.2f}\n"
        f"  EMA55: ${float(ind['ema_55'].iloc[-1]):.2f}\n\n"
        f"COMPANY: Sector={info.get('sector')} | Cap={_bn(info.get('market_cap'))} | "
        f"Beta={_flt(info.get('beta'), '.2f')}\n\n"
        f"CONTEXT: {context or 'None provided'}\n\n"
        f"Deliver the complete VCP analysis with quality score, execution state, "
        f"pivot price, stop-loss, and specific entry guidance. All levels derived from data above."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming VCP analysis…"):
            _stream(api_key, SYS_VCP, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("vcp-screener")


def _tab_pead_screener(api_key: str) -> None:
    """Skill: pead-screener — Post-Earnings Announcement Drift."""
    _tab_header(
        "pead-screener", "#06B6D4",
        "PEAD Screener — Post-Earnings Drift Weekly Pattern",
        "Detects post-earnings gap-up stocks in the PEAD pattern: earnings gap → "
        "weekly red candle pullback → breakout above red candle high. "
        "Stages: MONITORING → SIGNAL_READY → BREAKOUT → EXPIRED (5-week window).",
    )
    with st.form("pead_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker   = st.text_input("Post-Earnings Ticker", value="META").upper().strip()
            gap_pct  = st.number_input("Earnings Gap %", min_value=-50.0, max_value=100.0,
                                       value=8.0, step=0.5)
        with c2:
            weeks_ago = st.number_input("Weeks Since Earnings", min_value=1, max_value=10, value=2)
            context   = st.text_area("Market Context", height=70,
                placeholder="e.g. Market in uptrend. Sector leading. Breadth healthy.")
        submitted = st.form_submit_button("🎯 Run PEAD Analysis", type="primary")

    if not submitted:
        return

    with st.spinner(f"Fetching {ticker}…"):
        df   = _fetch_history(ticker, years=1)
        info = _fetch_info(ticker)

    if df.empty:
        st.error(f"No data for {ticker}.")
        return

    # Weekly resampling
    df_weekly = df.resample("W").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"
    }).dropna()

    ind = _compute_indicators(df)

    st.plotly_chart(
        _price_chart(df_weekly.tail(26), ticker,
                     title=f"{ticker} — PEAD Weekly Chart ({weeks_ago}W since earnings)",
                     indicators={k: _compute_indicators(df_weekly)[k].tail(26)
                                 for k in ["ema_9","ema_21"]}),
        use_container_width=True, config=TV_CONFIG,
    )

    # PEAD stage estimation
    cur_price = float(df["close"].iloc[-1]) if not df.empty else 0.0
    weeks_left = max(0, 5 - weeks_ago)
    stage = (
        "EXPIRED"       if weeks_ago > 5
        else "BREAKOUT" if weeks_ago >= 3 and gap_pct > 5.0
        else "SIGNAL_READY" if weeks_ago >= 2
        else "MONITORING"
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("PEAD Stage",   stage)
    with c2: st.metric("Earnings Gap", f"{gap_pct:+.1f}%")
    with c3: st.metric("Weeks Elapsed", weeks_ago)
    with c4: st.metric("Window Left",  f"{weeks_left} weeks")

    user_content = (
        f"PEAD SCREENER DATA — {ticker} | {info.get('name', ticker)}\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"EARNINGS GAP: {gap_pct:+.1f}% ({weeks_ago} weeks ago)\n"
        f"CURRENT PRICE: ${cur_price:.2f}\n"
        f"ESTIMATED PEAD STAGE: {stage}\n"
        f"MONITORING WINDOW: {weeks_left} weeks remaining (expires week 5)\n\n"
        f"WEEKLY CHART SUMMARY (last 8 weeks):\n"
    )
    for i, (idx, row) in enumerate(df_weekly.tail(8).iterrows()):
        wk_ret = (float(row["close"]) / float(row["open"]) - 1.0) * 100.0 if float(row["open"]) > 1e-10 else 0.0
        candle  = "RED" if float(row["close"]) < float(row["open"]) else "GREEN"
        user_content += (
            f"  Week-{8-i}: {idx.strftime('%Y-%m-%d')} "
            f"Close=${float(row['close']):.2f} ({wk_ret:+.1f}%) [{candle}]\n"
        )
    user_content += (
        f"\nTECHNICALS:\n"
        f"  RSI(21): {float(ind['rsi_21'].iloc[-1]):.1f}\n"
        f"  EMA21: ${float(ind['ema_21'].iloc[-1]):.2f}\n\n"
        f"COMPANY: Cap={_bn(info.get('market_cap'))} | Sector={info.get('sector')}\n\n"
        f"MARKET CONTEXT: {context or 'Not provided'}\n\n"
        f"Deliver the complete PEAD analysis: stage classification, weekly candle pattern, "
        f"breakout trigger price, stop-loss, target, and risk/reward ratio."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming PEAD analysis…"):
            _stream(api_key, SYS_PEAD, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("pead-screener")


def _tab_macro_regime(api_key: str) -> None:
    """Skill: macro-regime-detector — 6-component cross-asset regime analysis."""
    _tab_header(
        "macro-regime-detector", "#F59E0B",
        "Macro Regime Detector — 6 Cross-Asset Ratios",
        "Identifies 1-2 year structural macro regime transitions using monthly-frequency "
        "cross-asset ratios: RSP/SPY concentration, yield curve, credit (HYG/LQD), "
        "size factor (IWM/SPY), equity-bond (SPY/TLT), sector rotation (XLY/XLP). "
        "5 regimes: Concentration / Broadening / Contraction / Inflationary / Transitional.",
    )
    run_btn = st.button("🌐 Run Macro Regime Analysis", type="primary")
    if not run_btn:
        st.info("Click to fetch live cross-asset ratio data and run regime analysis.")
        return

    with st.spinner("Fetching cross-asset ratio data…"):
        macro_etfs_data: Dict[str, pd.DataFrame] = {}
        for etf in MACRO_ETFS:
            d = _fetch_history(etf, years=2)
            if not d.empty:
                macro_etfs_data[etf] = d

    if not macro_etfs_data:
        st.error("Failed to fetch macro ETF data.")
        return

    # Compute ratios (monthly frequency)
    ratios: Dict[str, Any] = {}
    def _ratio_trend(a_tkr: str, b_tkr: str, name: str) -> Dict[str, float]:
        if a_tkr not in macro_etfs_data or b_tkr not in macro_etfs_data:
            return {"current": 0.0, "6m_ago": 0.0, "trend": 0.0}
        a_ser = macro_etfs_data[a_tkr]["close"].resample("ME").last()
        b_ser = macro_etfs_data[b_tkr]["close"].resample("ME").last()
        ratio = (a_ser / b_ser.replace(0.0, float("nan"))).dropna()
        if len(ratio) < 6:
            return {"current": 0.0, "6m_ago": 0.0, "trend": 0.0}
        cur    = float(ratio.iloc[-1])
        six_m  = float(ratio.iloc[-6]) if len(ratio) >= 6 else cur
        trend  = (cur / six_m - 1.0) * 100.0 if six_m > 1e-10 else 0.0
        return {"current": round(cur, 4), "6m_ago": round(six_m, 4), "trend": round(trend, 2)}

    ratios["concentration"] = _ratio_trend("RSP", "SPY",  "RSP/SPY")
    ratios["credit"]        = _ratio_trend("HYG", "LQD",  "HYG/LQD")
    ratios["size_factor"]   = _ratio_trend("IWM", "SPY",  "IWM/SPY")
    ratios["equity_bond"]   = _ratio_trend("SPY", "TLT",  "SPY/TLT")
    ratios["sector_rot"]    = _ratio_trend("XLY", "XLP",  "XLY/XLP")

    # Yield curve proxy via TNX and IRX
    try:
        tnx = yf.Ticker("^TNX").history(period="6mo")
        irx = yf.Ticker("^IRX").history(period="6mo")
        if not tnx.empty and not irx.empty:
            spread_cur   = float(tnx["Close"].iloc[-1]) - float(irx["Close"].iloc[-1])
            spread_6m    = float(tnx["Close"].iloc[0])  - float(irx["Close"].iloc[0])
            ratios["yield_curve"] = {"current": round(spread_cur, 2), "6m_ago": round(spread_6m, 2),
                                     "trend": round(spread_cur - spread_6m, 2)}
        else:
            ratios["yield_curve"] = {"current": 0.0, "6m_ago": 0.0, "trend": 0.0}
    except Exception:
        ratios["yield_curve"] = {"current": 0.0, "6m_ago": 0.0, "trend": 0.0}

    # Metric display
    st.markdown("#### " + t("hub2_cross_asset"))
    c1, c2, c3 = st.columns(3)
    ratio_display = [
        ("RSP/SPY (Concentration)", ratios["concentration"], "↑ Broadening, ↓ Concentration"),
        ("IWM/SPY (Size Factor)",   ratios["size_factor"],   "↑ Small-cap leadership"),
        ("HYG/LQD (Credit)",        ratios["credit"],        "↑ Risk-On, ↓ Risk-Off"),
        ("SPY/TLT (Equity-Bond)",   ratios["equity_bond"],   "↑ Inflationary regime"),
        ("XLY/XLP (Sector Rot.)",   ratios["sector_rot"],    "↑ Cyclical, ↓ Defensive"),
        ("10Y-2Y Yield Spread (bp)", ratios["yield_curve"],  "↑ Steepening, ↓ Inverting"),
    ]
    for i, (label, data, meaning) in enumerate(ratio_display):
        with [c1, c2, c3][i % 3]:
            trend = data.get("trend", 0.0)
            color = "normal" if trend >= 0 else "inverse"
            st.metric(label, f"{data.get('current', 0):.3f}", f"{trend:+.2f}% (6M)")
            st.caption(meaning)

    # Build context
    lines = [
        f"MACRO REGIME DETECTOR DATA — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        "6-COMPONENT CROSS-ASSET RATIOS (monthly frequency):", "",
        f"1. CONCENTRATION (RSP/SPY): {ratios['concentration']['current']:.4f} "
        f"| 6M ago: {ratios['concentration']['6m_ago']:.4f} "
        f"| Trend: {ratios['concentration']['trend']:+.2f}%",
        f"   → {'BROADENING (RSP outperforming SPY)' if ratios['concentration']['trend'] > 0 else 'CONCENTRATION (Mega-cap dominance)'}",
        "",
        f"2. YIELD CURVE (10Y-2Y spread): {ratios['yield_curve']['current']:.2f} bps "
        f"| 6M ago: {ratios['yield_curve']['6m_ago']:.2f} bps "
        f"| Trend: {ratios['yield_curve']['trend']:+.2f} bps",
        f"   → {'Steepening (reflationary)' if ratios['yield_curve']['trend'] > 0 else 'Flattening/Inverting (recessionary pressure)'}",
        "",
        f"3. CREDIT (HYG/LQD): {ratios['credit']['current']:.4f} "
        f"| 6M trend: {ratios['credit']['trend']:+.2f}%",
        f"   → {'Risk-On (credit spreads tightening)' if ratios['credit']['trend'] > 0 else 'Risk-Off (credit stress)'}",
        "",
        f"4. SIZE FACTOR (IWM/SPY): {ratios['size_factor']['current']:.4f} "
        f"| 6M trend: {ratios['size_factor']['trend']:+.2f}%",
        f"   → {'Small-cap leadership' if ratios['size_factor']['trend'] > 0 else 'Large-cap/Mega-cap dominance'}",
        "",
        f"5. EQUITY-BOND (SPY/TLT): {ratios['equity_bond']['current']:.4f} "
        f"| 6M trend: {ratios['equity_bond']['trend']:+.2f}%",
        f"   → {'Inflationary regime (stocks-bonds positive corr)' if ratios['equity_bond']['trend'] > 0 else 'Deflationary/Risk-off regime'}",
        "",
        f"6. SECTOR ROTATION (XLY/XLP): {ratios['sector_rot']['current']:.4f} "
        f"| 6M trend: {ratios['sector_rot']['trend']:+.2f}%",
        f"   → {'Cyclical leadership' if ratios['sector_rot']['trend'] > 0 else 'Defensive rotation underway'}",
        "",
        "Deliver the complete Macro Regime analysis. Identify the current regime, ",
        "transition probability, and strategic portfolio posture for a 1-2 year horizon.",
    ]
    user_content = "\n".join(lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming macro regime analysis…"):
            _stream(api_key, SYS_MACRO_REGIME, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("macro-regime-detector")


def _tab_ftd_detector(api_key: str) -> None:
    """Skill: ftd-detector — O'Neil Follow-Through Day detection."""
    _tab_header(
        "ftd-detector", "#10B981",
        "FTD Detector — O'Neil Follow-Through Day Analysis",
        "Detects market bottom confirmation using William O'Neil's Follow-Through Day methodology. "
        "State machine: NO_SIGNAL → CORRECTION → RALLY_ATTEMPT → FTD_WINDOW → FTD_CONFIRMED. "
        "Quality score 0-100. Complementary to Market Top Detector (offensive vs defensive).",
    )
    with st.form("ftd_form"):
        c1, c2 = st.columns(2)
        with c1:
            index_choice = st.selectbox(
                "Index to Monitor",
                ["SPY (S&P 500 ETF)", "QQQ (NASDAQ ETF)", "^GSPC (S&P 500)", "^IXIC (NASDAQ)"],
            )
        with c2:
            observation = st.text_area("Observations (optional)",
                placeholder="e.g. Bounce attempt started Monday. Leaders quiet.",
                height=80)
        submitted = st.form_submit_button("📡 Run FTD Analysis", type="primary")

    if not submitted:
        return

    tkr_map = {
        "SPY (S&P 500 ETF)": "SPY", "QQQ (NASDAQ ETF)": "QQQ",
        "^GSPC (S&P 500)": "^GSPC", "^IXIC (NASDAQ)": "^IXIC",
    }
    index_t = tkr_map.get(index_choice, "SPY")

    with st.spinner(f"Fetching {index_choice}…"):
        df = _fetch_history(index_t, years=1)

    if df.empty:
        st.error(f"No data for {index_t}.")
        return

    ind = _compute_indicators(df)

    # FTD state estimation from price action
    recent  = df.tail(40)
    if len(recent) < 10:
        st.error("Insufficient recent data.")
        return

    period_high    = float(recent["close"].max())
    current_close  = float(recent["close"].iloc[-1])
    peak_to_now    = (current_close / period_high - 1.0) * 100.0 if period_high > 1e-10 else 0.0
    in_correction  = peak_to_now < -FTD_CORRECTION_PCT
    last_low       = float(recent["close"].min())
    bounce_from_low = (current_close / last_low - 1.0) * 100.0 if last_low > 1e-10 else 0.0

    # Volume vs 21D avg
    vol_avg_21 = float(df["volume"].tail(21).mean()) if "volume" in df.columns else 0.0
    vol_today   = float(df["volume"].iloc[-1])        if "volume" in df.columns else 0.0
    vol_ratio   = vol_today / vol_avg_21 if vol_avg_21 > 1e-10 else 1.0

    # Day return
    day_ret = (
        (float(df["close"].iloc[-1]) / float(df["close"].iloc[-2]) - 1.0) * 100.0
        if len(df) >= 2 else 0.0
    )

    # Simple FTD state estimate
    if not in_correction:
        state      = "NO_SIGNAL (Uptrend)"
        state_color = "#00FF88"
        quality     = 0
    elif bounce_from_low < 1.0:
        state      = "CORRECTION"
        state_color = "#FF5252"
        quality     = 10
    elif bounce_from_low < 3.0:
        state      = "RALLY_ATTEMPT (Day 1-3)"
        state_color = "#FF9500"
        quality     = 30
    elif day_ret > 1.25 and vol_ratio > 1.1:
        state      = "FTD_WINDOW — Qualifying Day Detected!"
        state_color = "#00FF88"
        quality     = min(100, int(50.0 + day_ret * 5.0 + vol_ratio * 10.0))
    else:
        state      = "FTD_WINDOW (Day 4+, awaiting volume confirmation)"
        state_color = "#FFD700"
        quality     = 40

    st.markdown(
        f"""<div style='background:#001a0d;border:2px solid {state_color};border-radius:10px;
                    padding:18px 26px;margin-bottom:14px;'>
            <p style='color:{state_color};font-family:monospace;font-size:10px;
                      letter-spacing:2px;margin:0 0 5px;'>FTD STATE MACHINE</p>
            <p style='color:{state_color};font-size:22px;font-weight:bold;
                      font-family:monospace;margin:0 0 5px;'>{state}</p>
            <p style='color:#E8E0D0;font-size:14px;margin:0;'>
                Quality Score: <strong style='color:{state_color};'>{quality}/100</strong> &nbsp;|&nbsp;
                Peak-to-now: <strong>{peak_to_now:+.1f}%</strong> &nbsp;|&nbsp;
                Bounce from low: <strong>{bounce_from_low:+.1f}%</strong>
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

    st.plotly_chart(
        _price_chart(df.tail(60), index_t, title=f"{index_choice} — FTD State Monitor (60D)"),
        use_container_width=True, config=TV_CONFIG,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Today's Return", f"{day_ret:+.2f}%")
    with c2: st.metric("Volume vs 21D avg", f"{vol_ratio:.2f}x")
    with c3: st.metric("From Period High", f"{peak_to_now:+.1f}%")
    with c4: st.metric("From Period Low", f"{bounce_from_low:+.1f}%")

    user_content = (
        f"FTD DETECTOR DATA — {index_choice}\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"ESTIMATED FTD STATE: {state}\n"
        f"QUALITY SCORE: {quality}/100\n\n"
        f"PRICE ACTION:\n"
        f"  Current close: ${current_close:.2f}\n"
        f"  Period high (40D): ${period_high:.2f}\n"
        f"  Distance from peak: {peak_to_now:+.1f}% — {'IN CORRECTION' if in_correction else 'NOT IN CORRECTION'}\n"
        f"  Swing low (40D): ${last_low:.2f}\n"
        f"  Bounce from low: {bounce_from_low:+.1f}%\n\n"
        f"TODAY'S SESSION:\n"
        f"  Return: {day_ret:+.2f}%\n"
        f"  Volume vs 21D avg: {vol_ratio:.2f}x — {'ABOVE AVG' if vol_ratio > 1.1 else 'BELOW/AVG'}\n"
        f"  FTD qualification: {'YES (>1.25% + volume)' if day_ret > 1.25 and vol_ratio > 1.1 else 'NOT YET'}\n\n"
        f"OBSERVATIONS: {observation or 'None'}\n\n"
        f"Deliver the complete FTD analysis: state classification, quality score, key watch levels, "
        f"re-entry guidance, and post-FTD health assessment."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming FTD analysis…"):
            _stream(api_key, SYS_FTD, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("ftd-detector")


def _tab_exposure_coach(api_key: str) -> None:
    """Skill: exposure-coach — Capital deployment decision synthesizer."""
    _tab_header(
        "exposure-coach", "#8B5CF6",
        "Exposure Coach — Capital Deployment Control Plane",
        "Synthesizes breadth, uptrend ratio, macro regime, market top risk, FTD state, "
        "sector rotation, and institutional flow into one exposure ceiling (0-100%) "
        "and a single action: NEW_ENTRY_ALLOWED / REDUCE_ONLY / CASH_PRIORITY.",
    )
    st.markdown("##### " + t("hub2_signal_inputs"))

    with st.form("exposure_form"):
        c1, c2 = st.columns(2)
        with c1:
            breadth_score   = st.slider("Breadth Health Score (0-100)",   0, 100, 60)
            uptrend_score   = st.slider("Uptrend Ratio Score (0-100)",     0, 100, 58)
            top_risk_score  = st.slider("Market Top Risk Score (0-100)",   0, 100, 35)
            macro_score     = st.slider("Macro Regime Score (0-100)",      0, 100, 55)
        with c2:
            ftd_score       = st.slider("FTD Quality Score (0-100)",       0, 100, 40)
            sector_score    = st.slider("Sector Analyst Score (0-100)",    0, 100, 62)
            institutional_s = st.slider("Institutional Flow Score (0-100)", 0, 100, 55)
            theme_score     = st.slider("Theme/Momentum Score (0-100)",    0, 100, 60)
        context = st.text_area("Market Context / Notes", height=70,
            placeholder="e.g. Fed meeting next week. Earnings season starting.")
        submitted = st.form_submit_button("🧭 Generate Market Posture", type="primary")

    if not submitted:
        return

    # Compute exposure ceiling
    top_risk_inv = max(0.0, 100.0 - float(top_risk_score))
    composite = (
        float(breadth_score)   * 0.15
        + float(uptrend_score) * 0.15
        + top_risk_inv         * 0.20
        + float(macro_score)   * 0.15
        + float(ftd_score)     * 0.10
        + float(theme_score)   * 0.10
        + float(sector_score)  * 0.10
        + float(institutional_s) * 0.05
    )
    composite = round(max(0.0, min(100.0, composite)), 1)

    # Bias and recommendation
    if composite >= 75.0:
        ceiling = min(100, int(composite))
        rec     = "NEW_ENTRY_ALLOWED"
        bias    = "GROWTH"
        partic  = "BROAD"
        confidence = "HIGH"
        rec_color  = "#00FF88"
    elif composite >= 55.0:
        ceiling = min(80, int(composite * 0.9))
        rec     = "NEW_ENTRY_ALLOWED (selective)"
        bias    = "NEUTRAL"
        partic  = "MODERATE"
        confidence = "MEDIUM"
        rec_color  = "#FFD700"
    elif composite >= 40.0:
        ceiling = min(60, int(composite * 0.75))
        rec     = "REDUCE_ONLY"
        bias    = "VALUE"
        partic  = "NARROW"
        confidence = "MEDIUM"
        rec_color  = "#FF9500"
    else:
        ceiling = min(30, int(composite * 0.5))
        rec     = "CASH_PRIORITY"
        bias    = "DEFENSIVE"
        partic  = "FRAGILE"
        confidence = "LOW"
        rec_color  = "#FF5252"

    st.markdown(
        f"""<div style='background:#0a0a1a;border:2px solid {rec_color};border-radius:12px;
                    padding:22px 28px;margin-bottom:14px;
                    display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;'>
            <div>
                <p style='color:{rec_color};font-family:monospace;font-size:10px;
                          letter-spacing:2px;margin:0 0 4px;'>MARKET POSTURE</p>
                <p style='color:{rec_color};font-size:48px;font-weight:bold;
                          font-family:monospace;margin:0;'>{ceiling}%</p>
                <p style='color:#E8E0D0;font-size:13px;margin:4px 0 0;'>Exposure Ceiling</p>
            </div>
            <div style='text-align:right;'>
                <p style='color:{rec_color};font-size:18px;font-weight:bold;margin:0 0 6px;'>{rec}</p>
                <p style='color:#8898A8;font-size:13px;margin:2px 0;'>Bias: {bias} | Participation: {partic}</p>
                <p style='color:#8898A8;font-size:13px;margin:2px 0;'>Confidence: {confidence}</p>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Component radar chart
    categories = ["Breadth", "Uptrend", "Top Risk\nInverse", "Macro", "FTD", "Theme", "Sector", "Instit."]
    values     = [breadth_score, uptrend_score, top_risk_inv, macro_score,
                  ftd_score, theme_score, sector_score, institutional_s]

    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(
        r=values + [values[0]], theta=categories + [categories[0]],
        fill="toself", fillcolor="rgba(0,229,255,0.10)",
        line=dict(color="#00E5FF", width=2),
        name="Signal Scores",
    ))
    layout_r = _tv_layout(height=340, title="Exposure Component Radar")
    layout_r["polar"] = {
        "radialaxis": {"range": [0, 100], "tickfont": {"color": "#8a8a8a", "size": 9}},
        "angularaxis": {"tickfont": {"color": "#E8E0D0", "size": 10}},
        "bgcolor": "#000d1a",
    }
    layout_r.pop("xaxis", None)
    layout_r.pop("yaxis", None)
    fig_radar.update_layout(**layout_r)
    st.plotly_chart(fig_radar, use_container_width=True, config=TV_CONFIG)

    user_content = (
        f"EXPOSURE COACH DATA\nDate: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"COMPUTED COMPOSITE: {composite}/100 → Ceiling: {ceiling}% → Recommendation: {rec}\n\n"
        f"COMPONENT SCORES:\n"
        f"  Breadth Health: {breadth_score}/100 (weight 15%)\n"
        f"  Uptrend Ratio:  {uptrend_score}/100 (weight 15%)\n"
        f"  Top Risk Inv.:  {top_risk_inv:.0f}/100 (weight 20%) [raw top risk: {top_risk_score}]\n"
        f"  Macro Regime:   {macro_score}/100 (weight 15%)\n"
        f"  FTD Quality:    {ftd_score}/100 (weight 10%)\n"
        f"  Theme/Momentum: {theme_score}/100 (weight 10%)\n"
        f"  Sector Score:   {sector_score}/100 (weight 10%)\n"
        f"  Institutional:  {institutional_s}/100 (weight 5%)\n\n"
        f"POSTURE: Ceiling={ceiling}% | Bias={bias} | Participation={partic} | Confidence={confidence}\n\n"
        f"CONTEXT: {context or 'None'}\n\n"
        f"Deliver the complete Market Posture Summary with specific guidance: "
        f"which sectors to overweight, position sizing vs normal, and what trigger would change this posture."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Generating market posture…"):
            _stream(api_key, SYS_EXPOSURE_COACH, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("exposure-coach")


def _tab_institutional_flow(api_key: str) -> None:
    """Skill: institutional-flow-tracker — 13F smart money flow analysis."""
    _tab_header(
        "institutional-flow-tracker", "#0EA5E9",
        "Institutional Flow Tracker — 13F Smart Money Analysis",
        "Analyzes SEC 13F filings to detect institutional accumulation/distribution patterns. "
        "Assigns data quality grades (A/B/C). Identifies new buyers, major sellers, and "
        "concentration risk. 45-day data lag — use as confirming indicator.",
    )
    with st.form("inst_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Ticker to Analyze", value="MSFT").upper().strip()
        with c2:
            sector_filter = st.selectbox(
                "Add Sector Context",
                ["None", "Technology", "Healthcare", "Financials", "Energy",
                 "Consumer", "Industrials", "Real Estate"],
            )
        notes = st.text_area("Investment Thesis (optional)",
            placeholder="e.g. Long-term AI infrastructure play. Checking institutional support.",
            height=70)
        submitted = st.form_submit_button("🏦 Run Institutional Analysis", type="primary")

    if not submitted:
        return

    with st.spinner(f"Fetching {ticker} data…"):
        info = _fetch_info(ticker)
        df   = _fetch_history(ticker, years=2)

    if not info:
        st.error(f"No data for {ticker}.")
        return

    # Proxy institutional metrics from yfinance
    try:
        t       = yf.Ticker(ticker)
        inst_raw = t.institutional_holders
        major_h  = t.major_holders
    except Exception:
        inst_raw = None
        major_h  = None

    # Price chart
    if not df.empty:
        ind = _compute_indicators(df)
        st.plotly_chart(
            _price_chart(df.tail(252), ticker,
                         title=f"{ticker} — Institutional Flow Context (1Y)",
                         indicators={k: ind[k].tail(252) for k in ["sma_200","ema_55"]}),
            use_container_width=True, config=TV_CONFIG,
        )

    # Build holder summary
    holder_lines = []
    if inst_raw is not None and not inst_raw.empty:
        cols_lower = {c: c.lower() for c in inst_raw.columns}
        inst_df = inst_raw.rename(columns=cols_lower)
        for _, row in inst_df.head(10).iterrows():
            holder_lines.append(f"  {str(row.get('holder','?'))[:35]:<36} {str(row.get('shares','?'))}")

    if major_h is not None and not major_h.empty:
        try:
            inst_pct = float(major_h.iloc[0, 0].replace("%","")) if len(major_h) >= 1 else 0.0
            insider_pct = float(major_h.iloc[1, 0].replace("%","")) if len(major_h) >= 2 else 0.0
        except Exception:
            inst_pct    = 0.0
            insider_pct = 0.0
    else:
        inst_pct    = 0.0
        insider_pct = 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric(f"{ticker} Price", f"${_flt(info.get('current_price'), '.2f')}")
    with c2: st.metric("Market Cap",  _bn(info.get("market_cap")))
    with c3: st.metric("Inst. Ownership%", f"{inst_pct:.1f}%" if inst_pct > 0 else "N/A")
    with c4: st.metric("Insider %",  f"{insider_pct:.1f}%" if insider_pct > 0 else "N/A")

    user_content = (
        f"INSTITUTIONAL FLOW TRACKER — {ticker} | {info.get('name', ticker)}\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"COMPANY PROFILE:\n"
        f"  Sector: {info.get('sector')} | Industry: {info.get('industry')}\n"
        f"  Market Cap: {_bn(info.get('market_cap'))} | Beta: {_flt(info.get('beta'), '.2f')}\n"
        f"  Short Ratio: {_flt(info.get('short_ratio'), '.1f')}\n\n"
        f"INSTITUTIONAL OWNERSHIP DATA (from yfinance/13F proxy):\n"
        f"  Institutional ownership %: {inst_pct:.1f}%\n"
        f"  Insider ownership %: {insider_pct:.1f}%\n\n"
        f"TOP INSTITUTIONAL HOLDERS (last available 13F):\n"
        + ("\n".join(holder_lines) if holder_lines else "  Data unavailable — FMP API key required for full 13F data\n")
        + f"\n\nFUNDAMENTALS:\n"
        f"  P/E: {_flt(info.get('pe_ratio'), '.1f')} | P/B: {_flt(info.get('pb_ratio'), '.2f')}\n"
        f"  Revenue Growth: {_pct(info.get('revenue_growth'))} | ROE: {_pct(info.get('roe'))}\n"
        f"  FCF: {_bn(info.get('free_cashflow'))} | D/E: {_flt(info.get('debt_to_equity'), '.1f')}\n\n"
        f"SECTOR CONTEXT: {sector_filter}\n"
        f"INVESTMENT THESIS: {notes or 'Not provided'}\n\n"
        f"⚠️ NOTE: Full 13F data requires FMP API. Displaying yfinance proxy data.\n\n"
        f"Deliver the complete institutional flow analysis: signal strength, ownership trend, "
        f"concentration risk, and investment implications. Be explicit about data quality limitations."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming institutional analysis…"):
            _stream(api_key, SYS_INSTITUTIONAL, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("institutional-flow-tracker")


def _tab_kanchi_sop(api_key: str) -> None:
    """Skill: kanchi-dividend-sop — 5-step Kanchi dividend investment SOP."""
    _tab_header(
        "kanchi-dividend-sop", "#F59E0B",
        "Kanchi Dividend SOP — 5-Step Japanese Method for US Equities",
        "Implements the Kanchi dividend investing framework adapted for US equities: "
        "Step 1: Yield filter (≥3.5%), Step 2: Growth & safety, Step 3: Sector-adjusted valuation, "
        "Step 4: One-off event filter, Step 5: Buy-on-weakness limit order plan.",
    )
    with st.form("kanchi_form"):
        c1, c2 = st.columns(2)
        with c1:
            custom_tickers = st.text_area(
                "Custom Tickers (optional — add to built-in universe)",
                placeholder="MAIN\nARCC\nWPC\nIRM",
                height=100,
            )
            account_type = st.selectbox("Account Type",
                ["US Taxable", "US IRA/Roth", "Swedish ISK", "Swedish KF"])
        with c2:
            invest_amount = st.number_input("Investment Amount ($)",
                min_value=5_000, max_value=10_000_000, value=50_000, step=5_000)
            income_goal   = st.number_input("Monthly Income Target ($)",
                min_value=0, max_value=100_000, value=300, step=50)
            prefs = st.text_area("Preferences", height=60,
                placeholder="e.g. No BDCs. REITs OK. Focus on dividend growth aristocrats.")
        submitted = st.form_submit_button("🌸 Run Kanchi Dividend SOP", type="primary")

    if not submitted:
        return

    universe = list(KANCHI_DIVIDEND_UNIVERSE)
    if custom_tickers.strip():
        for t in custom_tickers.strip().upper().splitlines():
            t = t.strip()
            if t and t not in universe:
                universe.append(t)

    screened: Dict[str, Dict[str, Any]] = {}
    bar = st.progress(0, text="Fetching dividend data…")
    for i, tkr in enumerate(universe):
        bar.progress((i + 1) / len(universe), text=f"Fetching {tkr}…")
        inf = _fetch_info(tkr)
        if inf:
            screened[tkr] = inf
        time.sleep(0.05)
    bar.empty()

    # Step 1: Yield filter (≥3.5%)
    step1_pass: List[str] = []
    step1_trap: List[str] = []
    for tkr, d in screened.items():
        dy = d.get("dividend_yield")
        if dy is None:
            continue
        dy_pct = float(dy) * 100.0
        if dy_pct >= 8.0:
            step1_trap.append(tkr)
        elif dy_pct >= 3.5:
            step1_pass.append(tkr)

    # Step 2: Safety filter
    step2_pass: List[str] = []
    for tkr in step1_pass:
        d       = screened[tkr]
        payout  = d.get("payout_ratio")
        rev_grw = d.get("revenue_growth")
        roe     = d.get("roe")
        safe = True
        if payout is not None and float(payout) > 0.85:
            safe = False
        if rev_grw is not None and float(rev_grw) < -0.10:
            safe = False
        if safe:
            step2_pass.append(tkr)

    # Display step summaries
    st.markdown(
        f"""<div style='display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;'>
            <div style='background:#0d1f33;border:1px solid #00E5FF;border-radius:8px;
                        padding:14px 20px;flex:1;min-width:140px;text-align:center;'>
                <p style='color:#00E5FF;font-family:monospace;font-size:10px;margin:0 0 4px;letter-spacing:1px;'>STEP 1 PASS</p>
                <p style='color:#F5ECD7;font-size:24px;font-weight:bold;font-family:monospace;margin:0;'>{len(step1_pass)}</p>
                <p style='color:#8898A8;font-size:11px;margin:3px 0 0;'>Yield ≥ 3.5%</p>
            </div>
            <div style='background:#0d1f33;border:1px solid #FFD700;border-radius:8px;
                        padding:14px 20px;flex:1;min-width:140px;text-align:center;'>
                <p style='color:#FFD700;font-family:monospace;font-size:10px;margin:0 0 4px;letter-spacing:1px;'>YIELD TRAPS</p>
                <p style='color:#F5ECD7;font-size:24px;font-weight:bold;font-family:monospace;margin:0;'>{len(step1_trap)}</p>
                <p style='color:#8898A8;font-size:11px;margin:3px 0 0;'>Yield ≥ 8% (deep-dive req.)</p>
            </div>
            <div style='background:#0d1f33;border:1px solid #00FF88;border-radius:8px;
                        padding:14px 20px;flex:1;min-width:140px;text-align:center;'>
                <p style='color:#00FF88;font-family:monospace;font-size:10px;margin:0 0 4px;letter-spacing:1px;'>STEP 2 PASS</p>
                <p style='color:#F5ECD7;font-size:24px;font-weight:bold;font-family:monospace;margin:0;'>{len(step2_pass)}</p>
                <p style='color:#8898A8;font-size:11px;margin:3px 0 0;'>Safety check passed</p>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Summary table
    if step2_pass:
        rows = []
        for tkr in step2_pass:
            d = screened[tkr]
            rows.append({
                "Ticker":   tkr,
                "Name":     (d.get("name") or tkr)[:24],
                "Sector":   (d.get("sector") or "?")[:16],
                "Yield":    _pct(d.get("dividend_yield")),
                "Payout%":  _pct(d.get("payout_ratio")),
                "P/E":      _flt(d.get("pe_ratio"), ".1f"),
                "P/B":      _flt(d.get("pb_ratio"), ".2f"),
                "FCF":      _bn(d.get("free_cashflow")),
                "ROE":      _pct(d.get("roe")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    lines = [
        f"KANCHI DIVIDEND SOP — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Universe: {len(screened)} stocks | Step 1 pass: {len(step1_pass)} | Step 2 pass: {len(step2_pass)}",
        f"Account: {account_type} | Investment: ${invest_amount:,} | Income target: ${income_goal:,}/mo",
        "", "STEP 1 PASSED (Yield 3.5-8%):",
    ]
    for tkr in step1_pass:
        d = screened[tkr]
        lines.append(
            f"  {tkr:<8} Yield={_pct(d.get('dividend_yield'))} "
            f"P/E={_flt(d.get('pe_ratio'),'.1f')} P/B={_flt(d.get('pb_ratio'),'.2f')}"
        )
    lines += ["", "YIELD TRAPS (≥8% — deep dive required):"]
    lines += [f"  {t}" for t in step1_trap]
    lines += ["", "STEP 2 PASSED (safety check):"]
    for tkr in step2_pass:
        d = screened[tkr]
        lines.append(
            f"  {tkr:<8} Payout={_pct(d.get('payout_ratio'))} "
            f"RevGrw={_pct(d.get('revenue_growth'))} FCF={_bn(d.get('free_cashflow'))}"
        )
    lines += [
        "", f"PREFERENCES: {prefs or 'None'}",
        "Apply full 5-step Kanchi SOP. For Step 3 use sector-appropriate valuation (P/E×P/B for banks, "
        "P/FFO for REITs). For Step 5 compute: 5Y average yield + 0.5pp = buy trigger yield. "
        "Generate one-page memo and limit-order plan (40/30/30 split) for each PASS stock.",
    ]
    user_content = "\n".join(lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming Kanchi Dividend SOP…"):
            _stream(api_key, SYS_KANCHI_SOP, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("kanchi-dividend-sop")


def _tab_position_sizer(api_key: str) -> None:
    """Skill: position-sizer — Risk-based position sizing calculator."""
    _tab_header(
        "position-sizer", "#22D3EE",
        "Position Sizer — Fixed Fractional · ATR-Based · Kelly Criterion",
        "Calculates exact share counts using three methods: Fixed Fractional (1% risk default), "
        "ATR-Based volatility-adjusted stops, and Kelly Criterion (half-Kelly in practice). "
        "Applies portfolio constraints (max position %, max sector %) — strictest constraint wins.",
    )
    with st.form("sizer_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker    = st.text_input("Ticker (optional for live price)", value="AAPL").upper().strip()
            use_live  = st.checkbox("Fetch live price", value=True)
            entry_price = st.number_input("Entry Price ($)", min_value=0.01, value=185.0, step=1.0)
            stop_price  = st.number_input("Stop Price ($)",  min_value=0.01, value=178.0, step=0.5)
        with c2:
            account_size  = st.number_input("Account Size ($)", min_value=1_000, max_value=10_000_000,
                                            value=100_000, step=5_000)
            risk_pct      = st.number_input("Risk % per Trade", min_value=0.1, max_value=5.0,
                                            value=float(POSITION_RISK_DEFAULT_PCT), step=0.1)
            max_pos_pct   = st.number_input("Max Position % of Account",
                                            min_value=1.0, max_value=50.0,
                                            value=float(POSITION_MAX_PCT_DEFAULT), step=1.0)
        with c3:
            atr_value     = st.number_input("ATR(14) Value ($, 0=skip)", min_value=0.0,
                                            value=0.0, step=0.1)
            atr_mult      = st.number_input("ATR Multiplier", min_value=0.5, max_value=5.0,
                                            value=2.0, step=0.25)
            win_rate      = st.number_input("Historical Win Rate % (Kelly)", min_value=0.0,
                                            max_value=100.0, value=55.0, step=1.0)
            avg_win_r     = st.number_input("Avg Win (R-multiple)", min_value=0.1, max_value=20.0,
                                            value=2.0, step=0.1)
            avg_loss_r    = st.number_input("Avg Loss (R-multiple)", min_value=0.1, max_value=10.0,
                                            value=1.0, step=0.1)
        submitted = st.form_submit_button("📏 Calculate Position Size", type="primary")

    if not submitted:
        return

    # Fetch live price if requested
    entry = entry_price
    if use_live and ticker:
        with st.spinner(f"Fetching live price for {ticker}…"):
            inf = _fetch_info(ticker)
        lp = inf.get("current_price")
        if lp:
            entry = float(lp)
            st.success(f"✓ Live price for {ticker}: ${entry:.2f}")

    # Fixed Fractional
    dollar_risk_ff  = account_size * risk_pct / 100.0
    risk_per_share  = float(entry) - float(stop_price)
    shares_ff       = int(dollar_risk_ff / risk_per_share) if risk_per_share > 1e-10 else 0
    pos_val_ff      = shares_ff * float(entry)
    max_shares_pos  = int(account_size * max_pos_pct / 100.0 / float(entry)) if float(entry) > 1e-10 else 0
    shares_ff_final = min(shares_ff, max_shares_pos)

    # ATR-Based
    if atr_value > 1e-10:
        atr_stop_dist   = atr_value * atr_mult
        dollar_risk_atr = account_size * risk_pct / 100.0
        shares_atr      = int(dollar_risk_atr / atr_stop_dist) if atr_stop_dist > 1e-10 else 0
        shares_atr_final = min(shares_atr, max_shares_pos)
        atr_stop_price  = float(entry) - atr_stop_dist
    else:
        shares_atr_final = 0
        atr_stop_price   = 0.0

    # Kelly Criterion (half-Kelly)
    w  = win_rate / 100.0
    wr = avg_win_r
    lr = avg_loss_r
    kelly_fraction = ((w * wr) - ((1.0 - w) * lr)) / wr if wr > 1e-10 else 0.0
    half_kelly_fraction = max(0.0, kelly_fraction * KELLY_HALF_FRACTION)
    dollar_kelly   = account_size * half_kelly_fraction
    shares_kelly   = int(dollar_kelly / float(entry)) if float(entry) > 1e-10 else 0
    shares_kelly_final = min(shares_kelly, max_shares_pos)

    # Display
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Fixed Fractional (1% Rule)**")
        st.metric("Shares",          shares_ff_final)
        st.metric("Position Value",  f"${shares_ff_final * float(entry):,.0f}")
        st.metric("Dollar Risk",     f"${shares_ff_final * risk_per_share:,.0f}")
        if shares_ff_final < shares_ff:
            st.caption(f"⚠️ Capped by max position ({max_pos_pct:.0f}%)")
    with c2:
        if atr_value > 1e-10:
            st.markdown(f"**ATR-Based ({atr_mult:.1f}x ATR)**")
            st.metric("Shares",          shares_atr_final)
            st.metric("Position Value",  f"${shares_atr_final * float(entry):,.0f}")
            st.metric("ATR Stop",        f"${atr_stop_price:.2f}")
        else:
            st.info("Enter ATR(14) value to enable ATR-based sizing.")
    with c3:
        st.markdown(f"**Kelly Criterion (½-Kelly = {half_kelly_fraction*100:.1f}%)**")
        st.metric("Shares",          shares_kelly_final)
        st.metric("Position Value",  f"${shares_kelly_final * float(entry):,.0f}")
        st.metric("Full Kelly",      f"{kelly_fraction*100:.1f}%")
        if shares_kelly_final < shares_kelly:
            st.caption(f"⚠️ Capped by max position ({max_pos_pct:.0f}%)")

    # Risk/reward bar
    rr = risk_per_share
    st.markdown(
        f"<p style='font-family:monospace;font-size:12px;color:#8898A8;margin-top:8px;'>"
        f"Entry: ${float(entry):.2f} | Stop: ${float(stop_price):.2f} | "
        f"Risk/share: ${rr:.2f} | Account: ${account_size:,} | Risk%: {risk_pct:.1f}%"
        f"</p>",
        unsafe_allow_html=True,
    )

    user_content = (
        f"POSITION SIZER DATA\n"
        f"Ticker: {ticker} | Account: ${account_size:,} | Risk%: {risk_pct:.1f}%\n"
        f"Entry: ${float(entry):.2f} | Stop: ${float(stop_price):.2f} | Risk/share: ${rr:.2f}\n"
        f"Max position: {max_pos_pct:.0f}% of account = {max_shares_pos} shares\n\n"
        f"FIXED FRACTIONAL:\n"
        f"  Dollar risk: ${dollar_risk_ff:,.0f}\n"
        f"  Raw shares: {shares_ff} → Final (constrained): {shares_ff_final}\n"
        f"  Position value: ${shares_ff_final * float(entry):,.0f}\n\n"
        f"ATR-BASED ({atr_mult:.1f}x ATR):\n"
        + (f"  ATR value: ${atr_value:.2f} | Stop dist: ${atr_value * atr_mult:.2f}\n"
           f"  Final shares: {shares_atr_final} | Stop price: ${atr_stop_price:.2f}\n"
           if atr_value > 1e-10 else "  ATR not provided — method not applicable\n")
        + f"\nKELLY CRITERION:\n"
        f"  Win rate: {win_rate:.0f}% | Avg win: {avg_win_r:.1f}R | Avg loss: {avg_loss_r:.1f}R\n"
        f"  Full Kelly: {kelly_fraction*100:.1f}% | Half-Kelly: {half_kelly_fraction*100:.1f}%\n"
        f"  Dollar allocation: ${dollar_kelly:,.0f} | Final shares: {shares_kelly_final}\n\n"
        f"Deliver the complete position sizing analysis. State the recommended final share count, "
        f"binding constraint, portfolio heat with this addition, and risk management reminders. "
        f"Key: round down, half-Kelly only, strictest constraint wins."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming position sizing analysis…"):
            _stream(api_key, SYS_POSITION_SIZER, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("position-sizer")


def _tab_sector_analyst(api_key: str) -> None:
    """Skill: sector-analyst — Sector rotation and market cycle analysis."""
    _tab_header(
        "sector-analyst", "#84CC16",
        "Sector Analyst — Rotation + Market Cycle Phase",
        "Analyzes 11 GICS sectors using live ETF data to identify sector rotation patterns, "
        "classify the current market cycle phase (Early Recovery / Mid Expansion / Late Cycle / Recession), "
        "and generate 2-3 probability-weighted scenarios with sector positioning recommendations.",
    )
    run_btn = st.button("🗺️ Run Sector Rotation Analysis", type="primary")
    if not run_btn:
        st.info("Click to fetch live sector data and run cycle phase analysis.")
        return

    with st.spinner("Fetching sector ETF data…"):
        sector_data = _fetch_sector_data()

    if not sector_data:
        st.error("Failed to fetch sector data.")
        return

    # Compute cyclical vs defensive
    cyclical_etfs  = ["XLK", "XLY", "XLC", "XLI", "XLF"]
    defensive_etfs = ["XLP", "XLU", "XLV"]
    commodity_etfs = ["XLE", "XLB"]

    cyc_rets  = [sector_data[e]["1m_return"] for e in cyclical_etfs  if e in sector_data]
    def_rets  = [sector_data[e]["1m_return"] for e in defensive_etfs if e in sector_data]
    com_rets  = [sector_data[e]["1m_return"] for e in commodity_etfs if e in sector_data]

    cyc_avg   = float(np.mean(cyc_rets))  if cyc_rets  else 0.0
    def_avg   = float(np.mean(def_rets))  if def_rets  else 0.0
    com_avg   = float(np.mean(com_rets))  if com_rets  else 0.0

    risk_regime = (
        "CYCLICAL"  if cyc_avg > def_avg + 1.0
        else "DEFENSIVE" if def_avg > cyc_avg + 1.0
        else "BALANCED"
    )
    regime_color = "#00FF88" if risk_regime == "CYCLICAL" else "#FF5252" if risk_regime == "DEFENSIVE" else "#FFD700"

    # Cycle phase estimate
    if cyc_avg > def_avg and cyc_avg > com_avg:
        phase = "Mid Expansion — Cyclical Leadership"
        phase_color = "#00FF88"
    elif com_avg > cyc_avg and com_avg > def_avg:
        phase = "Late Cycle — Commodity/Inflation Leadership"
        phase_color = "#FFD700"
    elif def_avg > cyc_avg:
        phase = "Contraction / Early Recession — Defensive Leadership"
        phase_color = "#FF5252"
    else:
        phase = "Early Recovery — Mixed Signals"
        phase_color = "#00E5FF"

    st.markdown(
        f"""<div style='display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px;'>
            <div style='background:#0d1f33;border:1px solid {phase_color};border-radius:8px;
                        padding:14px 22px;flex:2;min-width:240px;'>
                <p style='color:{phase_color};font-family:monospace;font-size:10px;
                          letter-spacing:1px;margin:0 0 5px;'>MARKET CYCLE PHASE</p>
                <p style='color:#F5ECD7;font-size:17px;font-weight:bold;margin:0;'>{phase}</p>
            </div>
            <div style='background:#0d1f33;border:1px solid {regime_color};border-radius:8px;
                        padding:14px 22px;flex:1;min-width:160px;text-align:center;'>
                <p style='color:{regime_color};font-family:monospace;font-size:10px;
                          letter-spacing:1px;margin:0 0 5px;'>RISK REGIME</p>
                <p style='color:{regime_color};font-size:18px;font-weight:bold;margin:0;'>{risk_regime}</p>
                <p style='color:#8898A8;font-size:11px;margin:3px 0 0;'>
                    Cyc {cyc_avg:+.1f}% / Def {def_avg:+.1f}%
                </p>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Sector heatmap
    sectors_sorted = sorted(sector_data.items(), key=lambda x: x[1]["1m_return"], reverse=True)
    etf_names  = [d["sector"] for _, d in sectors_sorted]
    returns_1m = [d["1m_return"] for _, d in sectors_sorted]
    bar_colors = ["#00FF88" if r > 0 else "#FF5252" for r in returns_1m]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=etf_names, y=returns_1m, marker_color=bar_colors,
        marker_line_width=0,
        text=[f"{r:+.1f}%" for r in returns_1m], textposition="outside",
        textfont=dict(color="#E8E0D0", size=10),
    ))
    layout_h = _tv_layout(height=300, title="Sector 1M Returns — Rotation Heatmap")
    layout_h["xaxis"] = {"gridcolor": "rgba(128,128,128,0.04)", "tickfont": {"color": "#8a8a8a", "size": 9}}
    layout_h["yaxis"] = _tv_yaxis(fixed_range=False)
    layout_h["margin"] = {"l": 10, "r": 50, "t": 50, "b": 60}
    fig.update_layout(**layout_h)
    st.plotly_chart(fig, use_container_width=True, config=TV_CONFIG)

    df_table = pd.DataFrame([{
        "Ticker": etf, "Sector": d["sector"],
        "1M Ret%": f"{d['1m_return']:+.1f}%",
        "3M Ret%": f"{d['3m_return']:+.1f}%",
        "vs MA50":  "↑" if d["above_ma50"]  else "↓",
        "vs MA200": "↑" if d["above_ma200"] else "↓",
        "Type": ("Cyclical" if etf in cyclical_etfs else
                 "Defensive" if etf in defensive_etfs else "Commodity"),
    } for etf, d in sectors_sorted])
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    sector_lines = [
        f"SECTOR ANALYST DATA — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Market Cycle Phase: {phase}",
        f"Risk Regime: {risk_regime} | Cyclical avg 1M: {cyc_avg:+.1f}% | "
        f"Defensive avg 1M: {def_avg:+.1f}% | Commodity avg 1M: {com_avg:+.1f}%", "",
        "SECTOR RANKINGS (by 1M return):",
    ]
    for etf, d in sectors_sorted:
        sector_lines.append(
            f"  {etf:<6} {d['sector']:<22} 1M:{d['1m_return']:+.1f}%  "
            f"3M:{d['3m_return']:+.1f}%  MA50:{'↑' if d['above_ma50'] else '↓'}  "
            f"MA200:{'↑' if d['above_ma200'] else '↓'}"
        )
    sector_lines.append("\nDeliver cycle phase assessment (with %), 2-3 rotation scenarios, "
                        "sector OW/UW recommendations, and tactical short-term opportunity.")
    user_content = "\n".join(sector_lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming sector rotation analysis…"):
            _stream(api_key, SYS_SECTOR_ANALYST, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("sector-analyst")


def _tab_scenario_analyzer(api_key: str) -> None:
    """Skill: scenario-analyzer — 18-month scenario analysis from news headlines."""
    _tab_header(
        "scenario-analyzer", "#EC4899",
        "Scenario Analyzer — 18-Month Base/Bull/Bear Scenarios",
        "Builds structured 18-month investment scenarios from any market headline or event. "
        "Covers 1st/2nd/3rd order sector impacts, positive/negative stock selection, "
        "and probability-weighted outcomes. Base + Bull + Bear = 100% always.",
    )
    with st.form("scenario_form"):
        headline = st.text_area(
            "Market Headline or Topic",
            height=80,
            placeholder=(
                "e.g. 'Fed signals 3 rate cuts in 2025, signals soft landing achieved'\n"
                "or 'China announces semiconductor export restrictions on US companies'\n"
                "or 'OPEC+ cuts production by 1.5M barrels per day'"
            ),
        )
        c1, c2 = st.columns(2)
        with c1:
            event_type = st.selectbox("Event Type",
                ["Monetary Policy", "Geopolitical", "Technology", "Commodity",
                 "Corporate/M&A", "Regulatory", "Economic Data"])
        with c2:
            horizon = st.selectbox("Time Horizon", ["18 Months (standard)", "12 Months", "6 Months"])
        submitted = st.form_submit_button("🧠 Run Scenario Analysis", type="primary")

    if not submitted:
        return

    if not headline.strip():
        st.error("Please enter a market headline or topic.")
        return

    # Fetch current market context
    with st.spinner("Fetching market context…"):
        sector_data = _fetch_sector_data()

    sector_summary = "\n".join(
        f"  {etf} {d['sector']}: 1M={d['1m_return']:+.1f}%"
        for etf, d in list(sector_data.items())[:8]
    ) if sector_data else "  Sector data unavailable"

    user_content = (
        f"SCENARIO ANALYZER\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
        f"Horizon: {horizon}\n\n"
        f"HEADLINE / TOPIC:\n{headline.strip()}\n\n"
        f"EVENT TYPE: {event_type}\n\n"
        f"CURRENT MARKET CONTEXT (live):\n{sector_summary}\n\n"
        f"Build the complete 18-month scenario analysis. "
        f"Probabilities must sum to 100%. Include 1st/2nd/3rd order sector impacts. "
        f"Stock selections must be US-listed (or ADRs). Provide monitoring checklist."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Building 18-month scenarios…"):
            _stream(api_key, SYS_SCENARIO, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("scenario-analyzer")


def _tab_backtest_expert(api_key: str) -> None:
    """Skill: backtest-expert — 'Beat ideas to death' strategy evaluation."""
    _tab_header(
        "backtest-expert", "#6366F1",
        "Backtest Expert — Beat Ideas to Death Methodology",
        "Evaluates trading strategies across 5 dimensions: Sample Size, Expectancy, "
        "Risk Management, Robustness, Execution Realism. Outputs Deploy / Refine / Abandon verdict. "
        "Philosophy: find strategies that 'break the least', not profit the most on paper.",
    )
    with st.form("backtest_form"):
        c1, c2 = st.columns(2)
        with c1:
            strategy_name  = st.text_input("Strategy Name", value="Post-Earnings Gap Fade")
            hypothesis     = st.text_area("Edge Hypothesis (one sentence)",
                placeholder="e.g. Stocks that gap up >5% on earnings and exceed 1.5x volume revert "
                            "to prior day close within 3 sessions.",
                height=80)
            total_trades   = st.number_input("Total Trades in Backtest", 1, 10000, 85)
            win_rate_pct   = st.number_input("Win Rate %", 0.0, 100.0, 58.0, 0.5)
        with c2:
            avg_win_pct    = st.number_input("Avg Win %",           0.01, 100.0, 2.1, 0.1)
            avg_loss_pct   = st.number_input("Avg Loss %",          0.01, 100.0, 1.4, 0.1)
            max_dd_pct     = st.number_input("Max Drawdown %",      0.0,  100.0, 18.0, 0.5)
            years_tested   = st.number_input("Years Tested",        1,    30,    7)
            num_params     = st.number_input("Number of Parameters",0,    20,    3)
            slippage_incl  = st.checkbox("Slippage stress-tested?", value=True)
            oos_ratio      = st.number_input("Out-of-Sample / In-Sample ratio", 0.0, 2.0, 0.65, 0.05,
                help="Ideally > 0.50. Values < 0.50 suggest overfitting.")
        notes = st.text_area("Additional Notes / Observations", height=60,
            placeholder="e.g. Strategy works well in bull markets. Struggling in high-VIX environments.")
        submitted = st.form_submit_button("🧪 Run Backtest Evaluation", type="primary")

    if not submitted:
        return

    # Quick scoring
    sample_score   = min(100.0, total_trades / 2.0)
    expectancy     = (win_rate_pct / 100.0) * avg_win_pct - ((100.0 - win_rate_pct) / 100.0) * avg_loss_pct
    expect_score   = max(0.0, min(100.0, 50.0 + expectancy * 15.0))
    risk_score     = max(0.0, min(100.0, 100.0 - max_dd_pct * 2.5))
    robust_score   = max(0.0, min(100.0,
        oos_ratio * 60.0
        - max(0.0, num_params - 3) * 8.0
        + years_tested * 3.0
        - (0.0 if slippage_incl else 15.0)
    ))
    exec_score     = 80.0 if slippage_incl else 40.0
    composite      = (
        sample_score * 0.20 + expect_score * 0.25 + risk_score * 0.20
        + robust_score * 0.20 + exec_score * 0.15
    )
    composite = round(composite, 1)

    if composite >= 70.0:
        verdict = "DEPLOY ✓"
        v_color = "#00FF88"
    elif composite >= 45.0:
        verdict = "REFINE 🔄"
        v_color = "#FFD700"
    else:
        verdict = "ABANDON ✗"
        v_color = "#FF5252"

    st.markdown(
        f"""<div style='background:#0a0a1a;border:2px solid {v_color};border-radius:12px;
                    padding:20px 28px;margin-bottom:14px;
                    display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;'>
            <div>
                <p style='color:{v_color};font-family:monospace;font-size:10px;
                          letter-spacing:2px;margin:0 0 4px;'>BACKTEST VERDICT</p>
                <p style='color:{v_color};font-size:42px;font-weight:bold;
                          font-family:monospace;margin:0;'>{verdict}</p>
            </div>
            <div style='text-align:right;'>
                <p style='color:#8898A8;font-size:13px;margin:0 0 4px;'>Composite Score</p>
                <p style='color:{v_color};font-size:36px;font-weight:bold;
                          font-family:monospace;margin:0;'>{composite:.0f}</p>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    dims = [
        ("Sample Size (20%)", sample_score, c1),
        ("Expectancy (25%)",  expect_score, c2),
        ("Risk Mgmt (20%)",   risk_score,   c3),
        ("Robustness (20%)",  robust_score, c4),
        ("Exec Real. (15%)",  exec_score,   c5),
    ]
    for label, score, col_obj in dims:
        with col_obj:
            st.metric(label, f"{score:.0f}/100")

    user_content = (
        f"BACKTEST EXPERT EVALUATION\n"
        f"Strategy: {strategy_name}\nDate: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"EDGE HYPOTHESIS: {hypothesis.strip()}\n\n"
        f"METRICS:\n"
        f"  Total trades: {total_trades} over {years_tested} years\n"
        f"  Win rate: {win_rate_pct:.1f}% | Avg win: {avg_win_pct:.1f}% | Avg loss: {avg_loss_pct:.1f}%\n"
        f"  Expectancy per trade: {expectancy:.2f}%\n"
        f"  Max drawdown: {max_dd_pct:.1f}%\n"
        f"  Parameters: {num_params} | OOS/IS ratio: {oos_ratio:.2f}\n"
        f"  Slippage stress-tested: {'YES' if slippage_incl else 'NO'}\n\n"
        f"PRELIMINARY SCORES:\n"
        f"  Sample Size: {sample_score:.0f} | Expectancy: {expect_score:.0f} | "
        f"Risk Mgmt: {risk_score:.0f} | Robustness: {robust_score:.0f} | Exec: {exec_score:.0f}\n"
        f"  Composite: {composite:.1f} | Verdict: {verdict}\n\n"
        f"NOTES: {notes or 'None'}\n\n"
        f"Deliver the complete 5-dimension evaluation. Identify specific red flags. "
        f"Provide the Deploy/Refine/Abandon verdict with specific action items. "
        f"State explicitly which stress tests should be run next."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Evaluating backtest…"):
            _stream(api_key, SYS_BACKTEST, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("backtest-expert")


def _tab_finviz_screener(api_key: str) -> None:
    """Skill: finviz-screener — Natural language to FinViz filter codes."""
    _tab_header(
        "finviz-screener", "#F97316",
        "FinViz Screener — Natural Language to Filter Codes",
        "Translates natural-language screening requests into precise FinViz filter codes. "
        "Supports Japanese and English. Provides the complete URL, filter table, "
        "recipe classification, and iterative refinement suggestions.",
    )
    with st.form("finviz_form"):
        request = st.text_area(
            "Screening Request (English or Japanese)",
            height=100,
            placeholder=(
                "Examples:\n"
                "• Find oversold large-cap technology stocks near 52-week lows with insider buying\n"
                "• 高配当で成長している小型株を探したい (yield 3-8%, dividend growth, small cap)\n"
                "• Minervini Stage 2 uptrend stocks near 52W high with volume expansion\n"
                "• Deep value: P/E < 15, P/B < 1.5, positive FCF, no debt issues"
            ),
        )
        c1, c2 = st.columns(2)
        with c1:
            view_type    = st.selectbox("FinViz View",
                ["Overview", "Valuation", "Financial", "Technical", "Ownership", "Performance"])
            sort_by      = st.selectbox("Sort By",
                ["Market Cap (desc)", "Dividend Yield (desc)", "Change (desc)",
                 "Volume (desc)", "P/E (asc)", "Custom"])
        with c2:
            elite_mode   = st.checkbox("FinViz Elite mode", value=False,
                help="Enable if you have a FINVIZ Elite subscription.")
            min_cap      = st.selectbox("Minimum Market Cap",
                ["Any", "Micro (>$50M)", "Small (>$300M)", "Mid (>$2B)", "Large (>$10B)", "Mega (>$100B)"])
        submitted = st.form_submit_button("🔎 Generate Screener", type="primary")

    if not submitted:
        return

    if not request.strip():
        st.error("Please describe your screening criteria.")
        return

    # Map common concepts to filter codes
    cap_map = {
        "Any": "", "Micro (>$50M)": "cap_microover", "Small (>$300M)": "cap_smallover",
        "Mid (>$2B)": "cap_midover", "Large (>$10B)": "cap_largeunder",
        "Mega (>$100B)": "cap_mega",
    }
    view_map = {
        "Overview": "v=111", "Valuation": "v=121", "Financial": "v=161",
        "Technical": "v=171", "Ownership": "v=131", "Performance": "v=141",
    }
    sort_map = {
        "Market Cap (desc)": "marketcap", "Dividend Yield (desc)": "dividendyield",
        "Change (desc)": "-change", "Volume (desc)": "-volume",
        "P/E (asc)": "pe", "Custom": "",
    }

    cap_filter = cap_map.get(min_cap, "")
    view_code  = view_map.get(view_type, "v=111")
    sort_code  = sort_map.get(sort_by, "")

    # Display current context
    st.markdown(
        f"""<div style='background:#080f1a;border:1px solid rgba(249,115,22,0.22);
                    border-radius:8px;padding:14px 20px;margin-bottom:12px;'>
            <p style='font-family:monospace;font-size:11px;color:#F97316;margin:0 0 6px;'>
                SCREENER CONFIGURATION
            </p>
            <p style='font-family:monospace;font-size:12px;color:#E8E0D0;margin:0;'>
                View: <strong>{view_type}</strong> &nbsp;|&nbsp;
                Sort: <strong>{sort_by}</strong> &nbsp;|&nbsp;
                Min Cap: <strong>{min_cap}</strong> &nbsp;|&nbsp;
                Mode: <strong>{'Elite' if elite_mode else 'Public'}</strong>
            </p>
        </div>""",
        unsafe_allow_html=True,
    )

    user_content = (
        f"FINVIZ SCREENER REQUEST\nDate: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"USER REQUEST: {request.strip()}\n\n"
        f"CONFIGURATION:\n"
        f"  View: {view_type} ({view_code})\n"
        f"  Sort: {sort_by} ({sort_code})\n"
        f"  Min Market Cap: {min_cap} → filter code: {cap_filter or 'none'}\n"
        f"  Mode: {'Elite' if elite_mode else 'Public'}\n\n"
        f"Build the complete FinViz screener: translate the request into filter codes, "
        f"show the filter table, construct the URL, classify the recipe type, "
        f"and provide iterative refinement suggestions (how to tighten or broaden)."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Building FinViz screener…"):
            _stream(api_key, SYS_FINVIZ, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("finviz-screener")


def _tab_pair_trade(api_key: str) -> None:
    """Skill: pair-trade-screener — Statistical arbitrage Z-score analysis."""
    _tab_header(
        "pair-trade-screener", "#A78BFA",
        "Pair Trade Screener — Statistical Arbitrage Z-Score",
        "Analyzes price pairs for cointegration, spread z-score, and mean reversion signals. "
        "Applies the statistical arbitrage methodology: Z-score > 2.0 = entry signal, "
        "Z-score → 0 = exit target, Z-score > 3.5 = stop-loss (spread breakdown).",
    )
    with st.form("pair_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            preset_pair = st.selectbox("Preset Pair",
                ["Custom"] + [f"{a} / {b} ({cat})" for a, b, cat in STAT_ARB_PAIRS])
        with c2:
            ticker_a = st.text_input("Ticker A", value="AAPL").upper().strip()
            ticker_b = st.text_input("Ticker B", value="MSFT").upper().strip()
        with c3:
            lookback_yr_p = st.selectbox("Lookback", ["1 Year", "2 Years"])
            notes_pair    = st.text_area("Pair Thesis", height=70,
                placeholder="e.g. Both are AI infrastructure plays. Pairs-trading historical premium.")
        submitted = st.form_submit_button("🔗 Analyze Pair", type="primary")

    if not submitted:
        return

    # Apply preset if selected
    ta, tb = ticker_a, ticker_b
    if preset_pair != "Custom":
        for a, b, cat in STAT_ARB_PAIRS:
            if a in preset_pair and b in preset_pair:
                ta, tb = a, b
                break

    years_p = 2 if "2" in lookback_yr_p else 1

    with st.spinner(f"Fetching {ta} and {tb}…"):
        df_a = _fetch_history(ta, years=years_p)
        df_b = _fetch_history(tb, years=years_p)

    if df_a.empty or df_b.empty:
        st.error("Could not fetch price data for one or both tickers.")
        return

    zscore_data = _compute_zscore(df_a["close"], df_b["close"])

    # Dual-axis chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_a.index, y=df_a["close"].values,
        mode="lines", name=ta,
        line=dict(color="#00E5FF", width=1.8),
    ))
    fig.add_trace(go.Scatter(
        x=df_b.index, y=df_b["close"].values,
        mode="lines", name=tb,
        line=dict(color="#FFD700", width=1.8),
        yaxis="y2",
    ))
    layout_pair = _tv_layout(height=320, title=f"{ta} vs {tb} — Pair Analysis")
    layout_pair["xaxis"] = _tv_xaxis()
    layout_pair["yaxis"] = _tv_yaxis()
    layout_pair["yaxis2"] = {"side": "left", "overlaying": "y", "showgrid": False,
                              "tickfont": {"color": "#8a8a8a", "size": 10}}
    fig.update_layout(**layout_pair)
    st.plotly_chart(fig, use_container_width=True, config=TV_CONFIG)

    zscore = zscore_data["zscore"]
    signal = zscore_data["signal"]
    signal_color = (
        "#00FF88" if "LONG_A" in signal
        else "#FF5252" if "SHORT_A" in signal
        else "#FFD700"
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Z-Score", f"{zscore:.3f}")
    with c2: st.metric("Signal", signal.replace("_", " "))
    with c3: st.metric("Correlation (1Y)", f"{zscore_data['correlation']:.3f}")
    with c4: st.metric("Hedge Ratio", f"{zscore_data['ratio']:.4f}")

    user_content = (
        f"PAIR TRADE ANALYSIS: {ta} vs {tb}\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')} | Lookback: {years_p} year(s)\n\n"
        f"PRICE DATA:\n"
        f"  {ta}: ${float(df_a['close'].iloc[-1]):.2f} (current)\n"
        f"  {tb}: ${float(df_b['close'].iloc[-1]):.2f} (current)\n\n"
        f"STATISTICAL METRICS:\n"
        f"  Hedge ratio ({ta}/{tb}): {zscore_data['ratio']:.4f}\n"
        f"  Spread mean: {zscore_data['spread_mean']:.4f}\n"
        f"  Spread std:  {zscore_data['spread_std']:.4f}\n"
        f"  Z-score:     {zscore:.3f}\n"
        f"  Correlation: {zscore_data['correlation']:.3f}\n"
        f"  Observations: {zscore_data['n_obs']}\n\n"
        f"SIGNAL: {signal}\n"
        f"  Entry condition: |Z-score| > 2.0 — current {abs(zscore):.3f} "
        f"{'→ SIGNAL ACTIVE' if abs(zscore) > 2.0 else '→ NO SIGNAL'}\n"
        f"  Exit target: Z-score → 0 (mean reversion)\n"
        f"  Stop-loss: |Z-score| > 3.5 (spread breakdown)\n\n"
        f"PAIR THESIS: {notes_pair or 'Not provided'}\n\n"
        f"Deliver the complete pair trade analysis: cointegration assessment, "
        f"current spread position, signal strength, dollar-neutral sizing, and risk factors."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming pair trade analysis…"):
            _stream(api_key, SYS_PAIR_TRADE, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("pair-trade-screener")


def _tab_downtrend_analyzer(api_key: str) -> None:
    """Skill: downtrend-duration-analyzer — Historical correction duration statistics."""
    _tab_header(
        "downtrend-duration-analyzer", "#FB7185",
        "Downtrend Duration Analyzer — Correction Length Statistics",
        "Analyzes historical peak-to-trough durations for stocks/ETFs across sectors and market caps. "
        "Generates statistical distributions (P25/P50/P75/P90) to set realistic holding periods "
        "for mean-reversion strategies and define stop-loss timeouts.",
    )
    with st.form("downtrend_form"):
        c1, c2 = st.columns(2)
        with c1:
            tickers_input = st.text_area(
                "Tickers to Analyze (one per line)",
                value="SPY\nQQQ\nIWM\nXLK\nXLE",
                height=130,
            )
            lookback_yr_d = st.selectbox("Historical Lookback", ["3 Years", "5 Years", "10 Years (approx.5Y)"])
        with c2:
            sector_focus  = st.selectbox("Sector Focus", ["All"] + list(SECTOR_ETFS.values()))
            drop_thresh   = st.number_input("Min Correction Threshold %",
                min_value=1.0, max_value=30.0, value=5.0, step=0.5,
                help="Minimum decline to qualify as a corrective move.")
        submitted = st.form_submit_button("📉 Analyze Downtrend Durations", type="primary")

    if not submitted:
        return

    tickers = [t.strip().upper() for t in tickers_input.strip().splitlines() if t.strip()]
    if not tickers:
        st.error("No tickers entered.")
        return

    years_d = 3 if "3" in lookback_yr_d else 5

    # Fetch and compute corrections
    results: List[Dict[str, Any]] = []
    bar = st.progress(0, text="Computing downtrend statistics…")
    for i, tkr in enumerate(tickers[:10]):
        bar.progress((i + 1) / min(len(tickers), 10), text=f"Analyzing {tkr}…")
        df = _fetch_history(tkr, years=years_d)
        if df.empty or len(df) < 30:
            continue

        close = df["close"]
        drops: List[int] = []
        peak_idx = 0
        for j in range(1, len(close)):
            if float(close.iloc[j]) > float(close.iloc[peak_idx]):
                peak_idx = j
            else:
                drop_pct = (float(close.iloc[j]) / float(close.iloc[peak_idx]) - 1.0) * 100.0
                if drop_pct <= -float(drop_thresh):
                    duration = j - peak_idx
                    drops.append(duration)

        if drops:
            results.append({
                "ticker":  tkr,
                "count":   len(drops),
                "p25":     int(np.percentile(drops, 25)),
                "p50":     int(np.percentile(drops, 50)),
                "p75":     int(np.percentile(drops, 75)),
                "p90":     int(np.percentile(drops, 90)),
                "mean":    round(float(np.mean(drops)), 1),
                "max":     max(drops),
                "min":     min(drops),
            })
        time.sleep(0.05)
    bar.empty()

    if not results:
        st.error("Could not compute statistics. Try different tickers.")
        return

    # Display table
    df_res = pd.DataFrame(results)
    df_res.columns = ["Ticker", "Count", "P25(d)", "Median(d)", "P75(d)", "P90(d)", "Mean(d)", "Max(d)", "Min(d)"]
    st.dataframe(df_res, use_container_width=True, hide_index=True)

    # Box plot
    fig = go.Figure()
    for r in results:
        fig.add_trace(go.Box(
            name=r["ticker"],
            q1=[r["p25"]], median=[r["p50"]], q3=[r["p75"]],
            lowerfence=[r["min"]], upperfence=[r["p90"]],
            mean=[r["mean"]], boxmean=True,
            marker_color="#00E5FF",
            fillcolor="rgba(0,229,255,0.15)",
        ))
    layout_box = _tv_layout(height=320, title=f"Downtrend Duration Distribution (>{drop_thresh:.0f}% corrections)")
    layout_box["xaxis"] = {"gridcolor": "rgba(128,128,128,0.04)", "tickfont": {"color": "#8a8a8a", "size": 10}}
    layout_box["yaxis"] = _tv_yaxis(fixed_range=False)
    layout_box["yaxis"]["title"] = {"text": "Duration (trading days)", "font": {"color": "#8a8a8a", "size": 9}}
    layout_box["margin"] = {"l": 20, "r": 80, "t": 50, "b": 50}
    fig.update_layout(**layout_box)
    st.plotly_chart(fig, use_container_width=True, config=TV_CONFIG)

    stats_lines = [
        f"DOWNTREND DURATION ANALYSIS — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Threshold: >{drop_thresh:.0f}% corrections | Lookback: {years_d} years | "
        f"Sector: {sector_focus}", "",
        "STATISTICS BY TICKER:",
    ]
    for r in results:
        stats_lines.append(
            f"  {r['ticker']:<6} Count={r['count']:>3} | P25={r['p25']:>3}d | "
            f"Median={r['p50']:>3}d | P75={r['p75']:>3}d | P90={r['p90']:>3}d | Mean={r['mean']}d"
        )
    stats_lines.append("\nDeliver complete duration analysis with key insights, "
                       "sector/cap comparison, and strategy implications.")
    user_content = "\n".join(stats_lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming downtrend analysis…"):
            _stream(api_key, SYS_DOWNTREND, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("downtrend-duration-analyzer")


def _tab_signal_postmortem(api_key: str) -> None:
    """Skill: signal-postmortem — Trade outcome attribution and feedback."""
    _tab_header(
        "signal-postmortem", "#F43F5E",
        "Signal Postmortem — Outcome Attribution & Feedback Loop",
        "Records and analyzes post-trade outcomes: TRUE_POSITIVE / FALSE_POSITIVE / "
        "MISSED_OPPORTUNITY / REGIME_MISMATCH. Generates weight adjustment recommendations "
        "for edge pipeline skills and identifies systematic failure patterns.",
    )
    with st.form("postmortem_form"):
        signals_input = st.text_area(
            "Signal Outcomes (one per line: TICKER | DATE | DIRECTION | ENTRY$ | EXIT$ | SOURCE_SKILL)",
            height=180,
            placeholder=(
                "NVDA | 2026-01-15 | LONG | 125.50 | 138.20 | vcp-screener\n"
                "META | 2026-01-20 | LONG | 585.00 | 562.30 | earnings-trade-analyzer\n"
                "AAPL | 2026-02-01 | LONG | 235.00 | 241.50 | pead-screener\n"
                "TSLA | 2026-02-10 | LONG | 320.00 | 298.00 | vcp-screener\n"
                "JPM  | 2026-02-15 | LONG | 225.00 | 232.50 | kanchi-dividend-sop"
            ),
        )
        c1, c2 = st.columns(2)
        with c1:
            market_regime = st.selectbox("Market Regime at Time of Signals",
                ["RISK_ON", "RISK_OFF", "MIXED/TRANSITIONAL"])
        with c2:
            period_label = st.text_input("Analysis Period", value="Q1 2026")
        submitted = st.form_submit_button("📊 Run Signal Postmortem", type="primary")

    if not submitted:
        return

    # Parse signals
    signal_records: List[Dict[str, Any]] = []
    for line in signals_input.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        try:
            ticker  = parts[0].upper()
            date_s  = parts[1] if len(parts) > 1 else "?"
            direction = parts[2].upper() if len(parts) > 2 else "LONG"
            entry   = float(parts[3]) if len(parts) > 3 else 0.0
            exit_p  = float(parts[4]) if len(parts) > 4 else 0.0
            skill   = parts[5] if len(parts) > 5 else "unknown"
            ret_pct = (exit_p / entry - 1.0) * 100.0 if entry > 1e-10 else 0.0
            outcome = (
                "TRUE_POSITIVE"  if ret_pct > 0.0
                else "FALSE_POSITIVE"
            )
            signal_records.append({
                "ticker": ticker, "date": date_s, "direction": direction,
                "entry": entry, "exit": exit_p, "return_pct": round(ret_pct, 2),
                "skill": skill, "outcome": outcome,
            })
        except ValueError:
            continue

    if not signal_records:
        st.error("No valid signal records parsed. Check format.")
        return

    # Summary
    outcomes = {"TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "MISSED_OPPORTUNITY": 0, "REGIME_MISMATCH": 0}
    for r in signal_records:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

    total    = len(signal_records)
    win_rate = outcomes["TRUE_POSITIVE"] / total * 100.0 if total > 0 else 0.0
    avg_ret  = float(np.mean([r["return_pct"] for r in signal_records]))

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Signals",    total)
    with c2: st.metric("Win Rate",         f"{win_rate:.1f}%")
    with c3: st.metric("Avg Return",       f"{avg_ret:+.2f}%")
    with c4: st.metric("False Positives",  outcomes["FALSE_POSITIVE"])

    df_res = pd.DataFrame([{
        "Ticker": r["ticker"], "Date": r["date"], "Direction": r["direction"],
        "Entry": f"${r['entry']:.2f}", "Exit": f"${r['exit']:.2f}",
        "Return%": f"{r['return_pct']:+.2f}%", "Outcome": r["outcome"],
        "Skill": r["skill"],
    } for r in signal_records])
    st.dataframe(df_res, use_container_width=True, hide_index=True)

    lines = [
        f"SIGNAL POSTMORTEM — {period_label}",
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')} | Regime: {market_regime}",
        f"Total: {total} | Win rate: {win_rate:.1f}% | Avg return: {avg_ret:+.2f}%", "",
        "SIGNAL DETAILS:",
    ]
    for r in signal_records:
        lines.append(
            f"  {r['ticker']:<6} {r['date']} {r['direction']:<5} "
            f"${r['entry']:.2f}→${r['exit']:.2f} ({r['return_pct']:+.1f}%) "
            f"[{r['outcome']}] Source:{r['skill']}"
        )
    lines.append(f"\nDeliver the complete signal postmortem: outcome classification, "
                 "skill performance table, regime analysis, false positive patterns, "
                 "and weight adjustment recommendations.")
    user_content = "\n".join(lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Running signal postmortem…"):
            _stream(api_key, SYS_POSTMORTEM, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("signal-postmortem")


def _tab_strategy_pivot(api_key: str) -> None:
    """Skill: strategy-pivot-designer — Break out of backtest local optima."""
    _tab_header(
        "strategy-pivot-designer", "#7C3AED",
        "Strategy Pivot Designer — Break Backtest Stagnation",
        "Detects when parameter tuning has reached a local optimum and proposes 3 structurally "
        "different pivot architectures: Assumption Inversion, Archetype Switch, Objective Reframe. "
        "Each pivot is scored for quality potential and novelty.",
    )
    with st.form("pivot_form"):
        c1, c2 = st.columns(2)
        with c1:
            strategy_desc = st.text_area(
                "Current Strategy Description",
                height=100,
                placeholder="e.g. Mean reversion on daily RSI(14) < 30 with 3-day holding period. "
                            "Stop at -3%, target at +2.5%. Filtered by: mid-cap+, avg vol > 500K."
            )
            num_iterations = st.number_input("Iteration Count (optimization rounds)", 1, 100, 15)
        with c2:
            score_history = st.text_area(
                "Score History (last N iterations, comma-separated)",
                placeholder="72, 73, 74, 73, 74, 73, 73, 74, 74, 73, 74, 73, 74, 73, 74",
                height=80,
            )
            stagnation_triggers = st.multiselect(
                "Observed Issues",
                ["Score Plateau", "Overfitting", "Transaction Cost Defeat",
                 "Tail Risk / Drawdown", "Regime Dependent", "Small Sample"],
                default=["Score Plateau"],
            )
        submitted = st.form_submit_button("🔄 Generate Pivot Proposals", type="primary")

    if not submitted:
        return

    # Parse score history
    score_list: List[float] = []
    if score_history.strip():
        for s in score_history.strip().split(","):
            try:
                score_list.append(float(s.strip()))
            except ValueError:
                pass

    plateau_detected = False
    if len(score_list) >= 5:
        recent_5   = score_list[-5:]
        score_range = max(recent_5) - min(recent_5)
        plateau_detected = score_range < 3.0

    user_content = (
        f"STRATEGY PIVOT DESIGNER\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"CURRENT STRATEGY:\n{strategy_desc.strip()}\n\n"
        f"ITERATION HISTORY:\n"
        f"  Total iterations: {num_iterations}\n"
        f"  Score history (last {len(score_list)}): {', '.join(f'{s:.0f}' for s in score_list)}\n"
        f"  Plateau detected: {'YES — range {score_range:.1f} over last 5 iterations' if plateau_detected else 'Inconclusive'}\n\n"
        f"STAGNATION TRIGGERS: {', '.join(stagnation_triggers)}\n\n"
        f"Generate 3 structurally distinct pivot proposals:\n"
        f"1. Assumption Inversion — identify the core assumption and flip it\n"
        f"2. Archetype Switch — change from {strategy_desc.split()[0] if strategy_desc.strip() else 'current'} to a different strategy type\n"
        f"3. Objective Reframe — optimize for something other than current objective\n\n"
        f"Score each pivot for quality potential (0-100) and novelty. "
        f"Specify which is export-ready for edge-candidate-agent pipeline."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Designing strategy pivots…"):
            _stream(api_key, SYS_PIVOT, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("strategy-pivot-designer")


def _tab_kanchi_monitor(api_key: str) -> None:
    """Skill: kanchi-dividend-review-monitor — T1-T5 trigger monitoring."""
    _tab_header(
        "kanchi-dividend-review-monitor", "#EF4444",
        "Kanchi Dividend Monitor — T1-T5 Trigger Review Queue",
        "Monitors dividend holdings for T1-T5 anomaly triggers: T1=dividend cut/suspension, "
        "T2=coverage deterioration, T3=credit stress, T4=SEC 8-K governance, T5=structural decline. "
        "Outputs OK / WARN / REVIEW states. Never auto-sells — always human confirmation first.",
    )
    with st.form("monitor_form"):
        holdings_input = st.text_area(
            "Current Holdings (TICKER:YIELD% — one per line)",
            value="JNJ:3.2\nPG:2.8\nKO:3.1\nABBV:4.5\nO:5.8\nVZ:7.2",
            height=150,
            help="Format: TICKER:CURRENT_YIELD_PCT. Yield helps detect T1 cuts."
        )
        c1, c2 = st.columns(2)
        with c1:
            monitor_context = st.text_area("Recent Alerts / Observations",
                placeholder="e.g. VZ cutting guidance. ABBV patent cliff approaching.",
                height=80)
        with c2:
            cadence = st.selectbox("Monitoring Cadence",
                ["Daily (T1+T4)", "Weekly (T1+T3+T4)", "Quarterly (T1-T5 full)"])
        submitted = st.form_submit_button("🚨 Run Portfolio Monitor", type="primary")

    if not submitted:
        return

    # Parse holdings
    holdings: Dict[str, float] = {}
    for line in holdings_input.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        parts = line.split(":")
        try:
            tkr     = parts[0].strip().upper()
            cur_yld = float(parts[1].strip())
            if tkr:
                holdings[tkr] = cur_yld
        except ValueError:
            continue

    if not holdings:
        st.error("No valid holdings parsed.")
        return

    # Fetch data and compute trigger indicators
    screened: Dict[str, Dict[str, Any]] = {}
    bar = st.progress(0, text="Fetching dividend data…")
    for i, tkr in enumerate(holdings):
        bar.progress((i + 1) / len(holdings), text=f"Checking {tkr}…")
        inf = _fetch_info(tkr)
        if inf:
            screened[tkr] = inf
        time.sleep(0.05)
    bar.empty()

    # Classify each holding
    statuses: List[Dict[str, Any]] = []
    for tkr, cur_yld in holdings.items():
        d         = screened.get(tkr, {})
        live_yld  = d.get("dividend_yield")
        live_yld_pct = float(live_yld) * 100.0 if live_yld else 0.0
        payout    = d.get("payout_ratio")

        t1_flag = False  # Dividend cut
        t2_flag = False  # Coverage deterioration
        t5_flag = False  # Structural decline

        if live_yld_pct > 0 and cur_yld > 0:
            yld_change_pct = (live_yld_pct / cur_yld - 1.0) * 100.0
            if yld_change_pct < -20.0:
                t1_flag = True

        if payout is not None and float(payout) > 0.85:
            t2_flag = True

        rev_grw = d.get("revenue_growth")
        earn_grw = d.get("earnings_growth")
        if rev_grw is not None and earn_grw is not None:
            if float(rev_grw) < -0.10 and float(earn_grw) < -0.15:
                t5_flag = True

        triggers = []
        if t1_flag: triggers.append("T1-CUT")
        if t2_flag: triggers.append("T2-COVERAGE")
        if t5_flag: triggers.append("T5-DECLINE")

        status = "OK" if not triggers else "REVIEW" if t1_flag else "WARN"
        statuses.append({
            "ticker":     tkr,
            "user_yield": cur_yld,
            "live_yield": round(live_yld_pct, 2),
            "payout_pct": round(float(payout) * 100.0, 1) if payout else 0.0,
            "triggers":   triggers,
            "status":     status,
        })

    # Display
    ok_n     = sum(1 for s in statuses if s["status"] == "OK")
    warn_n   = sum(1 for s in statuses if s["status"] == "WARN")
    review_n = sum(1 for s in statuses if s["status"] == "REVIEW")

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("✅ OK",     ok_n)
    with c2: st.metric("⚠️ WARN",   warn_n)
    with c3: st.metric("🚨 REVIEW", review_n)

    df_status = pd.DataFrame([{
        "Ticker":     s["ticker"],
        "User Yld%":  f"{s['user_yield']:.1f}%",
        "Live Yld%":  f"{s['live_yield']:.1f}%",
        "Payout%":    f"{s['payout_pct']:.0f}%" if s["payout_pct"] > 0 else "N/A",
        "Triggers":   ", ".join(s["triggers"]) if s["triggers"] else "None",
        "Status":     s["status"],
    } for s in statuses])
    st.dataframe(df_status, use_container_width=True, hide_index=True)

    lines = [
        f"KANCHI DIVIDEND MONITOR — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Cadence: {cadence} | Holdings: {len(holdings)}"
        f" | OK: {ok_n} | WARN: {warn_n} | REVIEW: {review_n}", "",
        "PORTFOLIO STATUS:",
    ]
    for s in statuses:
        lines.append(
            f"  {s['ticker']:<8} YldUser:{s['user_yield']:.1f}% YldLive:{s['live_yield']:.1f}% "
            f"Payout:{s['payout_pct']:.0f}% Triggers:{','.join(s['triggers']) or 'None'} → {s['status']}"
        )
    lines += [
        f"\nOBSERVATIONS: {monitor_context or 'None'}",
        "\nApply T1-T5 trigger logic. Generate review tickets for REVIEW items. "
        "WARN items: add to next cycle, pause optional adds. "
        "NEVER recommend auto-sell — always human confirmation first.",
    ]
    user_content = "\n".join(lines)

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Running dividend portfolio monitor…"):
            _stream(api_key, SYS_KANCHI_MONITOR, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("kanchi-dividend-review-monitor")


def _tab_trader_memory(api_key: str) -> None:
    """Skill: trader-memory-core — Investment thesis lifecycle tracker."""
    _tab_header(
        "trader-memory-core", "#0D9488",
        "Trader Memory Core — Investment Thesis Lifecycle",
        "Tracks investment theses from IDEA → ENTRY_READY → ACTIVE → CLOSED with full postmortem. "
        "Records source skill, sizing data, review dates, and MAE/MFE metrics. "
        "Maintains persistent investment journal with lessons learned.",
    )
    with st.form("memory_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker_m     = st.text_input("Ticker",    value="NVDA").upper().strip()
            thesis_type  = st.selectbox("Thesis Type",
                ["growth_momentum", "dividend_income", "mean_reversion",
                 "earnings_drift", "pivot_breakout"])
            status_m     = st.selectbox("Current Status",
                ["IDEA", "ENTRY_READY", "ACTIVE", "CLOSED", "INVALIDATED"])
            source_skill = st.selectbox("Source Skill",
                ["vcp-screener", "earnings-trade-analyzer", "pead-screener",
                 "kanchi-dividend-sop", "edge-candidate-agent", "manual"])
        with c2:
            entry_price_m  = st.number_input("Entry Price ($, 0=not yet entered)",
                min_value=0.0, value=0.0, step=0.5)
            stop_price_m   = st.number_input("Stop-Loss ($)", min_value=0.0, value=0.0, step=0.5)
            target_price_m = st.number_input("Target Price ($)", min_value=0.0, value=0.0, step=0.5)
            exit_price_m   = st.number_input("Exit Price ($, 0=not exited)",
                min_value=0.0, value=0.0, step=0.5)
        thesis_text = st.text_area("Thesis / Notes",
            placeholder="e.g. VCP pattern forming after strong earnings gap. "
                        "Stage 2 uptrend with 3 clean contractions. Vol dry-up confirmed. "
                        "Entry on breakout above $X. Stop below $Y.",
            height=100)
        submitted = st.form_submit_button("📝 Log Thesis", type="primary")

    if not submitted:
        return

    with st.spinner(f"Fetching {ticker_m}…"):
        inf   = _fetch_info(ticker_m)
        df_m  = _fetch_history(ticker_m, years=1)

    cur_price = inf.get("current_price", 0.0) or 0.0

    # Compute P&L if exit provided
    pnl_pct = 0.0
    ep       = float(entry_price_m)
    xp       = float(exit_price_m)
    if ep > 1e-10 and xp > 1e-10:
        pnl_pct = (xp / ep - 1.0) * 100.0

    # MAE/MFE estimation from price history if active
    mae = 0.0
    mfe = 0.0
    if ep > 1e-10 and not df_m.empty:
        close_from_entry = df_m["close"].iloc[-90:]
        if len(close_from_entry) > 5:
            mae = float((close_from_entry.min() / ep - 1.0) * 100.0) if ep > 1e-10 else 0.0
            mfe = float((close_from_entry.max() / ep - 1.0) * 100.0) if ep > 1e-10 else 0.0

    # Display thesis card
    status_color = {
        "IDEA": "#8898A8", "ENTRY_READY": "#FFD700",
        "ACTIVE": "#00FF88", "CLOSED": "#00E5FF", "INVALIDATED": "#FF5252",
    }.get(status_m, "#8898A8")

    st.markdown(
        f"""<div style='background:#080f1a;border-left:5px solid {status_color};border-radius:8px;
                    padding:16px 22px;margin-bottom:14px;'>
            <div style='display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;'>
                <div>
                    <p style='color:{status_color};font-family:monospace;font-size:10px;
                              letter-spacing:2px;margin:0 0 4px;'>{status_m}</p>
                    <p style='color:#F5ECD7;font-size:20px;font-weight:bold;margin:0;'>
                        {ticker_m} — {thesis_type.replace("_"," ").title()}
                    </p>
                    <p style='color:#8898A8;font-size:12px;margin:4px 0 0;'>
                        Source: {source_skill} | Live price: ${float(cur_price):.2f}
                    </p>
                </div>
                {'<p style="color:' + ("#00FF88" if pnl_pct >= 0 else "#FF5252") + ';font-size:24px;font-weight:bold;font-family:monospace;margin:0;">' + f"{pnl_pct:+.1f}% P&L" + '</p>' if ep > 1e-10 and xp > 1e-10 else ""}
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    if not df_m.empty:
        ind_m = _compute_indicators(df_m)
        st.plotly_chart(
            _price_chart(df_m.tail(90), ticker_m,
                         title=f"{ticker_m} — Thesis Chart (90D)",
                         indicators={k: ind_m[k].tail(90) for k in ["ema_21","sma_200"]}),
            use_container_width=True, config=TV_CONFIG,
        )

    if ep > 1e-10:
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Entry",  f"${ep:.2f}")
        with c2: st.metric("Stop",   f"${float(stop_price_m):.2f}" if stop_price_m > 0 else "N/A")
        with c3: st.metric("Target", f"${float(target_price_m):.2f}" if target_price_m > 0 else "N/A")
        with c4: st.metric("MAE/MFE", f"{mae:+.1f}% / {mfe:+.1f}%")

    user_content = (
        f"TRADER MEMORY CORE — THESIS LOG\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"THESIS:\n"
        f"  Ticker: {ticker_m} | Company: {inf.get('name', ticker_m)}\n"
        f"  Type: {thesis_type} | Status: {status_m}\n"
        f"  Source: {source_skill}\n\n"
        f"PRICES:\n"
        f"  Live price: ${float(cur_price):.2f}\n"
        f"  Entry: ${ep:.2f if ep > 0 else 'Not yet entered'}\n"
        f"  Stop: ${float(stop_price_m):.2f if stop_price_m > 0 else 'Not set'}\n"
        f"  Target: ${float(target_price_m):.2f if target_price_m > 0 else 'Not set'}\n"
        f"  Exit: ${xp:.2f if xp > 0 else 'Not exited'}\n"
        + (f"  P&L: {pnl_pct:+.2f}%\n" if ep > 1e-10 and xp > 1e-10 else "")
        + (f"  MAE (worst drawdown since entry): {mae:+.1f}%\n"
           f"  MFE (best level since entry): {mfe:+.1f}%\n" if ep > 1e-10 else "")
        + f"\nFUNDAMENTALS:\n"
        f"  Sector: {inf.get('sector')} | Cap: {_bn(inf.get('market_cap'))}\n"
        f"  P/E: {_flt(inf.get('pe_ratio'),'.1f')} | Beta: {_flt(inf.get('beta'),'.2f')}\n\n"
        f"THESIS TEXT:\n{thesis_text.strip()}\n\n"
        f"Generate the complete thesis tracker documentation: thesis ID, lifecycle state, "
        f"monitoring schedule, and if CLOSED — full postmortem with lessons learned."
    )

    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Generating thesis documentation…"):
            _stream(api_key, SYS_TRADER_MEMORY, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
    _analysis_footer("trader-memory-core")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def main() -> None:
    """
    Main entry point for Trading Intelligence Hub V2.
    Renders 18 tabs — one per new skill.
    Total platform: 13 (Hub V1) + 18 (Hub V2) = 31 skills.
    """
    st.markdown(HUB_V2_CSS, unsafe_allow_html=True)

    # ── PAGE HEADER ───────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='background:linear-gradient(135deg,#001a33 0%,#000d1a 50%,#0a001a 100%);
                    border:1px solid rgba(168,85,247,0.22);border-radius:12px;
                    padding:26px 34px;margin-bottom:18px;'>
            <div style='margin-bottom:12px;'>
                <span style='background:rgba(168,85,247,0.12);color:#A855F7;
                             font-size:10px;font-family:monospace;font-weight:bold;
                             padding:4px 14px;border-radius:3px;
                             border:1px solid rgba(168,85,247,0.30);letter-spacing:2px;'>
                    18 NEW SKILLS · LIVE DATA · LLAMA 3.3 70B · HUB V2
                </span>
            </div>
            <h1 style='color:#F5ECD7;font-family:"Times New Roman",serif;
                       font-size:28px;font-weight:bold;margin:0 0 8px 0;'>
                Intelligence Hub V2 — Advanced Trading Skills
            </h1>
            <p style='color:rgba(168,85,247,0.90);font-family:monospace;font-size:11px;
                      margin:0 0 10px 0;letter-spacing:1.5px;'>
                ◆ VCP · PEAD · MACRO REGIME · FTD · EXPOSURE COACH · INSTITUTIONAL FLOW · KANCHI ·
                POSITION SIZER · SECTOR ANALYST · SCENARIO · BACKTEST · FINVIZ · PAIRS · MORE
            </p>
            <p style='color:#7888A0;font-size:14px;line-height:1.85;margin:0;
                      font-family:"Times New Roman",serif;max-width:820px;'>
                18 professional trading skills in addition to the 13 in Hub V1.
                Total platform: <strong style='color:#E8E0D0;'>31 skills</strong>.
                All powered by live yfinance data and Groq LLaMA 3.3 70B.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── API KEY ───────────────────────────────────────────────────────────
    api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    if not api_key:
        st.error(
            "**GROQ_API_KEY not found.** Add it to your `.env` file:\n\n"
            "```\nGROQ_API_KEY=gsk_...\n```\n\n"
            "Get a free key at [console.groq.com](https://console.groq.com/keys)."
        )
        return
    if not _GROQ_AVAILABLE:
        st.error("**groq not installed.** Run: `pip install groq`")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("AI Model",  "LLaMA 3.3 70B")
    with c2: st.metric("New Skills", "18 in V2")
    with c3: st.metric("Total Platform", "31 Skills")
    with c4: st.metric("Data",      "Live yfinance")

    st.markdown("---")

    # ── 18 SKILL TABS ─────────────────────────────────────────────────────
    tabs = st.tabs([
        "🔬 VCP Screener",
        "🎯 PEAD Screener",
        "🌐 Macro Regime",
        "📡 FTD Detector",
        "🧭 Exposure Coach",
        "🏦 Institutional Flow",
        "🌸 Kanchi SOP",
        "📏 Position Sizer",
        "🗺️ Sector Analyst",
        "🧠 Scenario Analyzer",
        "🧪 Backtest Expert",
        "🔎 FinViz Screener",
        "🔗 Pair Trade",
        "📉 Downtrend Analyzer",
        "📊 Signal Postmortem",
        "🔄 Strategy Pivot",
        "🚨 Kanchi Monitor",
        "📝 Trader Memory",
    ])

    with tabs[0]:  _tab_vcp_screener(api_key)
    with tabs[1]:  _tab_pead_screener(api_key)
    with tabs[2]:  _tab_macro_regime(api_key)
    with tabs[3]:  _tab_ftd_detector(api_key)
    with tabs[4]:  _tab_exposure_coach(api_key)
    with tabs[5]:  _tab_institutional_flow(api_key)
    with tabs[6]:  _tab_kanchi_sop(api_key)
    with tabs[7]:  _tab_position_sizer(api_key)
    with tabs[8]:  _tab_sector_analyst(api_key)
    with tabs[9]:  _tab_scenario_analyzer(api_key)
    with tabs[10]: _tab_backtest_expert(api_key)
    with tabs[11]: _tab_finviz_screener(api_key)
    with tabs[12]: _tab_pair_trade(api_key)
    with tabs[13]: _tab_downtrend_analyzer(api_key)
    with tabs[14]: _tab_signal_postmortem(api_key)
    with tabs[15]: _tab_strategy_pivot(api_key)
    with tabs[16]: _tab_kanchi_monitor(api_key)
    with tabs[17]: _tab_trader_memory(api_key)

    st.markdown("---")
    st.markdown(
        f"""<div style='background:rgba(255,82,82,0.05);border:1px solid rgba(255,82,82,0.16);
                    border-radius:6px;padding:12px 18px;'>
            <p style='color:rgba(255,255,255,0.30);font-size:10px;font-family:monospace;margin:0;line-height:1.8;'>
                ⚠ LEGAL: Hub V2 uses LLaMA 3.3 70B via Groq and live yfinance market data.
                Skills: vcp-screener, pead-screener, macro-regime-detector, ftd-detector,
                exposure-coach, institutional-flow-tracker, kanchi-dividend-sop, position-sizer,
                sector-analyst, scenario-analyzer, backtest-expert, finviz-screener,
                pair-trade-screener, downtrend-duration-analyzer, signal-postmortem,
                strategy-pivot-designer, kanchi-dividend-review-monitor, trader-memory-core.
                NOT financial advice. Verify independently. Trading involves substantial risk.
                {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC.
            </p>
        </div>""",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
