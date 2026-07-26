# pages/analyst_intelligence_ui.py
# Wall Street Analyst Intelligence Suite — Live Data + Groq AI (Free)
#
# WHAT THIS PAGE DOES:
#   Each of the 10 frameworks:
#     1. Collects your inputs via a Streamlit form
#     2. Fetches LIVE financial data from yfinance / OpenBB
#     3. Formats that data into a structured context document
#     4. Calls the Groq API (streaming) with an institutional
#        system prompt + your live data + your profile
#     5. Streams the full analysis directly into the page
#
# SETUP REQUIRED:
#   1. pip install groq  (already installed if Copilot page works)
#   2. Add GROQ_API_KEY=gsk_... to your .env file
#      Get a free key at: https://console.groq.com/keys
#
# OPENBB: obb.equity.price.historical() used for price history.
#         All fundamentals use yfinance direct (more reliable for
#         Swedish .ST tickers and statement data).
#
# NO st.set_page_config() — called once only in app.py per project rule.
#
# <- FIXED [groq_migration]: Anthropic SDK replaced with Groq SDK (free tier).
#    _stream_analysis() rewritten to use groq.Groq streaming completions.
#    GROQ_MODEL constant replaces ANTHROPIC_MODEL.
#    All 10 analysis frameworks preserved without change.
# <- NEW [horizon_expansion]: Goldman Sachs tab — 4 sub-year horizons added
#    to Investment Time Horizon selectbox (1 Week, 1 Month, 3 Months, 6 Months).
#    All original 4 options preserved. Zero deletions.
# <- NEW [horizon_expansion]: BlackRock tab — Investment Time Horizon slider
#    replaced with selectbox covering sub-year and multi-year options.
#    All prior slider values (1–50 years) preserved as selectable entries.
import datetime
import logging
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import streamlit as st
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from translations import t, inject_rtl_css  # <- NEW [i18n]
import yfinance as yf

# ── Project root on sys.path ───────────────────────────────────────────────
_PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── OpenBB (optional fallback for price history) ──────────────────────────
try:
    from openbb import obb as _obb
    _OBB_AVAILABLE: bool = True
except ImportError:
    _OBB_AVAILABLE = False

# <- FIXED [groq_migration]: Groq SDK replaces Anthropic SDK.
#    groq package is already present in the project (used by Copilot).
try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE: bool = True
except ImportError:
    _GROQ_AVAILABLE = False

logger = logging.getLogger("AnalystIntelligenceUI")

# ─── CONSTANTS ─────────────────────────────────────────────────────────────
# <- FIXED [groq_migration]: GROQ_MODEL replaces ANTHROPIC_MODEL.
#    llama-3.3-70b-versatile is free on Groq and handles long-form
#    structured financial analysis with full instruction following.
GROQ_MODEL: str  = "llama-3.3-70b-versatile"
MAX_TOKENS:  int = 4096
CACHE_TTL:   int = 300  # 5 minutes

# <- NEW [horizon_expansion]: Goldman Sachs Investment Time Horizon options.
#    Sub-year options prepended. Original 4 options preserved exactly.
GOLDMAN_TIME_HORIZONS: List[str] = [
    "1 Week",
    "1 Month",
    "3 Months",
    "6 Months",
    "Short-term (< 1 year)",
    "Medium-term (1–3 years)",
    "Long-term (3–10 years)",
    "Very Long-term (10+ years)",
]

# <- NEW [horizon_expansion]: BlackRock Investment Time Horizon options.
#    Sub-year options added. All prior slider values preserved as entries.
BLACKROCK_TIME_HORIZONS: List[str] = [
    "1 Week",
    "1 Month",
    "3 Months",
    "6 Months",
    "1 Year",
    "2 Years",
    "3 Years",
    "5 Years",
    "7 Years",
    "10 Years",
    "15 Years",
    "20 Years",
    "25 Years",
    "30 Years",
    "40 Years",
    "50 Years",
]

# Swedish OMX Stockholm universe (yfinance .ST suffix)
SWEDISH_UNIVERSE: Dict[str, str] = {
    "VOLV-B.ST":   "Volvo AB",
    "ABB.ST":      "ABB Ltd",
    "HM-B.ST":     "H&M Group",
    "ERIC-B.ST":   "Ericsson B",
    "ATCO-B.ST":   "Atlas Copco B",
    "INVE-B.ST":   "Investor AB",
    "SAND.ST":     "Sandvik",
    "NDA-SE.ST":   "Nordea Bank",
    "EVO.ST":      "Evolution AB",
    "SWED-A.ST":   "Swedbank A",
    "ALFA.ST":     "Alfa Laval",
    "SKF-B.ST":    "SKF B",
    "SEB-A.ST":    "SEB A",
    "HEXA-B.ST":   "Hexagon B",
    "ESSITY-B.ST": "Essity B",
}

# International blue-chip universe
GLOBAL_UNIVERSE: Dict[str, str] = {
    "AAPL":      "Apple Inc",
    "MSFT":      "Microsoft Corp",
    "NVDA":      "NVIDIA Corp",
    "GOOGL":     "Alphabet Inc",
    "AMZN":      "Amazon.com",
    "META":      "Meta Platforms",
    "BRK-B":     "Berkshire Hathaway",
    "JPM":       "JPMorgan Chase",
    "JNJ":       "Johnson & Johnson",
    "V":         "Visa Inc",
    "PG":        "Procter & Gamble",
    "NOVO-B.CO": "Novo Nordisk",
    "ASML.AS":   "ASML Holding",
    "SAP":       "SAP SE",
    "NESN.SW":   "Nestlé SA",
}

# Dividend-focused universe for Framework 7
DIVIDEND_UNIVERSE: Dict[str, str] = {
    "NDA-SE.ST": "Nordea Bank",
    "INVE-B.ST": "Investor AB",
    "SWED-A.ST": "Swedbank",
    "SEB-A.ST":  "SEB",
    "VOLV-B.ST": "Volvo AB",
    "JNJ":       "Johnson & Johnson",
    "PG":        "Procter & Gamble",
    "KO":        "Coca-Cola",
    "PEP":       "PepsiCo",
    "MCD":       "McDonald's",
    "MMM":       "3M Company",
    "O":         "Realty Income",
    "VZ":        "Verizon",
    "XOM":       "ExxonMobil",
    "CVX":       "Chevron",
    "ABT":       "Abbott Labs",
    "ABBV":      "AbbVie",
    "MO":        "Altria Group",
    "NOVO-B.CO": "Novo Nordisk",
    "T":         "AT&T",
}

# Macro proxy tickers
MACRO_TICKERS: Dict[str, str] = {
    "^TNX":      "US 10-Year Treasury Yield",
    "^IRX":      "US 3-Month T-Bill Rate",
    "^VIX":      "CBOE VIX Volatility Index",
    "DX-Y.NYB":  "US Dollar Index (DXY)",
    "GLD":       "Gold ETF (SPDR)",
    "TLT":       "20Y Treasury Bond ETF",
    "^GSPC":     "S&P 500 Index",
    "^STOXX50E": "Euro Stoxx 50",
    "^OMX":      "OMX Stockholm 30",
    "CL=F":      "Crude Oil Futures",
}

