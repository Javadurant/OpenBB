"""
translations.py
QuantEdge Internationalization Engine — English · فارسی · Svenska

ARCHITECTURE:
  - All UI strings centralized here
  - t(key) function returns translated text based on st.session_state["qe_lang"]
  - Language selector stored in sidebar, persists across ALL pages
  - RTL CSS injected automatically when Persian is active

USAGE IN ANY PAGE:
  from translations import t, get_lang, render_language_selector, inject_rtl_css
  
  # In sidebar or top of page:
  inject_rtl_css()  # only needed once per page render
  
  # In any text:
  st.title(t("page_title_home"))
  st.markdown(t("hero_subtitle"))

SUPPORTED LANGUAGES:
  "en" — English (default)
  "fa" — فارسی (Persian/Farsi)
  "sv" — Svenska (Swedish)

LEVEL: Intermediate — covers all UI text, headers, labels, buttons, descriptions.
       Technical terms (RSI, MACD, Fibonacci, Elliott Wave) remain in English
       as they are universal trading vocabulary.
"""
import streamlit as st
from typing import Optional


# ─── LANGUAGE CONFIGURATION ───────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "en": {"name": "English",  "flag": "🇬🇧", "dir": "ltr"},
    "fa": {"name": "فارسی",   "flag": "🇮🇷", "dir": "rtl"},
    "sv": {"name": "Svenska",  "flag": "🇸🇪", "dir": "ltr"},
}

DEFAULT_LANG = "en"


# ─── MASTER TRANSLATION DICTIONARY ───────────────────────────────────────────

