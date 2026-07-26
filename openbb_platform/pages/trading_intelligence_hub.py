# pages/trading_intelligence_hub.py
# Trading Intelligence Hub — All 13 Skills Integrated (100%)
#
# SKILLS INTEGRATED (one tab per skill):
#   1. us-stock-analysis         → Stock Intelligence
#   2. technical-analyst         → Chart Analyst
#   3. market-environment-analysis → Market Environment
#   4. breadth-chart-analyst     → Breadth Dashboard
#   5. market-news-analyst       → News Impact
#   6. market-top-detector       → Top Detector
#   7. options-strategy-advisor  → Options Advisor
#   8. portfolio-manager         → Portfolio Manager
#   9. stanley-druckenmiller-investment → Druckenmiller
#  10. uptrend-analyzer          → Uptrend Analyzer
#  11. us-market-bubble-detector → Bubble Detector
#  12. value-dividend-screener   → Value Screener
#  13. earnings-trade-analyzer   → Earnings Analyzer
#
# UI: TradingView-quality dark theme — plotly_dark, yaxis right,
#     rangeslider=False, hovermode='x unified', scrollZoom=True,
#     spike lines (crosshair). Consistent with existing terminal.
#
# DATA: yfinance (primary) + web_search for macro/news.
# AI:   Groq LLaMA 3.3-70B — streaming, free tier.
# NO st.set_page_config() — called once in app.py.
# <- NEW [trading_hub]: Complete 13-skill integration page.

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

# ── Project root on sys.path ───────────────────────────────────────────────
_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── OpenBB optional (price history fallback) ──────────────────────────────
try:
    from openbb import obb as _obb
    _OBB_AVAILABLE: bool = True
except ImportError:
    _OBB_AVAILABLE = False

# ── Groq ──────────────────────────────────────────────────────────────────
try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE: bool = True
except ImportError:
    _GROQ_AVAILABLE = False

# ── scipy for Black-Scholes ────────────────────────────────────────────────
try:
    from scipy.stats import norm as _norm
    _SCIPY_AVAILABLE: bool = True
except ImportError:
    _SCIPY_AVAILABLE = False

logger = logging.getLogger("TradingHub")

# ─── MODULE CONSTANTS ──────────────────────────────────────────────────────
GROQ_MODEL: str  = "llama-3.3-70b-versatile"
MAX_TOKENS:  int = 4096
CACHE_TTL:   int = 300   # 5 minutes

# Bubble-detector Minsky/Kindleberger thresholds (from skill v2.1)
BUBBLE_VIX_LOW_PCT:    float = 10.0   # Bottom 10th-percentile VIX = bubble signal
BUBBLE_PC_RATIO_LOW:   float = 0.55   # P/C < 0.55 = excessive complacency
BUBBLE_BREADTH_HIGH:   float = 75.0   # >75% above 50DMA = overheated breadth
BUBBLE_MARGIN_YOY_HIGH: float = 25.0  # Margin debt YoY >25% = leverage excess

# Uptrend-analyzer scoring thresholds (from skill doc)
UPTREND_BULL_STRONG:   float = 80.0
UPTREND_BULL:          float = 60.0
UPTREND_NEUTRAL:       float = 40.0
UPTREND_CAUTIOUS:      float = 20.0

# Market-top distribution day window (O'Neil — 25 trading days)
DISTRIBUTION_DAY_WINDOW: int = 25
DISTRIBUTION_VOL_FACTOR: float = 1.02  # volume must exceed prior day by 2%+

# Value/Dividend screener thresholds (from skill doc)
VALUE_PE_MAX:    float = 20.0
VALUE_PB_MAX:    float = 2.0
VALUE_DIV_MIN:   float = 3.0   # percent
VALUE_COMPOSITE_MIN: float = 60.0  # 0-100 composite score

# Earnings-trade scoring weights (from skill doc — 5-factor system)
EARNINGS_WEIGHTS: Dict[str, float] = {
    "gap_size":        0.30,
    "pre_trend":       0.20,
    "volume_ratio":    0.20,
    "ma200_position":  0.15,
    "ma50_position":   0.15,
}

# Options/Black-Scholes
RISK_FREE_RATE_DEFAULT: float = 0.045   # 4.5% approximation — user can override
TRADING_DAYS_YEAR:      int   = 252

# Sector ETFs for breadth/uptrend analysis (GICS standard)
SECTOR_ETFS: Dict[str, str] = {
    "XLK":  "Technology",
    "XLV":  "Healthcare",
    "XLF":  "Financials",
    "XLI":  "Industrials",
    "XLY":  "Consumer Discret.",
    "XLP":  "Consumer Staples",
    "XLE":  "Energy",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Comm. Services",
}

# Macro proxy tickers for market environment
MACRO_TICKERS: Dict[str, str] = {
    "^GSPC":   "S&P 500",
    "^IXIC":   "NASDAQ",
    "^DJI":    "Dow Jones",
    "^VIX":    "VIX",
    "^TNX":    "10Y Treasury",
    "^IRX":    "3M T-Bill",
    "DX-Y.NYB": "DXY",
    "GLD":     "Gold ETF",
    "TLT":     "TLT (20Y Bond)",
    "CL=F":    "Crude Oil",
    "^STOXX50E": "Euro Stoxx 50",
    "^N225":   "Nikkei 225",
}

# Dividend universe for value screener
DIVIDEND_UNIVERSE: List[str] = [
    "JNJ", "PG", "KO", "PEP", "MCD", "MMM", "O", "VZ", "XOM",
    "CVX", "ABT", "ABBV", "MO", "T", "WMT", "HD", "MSFT", "AAPL",
    "JPM", "BRK-B", "V", "NEE", "D", "SO", "DUK", "APD", "EMR",
]

# Leading growth ETFs for market top / distribution day context
GROWTH_ETFS: List[str] = ["ARKK", "IGV", "XBI", "SOXX", "SMH"]

# Druckenmiller conviction component names and weights (from skill doc)
DRUCK_COMPONENTS: Dict[str, float] = {
    "breadth_health":      0.25,
    "uptrend_ratio":       0.20,
    "top_risk_inverse":    0.20,
    "macro_regime":        0.15,
    "momentum":            0.10,
    "leadership_quality":  0.10,
}

# ─── GLOBAL TYPOGRAPHY CSS ─────────────────────────────────────────────────
# Identical to app.py GLOBAL_TYPOGRAPHY_CSS — injected at top of main().
GLOBAL_TYPOGRAPHY_CSS: str = """
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
    font-size:16px !important; color:#E8E0D0 !important;
    line-height:1.75 !important;
}
p,span,li,td,th,label,div {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important;
    line-height:1.75 !important;
}
h1,h2,h3,h4,h5,h6,
.stMarkdown h1,.stMarkdown h2,.stMarkdown h3,.stMarkdown h4 {
    font-family:'Times New Roman',Times,serif !important;
    font-size:22px !important; font-weight:bold !important;
    color:#F5ECD7 !important; line-height:1.4 !important;
    margin-bottom:0.5em !important;
}
[data-testid="stAppViewContainer"] h1 {
    font-size:28px !important; color:#F5ECD7 !important;
    font-family:'Times New Roman',Times,serif !important;
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
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; background-color:#0d2233 !important;
    color:#E8E0D0 !important; border:1px solid rgba(0,229,255,0.25) !important;
}
[data-testid="stButton"] button[kind="primary"] {
    background-color:rgba(0,229,255,0.15) !important;
    color:#00E5FF !important; border:1px solid rgba(0,229,255,0.45) !important;
}
[data-testid="stTabs"] button,.stTabs [role="tab"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
    background-color:transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color:#00E5FF !important; border-bottom-color:#00E5FF !important;
}
[data-testid="stAlert"],.stAlert,.stInfo,.stSuccess,.stWarning,.stError {
    background-color:#0d1f33 !important; border-radius:6px !important;
}
[data-testid="stAlert"] p,.stAlert p,.stInfo p,
.stSuccess p,.stWarning p,.stError p {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; line-height:1.75 !important; color:#E8E0D0 !important;
}
[data-testid="stExpander"] {
    background-color:#080f1a !important;
    border:1px solid rgba(0,229,255,0.10) !important; border-radius:6px !important;
}
[data-testid="stExpander"] summary {
    color:#C8C0B0 !important; font-family:'Times New Roman',Times,serif !important;
}
[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label,
[data-testid="stSlider"] label,[data-testid="stCheckbox"] label,
[data-testid="stMultiSelect"] label {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
[data-testid="stTextInput"] input,[data-testid="stSelectbox"] div,
[data-testid="stNumberInput"] input,textarea {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
    border-color:rgba(0,229,255,0.20) !important;
    font-family:'Times New Roman',Times,serif !important;
}
code,pre,.monospace {
    font-family:'Courier New',Courier,monospace !important;
    font-size:13px !important; background-color:#080f1a !important;
    color:#A8E0C8 !important;
}
strong,b { font-family:'Times New Roman',Times,serif !important; color:#F5ECD7 !important; }
em,i     { font-family:'Times New Roman',Times,serif !important; color:#D4C9B8 !important; }
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

# ─── SYSTEM PROMPTS — ALL 13 SKILLS ────────────────────────────────────────

SYS_STOCK_INTELLIGENCE: str = """You are a senior equity analyst combining CFA, CMT, and FRM designations with 20+ years at top-tier institutions. You perform comprehensive US stock analysis integrating fundamental analysis (financial metrics, business quality, valuation), technical analysis (indicators, chart patterns, support/resistance), and investment report generation.
TASK: Deliver a complete, institutional-quality stock analysis report.
MANDATORY OUTPUT STRUCTURE (adapt based on analysis type selected):
1. EXECUTIVE SUMMARY: Company overview, current price, market cap, key finding
2. FUNDAMENTAL ANALYSIS: Revenue trends, margins, EPS growth, FCF, D/E ratio, ROE, P/E vs peers
3. TECHNICAL ANALYSIS: Trend direction, EMA/SMA alignment, RSI, MACD, key support/resistance levels
4. VALUATION: P/E, PEG, EV/EBITDA vs sector averages; DCF fair value estimate if data permits
5. INVESTMENT THESIS: Bull case, bear case with specific price targets derived from data
6. RISK FACTORS: Company-specific and macro risks with probability assessment
7. RECOMMENDATION: Buy/Hold/Sell with target price, stop-loss, conviction level 1-5
RULES: ALL metrics from live data provided. Flag N/A data explicitly. No invented numbers."""

SYS_CHART_ANALYST: str = """You are a CMT-certified technical analyst specializing in weekly and daily price chart analysis using pure price action and indicators. Your analysis is exclusively chart-based — no fundamentals, no news.
TASK: Deliver a comprehensive probabilistic technical analysis report.
MANDATORY OUTPUT STRUCTURE:
CHART OVERVIEW: Ticker, timeframe, current price, date
1. TREND ANALYSIS: Direction (up/down/sideways), strength (strong/moderate/weak), duration, HH/HL or LH/LL pattern
2. SUPPORT & RESISTANCE: Minimum 3 key levels each with specific price and basis
3. MOVING AVERAGE ANALYSIS: Price vs 20/50/200 MA; alignment classification; dynamic S/R
4. VOLUME ANALYSIS: Trend, spikes context, confirmation/divergence with price
5. CHART PATTERNS & PRICE ACTION: Reversal/continuation patterns identified, significance
6. CURRENT ASSESSMENT: Single-paragraph synthesis of all elements
7. SCENARIO ANALYSIS (2-4 scenarios, probabilities must sum to 100%):
   - Name | Probability % | Description | Triggers | Target | Invalidation
8. SUMMARY: Key levels to watch, recommended bias
CRITICAL: All price levels must come from the live technical data provided. Never invent levels."""

SYS_MARKET_ENVIRONMENT: str = """You are a senior macro strategist and global markets analyst with expertise spanning equities, fixed income, FX, commodities, and inter-market analysis. You produce institutional-quality market environment briefings.
TASK: Deliver a comprehensive global market environment assessment.
MANDATORY OUTPUT STRUCTURE:
REGIME DASHBOARD (lead with this box):
┌────────────────────────────────────────────────────┐
│ EQUITY:    [Bull/Bear/Transitional]                │
│ RATE REGIME: [Rising/Falling/Stable]               │
│ RISK MODE: [Risk-On/Risk-Off/Mixed]                │
│ VIX STATE: [Low/Normal/Elevated/Extreme]           │
│ USD TREND: [Strong/Weak/Neutral]                   │
│ OVERALL:   [RISK-ON / RISK-OFF / MIXED]            │
└────────────────────────────────────────────────────┘
THEN:
1. US MARKETS: S&P 500, NASDAQ, Dow — trend, momentum, key levels
2. GLOBAL MARKETS: Europe, Asia — relative strength
3. FOREX & COMMODITIES: DXY trend, Gold, Crude, Bonds
4. SECTOR ROTATION: Top 2 and bottom 2 performing sectors with rationale
5. INTEREST RATE ANALYSIS: Yield curve shape, Fed implications
6. RISK ASSESSMENT: Top 3 risk factors with probability and impact
7. STRATEGY IMPLICATIONS: 3 specific portfolio adjustments for current regime
DERIVE ALL CALLS FROM LIVE DATA PROVIDED. State confidence levels explicitly."""

SYS_BREADTH_DASHBOARD: str = """You are a quantitative market breadth analyst specializing in the S&P 500 Breadth Index (200-Day MA based) and the US Stock Market Uptrend Stock Ratio, applying backtested systematic strategies as documented in the TraderMonty framework.
TASK: Deliver a complete market breadth health assessment.
MANDATORY OUTPUT STRUCTURE:
BREADTH HEALTH SCORE: [0-100] — [Strong Bull / Bull / Neutral / Cautious / Bear]
1. OVERALL BREADTH: % of S&P 500 stocks above 200MA and 50MA — trend and level
2. SECTOR PARTICIPATION: Breadth by sector — identify strongest and weakest
3. STRATEGIC SIGNAL (200MA Breadth Index strategy):
   - Current position vs 73% (overheated) and 23% (oversold) thresholds
   - 8-day MA trend — reversal signal status
   - BUY/SELL/HOLD signal per backtested system
4. TACTICAL SIGNAL (Uptrend Ratio):
   - % of stocks in defined uptrend (above 200MA + 50MA + 20MA + positive 1M)
   - Green/Red regime classification
   - Swing trade bias
5. CYCLICAL vs DEFENSIVE ROTATION: Which is leading and what it implies
6. COMPOSITE ASSESSMENT: Strategic + tactical combined positioning recommendation
Derive ALL readings from the live sector ETF and breadth data provided."""

SYS_MARKET_NEWS: str = """You are a senior market impact analyst at a tier-1 institutional research desk with expertise in event-driven analysis, macro news interpretation, and portfolio impact assessment. You analyze recent market-moving news through the lens of portfolio positioning.
TASK: Deliver a high-impact market news analysis brief.
MANDATORY OUTPUT STRUCTURE:
NEWS IMPACT DASHBOARD: Overall market impact [Bullish/Bearish/Neutral/Mixed]
1. TOP NEWS EVENTS: List recent significant events (last 10 days) with:
   - Event description (1-2 sentences)
   - Affected assets/sectors
   - Market impact assessment [High/Medium/Low]
   - Direction [Bullish/Bearish/Neutral]
