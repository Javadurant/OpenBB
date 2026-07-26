"""
app.py
Institutional Elliott & Harmonic Terminal
+ Trading Intelligence Platform — Full Edition
Multi-Page Application Entry Point
Updated: 2026-04-03

Navigation pages:
  0. Home                      — page_home() [NEW]
  1. Elliott Terminal          — page_elliott_terminal() [preserved]
  2. Harmonic Auditor          — pages/harmonics_ui.py
  3. Confluence                — pages/confluence_ui.py
  4. Elliott Wave              — pages/elliott_ui.py
  5. 3-Month Scanner           — pages/scanner_ui.py
  6. AI Live Analysis          — pages/analyst_intelligence_ui.py
  7. Prompt Library            — pages/analyst_prompts_ui.py
  8. Copilot                   — page_copilot() [preserved]
  9. Trading Hub (13 skills)   — pages/trading_intelligence_hub.py
 10. Intelligence Hub V2       — pages/trading_intelligence_hub_v2.py [NEW]
 11. Swedish Stock Analysis    — pages/swedish_stock_analysis.py [NEW]
 12. AI Trading Agent          — pages/ai_trading_agent.py [NEW]
"""

import datetime
import logging
import os
from typing import Any, Dict, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from dotenv import load_dotenv
from groq import Groq
from groq.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
)
from openbb import obb

from engine.structure.swings import find_pivots
from engine.analysis.elliott import validate_wave_2, project_wave_3, validate_wave_4
from engine.analysis.harmonics import HarmonicEngine

# ── Council patch: clickable home buttons ─────────────────────
from home_buttons import render_home_quick_actions, render_home_stats, render_home_buttons

# ── Council i18n: language/locale system ──────────────────────  # <- NEW [i18n]
from translations import (                                        # <- NEW [i18n]
    t, get_lang, render_language_selector, inject_rtl_css,        # <- NEW [i18n]
    get_text_dir, fmt_number, fmt_currency, fmt_date,             # <- NEW [i18n]
    get_locale_profile,                                           # <- NEW [i18n]
)                                                                 # <- NEW [i18n]


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TerminalUI")

GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")

# ─── PAGE CONFIG — called ONCE ────────────────────────────────────────────
st.set_page_config(
    layout="wide",
    page_title="QuantEdge — Institutional Trading Intelligence Platform",
    page_icon="🎯",
    initial_sidebar_state="collapsed",
)

# ── Council i18n: global language selector + RTL support ──────  # <- NEW [i18n]
render_language_selector()                                         # <- NEW [i18n]: 🇬🇧/🇮🇷/🇸🇪 in sidebar
inject_rtl_css()                                                   # <- NEW [i18n]: RTL + Vazirmatn font for Persian

# ─── HOME PAGE ANIMATION CSS ──────────────────────────────────────────────
HOME_ANIMATION_CSS: str = """
<style>
@keyframes draw-line {
    from { stroke-dashoffset: 1200; }
    to   { stroke-dashoffset: 0; }
}
@keyframes glow-pulse {
    0%,100% { filter:drop-shadow(0 0 6px rgba(0,229,255,0.6)); }
    50%      { filter:drop-shadow(0 0 16px rgba(0,229,255,1.0)); }
}
@keyframes gold-pulse {
    0%,100% { filter:drop-shadow(0 0 8px rgba(255,215,0,0.7)); }
    50%      { filter:drop-shadow(0 0 20px rgba(255,215,0,1.0)); }
}
@keyframes purple-pulse {
    0%,100% { filter:drop-shadow(0 0 6px rgba(168,85,247,0.6)); }
    50%      { filter:drop-shadow(0 0 16px rgba(168,85,247,1.0)); }
}
@keyframes fade-in-up {
    from { opacity:0; transform:translateY(22px); }
    to   { opacity:1; transform:translateY(0); }
}
@keyframes ticker-scroll {
    0%   { transform:translateX(0); }
    100% { transform:translateX(-50%); }
}
@keyframes shimmer {
    0%   { background-position:-200% center; }
    100% { background-position:200% center; }
}
.hero-badge { animation:fade-in-up 0.7s ease both; animation-delay:0.05s; }
.hero-title { animation:fade-in-up 0.9s ease both; animation-delay:0.12s; }
.hero-sub   { animation:fade-in-up 0.9s ease both; animation-delay:0.28s; }
.hero-cta   { animation:fade-in-up 0.9s ease both; animation-delay:0.44s; }
.wave-line-1 { animation:draw-line 2.0s ease 0.4s both; }
.wave-line-2 { animation:draw-line 1.4s ease 1.0s both; }
.wave-line-3 { animation:draw-line 2.2s ease 0.7s both; }
.wave-line-4 { animation:draw-line 1.3s ease 1.4s both; }
.wave-line-5 { animation:draw-line 1.6s ease 1.1s both; }
.wave-abc    { animation:draw-line 1.8s ease 1.7s both; }
.bf-xa { animation:draw-line 2.0s ease 0.6s both; }
.bf-ab { animation:draw-line 1.4s ease 1.4s both; }
.bf-bc { animation:draw-line 1.5s ease 1.8s both; }
.bf-cd { animation:draw-line 2.2s ease 2.2s both; }
.ew-dot  { animation:glow-pulse  2.5s ease-in-out infinite; }
.bf-dot  { animation:purple-pulse 2.8s ease-in-out infinite; }
.prz-dot { animation:gold-pulse  2.2s ease-in-out infinite; }
.svc-card {
    background:#080f1a;
    border:1px solid rgba(0,229,255,0.12);
    border-radius:10px;
    padding:18px 16px 16px;
    transition:transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
    animation:fade-in-up 0.6s ease both;
    margin-bottom:4px;
}
.svc-card:hover {
    transform:translateY(-6px);
    border-color:rgba(0,229,255,0.35);
    box-shadow:0 12px 38px rgba(0,229,255,0.13);
}
.svc-card.gold:hover  { border-color:rgba(255,215,0,0.40);   box-shadow:0 12px 38px rgba(255,215,0,0.11); }
.svc-card.purple:hover{ border-color:rgba(168,85,247,0.40);  box-shadow:0 12px 38px rgba(168,85,247,0.11); }
.svc-card.green:hover { border-color:rgba(0,255,136,0.40);   box-shadow:0 12px 38px rgba(0,255,136,0.11); }
.svc-card.amber:hover { border-color:rgba(255,149,0,0.40);   box-shadow:0 12px 38px rgba(255,149,0,0.11); }
.svc-card.teal:hover  { border-color:rgba(0,210,200,0.40);   box-shadow:0 12px 38px rgba(0,210,200,0.11); }
.shimmer-text {
    background:linear-gradient(90deg,#00E5FF 0%,#FFD700 25%,#00FF88 50%,#A855F7 75%,#00E5FF 100%);
    background-size:200% auto;
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    background-clip:text;
    animation:shimmer 4s linear infinite;
}
.ticker-outer { overflow:hidden; background:rgba(0,10,26,0.95);
    border-top:1px solid rgba(0,229,255,0.12);
    border-bottom:1px solid rgba(0,229,255,0.12); padding:8px 0; }
.ticker-inner { display:flex; white-space:nowrap; animation:ticker-scroll 32s linear infinite; }
.ticker-inner:hover { animation-play-state:paused; }
.persona-card {
    background:linear-gradient(135deg,#080f1a 0%,#0a1222 100%);
    border-radius:12px; padding:26px 22px;
    border:1px solid rgba(255,255,255,0.07);
    animation:fade-in-up 0.8s ease both;
}
</style>
"""