TRANSLATIONS = {

# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION — Page titles shown in sidebar
# ═══════════════════════════════════════════════════════════════════════════════

"nav_home":               {"en": "Home",                "fa": "خانه",                    "sv": "Hem"},
"nav_market_terminal":    {"en": "Market Terminal",     "fa": "ترمینال بازار",           "sv": "Marknadsterminal"},
"nav_elliott_terminal":   {"en": "Elliott Terminal",    "fa": "ترمینال الیوت",           "sv": "Elliott-terminal"},
"nav_harmonic_auditor":   {"en": "Harmonic Auditor",    "fa": "بازرسی هارمونیک",         "sv": "Harmonisk granskning"},
"nav_confluence":         {"en": "Confluence",          "fa": "تلاقی",                    "sv": "Sammanflöde"},
"nav_elliott_wave":       {"en": "Elliott Wave",        "fa": "موج الیوت",               "sv": "Elliott-våg"},
"nav_scanner":            {"en": "3-Month Scanner",     "fa": "اسکنر ۳ ماهه",            "sv": "3-månaders skanner"},
"nav_ai_analysis":        {"en": "AI Live Analysis",    "fa": "تحلیل زنده هوش مصنوعی",   "sv": "AI-liveanalys"},
"nav_prompt_library":     {"en": "Prompt Library",      "fa": "کتابخانه دستورات",         "sv": "Promptbibliotek"},
"nav_copilot":            {"en": "Copilot",             "fa": "دستیار",                   "sv": "Copilot"},
"nav_trading_hub":        {"en": "Trading Hub",         "fa": "مرکز معاملات",             "sv": "Handelscentral"},
"nav_intelligence_v2":    {"en": "Intelligence Hub V2", "fa": "مرکز هوش نسخه ۲",         "sv": "Intelligenshubb V2"},
"nav_swedish_analysis":   {"en": "Swedish Analysis",    "fa": "تحلیل سوئد",              "sv": "Svensk analys"},
"nav_ai_agent":           {"en": "AI Trading Agent",    "fa": "عامل معاملاتی هوشمند",    "sv": "AI-handelsagent"},
"nav_let_god_trade":      {"en": "Let God Trade",       "fa": "معامله خودکار",            "sv": "Automatisk handel"},
"nav_two_signal":         {"en": "Two-Signal Analysis", "fa": "تحلیل دو سیگنال",         "sv": "Tvåsignalanalys"},

# ═══════════════════════════════════════════════════════════════════════════════
# HOME PAGE — Hero section
# ═══════════════════════════════════════════════════════════════════════════════

"hero_badge":             {"en": "INSTITUTIONAL GRADE · LIVE DATA · AI POWERED",
                           "fa": "درجه نهادی · داده زنده · مبتنی بر هوش مصنوعی",
                           "sv": "INSTITUTIONELL KLASS · REALTIDSDATA · AI-DRIVEN"},

"hero_title":             {"en": "Where Institutional<br>Intelligence Meets<br>Individual Vision",
                           "fa": "جایی که هوش نهادی<br>با بینش فردی<br>تلاقی می‌کند",
                           "sv": "Där institutionell<br>intelligens möter<br>individuell vision"},

"hero_subtitle":          {"en": 'One platform. <strong style="color:#E8E0D0;">31 professional skills.</strong> '
                                 'Elliott Wave, Butterfly Harmonics, Druckenmiller conviction, VCP screening, '
                                 'Swedish market analysis — all powered by live data and AI. '
                                 '<em style="color:#B0A898;">No jargon required.</em>',
                           "fa": 'یک پلتفرم. <strong style="color:#E8E0D0;">۳۱ مهارت حرفه‌ای.</strong> '
                                 'موج الیوت، هارمونیک پروانه‌ای، استراتژی دراکنمیلر، غربالگری VCP، '
                                 'تحلیل بازار سوئد — همه با داده زنده و هوش مصنوعی. '
                                 '<em style="color:#B0A898;">بدون نیاز به اصطلاحات تخصصی.</em>',
                           "sv": 'En plattform. <strong style="color:#E8E0D0;">31 professionella verktyg.</strong> '
                                 'Elliott-vågor, fjärilsharmonik, Druckenmiller-övertygelse, VCP-screening, '
                                 'svensk marknadsanalys — allt drivet av realtidsdata och AI. '
                                 '<em style="color:#B0A898;">Ingen jargong krävs.</em>'},

"hero_btn_analysis":      {"en": "🎯  LAUNCH ANALYSIS",    "fa": "🎯  شروع تحلیل",          "sv": "🎯  STARTA ANALYS"},
"hero_btn_wave":          {"en": "📊  WAVE TERMINAL",      "fa": "📊  ترمینال موج",          "sv": "📊  VÅGTERMINAL"},

"hero_stat_skills":       {"en": "SKILLS",     "fa": "مهارت",      "sv": "VERKTYG"},
"hero_stat_data":         {"en": "DATA",       "fa": "داده",       "sv": "DATA"},
"hero_stat_free":         {"en": "FREE",       "fa": "رایگان",     "sv": "GRATIS"},
"hero_stat_nordic":       {"en": "NORDIC",     "fa": "شمال اروپا", "sv": "NORDISK"},


# ═══════════════════════════════════════════════════════════════════════════════
# HOME PAGE — Service cards / sections
# ═══════════════════════════════════════════════════════════════════════════════

"home_services_title":    {"en": "Professional Trading Intelligence Suite",
                           "fa": "مجموعه هوش معاملاتی حرفه‌ای",
                           "sv": "Professionell handelsintelligenssvit"},

"home_persona_title":     {"en": "Built for Every Trader",
                           "fa": "ساخته شده برای هر معامله‌گر",
                           "sv": "Byggd för varje handlare"},

"home_nordic_title":      {"en": "Nordic Market Spotlight",
                           "fa": "بازار شمال اروپا زیر ذره‌بین",
                           "sv": "Nordisk marknad i fokus"},

"home_ai_strip":          {"en": "Powered by Groq LLaMA 3.3 70B · Free Tier · No API Cost",
                           "fa": "با قدرت Groq LLaMA 3.3 70B · رایگان · بدون هزینه API",
                           "sv": "Drivs av Groq LLaMA 3.3 70B · Gratis · Ingen API-kostnad"},

"home_disclaimer":        {"en": "⚠️ This platform is for educational and research purposes only. Not financial advice.",
                           "fa": "⚠️ این پلتفرم فقط برای اهداف آموزشی و تحقیقاتی است. توصیه مالی نیست.",
                           "sv": "⚠️ Denna plattform är enbart för utbildning och forskning. Inte finansiell rådgivning."},

# ═══════════════════════════════════════════════════════════════════════════════
# COMMON UI ELEMENTS — used across multiple pages
# ═══════════════════════════════════════════════════════════════════════════════

"btn_analyze":            {"en": "Analyze",             "fa": "تحلیل",                    "sv": "Analysera"},
"btn_run":                {"en": "Run Analysis",        "fa": "اجرای تحلیل",              "sv": "Kör analys"},
"btn_refresh":            {"en": "Refresh Data",        "fa": "بروزرسانی داده",           "sv": "Uppdatera data"},
"btn_clear":              {"en": "Clear",               "fa": "پاک کردن",                 "sv": "Rensa"},
"btn_export":             {"en": "Export",              "fa": "خروجی",                    "sv": "Exportera"},
"btn_submit":             {"en": "Submit",              "fa": "ارسال",                    "sv": "Skicka"},

"lbl_symbol":             {"en": "Symbol / Ticker",     "fa": "نماد",                     "sv": "Symbol / Ticker"},
"lbl_timeframe":          {"en": "Timeframe",           "fa": "بازه زمانی",               "sv": "Tidsram"},
"lbl_daily":              {"en": "Daily",               "fa": "روزانه",                   "sv": "Daglig"},
"lbl_weekly":             {"en": "Weekly",              "fa": "هفتگی",                    "sv": "Veckovis"},
"lbl_monthly":            {"en": "Monthly",             "fa": "ماهانه",                   "sv": "Månadsvis"},
"lbl_loading":            {"en": "Loading data...",     "fa": "در حال بارگذاری...",       "sv": "Laddar data..."},
"lbl_no_data":            {"en": "No data available",   "fa": "داده‌ای موجود نیست",       "sv": "Ingen data tillgänglig"},
"lbl_error":              {"en": "Error",               "fa": "خطا",                      "sv": "Fel"},
"lbl_success":            {"en": "Success",             "fa": "موفقیت",                   "sv": "Framgång"},
"lbl_warning":            {"en": "Warning",             "fa": "هشدار",                    "sv": "Varning"},

"lbl_bullish":            {"en": "Bullish",             "fa": "صعودی",                    "sv": "Hausse"},
"lbl_bearish":            {"en": "Bearish",             "fa": "نزولی",                    "sv": "Baisse"},
"lbl_neutral":            {"en": "Neutral",             "fa": "خنثی",                     "sv": "Neutral"},
"lbl_buy":                {"en": "BUY",                 "fa": "خرید",                     "sv": "KÖP"},
"lbl_sell":               {"en": "SELL",                "fa": "فروش",                     "sv": "SÄLJ"},
"lbl_hold":               {"en": "HOLD",                "fa": "نگهداری",                  "sv": "HÅLL"},
"lbl_strong_buy":         {"en": "STRONG BUY",          "fa": "خرید قوی",                 "sv": "STARK KÖP"},
"lbl_strong_sell":        {"en": "STRONG SELL",         "fa": "فروش قوی",                 "sv": "STARK SÄLJ"},

"lbl_price":              {"en": "Price",               "fa": "قیمت",                     "sv": "Pris"},
"lbl_change":             {"en": "Change",              "fa": "تغییر",                    "sv": "Förändring"},
"lbl_volume":             {"en": "Volume",              "fa": "حجم",                      "sv": "Volym"},
"lbl_open":               {"en": "Open",                "fa": "باز شدن",                  "sv": "Öppning"},
"lbl_high":               {"en": "High",                "fa": "بالاترین",                 "sv": "Högsta"},
"lbl_low":                {"en": "Low",                 "fa": "پایین‌ترین",               "sv": "Lägsta"},
"lbl_close":              {"en": "Close",               "fa": "بسته شدن",                 "sv": "Stängning"},


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET TERMINAL PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"mt_title":               {"en": "📡 Market Terminal",   "fa": "📡 ترمینال بازار",         "sv": "📡 Marknadsterminal"},
"mt_overview":            {"en": "Global Market Overview","fa": "نمای کلی بازار جهانی",    "sv": "Global marknadsöversikt"},
"mt_us_markets":          {"en": "US Markets",          "fa": "بازارهای آمریکا",          "sv": "Amerikanska marknader"},
"mt_omx_spotlight":       {"en": "OMX Stockholm",       "fa": "بورس استکهلم",             "sv": "OMX Stockholm"},
"mt_macro_regime":        {"en": "Macro Regime",        "fa": "رژیم کلان",                "sv": "Makroregim"},
"mt_yield_curve":         {"en": "Yield Curve",         "fa": "منحنی بازده",              "sv": "Avkastningskurva"},
"mt_inverted":            {"en": "INVERTED — Recession Signal",
                           "fa": "معکوس — سیگنال رکود",
                           "sv": "INVERTERAD — Recessionssignal"},
"mt_normal":              {"en": "Normal — Growth Mode",
                           "fa": "عادی — حالت رشد",
                           "sv": "Normal — Tillväxtläge"},
"mt_sector_heatmap":      {"en": "Sector Heatmap",      "fa": "نقشه حرارتی بخش‌ها",       "sv": "Sektorheatmap"},
"mt_news_feed":           {"en": "Market News",         "fa": "اخبار بازار",              "sv": "Marknadsnyheter"},
"mt_morning_brief":       {"en": "AI Morning Brief",    "fa": "خلاصه صبحگاهی هوش مصنوعی","sv": "AI-morgonbriefing"},
"mt_generate_brief":      {"en": "Generate Morning Brief",
                           "fa": "تولید خلاصه صبحگاهی",
                           "sv": "Generera morgonbriefing"},
"mt_vix_regime":          {"en": "VIX Regime",          "fa": "رژیم VIX",                 "sv": "VIX-regim"},
"mt_vix_low":             {"en": "LOW VOLATILITY",      "fa": "نوسان پایین",              "sv": "LÅG VOLATILITET"},
"mt_vix_normal":          {"en": "NORMAL",              "fa": "عادی",                     "sv": "NORMAL"},
"mt_vix_elevated":        {"en": "ELEVATED",            "fa": "بالا",                     "sv": "FÖRHÖJD"},
"mt_vix_crisis":          {"en": "CRISIS",              "fa": "بحران",                    "sv": "KRIS"},
"mt_quick_signal":        {"en": "Quick Signal Launcher","fa": "اجرای سریع سیگنال",       "sv": "Snabbsignalstart"},

# ═══════════════════════════════════════════════════════════════════════════════
# SCANNER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"scan_title":             {"en": "3-Month Scanner",      "fa": "اسکنر ۳ ماهه",            "sv": "3-månaders skanner"},
"scan_current_price":     {"en": "Current Price",        "fa": "قیمت فعلی",                "sv": "Aktuellt pris"},
"scan_elliott_status":    {"en": "Elliott Wave Status",  "fa": "وضعیت موج الیوت",          "sv": "Elliott-vågstatus"},
"scan_harmonic_signals":  {"en": "Harmonic Pattern Signals","fa": "سیگنال‌های الگوی هارمونیک","sv": "Harmoniska mönster-signaler"},
"scan_indicator_readings":{"en": "Indicator Readings",   "fa": "خوانش اندیکاتورها",        "sv": "Indikatoravläsningar"},
"scan_volume_profile":    {"en": "Volume Profile",       "fa": "پروفایل حجم",              "sv": "Volymprofil"},
"scan_market_structure":  {"en": "Market Structure",     "fa": "ساختار بازار",             "sv": "Marknadsstruktur"},
"scan_projections":       {"en": "Forward Projections",  "fa": "پیش‌بینی‌ها",               "sv": "Framåtblickande projektioner"},
"scan_main_chart":        {"en": "Main Chart — All Overlays",
                           "fa": "نمودار اصلی — تمام لایه‌ها",
                           "sv": "Huvuddiagram — Alla lager"},
"scan_advanced":          {"en": "Advanced Analysis Suite","fa": "مجموعه تحلیل پیشرفته",   "sv": "Avancerad analyssvit"},

# ═══════════════════════════════════════════════════════════════════════════════
# ELLIOTT WAVE PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"ew_title":               {"en": "Elliott Wave: Structural Deep Analysis",
                           "fa": "موج الیوت: تحلیل ساختاری عمیق",
                           "sv": "Elliott-våg: Djup strukturanalys"},
