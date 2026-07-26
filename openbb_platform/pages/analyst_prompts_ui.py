# pages/analyst_prompts_ui.py
# Wall Street Analyst Intelligence Suite
# 10 Professional-Grade AI Research Frameworks
#
# CONTENT: Verbatim from user specification. No text invented or paraphrased.
# FRAMING: "Claude can analyze any stock like a Wall Street analyst for free.
#            Here are 10 prompts they don't want you to see." — user specification.
# OPENBB: No calls on this page.
# DOMAIN VALUES: None — static content only.
#
# <- NEW [analyst_intelligence]: Full MPA page — 10 institutional AI prompt frameworks
#    with firm-specific color themes, copyable full prompts, sidebar filters, and hero.

import logging
import streamlit as st
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from translations import t, inject_rtl_css  # <- NEW [i18n]
from typing import Any, Dict, List

logger = logging.getLogger("AnalystIntelligenceUI")

# ─── GLOBAL TYPOGRAPHY ─────────────────────────────────────────────────────
# Times New Roman 16/22px · warm off-white palette — consistent with all pages.
GLOBAL_TYPOGRAPHY_CSS: str = """
<style>
html, body, [class*="css"], .stApp {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
    line-height: 1.75 !important;
}
p, span, li, td, th, label, div {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
    line-height: 1.75 !important;
}
h1, h2, h3, h4, h5, h6,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 22px !important;
    font-weight: bold !important;
    color: #F5ECD7 !important;
    line-height: 1.4 !important;
    margin-bottom: 0.5em !important;
}
[data-testid="stAppViewContainer"] h1 {
    font-size: 28px !important;
    color: #F5ECD7 !important;
    font-family: 'Times New Roman', Times, serif !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
    color: #B0A898 !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 20px !important;
    font-weight: bold !important;
    color: #F5ECD7 !important;
}
[data-testid="stMetricDelta"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
}
.stCaption, [data-testid="stCaptionContainer"] p, small, .caption {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 14px !important;
    color: #B0A898 !important;
    line-height: 1.6 !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] span, [data-testid="stSidebar"] div {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 15px !important;
    color: #E8E0D0 !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 18px !important;
    color: #F5ECD7 !important;
}
[data-testid="stButton"] button, .stButton button {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
}
[data-testid="stTabs"] button, .stTabs [role="tab"] {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    color: #E8E0D0 !important;
}
[data-testid="stAlert"] p, .stAlert p, .stInfo p,
.stSuccess p, .stWarning p, .stError p {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 16px !important;
    line-height: 1.75 !important;
}
[data-testid="stSelectbox"] label, [data-testid="stTextInput"] label,
[data-testid="stSlider"] label, [data-testid="stCheckbox"] label {
    font-family: 'Times New Roman', Times, serif !important;
    font-size: 15px !important;
    color: #E8E0D0 !important;
}
code, pre, .monospace {
    font-family: 'Courier New', Courier, monospace !important;
    font-size: 13px !important;
}
strong, b {
    font-family: 'Times New Roman', Times, serif !important;
    color: #F5ECD7 !important;
}
em, i {
    font-family: 'Times New Roman', Times, serif !important;
    color: #D4C9B8 !important;
}
hr { border-color: rgba(232,224,208,0.15) !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #000d1a; }
::-webkit-scrollbar-thumb { background: #3a3028; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #5a4a38; }
</style>
"""


# ─── PROMPT CARD DATA ──────────────────────────────────────────────────────
# All prompt text is verbatim from user specification.
# No content invented, paraphrased, or altered.
# firm, title, deliverables, full_prompt — exactly as provided by the user.