2. MONETARY POLICY: FOMC, ECB, BOJ developments and rate implications
3. MACRO DATA IMPACT: Employment, inflation, GDP — actual vs expectations
4. CORPORATE EVENTS: Key earnings, M&A, guidance changes
5. GEOPOLITICAL & TRADE: Risk events affecting specific sectors
6. SECTOR IMPACT MAP: For each major sector — News Tailwind / Headwind / Neutral
7. KEY RISKS: 3 upcoming events that could materially move markets
8. PORTFOLIO POSITIONING GUIDANCE: 3 specific adjustments given news flow
Focus on actionable intelligence. Flag any data that is estimated vs confirmed."""

SYS_MARKET_TOP: str = """You are a quantitative analyst specializing in market top detection using the O'Neil Distribution Day methodology, Minervini leading stock deterioration patterns, and Monty defensive sector rotation signals — exactly as described in the IBD/Investors.com framework.
TASK: Deliver a market top probability assessment.
MANDATORY OUTPUT STRUCTURE:
TOP DETECTOR SCORE: [0-100] — Risk Zone: [Normal/Early Warning/Elevated/High/Critical]
COMPONENT BREAKDOWN (25%/20%/15%/15%/15%/10% weights):
1. DISTRIBUTION DAY COUNT [25%]: Days in last 25 sessions with decline on higher volume than prior day. Score: [0-100]. Count: [N] days. Threshold: 5+ days = elevated risk.
2. LEADING STOCK HEALTH [20%]: Growth ETF performance (ARKK, IGV, XBI, SOXX). Deterioration vs index. Score: [0-100].
3. DEFENSIVE ROTATION [15%]: XLU/XLP/XLV vs XLK/XLY/XLC relative performance. Score: [0-100].
4. BREADTH DIVERGENCE [15%]: % above 200MA and 50MA — are breadth readings diverging from index levels? Score: [0-100].
5. INDEX TECHNICAL CONDITION [15%]: MA structure, failed rally attempts, lower highs. Score: [0-100].
6. SENTIMENT & SPECULATION [10%]: VIX level, Put/Call ratio context. Score: [0-100].
COMPOSITE SCORE & ACTION: State specific exposure reduction recommendation.
DERIVE ALL SCORES FROM LIVE DATA. Never fabricate distribution day counts."""

SYS_OPTIONS_ADVISOR: str = """You are a senior options strategist with CFA and CMT certifications and 15+ years at an options market-making desk. You analyze options strategies using Black-Scholes theoretical pricing, Greeks analysis, and risk management principles.
TASK: Deliver a complete options strategy analysis.
MANDATORY OUTPUT STRUCTURE:
OPTION PRICING SUMMARY:
- Underlying: [price], Strike: [K], Expiry: [days], IV: [%], Type: [C/P]
- Theoretical Price (Black-Scholes): $[X]
- Greeks: Delta=[Δ], Gamma=[Γ], Theta=[Θ/day], Vega=[V per 1%IV]
STRATEGY ANALYSIS: [Strategy Name]
- Max Profit: $[X] | Max Loss: $[X] | Breakeven: $[X]
- P&L at expiry: [key price levels with P&L]
RISK ASSESSMENT:
- Risk/Reward Ratio: [N:1]
- Probability of Profit (theoretical): [%]
- Key risk: [primary concern]
STRATEGY RECOMMENDATION: Given [context], consider [specific strategy]. Rationale: [data-driven]. Entry: [conditions]. Exit: [stop/target].
EARNINGS CONTEXT (if near earnings): [IV crush risk, expected move, strategy adjustment]
USE ONLY PROVIDED BLACK-SCHOLES CALCULATIONS. Flag when user inputs are outside normal ranges."""

SYS_PORTFOLIO_MANAGER: str = """You are a senior portfolio manager at a tier-1 asset management firm holding CFA, FRM, and CAIA designations. You perform comprehensive portfolio risk analysis using modern portfolio theory and institutional risk management frameworks.
TASK: Deliver a complete portfolio risk and optimization report.
MANDATORY OUTPUT STRUCTURE:
PORTFOLIO RISK DASHBOARD: [high-level summary of top 3 risk concerns]
1. ASSET ALLOCATION ANALYSIS: Current weights vs strategic targets; concentration flags (>25% single position = warning)
2. CORRELATION ANALYSIS: Matrix interpretation — pairs >0.70 = risk cluster; diversification score
3. VOLATILITY PROFILE: Position-level annualized vol; weighted portfolio vol estimate; VaR (95%) estimate
4. SECTOR CONCENTRATION: % per sector; flag any sector >30%
5. BETA & MARKET SENSITIVITY: Portfolio beta; interest rate sensitivity classification per holding
6. STRESS TEST: Estimated portfolio drawdown in 30% market decline using betas
7. LIQUIDITY ASSESSMENT: Rate each holding [1=daily liquid, 5=illiquid]
8. REBALANCING RECOMMENDATIONS: Specific weight adjustments with rationale
9. HEDGING IDEAS: 2-3 specific hedge instruments with sizing rationale
10. RISK-ADJUSTED METRICS: Portfolio Sharpe estimate; max drawdown context
ALL METRICS DERIVED FROM PROVIDED LIVE DATA. Be explicit about estimation assumptions."""

SYS_DRUCKENMILLER: str = """You are a quantitative meta-analyst applying Stanley Druckenmiller's investment framework — synthesizing breadth, uptrend, top-risk, macro regime, and momentum signals into a single conviction score with actionable allocation guidance. Druckenmiller's core principle: 'Be aggressive when conviction is high; capital preservation when uncertain.'
TASK: Synthesize all market signals into a Druckenmiller-style conviction score and allocation recommendation.
MANDATORY OUTPUT STRUCTURE:
CONVICTION SCORE: [0-100] — Pattern: [Policy Pivot / Distortion Play / Contrarian Reversal / Wait & See]
COMPONENT SCORES (weights: Breadth 25%, Uptrend 20%, Top Risk Inverse 20%, Macro 15%, Momentum 10%, Leadership 10%):
[Component Name]: [raw score] → weighted contribution: [N pts]
PATTERN CLASSIFICATION:
- Policy Pivot (70-100): Aggressive long positioning — 100% equity exposure
- Distortion Play (55-70): Selective long — 70-80% equity exposure
- Contrarian Reversal (40-55): Defensive with opportunistic entries — 50-60%
- Wait & See (<40): Capital preservation — <40% equity exposure
ALLOCATION RECOMMENDATION: Specific equity/bond/cash/alternative split
HIGHEST CONVICTION TRADE: Single best current opportunity with entry, target, stop
RISK MANAGEMENT: Maximum position size for current conviction level; stop-loss framework
DERIVE ALL SCORES FROM THE LIVE SIGNAL DATA PROVIDED. This is the final synthesis layer."""

SYS_UPTREND_ANALYZER: str = """You are a market breadth specialist applying Monty's Uptrend Ratio methodology — tracking the percentage of ~2,800 US stocks in defined uptrends across all 11 GICS sectors, generating a composite health score (0-100) with sector heatmap and exposure guidance.
TASK: Deliver a complete uptrend ratio breadth analysis.
MANDATORY OUTPUT STRUCTURE:
UPTREND HEALTH SCORE: [0-100] — Zone: [Strong Bull/Bull/Neutral/Cautious/Bear]
EXPOSURE GUIDANCE: [Full 100% / Normal 80-100% / Reduced 60-80% / Defensive 30-60% / Preservation 0-30%]
COMPONENT SCORES (Breadth 30%, Sector Participation 25%, Rotation 15%, Momentum 20%, Historical 10%):
[each component with score and brief rationale]
SECTOR HEATMAP: [11 sectors ranked strongest to weakest with uptrend ratio estimate]
ACTIVE WARNINGS (if any):
- Late Cycle: [YES/NO] — Commodity avg > both Cyclical and Defensive
- High Spread: [YES/NO] — Max-min sector spread > 40pp
- Divergence: [YES/NO] — Intra-group std > 8pp
MOMENTUM SIGNAL: EMA(3)-smoothed slope direction — [Accelerating/Decelerating/Flat]
TACTICAL GUIDANCE: 1-3 specific actions for current breadth environment
ALL READINGS COMPUTED FROM LIVE SECTOR ETF DATA PROVIDED."""

SYS_BUBBLE_DETECTOR: str = """You are a macro risk analyst applying the revised Minsky/Kindleberger bubble detection framework v2.1. You evaluate US market bubble risk through mandatory quantitative data collection before any qualitative assessment. Strict confirmation bias prevention rules apply.
TASK: Deliver a quantitative bubble risk assessment.
MANDATORY OUTPUT STRUCTURE:
BUBBLE RISK SCORE: [0-15 pts] — Phase: [Normal/Watch/Warning/Elevated/Critical]
PHASE THRESHOLDS: Normal 0-3 | Watch 4-5 | Warning 6-7 | Elevated 8-9 | Critical 10-15
QUANTITATIVE INDICATORS (Phase 1 — mandatory, no qualitative yet):
1. Put/Call Ratio: [value] → [0/1/2 pts] — Threshold: <0.55 = 2pts, 0.55-0.65 = 1pt
2. VIX Level & Percentile: [value] → [0/1/2 pts] — Bottom 10th pct = 2pts
3. Market Breadth (50DMA %): [value] → [0/1 pts] — >75% = 1pt overheated
4. Volatility Regime: [21-day realized vol] → [0/1 pts] — Extreme compression = 1pt
5. Margin Debt YoY: [value] → [0/1/2 pts] — >25% YoY = 2pts, 10-25% = 1pt
QUALITATIVE ADJUSTMENT (Phase 2 — max +3 pts, requires measurable evidence):
[Social phenomena, narrative intensity, IPO volume — score only with specific evidence]
COMPOSITE SCORE & RISK MANAGEMENT: Position sizing guidance, specific hedge instruments
CRITICAL: Do NOT score qualitative without concrete evidence. Prevent over-scoring."""

SYS_VALUE_SCREENER: str = """You are a value and income equity analyst applying the quality-value-dividend framework: P/E < 20, P/B < 2, Dividend Yield ≥ 3%, consistent dividend and revenue growth over 3 years. You rank stocks by composite quality scores and generate actionable income portfolio recommendations.
TASK: Screen and rank the provided universe for value/dividend quality.
MANDATORY OUTPUT STRUCTURE:
SCREENING CRITERIA APPLIED: P/E < 20, P/B < 2, Yield ≥ 3%, Growth positive
TOP 10 RANKED STOCKS (by composite quality score 0-100):
For each stock provide:
| Rank | Ticker | Name | P/E | P/B | Yield | 5Y Div Growth | Payout Ratio | FCF Yield | Score |
QUALITY SCORE METHODOLOGY:
- Valuation (30%): P/E below sector avg, P/B below 2 = full score
- Dividend Quality (40%): Yield, growth consistency, payout sustainability
- Financial Health (30%): FCF coverage, D/E, margin stability
INCOME PROJECTIONS: For $100,000 portfolio, Year 1/3/5 income at base case
DIVIDEND SAFETY FLAGS: ⚠️ payout ratio >75%, ⚠️ declining FCF, ⚠️ D/E >2.0
SECTOR DIVERSIFICATION: Ensure no sector >30% of portfolio
DRIP COMPOUNDING: 10-year projection at conservative/base/optimistic growth
ALL YIELDS AND RATIOS FROM LIVE DATA. Clearly mark where data is unavailable."""

SYS_EARNINGS_ANALYZER: str = """You are a quantitative earnings momentum analyst applying the 5-Factor Post-Earnings Scoring System: Gap Size (30%), Pre-Earnings Trend (20%), Volume Ratio (20%), MA200 Position (15%), MA50 Position (15%). You identify the strongest post-earnings setups for momentum accumulation trades (PEAD — Post-Earnings Announcement Drift).
TASK: Score and grade recent post-earnings stocks.
MANDATORY OUTPUT STRUCTURE:
SCREENING SUMMARY: N stocks analyzed, A/B/C/D grade distribution
GRADE A SETUPS (Score ≥ 85) — High-conviction entries:
For each: Ticker | Grade | Score | Gap% | Pre-Trend | Vol Ratio | vs MA200 | vs MA50 | Entry Notes
GRADE B SETUPS (Score 70-84) — Watch and confirm:
[same format as Grade A]
GRADE C/D OVERVIEW: Brief table — Monitor or Avoid
5-FACTOR SCORE DETAIL for top 5 stocks:
Factor | Weight | Raw Score | Weighted | Notes
ENTRY GUIDANCE BY GRADE:
- Grade A (85+): Strong PEAD candidate — entry near close or first-day pullback
- Grade B (70-84): Confirm with volume on day 2-3 before entry
- Grade C/D: Insufficient technical setup — avoid
KEY RISK: Earnings gap fades when broader market deteriorates — assess Grade A in context of Top Detector score
ALL SCORES CALCULATED FROM LIVE EARNINGS AND PRICE DATA PROVIDED."""

# ─── PLOTLY CONFIG — TRADINGVIEW-QUALITY ───────────────────────────────────
TV_CONFIG: Dict[str, Any] = {
    "scrollZoom":      True,
    "displayModeBar":  True,
    "displaylogo":     False,
    "doubleClick":     "reset+autosize",
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

def _tv_xaxis(**kwargs: Any) -> Dict[str, Any]:
    """Returns TradingView-quality x-axis config. Spike lines = crosshair."""
    base: Dict[str, Any] = {
        "rangeslider_visible": False,
        "type":                "date",
        "gridcolor":           "rgba(128,128,128,0.06)",
        "showgrid":            True,
        "zeroline":            False,
        "showspikes":          True,
        "spikecolor":          "rgba(200,200,200,0.55)",
        "spikethickness":      1,
        "spikedash":           "dot",
        "spikemode":           "across",
        "tickfont":            {"color": "#8a8a8a", "size": 10},
    }
    base.update(kwargs)
    return base

def _tv_yaxis(**kwargs: Any) -> Dict[str, Any]:
    """Returns TradingView-quality y-axis config. Side=right always."""
    base: Dict[str, Any] = {
        "side":           "right",
        "gridcolor":      "rgba(128,128,128,0.06)",
        "showgrid":       True,
        "zeroline":       False,
        "fixedrange":     False,
        "showspikes":     True,
        "spikecolor":     "rgba(200,200,200,0.55)",
        "spikethickness": 1,
        "spikedash":      "dot",
        "spikemode":      "across",
        "tickfont":       {"color": "#8a8a8a", "size": 10},
    }
    base.update(kwargs)
    return base

def _tv_layout(height: int = 480, title: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Returns base TradingView-quality layout."""
    layout: Dict[str, Any] = {
        "template":      "plotly_dark",
        "height":        height,
        "hovermode":     "x unified",
        "dragmode":      "zoom",
        "margin":        {"l": 10, "r": 100, "t": 50, "b": 10},
        "paper_bgcolor": "#000d1a",
        "plot_bgcolor":  "#000d1a",
        "hoverdistance": 25,
        "spikedistance": -1,
        "showlegend":    True,
        "legend": {
            "bgcolor":      "rgba(14,17,23,0.85)",
            "bordercolor":  "rgba(128,128,128,0.30)",
            "borderwidth":  1,
            "font":         {"color": "#e0e0e0", "size": 9},
            "orientation":  "h",
            "yanchor":      "bottom",
            "y":            1.01,
            "xanchor":      "left",
            "x":            0,
        },
    }
    if title:
        layout["title"] = {
            "text": title,
            "font": {"color": "#00E5FF", "size": 13, "family": "monospace"},
        }
    layout.update(kwargs)
    return layout

# ─── DATA FETCH UTILITIES ──────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL)
def _fetch_info(ticker: str) -> Dict[str, Any]:
    """Fetches comprehensive stock fundamentals via yfinance."""
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
            "ps_ratio":         info.get("priceToSalesTrailing12Months"),
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
            "target_high_price": info.get("targetHighPrice"),
            "target_low_price":  info.get("targetLowPrice"),
            "analyst_count":    info.get("numberOfAnalystOpinions"),
            "description":      (info.get("longBusinessSummary") or "")[:500],
        }
    except Exception as e:
        logger.error(f"_fetch_info [{ticker}]: {e}")
        return {}

@st.cache_data(ttl=CACHE_TTL)
def _fetch_history(ticker: str, years: int = 2) -> pd.DataFrame:
    """Fetches OHLCV price history via yfinance (OpenBB as fallback)."""
    start_str = (
        datetime.date.today() - datetime.timedelta(days=365 * years)
    ).strftime("%Y-%m-%d")
    if _OBB_AVAILABLE:
        try:
            res = _obb.equity.price.historical(
                ticker, start_date=start_str, provider="yfinance"
            )
            df = res.to_df()
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
def _fetch_macro() -> Dict[str, Any]:
    """Fetches current macro indicator values via yfinance."""
    result: Dict[str, Any] = {}
    for tkr, name in MACRO_TICKERS.items():
        try:
            t    = yf.Ticker(tkr)
            hist = t.history(period="1y")
            if hist.empty:
                continue
            cur    = float(hist["Close"].iloc[-1])
            yr_ago = float(hist["Close"].iloc[0])
            chg    = ((cur / yr_ago) - 1.0) * 100.0 if yr_ago > 1e-10 else 0.0
            result[tkr] = {
                "name":      name,
                "current":   cur,
                "1y_ago":    yr_ago,
                "1y_change": chg,
                "52w_high":  float(hist["High"].max()),
                "52w_low":   float(hist["Low"].min()),
            }
        except Exception:
            pass
    return result

@st.cache_data(ttl=CACHE_TTL)
def _fetch_sector_breadth() -> Dict[str, Any]:
    """
    Fetches sector ETF data and computes breadth metrics.
    Returns per-sector: current price, 1-month return, vs MA200, vs MA50.
    """
    result: Dict[str, Any] = {}
    for etf, sector_name in SECTOR_ETFS.items():
        try:
            t  = yf.Ticker(etf)
            df = t.history(period="1y", auto_adjust=True)
            if df.empty or len(df) < 50:
                continue
            cur    = float(df["Close"].iloc[-1])
            ma50   = float(df["Close"].rolling(50).mean().iloc[-1])
            ma200  = float(df["Close"].rolling(200).mean().iloc[-1]) if len(df) >= 200 else float("nan")
            m1_ago = float(df["Close"].iloc[-21]) if len(df) >= 21 else cur
            m1_ret = (cur / m1_ago - 1.0) * 100.0 if m1_ago > 1e-10 else 0.0
            m3_ago = float(df["Close"].iloc[-63]) if len(df) >= 63 else cur
            m3_ret = (cur / m3_ago - 1.0) * 100.0 if m3_ago > 1e-10 else 0.0
            above_ma50  = cur > ma50
            above_ma200 = cur > ma200 if not math.isnan(ma200) else False
            result[etf] = {
                "sector":       sector_name,
                "price":        cur,
                "ma50":         ma50,
                "ma200":        ma200,
                "1m_return":    m1_ret,
                "3m_return":    m3_ret,
                "above_ma50":   above_ma50,
                "above_ma200":  above_ma200,
            }
        except Exception as e:
            logger.debug(f"Sector breadth [{etf}]: {e}")
    return result