"ew_wave_audit":          {"en": "Wave Audit",           "fa": "بازرسی موج",               "sv": "Våggranskning"},
"ew_price_chart":         {"en": "Price Chart",          "fa": "نمودار قیمت",              "sv": "Prisdiagram"},
"ew_structure_chart":     {"en": "Elliott Wave Structure Chart",
                           "fa": "نمودار ساختار موج الیوت",
                           "sv": "Elliott-vågstrukturdiagram"},
"ew_rule_audit":          {"en": "Rule Audit",           "fa": "بازرسی قوانین",            "sv": "Regelgranskning"},
"ew_wave1":               {"en": "Wave 1",               "fa": "موج ۱",                    "sv": "Våg 1"},
"ew_wave2":               {"en": "Wave 2",               "fa": "موج ۲",                    "sv": "Våg 2"},
"ew_wave3":               {"en": "Wave 3",               "fa": "موج ۳",                    "sv": "Våg 3"},
"ew_wave4":               {"en": "Wave 4",               "fa": "موج ۴",                    "sv": "Våg 4"},
"ew_wave5":               {"en": "Wave 5",               "fa": "موج ۵",                    "sv": "Våg 5"},

# ═══════════════════════════════════════════════════════════════════════════════
# HARMONIC AUDITOR PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"ha_title":               {"en": "Harmonic Pattern Audit",
                           "fa": "بازرسی الگوی هارمونیک",
                           "sv": "Harmonisk mönstergranskning"},