PROMPT_CARDS: List[Dict[str, Any]] = [
    {
        "number":           1,
        "firm":             "Goldman Sachs",
        "title":            "A Goldman Sachs-Level Stock Screener",
        "category":         "Equity Research",
        "complexity":       "Advanced",
        "color":            "#00B4FF",
        "icon":             "🏦",
        "analyst_role":     (
            "Senior Equity Analyst · 20 Years Experience · "
            "High-Net-Worth Client Division"
        ),
        "what_you_get": (
            "A professional equity research screening report with summary table — "
            "top 10 stocks ranked by your criteria with full fundamental analysis, "
            "sector-relative valuation, competitive moat ratings, and institutional-grade "
            "12-month price targets."
        ),
        "deliverables": [
            "Top 10 stocks matching your criteria with ticker symbols",
            "P/E ratio analysis compared to sector averages",
            "Revenue growth trends over the last 5 years",
            "Debt-to-equity health check for each pick",
            "Dividend yield and payout sustainability score",
            "Competitive moat rating (weak, moderate, strong)",
            "Bull case and bear case price targets for 12 months",
            "Risk rating on a scale of 1–10 with clear reasoning",
            "Entry price zones and stop-loss suggestions",
        ],
        "output_format":    "Professional equity research screening report with summary table",
        "input_placeholder": (
            "Your risk tolerance, investment amount, time horizon, and preferred sectors"
        ),
        "use_case": "Stock discovery · Portfolio building · Sector rotation decisions",
        "full_prompt": (
            "You are a senior equity analyst at Goldman Sachs with 20 years of experience "
            "screening stocks for high-net-worth clients.\n\n"
            "I need a complete stock screening framework for my investment goals.\n\n"
            "Analyze and provide:\n"
            "• Top 10 stocks matching my criteria with ticker symbols\n"
            "• P/E ratio analysis compared to sector averages\n"
            "• Revenue growth trends over the last 5 years\n"
            "• Debt-to-equity health check for each pick\n"
            "• Dividend yield and payout sustainability score\n"
            "• Competitive moat rating (weak, moderate, strong)\n"
            "• Bull case and bear case price targets for 12 months\n"
            "• Risk rating on a scale of 1-10 with clear reasoning\n"
            "• Entry price zones and stop-loss suggestions\n\n"
            "Format as a professional equity research screening report with summary table.\n\n"
            "My investment profile: [DESCRIBE YOUR RISK TOLERANCE, INVESTMENT AMOUNT, "
            "TIME HORIZON, AND PREFERRED SECTORS]"
        ),
    },
    {
        "number":           2,
        "firm":             "Morgan Stanley",
        "title":            "A Morgan Stanley-Style DCF Valuation Deep Dive",
        "category":         "Valuation",
        "complexity":       "Expert",
        "color":            "#FFD700",
        "icon":             "📐",
        "analyst_role":     (
            "VP-Level Investment Banker · Fortune 500 M&A Valuation Models · "
            "DCF Specialist"
        ),
        "what_you_get": (
            "A full investment banking valuation memo with tables and clear math — "
            "5-year DCF model, WACC calculation, dual terminal value methods, "
            "sensitivity table, and a definitive verdict on intrinsic value vs market price."
        ),
        "deliverables": [
            "5-year revenue projection with growth assumptions",
            "Operating margin estimates based on historical trends",
            "Free cash flow calculations year by year",
            "Weighted average cost of capital (WACC) estimate",
            "Terminal value using both exit multiple and perpetuity growth methods",
            "Sensitivity table showing fair value at different discount rates",
            "Comparison of DCF value vs current market price",
            "Clear verdict: undervalued, fairly valued, or overvalued",
            "Key assumptions that could break the model",
        ],
        "output_format":    "Investment banking valuation memo with tables and clear math",
        "input_placeholder": "Ticker symbol and company name",
        "use_case": "Pre-investment deep dive · Fair value discovery · M&A screening",
        "full_prompt": (
            "You are a VP-level investment banker at Morgan Stanley who builds valuation "
            "models for Fortune 500 M&A deals.\n\n"
            "I need a full discounted cash flow analysis for a specific stock.\n\n"
            "Build out:\n"
            "• 5-year revenue projection with growth assumptions\n"
            "• Operating margin estimates based on historical trends\n"
            "• Free cash flow calculations year by year\n"
            "• Weighted average cost of capital (WACC) estimate\n"
            "• Terminal value using both exit multiple and perpetuity growth methods\n"
            "• Sensitivity table showing fair value at different discount rates\n"
            "• Comparison of DCF value vs current market price\n"
            "• Clear verdict: undervalued, fairly valued, or overvalued\n"
            "• Key assumptions that could break the model\n\n"
            "Format as an investment banking valuation memo with tables and clear math.\n\n"
            "The stock I want valued: [ENTER TICKER SYMBOL AND COMPANY NAME]"
        ),
    },
    {
        "number":           3,
        "firm":             "Bridgewater Associates",
        "title":            "A Bridgewater-Inspired Risk Analysis Framework",
        "category":         "Risk Management",
        "complexity":       "Expert",
        "color":            "#00E5FF",
        "icon":             "🛡️",
        "analyst_role":     (
            "Senior Risk Analyst · Ray Dalio's Radical Transparency Principles · "
            "All-Weather Portfolio Framework"
        ),
        "what_you_get": (
            "A professional risk management report with heat map summary table — "
            "complete correlation and concentration analysis, recession stress test, "
            "tail risk scenarios, top-3 hedging strategies, and rebalancing allocations."
        ),
        "deliverables": [
            "Correlation analysis between your holdings",
            "Sector concentration risk with percentage breakdown",
            "Geographic exposure and currency risk factors",
            "Interest rate sensitivity for each position",
            "Recession stress test showing estimated drawdown",
            "Liquidity risk rating for each holding",
            "Single stock risk and position sizing recommendations",
            "Tail risk scenarios with probability estimates",
            "Hedging strategies to reduce your top 3 risks",
            "Rebalancing suggestions with specific allocation percentages",
        ],
        "output_format":    "Professional risk management report with heat map summary table",
        "input_placeholder": (
            "Your holdings with approximate percentages and total portfolio value"
        ),
        "use_case": "Portfolio stress testing · Risk reduction · Rebalancing decisions",
        "full_prompt": (
            "You are a senior risk analyst at Bridgewater Associates trained by Ray Dalio's "
            "principles of radical transparency in investing.\n\n"
            "I need a complete risk assessment of my current portfolio.\n\n"
            "Evaluate:\n"
            "• Correlation analysis between my holdings\n"
            "• Sector concentration risk with percentage breakdown\n"
            "• Geographic exposure and currency risk factors\n"
            "• Interest rate sensitivity for each position\n"
            "• Recession stress test showing estimated drawdown\n"
            "• Liquidity risk rating for each holding\n"
            "• Single stock risk and position sizing recommendations\n"
            "• Tail risk scenarios with probability estimates\n"
            "• Hedging strategies to reduce my top 3 risks\n"
            "• Rebalancing suggestions with specific allocation percentages\n\n"
            "Format as a professional risk management report with a heat map summary table.\n\n"
            "My current portfolio: [LIST YOUR HOLDINGS WITH APPROXIMATE PERCENTAGES "
            "AND TOTAL PORTFOLIO VALUE]"
        ),
    },
    {
        "number":           4,
        "firm":             "JPMorgan Chase",
        "title":            "A JPMorgan-Level Earnings Breakdown",
        "category":         "Earnings Analysis",
        "complexity":       "Advanced",
        "color":            "#FF9500",
        "icon":             "📊",
        "analyst_role":     (
            "Senior Equity Research Analyst · Institutional Earnings Preview Specialist · "
            "JPMorgan Chase"
        ),
        "what_you_get": (
            "A pre-earnings research brief with decision summary at the top — "
            "beat/miss history, Wall Street consensus estimates, segment breakdown, "
            "options-implied move, bull/bear scenarios, and a clear recommended play."
        ),
        "deliverables": [
            "Last 4 quarters earnings vs estimates (beat or miss history)",
            "Revenue and EPS consensus estimates for the upcoming quarter",
            "Key metrics Wall Street is watching for this specific company",
            "Segment-by-segment revenue breakdown and trends",
            "Management guidance from last earnings call summarized",
            "Options market implied move for earnings day",
            "Historical stock price reaction after last 4 earnings reports",
            "Bull case scenario and price impact estimate",
            "Bear case scenario and downside risk estimate",
            "Recommended play: buy before, sell before, or wait",
        ],
        "output_format":    "Pre-earnings research brief with decision summary at the top",
        "input_placeholder": "Company name and earnings date (if known)",
        "use_case": "Earnings preparation · Options strategy · Volatility positioning",
        "full_prompt": (
            "You are a senior equity research analyst at JPMorgan Chase who writes "
            "earnings previews for institutional investors.\n\n"
            "I need a complete earnings analysis before a company reports.\n\n"
            "Deliver:\n"
            "• Last 4 quarters earnings vs estimates (beat or miss history)\n"
            "• Revenue and EPS consensus estimates for the upcoming quarter\n"
            "• Key metrics Wall Street is watching for this specific company\n"
            "• Segment-by-segment revenue breakdown and trends\n"
            "• Management guidance from last earnings call summarized\n"
            "• Options market implied move for earnings day\n"
            "• Historical stock price reaction after last 4 earnings reports\n"
            "• Bull case scenario and price impact estimate\n"
            "• Bear case scenario and downside risk estimate\n"
            "• My recommended play: buy before, sell before, or wait\n\n"
            "Format as a pre-earnings research brief with a decision summary at the top.\n\n"
            "The company reporting earnings: "
            "[ENTER COMPANY NAME AND EARNINGS DATE IF KNOWN]"
        ),
    },
    {
        "number":           5,
        "firm":             "BlackRock",
        "title":            "A BlackRock-Style Portfolio Construction Model",
        "category":         "Portfolio Strategy",
        "complexity":       "Expert",
        "color":            "#A855F7",
        "icon":             "⚖️",
        "analyst_role":     (
            "Senior Portfolio Strategist · $500M+ Multi-Asset Institutional Portfolios · "
            "BlackRock"
        ),
        "what_you_get": (
            "A professional investment policy document with allocation pie chart description — "
            "custom portfolio built from scratch with specific ETF tickers, DCA plan, "
            "rebalancing rules, tax strategy, and a one-page investment policy statement."
        ),
        "deliverables": [
            "Exact asset allocation with percentages across stocks, bonds, alternatives",
            "Specific ETF or fund recommendations for each category with ticker symbols",
            "Core holdings vs satellite positions clearly labeled",
            "Expected annual return range based on historical data",
            "Expected maximum drawdown in a bad year",
            "Rebalancing schedule and trigger rules",
            "Tax efficiency strategy for your account type",
            "Dollar cost averaging plan if you invest monthly",
            "Benchmark to measure your performance against",
            "One-page investment policy statement to follow",
        ],
        "output_format": (
            "Professional investment policy document with allocation pie chart description"
        ),
        "input_placeholder": (
            "Your age, income, savings, goals, risk tolerance, and account type "
            "(401K, IRA, or taxable)"
        ),
        "use_case": "Portfolio creation from scratch · IPS drafting · Long-term wealth building",
        "full_prompt": (
            "You are a senior portfolio strategist at BlackRock managing multi-asset "
            "portfolios worth $500M+ for institutional clients.\n\n"
            "I need a custom investment portfolio built from scratch for my situation.\n\n"
            "Create:\n"
            "• Exact asset allocation with percentages across stocks, bonds, alternatives\n"
            "• Specific ETF or fund recommendations for each category with ticker symbols\n"
            "• Core holdings vs satellite positions clearly labeled\n"
            "• Expected annual return range based on historical data\n"
            "• Expected maximum drawdown in a bad year\n"
            "• Rebalancing schedule and trigger rules\n"
            "• Tax efficiency strategy for my account type\n"
            "• Dollar cost averaging plan if I invest monthly\n"
            "• Benchmark to measure my performance against\n"
            "• One-page investment policy statement I can follow\n\n"
            "Format as a professional investment policy document with an allocation "
            "pie chart description.\n\n"
            "My details: [DESCRIBE YOUR AGE, INCOME, SAVINGS, GOALS, RISK TOLERANCE, "
            "AND ACCOUNT TYPE — 401K, IRA, TAXABLE]"
        ),
    },
    {
        "number":           6,
        "firm":             "Citadel",
        "title":            "A Citadel-Grade Technical Analysis System",
        "category":         "Technical Analysis",
        "complexity":       "Advanced",
        "color":            "#00FF88",
        "icon":             "📈",
        "analyst_role":     (
            "Senior Quantitative Trader · Technical Analysis + Statistical Models · "
            "Citadel"
        ),
        "what_you_get": (
            "A technical analysis report card with a clear trade plan summary — "
            "multi-timeframe trend, all major indicators including harmonic patterns, "
            "Elliott waves, and Ichimoku, with exact entry, stop-loss, target, and R:R ratio."
        ),
        "deliverables": [
            "Current trend direction on daily, weekly, and monthly timeframes",
            "Key support and resistance levels with exact price points",
            "Moving average analysis (50-day, 100-day, 200-day) and crossover signals",
            "RSI, MACD, Bollinger Bands, harmonic patterns, Elliott waves, price action, "
            "and Ichimoku cloud with plain-English interpretation",
            "Volume trend analysis — buyer vs seller strength signal",
            "Chart pattern identification (head & shoulders, cup & handle, etc.)",
            "Fibonacci retracement levels for potential bounce zones",
            "Ideal entry price, stop-loss level, and profit target",
            "Risk-to-reward ratio for the current setup",
            "Confidence rating: strong buy, buy, neutral, sell, or strong sell",
        ],
        "output_format":    "Technical analysis report card with clear trade plan summary",
        "input_placeholder": "Ticker symbol and your current position (if any)",
        "use_case": "Trade entry/exit timing · Pattern confirmation · Multi-timeframe analysis",
        "full_prompt": (
            "You are a senior quantitative trader at Citadel who combines technical "
            "analysis with statistical models to time entries and exits.\n\n"
            "I need a full technical analysis breakdown of a stock.\n\n"
            "Analyze:\n"
            "• Current trend direction on daily, weekly, and monthly timeframes\n"
            "• Key support and resistance levels with exact price points\n"
            "• Moving average analysis (50-day, 100-day, 200-day) and crossover signals\n"
            "• RSI, MACD, Bollinger Band, Harmonic patterns, Elliot waves, Price action "
            "and Ichimoku cloud strategy readings with plain-English interpretation\n"
            "• Volume trend analysis and what it signals about buyer vs seller strength\n"
            "• Chart pattern identification (head and shoulders, cup and handle, etc.)\n"
            "• Fibonacci retracement levels for potential bounce zones\n"
            "• Ideal entry price, stop-loss level, and profit target\n"
            "• Risk-to-reward ratio for the current setup\n"
            "• Confidence rating: strong buy, buy, neutral, sell, strong sell\n\n"
            "Format as a technical analysis report card with a clear trade plan summary.\n\n"
            "The stock to analyze: "
            "[ENTER TICKER SYMBOL AND YOUR CURRENT POSITION IF ANY]"
        ),
    },
    {
        "number":           7,
        "firm":             "Harvard Endowment",
        "title":            "A Harvard Endowment-Inspired Dividend Strategy",
        "category":         "Income Investing",
        "complexity":       "Intermediate",
        "color":            "#FF6B6B",
        "icon":             "💰",
        "analyst_role":     (
            "Chief Investment Strategist · Harvard $50B Endowment Fund · "
            "Income-Generating Equity Specialist"
        ),
        "what_you_get": (
            "A dividend portfolio blueprint with an income projection table — "
            "15–20 ranked picks from safest to most aggressive, DRIP compounding "
            "projection over 10 years, payout ratio flags, and tax implications."
        ),
        "deliverables": [
            "15–20 dividend stock picks with ticker symbols and current yield",
            "Dividend safety score for each stock (1–10 scale)",
            "Consecutive years of dividend growth for each pick",
            "Payout ratio analysis to flag any unsustainable dividends",
            "Monthly income projection based on your investment amount",
            "Sector diversification breakdown to avoid concentration",
            "Dividend growth rate estimate for the next 5 years",
            "DRIP reinvestment projection showing compounding over 10 years",
            "Tax implications summary for dividends in your account type",
            "Ranked list from safest to most aggressive picks",
        ],
        "output_format":    "Dividend portfolio blueprint with income projection table",
        "input_placeholder": (
            "Total investment amount, monthly income goal, account type, and tax bracket"
        ),
        "use_case": "Passive income generation · Retirement planning · Dividend growth investing",
        "full_prompt": (
            "You are the chief investment strategist for Harvard's $50B endowment fund "
            "specializing in income-generating equity strategies.\n\n"
            "I need a dividend income portfolio that generates reliable passive income.\n\n"
            "Build:\n"
            "• 15-20 dividend stock picks with ticker symbols and current yield\n"
            "• Dividend safety score for each stock (1-10 scale)\n"
            "• Consecutive years of dividend growth for each pick\n"
            "• Payout ratio analysis to flag any unsustainable dividends\n"
            "• Monthly income projection based on my investment amount\n"
            "• Sector diversification breakdown to avoid concentration\n"
            "• Dividend growth rate estimate for the next 5 years\n"
            "• DRIP reinvestment projection showing compounding over 10 years\n"
            "• Tax implications summary for dividends in my account type\n"
            "• Ranked list from safest to most aggressive picks\n\n"
            "Format as a dividend portfolio blueprint with an income projection table.\n\n"
            "My situation: [ENTER YOUR TOTAL INVESTMENT AMOUNT, MONTHLY INCOME GOAL, "
            "ACCOUNT TYPE, AND TAX BRACKET]"
        ),
    },
    {
        "number":           8,
        "firm":             "Bain & Company",
        "title":            "A Bain-Style Competitive Advantage Analysis",
        "category":         "Competitive Intelligence",
        "complexity":       "Advanced",
        "color":            "#FF5252",
        "icon":             "⚔️",
        "analyst_role":     (
            "Senior Partner · Bain & Company · Competitive Strategy for "
            "Major Investment Funds"
        ),
        "what_you_get": (
            "A Bain-style competitive strategy deck summary with comparison tables — "
            "full competitive landscape identifying the single best stock to buy "
            "in a sector, with moat analysis, SWOT on the top 2, and 12-month catalysts."
        ),
        "deliverables": [
            "Top 5–7 competitors in the sector with market cap comparison",
            "Revenue and profit margin comparison in a table format",
            "Competitive moat analysis for each company (brand, cost, network, switching)",
            "Market share trends over the last 3 years",
            "Management quality rating based on capital allocation track record",
            "Innovation pipeline and R&D spending comparison",
            "Biggest threats to the sector (regulation, disruption, macro)",
            "SWOT analysis for the top 2 companies",
            "Single best stock pick with a clear rationale",
            "Catalysts that could move the winner stock in the next 12 months",
        ],
        "output_format": (
            "Bain-style competitive strategy deck summary with comparison tables"
        ),
        "input_placeholder": "Industry or sector name",
        "use_case": (
            "Sector selection · Best-of-breed stock picking · Competitive positioning"
        ),
        "full_prompt": (
            "You are a senior partner at Bain & Company conducting a competitive "
            "strategy analysis for a major investment fund evaluating an industry.\n\n"
            "I need a full competitive landscape report to find the best stock to "
            "buy in a sector.\n\n"
            "Provide:\n"
            "• Top 5-7 competitors in the sector with market cap comparison\n"
            "• Revenue and profit margin comparison in a table format\n"
            "• Competitive moat analysis for each company "
            "(brand, cost, network, switching)\n"
            "• Market share trends over the last 3 years\n"
            "• Management quality rating based on capital allocation track record\n"
            "• Innovation pipeline and R&D spending comparison\n"
            "• Biggest threats to the sector (regulation, disruption, macro)\n"
            "• SWOT analysis for the top 2 companies\n"
            "• My single best stock pick with a clear rationale\n"
            "• Catalysts that could move the winner stock in the next 12 months\n\n"
            "Format as a Bain-style competitive strategy deck summary with "
            "comparison tables.\n\n"
            "The sector I want analyzed: [ENTER INDUSTRY OR SECTOR NAME]"
        ),
    },
    {
        "number":           9,
        "firm":             "Renaissance Technologies",
        "title":            "The Renaissance Technologies Pattern Finder",
        "category":         "Quantitative Analysis",
        "complexity":       "Expert",
        "color":            "#00D2FF",
        "icon":             "🔬",
        "analyst_role":     (
            "Quantitative Researcher · Statistical Edge Discovery · Anomaly Detection · "
            "Renaissance Technologies"
        ),
        "what_you_get": (
            "A quantitative research memo with data tables and pattern summaries — "
            "seasonal and day-of-week edges, event correlations, institutional flow, "
            "short squeeze analysis, unusual options activity, and statistical edge summary."
        ),
        "deliverables": [
            "Seasonal patterns: best and worst months historically",
            "Day-of-week performance patterns if any exist",
            "Correlation with major market events (Fed meetings, CPI reports)",
            "Insider buying and selling patterns from recent filings",
            "Institutional ownership trend: are big funds buying or selling",
            "Short interest analysis and squeeze potential",
            "Unusual options activity signals worth watching",
            "Price behavior around earnings (pre-run, post-gap patterns)",
            "Sector rotation signals that affect this stock",
            "Statistical edge summary: quantifiable advantage identification",
        ],
        "output_format": (
            "Quantitative research memo with data tables and pattern summaries"
        ),
        "input_placeholder": "Ticker symbol and time period you care about",
        "use_case": "Statistical edge discovery · Timing optimization · Institutional flow tracking",
        "full_prompt": (
            "You are a quantitative researcher at Renaissance Technologies using "
            "data-driven methods to find statistical edges in the stock market.\n\n"
            "I need you to identify hidden patterns and anomalies in a stock's behavior.\n\n"
            "Research:\n"
            "• Seasonal patterns: best and worst months historically\n"
            "• Day-of-week performance patterns if any exist\n"
            "• Correlation with major market events (Fed meetings, CPI reports)\n"
            "• Insider buying and selling patterns from recent filings\n"
            "• Institutional ownership trend: are big funds buying or selling\n"
            "• Short interest analysis and squeeze potential\n"
            "• Unusual options activity signals worth watching\n"
            "• Price behavior around earnings (pre-run, post-gap patterns)\n"
            "• Sector rotation signals that affect this stock\n"
            "• Statistical edge summary: what gives this stock a quantifiable advantage\n\n"
            "Format as a quantitative research memo with data tables and "
            "pattern summaries.\n\n"
            "The stock to investigate: "
            "[ENTER TICKER SYMBOL AND TIME PERIOD YOU CARE ABOUT]"
        ),
    },
    {
        "number":           10,
        "firm":             "McKinsey Global Institute",
        "title":            "A McKinsey-Level Macro Impact Assessment",
        "category":         "Macro Strategy",
        "complexity":       "Expert",
        "color":            "#94A3B8",
        "icon":             "🌐",
        "analyst_role":     (
            "Senior Partner · McKinsey's Global Institute · "
            "Sovereign Wealth Fund Macro Strategy Advisor"
        ),
        "what_you_get": (
            "An executive macro strategy briefing with a clear action plan — "
            "full macroeconomic impact analysis on your specific holdings with "
            "sector rotation recommendations, concrete portfolio adjustments, and a timeline."
        ),
        "deliverables": [
            "Interest rate environment impact on growth vs value stocks",
            "Inflation trend analysis and which sectors benefit or suffer",
            "GDP growth forecast and implications for corporate earnings",
            "US dollar strength impact on international vs domestic holdings",
            "Employment data trends and consumer spending implications",
            "Federal Reserve policy outlook for the next 6–12 months",
            "Global risk factors (geopolitics, trade wars, supply chains)",
            "Sector rotation recommendation based on current economic cycle",
            "Specific portfolio adjustments to consider right now",
            "Timeline: when macro factors will most likely impact markets",
        ],
        "output_format": "Executive macro strategy briefing with a clear action plan",
        "input_placeholder": (
            "Your portfolio holdings and your biggest concern about the economy"
        ),
        "use_case": (
            "Macro positioning · Sector rotation · Portfolio adjustment under uncertainty"
        ),
        "full_prompt": (
            "You are a senior partner at McKinsey's Global Institute who advises "
            "sovereign wealth funds on how macroeconomic trends affect equity markets.\n\n"
            "I need a macro analysis showing how current economic conditions "
            "affect my portfolio.\n\n"
            "Analyze:\n"
            "• Current interest rate environment and its impact on growth vs value stocks\n"
            "• Inflation trend analysis and which sectors benefit or suffer\n"
            "• GDP growth forecast and what it means for corporate earnings\n"
            "• US dollar strength impact on international vs domestic holdings\n"
            "• Employment data trends and consumer spending implications\n"
            "• Federal Reserve policy outlook for the next 6-12 months\n"
            "• Global risk factors (geopolitics, trade wars, supply chains)\n"
            "• Sector rotation recommendation based on current economic cycle\n"
            "• Specific portfolio adjustments I should consider right now\n"
            "• Timeline: when these macro factors will most likely impact markets\n\n"
            "Format as an executive macro strategy briefing with a clear action plan.\n\n"
            "My current holdings: [LIST YOUR PORTFOLIO AND DESCRIBE YOUR BIGGEST "
            "CONCERN ABOUT THE ECONOMY]"
        ),
    },
]