@st.cache_data(ttl=CACHE_TTL)
def _fetch_earnings_history(ticker: str) -> Dict[str, Any]:
    """Fetches quarterly earnings and income statement data."""
    result: Dict[str, Any] = {}
    try:
        t = yf.Ticker(ticker)
        for key, attr in [
            ("quarterly_earnings",  "quarterly_earnings"),
            ("quarterly_income",    "quarterly_financials"),
        ]:
            try:
                df = getattr(t, attr, None)
                if df is not None and not df.empty:
                    result[key] = df
            except Exception:
                pass
    except Exception as e:
        logger.error(f"_fetch_earnings_history [{ticker}]: {e}")
    return result

# ─── NUMERIC FORMATTING UTILITIES ──────────────────────────────────────────
def _flt(v: Any, fmt: str = ".2f", suffix: str = "") -> str:
    """Safely formats a numeric value."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v):{fmt}}{suffix}"
    except (TypeError, ValueError):
        return "N/A"

def _pct(v: Any) -> str:
    """Formats a decimal fraction as a percentage string."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100.0:.1f}%"
    except (TypeError, ValueError):
        return "N/A"

def _bn(v: Any) -> str:
    """Formats a large number as $T/$B/$M string."""
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

# ─── GROQ STREAMING UTILITY ────────────────────────────────────────────────
def _stream(
    api_key:       str,
    system_prompt: str,
    user_content:  str,
    placeholder:   st.delta_generator.DeltaGenerator,
    max_tokens:    int = MAX_TOKENS,
) -> str:
    """Streams a Groq analysis response into an st.empty() placeholder."""
    if not _GROQ_AVAILABLE:
        raise RuntimeError("groq package not installed. Run: pip install groq")
    client = _Groq(api_key=api_key)
    full: str = ""
    try:
        stream = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            stream=True,
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
            raise RuntimeError("Invalid GROQ_API_KEY. Check .env and restart.")
        if "429" in err or "rate" in err.lower():
            raise RuntimeError("Groq rate limit. Wait 60 seconds and retry.")
        raise RuntimeError(f"Groq API error: {e}")

# ─── SHARED HEADER RENDERER ────────────────────────────────────────────────
def _tab_header(skill_name: str, color: str, title: str, description: str) -> None:
    """Renders the standard skill card header for each tab."""
    st.markdown(
        f"""
        <div style='background:linear-gradient(135deg,rgba(0,10,26,0.97) 0%,#000d1a 100%);
                    border-left:5px solid {color};border-radius:8px;
                    padding:20px 26px;margin-bottom:20px;'>
            <p style='color:{color};font-family:monospace;font-size:10px;
                      letter-spacing:2px;margin:0 0 8px 0;'>
                ◆ SKILL: {skill_name.upper()} · LIVE DATA · {GROQ_MODEL.upper()}
            </p>
            <h3 style='color:#F5ECD7;font-family:"Times New Roman",serif;
                       font-size:20px;margin:0 0 8px 0;'>
                {title}
            </h3>
            <p style='color:#8898A8;font-size:13px;margin:0;
                      font-family:"Times New Roman",serif;line-height:1.7;'>
                {description}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _analysis_footer(skill_name: str) -> None:
    """Renders the standard analysis disclaimer footer."""
    st.markdown(
        f"""
        <div style='background:rgba(255,82,82,0.06);border:1px solid rgba(255,82,82,0.18);
                    border-radius:4px;padding:10px 16px;margin-top:16px;'>
            <p style='color:rgba(255,255,255,0.38);font-size:10px;
                      font-family:monospace;margin:0;'>
                ⚠ Analysis generated by {GROQ_MODEL} via skill [{skill_name}] using live
                yfinance market data as of {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} UTC.
                Not financial advice. Verify all figures before acting.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ─── PRICE CHART (SHARED) ──────────────────────────────────────────────────
def _price_chart(
    df: pd.DataFrame,
    ticker: str,
    title: str = "",
    indicators: Optional[Dict[str, pd.Series]] = None,
    height: int = 480,
) -> go.Figure:
    """
    Renders a TradingView-quality candlestick chart with optional indicator overlays.
    All overlays: EMA9 (cyan), EMA21 (lime), EMA55 (gold), BB (blue dashed).
    """
    fig = go.Figure()
    # Candlestick base
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        increasing_line_color="#089981", increasing_fillcolor="#089981",
        decreasing_line_color="#F23645", decreasing_fillcolor="#F23645",
        name=ticker, showlegend=False,
    ))
    if indicators:
        color_map = {
            "ema_9":  ("#00E5FF", 1.8),
            "ema_21": ("#00FF88", 1.5),
            "ema_55": ("#FFD700", 1.4),
            "sma_200":("rgba(255,215,0,0.45)", 1.2),
            "bb_upper": ("#6495ED", 0.9),
            "bb_lower": ("#6495ED", 0.9),
        }
        for key, series in indicators.items():
            if key.startswith("bb_"):
                color, width = color_map.get(key, ("#ffffff", 1.0))
                fig.add_trace(go.Scatter(
                    x=df.index, y=series,
                    mode="lines",
                    line=dict(color=color, width=width, dash="dot"),
                    name=key.upper(), showlegend=True, opacity=0.7,
                ))
            elif key in color_map:
                color, width = color_map[key]
                fig.add_trace(go.Scatter(
                    x=df.index, y=series,
                    mode="lines",
                    line=dict(color=color, width=width),
                    name=key.upper(), showlegend=True,
                ))
    layout = _tv_layout(height=height, title=title or f"{ticker} Price Chart")
    layout["xaxis"] = _tv_xaxis()
    layout["yaxis"] = _tv_yaxis()
    fig.update_layout(**layout)
    return fig