"ha_detail":              {"en": "Pattern Detail — PRZ Zoom & Full Shape",
                           "fa": "جزئیات الگو — بزرگنمایی PRZ و شکل کامل",
                           "sv": "Mönsterdetalj — PRZ-zoom & fullständig form"},
"ha_pattern_found":       {"en": "Pattern Found",        "fa": "الگو یافت شد",             "sv": "Mönster hittat"},
"ha_no_pattern":          {"en": "No valid pattern detected",
                           "fa": "هیچ الگوی معتبری شناسایی نشد",
                           "sv": "Inget giltigt mönster upptäckt"},

# ═══════════════════════════════════════════════════════════════════════════════
# CONFLUENCE PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"cf_title":               {"en": "EW + HP Golden Setup — Confluence Terminal",
                           "fa": "ترکیب طلایی الیوت + هارمونیک — ترمینال تلاقی",
                           "sv": "EW + HP Gyllene Setup — Sammanflödesterminal"},
"cf_framework":           {"en": "The Elliott Wave + Harmonic Confluence Framework",
                           "fa": "چارچوب تلاقی موج الیوت + هارمونیک",
                           "sv": "Elliott-våg + harmoniskt sammanflödesramverk"},
"cf_golden_setup":        {"en": "The Golden Setup — EW + HP Confluence",
                           "fa": "ترکیب طلایی — تلاقی الیوت + هارمونیک",
                           "sv": "Gyllene setup — EW + HP sammanflöde"},
"cf_map":                 {"en": "Confluence Map",       "fa": "نقشه تلاقی",               "sv": "Sammanflödeskarta"},


# ═══════════════════════════════════════════════════════════════════════════════
# AI TRADING AGENT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"agent_title":            {"en": "AI Trading Agent — Multi-Engine Analysis",
                           "fa": "عامل معاملاتی هوشمند — تحلیل چندموتوره",
                           "sv": "AI-handelsagent — Flermotorsanalys"},