# ─── HELPER ────────────────────────────────────────────────────────────────

def _build_deliverables_html(deliverables: List[str], color: str) -> str:
    """
    Builds the numbered deliverables list as an HTML string for embedding
    inside a card's markdown block.

    Args:
        deliverables: List of deliverable description strings.
        color:        Hex color string for the number labels.

    Returns:
        HTML string rendering a styled numbered list.
    """
    rows: str = ""
    for i, item in enumerate(deliverables, 1):
        rows += (
            f"<div style='display:flex; align-items:flex-start; gap:10px; "
            f"padding:5px 0; border-bottom:1px solid rgba(255,255,255,0.035);'>"
            f"<span style='color:{color}; font-weight:bold; font-family:monospace; "
            f"font-size:11px; min-width:24px; flex-shrink:0; padding-top:2px;'>"
            f"{i:02d}.</span>"
            f"<span style='color:#B0B8C4; font-size:12px; line-height:1.55;'>"
            f"{item}</span>"
            f"</div>"
        )
    return rows


# ─── RENDER: HERO ──────────────────────────────────────────────────────────

def render_hero_section() -> None:
    """
    Renders the full-width gradient hero banner with headline, tagline,
    description, and all 10 firm badges.
    """
    firm_badges: List[Dict[str, str]] = [
        {"label": "Goldman Sachs",            "color": "#00B4FF"},
        {"label": "Morgan Stanley",           "color": "#FFD700"},
        {"label": "Bridgewater Associates",   "color": "#00E5FF"},
        {"label": "JPMorgan Chase",           "color": "#FF9500"},
        {"label": "BlackRock",                "color": "#A855F7"},
        {"label": "Citadel",                  "color": "#00FF88"},
        {"label": "Harvard Endowment",        "color": "#FF6B6B"},
        {"label": "Bain & Company",           "color": "#FF5252"},
        {"label": "Renaissance Technologies", "color": "#00D2FF"},
        {"label": "McKinsey Global Institute","color": "#94A3B8"},
    ]
    badges_html: str = ""
    for badge in firm_badges:
        c: str = badge["color"]
        badges_html += (
            f"<span style='color:{c}; font-size:11px; font-family:monospace; "
            f"background:{c}14; padding:3px 10px; border-radius:3px; "
            f"border:1px solid {c}33;'>{badge['label']}</span>"
        )

    st.markdown(
        f"""
        <div style='
            background: linear-gradient(135deg, #001a33 0%, #000d1a 45%, #0a001a 100%);
            border: 1px solid rgba(0,180,255,0.18);
            border-radius: 12px;
            padding: 42px 40px 34px 40px;
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        '>
            <!-- Decorative ambient light -->
            <div style='position:absolute; top:-60px; right:-60px; width:260px; height:260px;
                        background:radial-gradient(circle, rgba(0,180,255,0.07) 0%,
                        transparent 70%); border-radius:50%; pointer-events:none;'></div>
            <div style='position:absolute; bottom:-80px; left:28%; width:340px; height:340px;
                        background:radial-gradient(circle, rgba(168,85,247,0.05) 0%,
                        transparent 70%); border-radius:50%; pointer-events:none;'></div>
            <div style='position:absolute; top:50%; left:-40px; width:180px; height:180px;
                        background:radial-gradient(circle, rgba(0,229,255,0.04) 0%,
                        transparent 70%); border-radius:50%; pointer-events:none;'></div>

            <!-- Top badge -->
            <div style='margin-bottom:18px;'>
                <span style='background:rgba(0,180,255,0.12); color:#00B4FF;
                             font-size:10px; font-family:monospace; font-weight:bold;
                             padding:4px 14px; border-radius:3px;
                             border:1px solid rgba(0,180,255,0.28); letter-spacing:2px;'>
                    INSTITUTIONAL INTELLIGENCE SUITE &nbsp;·&nbsp;
                    WALL STREET RESEARCH FRAMEWORKS &nbsp;·&nbsp; FREE ACCESS
                </span>
            </div>

            <!-- Headline -->
            <h1 style='color:#F5ECD7; font-family:"Times New Roman",serif;
                       font-size:38px; font-weight:bold; margin:0 0 10px 0;
                       line-height:1.2;'>
                Claude Can Analyze Any Stock Like a<br>
                <span style='color:#00B4FF;'>Wall Street Analyst</span> — For Free
            </h1>

            <!-- Tagline -->
            <p style='color:rgba(255,215,0,0.90); font-family:monospace; font-size:13px;
                      font-weight:bold; margin:0 0 18px 0; letter-spacing:1.5px;'>
                ◆ HERE ARE 10 PROMPTS THEY DON'T WANT YOU TO SEE
            </p>

            <!-- Description -->
            <p style='color:#A8B4C0; font-size:15px; line-height:1.85; margin:0 0 28px 0;
                      max-width:760px; font-family:"Times New Roman",serif;'>
                The exact analytical frameworks used by the world's most prestigious
                financial institutions — now accessible as AI prompt templates.
                Goldman Sachs stock screening. Morgan Stanley DCF models.
                Bridgewater risk analysis. Citadel technical analysis with Elliott waves,
                harmonics, and Ichimoku. Copy any prompt, fill in your details,
                and deploy to Claude or any AI for institutional-grade research in seconds.
            </p>

            <!-- Firm badges -->
            <div style='display:flex; gap:8px; flex-wrap:wrap; align-items:center;'>
                {badges_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── RENDER: STATS BAR ─────────────────────────────────────────────────────

def render_stats_bar() -> None:
    """Renders the four-column quick-stats metrics row."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Research Frameworks", value="10")
    with col2:
        st.metric(label="Wall Street Firms Modelled", value="10")
    with col3:
        st.metric(label="Deliverables Across All Prompts", value="100+")
    with col4:
        st.metric(label="Cost to Access", value="$0")
    st.markdown("---")