# ─── GLOBAL TYPOGRAPHY CSS ─────────────────────────────────────────────────
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
    font-size:20px !important; font-weight:bold !important;
    color:#F5ECD7 !important;
}
[data-testid="stMetricDelta"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:14px !important;
}
.stCaption,[data-testid="stCaptionContainer"] p,small,.caption {
    font-family:'Times New Roman',Times,serif !important;
    font-size:14px !important; color:#B0A898 !important;
    line-height:1.6 !important;
}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,[data-testid="stSidebar"] div {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family:'Times New Roman',Times,serif !important;
    font-size:18px !important; color:#F5ECD7 !important;
}
[data-testid="stTextInput"] input,[data-testid="stSelectbox"] div,
[data-testid="stNumberInput"] input,textarea {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
    border-color:rgba(0,229,255,0.20) !important;
    font-family:'Times New Roman',Times,serif !important;
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
    font-size:16px !important; color:#E8E0D0 !important;
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
    font-size:16px !important; line-height:1.75 !important;
    color:#E8E0D0 !important;
}
[data-testid="stExpander"] {
    background-color:#080f1a !important;
    border:1px solid rgba(0,229,255,0.10) !important;
    border-radius:6px !important;
}
[data-testid="stExpander"] summary {
    color:#C8C0B0 !important;
    font-family:'Times New Roman',Times,serif !important;
}
[data-testid="stChatInput"] textarea,[data-testid="stChatMessage"] p {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important;
    line-height:1.75 !important;
}
[data-testid="stChatInput"] { background-color:#0d1f33 !important; }
[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label,
[data-testid="stSlider"] label,[data-testid="stCheckbox"] label,
[data-testid="stMultiSelect"] label {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
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
</style>
"""

# ─── SYSTEM PROMPTS ────────────────────────────────────────────────────────
SYSTEM_PROMPT_GOLDMAN: str = """You are a senior equity analyst at Goldman Sachs with 20 years of experience in global equity research, screening stocks for ultra-high-net-worth clients. You have been given LIVE market data fetched in real time.
TASK: Deliver a Goldman Sachs-quality equity research screening report.
MANDATORY OUTPUT STRUCTURE:
1. EXECUTIVE SUMMARY (3 sentences: market context, screening thesis, key finding)
2. TOP 10 PICKS — for each stock:
   - Ticker, Company, Current Price, Sector
   - P/E Analysis: actual P/E vs estimated sector average (derive sector avg from the data set)
   - Revenue Growth: trend assessment based on provided revenue_growth field
   - Debt/Equity: risk assessment — note anything above 2.0x as elevated
   - Dividend: yield, sustainability score 1-5 (5=very safe), payout ratio flag
   - Competitive Moat: WEAK / MODERATE / STRONG with one-sentence justification
   - 12-Month Bull Target: derive as current_price × (1 + justified upside %)
   - 12-Month Bear Target: derive as current_price × (1 - justified downside %)
   - Risk Rating: 1–10 (1=very safe, 10=highly speculative) with reasoning
   - Entry Zone: support level derived from 52-week range
   - Stop-Loss: risk management level derived from 52-week low and beta
3. SUMMARY COMPARISON TABLE (markdown table: all 10 picks × key metrics)
4. PORTFOLIO CONSTRUCTION NOTE: suggested position sizing for stated amount
CRITICAL RULES:
- ALL price targets must be derived from the live data ratios. Show your methodology.
- NEVER fabricate financial figures. If data shows N/A for a field, state it and work around it.
- Include at least 4 Swedish (OMX) stocks if they are in the data set.
- Tailor every recommendation to the stated risk tolerance and time horizon."""

SYSTEM_PROMPT_MORGAN_STANLEY: str = """You are a VP-level investment banker at Morgan Stanley who builds DCF valuation models for Fortune 500 M&A transactions. You have been given LIVE financial statement data for a specific company.
TASK: Build a complete Morgan Stanley-quality DCF valuation memo.
MANDATORY OUTPUT STRUCTURE:
1. VALUATION MEMO HEADER: Company, date, analyst (you), current price, shares outstanding
2. HISTORICAL PERFORMANCE ANALYSIS: Derive revenue CAGR, margin trends, FCF conversion from the provided statements
3. 5-YEAR REVENUE PROJECTIONS: Three scenarios (Bear/Base/Bull) with stated growth assumptions derived from historical trends
4. FREE CASH FLOW MODEL: Year-by-year FCF = EBIT × (1-tax rate) + D&A - CapEx - ΔWorking Capital. Show all math.
5. WACC CALCULATION: Use the provided beta. State your risk-free rate assumption (current 10Y yield context). CAPM for cost of equity + capital structure for WACC.
6. TERMINAL VALUE: Both methods:
   - Exit Multiple: EV/EBITDA multiple × Year 5 EBITDA
   - Perpetuity Growth: FCF₅ × (1+g) / (WACC - g) — state your g assumption
7. SENSITIVITY TABLE: 3×3 grid — three WACC rates × three terminal growth rates → fair value per share
8. VERDICT: Undervalued / Fairly Valued / Overvalued — with margin of safety calculation
9. MODEL RISK FACTORS: Top 3 assumptions that if wrong would invalidate the model
ALL NUMBERS must be derived from the provided financial data. Show every formula step. Format tables in clean markdown."""

SYSTEM_PROMPT_BRIDGEWATER: str = """You are a senior risk analyst at Bridgewater Associates, trained in Ray Dalio's All-Weather principles, radical transparency, and balanced portfolio construction. You have been given LIVE portfolio data including correlation analysis computed from real price history.
TASK: Deliver a Bridgewater-quality portfolio risk management report.
MANDATORY OUTPUT STRUCTURE:
1. PORTFOLIO RISK DASHBOARD: Single-view summary of top 3 risk concerns
2. CORRELATION ANALYSIS: Interpret the provided correlation matrix. Flag pairs >0.70 as risk clusters. Identify the 2 highest-risk concentration pairs.
3. CONCENTRATION RISK: Sector breakdown, geographic breakdown, single-stock limit analysis (flag any position >25%)
4. VOLATILITY PROFILE: Individual position volatility from the data; weighted portfolio volatility estimate
5. INTEREST RATE SENSITIVITY: Classify each holding as rate-sensitive, rate-neutral, or rate-beneficiary
6. RECESSION STRESS TEST: Estimate portfolio drawdown in a 30% equity market decline using provided betas
7. LIQUIDITY RISK RATINGS: Rate each holding 1–5 (1=daily liquid, 5=illiquid) based on market cap and sector
8. POSITION SIZING RECOMMENDATIONS: Use the 1/volatility weighting approach. Suggest rebalanced weights.
9. TAIL RISK SCENARIOS: 2 black swan scenarios specific to this portfolio's exposures with estimated impact
10. HEDGING STRATEGIES: 3 specific hedges (instruments, sizing rationale, cost estimate)
11. REBALANCING PLAN: Exact target allocations in percentage format.
Base ALL risk metrics on the provided data. State clearly when you are making a judgment vs deriving from data."""

SYSTEM_PROMPT_JPMORGAN: str = """You are a senior equity research analyst at JPMorgan Chase who writes institutional earnings preview notes for portfolio managers. You have been given LIVE earnings history, price data, and financial data.
TASK: Deliver a JPMorgan-quality pre-earnings research brief.
MANDATORY OUTPUT STRUCTURE — LEAD WITH DECISION SUMMARY:
╔══════════════════════════════════════════════════╗
║ DECISION: [BUY BEFORE / SELL BEFORE / HOLD / WAIT]  ║
║ Confidence: [HIGH/MEDIUM/LOW]                     ║
║ Key Catalyst: [one sentence]                      ║
╚══════════════════════════════════════════════════╝
THEN:
1. EARNINGS TRACK RECORD: Last 4 quarters — format as table: Quarter | EPS Actual | Estimate | Surprise% | Price Reaction%. Derive beat/miss pattern from the data.
2. REVENUE TREND: Quarter-by-quarter revenue with growth rate. Identify acceleration or deceleration.
3. KEY METRICS WALL STREET WATCHES: Based on the sector/business description, identify the 3 most important non-GAAP metrics for this specific company.
4. MANAGEMENT GUIDANCE ASSESSMENT: Based on prior EPS revisions and analyst target changes in the data.
5. OPTIONS-IMPLIED MOVE: If current price and 52W range available, estimate typical earnings move based on historical reactions from the data.
6. SCENARIO ANALYSIS:
   - Bull Case: specific price target with % upside, trigger conditions
   - Bear Case: specific downside target with % risk, trigger conditions
7. TRADE RECOMMENDATION: Rationale tied directly to the data provided.
ALL figures derived from provided data. Flag any data gaps explicitly."""

SYSTEM_PROMPT_BLACKROCK: str = """You are a senior portfolio strategist at BlackRock, managing multi-asset portfolios for institutional and UHNW private clients. You build Investment Policy Statements and allocate across global asset classes.
TASK: Build a custom BlackRock-quality portfolio from scratch for this specific client.
MANDATORY OUTPUT STRUCTURE:
1. CLIENT PROFILE SUMMARY: Restate objectives, constraints, time horizon, account type
2. STRATEGIC ASSET ALLOCATION:
   - Equity: domestic / international / emerging split with %
   - Fixed Income: duration and credit quality split with %
   - Alternatives: if appropriate for profile
   - Cash buffer: %
   (Total must = 100%)
3. IMPLEMENTATION — specific ETF/fund for each category:
   - Ticker | Name | Category | Expense Ratio (estimate) | Why Selected
   (If Swedish ISK/KF account: note Avanza/Nordnet equivalents)
4. CORE vs SATELLITE: Label each position
5. EXPECTED OUTCOMES (derive from historical asset class return data, not invention):
   - Expected annual return range (e.g., 6–9%)
   - Expected max 12-month drawdown (cite comparable portfolio history)
6. REBALANCING RULES: Specific calendar (quarterly/annual) + threshold triggers (e.g., drift >5%)
7. TAX EFFICIENCY: Specific to the stated account type (401K / IRA / ISK / KF / Taxable)
8. DCA PLAN: If monthly investment stated, show Year 1, 3, 5 projected portfolio value at base return
9. BENCHMARK: Primary and secondary benchmarks with rationale
10. ONE-PAGE INVESTMENT POLICY STATEMENT: Full IPS with objectives, constraints, allocation ranges, prohibited investments, review schedule
Tailor everything to the client's stated situation. No generic output."""

SYSTEM_PROMPT_CITADEL: str = """You are a senior quantitative trader at Citadel who combines systematic technical analysis with statistical models to produce precise entry/exit signals. You have been given LIVE technical indicator data computed from real market prices.
TASK: Deliver a Citadel-grade technical analysis report card.
MANDATORY OUTPUT STRUCTURE:
REPORT CARD HEADER: Ticker | Current Price | Date | Overall Rating
SECTION 1 — TREND ANALYSIS
- Primary trend (based on EMA 9/21/50/200 stack from data)
- Momentum direction (RSI, MACD, EWO from data)
- Ichimoku regime (price vs cloud, TK cross from data)
SECTION 2 — INDICATOR READINGS (use EXACT values from data)
- RSI(21): [value] → interpretation
- MACD Line/Signal/Histogram: [values] → crossover status
- Bollinger Bands: [values] → position in band (% from lower band)
- EWO(5/35): [value] → wave phase interpretation
- EMA Stack: [9/21/50/200 values] → alignment status (bullish/mixed/bearish)
- Ichimoku: [Tenkan/Kijun/Cloud status] → full interpretation
SECTION 3 — PRICE STRUCTURE
- Fibonacci levels from data: list all 6 levels with current price location
- 90-day High/Low with price context
- Volume trend vs average (from data)
SECTION 4 — TRADE PLAN (all levels DERIVED from indicator data above)
┌─────────────────────────────────────────────┐
│ ENTRY ZONE:   [price range — from support]  │
│ STOP LOSS:    [price — from invalidation]   │
│ TARGET 1:     [1.618 extension]             │
│ TARGET 2:     [2.0 extension]               │
│ TARGET 3:     [2.618 extension]             │
│ R:R RATIO:    [calculated]                  │
│ CONFIDENCE:   STRONG BUY / BUY / NEUTRAL    │
│               SELL / STRONG SELL            │
└─────────────────────────────────────────────┘
NEVER invent indicator values. Use ONLY the numbers in the data context."""

SYSTEM_PROMPT_HARVARD: str = """You are the chief investment strategist for Harvard's $50B endowment fund, specializing in income-generating equity strategies with a multi-decade investment horizon. You have been given LIVE dividend data for a universe of stocks.
TASK: Build a Harvard Endowment-quality dividend income portfolio.
MANDATORY OUTPUT STRUCTURE:
1. PORTFOLIO OVERVIEW: Investment thesis, income target, time horizon
2. SELECTED HOLDINGS (15–18 stocks ranked safest to most aggressive):
   For each:
   - Ticker | Name | Current Yield (from live data) | Annual Rate
   - Dividend Safety Score: 1–10. Derive from: payout ratio (>80% = concern), D/E, FCF coverage, earnings growth. JUSTIFY each score.
   - Consecutive growth note: flag any stock where data shows declining earnings growth
   - Payout Ratio flag: mark ⚠️ if payout ratio >75% from data
3. INCOME PROJECTIONS (for stated investment amount):
   | Year | Capital | Avg Yield | Annual Income | Monthly Income |
   Show year 1, 3, 5, 10 with assumed dividend growth and reinvestment
4. SECTOR DIVERSIFICATION TABLE: % allocation per sector (no sector >30%)
5. DRIP COMPOUNDING MODEL: Starting with stated capital, show compounding at conservative/base/optimistic dividend growth rates over 10 years
6. TAX CONSIDERATIONS: Specific to stated account type and tax bracket
7. RANKED LIST (Table): All picks sorted from highest safety score to lowest, with yield and score
ALL yield and ratio figures from live data only. State clearly when deriving vs observing."""

SYSTEM_PROMPT_BAIN: str = """You are a senior partner at Bain & Company conducting a competitive strategy analysis for a major investment fund evaluating a sector. You have been given LIVE comparative financial data for sector peers.
TASK: Deliver a Bain & Company-quality competitive advantage analysis.
MANDATORY OUTPUT STRUCTURE:
1. SECTOR OVERVIEW: Size, growth characteristics, key competitive dynamics (1 paragraph)
2. COMPETITIVE COMPARISON TABLE (markdown):
   Company | Market Cap | Revenue | Operating Margin | P/E | ROE | D/E | Analyst Rating
   (Use exact figures from live data)
3. MOAT ANALYSIS — for each company:
   Moat Type: BRAND / COST / NETWORK / SWITCHING / REGULATORY / NONE
   Strength: NARROW / WIDE with one-sentence evidence from financial data
4. MARKET LEADERSHIP METRICS: Rank companies by revenue, margin, efficiency (ROE/ROIC proxy)
5. CAPITAL ALLOCATION QUALITY: FCF generation vs deployment. Identify best and worst allocator from data.
6. SECTOR THREATS: 3 specific threats with probability (High/Medium/Low) and most-exposed company
7. SWOT ANALYSIS: Full SWOT for the 2 highest-scoring companies by fundamentals
8. SINGLE BEST PICK:
   - Winner: [Ticker]
   - Rationale: 4-sentence case tied to specific data points
   - Entry consideration: current valuation context
9. 3 SPECIFIC CATALYSTS: Events/conditions that would confirm the thesis in next 12 months
Base every qualitative judgment on a specific quantitative data point from the provided data."""

SYSTEM_PROMPT_RENAISSANCE: str = """You are a quantitative researcher at Renaissance Technologies applying rigorous statistical methods to extract exploitable patterns from historical market data. You have been given LIVE computed statistics from real price history.
TASK: Deliver a Renaissance-quality quantitative research memo.
MANDATORY OUTPUT STRUCTURE:
1. QUANT RESEARCH MEMO HEADER: Ticker | Data Period | Total Observations | Key Finding
2. SEASONALITY ANALYSIS:
   - Monthly Return Table: all 12 months with avg return, std dev, % positive days
   - Best 3 months: [name them, avg return, statistical consistency]
   - Worst 3 months: [name them, with same metrics]
   - Seasonal edge assessment: is any pattern statistically meaningful?
3. DAY-OF-WEEK PATTERNS:
   - Table: Mon–Fri with avg daily return % and % positive
   - Note if any day shows >55% positive rate as potentially exploitable
4. VOLATILITY REGIME ANALYSIS:
   - From the provided annualized volatility: classify current regime
   - Historical note on what typically follows high/low vol regimes
5. MOMENTUM SCORECARD: 1M / 3M / 6M / 12M returns from data — trend strength assessment
6. RISK-ADJUSTED METRICS:
   - Sharpe ratio from data
   - Maximum drawdown and recovery context
7. STATISTICAL EDGE SUMMARY:
   - Identify the 1–2 strongest patterns (if any) with confidence level
   - Clearly distinguish: STATISTICALLY SIGNIFICANT vs NOISE vs INSUFFICIENT DATA
8. QUANTIFIABLE ADVANTAGES: If a pattern exists, state it precisely
9. VERDICT: What specific actionable edge (if any) does this data reveal?
CRITICAL: Be scientifically honest. Saying "insufficient data to conclude" is valid and preferred over fabricating significance."""

SYSTEM_PROMPT_MCKINSEY: str = """You are a senior partner at McKinsey's Global Institute advising sovereign wealth funds on how macroeconomic conditions affect equity portfolio positioning. You have been given LIVE macroeconomic indicator data.
TASK: Deliver a McKinsey-quality executive macro strategy briefing.
MANDATORY OUTPUT STRUCTURE:
CURRENT REGIME DASHBOARD (lead the report with this):
┌────────────────────────────────────────────────────────┐
│ RATE REGIME:    [Rising/Falling/Stable] — from data    │
│ RISK REGIME:    [Low/Elevated/High] — from VIX data    │
│ USD TREND:      [Strong/Weak/Neutral] — from DXY data  │
│ EQUITY REGIME:  [Bull/Bear/Transitional] — from S&P    │
│ OVERALL:        [RISK-ON / RISK-OFF / MIXED]           │
└────────────────────────────────────────────────────────┘
THEN:
1. INTEREST RATE ANALYSIS: Interpret the live 10Y and 3M yield data.
2. INFLATION PROXY ANALYSIS: Gold trend, commodity prices, TLT context from data.
3. VOLATILITY ASSESSMENT: VIX level and 1Y trend. Risk appetite implication.
4. USD STRENGTH IMPACT: DXY trend from data. Impact on domestic, European, EM.
5. PORTFOLIO HOLDINGS MACRO SENSITIVITY: For each holding, one line: macro tailwind / headwind / neutral — with reason.
6. SECTOR ROTATION RECOMMENDATION: 2 sectors overweight, 2 underweight, based on current regime.
7. 3 SPECIFIC PORTFOLIO ADJUSTMENTS: Concrete changes with position sizing rationale.
8. TIMELINE MATRIX: | Factor | Direction | 0–3 Months | 6–12 Months |
9. SCENARIO ANALYSIS: Base (60%) / Bear (25%) / Bull (15%) with portfolio impact
10. ACTION PLAN: 5 bullet points, each a specific actionable decision.
DERIVE all regime calls from the live data values provided. State confidence levels."""

# ─── NUMERIC HELPER UTILITIES ──────────────────────────────────────────────
def _safe_pct(value: Any) -> str:
    """Formats a decimal fraction (0.0–1.0) as a percentage string."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100.0:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _safe_float(value: Any, fmt: str = ".2f", suffix: str = "") -> str:
    """Safely formats a numeric value with given format spec."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):{fmt}}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _safe_bn(value: Any) -> str:
    """Formats a large number as $T/$B/$M string."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if abs(v) >= 1e12:
            return f"${v / 1e12:.1f}T"
        if abs(v) >= 1e9:
            return f"${v / 1e9:.1f}B"
        if abs(v) >= 1e6:
            return f"${v / 1e6:.1f}M"
        return f"${v:.0f}"
    except (TypeError, ValueError):
        return "N/A"


# ─── DATA FETCHING UTILITIES ───────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL)
def fetch_stock_info(ticker: str) -> Dict[str, Any]:
    """
    Fetches comprehensive stock fundamentals via yfinance.
    Args:
        ticker: yfinance-compatible ticker symbol.
    Returns:
        Dict of fundamentals, or empty dict on failure.
    """
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
            "current_price":    (info.get("currentPrice")
                                 or info.get("regularMarketPrice")),
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
            "description":      (info.get("longBusinessSummary") or "")[:400],
        }
    except Exception as e:
        logger.error(f"fetch_stock_info failed [{ticker}]: {e}")
        return {}


@st.cache_data(ttl=CACHE_TTL)
def fetch_financial_statements(ticker: str) -> Dict[str, Any]:
    """
    Fetches annual and quarterly financial statements via yfinance.
    Args:
        ticker: yfinance ticker symbol.
    Returns:
        Dict with DataFrames for income, balance, cashflow statements.
    """
    result: Dict[str, Any] = {}
    try:
        t = yf.Ticker(ticker)
        for key, attr in [
            ("annual_income",       "financials"),
            ("annual_balance",      "balance_sheet"),
            ("annual_cashflow",     "cashflow"),
            ("quarterly_income",    "quarterly_financials"),
            ("quarterly_earnings",  "quarterly_earnings"),
        ]:
            try:
                df = getattr(t, attr, None)
                if df is not None and not df.empty:
                    result[key] = df
            except Exception as inner_e:
                logger.debug(f"{key} unavailable for {ticker}: {inner_e}")
    except Exception as e:
        logger.error(f"fetch_financial_statements failed [{ticker}]: {e}")
    return result


@st.cache_data(ttl=CACHE_TTL)
def fetch_price_history(ticker: str, years: int = 3) -> pd.DataFrame:
    """
    Fetches daily OHLCV price history. Tries OpenBB first, falls back to
    yfinance direct.
    Args:
        ticker: Ticker symbol.
        years:  Years of history to retrieve.
    Returns:
        DataFrame with OHLCV columns and DatetimeIndex, or empty DataFrame.
    """
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
        except Exception as e:
            logger.debug(f"OpenBB price fetch failed [{ticker}]: {e}")
    try:
        t  = yf.Ticker(ticker)
        df = t.history(start=start_str, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        df.index   = pd.to_datetime(df.index)
        return df
    except Exception as e:
        logger.error(f"fetch_price_history failed [{ticker}]: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL)
def fetch_macro_indicators() -> Dict[str, Any]:
    """
    Fetches current macro indicator values and 1-year change via yfinance.
    Returns:
        Dict of ticker → {name, current, 1y_ago, 1y_change, 52w_high, 52w_low}.
    """
    result: Dict[str, Any] = {}
    for ticker, name in MACRO_TICKERS.items():
        try:
            t    = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist.empty:
                continue
            cur    = float(hist["Close"].iloc[-1])
            yr_ago = float(hist["Close"].iloc[0])
            chg    = ((cur / yr_ago) - 1.0) * 100.0 if yr_ago > 1e-10 else 0.0
            result[ticker] = {
                "name":      name,
                "current":   cur,
                "1y_ago":    yr_ago,
                "1y_change": chg,
                "52w_high":  float(hist["High"].max()),
                "52w_low":   float(hist["Low"].min()),
            }
        except Exception as e:
            logger.debug(f"Macro fetch failed [{ticker}]: {e}")
    return result


# ─── DATA FORMATTING FOR GROQ ──────────────────────────────────────────────
def _format_screener_table(
    stocks_data: Dict[str, Dict[str, Any]],
    universe_label: str,
) -> str:
    """Builds the live data table string for Goldman Sachs screener."""
    lines: List[str] = [
        f"LIVE MARKET DATA — {universe_label}",
        f"Fetched: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"{'Ticker':<16} {'Name':<26} {'Sector':<18} "
        f"{'Price':>8} {'P/E':>6} {'FwdPE':>6} {'D/E':>6} "
        f"{'DivYld':>7} {'RevGrw':>7} {'ProfMgn':>8} "
        f"{'MktCap':>10} {'Beta':>5} {'AnalystRec':>12}",
        "-" * 150,
    ]
    available = 0
    for ticker, d in stocks_data.items():
        if not d:
            continue
        available += 1
        lines.append(
            f"{ticker:<16} "
            f"{(d.get('name') or ticker)[:24]:<26} "
            f"{(d.get('sector') or 'Unknown')[:16]:<18} "
            f"{_safe_float(d.get('current_price'), '.2f'):>8} "
            f"{_safe_float(d.get('pe_ratio'), '.1f'):>6} "
            f"{_safe_float(d.get('forward_pe'), '.1f'):>6} "
            f"{_safe_float(d.get('debt_to_equity'), '.1f'):>6} "
            f"{_safe_pct(d.get('dividend_yield')):>7} "
            f"{_safe_pct(d.get('revenue_growth')):>7} "
            f"{_safe_pct(d.get('profit_margin')):>8} "
            f"{_safe_bn(d.get('market_cap')):>10} "
            f"{_safe_float(d.get('beta'), '.2f'):>5} "
            f"{(d.get('recommendation') or 'N/A').upper():>12}"
        )
    lines += [
        "",
        f"Stocks with available data: {available}/{len(stocks_data)}",
        "",
        "ANALYST TARGETS (where available):",
    ]
    for ticker, d in stocks_data.items():
        if not d:
            continue
        lines.append(
            f"  {ticker}: Mean={_safe_float(d.get('target_mean_price'), '.2f')} "
            f"High={_safe_float(d.get('target_high_price'), '.2f')} "
            f"Low={_safe_float(d.get('target_low_price'), '.2f')} "
            f"(N={d.get('analyst_count', 'N/A')} analysts) "
            f"FCF={_safe_bn(d.get('free_cashflow'))} "
            f"ROE={_safe_pct(d.get('roe'))}"
        )
    return "\n".join(lines)


def _format_statements_for_dcf(
    ticker: str,
    info: Dict[str, Any],
    stmts: Dict[str, Any],
) -> str:
    """Formats financial statements for Morgan Stanley DCF."""
    lines: List[str] = [
        f"LIVE FINANCIAL DATA — {ticker} | {info.get('name', ticker)}",
        f"Currency: {info.get('currency', 'USD')} | "
        f"Price: {_safe_float(info.get('current_price'), '.4f')} | "
        f"Mkt Cap: {_safe_bn(info.get('market_cap'))} | "
        f"Shares: {_safe_bn(info.get('shares_outstanding'))}",
        f"Beta: {_safe_float(info.get('beta'), '.3f')} | "
        f"Sector: {info.get('sector', 'N/A')} | "
        f"Industry: {info.get('industry', 'N/A')}",
        "",
        "KEY VALUATION RATIOS:",
        f"  P/E(TTM)={_safe_float(info.get('pe_ratio'), '.1f')} | "
        f"Fwd P/E={_safe_float(info.get('forward_pe'), '.1f')} | "
        f"EV/EBITDA={_safe_float(info.get('ev_ebitda'), '.1f')} | "
        f"P/B={_safe_float(info.get('pb_ratio'), '.2f')} | "
        f"PEG={_safe_float(info.get('peg_ratio'), '.2f')}",
        f"  D/E={_safe_float(info.get('debt_to_equity'), '.1f')} | "
        f"Op Margin={_safe_pct(info.get('operating_margin'))} | "
        f"Net Margin={_safe_pct(info.get('profit_margin'))} | "
        f"ROE={_safe_pct(info.get('roe'))} | ROA={_safe_pct(info.get('roa'))}",
        f"  FCF={_safe_bn(info.get('free_cashflow'))} | "
        f"Total Debt={_safe_bn(info.get('total_debt'))} | "
        f"Cash={_safe_bn(info.get('total_cash'))} | "
        f"EBITDA={_safe_bn(info.get('ebitda'))}",
        "",
    ]
    row_groups = {
        "annual_income": [
            "Total Revenue", "Gross Profit", "Operating Income",
            "Net Income", "EBIT", "EBITDA",
        ],
        "annual_cashflow": [
            "Operating Cash Flow", "Free Cash Flow",
            "Capital Expenditure", "Investing Cash Flow",
        ],
        "annual_balance": [
            "Total Assets", "Total Liabilities",
            "Stockholders Equity", "Long Term Debt",
        ],
    }
    section_names = {
        "annual_income":   "ANNUAL INCOME STATEMENT (recent 4Y, millions):",
        "annual_cashflow": "ANNUAL CASH FLOW (recent 4Y, millions):",
        "annual_balance":  "ANNUAL BALANCE SHEET (most recent year, millions):",
    }
    for key, rows in row_groups.items():
        if key not in stmts:
            continue
        df = stmts[key]
        lines.append(section_names[key])
        for row in rows:
            if row in df.index:
                vals = df.loc[row].values[:4]
                vals_str = "  ".join(
                    f"{v / 1e6:.0f}M"
                    if (isinstance(v, (int, float)) and not math.isnan(float(v)))
                    else "N/A"
                    for v in vals
                )
                lines.append(f"  {row:<30}: {vals_str}")
        lines.append("")
    lines.append(
        f"ANALYST: {(info.get('recommendation') or 'N/A').upper()} | "
        f"Target Mean=${_safe_float(info.get('target_mean_price'), '.2f')} | "
        f"High=${_safe_float(info.get('target_high_price'), '.2f')} | "
        f"Low=${_safe_float(info.get('target_low_price'), '.2f')} | "
        f"N={info.get('analyst_count', 'N/A')} analysts"
    )
    return "\n".join(lines)


def _format_portfolio_risk(
    holdings: Dict[str, float],
    info_map: Dict[str, Dict[str, Any]],
    price_map: Dict[str, pd.DataFrame],
) -> str:
    """Formats portfolio + computed correlations for Bridgewater risk."""
    lines: List[str] = [
        "LIVE PORTFOLIO RISK DATA",
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}",
        "",
        "HOLDINGS:",
    ]
    for ticker, pct in holdings.items():
        d      = info_map.get(ticker, {})
        name   = (d.get("name") or ticker)[:28]
        sector = d.get("sector", "Unknown")
        price  = _safe_float(d.get("current_price"), ".2f")
        beta   = _safe_float(d.get("beta"), ".2f")
        mc     = _safe_bn(d.get("market_cap"))
        lines.append(
            f"  {ticker:<12} {name:<30} {pct:.1f}%  "
            f"Sector:{sector}  Price:{price}  Beta:{beta}  Cap:{mc}"
        )
    sector_wts: Dict[str, float] = {}
    for ticker, pct in holdings.items():
        s = info_map.get(ticker, {}).get("sector", "Unknown")
        sector_wts[s] = sector_wts.get(s, 0.0) + pct
    lines += ["", "SECTOR CONCENTRATION:"]
    for sec, wt in sorted(sector_wts.items(), key=lambda x: -x[1]):
        flag = "  ⚠️ CONCENTRATED" if wt > 30.0 else ""
        lines.append(f"  {sec:<30}: {wt:.1f}%{flag}")
    lines += ["", "POSITION VOLATILITY (annualized):"]
    for ticker, df in price_map.items():
        if df.empty or "close" not in df.columns or len(df) < 30:
            continue
        rets = df["close"].pct_change().dropna()
        vol  = float(rets.std()) * math.sqrt(252.0) * 100.0
        lines.append(f"  {ticker:<12}: {vol:.1f}% annualized")
    returns_series: Dict[str, pd.Series] = {}
    for ticker, df in price_map.items():
        if not df.empty and "close" in df.columns and len(df) > 30:
            returns_series[ticker] = df["close"].pct_change().dropna()
    if len(returns_series) > 1:
        tlist     = list(returns_series.keys())
        prices_df = pd.DataFrame(returns_series).dropna()
        if len(prices_df) > 20:
            corr   = prices_df.corr()
            lines += ["", "CORRELATION MATRIX (2Y daily returns):"]
            header = f"{'':12}" + "".join(f"{t:>12}" for t in tlist)
            lines.append(header)
            for t1 in tlist:
                row = f"{t1:<12}"
                for t2 in tlist:
                    row += f"{float(corr.loc[t1, t2]):>12.2f}"
                lines.append(row)
            high_pairs = [
                (t1, t2, float(corr.loc[t1, t2]))
                for i, t1 in enumerate(tlist)
                for j, t2 in enumerate(tlist)
                if j > i and float(corr.loc[t1, t2]) > 0.70
            ]
            if high_pairs:
                lines += ["", "HIGH CORRELATION PAIRS (>0.70):"]
                for t1, t2, v in sorted(high_pairs, key=lambda x: -x[2]):
                    lines.append(f"  {t1} & {t2}: {v:.2f}")
    return "\n".join(lines)


def _format_earnings_data(
    ticker: str,
    info: Dict[str, Any],
    stmts: Dict[str, Any],
    price_df: pd.DataFrame,
) -> str:
    """Formats earnings history for JPMorgan earnings analysis."""
    lines: List[str] = [
        f"LIVE EARNINGS DATA — {ticker} | {info.get('name', ticker)}",
        f"Price: {_safe_float(info.get('current_price'), '.4f')} | "
        f"52W: {_safe_float(info.get('52w_high'), '.2f')} – "
        f"{_safe_float(info.get('52w_low'), '.2f')}",
        f"Sector: {info.get('sector', 'N/A')} | "
        f"Industry: {info.get('industry', 'N/A')}",
        "",
    ]
    if "quarterly_earnings" in stmts:
        try:
            qe = stmts["quarterly_earnings"]
            lines += [
                "QUARTERLY EPS — ACTUAL vs ESTIMATE:",
                f"{'Quarter':<14} {'EPS Actual':>12} {'EPS Est':>10} {'Surprise':>10}",
                "-" * 50,
            ]
            for idx, row in list(qe.iterrows())[:6]:
                act  = row.get("Earnings", row.get("actual"))
                est  = row.get("Estimate", row.get("estimate"))
                a_s  = f"{float(act):.3f}" if act is not None else "N/A"
                e_s  = f"{float(est):.3f}" if est is not None else "N/A"
                surp = "N/A"
                if act is not None and est is not None:
                    ef = float(est)
                    if abs(ef) > 1e-10:
                        surp = f"{((float(act) - ef) / abs(ef) * 100.0):+.1f}%"
                lines.append(
                    f"{str(idx)[:12]:<14} {a_s:>12} {e_s:>10} {surp:>10}"
                )
            lines.append("")
        except Exception as e:
            lines.append(f"  (Quarterly earnings error: {e})")
    if "quarterly_income" in stmts and not stmts["quarterly_income"].empty:
        try:
            qi = stmts["quarterly_income"]
            if "Total Revenue" in qi.index:
                lines.append("QUARTERLY REVENUE (millions):")
                rev = qi.loc["Total Revenue"]
                for col in list(rev.index)[:6]:
                    v  = rev[col]
                    vs = (f"{v / 1e6:.1f}M"
                          if isinstance(v, float) and not math.isnan(v)
                          else "N/A")
                    lines.append(f"  {str(col)[:10]}: {vs}")
                lines.append("")
        except Exception as e:
            lines.append(f"  (Revenue trend error: {e})")
    if not price_df.empty and "quarterly_earnings" in stmts:
        lines.append("PRICE BEHAVIOR ±5 DAYS AROUND EARNINGS:")
        try:
            qe        = stmts["quarterly_earnings"]
            close_col = "close" if "close" in price_df.columns else "Close"
            for idx in list(qe.index)[:4]:
                try:
                    ts = pd.Timestamp(idx)
                except Exception:
                    continue
                window = price_df[
                    (price_df.index >= ts - datetime.timedelta(days=7)) &
                    (price_df.index <= ts + datetime.timedelta(days=7))
                ]
                if len(window) >= 2 and close_col in window.columns:
                    pre  = float(window[close_col].iloc[0])
                    post = float(window[close_col].iloc[-1])
                    chg  = (post / pre - 1.0) * 100.0 if pre > 1e-10 else 0.0
                    lines.append(
                        f"  {ts.strftime('%Y-%m-%d')}: "
                        f"${pre:.2f} → ${post:.2f} ({chg:+.1f}%)"
                    )
        except Exception as e:
            lines.append(f"  (Price behavior error: {e})")
        lines.append("")
    lines.append(
        f"ANALYST: {(info.get('recommendation') or 'N/A').upper()} | "
        f"Target=${_safe_float(info.get('target_mean_price'), '.2f')}"
    )
    return "\n".join(lines)


# ─── GROQ STREAMING UTILITY ────────────────────────────────────────────────
# <- FIXED [groq_migration]: Entire function rewritten to use Groq SDK.
def _stream_analysis(
    api_key: str,
    system_prompt: str,
    user_content: str,
    placeholder: st.delta_generator.DeltaGenerator,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """
    Streams a Groq analysis response into a Streamlit st.empty() placeholder.
    Args:
        api_key:       Groq API key (from GROQ_API_KEY env var).
        system_prompt: Institutional persona + output structure instructions.
        user_content:  Live data context + specific analysis request.
        placeholder:   st.empty() container to stream into.
        max_tokens:    Maximum response tokens.
    Returns:
        Full response text after streaming completes.
    Raises:
        RuntimeError on auth failure, connection error, or missing SDK.
    """
    if not _GROQ_AVAILABLE:
        raise RuntimeError(
            "groq package not installed. Run: pip install groq"
        )
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
        error_str = str(e)
        if "401" in error_str or "authentication" in error_str.lower():
            raise RuntimeError(
                "Invalid GROQ_API_KEY. Check your .env file and restart the app."
            )
        if "429" in error_str or "rate" in error_str.lower():
            raise RuntimeError(
                "Groq rate limit reached. Wait 60 seconds and try again."
            )
        if "connection" in error_str.lower():
            raise RuntimeError(f"Groq API connection failed: {e}")
        logger.error(f"Groq API unexpected error: {e}", exc_info=True)
        raise RuntimeError(f"Groq API error: {e}")


def _render_tab_header(
    firm: str,
    color: str,
    title: str,
    description: str,
) -> None:
    """Renders the standard institutional header card for each tab."""
    st.markdown(
        f"""
        <div style='
            background:linear-gradient(135deg,rgba(0,10,26,0.95) 0%,#000d1a 100%);
            border-left:5px solid {color};border-radius:8px;
            padding:20px 26px;margin-bottom:20px;
        '>
            <p style='color:{color};font-family:monospace;font-size:10px;
                      letter-spacing:2px;margin:0 0 8px 0;'>
                ◆ {firm.upper()} · LIVE DATA · {GROQ_MODEL.upper()}
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


def _render_analysis_footer(firm: str, model: str) -> None:
    """Renders the standard disclaimer + metadata footer after each analysis."""
    st.markdown(
        f"""
        <div style='background:rgba(255,82,82,0.06);border:1px solid rgba(255,82,82,0.20);
                    border-radius:4px;padding:10px 16px;margin-top:16px;'>
            <p style='color:rgba(255,255,255,0.40);font-size:10px;
                      font-family:monospace;margin:0;'>
                ⚠ Analysis generated by {model} using live yfinance market data
                as of {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} UTC.
                {firm} does not endorse this platform. Not financial advice.
                All figures derived from live data — verify before acting.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── TAB 1 — GOLDMAN SACHS STOCK SCREENER ──────────────────────────────────
def _render_tab_goldman(api_key: str) -> None:
    """
    Renders the Goldman Sachs-level stock screener.
    Fetches live fundamentals for Swedish/international universe,
    then streams a full Groq analysis report.
    """
    _render_tab_header(
        firm="Goldman Sachs",
        color="#00B4FF",
        title="Goldman Sachs-Level Stock Screener",
        description=(
            "Fetches live fundamentals for Swedish (OMX Stockholm) and international "
            "blue-chip stocks, then deploys an institutional AI as a 20-year Goldman Sachs "
            "equity analyst to screen and rank the top 10 picks for your profile. "
            "Includes P/E vs sector, moat rating, 12-month bull/bear targets, "
            "risk rating 1–10, entry zones, and stop-loss levels."
        ),
    )
    with st.form("gs_screener_form"):
        c1, c2 = st.columns(2)
        with c1:
            risk_tol = st.selectbox(
                "Risk Tolerance",
                ["Conservative — Capital Preservation",
                 "Moderate — Balanced Growth",
                 "Aggressive — High Growth",
                 "Speculative — Maximum Return"],
            )
            # <- NEW [horizon_expansion]: 4 sub-year options prepended.
            #    Original 4 options preserved exactly at positions 4–7.
            time_horizon = st.selectbox(
                "Investment Time Horizon",
                GOLDMAN_TIME_HORIZONS,
                index=4,  # default: "Short-term (< 1 year)" — preserves prior default
            )
            universe_choice = st.radio(
                "Stock Universe",
                ["Swedish (OMX Stockholm)",
                 "International Blue Chips",
                 "Both (Swedish + International)"],
            )
        with c2:
            invest_amount = st.number_input(
                "Investment Amount (SEK or USD equivalent)",
                min_value=10_000,
                max_value=100_000_000,
                value=500_000,
                step=10_000,
            )
            sectors = st.multiselect(
                "Preferred Sectors (leave empty for all sectors)",
                ["Technology", "Healthcare", "Financial Services",
                 "Consumer Defensive", "Consumer Cyclical", "Industrials",
                 "Energy", "Materials", "Real Estate", "Utilities",
                 "Communication Services"],
                default=[],
            )
            extra_criteria = st.text_area(
                "Additional Criteria (optional)",
                placeholder="e.g. Must pay dividend. No fossil fuels. ESG only.",
                height=82,
            )
        submitted = st.form_submit_button(
            "🔍 Run Goldman Sachs Screen", type="primary"
        )
    if not submitted:
        return
    if "Swedish" in universe_choice:
        universe = SWEDISH_UNIVERSE.copy()
    elif "International" in universe_choice:
        universe = GLOBAL_UNIVERSE.copy()
    else:
        universe = {**SWEDISH_UNIVERSE, **GLOBAL_UNIVERSE}
    stocks_data: Dict[str, Dict[str, Any]] = {}
    tickers = list(universe.keys())
    bar     = st.progress(0, text="Initialising data fetch…")
    for i, ticker in enumerate(tickers):
        bar.progress(
            (i + 1) / len(tickers),
            text=f"Fetching {universe[ticker]} ({ticker})…",
        )
        stocks_data[ticker] = fetch_stock_info(ticker)
        time.sleep(0.08)
    bar.empty()
    available = sum(1 for d in stocks_data.values() if d)
    if available < 4:
        st.error(
            f"Only {available} stocks returned data. yfinance may be "
            "rate-limited. Wait 30 seconds and try again."
        )
        return
    st.success(f"✓ Live data fetched for {available}/{len(tickers)} stocks")
    data_ctx   = _format_screener_table(stocks_data, universe_choice)
    sector_str = ", ".join(sectors) if sectors else "All sectors"
    user_msg   = (
        f"LIVE MARKET DATA:\n\n{data_ctx}\n\n"
        f"INVESTOR PROFILE:\n"
        f"  Risk Tolerance: {risk_tol}\n"
        f"  Investment Amount: {invest_amount:,}\n"
        f"  Time Horizon: {time_horizon}\n"
        f"  Preferred Sectors: {sector_str}\n"
        f"  Additional Criteria: {extra_criteria or 'None'}\n\n"
        f"Using the LIVE DATA above, screen these stocks as a Goldman Sachs senior "
        f"equity analyst. Deliver the full screening report exactly as specified in "
        f"your instructions, selecting the TOP 10 best matches for this investor's "
        f"profile. All price targets must reference specific data points."
    )
    st.markdown("---")
    st.markdown(
        f"### Goldman Sachs Equity Research — Live Screen  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        with st.spinner("Streaming Goldman Sachs analysis…"):
            _stream_analysis(api_key, SYSTEM_PROMPT_GOLDMAN, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Goldman Sachs Group Inc.", GROQ_MODEL)


# ─── TAB 2 — MORGAN STANLEY DCF VALUATION ──────────────────────────────────
def _render_tab_morgan_stanley(api_key: str) -> None:
    """
    Renders the Morgan Stanley DCF valuation tool.
    Fetches 4 years of financial statements, then streams a full DCF model.
    """
    _render_tab_header(
        firm="Morgan Stanley",
        color="#FFD700",
        title="Morgan Stanley-Style DCF Valuation Deep Dive",
        description=(
            "Fetches live annual income statements, cash flow statements, and balance "
            "sheet data via yfinance, then deploys an institutional AI as a Morgan Stanley "
            "M&A investment banker to build a complete DCF model: 5-year projections, "
            "WACC, dual terminal value, sensitivity table, and a clear verdict."
        ),
    )
    with st.form("ms_dcf_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker_input = st.text_input(
                "Ticker Symbol",
                value="AAPL",
                help="Any yfinance-compatible ticker. Swedish: VOLV-B.ST",
            ).upper().strip()
        with c2:
            dcf_notes = st.text_area(
                "Additional Context (optional)",
                placeholder="e.g. Evaluate at different discount rates.",
                height=82,
            )
        submitted = st.form_submit_button("📐 Build DCF Model", type="primary")
    if not submitted:
        return
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
        return
    with st.spinner(f"Fetching live financial statements for {ticker_input}…"):
        info  = fetch_stock_info(ticker_input)
        stmts = fetch_financial_statements(ticker_input)
    if not info:
        st.error(
            f"No data returned for {ticker_input}. Check the ticker symbol "
            "(Swedish stocks: add .ST suffix, e.g. VOLV-B.ST)."
        )
        return
    if not stmts:
        st.warning(
            f"Financial statements not available for {ticker_input}. "
            "AI will build the DCF from available ratio data only."
        )
    st.success(
        f"✓ Fetched live data for {info.get('name', ticker_input)} "
        f"({info.get('currency', '?')}) | "
        f"Price: {_safe_float(info.get('current_price'), '.2f')}"
    )
    data_ctx = _format_statements_for_dcf(ticker_input, info, stmts)
    user_msg = (
        f"LIVE FINANCIAL DATA:\n\n{data_ctx}\n\n"
        f"ADDITIONAL NOTES: {dcf_notes or 'None'}\n\n"
        f"Build the complete Morgan Stanley DCF valuation memo for {ticker_input} "
        f"({info.get('name', '')}) as specified. Show all calculations. "
        f"Derive all projections from the historical data provided."
    )
    st.markdown("---")
    st.markdown(
        f"### Morgan Stanley DCF — {info.get('name', ticker_input)}  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(
            api_key, SYSTEM_PROMPT_MORGAN_STANLEY, user_msg,
            placeholder, max_tokens=MAX_TOKENS,
        )
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Morgan Stanley", GROQ_MODEL)


# ─── TAB 3 — BRIDGEWATER RISK ANALYSIS ────────────────────────────────────
def _render_tab_bridgewater(api_key: str) -> None:
    """
    Renders the Bridgewater portfolio risk analysis tool.
    Computes live correlation matrix from price history, then streams risk report.
    """
    _render_tab_header(
        firm="Bridgewater Associates",
        color="#00E5FF",
        title="Bridgewater-Inspired Portfolio Risk Analysis",
        description=(
            "Enter your holdings as ticker:percentage pairs. The system fetches "
            "2 years of live daily price data, computes a real correlation matrix, "
            "annualized volatility per position, and sector concentration — then "
            "deploys an institutional AI as a Bridgewater risk analyst for full assessment."
        ),
    )
    with st.form("bw_risk_form"):
        st.markdown("**Enter Portfolio Holdings** (one per line: TICKER:PERCENTAGE)")
        portfolio_text = st.text_area(
            "Holdings (ticker:weight%)",
            value="AAPL:20\nMSFT:20\nNVDA:15\nJPM:15\nJNJ:15\nBRK-B:15",
            height=180,
        )
        c1, c2 = st.columns(2)
        with c1:
            total_value = st.number_input(
                "Total Portfolio Value (USD/SEK)",
                min_value=10_000,
                max_value=1_000_000_000,
                value=1_000_000,
                step=10_000,
            )
        with c2:
            risk_concerns = st.text_area(
                "Primary Risk Concerns (optional)",
                placeholder="e.g. Worried about rate rises.",
                height=80,
            )
        submitted = st.form_submit_button("🛡️ Run Risk Analysis", type="primary")
    if not submitted:
        return
    holdings: Dict[str, float] = {}
    for line in portfolio_text.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
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
        st.error("Please enter at least 2 holdings in TICKER:PERCENTAGE format.")
        return
    info_map:  Dict[str, Dict[str, Any]] = {}
    price_map: Dict[str, pd.DataFrame]   = {}
    tickers    = list(holdings.keys())
    bar        = st.progress(0, text="Fetching price history…")
    for i, ticker in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
        info_map[ticker]  = fetch_stock_info(ticker)
        price_map[ticker] = fetch_price_history(ticker, years=2)
        time.sleep(0.05)
    bar.empty()
    avail_info  = sum(1 for d in info_map.values() if d)
    avail_price = sum(1 for d in price_map.values() if not d.empty)
    st.success(
        f"✓ Info for {avail_info}/{len(tickers)} tickers | "
        f"Price history for {avail_price}/{len(tickers)} tickers"
    )
    data_ctx = _format_portfolio_risk(holdings, info_map, price_map)
    user_msg = (
        f"LIVE PORTFOLIO RISK DATA:\n\n{data_ctx}\n\n"
        f"TOTAL PORTFOLIO VALUE: {total_value:,}\n"
        f"PRIMARY RISK CONCERNS: {risk_concerns or 'None specified'}\n\n"
        f"Deliver the complete Bridgewater risk management report as specified. "
        f"All metrics must be derived from the live data above."
    )
    st.markdown("---")
    st.markdown(
        f"### Bridgewater Risk Report  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_BRIDGEWATER, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Bridgewater Associates", GROQ_MODEL)


# ─── TAB 4 — JPMORGAN EARNINGS BREAKDOWN ───────────────────────────────────
def _render_tab_jpmorgan(api_key: str) -> None:
    """
    Renders the JPMorgan earnings preview tool.
    Fetches live earnings history + price data, streams pre-earnings brief.
    """
    _render_tab_header(
        firm="JPMorgan Chase",
        color="#FF9500",
        title="JPMorgan-Level Earnings Breakdown",
        description=(
            "Fetches live quarterly earnings history, EPS estimates, revenue trends, "
            "and price behavior around recent earnings via yfinance — then deploys "
            "an institutional AI as a JPMorgan equity analyst for a full "
            "pre-earnings brief with beat/miss history, scenarios, and a clear "
            "recommended play."
        ),
    )
    with st.form("jpm_earnings_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker_input = st.text_input(
                "Ticker Symbol",
                value="NVDA",
                help="Any yfinance ticker. Swedish stocks: add .ST",
            ).upper().strip()
            earnings_date = st.text_input(
                "Next Earnings Date (optional, YYYY-MM-DD)",
                value="",
            )
        with c2:
            position_note = st.text_area(
                "Your Current Position / Context",
                placeholder="e.g. Long 100 shares @ $800.",
                height=82,
            )
            focus_areas = st.text_area(
                "Focus Areas (optional)",
                placeholder="e.g. Focus on data center revenue.",
                height=82,
            )
        submitted = st.form_submit_button(
            "📊 Run Earnings Analysis", type="primary"
        )
    if not submitted:
        return
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
        return
    with st.spinner(f"Fetching live earnings data for {ticker_input}…"):
        info     = fetch_stock_info(ticker_input)
        stmts    = fetch_financial_statements(ticker_input)
        price_df = fetch_price_history(ticker_input, years=2)
    if not info:
        st.error(f"No data returned for {ticker_input}. Check the ticker.")
        return
    st.success(
        f"✓ {info.get('name', ticker_input)} | "
        f"Price: {_safe_float(info.get('current_price'), '.2f')} | "
        f"Sector: {info.get('sector', 'N/A')}"
    )
    data_ctx = _format_earnings_data(ticker_input, info, stmts, price_df)
    user_msg = (
        f"LIVE EARNINGS DATA:\n\n{data_ctx}\n\n"
        f"NEXT EARNINGS DATE: {earnings_date or 'Unknown — note this in your brief'}\n"
        f"CURRENT POSITION: {position_note or 'Not specified'}\n"
        f"FOCUS AREAS: {focus_areas or 'None'}\n\n"
        f"Deliver the complete JPMorgan pre-earnings research brief as specified, "
        f"LEADING WITH THE DECISION SUMMARY. All figures from the live data above."
    )
    st.markdown("---")
    st.markdown(
        f"### JPMorgan Pre-Earnings Brief — {info.get('name', ticker_input)}  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_JPMORGAN, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("JPMorgan Chase & Co.", GROQ_MODEL)


# ─── TAB 5 — BLACKROCK PORTFOLIO CONSTRUCTION ──────────────────────────────
def _render_tab_blackrock(api_key: str) -> None:
    """
    Renders the BlackRock portfolio construction tool.
    Fetches broad index data for macro context, streams full IPS.
    """
    _render_tab_header(
        firm="BlackRock",
        color="#A855F7",
        title="BlackRock-Style Portfolio Construction",
        description=(
            "Describe your personal financial situation and goals. An institutional AI, "
            "acting as a BlackRock senior portfolio strategist, builds a custom "
            "portfolio from scratch: exact asset allocation, specific ETF tickers, "
            "DCA plan, rebalancing rules, tax strategy, and a complete one-page IPS."
        ),
    )
    with st.form("br_portfolio_form"):
        c1, c2 = st.columns(2)
        with c1:
            age             = st.number_input(
                "Age", min_value=18, max_value=90, value=35
            )
            annual_income   = st.number_input(
                "Annual Income (USD/SEK)", min_value=0,
                max_value=100_000_000, value=600_000, step=10_000,
            )
            current_savings = st.number_input(
                "Current Savings/Investable Assets", min_value=0,
                max_value=1_000_000_000, value=500_000, step=10_000,
            )
            monthly_invest  = st.number_input(
                "Monthly DCA Amount (0 if lump sum)", min_value=0,
                max_value=1_000_000, value=5_000, step=500,
            )
        with c2:
            risk_profile = st.selectbox(
                "Risk Profile",
                ["Very Conservative (capital preservation)",
                 "Conservative (modest growth)",
                 "Moderate (balanced)",
                 "Growth (long-term growth)",
                 "Aggressive Growth (maximum return)"],
                index=2,
            )
            account_type = st.selectbox(
                "Account Type",
                ["Swedish ISK (Investeringssparkonto)",
                 "Swedish KF (Kapitalförsäkring)",
                 "Swedish Aktie & Fondkonto (taxable)",
                 "US 401K",
                 "US IRA (Traditional)",
                 "US Roth IRA",
                 "US Taxable Brokerage",
                 "Other Taxable"],
            )
            primary_goal = st.selectbox(
                "Primary Goal",
                ["Retirement at 65+",
                 "Early Retirement (FIRE)",
                 "Wealth Accumulation",
                 "Income Generation",
                 "Capital Preservation",
                 "Education Fund (10Y horizon)"],
            )
            # <- NEW [horizon_expansion]: st.slider replaced with st.selectbox.
            #    Sub-year options added (1 Week, 1 Month, 3 Months, 6 Months).
            #    All prior slider integer values 1–50 preserved as labeled entries.
            #    Default set to "20 Years" to match prior slider default of 20.
            time_horizon_str: str = st.selectbox(
                "Investment Time Horizon",
                BLACKROCK_TIME_HORIZONS,
                index=11,  # default: "20 Years" — matches prior slider default
            )
            restrictions = st.text_area(
                "Restrictions / Preferences (optional)",
                placeholder="e.g. No fossil fuels. Must include Swedish stocks.",
                height=70,
            )
        submitted = st.form_submit_button(
            "⚖️ Build BlackRock Portfolio", type="primary"
        )
    if not submitted:
        return
    with st.spinner("Fetching broad market context…"):
        sp500_info = fetch_stock_info("SPY")
        bond_info  = fetch_stock_info("TLT")
    market_ctx = (
        f"CURRENT MARKET CONTEXT:\n"
        f"  S&P 500 (SPY): Price={_safe_float(sp500_info.get('current_price'), '.2f')} | "
        f"52W High={_safe_float(sp500_info.get('52w_high'), '.2f')} | "
        f"52W Low={_safe_float(sp500_info.get('52w_low'), '.2f')}\n"
        f"  TLT (20Y Bond ETF): Price={_safe_float(bond_info.get('current_price'), '.2f')}\n"
    )
    # <- NEW [horizon_expansion]: time_horizon_str passed directly as label string.
    #    Prior code passed f"  Time Horizon: {time_horizon_yrs} years\n" (integer).
    #    New code passes the selectbox label verbatim — self-describing for all horizons.
    user_msg = (
        f"{market_ctx}\n\n"
        f"CLIENT PROFILE:\n"
        f"  Age: {age}\n"
        f"  Annual Income: {annual_income:,}\n"
        f"  Current Investable Assets: {current_savings:,}\n"
        f"  Monthly DCA: {monthly_invest:,}\n"
        f"  Risk Profile: {risk_profile}\n"
        f"  Account Type: {account_type}\n"
        f"  Primary Goal: {primary_goal}\n"
        f"  Time Horizon: {time_horizon_str}\n"
        f"  Restrictions: {restrictions or 'None'}\n\n"
        f"Build the complete BlackRock-quality portfolio and Investment Policy "
        f"Statement as specified. For ETF selections, provide specific ticker "
        f"symbols. For Swedish ISK/KF, include Avanza/Nordnet equivalents."
    )
    st.markdown("---")
    st.markdown(
        f"### BlackRock Portfolio — Custom Build  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_BLACKROCK, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("BlackRock Inc.", GROQ_MODEL)
    # ─── TAB 6 — CITADEL TECHNICAL ANALYSIS ────────────────────────────────────
def _format_technical_context(
    ticker: str,
    df: pd.DataFrame,
    info: Dict[str, Any],
) -> str:
    """
    Computes all technical indicators from live OHLCV data and formats
    them into a structured string for the Citadel technical analysis prompt.
    """
    if df.empty or "close" not in df.columns:
        return f"ERROR: No OHLCV data available for {ticker}"
    close = df["close"]
    high  = df["high"]   if "high"   in df.columns else close
    low   = df["low"]    if "low"    in df.columns else close
    vol   = df["volume"] if "volume" in df.columns else pd.Series(
        dtype=float, index=df.index
    )
    n = len(close)
    ema_9   = float(close.ewm(span=9,   adjust=False).mean().iloc[-1])
    ema_21  = float(close.ewm(span=21,  adjust=False).mean().iloc[-1])
    ema_50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
    ema_200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

    def _sma(span: int) -> Optional[float]:
        return float(close.rolling(span).mean().iloc[-1]) if n >= span else None

    sma_20  = _sma(20)
    sma_50  = _sma(50)
    sma_200 = _sma(200)
    delta    = close.diff()
    gain     = delta.clip(lower=0.0)
    loss     = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(com=20, adjust=False).mean()
    avg_loss = loss.ewm(com=20, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi_ser  = 100.0 - (100.0 / (1.0 + rs))
    rsi_val  = float(rsi_ser.iloc[-1])
    ema_12   = close.ewm(span=12, adjust=False).mean()
    ema_26   = close.ewm(span=26, adjust=False).mean()
    macd     = ema_12 - ema_26
    sig      = macd.ewm(span=9, adjust=False).mean()
    hist     = macd - sig
    macd_val = float(macd.iloc[-1])
    sig_val  = float(sig.iloc[-1])
    hist_val = float(hist.iloc[-1])
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std(ddof=0)
    bb_up  = (bb_mid + 2.0 * bb_std).iloc[-1]
    bb_dn  = (bb_mid - 2.0 * bb_std).iloc[-1]
    bb_md  = bb_mid.iloc[-1]
    ewo_val = (
        float((close.rolling(5).mean() - close.rolling(35).mean()).iloc[-1])
        if n >= 35 else float("nan")
    )
    tenkan   = (high.rolling(9).max()  + low.rolling(9).min())  / 2.0
    kijun    = (high.rolling(26).max() + low.rolling(26).min()) / 2.0
    senkou_a = ((tenkan + kijun) / 2.0).shift(26)
    senkou_b = (
        (high.rolling(52).max() + low.rolling(52).min()) / 2.0
    ).shift(26)
    tk_v  = float(tenkan.iloc[-1])
    kj_v  = float(kijun.iloc[-1])
    sa_cl = senkou_a.dropna()
    sb_cl = senkou_b.dropna()
    sa_v  = float(sa_cl.iloc[-1]) if len(sa_cl) > 0 else float("nan")
    sb_v  = float(sb_cl.iloc[-1]) if len(sb_cl) > 0 else float("nan")
    cloud_top = (
        max(sa_v, sb_v)
        if not (math.isnan(sa_v) or math.isnan(sb_v)) else float("nan")
    )
    cloud_bot = (
        min(sa_v, sb_v)
        if not (math.isnan(sa_v) or math.isnan(sb_v)) else float("nan")
    )
    vol_str = "N/A"
    if not vol.empty and len(vol) > 20:
        avg_v  = float(vol.rolling(20).mean().iloc[-1])
        cur_v  = float(vol.iloc[-1])
        vr     = cur_v / avg_v if avg_v > 1e-10 else 1.0
        trend  = "ABOVE AVG" if vr > 1.2 else "BELOW AVG" if vr < 0.8 else "AVERAGE"
        vol_str = f"{vr:.2f}x average ({trend})"
    ph   = float(high.max())
    pl   = float(low.min())
    pr   = ph - pl
    fibs = {lvl: ph - pr * lvl for lvl in [0.236, 0.382, 0.500, 0.618, 0.786]}
    cur = float(close.iloc[-1])

    def _pos(val: float) -> str:
        return "↑ ABOVE" if cur > val else "↓ BELOW"

    def _fmt(v: Optional[float], d: int = 4) -> str:
        return f"{v:.{d}f}" if v is not None and not math.isnan(v) else "N/A"

    bb_pct = (
        f"{((cur - float(bb_dn)) / (float(bb_up) - float(bb_dn)) * 100.0):.0f}% "
        "from lower band"
        if not (math.isnan(float(bb_up)) or math.isnan(float(bb_dn)))
        and abs(float(bb_up) - float(bb_dn)) > 1e-10
        else "N/A"
    )
    if math.isnan(cloud_top) or math.isnan(cloud_bot):
        cloud_pos = "N/A"
    elif cur > cloud_top:
        cloud_pos = "ABOVE CLOUD (Bullish)"
    elif cur < cloud_bot:
        cloud_pos = "BELOW CLOUD (Bearish)"
    else:
        cloud_pos = "INSIDE CLOUD (Neutral)"
    ema_stack = (
        "BULLISH ▲" if ema_9 > ema_21 > ema_50 > ema_200
        else "BEARISH ▼" if ema_9 < ema_21 < ema_50 < ema_200
        else "MIXED"
    )
    lines: List[str] = [
        f"LIVE TECHNICAL DATA — {ticker} | {info.get('name', ticker)}",
        f"{n} daily bars | "
        f"{df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}",
        "",
        f"PRICE:    {cur:.4f}",
        f"90D HIGH: {ph:.4f} | 90D LOW: {pl:.4f}",
        f"52W HIGH: {_safe_float(info.get('52w_high'), '.4f')} | "
        f"52W LOW: {_safe_float(info.get('52w_low'), '.4f')}",
        "",
        "MOVING AVERAGES:",
        f"  EMA   9: {ema_9:.4f}  {_pos(ema_9)}",
        f"  EMA  21: {ema_21:.4f}  {_pos(ema_21)}",
        f"  EMA  50: {ema_50:.4f}  {_pos(ema_50)}",
        f"  EMA 200: {ema_200:.4f}  {_pos(ema_200)}",
        f"  SMA  20: {_fmt(sma_20)}  {_pos(sma_20) if sma_20 else 'N/A'}",
        f"  SMA  50: {_fmt(sma_50)}  {_pos(sma_50) if sma_50 else 'N/A'}",
        f"  SMA 200: {_fmt(sma_200)}  {_pos(sma_200) if sma_200 else 'N/A'}",
        f"  EMA Stack: {ema_stack}",
        "",
        "OSCILLATORS:",
        f"  RSI (21):       {rsi_val:.2f}  "
        f"({'OVERBOUGHT >70' if rsi_val > 70.0 else 'OVERSOLD <30' if rsi_val < 30.0 else 'NEUTRAL'})",
        f"  MACD Line:      {macd_val:.4f}",
        f"  MACD Signal:    {sig_val:.4f}",
        f"  MACD Histogram: {hist_val:.4f}  "
        f"({'BULLISH ▲' if hist_val > 0 else 'BEARISH ▼'})",
        f"  EWO (5/35):     {_fmt(ewo_val)}  "
        f"({'POSITIVE ▲' if not math.isnan(ewo_val) and ewo_val > 0 else 'NEGATIVE ▼' if not math.isnan(ewo_val) else 'N/A'})",
        "",
        "BOLLINGER BANDS (20, 2):",
        f"  Upper: {float(bb_up):.4f} | Mid: {float(bb_md):.4f} | Lower: {float(bb_dn):.4f}",
        f"  Price position: {bb_pct}",
        "",
        "ICHIMOKU CLOUD:",
        f"  Tenkan-sen (9):  {tk_v:.4f}",
        f"  Kijun-sen  (26): {kj_v:.4f}",
        f"  Senkou A:        {_fmt(sa_v)}",
        f"  Senkou B:        {_fmt(sb_v)}",
        f"  Price vs Cloud:  {cloud_pos}",
        f"  TK Cross:        "
        f"{'Tenkan > Kijun (Bullish)' if tk_v > kj_v else 'Tenkan < Kijun (Bearish)'}",
        "",
        "FIBONACCI RETRACEMENT (90-day range):",
        f"  HIGH:   {ph:.4f}",
    ]
    for lvl, price_level in fibs.items():
        marker = " ← PRICE NEAR" if abs(cur - price_level) / ph < 0.005 else ""
        lines.append(f"  {lvl * 100:.1f}%: {price_level:.4f}{marker}")
    lines.append(f"  LOW:    {pl:.4f}")
    lines += [
        "",
        f"VOLUME TREND: {vol_str}",
        f"BETA:         {_safe_float(info.get('beta'), '.3f')}",
    ]
    return "\n".join(lines)


def _render_tab_citadel(api_key: str) -> None:
    """Renders the Citadel technical analysis system."""
    _render_tab_header(
        firm="Citadel",
        color="#00FF88",
        title="Citadel-Grade Technical Analysis System",
        description=(
            "Fetches 90 days of live daily OHLCV data, computes all indicators in "
            "real time: EMA 9/21/50/200, RSI(21), MACD(12/26/9), Bollinger(20,2), "
            "EWO(5/35), Ichimoku, Fibonacci — then deploys an institutional AI as a Citadel "
            "quantitative trader for a full technical report card with a precise "
            "trade plan: entry, stop-loss, three targets, and R:R ratio."
        ),
    )
    with st.form("citadel_tech_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker_input = st.text_input(
                "Ticker Symbol",
                value="NVDA",
                help="Any yfinance ticker. Swedish: VOLV-B.ST",
            ).upper().strip()
        with c2:
            position_note = st.text_area(
                "Current Position / Context (optional)",
                placeholder="e.g. Long 100 shares. Looking for an exit.",
                height=82,
            )
        submitted = st.form_submit_button(
            "📈 Run Technical Analysis", type="primary"
        )
    if not submitted:
        return
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
        return
    with st.spinner(f"Fetching live 90-day OHLCV for {ticker_input}…"):
        info = fetch_stock_info(ticker_input)
        df   = fetch_price_history(ticker_input, years=1)
    if df.empty:
        st.error(f"No price data for {ticker_input}.")
        return
    df_90 = df.tail(90).copy()
    st.success(
        f"✓ {info.get('name', ticker_input)} | "
        f"{len(df_90)} bars | "
        f"Last: {_safe_float(info.get('current_price'), '.4f')}"
    )
    data_ctx = _format_technical_context(ticker_input, df_90, info)
    user_msg = (
        f"LIVE TECHNICAL INDICATOR DATA:\n\n{data_ctx}\n\n"
        f"CURRENT POSITION: {position_note or 'Not specified'}\n\n"
        f"Deliver the complete Citadel technical analysis report card for "
        f"{ticker_input} as specified. Use ONLY the exact indicator values "
        f"in the data above. Derive all trade plan levels from the data."
    )
    st.markdown("---")
    st.markdown(
        f"### Citadel Technical Report — {info.get('name', ticker_input)}  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_CITADEL, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Citadel LLC", GROQ_MODEL)


# ─── TAB 7 — HARVARD ENDOWMENT DIVIDEND STRATEGY ───────────────────────────
def _render_tab_harvard_dividend(api_key: str) -> None:
    """Renders the Harvard Endowment dividend strategy builder."""
    _render_tab_header(
        firm="Harvard Endowment",
        color="#FF6B6B",
        title="Harvard Endowment-Inspired Dividend Strategy",
        description=(
            "Fetches live dividend yield, payout ratio, earnings growth, and FCF "
            "for a curated universe of dividend payers (Swedish + international) — "
            "then deploys an institutional AI as the Harvard Endowment chief strategist to "
            "build a 15–18 stock dividend portfolio with safety scores, income "
            "projections, DRIP compounding, and a sector-diversified blueprint."
        ),
    )
    with st.form("harvard_div_form"):
        c1, c2 = st.columns(2)
        with c1:
            invest_amount = st.number_input(
                "Total Investment Amount (USD/SEK)",
                min_value=10_000,
                max_value=100_000_000,
                value=1_000_000,
                step=10_000,
            )
            income_goal = st.number_input(
                "Monthly Income Goal (USD/SEK, 0 if no specific target)",
                min_value=0,
                max_value=10_000_000,
                value=5_000,
                step=500,
            )
        with c2:
            account_type = st.selectbox(
                "Account Type",
                ["Swedish ISK", "Swedish KF", "Swedish Aktie & Fondkonto",
                 "US Taxable", "US IRA/Roth", "Other"],
            )
            tax_bracket = st.selectbox(
                "Tax Bracket",
                ["0–20%", "21–30%", "31–40%", "41–50%", "50%+"],
                index=2,
            )
            extra_prefs = st.text_area(
                "Preferences (optional)",
                placeholder="e.g. Focus on Swedish dividend aristocrats. No financials.",
                height=70,
            )
        submitted = st.form_submit_button("💰 Build Dividend Portfolio", type="primary")
    if not submitted:
        return
    div_data: Dict[str, Dict[str, Any]] = {}
    tickers = list(DIVIDEND_UNIVERSE.keys())
    bar     = st.progress(0, text="Fetching dividend data…")
    for i, ticker in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
        div_data[ticker] = fetch_stock_info(ticker)
        time.sleep(0.08)
    bar.empty()
    avail = sum(1 for d in div_data.values() if d)
    st.success(f"✓ Live dividend data for {avail}/{len(tickers)} stocks")
    lines: List[str] = [
        "LIVE DIVIDEND UNIVERSE DATA:",
        f"{'Ticker':<14} {'Name':<26} {'Sector':<18} "
        f"{'Price':>8} {'DivYld':>7} {'DivRate':>8} "
        f"{'PayoutR':>8} {'EpsGrwth':>9} {'FCF':>10} "
        f"{'D/E':>6} {'ProfMgn':>8} {'Rec':>10}",
        "-" * 140,
    ]
    for ticker, d in div_data.items():
        if not d:
            continue
        lines.append(
            f"{ticker:<14} "
            f"{(d.get('name') or ticker)[:24]:<26} "
            f"{(d.get('sector') or 'Unknown')[:16]:<18} "
            f"{_safe_float(d.get('current_price'), '.2f'):>8} "
            f"{_safe_pct(d.get('dividend_yield')):>7} "
            f"{_safe_float(d.get('dividend_rate'), '.2f'):>8} "
            f"{_safe_pct(d.get('payout_ratio')):>8} "
            f"{_safe_pct(d.get('earnings_growth')):>9} "
            f"{_safe_bn(d.get('free_cashflow')):>10} "
            f"{_safe_float(d.get('debt_to_equity'), '.1f'):>6} "
            f"{_safe_pct(d.get('profit_margin')):>8} "
            f"{(d.get('recommendation') or 'N/A').upper()[:10]:>10}"
        )
    data_ctx = "\n".join(lines)
    user_msg = (
        f"LIVE DIVIDEND DATA:\n\n{data_ctx}\n\n"
        f"CLIENT SITUATION:\n"
        f"  Total Investment: {invest_amount:,}\n"
        f"  Monthly Income Goal: {income_goal:,}\n"
        f"  Account Type: {account_type}\n"
        f"  Tax Bracket: {tax_bracket}\n"
        f"  Preferences: {extra_prefs or 'None'}\n\n"
        f"Build the complete Harvard Endowment dividend portfolio as specified. "
        f"All yields, safety scores, and projections must be derived from the "
        f"live data above. Show your scoring methodology for each stock."
    )
    st.markdown("---")
    st.markdown(
        f"### Harvard Endowment Dividend Blueprint  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_HARVARD, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Harvard Management Company", GROQ_MODEL)


# ─── TAB 8 — BAIN COMPETITIVE ANALYSIS ────────────────────────────────────
def _render_tab_bain(api_key: str) -> None:
    """Renders the Bain & Company competitive advantage analysis."""
    _render_tab_header(
        firm="Bain & Company",
        color="#FF5252",
        title="Bain-Style Competitive Advantage Analysis",
        description=(
            "Enter 5–7 tickers from a sector or industry. The system fetches "
            "live revenue, margins, ROE, market cap, and moat indicators for each, "
            "then deploys an institutional AI as a Bain senior partner to deliver a full "
            "competitive landscape: moat analysis, SWOT on top 2, a single best "
            "pick, and 3 specific 12-month catalysts."
        ),
    )
    with st.form("bain_competitive_form"):
        c1, c2 = st.columns(2)
        with c1:
            sector_name = st.text_input(
                "Sector or Industry Name",
                value="Swedish Banking",
                placeholder="e.g. Global Semiconductors, European Luxury, Nordic Banks",
            )
            ticker_list = st.text_area(
                "Competitor Tickers (one per line, 5–8 tickers)",
                value="NDA-SE.ST\nSEB-A.ST\nSWED-A.ST\nHAND-B.ST\nSHBA-A.ST",
                height=160,
            )
        with c2:
            investment_thesis = st.text_area(
                "Investment Thesis / Context (optional)",
                placeholder="e.g. Looking for best long-term compounder.",
                height=80,
            )
            focus_metrics = st.text_area(
                "Key Metrics to Focus On (optional)",
                placeholder="e.g. Net interest margin, loan growth.",
                height=80,
            )
        submitted = st.form_submit_button("⚔️ Run Competitive Analysis", type="primary")
    if not submitted:
        return
    tickers: List[str] = [
        t.strip().upper()
        for t in ticker_list.strip().splitlines()
        if t.strip()
    ]
    if len(tickers) < 3:
        st.error("Please enter at least 3 competitor tickers.")
        return
    peer_data: Dict[str, Dict[str, Any]] = {}
    bar = st.progress(0, text="Fetching peer fundamentals…")
    for i, ticker in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
        peer_data[ticker] = fetch_stock_info(ticker)
        time.sleep(0.08)
    bar.empty()
    avail = sum(1 for d in peer_data.values() if d)
    if avail < 2:
        st.error("Fewer than 2 stocks returned data. Check ticker symbols and retry.")
        return
    st.success(f"✓ Live data for {avail}/{len(tickers)} competitors")
    comp_lines: List[str] = [
        f"LIVE COMPETITIVE DATA — {sector_name}",
        f"{'Ticker':<14} {'Name':<26} {'MktCap':>10} {'Revenue':>10} "
        f"{'OpMgn':>7} {'ProfMgn':>8} {'P/E':>6} {'ROE':>7} "
        f"{'D/E':>6} {'RevGrw':>7} {'AnalystRec':>12}",
        "-" * 130,
    ]
    for ticker, d in peer_data.items():
        if not d:
            continue
        comp_lines.append(
            f"{ticker:<14} "
            f"{(d.get('name') or ticker)[:24]:<26} "
            f"{_safe_bn(d.get('market_cap')):>10} "
            f"{_safe_bn(d.get('total_revenue')):>10} "
            f"{_safe_pct(d.get('operating_margin')):>7} "
            f"{_safe_pct(d.get('profit_margin')):>8} "
            f"{_safe_float(d.get('pe_ratio'), '.1f'):>6} "
            f"{_safe_pct(d.get('roe')):>7} "
            f"{_safe_float(d.get('debt_to_equity'), '.1f'):>6} "
            f"{_safe_pct(d.get('revenue_growth')):>7} "
            f"{(d.get('recommendation') or 'N/A').upper()[:12]:>12}"
        )
    comp_lines += ["", "ADDITIONAL METRICS:"]
    for ticker, d in peer_data.items():
        if not d:
            continue
        comp_lines.append(
            f"  {ticker}: EV/EBITDA={_safe_float(d.get('ev_ebitda'), '.1f')} | "
            f"FCF={_safe_bn(d.get('free_cashflow'))} | "
            f"Beta={_safe_float(d.get('beta'), '.2f')} | "
            f"Fwd P/E={_safe_float(d.get('forward_pe'), '.1f')}"
        )
    data_ctx = "\n".join(comp_lines)
    user_msg = (
        f"LIVE COMPETITIVE DATA:\n\n{data_ctx}\n\n"
        f"SECTOR: {sector_name}\n"
        f"INVESTMENT THESIS: {investment_thesis or 'None specified'}\n"
        f"KEY METRICS FOCUS: {focus_metrics or 'None specified'}\n\n"
        f"Deliver the complete Bain competitive advantage analysis as specified. "
        f"Every qualitative judgment must reference at least one specific data point "
        f"from the live data above."
    )
    st.markdown("---")
    st.markdown(
        f"### Bain Competitive Analysis — {sector_name}  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_BAIN, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Bain & Company", GROQ_MODEL)


# ─── TAB 9 — RENAISSANCE TECHNOLOGIES PATTERN FINDER ──────────────────────
def _format_quant_stats(
    ticker: str,
    df: pd.DataFrame,
    info: Dict[str, Any],
) -> str:
    """Computes full quantitative statistical profile from live price history."""
    if df.empty or "close" not in df.columns:
        return f"ERROR: No data for {ticker}"
    close = df["close"]
    rets  = close.pct_change().dropna()
    n     = len(rets)
    lines: List[str] = [
        f"LIVE QUANTITATIVE DATA — {ticker} | {info.get('name', ticker)}",
        f"Data range: {df.index[0].strftime('%Y-%m-%d')} → "
        f"{df.index[-1].strftime('%Y-%m-%d')} | {n} daily observations",
        f"Current Price: {float(close.iloc[-1]):.4f}",
        "",
    ]
    df_work          = df.copy()
    df_work["month"] = df_work.index.month
    df_work["ret"]   = close.pct_change()
    lines.append("MONTHLY SEASONALITY (avg daily return % per month):")
    month_names = [
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec",
    ]
    monthly_stats: List[Dict[str, Any]] = []
    for m in range(1, 13):
        m_rets = df_work[df_work["month"] == m]["ret"].dropna()
        if len(m_rets) < 5:
            continue
        avg_r   = float(m_rets.mean()) * 100.0
        std_r   = float(m_rets.std())  * 100.0
        pct_pos = float((m_rets > 0.0).mean()) * 100.0
        monthly_stats.append({
            "month": month_names[m - 1],
            "avg":   avg_r,
            "std":   std_r,
            "pos":   pct_pos,
            "n":     len(m_rets),
        })
        lines.append(
            f"  {month_names[m - 1]:4}: avg={avg_r:+.3f}% | "
            f"std={std_r:.3f}% | pos={pct_pos:.0f}% | n={len(m_rets)} days"
        )
    if monthly_stats:
        best  = sorted(monthly_stats, key=lambda x: x["avg"], reverse=True)[:3]
        worst = sorted(monthly_stats, key=lambda x: x["avg"])[:3]
        lines += [
            "",
            "BEST MONTHS:  " +
            " | ".join(f"{m['month']}({m['avg']:+.2f}%)" for m in best),
            "WORST MONTHS: " +
            " | ".join(f"{m['month']}({m['avg']:+.2f}%)" for m in worst),
        ]
    lines.append("\nDAY-OF-WEEK PATTERNS:")
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for dow in range(5):
        d_rets = rets[rets.index.dayofweek == dow]
        if len(d_rets) < 20:
            continue
        avg_r   = float(d_rets.mean()) * 100.0
        pct_pos = float((d_rets > 0.0).mean()) * 100.0
        lines.append(
            f"  {dow_names[dow]}: avg={avg_r:+.3f}% | "
            f"pos={pct_pos:.0f}% | n={len(d_rets)}"
        )
    cur_price = float(close.iloc[-1])
    lines.append("\nMOMENTUM RETURNS (as of latest price):")
    for label, days in [("1M", 21), ("3M", 63), ("6M", 126), ("12M", 252)]:
        if len(close) > days:
            past  = float(close.iloc[-days - 1])
            ret_p = (cur_price / past - 1.0) * 100.0 if past > 1e-10 else 0.0
            lines.append(f"  {label}: {ret_p:+.2f}%")
    ann_vol = float(rets.std()) * math.sqrt(252.0) * 100.0
    ann_ret = float(rets.mean()) * 252.0 * 100.0
    sharpe  = ann_ret / ann_vol if ann_vol > 1e-10 else 0.0
    rolling_max = close.expanding().max()
    drawdowns   = (close / rolling_max) - 1.0
    max_dd      = float(drawdowns.min()) * 100.0
    lines += [
        "",
        "RISK-ADJUSTED METRICS:",
        f"  Annualized Return: {ann_ret:+.2f}%",
        f"  Annualized Vol:    {ann_vol:.2f}%",
        f"  Sharpe Ratio:      {sharpe:.3f} (using risk-free=0)",
        f"  Max Drawdown:      {max_dd:.2f}%",
        f"  Beta:              {_safe_float(info.get('beta'), '.3f')}",
    ]
    return "\n".join(lines)


def _render_tab_renaissance(api_key: str) -> None:
    """Renders the Renaissance Technologies quantitative pattern finder."""
    _render_tab_header(
        firm="Renaissance Technologies",
        color="#00D2FF",
        title="Renaissance Technologies Pattern Finder",
        description=(
            "Fetches 3 years of live daily price history, computes full "
            "quantitative statistical profile: monthly and day-of-week seasonality "
            "from real return data, momentum returns (1M/3M/6M/12M), Sharpe ratio, "
            "max drawdown — then deploys an institutional AI as a Renaissance quant researcher "
            "to identify exploitable patterns with scientific rigor."
        ),
    )
    with st.form("renaissance_quant_form"):
        c1, c2 = st.columns(2)
        with c1:
            ticker_input = st.text_input(
                "Ticker Symbol",
                value="EVO.ST",
                help="3 years of data required for seasonality analysis.",
            ).upper().strip()
        with c2:
            quant_focus = st.text_area(
                "Research Focus (optional)",
                placeholder="e.g. Interested in earnings-related patterns.",
                height=82,
            )
        submitted = st.form_submit_button("🔬 Run Quantitative Analysis", type="primary")
    if not submitted:
        return
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
        return
    with st.spinner(f"Fetching 3 years of daily data for {ticker_input}…"):
        info = fetch_stock_info(ticker_input)
        df   = fetch_price_history(ticker_input, years=3)
    if df.empty:
        st.error(f"No price data for {ticker_input}.")
        return
    st.success(
        f"✓ {info.get('name', ticker_input)} | "
        f"{len(df)} trading days | "
        f"{df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}"
    )
    data_ctx = _format_quant_stats(ticker_input, df, info)
    user_msg = (
        f"LIVE QUANTITATIVE DATA:\n\n{data_ctx}\n\n"
        f"RESEARCH FOCUS: {quant_focus or 'General pattern discovery'}\n\n"
        f"Deliver the complete Renaissance Technologies quantitative research memo "
        f"as specified. Base all pattern claims on the actual numbers in the data "
        f"above. Be scientifically honest about statistical significance."
    )
    st.markdown("---")
    st.markdown(
        f"### Renaissance Quant Memo — {info.get('name', ticker_input)}  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_RENAISSANCE, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("Renaissance Technologies LLC", GROQ_MODEL)


# ─── TAB 10 — MCKINSEY MACRO IMPACT ASSESSMENT ────────────────────────────
def _render_tab_mckinsey(api_key: str) -> None:
    """Renders the McKinsey macro impact assessment."""
    _render_tab_header(
        firm="McKinsey Global Institute",
        color="#94A3B8",
        title="McKinsey-Level Macro Impact Assessment",
        description=(
            "Fetches live macro indicators: US 10Y yield, VIX, US Dollar Index (DXY), "
            "S&P 500, Euro Stoxx 50, OMX Stockholm, Gold, Crude Oil, and TLT bond ETF — "
            "then deploys an institutional AI as a McKinsey Global Institute senior partner to "
            "assess how current macro conditions affect your specific portfolio, with "
            "sector rotation recommendations and a concrete 5-point action plan."
        ),
    )
    with st.form("mckinsey_macro_form"):
        st.markdown("**Portfolio Holdings** (ticker:weight%, one per line)")
        portfolio_text = st.text_area(
            "Holdings",
            value="AAPL:25\nMSFT:20\nNVDA:15\nJPM:15\nXOM:10\nGLD:15",
            height=160,
        )
        c1, c2 = st.columns(2)
        with c1:
            macro_concern = st.text_area(
                "Primary Macro Concern",
                placeholder="e.g. Worried about stagflation.",
                height=80,
            )
        with c2:
            geographic_exposure = st.selectbox(
                "Primary Geographic Exposure",
                ["US Domestic", "US + European (mixed)", "US + Swedish/Nordic",
                 "Global Diversified", "Emerging Markets Tilt"],
            )
        submitted = st.form_submit_button("🌐 Run Macro Assessment", type="primary")
    if not submitted:
        return
    holdings: Dict[str, float] = {}
    for line in portfolio_text.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
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
    if not holdings:
        st.error("No valid holdings parsed. Use TICKER:PERCENTAGE format.")
        return
    with st.spinner("Fetching live macro indicators…"):
        macro_data = fetch_macro_indicators()
    holding_info: Dict[str, Dict[str, Any]] = {}
    tickers = list(holdings.keys())
    bar     = st.progress(0, text="Fetching holding data…")
    for i, ticker in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
        holding_info[ticker] = fetch_stock_info(ticker)
        time.sleep(0.05)
    bar.empty()
    st.success(
        f"✓ Macro data: {len(macro_data)}/{len(MACRO_TICKERS)} indicators | "
        f"Holdings: {sum(1 for d in holding_info.values() if d)}/{len(tickers)}"
    )
    macro_lines: List[str] = [
        "LIVE MACRO INDICATOR DATA:",
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"{'Indicator':<40} {'Current':>10} {'1Y Ago':>10} "
        f"{'1Y Chg':>9} {'52W H':>10} {'52W L':>10}",
        "-" * 90,
    ]
    for ticker, d in macro_data.items():
        macro_lines.append(
            f"{d['name'][:38]:<40} "
            f"{d['current']:>10.4f} "
            f"{d['1y_ago']:>10.4f} "
            f"{d['1y_change']:>+9.2f}% "
            f"{d['52w_high']:>10.4f} "
            f"{d['52w_low']:>10.4f}"
        )
    macro_lines += ["", "PORTFOLIO HOLDINGS FUNDAMENTALS:"]
    for ticker, pct in holdings.items():
        d      = holding_info.get(ticker, {})
        name   = (d.get("name") or ticker)[:28]
        sector = d.get("sector", "Unknown")
        beta   = _safe_float(d.get("beta"), ".2f")
        macro_lines.append(
            f"  {ticker:<12} {name:<30} {pct:.0f}%  "
            f"Sector:{sector}  Beta:{beta}"
        )
    data_ctx = "\n".join(macro_lines)
    user_msg = (
        f"LIVE MACRO DATA:\n\n{data_ctx}\n\n"
        f"PRIMARY MACRO CONCERN: {macro_concern or 'General assessment'}\n"
        f"GEOGRAPHIC EXPOSURE: {geographic_exposure}\n\n"
        f"Deliver the complete McKinsey macro assessment as specified, "
        f"LEADING with the Current Regime Dashboard. All regime calls must "
        f"reference specific data values from the live indicators above. "
        f"The 5-point action plan must include position-specific recommendations "
        f"for this exact portfolio."
    )
    st.markdown("---")
    st.markdown(
        f"### McKinsey Macro Strategy Briefing  "
        f"<span style='color:#606870;font-size:12px;font-family:monospace;'>"
        f"{GROQ_MODEL} · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"</span>",
        unsafe_allow_html=True,
    )
    placeholder = st.empty()
    try:
        _stream_analysis(api_key, SYSTEM_PROMPT_MCKINSEY, user_msg, placeholder)
    except RuntimeError as e:
        st.error(f"Analysis failed: {e}")
        return
    _render_analysis_footer("McKinsey & Company / McKinsey Global Institute", GROQ_MODEL)


# ─── MAIN ──────────────────────────────────────────────────────────────────
def main() -> None:
    """
    Main entry point for the Wall Street Analyst Intelligence Suite.
    Validates Groq API key, renders 10 institutional analysis tabs.
    All analysis is AI-powered: live data → Groq LLaMA → streamed output.
    """
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div style='
            background:linear-gradient(135deg,#001a33 0%,#000d1a 50%,#0a001a 100%);
            border:1px solid rgba(0,180,255,0.18); border-radius:12px;
            padding:34px 36px 28px 36px; margin-bottom:20px;
        '>
            <div style='margin-bottom:14px;'>
                <span style='background:rgba(0,180,255,0.12);color:#00B4FF;
                             font-size:10px;font-family:monospace;font-weight:bold;
                             padding:4px 14px;border-radius:3px;
                             border:1px solid rgba(0,180,255,0.28);letter-spacing:2px;'>
                    LIVE AI · REAL DATA · LLAMA 3.3 70B · 10 FRAMEWORKS · FREE
                </span>
            </div>
            <h1 style='color:#F5ECD7;font-family:"Times New Roman",serif;
                       font-size:34px;font-weight:bold;margin:0 0 10px 0;'>
                Wall Street Analyst Intelligence Suite
            </h1>
            <p style='color:rgba(255,215,0,0.90);font-family:monospace;font-size:12px;
                      margin:0 0 14px 0;letter-spacing:1.5px;'>
                ◆ NOT PROMPTS. ACTUAL AI ANALYSIS. LIVE MARKET DATA. RIGHT NOW. 100% FREE.
            </p>
            <p style='color:#7888A0;font-size:14px;line-height:1.85;margin:0;
                      font-family:"Times New Roman",serif;max-width:700px;'>
                Each framework fetches LIVE financial data via yfinance/OpenBB,
                passes it to LLaMA 3.3 70B via Groq with an institutional system prompt,
                and streams a complete professional analysis directly into this page.
                Goldman Sachs screens real stocks. Morgan Stanley builds real DCF
                models. Citadel reads actual indicator values computed from live prices.
                Every number you see is derived from real market data. Powered by Groq free tier.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    if not api_key:
        st.error(
            "**GROQ_API_KEY not found.** Add it to your `.env` file:\n\n"
            "```\nGROQ_API_KEY=gsk_...\n```\n\n"
            "Then restart the Streamlit app. Get your FREE key at "
            "[console.groq.com](https://console.groq.com/keys)."
        )
        return
    if not _GROQ_AVAILABLE:
        st.error(
            "**groq package not installed.** Run in your venv:\n\n"
            "```bash\npip install groq\n```\n\nThen restart the app."
        )
        return
    st.success(
        f"✓ Connected · {GROQ_MODEL} · "
        f"Groq API Key configured · yfinance data live · FREE tier"
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("AI Model", "LLaMA 3.3 70B")
    with col2:
        st.metric("Frameworks Available", "10")
    with col3:
        st.metric("Data Source", "Live yfinance")
    with col4:
        st.metric("Cost", "Free")
    st.markdown("---")
    tabs = st.tabs([
        "🏦 Goldman Sachs",
        "📐 Morgan Stanley",
        "🛡️ Bridgewater",
        "📊 JPMorgan",
        "⚖️ BlackRock",
        "📈 Citadel",
        "💰 Harvard",
        "⚔️ Bain & Co",
        "🔬 Renaissance",
        "🌐 McKinsey",
    ])
    with tabs[0]:
        _render_tab_goldman(api_key)
    with tabs[1]:
        _render_tab_morgan_stanley(api_key)
    with tabs[2]:
        _render_tab_bridgewater(api_key)
    with tabs[3]:
        _render_tab_jpmorgan(api_key)
    with tabs[4]:
        _render_tab_blackrock(api_key)
    with tabs[5]:
        _render_tab_citadel(api_key)
    with tabs[6]:
        _render_tab_harvard_dividend(api_key)
    with tabs[7]:
        _render_tab_bain(api_key)
    with tabs[8]:
        _render_tab_renaissance(api_key)
    with tabs[9]:
        _render_tab_mckinsey(api_key)
    st.markdown("---")
    st.markdown(
        """
        <div style='background:rgba(255,82,82,0.06);
                    border:1px solid rgba(255,82,82,0.18);
                    border-radius:6px;padding:14px 20px;'>
            <p style='color:rgba(255,255,255,0.38);font-size:10px;
                      font-family:monospace;margin:0;line-height:1.8;'>
                ⚠ LEGAL DISCLAIMER: This platform uses LLaMA 3.3 70B via Groq and
                live market data to produce AI-generated financial analysis.
                Goldman Sachs, Morgan Stanley, Bridgewater Associates,
                JPMorgan Chase, BlackRock, Citadel LLC, Harvard Management
                Company, Bain & Company, Renaissance Technologies, and
                McKinsey & Company do not endorse, sponsor, or affiliate with
                this platform in any way. All analysis is AI-generated from
                publicly available market data. NOT financial advice. Verify
                all figures independently before making investment decisions.
                Past performance is not indicative of future results.
                Trading involves substantial risk of loss.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
    