"agent_prz":              {"en": "Potential Reversal Zone","fa": "منطقه بازگشت احتمالی",   "sv": "Potentiell vändzon"},
"agent_harmonics":        {"en": "Harmonic Patterns",    "fa": "الگوهای هارمونیک",         "sv": "Harmoniska mönster"},
"agent_macro":            {"en": "Macro Regime",         "fa": "رژیم کلان",                "sv": "Makroregim"},
"agent_fundamentals":     {"en": "Fundamentals",         "fa": "تحلیل بنیادی",             "sv": "Fundamenta"},
"agent_institutional":    {"en": "Institutional Ownership","fa": "مالکیت نهادی",            "sv": "Institutionellt ägande"},
"agent_elliott":          {"en": "Elliott Wave",         "fa": "موج الیوت",                "sv": "Elliott-våg"},
"agent_indicators":       {"en": "Indicator Snapshot",   "fa": "خلاصه اندیکاتورها",        "sv": "Indikatoröversikt"},

# ═══════════════════════════════════════════════════════════════════════════════
# LET GOD TRADE PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"lgt_title":              {"en": "Let God Trade — Autonomous Execution",
                           "fa": "معامله خودکار — اجرای مستقل",
                           "sv": "Automatisk handel — Autonom exekvering"},
"lgt_sessions":           {"en": "Global Market Sessions","fa": "جلسات بازار جهانی",       "sv": "Globala marknadssessioner"},
"lgt_engine":             {"en": "Execution Engine",     "fa": "موتور اجرا",               "sv": "Exekveringsmotor"},
"lgt_history":            {"en": "Order History (this session)",
                           "fa": "تاریخچه سفارشات (این جلسه)",
                           "sv": "Orderhistorik (denna session)"},
"lgt_broker":             {"en": "Broker Account",       "fa": "حساب کارگزاری",            "sv": "Mäklarkonto"},

# ═══════════════════════════════════════════════════════════════════════════════
# TWO-SIGNAL ANALYSIS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"ts_title":               {"en": "🎯 Two-Signal Analysis",
                           "fa": "🎯 تحلیل دو سیگنال",
                           "sv": "🎯 Tvåsignalanalys"},
"ts_technical":           {"en": "Technical Signal",     "fa": "سیگنال تکنیکال",           "sv": "Teknisk signal"},
"ts_fundamental":         {"en": "Fundamental Signal",   "fa": "سیگنال بنیادی",            "sv": "Fundamental signal"},
"ts_combined":            {"en": "Combined View",        "fa": "نمای ترکیبی",              "sv": "Kombinerad vy"},
"ts_psychology":          {"en": "Psychology Gate",       "fa": "دروازه روانشناسی",         "sv": "Psykologiport"},

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING INTELLIGENCE HUB
# ═══════════════════════════════════════════════════════════════════════════════

"hub_title":              {"en": "Trading Intelligence Hub",
                           "fa": "مرکز هوش معاملاتی",
                           "sv": "Handelsintelligenshubb"},
"hub_v2_title":           {"en": "Intelligence Hub V2 — 31 Professional Skills",
                           "fa": "مرکز هوش نسخه ۲ — ۳۱ مهارت حرفه‌ای",
                           "sv": "Intelligenshubb V2 — 31 professionella verktyg"},

# ═══════════════════════════════════════════════════════════════════════════════
# SWEDISH ANALYSIS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"swe_title":              {"en": "Swedish Stock Analysis 🇸🇪",
                           "fa": "تحلیل سهام سوئد 🇸🇪",
                           "sv": "Svensk aktieanalys 🇸🇪"},
"swe_omx":                {"en": "OMX Stockholm",        "fa": "بورس استکهلم",             "sv": "OMX Stockholm"},

# ═══════════════════════════════════════════════════════════════════════════════
# COPILOT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

"copilot_title":          {"en": "QuantEdge Copilot",    "fa": "دستیار کوانت‌اج",           "sv": "QuantEdge Copilot"},
"copilot_placeholder":    {"en": "Ask me anything about trading, markets, or analysis...",
                           "fa": "هر سوالی درباره معامله‌گری، بازارها یا تحلیل بپرسید...",
                           "sv": "Fråga mig vad som helst om handel, marknader eller analys..."},

# ═══════════════════════════════════════════════════════════════════════════════
# LANGUAGE SELECTOR
# ═══════════════════════════════════════════════════════════════════════════════

"lang_select_label":      {"en": "Language",             "fa": "زبان",                     "sv": "Språk"},

# ═══════════════════════════════════════════════════════════════════════════════
# MARKET TERMINAL (mt_) — section headers
# ═══════════════════════════════════════════════════════════════════════════════