# ─── RENDER: HOW TO USE ────────────────────────────────────────────────────

def render_how_to_use() -> None:
    """
    Renders the three-step instructional guide for using these frameworks.
    """
    st.markdown(
        """
        <div style='
            background: linear-gradient(135deg, #001820 0%, #000d1a 100%);
            border: 1px solid rgba(0,229,255,0.14);
            border-left: 4px solid #00E5FF;
            border-radius: 8px;
            padding: 22px 28px;
            margin-bottom: 28px;
        '>
            <p style='color:#00E5FF; font-family:monospace; font-size:10px;
                      font-weight:bold; letter-spacing:2px; margin:0 0 16px 0;'>
                ◆ THREE STEPS TO INSTITUTIONAL-GRADE AI ANALYSIS
            </p>
            <div style='display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px;'>
                <div>
                    <div style='display:flex; align-items:center; gap:10px; margin-bottom:8px;'>
                        <span style='background:#FFD70020; color:#FFD700;
                                     font-size:16px; font-weight:bold; font-family:monospace;
                                     padding:4px 10px; border-radius:4px;
                                     border:1px solid #FFD70040;'>01</span>
                        <span style='color:#FFD700; font-size:11px; font-family:monospace;
                                     font-weight:bold; letter-spacing:1px;'>CHOOSE</span>
                    </div>
                    <p style='color:#A0A8B4; font-size:12px; line-height:1.7; margin:0;
                              font-family:"Times New Roman",serif;'>
                        Browse the 10 frameworks below and select the one that matches
                        your current research need. Each serves a distinct analytical
                        purpose modelled on a specific institution.
                    </p>
                </div>
                <div>
                    <div style='display:flex; align-items:center; gap:10px; margin-bottom:8px;'>
                        <span style='background:#00FF8820; color:#00FF88;
                                     font-size:16px; font-weight:bold; font-family:monospace;
                                     padding:4px 10px; border-radius:4px;
                                     border:1px solid #00FF8840;'>02</span>
                        <span style='color:#00FF88; font-size:11px; font-family:monospace;
                                     font-weight:bold; letter-spacing:1px;'>COPY</span>
                    </div>
                    <p style='color:#A0A8B4; font-size:12px; line-height:1.7; margin:0;
                              font-family:"Times New Roman",serif;'>
                        Expand the <em>Copy Full Prompt</em> section at the bottom
                        of any card. Click the copy icon (⧉) in the top-right corner
                        of the code block. The entire prompt is instantly on your clipboard.
                    </p>
                </div>
                <div>
                    <div style='display:flex; align-items:center; gap:10px; margin-bottom:8px;'>
                        <span style='background:#00B4FF20; color:#00B4FF;
                                     font-size:16px; font-weight:bold; font-family:monospace;
                                     padding:4px 10px; border-radius:4px;
                                     border:1px solid #00B4FF40;'>03</span>
                        <span style='color:#00B4FF; font-size:11px; font-family:monospace;
                                     font-weight:bold; letter-spacing:1px;'>DEPLOY</span>
                    </div>
                    <p style='color:#A0A8B4; font-size:12px; line-height:1.7; margin:0;
                              font-family:"Times New Roman",serif;'>
                        Paste into Claude, ChatGPT, or any AI assistant. Replace the
                        <em>[BRACKETED PLACEHOLDER]</em> at the bottom with your
                        specific details. Send. Receive institutional-grade analysis
                        in seconds — completely free.
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── RENDER: SIDEBAR FILTER ────────────────────────────────────────────────

def render_filter_bar(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Renders the sidebar filter controls and returns the filtered list of cards.

    Args:
        cards: The full PROMPT_CARDS list.

    Returns:
        Filtered list of card dicts matching the sidebar selections.
    """
    all_categories: List[str] = [c["category"] for c in cards]
    all_complexities: List[str] = ["Intermediate", "Advanced", "Expert"]

    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 Filter Frameworks**")

    selected_categories: List[str] = st.sidebar.multiselect(
        "Category",
        options=all_categories,
        default=all_categories,
    )

    selected_complexities: List[str] = st.sidebar.multiselect(
        "Complexity Level",
        options=all_complexities,
        default=all_complexities,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**📋 Quick Reference**")
    for card in cards:
        c: str = card["color"]
        n: int = card["number"]
        st.sidebar.markdown(
            f"<span style='color:{c}; font-size:12px;'>#{n:02d}</span> "
            f"<span style='color:#A0A8B0; font-size:12px;'>{card['firm']}</span>",
            unsafe_allow_html=True,
        )

    filtered: List[Dict[str, Any]] = [
        c for c in cards
        if c["category"] in selected_categories
        and c["complexity"] in selected_complexities
    ]

    total:   int = len(cards)
    visible: int = len(filtered)
    if visible < total:
        st.info(
            f"Showing {visible} of {total} frameworks. "
            "Adjust the sidebar filters to show more."
        )

    return filtered


# ─── RENDER: SINGLE PROMPT CARD ────────────────────────────────────────────

def render_prompt_card(card: Dict[str, Any]) -> None:
    """
    Renders a single Wall Street analyst prompt card with:
    · Firm-colored header with badges, icon, title, and analyst role
    · What-you-get description block
    · Full numbered deliverables list
    · Input required and output format indicators
    · Use case footer
    · Expandable full copyable prompt (st.code with built-in copy button)

    Args:
        card: A dict from PROMPT_CARDS with all required keys.
    """
    number:            int        = card["number"]
    firm:              str        = card["firm"]
    title:             str        = card["title"]
    category:          str        = card["category"]
    complexity:        str        = card["complexity"]
    color:             str        = card["color"]
    icon:              str        = card["icon"]
    analyst_role:      str        = card["analyst_role"]
    what_you_get:      str        = card["what_you_get"]
    deliverables:      List[str]  = card["deliverables"]
    output_format:     str        = card["output_format"]
    input_placeholder: str        = card["input_placeholder"]
    use_case:          str        = card["use_case"]
    full_prompt:       str        = card["full_prompt"]

    deliverables_html: str = _build_deliverables_html(deliverables, color)

    complexity_color_map: Dict[str, str] = {
        "Intermediate": "#00E676",
        "Advanced":     "#FFD700",
        "Expert":       "#FF5252",
    }
    complexity_color: str = complexity_color_map.get(complexity, "#888888")

    st.markdown(
        f"""
        <div style='
            background: linear-gradient(145deg, {color}07 0%, #000d1a 55%, #000508 100%);
            border: 1px solid {color}30;
            border-left: 5px solid {color};
            border-radius: 10px;
            padding: 26px 30px 22px 30px;
            margin-bottom: 6px;
            box-shadow: 0 6px 32px {color}0C, inset 0 1px 0 rgba(255,255,255,0.03);
        '>

            <!-- ── BADGE ROW ─────────────────────────────────────── -->
            <div style='display:flex; gap:8px; margin-bottom:18px;
                        flex-wrap:wrap; align-items:center;'>
                <span style='
                    background:{color}1A; color:{color}; font-size:10px;
                    font-family:monospace; font-weight:bold;
                    padding:3px 12px; border-radius:3px;
                    border:1px solid {color}50; letter-spacing:1.8px;
                '>#{number:02d} &nbsp;·&nbsp; {firm.upper()}</span>

                <span style='
                    background:rgba(255,255,255,0.04); color:#8898A8;
                    font-size:10px; font-family:monospace;
                    padding:3px 10px; border-radius:3px;
                    border:1px solid rgba(255,255,255,0.08); letter-spacing:0.8px;
                '>{category.upper()}</span>

                <span style='
                    background:{complexity_color}14; color:{complexity_color};
                    font-size:10px; font-family:monospace;
                    padding:3px 10px; border-radius:3px;
                    border:1px solid {complexity_color}30; letter-spacing:0.8px;
                '>{complexity.upper()}</span>

                <span style='
                    margin-left:auto; font-size:28px; line-height:1;
                    filter:drop-shadow(0 0 6px {color}66);
                '>{icon}</span>
            </div>

            <!-- ── TITLE + ROLE ──────────────────────────────────── -->
            <h3 style='
                color:{color}; font-family:"Times New Roman",serif;
                font-size:21px; font-weight:bold;
                margin:0 0 5px 0; line-height:1.25;
                text-shadow: 0 0 24px {color}44;
            '>{title}</h3>
            <p style='
                color:#606870; font-size:11px; font-family:monospace;
                margin:0 0 18px 0; letter-spacing:0.3px;
            '>{analyst_role}</p>

            <!-- ── WHAT YOU GET ──────────────────────────────────── -->
            <div style='
                padding:14px 16px; margin-bottom:20px;
                background:rgba(255,255,255,0.025);
                border-radius:6px;
                border-left:3px solid {color}55;
            '>
                <p style='
                    color:#C0C8D0; font-size:13px; line-height:1.75; margin:0;
                    font-family:"Times New Roman",serif;
                '>{what_you_get}</p>
            </div>

            <!-- ── DELIVERABLES HEADER ───────────────────────────── -->
            <p style='
                color:{color}; font-size:10px; font-family:monospace;
                font-weight:bold; letter-spacing:2px; margin:0 0 10px 0;
            '>◆ &nbsp;{len(deliverables)} DELIVERABLES INCLUDED</p>

            <!-- ── DELIVERABLES LIST ─────────────────────────────── -->
            {deliverables_html}

            <!-- ── INPUT REQUIRED ───────────────────────────────── -->
            <div style='
                margin-top:20px; padding:11px 16px;
                background:rgba(255,215,0,0.05);
                border:1px solid rgba(255,215,0,0.18);
                border-radius:5px;
            '>
                <span style='
                    color:#FFD700; font-size:10px; font-family:monospace;
                    font-weight:bold; letter-spacing:1.2px;
                '>✏️ &nbsp;YOU PROVIDE: </span>
                <span style='
                    color:#C8A030; font-size:12px;
                    font-family:"Times New Roman",serif;
                '>{input_placeholder}</span>
            </div>

            <!-- ── OUTPUT FORMAT ────────────────────────────────── -->
            <div style='
                margin-top:8px; padding:9px 16px;
                background:rgba(255,255,255,0.025);
                border:1px solid rgba(255,255,255,0.07);
                border-radius:5px;
            '>
                <span style='
                    color:#505868; font-size:10px; font-family:monospace;
                    font-weight:bold; letter-spacing:1.2px;
                '>📄 &nbsp;OUTPUT FORMAT: </span>
                <span style='
                    color:#808898; font-size:12px;
                    font-family:"Times New Roman",serif;
                '>{output_format}</span>
            </div>

            <!-- ── USE CASE ─────────────────────────────────────── -->
            <p style='
                color:#404850; font-size:11px; font-family:monospace;
                margin:12px 0 0 0; letter-spacing:0.3px;
            '>🎯 &nbsp;USE CASE: {use_case}</p>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Full copyable prompt (st.code provides built-in ⧉ copy button) ──
    with st.expander(
        f"📋 &nbsp; Copy Full Prompt #{number:02d} — {firm}",
        expanded=False,
    ):
        st.markdown(
            f"<p style='color:#606870; font-size:11px; font-family:monospace; "
            f"margin:0 0 10px 0; line-height:1.6;'>"
            f"Click the <strong style='color:#E8E0D0;'>⧉ copy</strong> button "
            f"in the top-right corner of the code block below. "
            f"Paste directly into Claude, ChatGPT, Gemini, or any AI assistant. "
            f"Then replace the <em style='color:#FFD700;'>[BRACKETED PLACEHOLDER]</em> "
            f"at the bottom with your specific details before sending.</p>",
            unsafe_allow_html=True,
        )
        st.code(full_prompt, language=None)
        st.markdown(
            f"<p style='color:#404050; font-size:11px; font-family:monospace; "
            f"margin:8px 0 0 0;'>"
            f"Tip: the more detail you provide in the placeholder, "
            f"the more precise and actionable the output will be.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)


# ─── RENDER: FOOTER ────────────────────────────────────────────────────────

def render_footer() -> None:
    """Renders the legal disclaimer footer at the bottom of the page."""
    st.markdown("---")
    st.markdown(
        """
        <div style='
            background:rgba(255,82,82,0.06);
            border:1px solid rgba(255,82,82,0.18);
            border-radius:6px;
            padding:14px 20px;
            margin-top:6px;
        '>
            <p style='
                color:rgba(255,255,255,0.38); font-size:10px;
                font-family:monospace; margin:0; line-height:1.8;
            '>
                ⚠️ DISCLAIMER: These AI prompt frameworks are for educational and
                informational purposes only. Goldman Sachs, Morgan Stanley,
                Bridgewater Associates, JPMorgan Chase, BlackRock, Citadel LLC,
                Harvard Management Company, Bain & Company, Renaissance Technologies,
                and McKinsey & Company do not endorse, sponsor, or affiliate with
                this platform or these prompt templates in any way. These frameworks
                are inspired by publicly known methodologies and analytical styles
                associated with these institutions — they are not proprietary documents
                from those firms. All AI-generated analysis produced using these prompts
                should be independently verified before making any investment decision.
                Not financial advice. Past performance is not indicative of future
                results. Trading involves substantial risk of loss.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Main entry point for the Wall Street Analyst Intelligence Suite page.
    Renders hero, stats, how-to-use guide, sidebar filters, all 10 prompt
    cards, and disclaimer footer.
    No OpenBB calls. No session state. Fully static content.
    """
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    render_hero_section()
    render_stats_bar()
    render_how_to_use()

    filtered_cards: List[Dict[str, Any]] = render_filter_bar(PROMPT_CARDS)

    if not filtered_cards:
        st.warning(
            "No frameworks match your current filter selection. "
            "Adjust the Category and Complexity filters in the sidebar."
        )
    else:
        for card in filtered_cards:
            render_prompt_card(card)

    render_footer()


if __name__ == "__main__":
    main()