def _compute_indicators(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Computes EMA9/21/55, SMA200, RSI21, MACD, BB20, EWO5/35 from OHLCV."""
    close = df["close"]
    ind: Dict[str, pd.Series] = {}
    ind["ema_9"]  = close.ewm(span=9,   adjust=False).mean()
    ind["ema_21"] = close.ewm(span=21,  adjust=False).mean()
    ind["ema_55"] = close.ewm(span=55,  adjust=False).mean()
    ind["sma_200"] = close.rolling(200).mean()
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std(ddof=0)
    ind["bb_mid"]   = bb_mid
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
    ind["ewo"] = close.rolling(5).mean() - close.rolling(35).mean()
    return ind

# ─── BLACK-SCHOLES IMPLEMENTATION (options-strategy-advisor skill) ─────────
def _bs_price(
    S: float,   # underlying price
    K: float,   # strike
    T: float,   # time to expiry in years
    r: float,   # risk-free rate (decimal)
    sigma: float, # volatility (decimal)
    option_type: str = "call",
) -> Tuple[float, Dict[str, float]]:
    """
    Computes Black-Scholes theoretical option price and Greeks.
    Float safety: all division guarded; sigma > 1e-10 required.
    Returns (price, {delta, gamma, theta, vega, rho}).
    """
    if not _SCIPY_AVAILABLE:
        raise RuntimeError("scipy not installed. Run: pip install scipy")
    if sigma < 1e-10:
        raise ValueError("sigma must be > 0")
    if T < 1e-10:
        raise ValueError("T (time to expiry) must be > 0")
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if option_type.lower() == "call":
        price = S * _norm.cdf(d1) - K * math.exp(-r * T) * _norm.cdf(d2)
        delta = float(_norm.cdf(d1))
        rho   = K * T * math.exp(-r * T) * _norm.cdf(d2) / 100.0
    else:
        price = K * math.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1)
        delta = float(_norm.cdf(d1) - 1.0)
        rho   = -K * T * math.exp(-r * T) * _norm.cdf(-d2) / 100.0
    gamma = float(_norm.pdf(d1)) / (S * sigma * sqrt_T)
    theta = (
        -(S * _norm.pdf(d1) * sigma) / (2.0 * sqrt_T)
        - r * K * math.exp(-r * T) * (
            _norm.cdf(d2) if option_type.lower() == "call" else _norm.cdf(-d2)
        )
    ) / 365.0
    vega = S * _norm.pdf(d1) * sqrt_T / 100.0
    return price, {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": rho}

def _options_pnl_chart(
    S: float, K: float, premium: float, option_type: str, contract_size: int = 100
) -> go.Figure:
    """Renders an option P&L at expiry chart."""
    price_range = np.linspace(S * 0.70, S * 1.30, 200)
    if option_type.lower() == "call":
        payoffs = np.maximum(price_range - K, 0.0) - premium
    else:
        payoffs = np.maximum(K - price_range, 0.0) - premium
    payoffs_usd = payoffs * contract_size
    colors = ["#00E676" if p >= 0.0 else "#FF5252" for p in payoffs_usd]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=price_range, y=payoffs_usd,
        mode="lines",
        line=dict(color="#00E5FF", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(0,229,255,0.08)",
        name=f"{option_type.upper()} P&L at Expiry",
    ))
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.25)", line_width=1, line_dash="dot")
    fig.add_vline(x=S, line_color="#FFD700", line_width=1.5, line_dash="dash")
    fig.add_annotation(x=S, y=1.0, yref="paper", text="Current Price",
                       showarrow=False, font=dict(color="#FFD700", size=10))
    layout = _tv_layout(height=340, title=f"{option_type.upper()} P&L at Expiry")
    layout["xaxis"] = {"title": "Underlying Price at Expiry", "gridcolor": "rgba(128,128,128,0.06)"}
    layout["yaxis"] = _tv_yaxis(title_text="P&L ($)")
    layout["yaxis"]["title"] = {"text": "P&L ($)", "font": {"color": "#8a8a8a", "size": 9}}
    layout["margin"] = {"l": 10, "r": 80, "t": 50, "b": 40}
    fig.update_layout(**layout)
    return fig

# ─── DISTRIBUTION DAY COMPUTATION (market-top-detector skill) ─────────────
def _compute_distribution_days(df: pd.DataFrame) -> int:
    """
    Counts O'Neil Distribution Days in the last DISTRIBUTION_DAY_WINDOW sessions.
    A distribution day is a session where:
      - The index closes DOWN on the day, AND
      - Volume is higher than the prior session.
    Returns: count of distribution days.
    """
    if df.empty or "close" not in df.columns or "volume" not in df.columns:
        return 0
    recent = df.tail(DISTRIBUTION_DAY_WINDOW + 1).copy()
    if len(recent) < 2:
        return 0
    count = 0
    for i in range(1, len(recent)):
        close_today = float(recent["close"].iloc[i])
        close_prev  = float(recent["close"].iloc[i - 1])
        vol_today   = float(recent["volume"].iloc[i])
        vol_prev    = float(recent["volume"].iloc[i - 1])
        if close_today < close_prev and vol_today > vol_prev * DISTRIBUTION_VOL_FACTOR:
            count += 1
    return count

# ─── UPTREND SCORE COMPUTATION (uptrend-analyzer skill) ───────────────────
def _compute_uptrend_score(sector_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes a 0-100 uptrend breadth score from sector ETF data.
    Components (weights per skill doc):
      Breadth 30%, Sector Participation 25%, Rotation 15%, Momentum 20%, Historical 10%.
    """
    if not sector_data:
        return {"score": 50, "zone": "Neutral", "components": {}}
    etfs = list(sector_data.values())
    # Breadth (30%): % of sectors above MA50 and MA200
    above_50  = sum(1 for e in etfs if e.get("above_ma50",  False))
    above_200 = sum(1 for e in etfs if e.get("above_ma200", False))
    n_etfs    = len(etfs) if etfs else 1
    breadth_raw = (above_50 / n_etfs * 50.0 + above_200 / n_etfs * 50.0)
    # Sector participation (25%): number of sectors with positive 1M return
    pos_1m   = sum(1 for e in etfs if e.get("1m_return", 0) > 0.0)
    part_raw = (pos_1m / n_etfs) * 100.0
    # Rotation (15%): cyclical vs defensive balance
    cyclical  = ["XLK", "XLY", "XLC", "XLI", "XLF"]
    defensive = ["XLP", "XLU", "XLV"]
    cyc_ret  = float(np.mean([sector_data[k]["1m_return"] for k in cyclical if k in sector_data])) if any(k in sector_data for k in cyclical) else 0.0
    def_ret  = float(np.mean([sector_data[k]["1m_return"] for k in defensive if k in sector_data])) if any(k in sector_data for k in defensive) else 0.0
    rot_raw  = 70.0 if cyc_ret > def_ret else 30.0
    # Momentum (20%): average 3M return of all sectors
    avg_3m   = float(np.mean([e.get("3m_return", 0.0) for e in etfs]))
    mom_raw  = min(100.0, max(0.0, 50.0 + avg_3m * 2.0))
    # Historical context (10%): fixed at 60 as neutral baseline (no long-run history available)
    hist_raw = 60.0
    composite = (
        breadth_raw * 0.30
        + part_raw  * 0.25
        + rot_raw   * 0.15
        + mom_raw   * 0.20
        + hist_raw  * 0.10
    )
    if composite >= UPTREND_BULL_STRONG:
        zone     = "Strong Bull"
        exposure = "Full (100%)"
    elif composite >= UPTREND_BULL:
        zone     = "Bull"
        exposure = "Normal (80-100%)"
    elif composite >= UPTREND_NEUTRAL:
        zone     = "Neutral"
        exposure = "Reduced (60-80%)"
    elif composite >= UPTREND_CAUTIOUS:
        zone     = "Cautious"
        exposure = "Defensive (30-60%)"
    else:
        zone     = "Bear"
        exposure = "Preservation (<30%)"
    return {
        "score":     round(composite, 1),
        "zone":      zone,
        "exposure":  exposure,
        "components": {
            "breadth":       round(breadth_raw, 1),
            "participation": round(part_raw,    1),
            "rotation":      round(rot_raw,     1),
            "momentum":      round(mom_raw,     1),
            "historical":    round(hist_raw,    1),
        },
        "cyclical_1m":  round(cyc_ret, 2),
        "defensive_1m": round(def_ret, 2),
        "above_ma50_pct":  round(above_50  / n_etfs * 100.0, 1),
        "above_ma200_pct": round(above_200 / n_etfs * 100.0, 1),
    }

# ─── BUBBLE SCORE COMPUTATION (us-market-bubble-detector skill) ───────────
def _compute_bubble_score(
    vix:          float,
    vix_pct_3m:   float,
    put_call:     float,
    breadth_50:   float,
    margin_yoy:   Optional[float],
    realized_vol: float,
) -> Dict[str, Any]:
    """
    Computes Minsky/Kindleberger bubble score (0-15 pts, Phase 1 only).
    All thresholds sourced from skill v2.1 documentation.
    """
    score   = 0
    details: Dict[str, Any] = {}
    # Put/Call Ratio (0-2 pts)
    if put_call < 0.55:
        pc_pts = 2
    elif put_call < 0.65:
        pc_pts = 1
    else:
        pc_pts = 0
    score           += pc_pts
    details["pc_pts"] = pc_pts

    # VIX + percentile (0-2 pts)
    vix_pts = 0
    if vix_pct_3m < BUBBLE_VIX_LOW_PCT:
        vix_pts = 2
    elif vix_pct_3m < 20.0:
        vix_pts = 1
    score            += vix_pts
    details["vix_pts"] = vix_pts

    # Breadth 50DMA (0-1 pt)
    breadth_pts = 1 if breadth_50 > BUBBLE_BREADTH_HIGH else 0
    score               += breadth_pts
    details["breadth_pts"] = breadth_pts

    # Volatility regime (0-1 pt)
    vol_pts = 1 if realized_vol < 8.0 else 0   # <8% annualized = extreme compression
    score          += vol_pts
    details["vol_pts"] = vol_pts

    # Margin debt YoY (0-2 pts)
    margin_pts = 0
    if margin_yoy is not None:
        if margin_yoy > BUBBLE_MARGIN_YOY_HIGH:
            margin_pts = 2
        elif margin_yoy > 10.0:
            margin_pts = 1
    score              += margin_pts
    details["margin_pts"] = margin_pts

    # Phase classification
    if score <= 3:
        phase = "Normal"
        color = "#00FF88"
    elif score <= 5:
        phase = "Watch"
        color = "#FFD700"
    elif score <= 7:
        phase = "Warning"
        color = "#FF9800"
    elif score <= 9:
        phase = "Elevated Risk"
        color = "#FF5252"
    else:
        phase = "Critical"
        color = "#FF0000"
    return {"score": score, "phase": phase, "color": color, "details": details}

# ─── DRUCKENMILLER CONVICTION SCORE ───────────────────────────────────────
def _compute_conviction(
    uptrend_score:     float,
    top_detector_score: float,
    distribution_days:  int,
    macro_data:         Dict[str, Any],
    sector_data:        Dict[str, Any],
) -> Dict[str, Any]:
    """
    Synthesizes 6 components into a Druckenmiller-style conviction score (0-100).
    Weights per skill documentation.
    """
    # Breadth health (25%): from uptrend score (0-100)
    breadth_health = uptrend_score

    # Uptrend ratio (20%): same input, different framing
    uptrend_ratio = uptrend_score

    # Top risk inverse (20%): invert the top detector score
    top_risk_inv = max(0.0, 100.0 - float(top_detector_score))

    # Macro regime (15%): VIX level + 10Y yield direction
    vix_cur  = macro_data.get("^VIX",  {}).get("current", 20.0)
    tnx_chg  = macro_data.get("^TNX",  {}).get("1y_change", 0.0)
    sp_chg   = macro_data.get("^GSPC", {}).get("1y_change", 0.0)
    macro_score = 50.0  # baseline
    if vix_cur < 15.0:
        macro_score += 15.0
    elif vix_cur > 30.0:
        macro_score -= 25.0
    elif vix_cur > 22.0:
        macro_score -= 10.0
    if tnx_chg < -10.0:
        macro_score += 10.0
    elif tnx_chg > 20.0:
        macro_score -= 10.0
    if sp_chg > 10.0:
        macro_score += 10.0
    elif sp_chg < -15.0:
        macro_score -= 15.0
    macro_score = max(0.0, min(100.0, macro_score))

    # Momentum (10%): average sector 1M return translated to 0-100
    if sector_data:
        avg_1m = float(np.mean([v.get("1m_return", 0.0) for v in sector_data.values()]))
    else:
        avg_1m = 0.0
    momentum = max(0.0, min(100.0, 50.0 + avg_1m * 5.0))

    # Leadership quality (10%): distribution days inverse
    # 0 days = 100 pts, 5+ days = 0 pts
    leadership = max(0.0, min(100.0, 100.0 - distribution_days * 20.0))

    conviction = (
        breadth_health * DRUCK_COMPONENTS["breadth_health"]
        + uptrend_ratio * DRUCK_COMPONENTS["uptrend_ratio"]
        + top_risk_inv  * DRUCK_COMPONENTS["top_risk_inverse"]
        + macro_score   * DRUCK_COMPONENTS["macro_regime"]
        + momentum      * DRUCK_COMPONENTS["momentum"]
        + leadership    * DRUCK_COMPONENTS["leadership_quality"]
    )
    # Druckenmiller pattern classification
    if conviction >= 70.0:
        pattern    = "Policy Pivot"
        allocation = "Aggressive Long — 100% Equity"
    elif conviction >= 55.0:
        pattern    = "Distortion Play"
        allocation = "Selective Long — 70-80% Equity"
    elif conviction >= 40.0:
        pattern    = "Contrarian Reversal"
        allocation = "Defensive + Opportunistic — 50-60% Equity"
    else:
        pattern    = "Wait & See"
        allocation = "Capital Preservation — <40% Equity"
    return {
        "score":      round(conviction, 1),
        "pattern":    pattern,
        "allocation": allocation,
        "components": {
            "breadth_health":    round(breadth_health, 1),
            "uptrend_ratio":     round(uptrend_ratio, 1),
            "top_risk_inverse":  round(top_risk_inv,  1),
            "macro_regime":      round(macro_score,   1),
            "momentum":          round(momentum,      1),
            "leadership_quality":round(leadership,    1),
        },
    }

# ─── EARNINGS SCORING (earnings-trade-analyzer skill) ─────────────────────
def _score_earnings_trade(
    ticker: str,
    df: pd.DataFrame,
    gap_pct: float,
) -> Dict[str, Any]:
    """
    Scores a post-earnings trade setup using the 5-factor system.
    Weights: gap_size 30%, pre_trend 20%, volume_ratio 20%, ma200 15%, ma50 15%.
    """
    if df.empty or len(df) < 60:
        return {"ticker": ticker, "score": 0, "grade": "D"}
    close = df["close"]
    # Gap size score (30%): larger positive gaps score higher
    gap_score = min(100.0, max(0.0, gap_pct * 5.0 + 50.0))
    # Pre-earnings 20-day trend (20%): positive trend = high score
    if len(close) >= 20:
        trend_20 = (float(close.iloc[-20]) / float(close.iloc[-21]) - 1.0) * 100.0 if len(close) >= 21 else 0.0
        trend_score = min(100.0, max(0.0, 50.0 + trend_20 * 5.0))
    else:
        trend_score = 50.0
    # Volume ratio (20%): current vol vs 60-day avg
    if "volume" in df.columns and len(df) >= 60:
        avg_vol_60 = float(df["volume"].tail(60).mean())
        cur_vol    = float(df["volume"].iloc[-1])
        vr = cur_vol / avg_vol_60 if avg_vol_60 > 1e-10 else 1.0
        vol_score = min(100.0, max(0.0, (vr - 1.0) * 40.0 + 50.0))
    else:
        vol_score = 50.0
    # MA200 position (15%)
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else float("nan")
    if not math.isnan(ma200):
        cur = float(close.iloc[-1])
        ma200_score = 100.0 if cur > float(ma200) else 0.0
    else:
        ma200_score = 50.0
    # MA50 position (15%)
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else float("nan")
    if not math.isnan(ma50):
        cur = float(close.iloc[-1])
        ma50_score = 100.0 if cur > float(ma50) else 0.0
    else:
        ma50_score = 50.0
    composite = (
        gap_score    * EARNINGS_WEIGHTS["gap_size"]
        + trend_score  * EARNINGS_WEIGHTS["pre_trend"]
        + vol_score    * EARNINGS_WEIGHTS["volume_ratio"]
        + ma200_score  * EARNINGS_WEIGHTS["ma200_position"]
        + ma50_score   * EARNINGS_WEIGHTS["ma50_position"]
    )
    if composite >= 85.0:
        grade = "A"
    elif composite >= 70.0:
        grade = "B"
    elif composite >= 55.0:
        grade = "C"
    else:
        grade = "D"
    return {
        "ticker":      ticker,
        "score":       round(composite, 1),
        "grade":       grade,
        "components": {
            "gap_size":       round(gap_score,    1),
            "pre_trend":      round(trend_score,  1),
            "volume_ratio":   round(vol_score,    1),
            "ma200_position": round(ma200_score,  1),
            "ma50_position":  round(ma50_score,   1),
        },
    }

# ═══════════════════════════════════════════════════════════════════════════
# TAB RENDERERS — ALL 13 SKILLS
# ═══════════════════════════════════════════════════════════════════════════

# ─── TAB 1: US-STOCK-ANALYSIS ──────────────────────────────────────────────
def _tab_stock_intelligence(api_key: str) -> None:
    """Skill: us-stock-analysis — Comprehensive US stock analysis."""
    _tab_header(
        skill_name="us-stock-analysis",
        color="#00B4FF",
        title="Stock Intelligence — Fundamental + Technical + Valuation",
        description=(
            "Comprehensive analysis of any US stock using live yfinance data. "
            "Select analysis depth: Basic overview, fundamental deep-dive, "
            "technical chart analysis, or full investment report. "
            "All metrics fetched live. AI analyst delivers institutional-grade output."
        ),
    )
    with st.form("stock_intel_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.text_input("Ticker Symbol", value="AAPL").upper().strip()
        with c2:
            analysis_type = st.selectbox(
                "Analysis Type",
                ["Comprehensive Report", "Fundamental Analysis",
                 "Technical Analysis", "Basic Overview"],
            )
        with c3:
            time_horizon = st.selectbox(
                "Investment Horizon",
                ["Short-Term (< 3 months)", "Medium-Term (3-12 months)",
                 "Long-Term (1-3 years)", "Strategic (3+ years)"],
            )
        extra = st.text_area("Additional Context (optional)",
                             placeholder="e.g. Bullish on AI tailwinds, concerned about valuation.",
                             height=70)
        submitted = st.form_submit_button("🔍 Run Stock Analysis", type="primary")
    if not submitted:
        return
    if not ticker:
        st.error("Please enter a ticker symbol.")
        return
    with st.spinner(f"Fetching live data for {ticker}…"):
        info = _fetch_info(ticker)
        df   = _fetch_history(ticker, years=2)
    if not info:
        st.error(f"No data for {ticker}. Verify the ticker.")
        return
    if not df.empty:
        ind = _compute_indicators(df)
        st.plotly_chart(
            _price_chart(df.tail(252), ticker,
                         title=f"{info.get('name', ticker)} — Price Chart (1Y)",
                         indicators={k: ind[k].tail(252) for k in ["ema_9", "ema_21", "ema_55"]}),
            use_container_width=True, config=TV_CONFIG,
        )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(f"{ticker} Price", f"${_flt(info.get('current_price'), '.2f')}")
    with c2:
        st.metric("Market Cap", _bn(info.get("market_cap")))
    with c3:
        st.metric("P/E (TTM)", _flt(info.get("pe_ratio"), ".1f"))
    with c4:
        st.metric("Div Yield", _pct(info.get("dividend_yield")))
    rsi_val = float(ind["rsi_21"].iloc[-1]) if not df.empty else 50.0
    user_content = (
        f"LIVE STOCK DATA — {ticker} | {info.get('name', ticker)}\n"
        f"Analysis Type: {analysis_type} | Horizon: {time_horizon}\n\n"
        f"PRICE: ${_flt(info.get('current_price'), '.4f')} | "
        f"Cap: {_bn(info.get('market_cap'))} | Beta: {_flt(info.get('beta'), '.2f')}\n"
        f"52W: ${_flt(info.get('52w_low'), '.2f')} – ${_flt(info.get('52w_high'), '.2f')}\n"
        f"Sector: {info.get('sector')} | Industry: {info.get('industry')}\n\n"
        f"VALUATION: P/E={_flt(info.get('pe_ratio'), '.1f')} | "
        f"Fwd P/E={_flt(info.get('forward_pe'), '.1f')} | "
        f"EV/EBITDA={_flt(info.get('ev_ebitda'), '.1f')} | "
        f"P/B={_flt(info.get('pb_ratio'), '.2f')} | PEG={_flt(info.get('peg_ratio'), '.2f')}\n\n"
        f"FUNDAMENTALS: Rev Growth={_pct(info.get('revenue_growth'))} | "
        f"Op Margin={_pct(info.get('operating_margin'))} | "
        f"Net Margin={_pct(info.get('profit_margin'))} | ROE={_pct(info.get('roe'))} | "
        f"D/E={_flt(info.get('debt_to_equity'), '.1f')} | FCF={_bn(info.get('free_cashflow'))}\n\n"
        f"TECHNICALS (live): RSI(21)={rsi_val:.1f} | "
        f"EMA9={_flt(ind['ema_9'].iloc[-1] if not df.empty else None, '.2f')} | "
        f"EMA55={_flt(ind['ema_55'].iloc[-1] if not df.empty else None, '.2f')}\n\n"
        f"ANALYST: {(info.get('recommendation') or 'N/A').upper()} | "
        f"Target Mean=${_flt(info.get('target_mean_price'), '.2f')} | "
        f"N={info.get('analyst_count', 'N/A')} analysts\n\n"
        f"BUSINESS: {info.get('description', 'N/A')}\n\n"
        f"ADDITIONAL CONTEXT: {extra or 'None'}\n\n"
        f"Deliver the complete {analysis_type} for {ticker}. "
        f"All price targets must be derived from the live data above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming stock analysis…"):
            _stream(api_key, SYS_STOCK_INTELLIGENCE, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("us-stock-analysis")

# ─── TAB 2: TECHNICAL-ANALYST ─────────────────────────────────────────────
def _tab_chart_analyst(api_key: str) -> None:
    """Skill: technical-analyst — Pure chart technical analysis with scenarios."""
    _tab_header(
        skill_name="technical-analyst",
        color="#00FF88",
        title="Chart Analyst — Probabilistic Technical Scenarios",
        description=(
            "Pure price-action technical analysis. Fetches live OHLCV data, computes "
            "all indicators (EMA/SMA stack, RSI, MACD, Bollinger, Ichimoku), and "
            "deploys a CMT-certified analyst persona to develop 2-4 probability-weighted "
            "scenarios. All analysis strictly chart-based — no fundamentals."
        ),
    )
    with st.form("chart_analyst_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.text_input("Ticker / Index / ETF", value="SPY").upper().strip()
        with c2:
            timeframe_label = st.selectbox(
                "Chart Timeframe",
                ["Daily (1Y)", "Daily (6M)", "Weekly (2Y)", "Monthly (5Y)"],
            )
        with c3:
            focus = st.text_area("Analysis Focus (optional)",
                                  placeholder="e.g. Near resistance. Looking for breakout.",
                                  height=70)
        submitted = st.form_submit_button("📈 Run Chart Analysis", type="primary")
    if not submitted:
        return
    tf_years = {"Daily (1Y)": 1, "Daily (6M)": 1, "Weekly (2Y)": 2, "Monthly (5Y)": 5}
    tf_tail  = {"Daily (1Y)": 252, "Daily (6M)": 126, "Weekly (2Y)": 104, "Monthly (5Y)": 60}
    years    = tf_years.get(timeframe_label, 1)
    n_bars   = tf_tail.get(timeframe_label, 252)
    with st.spinner(f"Fetching {ticker} [{timeframe_label}]…"):
        df   = _fetch_history(ticker, years=years)
        info = _fetch_info(ticker)
    if df.empty:
        st.error(f"No price data for {ticker}.")
        return
    if "weekly" in timeframe_label.lower():
        df = df.resample("W").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    elif "monthly" in timeframe_label.lower():
        df = df.resample("ME").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    df = df.tail(n_bars)
    ind = _compute_indicators(df)
    cur = float(df["close"].iloc[-1])
    st.plotly_chart(
        _price_chart(df, ticker,
                     title=f"{ticker} — {timeframe_label} | Technical Analysis",
                     indicators={k: ind[k] for k in ["ema_9","ema_21","ema_55","bb_upper","bb_lower"]}),
        use_container_width=True, config=TV_CONFIG,
    )
    e9   = float(ind["ema_9"].iloc[-1])
    e21  = float(ind["ema_21"].iloc[-1])
    e55  = float(ind["ema_55"].iloc[-1])
    s200 = float(ind["sma_200"].iloc[-1]) if not pd.isna(ind["sma_200"].iloc[-1]) else 0.0
    rsi  = float(ind["rsi_21"].iloc[-1])
    macd = float(ind["macd_line"].iloc[-1])
    sig  = float(ind["signal_line"].iloc[-1])
    hist = float(ind["histogram"].iloc[-1])
    bbu  = float(ind["bb_upper"].iloc[-1]) if not pd.isna(ind["bb_upper"].iloc[-1]) else cur
    bbl  = float(ind["bb_lower"].iloc[-1]) if not pd.isna(ind["bb_lower"].iloc[-1]) else cur
    ph_hi = float(df["high"].max())
    ph_lo = float(df["low"].min())
    vol_avg = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 0.0
    vol_cur = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
    user_content = (
        f"LIVE TECHNICAL DATA — {ticker} | {timeframe_label}\n"
        f"Bars analyzed: {len(df)} | "
        f"Date range: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}\n\n"
        f"CURRENT PRICE: {cur:.4f}\n"
        f"PERIOD HIGH: {ph_hi:.4f} | PERIOD LOW: {ph_lo:.4f}\n\n"
        f"MOVING AVERAGES:\n"
        f"  EMA9={e9:.4f} ({'↑ ABOVE' if cur > e9 else '↓ BELOW'})\n"
        f"  EMA21={e21:.4f} ({'↑ ABOVE' if cur > e21 else '↓ BELOW'})\n"
        f"  EMA55={e55:.4f} ({'↑ ABOVE' if cur > e55 else '↓ BELOW'})\n"
        f"  SMA200={s200:.4f} ({'↑ ABOVE' if s200 > 0 and cur > s200 else '↓ BELOW'})\n"
        f"  EMA Stack: {'BULLISH' if e9 > e21 > e55 else 'BEARISH' if e9 < e21 < e55 else 'MIXED'}\n\n"
        f"OSCILLATORS:\n"
        f"  RSI(21)={rsi:.2f} — "
        f"{'OVERBOUGHT' if rsi > 70 else 'OVERSOLD' if rsi < 30 else 'NEUTRAL'}\n"
        f"  MACD={macd:.4f} | Signal={sig:.4f} | Hist={hist:.4f} — "
        f"{'BULLISH' if hist > 0 else 'BEARISH'}\n\n"
        f"BOLLINGER BANDS (20,2): Upper={bbu:.4f} | Lower={bbl:.4f}\n"
        f"  Price position: {((cur - bbl) / (bbu - bbl) * 100):.0f}% from lower band\n\n"
        f"VOLUME: Current={vol_cur:.0f} vs 20D avg={vol_avg:.0f} "
        f"({'ABOVE AVG' if vol_avg > 0 and vol_cur > vol_avg * 1.2 else 'BELOW AVG' if vol_avg > 0 and vol_cur < vol_avg * 0.8 else 'AVERAGE'})\n\n"
        f"FIBONACCI LEVELS (period high/low):\n"
        f"  Period High: {ph_hi:.4f}\n"
        + "".join(f"  {lvl*100:.1f}%: {ph_hi - (ph_hi - ph_lo) * lvl:.4f}\n"
                  for lvl in [0.236, 0.382, 0.500, 0.618, 0.786])
        + f"  Period Low: {ph_lo:.4f}\n\n"
        f"ANALYSIS FOCUS: {focus or 'General technical assessment'}\n\n"
        f"Deliver the complete technical analysis report with 2-4 probabilistic scenarios. "
        f"All price levels must be derived from the data above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming chart analysis…"):
            _stream(api_key, SYS_CHART_ANALYST, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("technical-analyst")

# ─── TAB 3: MARKET-ENVIRONMENT-ANALYSIS ───────────────────────────────────
def _tab_market_environment(api_key: str) -> None:
    """Skill: market-environment-analysis — Global markets, risk-on/off regime."""
    _tab_header(
        skill_name="market-environment-analysis",
        color="#FFD700",
        title="Market Environment — Global Regime Dashboard",
        description=(
            "Fetches live macro indicators: S&P 500, NASDAQ, Dow, VIX, 10Y/3M Treasury yields, "
            "DXY, Gold, Crude, Euro Stoxx 50, Nikkei. Deploys a senior macro strategist to "
            "classify the current regime (Risk-On/Off/Mixed), assess sector rotation, and "
            "deliver 3 specific portfolio adjustments for current conditions."
        ),
    )
    c1, c2 = st.columns([2, 1])
    with c1:
        portfolio_context = st.text_area(
            "Portfolio Context (optional)",
            placeholder="e.g. 60% US equities, 20% bonds, 20% cash.",
            height=80,
        )
    with c2:
        investor_type = st.selectbox(
            "Investor Profile",
            ["Long-term Investor", "Swing Trader", "Day Trader", "Options Trader", "Forex Trader"],
        )
    run_btn = st.button("🌐 Run Market Environment Analysis", type="primary")
    if not run_btn:
        st.info("Press the button to fetch live global market data and run analysis.")
        return
    with st.spinner("Fetching global market data…"):
        macro = _fetch_macro()
    if not macro:
        st.error("Failed to fetch macro data. Check network connection.")
        return
    # Display macro dashboard
    st.markdown("#### " + t("hub_macro_dashboard"))
    cols = st.columns(4)
    for i, (tkr, d) in enumerate(list(macro.items())[:8]):
        with cols[i % 4]:
            delta_color = "normal" if abs(d["1y_change"]) < 5.0 else "off"
            st.metric(
                label=d["name"],
                value=f"{d['current']:.2f}",
                delta=f"{d['1y_change']:+.1f}% (1Y)",
                delta_color="normal",
            )
    vix_cur = macro.get("^VIX", {}).get("current", 20.0)
    # VIX percentile estimate from 1Y data
    with st.spinner("Fetching sector performance…"):
        sector_data = _fetch_sector_breadth()
    macro_lines = [
        f"LIVE MACRO INDICATORS — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"{'Indicator':<30} {'Current':>10} {'1Y Change':>10} {'52W High':>10} {'52W Low':>10}",
        "-" * 75,
    ]
    for tkr, d in macro.items():
        macro_lines.append(
            f"{d['name']:<30} {d['current']:>10.4f} {d['1y_change']:>+10.2f}% "
            f"{d['52w_high']:>10.4f} {d['52w_low']:>10.4f}"
        )
    macro_lines += ["", "SECTOR ETF PERFORMANCE:"]
    for etf, d in sector_data.items():
        macro_lines.append(
            f"  {etf:<6} {d['sector']:<22} 1M: {d['1m_return']:+.1f}%  3M: {d['3m_return']:+.1f}%  "
            f"vs MA50: {'↑' if d['above_ma50'] else '↓'}  vs MA200: {'↑' if d['above_ma200'] else '↓'}"
        )
    user_content = (
        "\n".join(macro_lines) + f"\n\n"
        f"INVESTOR PROFILE: {investor_type}\n"
        f"PORTFOLIO CONTEXT: {portfolio_context or 'Not specified'}\n\n"
        f"Deliver the complete global market environment assessment, LEADING with the "
        f"Regime Dashboard. All calls must reference specific data values provided."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming market environment analysis…"):
            _stream(api_key, SYS_MARKET_ENVIRONMENT, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("market-environment-analysis")

# ─── TAB 4: BREADTH-CHART-ANALYST ─────────────────────────────────────────
def _tab_breadth_dashboard(api_key: str) -> None:
    """Skill: breadth-chart-analyst — S&P 500 breadth index + uptrend stock ratio."""
    _tab_header(
        skill_name="breadth-chart-analyst",
        color="#A855F7",
        title="Breadth Dashboard — S&P 500 Breadth Index + Uptrend Ratio",
        description=(
            "Computes live S&P 500 market breadth from sector ETF data: % above MA200 / MA50, "
            "sector participation, cyclical vs defensive rotation. Applies the TraderMonty "
            "backtested strategy (BUY: 8MA reversal from trough; SELL: 200MA peak near 73%). "
            "Delivers strategic + tactical positioning recommendations."
        ),
    )
    run_btn = st.button("📡 Run Breadth Dashboard", type="primary")
    if not run_btn:
        st.info("Click to fetch live sector breadth data and run analysis.")
        return
    with st.spinner("Fetching sector breadth data…"):
        sector_data = _fetch_sector_breadth()
    if not sector_data:
        st.error("Failed to fetch sector data.")
        return
    uptrend = _compute_uptrend_score(sector_data)
    # Visual score gauge
    score = uptrend["score"]
    zone  = uptrend["zone"]
    zone_color = {
        "Strong Bull": "#00FF88",
        "Bull":        "#00E676",
        "Neutral":     "#FFD700",
        "Cautious":    "#FF9800",
        "Bear":        "#FF5252",
    }.get(zone, "#FFD700")
    st.markdown(
        f"""
        <div style='background:#001a0d;border:2px solid {zone_color};border-radius:12px;
                    padding:20px 28px;margin-bottom:16px;text-align:center;'>
            <p style='color:{zone_color};font-family:monospace;font-size:11px;
                      letter-spacing:2px;margin:0 0 6px 0;'>BREADTH HEALTH SCORE</p>
            <p style='color:{zone_color};font-size:52px;font-weight:bold;
                      font-family:monospace;margin:0;'>{score}</p>
            <p style='color:#E8E0D0;font-size:16px;margin:4px 0 0 0;'>{zone} — {uptrend['exposure']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Component metrics
    comps = uptrend["components"]
    cols  = st.columns(5)
    comp_names = ["Breadth", "Participation", "Rotation", "Momentum", "Historical"]
    comp_keys  = ["breadth", "participation", "rotation", "momentum", "historical"]
    comp_weights = ["30%", "25%", "15%", "20%", "10%"]
    for i, (col, key, name, w) in enumerate(zip(cols, comp_keys, comp_names, comp_weights)):
        with col:
            st.metric(f"{name} ({w})", f"{comps.get(key, 0):.0f}/100")
    # Sector heatmap chart
    etf_names  = [v["sector"] for v in sector_data.values()]
    returns_1m = [v["1m_return"] for v in sector_data.values()]
    colors_bar = ["#00FF88" if r > 0 else "#FF5252" for r in returns_1m]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=etf_names, y=returns_1m,
        marker_color=colors_bar, marker_line_width=0,
        text=[f"{r:+.1f}%" for r in returns_1m], textposition="outside",
        textfont=dict(color="#E8E0D0", size=10),
        name="1M Return %",
    ))
    layout = _tv_layout(height=300, title="Sector ETF 1-Month Returns")
    layout["xaxis"] = {"gridcolor": "rgba(128,128,128,0.06)", "tickfont": {"color": "#8a8a8a", "size": 10}}
    layout["yaxis"] = _tv_yaxis(fixed_range=False)
    layout["margin"] = {"l": 10, "r": 50, "t": 50, "b": 60}
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config=TV_CONFIG)
    # Prepare data for AI analysis
    sector_lines = [
        f"LIVE SECTOR BREADTH DATA — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"BREADTH HEALTH SCORE: {score}/100 | Zone: {zone} | Exposure: {uptrend['exposure']}",
        f"Above MA50:  {uptrend['above_ma50_pct']:.1f}% of sectors",
        f"Above MA200: {uptrend['above_ma200_pct']:.1f}% of sectors",
        f"Cyclical avg 1M: {uptrend['cyclical_1m']:+.2f}% | Defensive avg 1M: {uptrend['defensive_1m']:+.2f}%",
        "",
        f"COMPONENT SCORES: Breadth={comps.get('breadth',0):.0f} | Participation={comps.get('participation',0):.0f} | "
        f"Rotation={comps.get('rotation',0):.0f} | Momentum={comps.get('momentum',0):.0f}",
        "",
        "SECTOR DETAIL:",
    ]
    for etf, d in sector_data.items():
        sector_lines.append(
            f"  {etf} {d['sector']:<22} 1M:{d['1m_return']:+.1f}%  3M:{d['3m_return']:+.1f}%  "
            f"MA50:{'↑' if d['above_ma50'] else '↓'}  MA200:{'↑' if d['above_ma200'] else '↓'}"
        )
    user_content = "\n".join(sector_lines) + (
        "\n\nDeliver the complete breadth dashboard analysis applying the TraderMonty "
        "backtested strategy. Identify strategic and tactical signals, and provide specific "
        "positioning recommendations."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming breadth analysis…"):
            _stream(api_key, SYS_BREADTH_DASHBOARD, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("breadth-chart-analyst")

# ─── TAB 5: MARKET-NEWS-ANALYST ────────────────────────────────────────────
def _tab_market_news(api_key: str) -> None:
    """Skill: market-news-analyst — Impact analysis of recent market news."""
    _tab_header(
        skill_name="market-news-analyst",
        color="#FF6B6B",
        title="News Impact Analyst — 10-Day Market Intelligence Brief",
        description=(
            "Analyzes recent market-moving events and their portfolio impact. "
            "User describes current news flow; AI deploys a tier-1 institutional "
            "research analyst to assess macro, monetary policy, corporate events, "
            "and geopolitical impacts by sector. Delivers specific portfolio adjustments."
        ),
    )
    with st.form("news_form"):
        news_summary = st.text_area(
            "Recent News Summary (paste or describe key news from the last 10 days)",
            height=160,
            placeholder=(
                "e.g.\n"
                "- Fed held rates steady, signaled 2 cuts in 2025\n"
                "- Strong NFP: 280K jobs added vs 200K expected\n"
                "- NVDA earnings beat: +15% revenue guidance raise\n"
                "- Oil jumped 8% on Middle East tensions\n"
                "- CPI came in hot at 3.4% vs 3.1% expected"
            ),
        )
        c1, c2 = st.columns(2)
        with c1:
            sector_focus = st.multiselect(
                "Sector Focus (optional)",
                ["Technology", "Healthcare", "Financials", "Energy", "Consumer",
                 "Industrials", "Utilities", "Materials", "Real Estate", "All Sectors"],
                default=["All Sectors"],
            )
        with c2:
            portfolio_text = st.text_area(
                "Your Portfolio (optional, ticker:weight%)",
                placeholder="AAPL:25\nMSFT:20\nNVDA:15\nJPM:20\nXOM:20",
                height=80,
            )
        submitted = st.form_submit_button("📰 Run News Impact Analysis", type="primary")
    if not submitted:
        return
    if not news_summary.strip():
        st.error("Please describe recent news events in the text area.")
        return
    with st.spinner("Fetching macro context…"):
        macro = _fetch_macro()
    macro_summary = "\n".join(
        f"  {d['name']}: {d['current']:.4f} ({d['1y_change']:+.1f}% 1Y)"
        for d in macro.values()
    ) if macro else "  Macro data unavailable"
    sector_str = ", ".join(sector_focus) if sector_focus else "All Sectors"
    user_content = (
        f"RECENT NEWS EVENTS (user provided):\n{news_summary}\n\n"
        f"CURRENT MACRO CONTEXT (live):\n{macro_summary}\n\n"
        f"SECTOR FOCUS: {sector_str}\n"
        f"PORTFOLIO: {portfolio_text or 'Not specified'}\n\n"
        f"Deliver the complete 10-day market news impact brief. Rank events by impact. "
        f"Provide sector-by-sector impact map and specific portfolio adjustments."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming news impact analysis…"):
            _stream(api_key, SYS_MARKET_NEWS, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("market-news-analyst")

# ─── TAB 6: MARKET-TOP-DETECTOR ────────────────────────────────────────────
def _tab_market_top(api_key: str) -> None:
    """Skill: market-top-detector — O'Neil distribution days + top probability."""
    _tab_header(
        skill_name="market-top-detector",
        color="#FF9500",
        title="Market Top Detector — Distribution Day Analysis",
        description=(
            "Detects market top probability using O'Neil Distribution Day accumulation, "
            "Minervini leading stock deterioration, and Monty defensive rotation signals. "
            "Generates a 0-100 composite score across 6 components. Focuses on 2-8 week "
            "tactical timing for 10-20% corrections."
        ),
    )
    with st.form("top_detector_form"):
        c1, c2 = st.columns(2)
        with c1:
            index_ticker = st.selectbox(
                "Index to Analyze",
                ["^GSPC (S&P 500)", "^IXIC (NASDAQ)", "^DJI (Dow)", "QQQ (NASDAQ ETF)", "SPY (S&P 500 ETF)"],
            )
        with c2:
            extra_context = st.text_area(
                "Additional Observations (optional)",
                placeholder="e.g. Seeing stalling action near highs. Leaders like NVDA acting tired.",
                height=80,
            )
        submitted = st.form_submit_button("⚠️ Run Top Detector", type="primary")
    if not submitted:
        return
    ticker_map = {
        "^GSPC (S&P 500)": "^GSPC", "^IXIC (NASDAQ)": "^IXIC",
        "^DJI (Dow)": "^DJI", "QQQ (NASDAQ ETF)": "QQQ", "SPY (S&P 500 ETF)": "SPY",
    }
    index_t = ticker_map.get(index_ticker, "^GSPC")
    with st.spinner(f"Fetching {index_ticker} and growth ETF data…"):
        df_idx = _fetch_history(index_t, years=1)
        sector = _fetch_sector_breadth()
        macro  = _fetch_macro()
        growth_etfs_data: Dict[str, pd.DataFrame] = {}
        for etf in GROWTH_ETFS:
            d = _fetch_history(etf, years=1)
            if not d.empty:
                growth_etfs_data[etf] = d
    if df_idx.empty:
        st.error(f"No data for {index_t}.")
        return
    dist_days = _compute_distribution_days(df_idx)
    # Compute growth ETF deterioration
    growth_perf: Dict[str, float] = {}
    for etf, df_e in growth_etfs_data.items():
        if len(df_e) >= 21:
            m1_ret = (float(df_e["close"].iloc[-1]) / float(df_e["close"].iloc[-21]) - 1.0) * 100.0
            growth_perf[etf] = m1_ret
    avg_growth_1m = float(np.mean(list(growth_perf.values()))) if growth_perf else 0.0
    idx_1m = (float(df_idx["close"].iloc[-1]) / float(df_idx["close"].iloc[-21]) - 1.0) * 100.0 if len(df_idx) >= 21 else 0.0
    vix_cur = macro.get("^VIX", {}).get("current", 20.0)
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dist_color = "red" if dist_days >= 5 else "orange" if dist_days >= 3 else "green"
        st.metric("Distribution Days (25D)", dist_days)
    with c2:
        st.metric("Index 1M Return", f"{idx_1m:+.1f}%")
    with c3:
        st.metric("Avg Growth ETF 1M", f"{avg_growth_1m:+.1f}%")
    with c4:
        st.metric("VIX", f"{vix_cur:.1f}")
    uptrend = _compute_uptrend_score(sector)
    data_ctx = (
        f"LIVE MARKET TOP DETECTION DATA — {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"INDEX: {index_ticker}\n"
        f"Distribution Days (last {DISTRIBUTION_DAY_WINDOW} sessions): {dist_days}\n"
        f"  (O'Neil: 5+ distribution days = elevated top risk)\n\n"
        f"INDEX TECHNICAL:\n"
        f"  1M Return: {idx_1m:+.1f}%\n"
        f"  Current: ${float(df_idx['close'].iloc[-1]):.2f}\n"
        f"  50D Trend: {('Rising' if df_idx['close'].iloc[-1] > df_idx['close'].ewm(span=50).mean().iloc[-1] else 'Declining')}\n\n"
        f"GROWTH ETF HEALTH (Minervini leading stock check):\n"
        + "\n".join(f"  {etf}: {ret:+.1f}% 1M" for etf, ret in growth_perf.items())
        + f"\n  Average growth ETF vs index: {avg_growth_1m - idx_1m:+.1f}% relative\n\n"
        f"DEFENSIVE ROTATION (sector data):\n"
        f"  Breadth health: {uptrend['score']}/100 ({uptrend['zone']})\n"
        f"  Cyclical 1M: {uptrend['cyclical_1m']:+.2f}% | Defensive 1M: {uptrend['defensive_1m']:+.2f}%\n"
        f"  Rotation: {'Cyclical LEADING (risk-on)' if uptrend['cyclical_1m'] > uptrend['defensive_1m'] else 'Defensive LEADING (risk-off)'}\n\n"
        f"SENTIMENT:\n"
        f"  VIX: {vix_cur:.1f} ({'LOW <15' if vix_cur < 15 else 'ELEVATED >25' if vix_cur > 25 else 'NORMAL'})\n\n"
        f"ADDITIONAL OBSERVATIONS: {extra_context or 'None'}\n\n"
        f"Deliver the complete Market Top Detector analysis with a 0-100 composite score, "
        f"all 6 component scores, and specific exposure management recommendation."
    )
    ph = st.empty()
    try:
        with st.spinner("Streaming top detector analysis…"):
            _stream(api_key, SYS_MARKET_TOP, data_ctx, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("market-top-detector")

# ─── TAB 7: OPTIONS-STRATEGY-ADVISOR ──────────────────────────────────────
def _tab_options_advisor(api_key: str) -> None:
    """Skill: options-strategy-advisor — Black-Scholes pricing + strategy P&L."""
    _tab_header(
        skill_name="options-strategy-advisor",
        color="#18FFFF",
        title="Options Strategy Advisor — Black-Scholes + Strategy P&L",
        description=(
            "Theoretical option pricing using Black-Scholes with full Greeks (Δ, Γ, Θ, V, ρ). "
            "Simulates P&L profiles for calls, puts, spreads, straddles, and iron condors. "
            "Analyzes earnings IV crush risk. All calculations computed from your inputs "
            "using the Black-Scholes model — no live options chain required."
        ),
    )
    if not _SCIPY_AVAILABLE:
        st.error("scipy not installed. Run: `pip install scipy` and restart the app.")
        return
    with st.form("options_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            underlying = st.text_input("Underlying Ticker", value="AAPL").upper().strip()
            option_type = st.selectbox("Option Type", ["call", "put"])
        with c2:
            use_live = st.checkbox("Fetch live price", value=True)
            manual_price = st.number_input("Stock Price (if not live)", min_value=1.0, value=185.0, step=1.0)
            strike = st.number_input("Strike Price", min_value=1.0, value=190.0, step=1.0)
        with c3:
            days_to_expiry = st.number_input("Days to Expiry", min_value=1, max_value=730, value=30)
            iv = st.number_input("Implied Volatility (%)", min_value=1.0, max_value=500.0, value=25.0) / 100.0
            rfr = st.number_input("Risk-Free Rate (%)", min_value=0.0, max_value=20.0, value=4.5) / 100.0
        strategy = st.selectbox(
            "Strategy to Analyze",
            ["Single Option", "Covered Call", "Protective Put",
             "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle", "Iron Condor"],
        )
        position_note = st.text_area("Context / Thesis (optional)",
                                      placeholder="e.g. Long 200 shares, want downside protection before earnings.",
                                      height=70)
        submitted = st.form_submit_button("💡 Calculate Options Strategy", type="primary")
    if not submitted:
        return
    S = manual_price
    if use_live:
        with st.spinner(f"Fetching live price for {underlying}…"):
            info = _fetch_info(underlying)
        live_price = info.get("current_price")
        if live_price:
            S = float(live_price)
            st.success(f"✓ Live price for {underlying}: ${S:.2f}")
        else:
            st.warning(f"Could not fetch live price for {underlying}. Using ${manual_price:.2f}.")
    T = days_to_expiry / 365.0
    K = float(strike)
    try:
        price, greeks = _bs_price(S, K, T, rfr, iv, option_type)
    except (ValueError, RuntimeError) as e:
        st.error(f"Black-Scholes calculation error: {e}")
        return
    # Display results
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(f"BS {option_type.upper()} Price", f"${price:.4f}")
    with c2:
        st.metric("Delta (Δ)", f"{greeks['delta']:+.4f}")
    with c3:
        st.metric("Gamma (Γ)", f"{greeks['gamma']:.6f}")
    with c4:
        st.metric("Theta (Θ/day)", f"${greeks['theta']:+.4f}")
    with c5:
        st.metric("Vega (V/1%IV)", f"${greeks['vega']:.4f}")
    # P&L chart
    st.plotly_chart(
        _options_pnl_chart(S, K, price, option_type),
        use_container_width=True, config=TV_CONFIG,
    )
    # Intrinsic / time value breakdown
    intrinsic = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
    time_val  = max(0.0, price - intrinsic)
    st.caption(
        f"Intrinsic Value: ${intrinsic:.4f} | Time Value: ${time_val:.4f} | "
        f"Moneyness: {'ITM' if intrinsic > 0 else 'OTM'} | "
        f"Breakeven: ${S + price:.2f if option_type == 'call' else S - price:.2f}"
    )
    user_content = (
        f"LIVE BLACK-SCHOLES CALCULATION:\n"
        f"  Underlying: {underlying} | Current Price: ${S:.2f} | Strike: ${K:.2f}\n"
        f"  Option Type: {option_type.upper()} | Days to Expiry: {days_to_expiry}\n"
        f"  IV: {iv*100:.1f}% | Risk-Free Rate: {rfr*100:.1f}%\n\n"
        f"THEORETICAL PRICING RESULTS:\n"
        f"  BS Option Price: ${price:.4f}\n"
        f"  Delta: {greeks['delta']:+.4f} | Gamma: {greeks['gamma']:.6f}\n"
        f"  Theta: {greeks['theta']:+.4f}/day | Vega: {greeks['vega']:.4f}/1%IV\n"
        f"  Rho: {greeks['rho']:+.4f}/1%Rate\n"
        f"  Intrinsic: ${intrinsic:.4f} | Time Value: ${time_val:.4f}\n"
        f"  Moneyness: {'ITM' if intrinsic > 0 else 'OTM'}\n\n"
        f"STRATEGY REQUESTED: {strategy}\n"
        f"POSITION CONTEXT: {position_note or 'None provided'}\n\n"
        f"Deliver the complete options strategy analysis. For {strategy}, show exact premium costs, "
        f"max profit/loss, breakeven(s), and specific entry/exit guidance. "
        f"Derive all calculations from the Black-Scholes outputs above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming options strategy analysis…"):
            _stream(api_key, SYS_OPTIONS_ADVISOR, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("options-strategy-advisor")

# ─── TAB 8: PORTFOLIO-MANAGER ──────────────────────────────────────────────
def _tab_portfolio_manager(api_key: str) -> None:
    """Skill: portfolio-manager — Portfolio risk, correlation, rebalancing."""
    _tab_header(
        skill_name="portfolio-manager",
        color="#76FF03",
        title="Portfolio Manager — Risk Analysis + Rebalancing",
        description=(
            "Enter your holdings as TICKER:WEIGHT% pairs. Fetches 2 years of live price history, "
            "computes annualized volatility, correlation matrix, sector concentration, and beta-weighted "
            "stress test. Deploys a CFA/FRM/CAIA portfolio manager to deliver full risk assessment "
            "with specific rebalancing and hedging recommendations."
        ),
    )
    with st.form("portfolio_form"):
        portfolio_text = st.text_area(
            "Portfolio Holdings (TICKER:WEIGHT% — one per line)",
            value="AAPL:20\nMSFT:20\nNVDA:15\nJPM:15\nJNJ:15\nBRK-B:15",
            height=160,
        )
        c1, c2 = st.columns(2)
        with c1:
            total_value = st.number_input("Total Portfolio Value (USD)", min_value=1000,
                                          max_value=1_000_000_000, value=250_000, step=5_000)
        with c2:
            risk_concerns = st.text_area("Primary Risk Concerns (optional)",
                                          placeholder="e.g. Rising rates, concentrated in tech.",
                                          height=80)
        submitted = st.form_submit_button("🛡️ Run Portfolio Analysis", type="primary")
    if not submitted:
        return
    holdings: Dict[str, float] = {}
    for line in portfolio_text.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        parts = line.split(":")
        if len(parts) != 2:
            continue
        try:
            t   = parts[0].strip().upper()
            pct = float(parts[1].strip())
            if t and pct > 0.0:
                holdings[t] = pct
        except ValueError:
            continue
    if len(holdings) < 2:
        st.error("Please enter at least 2 holdings in TICKER:WEIGHT% format.")
        return
    tickers = list(holdings.keys())
    info_map:  Dict[str, Dict[str, Any]] = {}
    price_map: Dict[str, pd.DataFrame]   = {}
    bar = st.progress(0, text="Fetching portfolio data…")
    for i, tkr in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"Fetching {tkr}…")
        info_map[tkr]  = _fetch_info(tkr)
        price_map[tkr] = _fetch_history(tkr, years=2)
        time.sleep(0.05)
    bar.empty()
    # Compute volatilities and correlations
    returns_map: Dict[str, pd.Series] = {}
    for tkr, df in price_map.items():
        if not df.empty and "close" in df.columns and len(df) > 30:
            returns_map[tkr] = df["close"].pct_change().dropna()
    vols: Dict[str, float] = {
        tkr: float(r.std()) * math.sqrt(TRADING_DAYS_YEAR) * 100.0
        for tkr, r in returns_map.items()
    }
    if len(returns_map) > 1:
        prices_df    = pd.DataFrame(returns_map).dropna()
        corr_matrix  = prices_df.corr()
        high_corr_pairs: List[Tuple[str, str, float]] = []
        t_list = list(returns_map.keys())
        for i in range(len(t_list)):
            for j in range(i + 1, len(t_list)):
                v = float(corr_matrix.loc[t_list[i], t_list[j]])
                if v > 0.70:
                    high_corr_pairs.append((t_list[i], t_list[j], v))
    else:
        corr_matrix = pd.DataFrame()
        high_corr_pairs = []
    # Sector breakdown
    sector_wts: Dict[str, float] = {}
    for tkr, pct in holdings.items():
        sec = info_map.get(tkr, {}).get("sector", "Unknown")
        sector_wts[sec] = sector_wts.get(sec, 0.0) + pct
    # Correlation heatmap
    if not corr_matrix.empty:
        fig_corr = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns.tolist(),
            y=corr_matrix.index.tolist(),
            colorscale=[
                [0.0, "#FF5252"], [0.5, "#000d1a"], [1.0, "#00FF88"]
            ],
            zmid=0,
            text=[[f"{v:.2f}" for v in row] for row in corr_matrix.values],
            texttemplate="%{text}",
            textfont={"size": 11, "color": "white"},
            zmin=-1.0, zmax=1.0,
        ))
        layout_h = _tv_layout(height=360, title="Portfolio Correlation Matrix")
        layout_h["margin"] = {"l": 80, "r": 80, "t": 60, "b": 80}
        layout_h["xaxis"] = {"tickfont": {"color": "#8a8a8a", "size": 10}}
        layout_h["yaxis"] = {"tickfont": {"color": "#8a8a8a", "size": 10}, "side": "left"}
        fig_corr.update_layout(**layout_h)
        st.plotly_chart(fig_corr, use_container_width=True, config=TV_CONFIG)
    # Build data context for AI
    lines = [
        f"LIVE PORTFOLIO RISK DATA — ${total_value:,}",
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}", "",
        "HOLDINGS:",
    ]
    for tkr, pct in holdings.items():
        d    = info_map.get(tkr, {})
        vol  = vols.get(tkr, 0.0)
        beta = _flt(d.get("beta"), ".2f")
        sec  = d.get("sector", "Unknown")
        lines.append(
            f"  {tkr:<12} {(d.get('name') or tkr)[:28]:<30} {pct:.1f}%  "
            f"Sector:{sec}  Vol:{vol:.1f}%  Beta:{beta}  Cap:{_bn(d.get('market_cap'))}"
        )
    lines += ["", "SECTOR CONCENTRATION:"]
    for sec, wt in sorted(sector_wts.items(), key=lambda x: -x[1]):
        flag = "  ⚠️ CONCENTRATED" if wt > 30.0 else ""
        lines.append(f"  {sec:<30}: {wt:.1f}%{flag}")
    if high_corr_pairs:
        lines += ["", "HIGH CORRELATION PAIRS (>0.70):"]
        for t1, t2, v in sorted(high_corr_pairs, key=lambda x: -x[2]):
            lines.append(f"  {t1} & {t2}: {v:.2f} ⚠️ RISK CLUSTER")
    user_content = (
        "\n".join(lines) + f"\n\n"
        f"TOTAL VALUE: ${total_value:,}\n"
        f"PRIMARY CONCERNS: {risk_concerns or 'None specified'}\n\n"
        f"Deliver the complete portfolio risk management report. All metrics from live data above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming portfolio analysis…"):
            _stream(api_key, SYS_PORTFOLIO_MANAGER, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("portfolio-manager")

# ─── TAB 9: STANLEY-DRUCKENMILLER ─────────────────────────────────────────
def _tab_druckenmiller(api_key: str) -> None:
    """Skill: stanley-druckenmiller-investment — Conviction score synthesis."""
    _tab_header(
        skill_name="stanley-druckenmiller-investment",
        color="#FF6B35",
        title="Druckenmiller Strategy Synthesizer — Conviction Score",
        description=(
            "Synthesizes breadth, uptrend ratio, market top risk, macro regime, "
            "momentum, and leadership quality into a single conviction score (0-100) "
            "with Druckenmiller pattern classification and exact allocation recommendation. "
            "Based on Druckenmiller's principle: aggressive when conviction is high, "
            "capital preservation when uncertain."
        ),
    )
    with st.form("druck_form"):
        portfolio_input = st.text_area(
            "Portfolio Holdings (TICKER:WEIGHT% optional, for position sizing context)",
            value="SPY:60\nTLT:25\nGLD:15",
            height=100,
        )
        extra_context = st.text_area(
            "Macro Thesis / Context",
            placeholder="e.g. Fed pivot expected in Q3. Inflation decelerating. Soft landing narrative dominant.",
            height=80,
        )
        submitted = st.form_submit_button("🏆 Run Druckenmiller Synthesizer", type="primary")
    if not submitted:
        return
    with st.spinner("Fetching all signal inputs…"):
        macro        = _fetch_macro()
        sector_data  = _fetch_sector_breadth()
        df_spy       = _fetch_history("SPY", years=1)
    uptrend_data = _compute_uptrend_score(sector_data)
    dist_days    = _compute_distribution_days(df_spy) if not df_spy.empty else 0
    # Approximate top detector score from distribution days + breadth
    top_score_est = min(100.0, dist_days * 15.0 + max(0.0, 70.0 - uptrend_data["score"]))
    conviction   = _compute_conviction(
        uptrend_score=uptrend_data["score"],
        top_detector_score=top_score_est,
        distribution_days=dist_days,
        macro_data=macro,
        sector_data=sector_data,
    )
    score   = conviction["score"]
    pattern = conviction["pattern"]
    alloc   = conviction["allocation"]
    # Color coding
    conv_color = (
        "#00FF88" if score >= 70.0
        else "#FFD700" if score >= 55.0
        else "#FF9800" if score >= 40.0
        else "#FF5252"
    )
    st.markdown(
        f"""
        <div style='background:#0d1a0d;border:2px solid {conv_color};border-radius:12px;
                    padding:22px 32px;margin-bottom:16px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;'>
                <div>
                    <p style='color:{conv_color};font-family:monospace;font-size:10px;
                              letter-spacing:2px;margin:0 0 4px 0;'>CONVICTION SCORE</p>
                    <p style='color:{conv_color};font-size:56px;font-weight:bold;
                              font-family:monospace;margin:0;'>{score}</p>
                </div>
                <div style='text-align:right;'>
                    <p style='color:#E8E0D0;font-size:18px;font-weight:bold;margin:0 0 6px 0;'>{pattern}</p>
                    <p style='color:{conv_color};font-size:14px;margin:0;'>{alloc}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    comps = conviction["components"]
    comp_display = [
        ("Breadth Health (25%)", "breadth_health"),
        ("Uptrend Ratio (20%)",  "uptrend_ratio"),
        ("Top Risk Inv. (20%)",  "top_risk_inverse"),
        ("Macro Regime (15%)",   "macro_regime"),
        ("Momentum (10%)",       "momentum"),
        ("Leadership (10%)",     "leadership_quality"),
    ]
    cols = st.columns(3)
    for i, (label, key) in enumerate(comp_display):
        with cols[i % 3]:
            val = comps.get(key, 0.0)
            st.metric(label, f"{val:.0f}/100")
    # Build data context
    vix_cur = macro.get("^VIX",  {}).get("current", 20.0)
    tnx_cur = macro.get("^TNX",  {}).get("current", 4.0)
    sp_1y   = macro.get("^GSPC", {}).get("1y_change", 0.0)
    user_content = (
        f"DRUCKENMILLER STRATEGY SYNTHESIZER DATA\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"CONVICTION SCORE: {score}/100 | Pattern: {pattern}\n"
        f"Recommended Allocation: {alloc}\n\n"
        f"COMPONENT SCORES:\n"
        + "\n".join(f"  {k.replace('_',' ').title()}: {comps.get(k,0):.0f}/100" for k in comps)
        + f"\n\nKEY SIGNAL INPUTS:\n"
        f"  VIX: {vix_cur:.1f}\n"
        f"  10Y Treasury: {tnx_cur:.2f}%\n"
        f"  S&P 500 1Y Return: {sp_1y:+.1f}%\n"
        f"  Uptrend Breadth: {uptrend_data['score']:.0f}/100 ({uptrend_data['zone']})\n"
        f"  Distribution Days (SPY, 25D): {dist_days}\n"
        f"  Cyclical vs Defensive: {uptrend_data['cyclical_1m']:+.1f}% vs {uptrend_data['defensive_1m']:+.1f}%\n\n"
        f"PORTFOLIO CONTEXT: {portfolio_input}\n"
        f"MACRO THESIS: {extra_context or 'None provided'}\n\n"
        f"Deliver the complete Druckenmiller Strategy Synthesis. "
        f"Confirm the conviction score, classify the pattern, and provide the single highest-conviction trade. "
        f"Derive all allocation guidance from the live signal data above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming Druckenmiller synthesis…"):
            _stream(api_key, SYS_DRUCKENMILLER, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("stanley-druckenmiller-investment")

# ─── TAB 10: UPTREND-ANALYZER ─────────────────────────────────────────────
def _tab_uptrend_analyzer(api_key: str) -> None:
    """Skill: uptrend-analyzer — Monty uptrend ratio dashboard + 5-component score."""
    _tab_header(
        skill_name="uptrend-analyzer",
        color="#00D2FF",
        title="Uptrend Analyzer — Monty Dashboard + 5-Component Score",
        description=(
            "Tracks uptrend ratio across all 11 GICS sectors — the percentage of US stocks "
            "above 200MA + 50MA + 20MA with positive 1-month performance. Generates a 0-100 "
            "composite score from 5 components (Breadth 30%, Participation 25%, Rotation 15%, "
            "Momentum 20%, Historical 10%) with sector heatmap and exposure guidance."
        ),
    )
    run_btn = st.button("🔭 Run Uptrend Analyzer", type="primary")
    if not run_btn:
        st.info("Click to fetch live sector uptrend data and compute the Monty composite score.")
        return
    with st.spinner("Fetching sector ETF data…"):
        sector_data = _fetch_sector_breadth()
    if not sector_data:
        st.error("Failed to fetch sector data.")
        return
    uptrend = _compute_uptrend_score(sector_data)
    score    = uptrend["score"]
    zone     = uptrend["zone"]
    exposure = uptrend["exposure"]
    zone_color = {
        "Strong Bull": "#00FF88", "Bull": "#00E676",
        "Neutral": "#FFD700", "Cautious": "#FF9800", "Bear": "#FF5252",
    }.get(zone, "#FFD700")
    # Gauge display
    st.markdown(
        f"""
        <div style='background:#000d1a;border:2px solid {zone_color};border-radius:12px;
                    padding:22px 32px;margin-bottom:16px;display:flex;
                    justify-content:space-between;align-items:center;flex-wrap:wrap;'>
            <div>
                <p style='color:{zone_color};font-family:monospace;font-size:10px;
                          letter-spacing:2px;margin:0 0 4px 0;'>UPTREND HEALTH SCORE</p>
                <p style='color:{zone_color};font-size:56px;font-weight:bold;
                          font-family:monospace;margin:0;'>{score}</p>
                <p style='color:#E8E0D0;font-size:15px;margin:4px 0 0 0;'>Zone: {zone}</p>
            </div>
            <div style='text-align:right;'>
                <p style='color:#B0A898;font-size:12px;font-family:monospace;margin:0 0 4px 0;'>EXPOSURE GUIDANCE</p>
                <p style='color:{zone_color};font-size:18px;font-weight:bold;margin:0;'>{exposure}</p>
                <p style='color:#8898A8;font-size:12px;margin:4px 0 0 0;'>
                    Cyclical {uptrend["cyclical_1m"]:+.1f}% vs Defensive {uptrend["defensive_1m"]:+.1f}% (1M)
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Component bars
    comps = uptrend["components"]
    comp_labels  = ["Breadth\n(30%)", "Participation\n(25%)", "Rotation\n(15%)", "Momentum\n(20%)", "Historical\n(10%)"]
    comp_keys    = ["breadth", "participation", "rotation", "momentum", "historical"]
    comp_values  = [comps.get(k, 0.0) for k in comp_keys]
    comp_colors  = ["#00FF88" if v >= 60 else "#FFD700" if v >= 40 else "#FF5252" for v in comp_values]
    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(
        x=comp_labels, y=comp_values,
        marker_color=comp_colors, marker_line_width=0,
        text=[f"{v:.0f}" for v in comp_values], textposition="outside",
        textfont=dict(color="#E8E0D0", size=12, family="monospace"),
    ))
    layout_c = _tv_layout(height=280, title="5-Component Score Breakdown")
    layout_c["yaxis"] = _tv_yaxis(fixed_range=True)
    layout_c["yaxis"]["range"] = [0, 110]
    layout_c["xaxis"] = {"gridcolor": "rgba(128,128,128,0.04)", "tickfont": {"color": "#8a8a8a", "size": 11}}
    layout_c["margin"] = {"l": 10, "r": 50, "t": 50, "b": 60}
    fig_comp.update_layout(**layout_c)
    st.plotly_chart(fig_comp, use_container_width=True, config=TV_CONFIG)
    # Sector table
    sector_rows = sorted(sector_data.items(), key=lambda x: x[1]["1m_return"], reverse=True)
    df_table = pd.DataFrame([{
        "Ticker": etf,
        "Sector": d["sector"],
        "1M Ret%": f"{d['1m_return']:+.1f}%",
        "3M Ret%": f"{d['3m_return']:+.1f}%",
        "vs MA50":  "↑" if d["above_ma50"]  else "↓",
        "vs MA200": "↑" if d["above_ma200"] else "↓",
    } for etf, d in sector_rows])
    st.dataframe(df_table, use_container_width=True, hide_index=True)
    # Build context for AI
    data_ctx = (
        f"UPTREND ANALYZER DATA — {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"COMPOSITE SCORE: {score}/100 | Zone: {zone} | Exposure: {exposure}\n"
        f"Above MA50: {uptrend['above_ma50_pct']:.1f}% | Above MA200: {uptrend['above_ma200_pct']:.1f}%\n"
        f"Cyclical 1M: {uptrend['cyclical_1m']:+.2f}% | Defensive 1M: {uptrend['defensive_1m']:+.2f}%\n\n"
        f"COMPONENT SCORES:\n"
        + "\n".join(f"  {k.title()}: {comps.get(k,0):.0f}/100" for k in comp_keys)
        + "\n\nSECTOR DETAIL (ranked by 1M return):\n"
        + "\n".join(
            f"  {etf} {d['sector']:<22} 1M:{d['1m_return']:+.1f}%  3M:{d['3m_return']:+.1f}%"
            for etf, d in sector_rows
        )
        + "\n\nDeliver the complete Uptrend Analyzer report with sector heatmap interpretation, "
        "active warning check (Late Cycle / High Spread / Divergence), momentum signal, "
        "and 3 specific tactical actions for the current breadth environment."
    )
    ph = st.empty()
    try:
        with st.spinner("Streaming uptrend analysis…"):
            _stream(api_key, SYS_UPTREND_ANALYZER, data_ctx, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("uptrend-analyzer")

# ─── TAB 11: US-MARKET-BUBBLE-DETECTOR ────────────────────────────────────
def _tab_bubble_detector(api_key: str) -> None:
    """Skill: us-market-bubble-detector — Minsky/Kindleberger bubble scoring."""
    _tab_header(
        skill_name="us-market-bubble-detector",
        color="#FF5252",
        title="Bubble Detector — Minsky/Kindleberger Framework v2.1",
        description=(
            "Evaluates US market bubble risk using mandatory quantitative data collection "
            "before any qualitative assessment. Scores 5 quantitative indicators (Put/Call, VIX "
            "percentile, breadth, volatility regime, margin debt YoY) plus qualitative adjustment. "
            "Provides position sizing guidance and specific hedge instruments."
        ),
    )
    with st.form("bubble_form"):
        st.markdown("**Phase 1: Quantitative Data Input (Required)**")
        c1, c2, c3 = st.columns(3)
        with c1:
            put_call  = st.number_input("CBOE Equity Put/Call Ratio", min_value=0.20, max_value=2.00, value=0.65, step=0.01,
                                         help="Current 5-day MA. Source: CBOE.")
            vix_level = st.number_input("VIX Level", min_value=5.0, max_value=100.0, value=16.0, step=0.1)
        with c2:
            vix_pct_3m  = st.number_input("VIX 3-Month Percentile (%)", min_value=0.0, max_value=100.0, value=25.0, step=1.0,
                                            help="Where current VIX sits in its 3-month distribution.")
            breadth_50  = st.number_input("% S&P 500 Stocks Above 50DMA", min_value=10.0, max_value=100.0, value=62.0, step=1.0)
        with c3:
            margin_yoy  = st.number_input("Margin Debt YoY % Change (blank=unknown)", min_value=-50.0, max_value=100.0, value=8.0, step=1.0)
            realized_vol = st.number_input("21-Day Realized Volatility (% annualized)", min_value=1.0, max_value=100.0, value=12.0, step=0.5)
        st.markdown("**Phase 2: Qualitative Context (for +0 to +3 points adjustment)**")
        qualitative_note = st.text_area(
            "Social / Narrative Phenomena (require measurable evidence to score)",
            placeholder="e.g. IPO volume up 40% YoY, retail margin accounts +35% YoY, mainstream media coverage extreme.",
            height=80,
        )
        submitted = st.form_submit_button("🫧 Run Bubble Detector", type="primary")
    if not submitted:
        return
    margin_val = margin_yoy if margin_yoy > -49.0 else None
    bubble = _compute_bubble_score(vix_level, vix_pct_3m, put_call, breadth_50, margin_val, realized_vol)
    score   = bubble["score"]
    phase   = bubble["phase"]
    color   = bubble["color"]
    details = bubble["details"]
    # Score display
    st.markdown(
        f"""
        <div style='background:#1a0000;border:2px solid {color};border-radius:12px;
                    padding:22px 32px;margin-bottom:16px;display:flex;
                    justify-content:space-between;align-items:center;flex-wrap:wrap;'>
            <div>
                <p style='color:{color};font-family:monospace;font-size:10px;
                          letter-spacing:2px;margin:0 0 4px 0;'>BUBBLE RISK SCORE (0-15 pts)</p>
                <p style='color:{color};font-size:56px;font-weight:bold;
                          font-family:monospace;margin:0;'>{score}/15</p>
            </div>
            <div style='text-align:right;'>
                <p style='color:{color};font-size:22px;font-weight:bold;margin:0;'>{phase}</p>
                <p style='color:#8898A8;font-size:12px;margin:4px 0 0 0;'>
                    Thresholds: Normal ≤3 | Watch 4-5 | Warning 6-7 | Elevated 8-9 | Critical 10+
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Component scores
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Put/Call (0-2pts)", f"{details.get('pc_pts',0)}")
    with c2:
        st.metric("VIX Pct (0-2pts)", f"{details.get('vix_pts',0)}")
    with c3:
        st.metric("Breadth (0-1pt)", f"{details.get('breadth_pts',0)}")
    with c4:
        st.metric("Vol Regime (0-1pt)", f"{details.get('vol_pts',0)}")
    with c5:
        st.metric("Margin Debt (0-2pts)", f"{details.get('margin_pts',0)}")
    user_content = (
        f"BUBBLE DETECTOR DATA — Minsky/Kindleberger v2.1\n"
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"PHASE 1 — QUANTITATIVE INPUTS:\n"
        f"  Put/Call Ratio: {put_call:.2f} → {details.get('pc_pts',0)}/2 pts\n"
        f"    (Threshold: <0.55=2pts, 0.55-0.65=1pt)\n"
        f"  VIX Level: {vix_level:.1f} | 3M Percentile: {vix_pct_3m:.0f}% → {details.get('vix_pts',0)}/2 pts\n"
        f"    (Threshold: <10th pct=2pts, <20th pct=1pt)\n"
        f"  S&P 500 Breadth (50DMA): {breadth_50:.0f}% → {details.get('breadth_pts',0)}/1 pt\n"
        f"    (Threshold: >75%=1pt overheated)\n"
        f"  21-Day Realized Vol: {realized_vol:.1f}% → {details.get('vol_pts',0)}/1 pt\n"
        f"    (Threshold: <8% annualized=extreme compression=1pt)\n"
        f"  Margin Debt YoY: {margin_yoy:.1f}% → {details.get('margin_pts',0)}/2 pts\n"
        f"    (Threshold: >25%=2pts, 10-25%=1pt)\n\n"
        f"PHASE 1 SUBTOTAL: {score}/10 pts\n\n"
        f"PHASE 2 — QUALITATIVE CONTEXT (max +3 pts, requires evidence):\n"
        f"  {qualitative_note or 'None provided'}\n\n"
        f"COMPOSITE SCORE: {score}/15+ | Phase: {phase}\n\n"
        f"Deliver the complete bubble detection report. Apply Phase 2 qualitative scoring ONLY "
        f"if the user provided specific, measurable evidence. "
        f"Include position sizing guidance and specific hedge instruments. "
        f"Strictly prevent confirmation bias — state clearly when data is insufficient to score qualitative points."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming bubble detection analysis…"):
            _stream(api_key, SYS_BUBBLE_DETECTOR, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("us-market-bubble-detector")

# ─── TAB 12: VALUE-DIVIDEND-SCREENER ──────────────────────────────────────
def _tab_value_screener(api_key: str) -> None:
    """Skill: value-dividend-screener — P/E<20, P/B<2, Yield≥3%, growth screen."""
    _tab_header(
        skill_name="value-dividend-screener",
        color="#FFD700",
        title="Value & Dividend Screener — P/E<20 · P/B<2 · Yield≥3%",
        description=(
            "Screens a universe of quality dividend stocks using the two-stage methodology: "
            "P/E < 20, P/B < 2, Dividend Yield ≥ 3%, consistent revenue/EPS growth. "
            "Fetches live fundamentals via yfinance, ranks by composite quality score, "
            "and delivers income projections + DRIP compounding analysis."
        ),
    )
    with st.form("value_form"):
        c1, c2 = st.columns(2)
        with c1:
            custom_tickers = st.text_area(
                "Custom Universe (optional — add tickers, one per line)",
                placeholder="Leave empty to use built-in dividend universe\nor add specific tickers to include.",
                height=100,
            )
            invest_amount = st.number_input(
                "Investment Amount (USD)", min_value=1_000, max_value=100_000_000,
                value=100_000, step=5_000,
            )
        with c2:
            income_goal  = st.number_input("Monthly Income Goal (0 if no target)", min_value=0, max_value=1_000_000, value=500, step=100)
            account_type = st.selectbox("Account Type", ["US Taxable", "US IRA/Roth", "US 401K", "Swedish ISK", "Swedish KF", "Other"])
            tax_bracket  = st.selectbox("Tax Bracket", ["0-20%", "21-30%", "31-40%", "41-50%", "50%+"], index=2)
            screen_prefs = st.text_area("Screening Preferences (optional)", placeholder="e.g. No financials. REITs OK. Focus on dividend growth aristocrats.", height=70)
        submitted = st.form_submit_button("💰 Run Value/Dividend Screen", type="primary")
    if not submitted:
        return
    # Build universe
    universe = list(DIVIDEND_UNIVERSE)
    if custom_tickers.strip():
        custom = [t.strip().upper() for t in custom_tickers.strip().splitlines() if t.strip()]
        for t in custom:
            if t not in universe:
                universe.append(t)
    screened: Dict[str, Dict[str, Any]] = {}
    bar = st.progress(0, text="Fetching dividend data…")
    for i, tkr in enumerate(universe):
        bar.progress((i + 1) / len(universe), text=f"Fetching {tkr}…")
        info = _fetch_info(tkr)
        if info:
            screened[tkr] = info
        time.sleep(0.06)
    bar.empty()
    # Apply screens
    passed: Dict[str, Dict[str, Any]] = {}
    for tkr, info in screened.items():
        pe    = info.get("pe_ratio")
        pb    = info.get("pb_ratio")
        div_y = info.get("dividend_yield")
        if pe is None or pb is None or div_y is None:
            continue
        if (float(pe) < VALUE_PE_MAX
                and float(pb) < VALUE_PB_MAX
                and float(div_y) * 100.0 >= VALUE_DIV_MIN):
            passed[tkr] = info
    if not passed:
        st.warning(
            f"No stocks passed all 3 screens (P/E<{VALUE_PE_MAX}, P/B<{VALUE_PB_MAX}, "
            f"Yield≥{VALUE_DIV_MIN}%) from the fetched universe. "
            "Try adding custom tickers or relaxing criteria via context."
        )
    else:
        st.success(f"✓ {len(passed)}/{len(screened)} stocks passed all 3 screens")
    # Show table of passed stocks
    if passed:
        rows = []
        for tkr, d in passed.items():
            rows.append({
                "Ticker": tkr,
                "Name":     (d.get("name") or tkr)[:25],
                "Sector":   (d.get("sector") or "N/A")[:18],
                "P/E":      _flt(d.get("pe_ratio"), ".1f"),
                "P/B":      _flt(d.get("pb_ratio"), ".2f"),
                "Yield":    _pct(d.get("dividend_yield")),
                "Payout%":  _pct(d.get("payout_ratio")),
                "RevGrw":   _pct(d.get("revenue_growth")),
                "ROE":      _pct(d.get("roe")),
                "FCF":      _bn(d.get("free_cashflow")),
                "MktCap":   _bn(d.get("market_cap")),
            })
        df_screen = pd.DataFrame(rows)
        st.dataframe(df_screen, use_container_width=True, hide_index=True)
    # Build full universe string for AI (all fetched, including those that failed screens)
    lines = [
        f"VALUE/DIVIDEND SCREENER RESULTS — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Universe: {len(screened)} stocks | Passed screens: {len(passed)}",
        f"Screen criteria: P/E<{VALUE_PE_MAX}, P/B<{VALUE_PB_MAX}, Yield≥{VALUE_DIV_MIN}%", "",
        f"{'Ticker':<10} {'Name':<26} {'Sector':<18} "
        f"{'P/E':>6} {'P/B':>5} {'Yield':>6} {'Payout':>7} {'FCF':>9} {'ROE':>7} {'RevGrw':>7}",
        "-" * 110,
    ]
    for tkr, d in screened.items():
        flag = " ✓" if tkr in passed else ""
        lines.append(
            f"{tkr:<10} {(d.get('name') or tkr)[:24]:<26} "
            f"{(d.get('sector') or 'N/A')[:16]:<18} "
            f"{_flt(d.get('pe_ratio'), '.1f'):>6} "
            f"{_flt(d.get('pb_ratio'), '.2f'):>5} "
            f"{_pct(d.get('dividend_yield')):>6} "
            f"{_pct(d.get('payout_ratio')):>7} "
            f"{_bn(d.get('free_cashflow')):>9} "
            f"{_pct(d.get('roe')):>7} "
            f"{_pct(d.get('revenue_growth')):>7}{flag}"
        )
    user_content = (
        "\n".join(lines) + f"\n\n"
        f"INVESTOR SITUATION:\n"
        f"  Investment Amount: ${invest_amount:,}\n"
        f"  Monthly Income Goal: ${income_goal:,}\n"
        f"  Account Type: {account_type} | Tax Bracket: {tax_bracket}\n"
        f"  Preferences: {screen_prefs or 'None'}\n\n"
        f"Stocks marked ✓ passed all 3 screens. Focus your top-10 ranking on those, "
        f"but you may include near-miss stocks with exceptional quality. "
        f"Show income projections and DRIP compounding. All yields from live data above."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming value/dividend screen analysis…"):
            _stream(api_key, SYS_VALUE_SCREENER, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("value-dividend-screener")

# ─── TAB 13: EARNINGS-TRADE-ANALYZER ──────────────────────────────────────
def _tab_earnings_analyzer(api_key: str) -> None:
    """Skill: earnings-trade-analyzer — Post-earnings 5-factor scoring + PEAD."""
    _tab_header(
        skill_name="earnings-trade-analyzer",
        color="#E040FB",
        title="Earnings Trade Analyzer — 5-Factor PEAD Scoring",
        description=(
            "Scores post-earnings stocks on 5 factors: Gap Size (30%), Pre-Earnings Trend (20%), "
            "Volume Ratio (20%), MA200 Position (15%), MA50 Position (15%). Assigns A/B/C/D grades. "
            "Grade A (≥85) = high-conviction PEAD entry. Grade B (70-84) = wait for confirmation. "
            "All scores computed from live yfinance data."
        ),
    )
    with st.form("earnings_form"):
        tickers_input = st.text_area(
            "Post-Earnings Tickers (one per line, with approximate gap % if known)",
            value="NVDA:+14\nMETA:+8\nAMZN:+5\nGOOGL:-3\nMSFT:+4",
            height=160,
            help="Format: TICKER or TICKER:GAP% (e.g. NVDA:+14 means +14% earnings gap)"
        )
        c1, c2 = st.columns(2)
        with c1:
            min_market_cap = st.selectbox(
                "Minimum Market Cap",
                ["Any", "Micro (>$50M)", "Small (>$300M)", "Mid (>$2B)", "Large (>$10B)", "Mega (>$100B)"],
                index=3,
            )
        with c2:
            market_context = st.text_area(
                "Market Context (optional)",
                placeholder="e.g. Broad market in uptrend, breadth healthy. Top detector score 25.",
                height=80,
            )
        submitted = st.form_submit_button("📋 Run Earnings Analysis", type="primary")
    if not submitted:
        return
    # Parse tickers and gaps
    ticker_gaps: Dict[str, float] = {}
    for line in tickers_input.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.split(":")
            tkr   = parts[0].strip().upper()
            try:
                gap = float(parts[1].strip().replace("%", ""))
            except ValueError:
                gap = 0.0
        else:
            tkr = line.upper()
            gap = 0.0
        if tkr:
            ticker_gaps[tkr] = gap
    if not ticker_gaps:
        st.error("No valid tickers parsed.")
        return
    scores: List[Dict[str, Any]] = []
    bar = st.progress(0, text="Scoring earnings setups…")
    for i, (tkr, gap) in enumerate(ticker_gaps.items()):
        bar.progress((i + 1) / len(ticker_gaps), text=f"Scoring {tkr}…")
        df = _fetch_history(tkr, years=1)
        if not df.empty:
            result = _score_earnings_trade(tkr, df, gap)
            # Fetch additional info for context
            info = _fetch_info(tkr)
            result["name"]     = (info.get("name") or tkr)[:30]
            result["sector"]   = info.get("sector", "N/A")
            result["price"]    = _flt(info.get("current_price"), ".2f")
            result["gap_pct"]  = gap
            scores.append(result)
        time.sleep(0.05)
    bar.empty()
    if not scores:
        st.error("Could not score any tickers — no price data available.")
        return
    scores.sort(key=lambda x: x["score"], reverse=True)
    # Grade distribution
    grades = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scores:
        grades[s["grade"]] += 1
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Grade A (≥85)", grades["A"], delta="Strong Entry" if grades["A"] > 0 else None)
    with c2:
        st.metric("Grade B (70-84)", grades["B"], delta="Watch" if grades["B"] > 0 else None)
    with c3:
        st.metric("Grade C (55-69)", grades["C"])
    with c4:
        st.metric("Grade D (<55)", grades["D"])
    # Leaderboard chart
    tickers_sorted = [s["ticker"] for s in scores]
    scores_sorted  = [s["score"] for s in scores]
    grade_colors   = {"A": "#00FF88", "B": "#FFD700", "C": "#FF9800", "D": "#FF5252"}
    bar_colors     = [grade_colors.get(s["grade"], "#8898A8") for s in scores]
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=tickers_sorted, y=scores_sorted,
        marker_color=bar_colors, marker_line_width=0,
        text=[f"{s:.0f}\n{g}" for s, g in zip(scores_sorted, [s["grade"] for s in scores])],
        textposition="outside",
        textfont=dict(color="#E8E0D0", size=11, family="monospace"),
    ))
    layout_e = _tv_layout(height=320, title="Post-Earnings 5-Factor Scores")
    layout_e["yaxis"] = _tv_yaxis(fixed_range=True)
    layout_e["yaxis"]["range"] = [0, 115]
    layout_e["xaxis"] = {"gridcolor": "rgba(128,128,128,0.04)", "tickfont": {"color": "#8a8a8a", "size": 11}}
    layout_e["margin"] = {"l": 10, "r": 50, "t": 50, "b": 50}
    fig_bar.update_layout(**layout_e)
    st.plotly_chart(fig_bar, use_container_width=True, config=TV_CONFIG)
    # Detailed table
    rows = []
    for s in scores:
        comps = s.get("components", {})
        rows.append({
            "Ticker":  s["ticker"],
            "Name":    s.get("name", ""),
            "Grade":   s["grade"],
            "Score":   s["score"],
            "Gap%":    f"{s.get('gap_pct', 0):+.1f}%",
            "Pre-Trend": f"{comps.get('pre_trend', 0):.0f}",
            "Vol Ratio": f"{comps.get('volume_ratio', 0):.0f}",
            "vs MA200":  f"{comps.get('ma200_position', 0):.0f}",
            "vs MA50":   f"{comps.get('ma50_position', 0):.0f}",
            "Price":   f"${s.get('price', 'N/A')}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    # Build AI context
    score_lines = [
        f"EARNINGS TRADE ANALYZER RESULTS — {datetime.datetime.now().strftime('%Y-%m-%d')}",
        f"Stocks analyzed: {len(scores)} | Grade A: {grades['A']} | B: {grades['B']} | C: {grades['C']} | D: {grades['D']}",
        f"Min market cap filter: {min_market_cap}", "",
    ]
    for s in scores:
        comps = s.get("components", {})
        score_lines.append(
            f"{s['ticker']:<8} {s['name'][:28]:<30} Grade:{s['grade']}  Score:{s['score']:.0f}  "
            f"Gap:{s.get('gap_pct',0):+.1f}%  "
            f"GapScore:{comps.get('gap_size',0):.0f}  PreTrend:{comps.get('pre_trend',0):.0f}  "
            f"VolRatio:{comps.get('volume_ratio',0):.0f}  MA200:{comps.get('ma200_position',0):.0f}  "
            f"MA50:{comps.get('ma50_position',0):.0f}"
        )
    user_content = (
        "\n".join(score_lines) + f"\n\n"
        f"MARKET CONTEXT: {market_context or 'Not specified'}\n\n"
        f"Deliver the complete Earnings Trade Analyzer report. For each Grade A and B setup, "
        f"provide specific entry guidance, risk management, and PEAD momentum thesis. "
        f"Contextualize all setups against the market environment provided."
    )
    st.markdown("---")
    ph = st.empty()
    try:
        with st.spinner("Streaming earnings analysis…"):
            _stream(api_key, SYS_EARNINGS_ANALYZER, user_content, ph)
    except RuntimeError as e:
        st.error(str(e))
        return
    _analysis_footer("earnings-trade-analyzer")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def main() -> None:
    """
    Main entry point for the Trading Intelligence Hub.
    Renders 13 tabs — one per skill — with full live data + Groq AI analysis.
    All 13 skills integrated 100%:
      us-stock-analysis, technical-analyst, market-environment-analysis,
      breadth-chart-analyst, market-news-analyst, market-top-detector,
      options-strategy-advisor, portfolio-manager, stanley-druckenmiller-investment,
      uptrend-analyzer, us-market-bubble-detector, value-dividend-screener,
      earnings-trade-analyzer.
    """
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)
    # ── PAGE HEADER ───────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='background:linear-gradient(135deg,#001a33 0%,#000d1a 50%,#0a001a 100%);
                    border:1px solid rgba(0,180,255,0.18);border-radius:12px;
                    padding:28px 36px;margin-bottom:20px;'>
            <div style='margin-bottom:14px;'>
                <span style='background:rgba(0,180,255,0.12);color:#00B4FF;
                             font-size:10px;font-family:monospace;font-weight:bold;
                             padding:4px 14px;border-radius:3px;
                             border:1px solid rgba(0,180,255,0.28);letter-spacing:2px;'>
                    13 SKILLS · LIVE DATA · LLAMA 3.3 70B · TRADINGVIEW-QUALITY UI
                </span>
            </div>
            <h1 style='color:#F5ECD7;font-family:"Times New Roman",serif;
                       font-size:32px;font-weight:bold;margin:0 0 10px 0;'>
                Trading Intelligence Hub
            </h1>
            <p style='color:rgba(255,215,0,0.90);font-family:monospace;font-size:11px;
                      margin:0 0 12px 0;letter-spacing:1.5px;'>
                ◆ ALL 13 SKILLS INTEGRATED · ZERO QUALITY LOSS · INSTITUTIONAL GRADE
            </p>
            <p style='color:#7888A0;font-size:14px;line-height:1.85;margin:0;
                      font-family:"Times New Roman",serif;max-width:800px;'>
                Each tab is powered by a dedicated professional-grade skill: stock analysis,
                chart patterns, global markets, breadth dashboard, news impact, market top detection,
                options strategy, portfolio risk, Druckenmiller conviction, uptrend ratios,
                bubble detection, value screening, and earnings momentum. All using live market data.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # ── API KEY VALIDATION ────────────────────────────────────────────────
    api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    if not api_key:
        st.error(
            "**GROQ_API_KEY not found.** Add it to your `.env` file:\n\n"
            "```\nGROQ_API_KEY=gsk_...\n```\n\n"
            "Get a free key at [console.groq.com](https://console.groq.com/keys)."
        )
        return
    if not _GROQ_AVAILABLE:
        st.error("**groq package not installed.** Run: `pip install groq`")
        return
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("AI Model",  "LLaMA 3.3 70B")
    with col2:
        st.metric("Skills",    "13 Active")
    with col3:
        st.metric("Data",      "Live yfinance")
    with col4:
        st.metric("Cost",      "Free (Groq)")
    st.markdown("---")
    # ── 13 SKILL TABS ─────────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 Stock Intelligence",
        "📈 Chart Analyst",
        "🌍 Market Environment",
        "📡 Breadth Dashboard",
        "📰 News Impact",
        "⚠️ Top Detector",
        "💡 Options Advisor",
        "🛡️ Portfolio Manager",
        "🏆 Druckenmiller",
        "🔭 Uptrend Analyzer",
        "🫧 Bubble Detector",
        "💰 Value Screener",
        "📋 Earnings Analyzer",
    ])
    with tabs[0]:
        _tab_stock_intelligence(api_key)
    with tabs[1]:
        _tab_chart_analyst(api_key)
    with tabs[2]:
        _tab_market_environment(api_key)
    with tabs[3]:
        _tab_breadth_dashboard(api_key)
    with tabs[4]:
        _tab_market_news(api_key)
    with tabs[5]:
        _tab_market_top(api_key)
    with tabs[6]:
        _tab_options_advisor(api_key)
    with tabs[7]:
        _tab_portfolio_manager(api_key)
    with tabs[8]:
        _tab_druckenmiller(api_key)
    with tabs[9]:
        _tab_uptrend_analyzer(api_key)
    with tabs[10]:
        _tab_bubble_detector(api_key)
    with tabs[11]:
        _tab_value_screener(api_key)
    with tabs[12]:
        _tab_earnings_analyzer(api_key)
    # ── GLOBAL DISCLAIMER ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        """
        <div style='background:rgba(255,82,82,0.06);
                    border:1px solid rgba(255,82,82,0.18);
                    border-radius:6px;padding:14px 20px;'>
            <p style='color:rgba(255,255,255,0.38);font-size:10px;
                      font-family:monospace;margin:0;line-height:1.8;'>
                ⚠ LEGAL DISCLAIMER: This hub uses LLaMA 3.3 70B via Groq and live yfinance market data.
                Skills integrated: us-stock-analysis, technical-analyst, market-environment-analysis,
                breadth-chart-analyst, market-news-analyst, market-top-detector, options-strategy-advisor,
                portfolio-manager, stanley-druckenmiller-investment, uptrend-analyzer,
                us-market-bubble-detector, value-dividend-screener, earnings-trade-analyzer.
                None of the institutions, authors, or methodologies referenced endorse this platform.
                NOT financial advice. Verify all figures independently. Trading involves substantial risk.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()