"mt_refresh":             {"en": "Refresh",              "fa": "بروزرسانی",                "sv": "Uppdatera"},
"mt_us_sector":           {"en": "US SECTOR PERFORMANCE — TODAY",
                           "fa": "عملکرد بخش‌های آمریکا — امروز",
                           "sv": "AMERIKANSKA SEKTORER — IDAG"},
"mt_signal_launch":       {"en": "QUICK SIGNAL LAUNCH",  "fa": "اجرای سریع سیگنال",       "sv": "SNABBSIGNAL"},

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYST INTELLIGENCE (ai_) — 10 frameworks page
# ═══════════════════════════════════════════════════════════════════════════════

"ai_title":               {"en": "AI Live Analysis — 10 Institutional Frameworks",
                           "fa": "تحلیل زنده AI — ۱۰ چارچوب نهادی",
                           "sv": "AI-liveanalys — 10 institutionella ramverk"},
"ai_select_framework":    {"en": "Select Analysis Framework",
                           "fa": "انتخاب چارچوب تحلیلی",
                           "sv": "Välj analysramverk"},

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYST PROMPTS (ap_) — Prompt Library
# ═══════════════════════════════════════════════════════════════════════════════

"ap_title":               {"en": "Prompt Library — Institutional Templates",
                           "fa": "کتابخانه دستورات — قالب‌های نهادی",
                           "sv": "Promptbibliotek — Institutionella mallar"},
"ap_select":              {"en": "Select a prompt template",
                           "fa": "یک قالب دستور انتخاب کنید",
                           "sv": "Välj en promptmall"},

# ═══════════════════════════════════════════════════════════════════════════════
# SWEDISH STOCK ANALYSIS (swe_) — OMX page
# ═══════════════════════════════════════════════════════════════════════════════

"swe_market_pulse":       {"en": "OMXS30 Market Pulse",  "fa": "نبض بازار OMXS30",         "sv": "OMXS30 marknadspuls"},
"swe_individual":         {"en": "Individual Stock Analysis",
                           "fa": "تحلیل فردی سهام",
                           "sv": "Individuell aktieanalys"},
"swe_account_type":       {"en": "Account Type",         "fa": "نوع حساب",                 "sv": "Kontotyp"},
"swe_ai_analysis":        {"en": "AI Analysis — Groq LLaMA 3.3 70B",
                           "fa": "تحلیل AI — Groq LLaMA 3.3 70B",
                           "sv": "AI-analys — Groq LLaMA 3.3 70B"},
"swe_full_overview":      {"en": "Full OMXS30 Overview", "fa": "نمای کامل OMXS30",         "sv": "Fullständig OMXS30-översikt"},
"swe_isk":                {"en": "ISK (Tax-Free)", "fa": "ISK (بدون مالیات)", "sv": "ISK (skattefritt)"},
"swe_af":                 {"en": "AF (Standard)", "fa": "AF (استاندارد)", "sv": "AF (vanligt)"},
"swe_kapital":            {"en": "Kapitalförsäkring", "fa": "بیمه سرمایه", "sv": "Kapitalförsäkring"},

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING INTELLIGENCE HUB (hub_) — skills hub
# ═══════════════════════════════════════════════════════════════════════════════

"hub_macro_dashboard":    {"en": "Live Macro Dashboard",  "fa": "داشبورد کلان زنده",        "sv": "Levande makrodashboard"},
"hub_select_skill":       {"en": "Select a trading skill","fa": "انتخاب مهارت معاملاتی",    "sv": "Välj handelsverktyg"},

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING INTELLIGENCE HUB V2 (hub2_) — 31 skills
# ═══════════════════════════════════════════════════════════════════════════════

"hub2_cross_asset":       {"en": "Cross-Asset Ratio Dashboard",
                           "fa": "داشبورد نسبت بین‌دارایی",
                           "sv": "Tvärmarknadsdashboard"},
"hub2_signal_inputs":     {"en": "Enter Signal Inputs",  "fa": "ورودی‌های سیگنال",          "sv": "Ange signalindata"},

# ═══════════════════════════════════════════════════════════════════════════════
# TRADING TOOLKIT (tt_) — 5 hidden engines
# ═══════════════════════════════════════════════════════════════════════════════

"tt_title":               {"en": "Trading Toolkit",      "fa": "جعبه ابزار معاملاتی",      "sv": "Handelsverktygslåda"},
"tt_backtester":          {"en": "Strategy Backtester",   "fa": "بک‌تست استراتژی",           "sv": "Strategibacktest"},
"tt_risk_dashboard":      {"en": "Risk Dashboard",       "fa": "داشبورد ریسک",              "sv": "Riskdashboard"},
"tt_portfolio":           {"en": "Portfolio Optimizer",   "fa": "بهینه‌ساز پرتفوی",          "sv": "Portföljoptimering"},
"tt_predictions":         {"en": "AI Prediction Engine",  "fa": "موتور پیش‌بینی AI",         "sv": "AI-prediktionsmotor"},
"tt_alerts":              {"en": "Alert & Notification Setup",
                           "fa": "تنظیم هشدار و اعلان",
                           "sv": "Aviserings- och notifieringsinställning"},