# ─── GLOBAL TYPOGRAPHY CSS ────────────────────────────────────────────────
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
.stCaption,[data-testid="stCaptionContainer"] p,small,.caption {
    font-family:'Times New Roman',Times,serif !important;
    font-size:14px !important; color:#B0A898 !important; line-height:1.6 !important;
}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,[data-testid="stSidebar"] div {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 {
    font-family:'Times New Roman',Times,serif !important;
    font-size:18px !important; color:#F5ECD7 !important;
}
[data-testid="stSidebarNavItems"] a,[data-testid="stSidebarNavItems"] span,
[data-testid="stSidebarNav"] a,[data-testid="stSidebarNav"] span,
nav[data-testid="stSidebarNav"] li,nav[data-testid="stSidebarNav"] a {
    color:#C8C0B0 !important;
    font-family:'Times New Roman',Times,serif !important; font-size:15px !important;
}
[data-testid="stSidebarNavItems"] a:hover,[data-testid="stSidebarNav"] a:hover {
    color:#F5ECD7 !important; background-color:rgba(0,229,255,0.08) !important;
}
[data-testid="stSidebarNavItems"] a[aria-selected="true"],
[data-testid="stSidebarNav"] a[aria-selected="true"],[aria-selected="true"] span {
    color:#00E5FF !important; background-color:rgba(0,229,255,0.10) !important;
    border-left:3px solid #00E5FF !important;
}
[data-testid="stTextInput"] input,[data-testid="stSelectbox"] div,
[data-testid="stNumberInput"] input,textarea {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
    border-color:rgba(0,229,255,0.20) !important;
    font-family:'Times New Roman',Times,serif !important;
}
[data-testid="stSelectbox"] > div > div {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
}
[data-testid="stSlider"] > div > div > div {
    background-color:rgba(0,229,255,0.25) !important;
}
[data-testid="stCheckbox"] label { color:#E8E0D0 !important; }
[data-testid="stButton"] button,.stButton button {
    font-family:'Times New Roman',Times,serif !important; font-size:16px !important;
    background-color:#0d2233 !important; color:#E8E0D0 !important;
    border:1px solid rgba(0,229,255,0.25) !important;
}
[data-testid="stButton"] button[kind="primary"],.stButton button[kind="primary"] {
    background-color:rgba(0,229,255,0.15) !important;
    color:#00E5FF !important; border:1px solid rgba(0,229,255,0.45) !important;
}
[data-testid="stTabs"] button,.stTabs [role="tab"] {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important; background-color:transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color:#00E5FF !important; border-bottom-color:#00E5FF !important;
}
[data-testid="stAlert"],.stAlert,.stInfo,.stSuccess,.stWarning,.stError {
    background-color:#0d1f33 !important; border-radius:6px !important;
}
[data-testid="stAlert"] p,.stAlert p,.stInfo p,.stSuccess p,.stWarning p,.stError p {
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
[data-testid="stDataFrame"],[data-testid="stTable"] { background-color:#080f1a !important; }
[data-testid="stChatInput"] textarea,[data-testid="stChatMessage"] p {
    font-family:'Times New Roman',Times,serif !important;
    font-size:16px !important; color:#E8E0D0 !important; line-height:1.75 !important;
}
[data-testid="stChatInput"] { background-color:#0d1f33 !important; }
[data-testid="stSelectbox"] label,[data-testid="stTextInput"] label,
[data-testid="stSlider"] label,[data-testid="stCheckbox"] label {
    font-family:'Times New Roman',Times,serif !important;
    font-size:15px !important; color:#E8E0D0 !important;
}
[data-testid="stMultiSelect"] span,[data-testid="stMultiSelect"] div {
    background-color:#0d1f33 !important; color:#E8E0D0 !important;
}
code,pre,.monospace {
    font-family:'Courier New',Courier,monospace !important;
    font-size:13px !important; background-color:#080f1a !important; color:#A8E0C8 !important;
}
strong,b { font-family:'Times New Roman',Times,serif !important; color:#F5ECD7 !important; }
em,i     { font-family:'Times New Roman',Times,serif !important; color:#D4C9B8 !important; }
hr { border-color:rgba(232,224,208,0.15) !important; }
::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:#000d1a; }
::-webkit-scrollbar-thumb { background:#3a3028; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#5a4a38; }
[data-testid="stSpinner"] { color:#00E5FF !important; }
[data-testid="stMarkdownContainer"] { color:#E8E0D0 !important; }
</style>
"""

# ─── ENGINES ──────────────────────────────────────────────────────────────
harmonic_engine = HarmonicEngine()


# ─── HOME PAGE UTILITIES ──────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _home_fetch_pulse() -> Dict[str, Any]:
    """Fetches live market pulse for home page ticker strip (TTL=60s)."""
    targets: Dict[str, str] = {
        "^GSPC": "S&P 500", "^VIX": "VIX", "^IXIC": "NASDAQ",
        "^TNX": "10Y Yield", "GLD": "Gold", "CL=F": "WTI Oil", "DX-Y.NYB": "DXY",
    }
    result: Dict[str, Any] = {}
    for tkr, name in targets.items():
        try:
            t = yf.Ticker(tkr)  # type: ignore[attr-defined]
            hist = t.history(period="2d")
            if len(hist) >= 2:
                cur  = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                chg  = ((cur / prev) - 1.0) * 100.0 if prev > 1e-10 else 0.0
                result[tkr] = {"name": name, "current": cur, "change": chg, "up": chg >= 0.0}
        except Exception:
            pass
    return result


# ─── HOME PAGE ────────────────────────────────────────────────────────────
def page_home() -> None:
    """
    Spectacular landing page. Features:
    - Butterfly Harmonic + Elliott Wave animated SVG hero banner
    - Live market pulse ticker strip
    - 27-service card grid (3 columns)
    - Trader persona section
    - Nordic / Swedish spotlight
    - AI tech strip + disclaimer
    """
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)
    st.markdown(HOME_ANIMATION_CSS, unsafe_allow_html=True)

    # ── HERO BANNER ───────────────────────────────────────────────────────
    # <- FIXED [Gate5/FM-07]: Streamlit >= 1.30 sanitizes <svg>,<filter>,<feGaussianBlur>
    # inside st.markdown(unsafe_allow_html=True). st.html() renders in main document
    # context without sanitization. Fallback to st.markdown for older versions.
    _text_dir = get_text_dir()  # <- NEW [i18n]: RTL for Persian
    _hero_badge = t("hero_badge")  # <- NEW [i18n]
    _hero_title = t("hero_title")  # <- NEW [i18n]
    _hero_subtitle = t("hero_subtitle")  # <- NEW [i18n]
    _hero_btn1 = t("hero_btn_analysis")  # <- NEW [i18n]
    _hero_btn2 = t("hero_btn_wave")  # <- NEW [i18n]
    _hero_skills = t("hero_stat_skills")  # <- NEW [i18n]
    _hero_data = t("hero_stat_data")  # <- NEW [i18n]
    _hero_free = t("hero_stat_free")  # <- NEW [i18n]
    _hero_nordic = t("hero_stat_nordic")  # <- NEW [i18n]
    _HERO_HTML = f"""
<div style="background:linear-gradient(135deg,#000d1a 0%,#020b18 40%,#060015 100%);
            border-radius:16px;overflow:hidden;position:relative;
            border:1px solid rgba(0,229,255,0.14);margin-bottom:0;">

  <div style="position:absolute;top:-80px;right:-80px;width:320px;height:320px;
              background:radial-gradient(circle,rgba(168,85,247,0.16) 0%,transparent 70%);
              pointer-events:none;"></div>
  <div style="position:absolute;bottom:-50px;left:-50px;width:240px;height:240px;
              background:radial-gradient(circle,rgba(0,229,255,0.10) 0%,transparent 70%);
              pointer-events:none;"></div>

  <div style="display:flex;align-items:center;flex-wrap:wrap;min-height:380px;">

    <!-- Left text -->
    <div style="flex:1 1 360px;padding:44px 40px 44px 48px;min-width:300px;direction:{_text_dir};">

      <div class="hero-badge"
           style="display:inline-flex;align-items:center;gap:8px;
                  background:rgba(0,229,255,0.10);border:1px solid rgba(0,229,255,0.30);
                  border-radius:20px;padding:5px 16px;margin-bottom:22px;">
        <span style="width:7px;height:7px;border-radius:50%;background:#00E5FF;
                     box-shadow:0 0 8px #00E5FF;display:inline-block;"></span>
        <span style="font-family:monospace;font-size:10px;color:#00E5FF;
                     letter-spacing:2px;">{_hero_badge}</span>
      </div>

      <h1 class="hero-title shimmer-text"
          style="font-family:'Times New Roman',serif;
                 font-size:clamp(24px,3.8vw,42px);font-weight:bold;
                 line-height:1.18;margin:0 0 16px 0;">
        {_hero_title}
      </h1>

      <p class="hero-sub"
         style="font-family:'Times New Roman',serif;font-size:16px;color:#8898A8;
                line-height:1.85;margin:0 0 26px 0;max-width:440px;">
        {_hero_subtitle}
      </p>

      <div class="hero-cta" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:26px;">
        <div style="background:rgba(0,229,255,0.16);border:1.5px solid #00E5FF;
                    border-radius:8px;padding:12px 26px;font-family:monospace;
                    font-size:13px;font-weight:bold;color:#00E5FF;letter-spacing:1px;">
          {_hero_btn1}
        </div>
        <div style="background:rgba(255,215,0,0.10);border:1.5px solid rgba(255,215,0,0.50);
                    border-radius:8px;padding:12px 26px;font-family:monospace;
                    font-size:13px;font-weight:bold;color:#FFD700;letter-spacing:1px;">
          {_hero_btn2}
        </div>
      </div>

      <div style="display:flex;gap:22px;flex-wrap:wrap;">
        <div><span style="font-family:monospace;font-size:20px;font-weight:bold;color:#00FF88;">31</span>
             <span style="font-size:10px;color:#5a6a7a;font-family:monospace;margin-left:5px;letter-spacing:1px;">{_hero_skills}</span></div>
        <div><span style="font-family:monospace;font-size:20px;font-weight:bold;color:#00E5FF;">LIVE</span>
             <span style="font-size:10px;color:#5a6a7a;font-family:monospace;margin-left:5px;letter-spacing:1px;">DATA</span></div>
        <div><span style="font-family:monospace;font-size:20px;font-weight:bold;color:#A855F7;">FREE</span>
             <span style="font-size:10px;color:#5a6a7a;font-family:monospace;margin-left:5px;letter-spacing:1px;">GROQ</span></div>
        <div><span style="font-family:monospace;font-size:20px;font-weight:bold;color:#00D2C8;">🇸🇪</span>
             <span style="font-size:10px;color:#5a6a7a;font-family:monospace;margin-left:5px;letter-spacing:1px;">{_hero_nordic}</span></div>
      </div>
    </div>

    <!-- Right: animated SVG -->
    <div style="flex:0 0 480px;padding:16px 16px 16px 0;min-width:300px;">
      <svg viewBox="0 0 480 358" xmlns="http://www.w3.org/2000/svg"
           style="width:100%;max-height:358px;">
        <defs>
          <filter id="fc"><feGaussianBlur stdDeviation="3" result="cb"/>
            <feMerge><feMergeNode in="cb"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          <filter id="fg"><feGaussianBlur stdDeviation="2.5" result="gb"/>
            <feMerge><feMergeNode in="gb"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          <filter id="fp"><feGaussianBlur stdDeviation="2.5" result="pb"/>
            <feMerge><feMergeNode in="pb"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          <linearGradient id="ew-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(0,229,255,0.12)"/>
            <stop offset="100%" stop-color="rgba(0,229,255,0)"/>
          </linearGradient>
          <linearGradient id="bf-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(168,85,247,0.10)"/>
            <stop offset="100%" stop-color="rgba(168,85,247,0)"/>
          </linearGradient>
        </defs>

        <!-- Background -->
        <rect width="480" height="358" fill="#000d1a" rx="10"/>

        <!-- Grid lines -->
        <g stroke="rgba(255,255,255,0.03)" stroke-width="1">
          <line x1="0" y1="72" x2="480" y2="72"/>
          <line x1="0" y1="144" x2="480" y2="144"/>
          <line x1="0" y1="216" x2="480" y2="216"/>
          <line x1="0" y1="288" x2="480" y2="288"/>
          <line x1="96" y1="0" x2="96" y2="358"/>
          <line x1="192" y1="0" x2="192" y2="358"/>
          <line x1="288" y1="0" x2="288" y2="358"/>
          <line x1="384" y1="0" x2="384" y2="358"/>
        </g>

        <!-- Section divider -->
        <line x1="248" y1="16" x2="248" y2="342" stroke="rgba(255,255,255,0.055)" stroke-width="1"/>

        <!-- ══ ELLIOTT WAVE (left 0-248) ══ -->
        <path d="M 20,302 L 78,192 L 108,228 L 173,82 L 203,142 L 229,112 L 248,302 Z"
              fill="url(#ew-fill)" opacity="0.5"/>

        <line class="wave-line-1" x1="20" y1="302" x2="78" y2="192"
              stroke="#00E5FF" stroke-width="2.5" filter="url(#fc)"
              stroke-dasharray="180" stroke-dashoffset="180"/>
        <line class="wave-line-2" x1="78" y1="192" x2="108" y2="228"
              stroke="#FF6B6B" stroke-width="2.0"
              stroke-dasharray="70" stroke-dashoffset="70"/>
        <line class="wave-line-3" x1="108" y1="228" x2="173" y2="82"
              stroke="#00FF88" stroke-width="3.0" filter="url(#fc)"
              stroke-dasharray="210" stroke-dashoffset="210"/>
        <line class="wave-line-4" x1="173" y1="82" x2="203" y2="142"
              stroke="#FF6B6B" stroke-width="2.0"
              stroke-dasharray="90" stroke-dashoffset="90"/>
        <line class="wave-line-5" x1="203" y1="142" x2="229" y2="112"
              stroke="#00E5FF" stroke-width="2.2"
              stroke-dasharray="80" stroke-dashoffset="80"/>
        <polyline class="wave-abc" points="229,112 244,205 258,162 274,270"
                  fill="none" stroke="#FF9500" stroke-width="1.8" stroke-dasharray="5,3"
                  style="stroke-dasharray:360;stroke-dashoffset:360;"/>

        <!-- Wave dots -->
        <circle class="ew-dot" cx="20"  cy="302" r="4.5" fill="#00E5FF" filter="url(#fc)"/>
        <circle class="ew-dot" cx="78"  cy="192" r="4.0" fill="#00E5FF" filter="url(#fc)"/>
        <circle cx="108" cy="228" r="3.5" fill="#FF6B6B"/>
        <circle class="ew-dot" cx="173" cy="82"  r="5.5" fill="#00FF88" filter="url(#fc)"/>
        <circle cx="203" cy="142" r="3.5" fill="#FF6B6B"/>
        <circle class="ew-dot" cx="229" cy="112" r="4.0" fill="#00E5FF" filter="url(#fc)"/>
        <circle cx="244" cy="205" r="3.5" fill="#FF9500"/>
        <circle cx="258" cy="162" r="3.5" fill="#FF9500"/>
        <circle cx="274" cy="270" r="3.5" fill="#FF9500"/>

        <!-- Wave labels -->
        <text x="8"   y="322" fill="#00E5FF" font-size="11" font-family="monospace" font-weight="bold">0</text>
        <text x="65"  y="182" fill="#00E5FF" font-size="12" font-family="monospace" font-weight="bold">①</text>
        <text x="96"  y="248" fill="#FF6B6B" font-size="12" font-family="monospace" font-weight="bold">②</text>
        <text x="160" y="72"  fill="#00FF88" font-size="12" font-family="monospace" font-weight="bold">③</text>
        <text x="191" y="162" fill="#FF6B6B" font-size="12" font-family="monospace" font-weight="bold">④</text>
        <text x="217" y="102" fill="#00E5FF" font-size="12" font-family="monospace" font-weight="bold">⑤</text>
        <text x="232" y="222" fill="#FF9500" font-size="11" font-family="monospace">A</text>
        <text x="246" y="154" fill="#FF9500" font-size="11" font-family="monospace">B</text>
        <text x="262" y="288" fill="#FF9500" font-size="11" font-family="monospace">C</text>
        <text x="12" y="346" fill="rgba(0,229,255,0.50)" font-size="9"
              font-family="monospace" letter-spacing="1.5">ELLIOTT WAVE · 5-3 STRUCTURE</text>

        <!-- ══ BUTTERFLY HARMONIC (right 260-480) ══ -->
        <!-- PRZ completion zone -->
        <rect x="438" y="268" width="36" height="56" fill="rgba(255,215,0,0.07)" rx="3"/>
        <text x="440" y="263" fill="rgba(255,215,0,0.75)" font-size="9"
              font-family="monospace" font-weight="bold">PRZ</text>

        <path d="M 290,270 L 350,140 L 390,192 L 418,114 L 458,305 L 460,305 L 460,270 Z"
              fill="url(#bf-fill)" opacity="0.3"/>

        <line class="bf-xa" x1="290" y1="270" x2="350" y2="140"
              stroke="#A855F7" stroke-width="2.2" filter="url(#fp)"
              stroke-dasharray="200" stroke-dashoffset="200"/>
        <line class="bf-ab" x1="350" y1="140" x2="390" y2="192"
              stroke="#FF6B6B" stroke-width="1.8"
              stroke-dasharray="90" stroke-dashoffset="90"/>
        <line class="bf-bc" x1="390" y1="192" x2="418" y2="114"
              stroke="#A855F7" stroke-width="1.8"
              stroke-dasharray="105" stroke-dashoffset="105"/>
        <line class="bf-cd" x1="418" y1="114" x2="458" y2="306"
              stroke="#FFD700" stroke-width="2.8" filter="url(#fg)"
              stroke-dasharray="260" stroke-dashoffset="260"/>
        <line x1="290" y1="270" x2="462" y2="270"
              stroke="rgba(255,255,255,0.09)" stroke-width="1" stroke-dasharray="4,5"/>

        <!-- Fib labels -->
        <text x="302" y="208" fill="rgba(168,85,247,0.82)" font-size="8.5" font-family="monospace">78.6%</text>
        <text x="356" y="176" fill="rgba(255,107,107,0.82)" font-size="8.5" font-family="monospace">38.2%</text>
        <text x="393" y="158" fill="rgba(168,85,247,0.82)" font-size="8.5" font-family="monospace">88.6%</text>
        <text x="425" y="214" fill="rgba(255,215,0,0.90)" font-size="8.5" font-family="monospace">161.8%</text>

        <!-- Butterfly dots -->
        <circle class="bf-dot" cx="290" cy="270" r="5.0" fill="#A855F7" filter="url(#fp)"/>
        <circle cx="350" cy="140" r="4.0" fill="#A855F7"/>
        <circle cx="390" cy="192" r="3.5" fill="#FF6B6B"/>
        <circle cx="418" cy="114" r="4.0" fill="#A855F7"/>
        <circle class="prz-dot" cx="458" cy="306" r="6.0" fill="#FFD700" filter="url(#fg)"/>

        <!-- XABCD -->
        <text x="276" y="288" fill="#A855F7" font-size="13" font-family="monospace" font-weight="bold">X</text>
        <text x="338" y="132" fill="#A855F7" font-size="13" font-family="monospace" font-weight="bold">A</text>
        <text x="378" y="210" fill="#FF6B6B" font-size="13" font-family="monospace" font-weight="bold">B</text>
        <text x="406" y="108" fill="#A855F7" font-size="13" font-family="monospace" font-weight="bold">C</text>
        <text x="444" y="328" fill="#FFD700" font-size="14" font-family="monospace" font-weight="bold">D</text>

        <text x="264" y="346" fill="rgba(168,85,247,0.50)" font-size="9"
              font-family="monospace" letter-spacing="1.5">BUTTERFLY HARMONIC</text>
        <rect x="10" y="10" width="178" height="20" rx="3"
              fill="rgba(0,229,255,0.07)" stroke="rgba(0,229,255,0.20)" stroke-width="1"/>
        <text x="18" y="24" fill="#00E5FF" font-size="9" font-family="monospace"
              letter-spacing="1.5">PATTERN RECOGNITION ENGINE</text>
      </svg>
    </div>
  </div>
</div>
"""  # <- FIXED [Gate5/FM-07]: closed string; now call st.html() below
    try:
        st.html(_HERO_HTML)          # Streamlit >= 1.31: no SVG sanitization, main-doc context
    except AttributeError:
        st.markdown(_HERO_HTML, unsafe_allow_html=True)  # fallback older Streamlit

    # ── MARKET PULSE TICKER ────────────────────────────────────────────────
    with st.spinner(""):
        pulse = _home_fetch_pulse()

    if pulse:
        # <- FIXED [Gate5]: Vibrant pill-style ticker with green/red backgrounds for ▲▼
        items_html = ""
        for tkr, d in pulse.items():
            is_up      = d["up"]
            chg_str    = f"{d['change']:+.2f}%"
            price_str  = (
                f"{d['current']:.2f}" if d["current"] > 10.0 else f"{d['current']:.3f}"
            )
            # Pill background + bright triangle color
            pill_bg    = "rgba(0,255,136,0.14)"  if is_up else "rgba(255,68,68,0.14)"
            pill_border= "rgba(0,255,136,0.35)"  if is_up else "rgba(255,68,68,0.35)"
            chg_color  = "#00FF88"               if is_up else "#FF4444"
            arrow_html = (
                f"<span style='color:#00FF88;font-size:11px;'>▲</span>" if is_up
                else f"<span style='color:#FF4444;font-size:11px;'>▼</span>"
            )
            items_html += (
                f"<span style='display:inline-flex;align-items:center;gap:7px;"
                f"margin:0 18px;padding:4px 14px;"
                f"background:{pill_bg};border:1px solid {pill_border};"
                f"border-radius:20px;'>"
                f"<span style='font-family:monospace;font-size:10px;color:#6a7a8a;"
                f"letter-spacing:1px;text-transform:uppercase;'>{d['name']}</span>"
                f"<span style='font-family:monospace;font-size:13px;color:#F5ECD7;"
                f"font-weight:bold;'>{price_str}</span>"
                f"{arrow_html}"
                f"<span style='font-family:monospace;font-size:12px;color:{chg_color};"
                f"font-weight:bold;'>{chg_str}</span>"
                f"</span>"
            )
        ticker_html = (
            f"<div style='overflow:hidden;background:rgba(0,5,18,0.98);"
            f"border-top:1px solid rgba(0,229,255,0.15);"
            f"border-bottom:1px solid rgba(0,229,255,0.15);"
            f"padding:10px 0;margin:10px 0 20px;border-radius:6px;'>"
            f"<div style='display:flex;white-space:nowrap;"
            f"animation:ticker-scroll 34s linear infinite;'>"
            f"{items_html}{items_html}"
            f"</div></div>"
        )
        try:
            st.html(ticker_html)
        except AttributeError:
            st.markdown(ticker_html, unsafe_allow_html=True)

    # ── SECTION HEADER ────────────────────────────────────────────────────
    # <- IMPROVED [UI]: High-converting section header with urgency + value proposition
    _section_header = """
<div style="text-align:center;padding:36px 0 28px;">
  <div style="display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;
              background:rgba(255,215,0,0.09);border:1px solid rgba(255,215,0,0.28);
              border-radius:20px;padding:6px 20px;">
    <span style="width:6px;height:6px;border-radius:50%;background:#FFD700;
                 box-shadow:0 0 8px #FFD700;display:inline-block;"></span>
    <span style="font-family:monospace;font-size:10px;color:#FFD700;
                 letter-spacing:2.5px;font-weight:bold;">31 PROFESSIONAL TOOLS · ONE PLATFORM · FREE AI</span>
  </div>
  <h2 style="font-family:'Times New Roman',serif;
             font-size:clamp(22px,3.5vw,38px);font-weight:bold;
             color:#F5ECD7;margin:0 0 14px;line-height:1.2;">
    The Trading Edge Your<br>
    <span style="background:linear-gradient(90deg,#00E5FF,#FFD700,#00FF88);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                 background-clip:text;">
      Competitors Don't Have
    </span>
  </h2>
  <p style="font-family:'Times New Roman',serif;font-size:16px;color:#8898A8;
            max-width:580px;margin:0 auto 20px;line-height:1.9;">
    Stop paying $200/month for Bloomberg. Stop guessing when to buy.
    <strong style="color:#E8E0D0;">Every tool a professional uses</strong> —
    Elliott Wave, harmonic patterns, conviction scoring, VCP screening,
    options pricing — is right here. Powered by live data. Free AI.
  </p>
  <div style="display:inline-flex;gap:28px;padding:14px 32px;
              background:rgba(0,229,255,0.06);border:1px solid rgba(0,229,255,0.16);
              border-radius:12px;flex-wrap:wrap;justify-content:center;">
    <div style="text-align:center;">
      <div style="font-family:monospace;font-size:24px;font-weight:bold;color:#00FF88;">$0</div>
      <div style="font-family:monospace;font-size:9px;color:#5a6a7a;letter-spacing:1px;">AI COST</div>
    </div>
    <div style="width:1px;background:rgba(255,255,255,0.08);"></div>
    <div style="text-align:center;">
      <div style="font-family:monospace;font-size:24px;font-weight:bold;color:#00E5FF;">31</div>
      <div style="font-family:monospace;font-size:9px;color:#5a6a7a;letter-spacing:1px;">SKILLS</div>
    </div>
    <div style="width:1px;background:rgba(255,255,255,0.08);"></div>
    <div style="text-align:center;">
      <div style="font-family:monospace;font-size:24px;font-weight:bold;color:#FFD700;">LIVE</div>
      <div style="font-family:monospace;font-size:9px;color:#5a6a7a;letter-spacing:1px;">MARKET DATA</div>
    </div>
    <div style="width:1px;background:rgba(255,255,255,0.08);"></div>
    <div style="text-align:center;">
      <div style="font-family:monospace;font-size:24px;font-weight:bold;color:#A855F7;">🇸🇪</div>
      <div style="font-family:monospace;font-size:9px;color:#5a6a7a;letter-spacing:1px;">NORDIC</div>
    </div>
  </div>
</div>
"""
    try:
        st.html(_section_header)
    except AttributeError:
        st.markdown(_section_header, unsafe_allow_html=True)

    # ── SERVICE CARDS GRID ────────────────────────────────────────────────
    # (icon, title, description, benefit_tagline, color_class, anim_delay)
    SERVICES = [
        ("📊","Elliott Wave Terminal",
         "Auto-detect 5-wave impulse and ABC correction on any stock.",
         "Know where the market is in its cycle before it moves.",
         "cyan","0.05s"),
        ("📐","Harmonic Pattern Auditor",
         "Identify Butterfly, Gartley, Bat, Crab with Fibonacci validation.",
         "Trade high-probability reversals with exact entry zones.",
         "purple","0.12s"),
        ("⚡","Confluence Engine",
         "Combine EMA, RSI, MACD, harmonic signals into one verdict.",
         "Stop second-guessing. See when everything lines up.",
         "gold","0.19s"),

        ("📈","Chart Analyst",
         "Probabilistic technical scenarios: 2-4 outcomes with exact probabilities.",
         "Three clear paths for any chart — not just one opinion.",
         "cyan","0.26s"),
        ("🌍","Market Environment",
         "Global risk-on/off regime: US, Europe, Asia, FX, Bonds, Commodities.",
         "Know whether to be aggressive or defensive this week.",
         "gold","0.33s"),
        ("🔭","Uptrend Analyzer",
         "Monty's Uptrend Ratio across 11 GICS sectors — composite 0-100 score.",
         "See whether the rally is broad or dangerously narrow.",
         "cyan","0.40s"),

        ("📡","Breadth Dashboard",
         "S&P 500 breadth index with TraderMonty BUY/SELL/HOLD signals.",
         "Buy when breadth confirms. Sell when it diverges.",
         "purple","0.47s"),
        ("⚠️","Market Top Detector",
         "O'Neil Distribution Day + Minervini deterioration scoring.",
         "Get early warning before the next 10-20% correction.",
         "amber","0.54s"),
        ("🫧","Bubble Detector",
         "Minsky/Kindleberger v2.1: quantitative bubble risk 0-15 pts.",
         "Know when the market is pricing in perfection.",
         "amber","0.61s"),

        ("🏆","Druckenmiller Synthesizer",
         "Unifies 6 market signals into one conviction score with allocation.",
         "Know exactly how aggressive to be — in one number.",
         "gold","0.68s"),
        ("🌐","Macro Regime Detector",
         "Cross-asset analysis: RSP/SPY, yield curve, credit, size factor.",
         "Identify 1-2 year structural regime shifts early.",
         "cyan","0.75s"),
        ("📰","News Impact Analyst",
         "Translate market events into sector-by-sector portfolio impact.",
         "Know which sectors win or lose before the crowd reacts.",
         "green","0.82s"),

        ("💡","Options Advisor",
         "Black-Scholes pricing + full Greeks + P&L for 8 strategy types.",
         "Price any options strategy — no Bloomberg required.",
         "cyan","0.89s"),
        ("🛡️","Portfolio Manager",
         "Correlation matrix, sector concentration, beta stress test.",
         "Understand your true risk before the next market crash.",
         "green","0.96s"),
        ("📏","Position Sizer",
         "Fixed Fractional, ATR-based, Kelly Criterion with portfolio limits.",
         "Never over-size a trade again — sizing is risk management.",
         "gold","1.03s"),

        ("🔬","VCP Screener",
         "Minervini Volatility Contraction across S&P 500, 3-phase pipeline.",
         "Find the next breakout stock before it moves 30-50%.",
         "purple","1.10s"),
        ("📋","Earnings Analyzer",
         "5-factor PEAD scoring: gap, trend, volume, MA200, MA50.",
         "Know in minutes if a post-earnings stock is worth buying.",
         "amber","1.17s"),
        ("💰","Value & Dividend Screen",
         "P/E<20, P/B<2, Yield≥3% with DRIP and income projections.",
         "Build reliable dividend income — see it compound over 10 years.",
         "green","1.24s"),

        ("🎯","PEAD Screener",
         "Post-Earnings Drift: red candle pullback → breakout detection.",
         "Catch the second move after earnings — the one traders miss.",
         "cyan","1.31s"),
        ("🧪","Backtest Expert",
         "Beat-ideas-to-death: 5D scoring, stress test, Deploy/Refine/Abandon.",
         "Validate your strategy before risking real money.",
         "gold","1.38s"),
        ("🔁","FTD Detector",
         "O'Neil Follow-Through Day: CORRECTION→RALLY→FTD state machine.",
         "Know exactly when it is safe to re-enter after a correction.",
         "cyan","1.45s"),

        ("🌿","Exposure Coach",
         "8 upstream signals → one exposure ceiling + action recommendation.",
         "Answer the most important weekly question: how much to invest?",
         "green","1.52s"),
        ("🏦","Institutional Flow",
         "13F SEC filings: smart money accumulation/distribution with grades.",
         "Follow hedge fund positioning before price reflects it.",
         "purple","1.59s"),
        ("🌸","Kanchi Dividend SOP",
         "5-step Japanese dividend method adapted for US equities.",
         "A time-tested income strategy — now systematized for you.",
         "gold","1.66s"),

        ("🗺️","Sector Analyst",
         "TraderMonty sector rotation with market cycle phase estimation.",
         "Know which sectors lead — before the herd rotates in.",
         "amber","1.73s"),
        ("🧠","Scenario Analyzer",
         "18-month Base/Bull/Bear scenarios from any news headline.",
         "Think 18 months ahead — and own stocks that win in each case.",
         "cyan","1.80s"),
        ("🇸🇪","Swedish Analysis",
         "Full analysis for OMX Stockholm: Volvo, ABB, H&M — in SEK.",
         "Nordic traders: ISK/KF-optimized recommendations in Swedish context.",
         "teal","1.87s"),
    ]

    ACCENT: Dict[str, str] = {
        "cyan":   "#00E5FF", "gold": "#FFD700", "purple": "#A855F7",
        "green":  "#00FF88", "amber": "#FF9500", "teal": "#00D2C8",
    }
    BORDER: Dict[str, str] = {
        "cyan":   "rgba(0,229,255,0.20)",   "gold": "rgba(255,215,0,0.20)",
        "purple": "rgba(168,85,247,0.20)",  "green": "rgba(0,255,136,0.20)",
        "amber":  "rgba(255,149,0,0.20)",   "teal": "rgba(0,210,200,0.20)",
    }
    GLOW: Dict[str, str] = {
        "cyan":   "rgba(0,229,255,0.08)",   "gold": "rgba(255,215,0,0.08)",
        "purple": "rgba(168,85,247,0.08)",  "green": "rgba(0,255,136,0.08)",
        "amber":  "rgba(255,149,0,0.08)",   "teal": "rgba(0,210,200,0.08)",
    }
    # <- IMPROVED [UI]: Rich service cards with hover glow + outcome badges
    rows = [SERVICES[i:i+3] for i in range(0, len(SERVICES), 3)]
    for row in rows:
        cols = st.columns(3)
        for col, (ico, title, desc, benefit, clr, delay) in zip(cols, row):
            accent = ACCENT.get(clr, "#00E5FF")
            border = BORDER.get(clr, "rgba(0,229,255,0.20)")
            glow   = GLOW.get(clr,   "rgba(0,229,255,0.08)")
            card_html = (
                f"<div style='"
                f"background:linear-gradient(145deg,#080f1a 0%,#050c16 100%);"
                f"border:1px solid {border};"
                f"border-top:2px solid {accent};"
                f"border-radius:10px;"
                f"padding:20px 18px 18px;"
                f"margin-bottom:4px;"
                f"min-height:160px;"
                f"transition:transform 0.25s ease,box-shadow 0.25s ease;"
                f"'>"
                f"<div style='display:flex;align-items:flex-start;gap:12px;margin-bottom:10px;'>"
                f"<span style='font-size:26px;line-height:1;'>{ico}</span>"
                f"<h4 style='font-family: \"Times New Roman\", serif;font-size:15px;"
                f"font-weight:bold;color:#F5ECD7;margin:0;line-height:1.3;'>{title}</h4>"
                f"</div>"
                f"<p style='font-family: \"Times New Roman\", serif;font-size:13px;"
                f"color:#6a7a8a;line-height:1.72;margin:0 0 12px;'>{desc}</p>"
                f"<div style='background:{glow};"
                f"border:1px solid {border};"
                f"border-radius:6px;padding:7px 10px;'>"
                f"<span style='font-family:monospace;font-size:11px;color:{accent};"
                f"font-weight:bold;letter-spacing:0.3px;'>→ {benefit}</span>"
                f"</div>"
                f"</div>"
            )
            with col:
                try:
                    st.html(card_html)
                except AttributeError:
                    st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── TRADER PERSONAS ───────────────────────────────────────────────────
    # <- IMPROVED [UI]: Persona section header with urgency language
    _persona_hdr = """
<div style="text-align:center;padding:28px 0 22px;">
  <p style="font-family:monospace;font-size:10px;color:#A855F7;
            letter-spacing:3px;margin:0 0 10px;">◆ WHO IS THIS FOR?</p>
  <h2 style="font-family:'Times New Roman',serif;
             font-size:clamp(20px,3vw,32px);font-weight:bold;
             color:#F5ECD7;margin:0 0 10px;">
    Built for Everyone. Mastered by None. Yet.
  </h2>
  <p style="font-family:'Times New Roman',serif;font-size:15px;color:#7888A0;
            max-width:480px;margin:0 auto;line-height:1.85;">
    Whether you just opened your first brokerage account or you manage
    a million-dollar portfolio — this platform scales with you.
  </p>
</div>
"""
    try:
        st.html(_persona_hdr)
    except AttributeError:
        st.markdown(_persona_hdr, unsafe_allow_html=True)

    pc1, pc2, pc3 = st.columns(3)
    PERSONAS = [
        ("🌱","#00FF88","New to Investing",
         "You don't need to understand Elliott Wave to benefit from it.",
         ["Plain-English recommendations — no jargon",
          "Clear Buy / Hold / Sell signals with reasoning",
          "Income projections you can actually plan around",
          "No Bloomberg terminal required — ever"]),
        ("📈","#00E5FF","Active Trader",
         "Stop juggling 3 platforms. Everything you need is here.",
         ["VCP & PEAD screeners for high-probability entries",
          "Options P&L simulation before you place any trade",
          "Post-earnings gap scoring in seconds",
          "ATR and Kelly position sizing built in"]),
        ("🏛️","#FFD700","Professional / Fund Manager",
         "Institutional frameworks at retail speed and zero cost.",
         ["Druckenmiller conviction scoring 0-100",
          "Macro regime with cross-asset ratio analysis",
          "Institutional 13F flow tracking from SEC filings",
          "Backtest expert: Deploy / Refine / Abandon verdict"]),
    ]
    for col, (icon, accent, title, tagline, pts) in zip([pc1, pc2, pc3], PERSONAS):
        pts_html = "".join(f"<li style='margin-bottom:6px;font-size:13px;'>{p}</li>" for p in pts)
        p_card = (
            f"<div style='background:linear-gradient(145deg,#080f1a 0%,#060d1a 100%);"
            f"border-radius:12px;padding:26px 22px;"
            f"border:1px solid rgba(255,255,255,0.08);"
            f"border-top:3px solid {accent};'>"
            f"<div style='font-size:32px;margin-bottom:12px;'>{icon}</div>"
            f"<h3 style='font-family: \"Times New Roman\", serif;font-size:17px;"
            f"font-weight:bold;color:#F5ECD7;margin:0 0 6px;'>{title}</h3>"
            f"<p style='font-family: \"Times New Roman\", serif;font-size:13px;"
            f"color:{accent};font-style:italic;margin:0 0 16px;line-height:1.5;'>{tagline}</p>"
            f"<ul style='font-family: \"Times New Roman\", serif;color:#8898A8;"
            f"padding-left:17px;margin:0;line-height:1.82;'>{pts_html}</ul>"
            f"</div>"
    )
        with col:
            try:
                st.html(p_card)
            except AttributeError:
                st.markdown(p_card, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── NORDIC SPOTLIGHT ──────────────────────────────────────────────────
    _nordic = """
<div style="background:linear-gradient(135deg,#000d1a 0%,#001a14 100%);
            border:1px solid rgba(0,210,200,0.22);border-radius:14px;
            padding:28px 36px;margin:6px 0 14px;
            display:flex;align-items:center;flex-wrap:wrap;gap:22px;">
  <div style="font-size:50px;line-height:1;">🇸🇪</div>
  <div style="flex:1;min-width:260px;">
    <p style="font-family:monospace;font-size:10px;color:#00D2C8;
              letter-spacing:2px;margin:0 0 7px;">NEW · NORDIC MARKET INTELLIGENCE</p>
    <h3 style="font-family:'Times New Roman',serif;font-size:20px;
               font-weight:bold;color:#F5ECD7;margin:0 0 9px;">
      Swedish Stock Analysis — ISK &amp; KF Optimized
    </h3>
    <p style="font-family:'Times New Roman',serif;font-size:14px;
              color:#7888A0;line-height:1.85;margin:0 0 14px;max-width:540px;">
      Full institutional-grade analysis for OMX Stockholm — Volvo, ABB, H&amp;M, Ericsson,
      Atlas Copco and more. Prices in SEK, OMXS30 comparisons, Riksbank rate context, and
      tax-optimized recommendations for ISK, KF, and Aktie &amp; Fondkonto.
    </p>
    <div style="display:flex;gap:14px;flex-wrap:wrap;">
      <span style="font-family:monospace;font-size:11px;color:#00D2C8;
                   background:rgba(0,210,200,0.10);border:1px solid rgba(0,210,200,0.25);
                   border-radius:4px;padding:4px 11px;">ISK · Schablonintäkt</span>
      <span style="font-family:monospace;font-size:11px;color:#00D2C8;
                   background:rgba(0,210,200,0.10);border:1px solid rgba(0,210,200,0.25);
                   border-radius:4px;padding:4px 11px;">KF · Kapitalförsäkring</span>
      <span style="font-family:monospace;font-size:11px;color:#00D2C8;
                   background:rgba(0,210,200,0.10);border:1px solid rgba(0,210,200,0.25);
                   border-radius:4px;padding:4px 11px;">OMXS30 · 15 Stocks</span>
      <span style="font-family:monospace;font-size:11px;color:#00D2C8;
                   background:rgba(0,210,200,0.10);border:1px solid rgba(0,210,200,0.25);
                   border-radius:4px;padding:4px 11px;">Riksbank · SEK</span>
    </div>
  </div>
</div>
"""
    try:
        st.html(_nordic)
    except AttributeError:
        st.markdown(_nordic, unsafe_allow_html=True)

    # ── AI TECH STRIP ─────────────────────────────────────────────────────
    _aistrip = """
<div style="background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.13);
            border-radius:10px;padding:20px 30px;margin:6px 0 14px;
            display:flex;align-items:center;flex-wrap:wrap;gap:22px;">
  <div>
    <p style="font-family:monospace;font-size:10px;color:#FFD700;
              letter-spacing:2px;margin:0 0 6px;">⚡ POWERED BY</p>
    <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap;">
      <span style="font-family:monospace;font-size:14px;font-weight:bold;color:#FFD700;">
        Groq LLaMA 3.3 70B
      </span>
      <span style="color:rgba(255,255,255,0.15);">·</span>
      <span style="font-family:monospace;font-size:13px;color:#E8E0D0;">yfinance</span>
      <span style="color:rgba(255,255,255,0.15);">·</span>
      <span style="font-family:monospace;font-size:13px;color:#E8E0D0;">OpenBB 4.x</span>
      <span style="color:rgba(255,255,255,0.15);">·</span>
      <span style="font-family:monospace;font-size:13px;color:#E8E0D0;">Plotly Dark</span>
      <span style="color:rgba(255,255,255,0.15);">·</span>
      <span style="font-family:monospace;font-size:13px;color:#E8E0D0;">Streamlit</span>
    </div>
  </div>
  <div style="margin-left:auto;text-align:right;">
    <p style="font-family:monospace;font-size:10px;color:#5a6a7a;margin:0 0 3px;letter-spacing:1px;">
      GROQ API
    </p>
    <p style="font-family:monospace;font-size:16px;font-weight:bold;color:#00FF88;margin:0;">
      FREE ✓
    </p>
  </div>
</div>
"""
    try:
        st.html(_aistrip)
    except AttributeError:
        st.markdown(_aistrip, unsafe_allow_html=True)

    # ── QUICK NAVIGATION BUTTONS ──────────────────────────────────────────
    # <- FIXED [integration]: render_home_buttons() imported at line 47,
    #    called here so clickable buttons appear on the home page.
    #    _quantedge_home_buttons() defined after pages.run() is unreachable
    #    from page_home(); direct call to the imported function is correct.
    st.markdown("---")
    render_home_buttons()                                                    # <- FIXED: wires clickable home navigation buttons

    # ── FOOTER DISCLAIMER ─────────────────────────────────────────────────
    st.markdown(
        f"""<div style="background:rgba(255,82,82,0.05);border:1px solid rgba(255,82,82,0.14);
                        border-radius:6px;padding:12px 20px;margin-top:8px;">
              <p style="color:rgba(255,255,255,0.28);font-size:10px;
                        font-family:monospace;margin:0;line-height:1.9;">
                ⚠ RISK DISCLAIMER: This platform provides analytical tools and AI-generated analysis
                for educational and research purposes only. Nothing constitutes financial advice or a
                solicitation to buy or sell any security. All analysis uses live market data from
                public sources. Past patterns do not guarantee future results. Trading involves
                substantial risk of loss. Always verify independently before acting.
                Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} UTC.
              </p>
            </div>""",
        unsafe_allow_html=True,
    )


# ─── SHARED CHART RENDERER (preserved exactly) ───────────────────────────
def render_tradingview_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    """
    Renders a production-grade Japanese candlestick chart.
    Dark theme, right-side pricing, no range slider.
    """
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#089981",
        decreasing_line_color="#F23645",
        name=ticker,
    )])
    fig.update_layout(
        template="plotly_dark",
        height=600,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(rangeslider_visible=False, gridcolor="rgba(128,128,128,0.1)", type="date"),
        yaxis=dict(side="right", gridcolor="rgba(128,128,128,0.1)", fixedrange=False),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        showlegend=False,
    )
    return fig


# ─── ELLIOTT TERMINAL (preserved exactly) ────────────────────────────────
def page_elliott_terminal() -> None:
    """
    Elliott Terminal page — all original logic preserved.
    FIX [FM-07]: obb.technical.ema() removed in OpenBB 4.x; replaced with
    pandas .ewm(span=10, adjust=False).mean() — semantically identical.
    """
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "latest_scan_context" not in st.session_state:
        st.session_state.latest_scan_context = None

    st.sidebar.header("🕹️ Control Panel")
    ticker: str   = st.sidebar.text_input("Ticker Symbol", value="SPY").upper()
    lookback: int = st.sidebar.slider("Scan Depth (Pivots)", 5, 20, 10)

    st.title("📊 Elliott Terminal")

    if st.sidebar.button("🚀 Execute Analysis"):
        try:
            with st.spinner(f"Analyzing {ticker}..."):
                res = obb.equity.price.historical(ticker, provider="yfinance")  # type: ignore[attr-defined]
                df: pd.DataFrame = res.to_df()
                data_filtered: pd.DataFrame = df.copy()
                data_filtered["close"] = df["close"].ewm(span=10, adjust=False).mean()
                pivots   = find_pivots(data_filtered)
                p_prices = pivots["close"].values

                main_col, side_col = st.columns([3, 1])
                with main_col:
                    st.subheader(f"📈 {ticker} Institutional Terminal")
                    st.plotly_chart(render_tradingview_chart(df, ticker), width="stretch")

                with side_col:
                    st.subheader("🎯 Wave Targets")
                    found_valid: bool = False
                    for i in range(5, min(len(p_prices), lookback + 1)):
                        pts = p_prices[-i:-i+5] if i > 5 else p_prices[-5:]
                        w2_analysis = validate_wave_2(pts[0], pts[1], pts[2])
                        if w2_analysis["is_valid"]:
                            w4_analysis = validate_wave_4(pts[0], pts[1], pts[2], pts[3], pts[4])
                            targets     = project_wave_3(pts[0], pts[1], pts[2])
                            st.success("VALID MOTIVE BASE")
                            st.metric("Retrace Ratio", f"{w2_analysis['ratio']:.3f}")
                            if w4_analysis["is_valid"]:
                                st.info("✅ RULE 3: NO OVERLAP")
                                st.metric("Wave 3 Target", f"${targets['target_1618']:,.2f}")
                            else:
                                st.warning("⚠️ RULE 3 VIOLATION")
                                st.caption(f"Overlap detected: ${w4_analysis['overlap_depth']:.2f}")
                                if w4_analysis["is_diagonal"]:
                                    st.info("Potential Leading Diagonal Detected")
                            st.session_state.latest_scan_context = {
                                "ticker":      ticker,
                                "ratio":       w2_analysis["ratio"],
                                "w4_valid":    w4_analysis["is_valid"],
                                "target_1618": targets["target_1618"],
                            }
                            found_valid = True
                            break
                    if not found_valid:
                        st.warning("No valid Impulse structures detected in scan depth.")
        except Exception as e:
            logger.error(f"UI Engine Error: {str(e)}")
            st.error(f"Engine Error: {str(e)}")
    else:
        st.info("Input a ticker and press 'Execute Analysis' to begin.")


# ─── COPILOT PAGE (preserved exactly) ────────────────────────────────────
def page_copilot() -> None:
    """Hedge-Fund Copilot page — all original logic preserved."""
    st.markdown(GLOBAL_TYPOGRAPHY_CSS, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "latest_scan_context" not in st.session_state:
        st.session_state.latest_scan_context = None

    st.title("🧠 Hedge-Fund Copilot")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Analyze the Rule 3 status of this ticker..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            if not GROQ_API_KEY:
                st.error("⚠️ GROQ_API_KEY missing.")
            else:
                client = Groq(api_key=GROQ_API_KEY)
                sys_prompt = (
                    "You are a Trading Systems Architect.\n"
                    f"Context: {st.session_state.latest_scan_context}\n"
                    "Enforce Rule 3: Wave 4 must not overlap Wave 1 territory."
                )
                
                # ✅ FIXED: Construct properly typed messages for Groq API
                typed_messages: list = [
                    ChatCompletionSystemMessageParam(role="system", content=sys_prompt)
                ]
                
                # Add chat history with proper types
                for msg in st.session_state.messages:
                    if msg.get("role") == "user":
                        typed_messages.append(
                            ChatCompletionUserMessageParam(
                                role="user", content=msg["content"]
                            )
                        )
                    elif msg.get("role") == "assistant":
                        typed_messages.append(
                            ChatCompletionAssistantMessageParam(
                                role="assistant", content=msg["content"]
                            )
                        )
                
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=typed_messages,
                    temperature=0.0,
                )
                full_response = response.choices[0].message.content
                st.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})


# ─── NAVIGATION REGISTRY ──────────────────────────────────────────────────
# <- NEW [home]:   Home page added as default.
# <- NEW [hub_v2]: Intelligence Hub V2 added (31 skills total).
# <- NEW [swedish]: Swedish Stock Analysis added.
# All existing entries preserved exactly.
pages = st.navigation([
    st.Page(page_home,                           title=t("nav_home"),              icon="🏠", default=True),  # <- i18n
    st.Page("pages/ai_command_center.py",        title="AI Command Center",        icon="🎯"),  # <- NEW [Council]: Bloomberg Launchpad equivalent
    st.Page("pages/trading_toolkit.py",          title="Trading Toolkit",          icon="🛠️"),  # <- NEW [Council]: 5 hidden engines surfaced
    st.Page(page_elliott_terminal,               title=t("nav_elliott_terminal"),  icon="📊"),  # <- i18n
    st.Page("pages/harmonics_ui.py",             title=t("nav_harmonic_auditor"),  icon="📐"),  # <- i18n
    st.Page("pages/confluence_ui.py",            title=t("nav_confluence"),        icon="⚡"),  # <- i18n
    st.Page("pages/elliott_ui.py",               title=t("nav_elliott_wave"),      icon="🌊"),  # <- i18n
    st.Page("pages/scanner_ui.py",               title=t("nav_scanner"),           icon="📡"),  # <- i18n
    st.Page("pages/analyst_intelligence_ui.py",  title=t("nav_ai_analysis"),       icon="🤖"),  # <- i18n
    st.Page("pages/analyst_prompts_ui.py",       title=t("nav_prompt_library"),    icon="📋"),  # <- i18n
    st.Page(page_copilot,                        title=t("nav_copilot"),           icon="🧠"),  # <- i18n
    st.Page("pages/trading_intelligence_hub.py", title=t("nav_trading_hub"),       icon="🎯"),  # <- i18n
    # <- NEW [hub_v2]: 31-skill expanded hub
    st.Page("pages/trading_intelligence_hub_v2.py", title=t("nav_intelligence_v2"),icon="🚀"),  # <- i18n
    # <- NEW [swedish]: OMX Stockholm analysis page
    st.Page("pages/swedish_stock_analysis.py",   title=t("nav_swedish_analysis"),  icon="🇸🇪"),  # <- i18n
    st.Page("pages/ai_trading_agent.py",         title=t("nav_ai_agent"),          icon="🤖",  default=False,),  # <- i18n
    st.Page("pages/let_god_trade.py",            title=t("nav_let_god_trade"),     icon="🤖",  default=False,),  # <- i18n
    st.Page("pages/two_signal_analysis.py",      title=t("nav_two_signal"),        icon="🎯"),  # <- i18n
])

pages.run()

# ── Council patch: home page buttons (rendered when no other content) ─
# Place this where the home tab content lives, OR at the start of app body.
# If your app already renders the home from a function, call render_home_quick_actions(),
# render_home_stats(), and render_home_buttons() inside it.
def _quantedge_home_buttons():
    """Quick clickable nav — call this from your home tab/page."""
    render_home_quick_actions()
    render_home_stats()
    render_home_buttons()