# ═══════════════════════════════════════════════════════════════════════════════
# AI COMMAND CENTER (cc_) — batch scan page
# ═══════════════════════════════════════════════════════════════════════════════

"cc_title":               {"en": "AI Command Center",    "fa": "مرکز فرماندهی AI",         "sv": "AI-kommandocentral"},
"cc_scan_all":            {"en": "SCAN ALL SIGNALS",     "fa": "اسکن همه سیگنال‌ها",        "sv": "SKANNA ALLA SIGNALER"},
"cc_top_signals":         {"en": "Today's Top Signals",  "fa": "بهترین سیگنال‌های امروز",    "sv": "Dagens toppsignaler"},
"cc_full_results":        {"en": "Full Scan Results",    "fa": "نتایج کامل اسکن",           "sv": "Fullständiga skanningsresultat"},
"cc_bloomberg":           {"en": "Bloomberg Intelligence","fa": "هوش بلومبرگ",               "sv": "Bloomberg Intelligence"},
"cc_position_sizer":      {"en": "Position Sizer",       "fa": "محاسبه اندازه پوزیشن",      "sv": "Positionsdimensionering"},
"cc_trade_journal":       {"en": "Trade Journal",        "fa": "دفتر معاملات",              "sv": "Handelsdagbok"},
"cc_econ_calendar":       {"en": "Economic Calendar",    "fa": "تقویم اقتصادی",             "sv": "Ekonomisk kalender"},
"lang_changed":           {"en": "Language changed. Page will refresh.",
                           "fa": "زبان تغییر کرد. صفحه بازنشانی می‌شود.",
                           "sv": "Språk ändrat. Sidan laddas om."},

}  # END OF TRANSLATIONS DICT



# ─── LOCALE PROFILE ──────────────────────────────────────────────────────────
# Council verdict: language is one of SIX locale axes for a trading platform.
# All six stored in a single session_state dict for persistence across pages.

LOCALE_PROFILES = {
    "en": {
        "lang": "en",
        "timezone": "America/New_York",
        "number_format": "en_US",
        "currency": "USD",
        "currency_symbol": "$",
        "date_format": "MM/DD/YYYY",
        "thousand_sep": ",",
        "decimal_sep": ".",
        "font_family": "'Times New Roman', serif",
        "dir": "ltr",
    },
    "fa": {
        "lang": "fa",
        "timezone": "Asia/Tehran",
        "number_format": "fa_IR",
        "currency": "IRR",
        "currency_symbol": "﷼",
        "date_format": "YYYY/MM/DD",
        "thousand_sep": "٬",
        "decimal_sep": "٫",
        "font_family": "'Vazirmatn', 'Tahoma', sans-serif",
        "dir": "rtl",
    },
    "sv": {
        "lang": "sv",
        "timezone": "Europe/Stockholm",
        "number_format": "sv_SE",
        "currency": "SEK",
        "currency_symbol": "kr",
        "date_format": "YYYY-MM-DD",
        "thousand_sep": " ",
        "decimal_sep": ",",
        "font_family": "'Times New Roman', serif",
        "dir": "ltr",
    },
}


# ─── UTILITY FUNCTIONS ────────────────────────────────────────────────────────

def get_lang() -> str:
    """Returns current language code from session state. Defaults to 'en'."""
    return st.session_state.get("qe_lang", DEFAULT_LANG)


def get_locale_profile() -> dict:
    """Returns the full locale profile dict for the current language."""
    lang = get_lang()
    return LOCALE_PROFILES.get(lang, LOCALE_PROFILES[DEFAULT_LANG])


def t(key: str) -> str:
    """
    Translate a key to the current language.
    Falls back to English, then to the raw key itself.
    """
    lang = get_lang()
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("en", key))


def fmt_number(value: float, decimals: int = 2) -> str:
    """
    Format a number according to the current locale.
    Council mandate: number formatting is a SAFETY issue in trading platforms.
    
    Examples:
        en: 1,234.56
        sv: 1 234,56
        fa: 1٬234٫56
    """
    profile = get_locale_profile()
    tsep = profile["thousand_sep"]
    dsep = profile["decimal_sep"]
    
    # Format with standard separators first
    if decimals > 0:
        formatted = f"{value:,.{decimals}f}"
    else:
        formatted = f"{value:,.0f}"
    
    # Replace standard separators with locale-specific
    # Step 1: temporary placeholder for decimal
    formatted = formatted.replace(".", "DECIMAL")
    # Step 2: replace thousand separator
    formatted = formatted.replace(",", tsep)
    # Step 3: replace decimal
    formatted = formatted.replace("DECIMAL", dsep)
    
    return formatted


def fmt_currency(value: float, decimals: int = 2, show_symbol: bool = True) -> str:
    """
    Format a currency value with locale-appropriate symbol and number format.
    
    Examples:
        en: $1,234.56
        sv: 1 234,56 kr
        fa: ﷼1٬234٫56
    """
    profile = get_locale_profile()
    num = fmt_number(value, decimals)
    
    if not show_symbol:
        return num
    
    symbol = profile["currency_symbol"]
    lang = profile["lang"]
    
    # Symbol placement: $ prefix for USD, suffix for SEK/IRR
    if lang == "en":
        return f"{symbol}{num}"
    elif lang == "sv":
        return f"{num} {symbol}"
    elif lang == "fa":
        return f"{num} {symbol}"
    else:
        return f"{symbol}{num}"


def fmt_date(dt) -> str:
    """
    Format a datetime according to locale date format.
    
    Examples:
        en: 04/28/2026
        sv: 2026-04-28
        fa: 1405/02/08 (Solar Hijri approximation)
    """
    import datetime as _dt
    if isinstance(dt, str):
        return dt
    if not isinstance(dt, (_dt.date, _dt.datetime)):
        return str(dt)
    
    profile = get_locale_profile()
    fmt = profile["date_format"]
    
    if fmt == "MM/DD/YYYY":
        return dt.strftime("%m/%d/%Y")
    elif fmt == "YYYY-MM-DD":
        return dt.strftime("%Y-%m-%d")
    elif fmt == "YYYY/MM/DD":
        # Solar Hijri approximation for Persian
        # Accurate conversion requires jdatetime library
        # Fallback: ISO format with note
        try:
            import jdatetime
            if isinstance(dt, _dt.datetime):
                jdt = jdatetime.datetime.fromgregorian(datetime=dt)
            else:
                jdt = jdatetime.date.fromgregorian(date=dt)
            return jdt.strftime("%Y/%m/%d")
        except ImportError:
            return dt.strftime("%Y/%m/%d")
    return dt.strftime("%Y-%m-%d")


def fmt_time(dt) -> str:
    """Format time with timezone context."""
    import datetime as _dt
    if not isinstance(dt, (_dt.time, _dt.datetime)):
        return str(dt)
    
    profile = get_locale_profile()
    tz_name = profile["timezone"].split("/")[-1].replace("_", " ")
    
    if isinstance(dt, _dt.datetime):
        return f"{dt.strftime('%H:%M')} ({tz_name})"
    return f"{dt.strftime('%H:%M')} ({tz_name})"


def render_language_selector() -> None:
    """
    Renders language + locale selector in the SIDEBAR.
    Call ONCE in app.py — persists across all pages via session state.
    Triggers st.rerun() on change to refresh all text.
    """
    if "qe_lang" not in st.session_state:
        st.session_state["qe_lang"] = DEFAULT_LANG

    with st.sidebar:
        st.markdown("---")
        options = list(SUPPORTED_LANGUAGES.keys())
        current_idx = options.index(st.session_state["qe_lang"]) if st.session_state["qe_lang"] in options else 0

        selected = st.radio(
            label="🌐 " + t("lang_select_label"),
            options=options,
            format_func=lambda k: f'{SUPPORTED_LANGUAGES[k]["flag"]} {SUPPORTED_LANGUAGES[k]["name"]}',
            index=current_idx,
            key="qe_lang_selector",
            horizontal=True,
        )

        if selected != st.session_state.get("qe_lang"):
            st.session_state["qe_lang"] = selected
            st.rerun()
        
        # Show locale info
        profile = get_locale_profile()
        tz_display = profile["timezone"].replace("_", " ").split("/")[-1]
        st.caption(f"🕐 {tz_display} · {profile['currency']}")


def inject_rtl_css() -> None:
    """
    Injects RTL CSS + Vazirmatn font when Persian is active.
    Council finding: Vazirmatn is the standard Persian web font.
    Safe to call on every page — does nothing for LTR languages.
    """
    if get_lang() != "fa":
        return

    st.markdown("""
    <style>
    /* Vazirmatn — standard Persian/Farsi web font (Council recommendation) */
    @import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');
    
    /* RTL support for Persian/Farsi text */
    .stMarkdown, .stText, .stTitle, .stHeader, .stSubheader,
    .stCaption, .stAlert, .stMetric label,
    .stRadio label, .stSelectbox label, .stTextInput label,
    .stExpander summary, .stTabs [data-baseweb="tab"] {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Vazirmatn', 'Tahoma', sans-serif !important;
    }
    /* Keep numbers, code, charts, and technical content LTR */
    .stMetric [data-testid="stMetricValue"],
    .stMetric [data-testid="stMetricDelta"],
    code, pre, .stCodeBlock, .stPlotlyChart,
    .stDataFrame, .stTable {
        direction: ltr !important;
        text-align: left !important;
    }
    /* Sidebar navigation stays LTR for icons */
    [data-testid="stSidebarNav"] {
        direction: ltr !important;
    }
    </style>
    """, unsafe_allow_html=True)


def get_text_dir() -> str:
    """Returns 'rtl' for Persian, 'ltr' for everything else."""
    return SUPPORTED_LANGUAGES.get(get_lang(), {}).get("dir", "ltr")
