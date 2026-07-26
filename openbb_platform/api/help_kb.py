"""
api/help_kb.py  — <- NEW [HELP/KB]: curated, SECRETS-FREE knowledge base + retriever.

SECURITY CONTRACT (Gurpreet sign-off): this module is the ONLY corpus the help
agent is ever allowed to see. It contains ZERO secrets — no API keys, no env var
names, no file paths, no server/infra config, no personal info, no vendor key
stack. Domain content is conceptual and attributed (harmonics -> Carney; Elliott
-> Frost & Prechter); no ratios/tolerances are invented here.
"""
from __future__ import annotations

import re
from typing import Final, TypedDict


class Article(TypedDict):
    id: str
    category: str
    title: str
    summary: str
    body: str
    keywords: str
    route: str


class Faq(TypedDict):
    id: str
    category: str
    q: str
    a: str
    keywords: str


# ── Knowledge base articles ───────────────────────────────────────────────
_ARTICLES: Final[list[Article]] = [
    {"id": "getting-started", "category": "Getting Started", "route": "/",
     "title": "What is SENTRIQ and how do I start?",
     "summary": "SENTRIQ is a trading-signal terminal for US and Stockholm (OMX) equities.",
     "keywords": "start begin intro overview welcome new user dashboard home",
     "body": "SENTRIQ is an institutional-style research terminal covering US equities and "
             "OMX Stockholm tickers (the .ST suffix). Start by searching for any asset in the "
             "top search bar (or press Cmd/Ctrl+K), open its Symbol page, and explore the tabs: "
             "Overview, Technical, Fundamental, News, Psychology, AI Analysis, Risk and Data. "
             "The Discover page surfaces a daily Setup of the Day and a Track Record of past calls."},
    {"id": "search-symbols", "category": "Symbols & Search", "route": "/",
     "title": "How do I find a stock or symbol?",
     "summary": "Search by company name or ticker; Stockholm tickers use the .ST suffix.",
     "keywords": "search find ticker symbol company name omx stockholm .ST swedish us equity asset lookup",
     "body": "Use the search bar at the top of any page, or press Cmd+K (Mac) / Ctrl+K (Windows) "
             "to open quick search. You can type a company name (e.g. Apple, Volvo) or a ticker. "
             "US tickers are plain (AAPL, NVDA). Stockholm / OMX tickers carry a .ST suffix "
             "(e.g. VOLV-B.ST, SEB-A.ST, INVE-B.ST). Results show the company name first so you "
             "do not have to remember exact tickers."},
    {"id": "chart-timeframes", "category": "Chart & Timeframes", "route": "/symbol/AAPL",
     "title": "Using the chart: timeframes, ranges and overlays",
     "summary": "Switch interval (1H/1D/1W/1M) and zoom window (3M/1Y/All); toggle overlays.",
     "keywords": "chart candlestick timeframe interval hourly daily weekly monthly range 3m 1y all "
                 "volume bollinger ma20 moving average pitchfork zoom pan",
     "body": "On the Overview tab the candlestick chart supports four intervals — 1H (hourly), "
             "1D (daily), 1W (weekly), 1M (monthly) — and three zoom windows — 3M, 1Y and All. "
             "Toggle overlays for Volume, MA 20, Bollinger Bands and the Andrews Pitchfork. "
             "Click and drag to pan, scroll to zoom, and hover for the OHLC readout. Detected "
             "harmonic patterns and the nearest near-miss are labelled directly on the chart."},
    {"id": "overview-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=overview",
     "title": "The Overview tab",
     "summary": "Snapshot: price, chart, AI snapshot, leanings and top news.",
     "keywords": "overview snapshot price at-a-glance identity ai summary news strip",
     "body": "Overview is the home of a Symbol page: the interactive chart, an at-a-glance price "
             "and identity panel, an AI snapshot with directional leanings (bullish / bearish / "
             "neutral chips), and a strip of the latest news headlines."},
    {"id": "technical-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=technical",
     "title": "The Technical tab",
     "summary": "Multi-engine technicals: indicators, harmonics, Ichimoku, Signal Proximity, Pitchfork.",
     "keywords": "technical analysis indicators rsi macd bollinger ichimoku harmonic proximity pitchfork engine",
     "body": "The Technical tab runs the multi-engine analysis: momentum and trend indicators, "
             "harmonic pattern detection, Ichimoku cloud, the Signal Proximity readout (how close "
             "each indicator is to a meaningful threshold) and the Andrews Pitchfork geometry."},
    {"id": "fundamental-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=fundamental",
     "title": "The Fundamental tab",
     "summary": "Company financials plus an Analyst Intelligence card (rating, scores, earnings, dividends).",
     "keywords": "fundamental financials analyst rating earnings dividend valuation pe score",
     "body": "Fundamental shows company financials and an Analyst Intelligence card: a composite "
             "rating, component score bars, analyst grade changes, an earnings calendar with "
             "beat/miss, and dividend history. The card hides itself for tickers without coverage."},
    {"id": "news-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=news",
     "title": "The News tab",
     "summary": "Headlines with sentiment, related tickers and official SEC filings.",
     "keywords": "news headlines sentiment bull bear filings sec 8-k 10-q form 4 publisher",
     "body": "News aggregates headlines with sentiment badges (bull / bear / flat), related-ticker "
             "chips and keyword tags. It also surfaces official SEC EDGAR filings (8-K, 10-Q, "
             "Form 4 and more) so you can read primary sources."},
    {"id": "psychology-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=psychology",
     "title": "The Psychology tab",
     "summary": "Market psychology plus institutional ownership / flow.",
     "keywords": "psychology sentiment institutional ownership flow blackrock vanguard grade",
     "body": "Psychology blends behavioural read-outs with an institutional flow view — large "
             "holders and their positioning — summarised into a directional lean and grade."},
    {"id": "ai-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=ai",
     "title": "The AI Analysis tab",
     "summary": "AI narrative plus ten institutional framework buttons.",
     "keywords": "ai analysis narrative framework institutional buttons groq llm",
     "body": "AI Analysis gives a plain-language narrative and ten institutional framework buttons. "
             "Each framework returns a focused read-out with its source book and key principle so "
             "you can see the reasoning behind the lens."},
    {"id": "risk-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=risk",
     "title": "The Risk tab",
     "summary": "Volatility, drawdown and position-context risk metrics.",
     "keywords": "risk volatility drawdown atr exposure position stop",
     "body": "Risk surfaces volatility and drawdown context to help you size and frame a trade. "
             "Levels are computed from live data, never hardcoded."},
    {"id": "data-tab", "category": "Symbol Tabs", "route": "/symbol/AAPL?tab=data",
     "title": "The Data tab",
     "summary": "Raw quote and series data with source + as-of provenance.",
     "keywords": "data quote raw series provenance source as of",
     "body": "Data exposes the underlying quote and series with provenance — each value shows its "
             "source and an as-of timestamp so you always know how fresh a number is."},
    {"id": "harmonic-patterns", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=technical",
     "title": "Harmonic patterns and the PRZ",
     "summary": "Geometric reversal patterns; ratios follow Carney's Harmonic Trading.",
     "keywords": "harmonic gartley bat crab butterfly shark cypher prz reversal carney pattern near miss",
     "body": "Harmonic patterns are geometric price structures (Gartley, Bat, Butterfly, Crab, "
             "Shark, Cypher and others) whose ratio rules follow Scott Carney's Harmonic Trading "
             "(Vol. 1-3). When a pattern's points satisfy the rules, SENTRIQ marks a Potential "
             "Reversal Zone (PRZ) — a price band to watch for a turn. If no pattern is confirmed, "
             "the chart shows the nearest near-miss and by how much a ratio is off, so you can see "
             "what almost qualified. SENTRIQ never relaxes Carney's tolerances to force a match."},
    {"id": "elliott-wave", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=technical",
     "title": "Elliott Wave phases",
     "summary": "Wave structure read using Frost & Prechter's rules.",
     "keywords": "elliott wave impulse correction w3 w5 reversal frost prechter phase",
     "body": "Elliott Wave describes trends as repeating impulse and corrective wave structures. "
             "SENTRIQ labels the current wave phase using the rules from Frost & Prechter's "
             "Elliott Wave Principle. Wave phase feeds the Signal Proximity read-out for context."},
    {"id": "ichimoku", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=technical",
     "title": "Ichimoku cloud",
     "summary": "Trend, support/resistance and momentum in one overlay.",
     "keywords": "ichimoku cloud kumo tenkan kijun tk cross price vs cloud",
     "body": "The Ichimoku cloud combines trend, support/resistance and momentum. SENTRIQ reports "
             "whether price sits above, inside or below the cloud and whether a TK cross has "
             "occurred, then folds that into the proximity read-out."},
    {"id": "indicators", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=technical",
     "title": "RSI, MACD, Bollinger and moving averages",
     "summary": "The core momentum, trend and volatility indicators.",
     "keywords": "rsi macd bollinger bands moving average ma20 overbought oversold momentum",
     "body": "RSI flags overbought / oversold momentum; MACD tracks trend momentum via its signal "
             "line and histogram; Bollinger Bands show volatility envelopes around a moving "
             "average; MA 20 is a short trend reference drawn on the chart."},
    {"id": "signal-proximity", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=technical",
     "title": "Signal Proximity",
     "summary": "How close each indicator is to a meaningful threshold — a 'nearest-to' read-out.",
     "keywords": "signal proximity readout nearest threshold lean to note rsi macd bollinger cloud",
     "body": "Signal Proximity tells you how close each indicator is to a meaningful level (for "
             "example, how far RSI is from overbought, or price from a Bollinger band or cloud "
             "edge). It is a separate 'nearest-to' read-out and never changes pattern detection."},
    {"id": "andrews-pitchfork", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=overview",
     "title": "Andrews Pitchfork",
     "summary": "A median line with parallel rails drawn from three pivots.",
     "keywords": "andrews pitchfork median line rails channel three pivots geometry",
     "body": "The Andrews Pitchfork draws a median line and two parallel rails from three chosen "
             "pivots to frame a trend channel. It is pure geometry — no invented ratios — and is "
             "drawn directly on the Overview chart when the Pitchfork overlay is on."},
    {"id": "institutional-frameworks", "category": "Analysis Concepts", "route": "/symbol/AAPL?tab=ai",
     "title": "The ten institutional frameworks",
     "summary": "Named analytical lenses, each with its source book and key principle.",
     "keywords": "institutional framework lens buttons methodology source book principle ai tab",
     "body": "The AI Analysis tab offers ten institutional frameworks — each a named analytical "
             "lens you can apply to the current symbol. Every framework cites its source book and "
             "key principle, so the output is traceable rather than a black box."},
    {"id": "setup-of-the-day", "category": "Discover", "route": "/discover",
     "title": "Setup of the Day",
     "summary": "Daily best A/B/C-graded setups across asset classes and regions.",
     "keywords": "setup of the day discover scanner grade a b c entry stop target atr isk kf swedish international",
     "body": "Setup of the Day scans for the best aligned setups and grades them A, B or C with an "
             "ATR-based entry, stop and target. It spans Swedish and International boxes across "
             "Equities, ETFs, Funds and Crypto. It is decision-support, not advice, and will "
             "honestly say when there is no A/B-grade setup. Time estimates are ATR windows, never "
             "fixed calendar dates."},
    {"id": "trust-ledger", "category": "Discover", "route": "/discover",
     "title": "Track Record (Trust Ledger)",
     "summary": "An append-only record of past setups with win-rate and expectancy by grade.",
     "keywords": "track record trust ledger win rate expectancy reliability grade last checked honesty",
     "body": "The Track Record is an append-only ledger of past setups, evaluated look-ahead-safe, "
             "showing win-rate and expectancy by grade with sample counts and a reliability gate. "
             "It also shows when results were last checked. This keeps the product honest about "
             "how calls actually performed."},
    {"id": "the-council", "category": "Features", "route": "/demo",
     "title": "The streaming Council",
     "summary": "Multiple AI advisors deliberate, then a synthesis verdict.",
     "keywords": "council advisors deliberation streaming verdict synthesis hold buy multi model",
     "body": "The Council streams several AI advisors that each reason over the live market context "
             "for a symbol, then assembles a synthesis verdict (e.g. BUY / HOLD with a score). It "
             "is grounded in the symbol's own data — overview, technical and institutional read-outs."},
    {"id": "navigation", "category": "Navigation", "route": "/",
     "title": "Getting around: the main sections",
     "summary": "Symbol, Discover, Portfolio, Market, Bonds, News, Sweden and Lab.",
     "keywords": "navigation menu sections symbol discover portfolio market bonds news sweden lab nav",
     "body": "The top navigation covers: Symbol (per-asset research), Discover (daily setups + track "
             "record), Portfolio, Market (broad market view), Bonds, News, Sweden (OMX focus) and "
             "Lab (experimental tools). The search bar and Cmd+K quick search work from anywhere."},
    {"id": "pricing-tiers", "category": "Account & Pricing", "route": "/pricing",
     "title": "Free, Pro and Vault tiers",
     "summary": "Three plans; Vault is the top tier and uses BankID sign-in.",
     "keywords": "pricing plan tier free pro vault upgrade subscription bankid mastermind glass",
     "body": "SENTRIQ has three tiers — Free, Pro and Vault. Higher tiers unlock more depth and "
             "the premium Vault experience. Vault sign-in uses BankID. See the Pricing page for "
             "the current feature breakdown per tier."},
    {"id": "ratings-feedback", "category": "Account & Pricing", "route": "/",
     "title": "Rating help, FAQ and sections",
     "summary": "Give 1-5 stars on any help article, FAQ answer, AI answer or section.",
     "keywords": "rating stars feedback helpful thumbs review rate quality",
     "body": "You can rate help articles, FAQ answers, the assistant's AI answers, and individual "
             "sections with 1-5 stars (and a quick 'was this helpful?'). Ratings are anonymous and "
             "help improve the product — no personal information is stored."},
    {"id": "data-provenance", "category": "Data", "route": "/symbol/AAPL?tab=data",
     "title": "Where the numbers come from",
     "summary": "Market data is from licensed providers; every value shows source + as-of.",
     "keywords": "data provider provenance source as of fresh delayed realtime quote series",
     "body": "Market data is sourced from licensed providers with a tiered fallback for resilience. "
             "Every value carries provenance — its source and an as-of timestamp — so you can judge "
             "freshness. Some free data is end-of-day; real-time depth depends on your plan."},
]

# ── FAQ ────────────────────────────────────────────────────────────────────
_FAQ: Final[list[Faq]] = [
    {"id": "faq-find-stock", "category": "Symbols & Search",
     "q": "How do I find a specific stock?",
     "a": "Use the top search bar or press Cmd/Ctrl+K and type a company name or ticker. "
          "US tickers are plain (AAPL); Stockholm tickers end in .ST (VOLV-B.ST).",
     "keywords": "find stock search ticker symbol company"},
    {"id": "faq-swedish", "category": "Symbols & Search",
     "q": "How do I look up a Swedish / OMX stock?",
     "a": "Swedish (OMX Stockholm) tickers use the .ST suffix, e.g. VOLV-B.ST or SEB-A.ST. "
          "You can also just type the company name and pick it from the results.",
     "keywords": "swedish omx stockholm .ST sweden ticker"},
    {"id": "faq-chart-blank", "category": "Chart & Timeframes",
     "q": "What do the 1H / 1D / 1W / 1M and 3M / 1Y / All buttons do?",
     "a": "1H-1M change the candle interval (hourly to monthly); 3M / 1Y / All change the zoom "
          "window. They are independent — pick an interval and a zoom that suit your analysis.",
     "keywords": "timeframe interval range zoom chart buttons hourly weekly monthly"},
    {"id": "faq-harmonic", "category": "Analysis Concepts",
     "q": "What is a PRZ / harmonic pattern?",
     "a": "A harmonic pattern is a geometric reversal structure (Gartley, Bat, Crab, etc.) defined "
          "by Carney's ratio rules. The PRZ (Potential Reversal Zone) is the price band to watch "
          "for a turn. If none is confirmed, the chart shows the nearest near-miss.",
     "keywords": "prz harmonic pattern reversal gartley bat crab carney"},
    {"id": "faq-near-miss", "category": "Analysis Concepts",
     "q": "Why does it say 'no confirmed harmonic, nearest ...'?",
     "a": "No pattern fully met Carney's ratio rules, so SENTRIQ shows the closest near-miss and "
          "how far a ratio is off. Tolerances are never relaxed to force a match.",
     "keywords": "near miss no confirmed harmonic nearest ratio off"},
    {"id": "faq-setup", "category": "Discover",
     "q": "What is Setup of the Day and is it financial advice?",
     "a": "It is a daily, graded (A/B/C) decision-support setup with an ATR-based entry, stop and "
          "target across regions and asset classes. It is not financial advice.",
     "keywords": "setup of the day advice grade decision support discover"},
    {"id": "faq-track-record", "category": "Discover",
     "q": "Can I see how past calls performed?",
     "a": "Yes — the Track Record (Trust Ledger) on Discover shows win-rate and expectancy by "
          "grade, with sample counts and when it was last checked.",
     "keywords": "track record performance win rate ledger past calls"},
    {"id": "faq-tiers", "category": "Account & Pricing",
     "q": "What is the difference between Free, Pro and Vault?",
     "a": "Three tiers with increasing depth; Vault is the premium tier and signs in with BankID. "
          "See the Pricing page for the current per-tier feature list.",
     "keywords": "free pro vault tier plan difference pricing bankid"},
    {"id": "faq-rate", "category": "Account & Pricing",
     "q": "How do I rate an answer or section?",
     "a": "Use the star control on any help article, FAQ answer, AI answer or section. Ratings are "
          "anonymous and store no personal information.",
     "keywords": "rate stars feedback helpful review"},
    {"id": "faq-ai-trust", "category": "Features",
     "q": "Can I trust the AI assistant's answers?",
     "a": "The assistant answers only from SENTRIQ's help knowledge base and cites the section it "
          "used. It will not discuss anything outside the product, and it cannot access private "
          "system or account internals.",
     "keywords": "ai assistant trust accurate cite source safe"},
]

# ── Retrieval (pure, no external deps) ──────────────────────────────────────
_TOKEN_RE: Final = re.compile(r"[a-z0-9]+")
_STOP: Final = frozenset(
    {"the", "a", "an", "is", "are", "do", "i", "to", "of", "and", "or", "for",
     "how", "what", "in", "on", "my", "me", "it", "this", "that", "with", "can",
     "does", "you", "your", "use", "using", "get", "find"}
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP]


def _score(query_tokens: set[str], art: Article) -> int:
    """Weighted overlap: title x3, keywords x2, body x1. Pure integer scoring."""
    if not query_tokens:
        return 0
    title = set(_tokens(art["title"]))
    keys = set(_tokens(art["keywords"]))
    body = set(_tokens(art["body"] + " " + art["summary"]))
    return (3 * len(query_tokens & title)
            + 2 * len(query_tokens & keys)
            + 1 * len(query_tokens & body))


def search(query: str, limit: int = 6) -> list[dict]:
    """Return ranked KB hits (articles + faq) for a free-text query."""
    qt = set(_tokens(query))
    scored: list[tuple[int, dict]] = []
    for art in _ARTICLES:
        s = _score(qt, art)
        if s > 0:
            scored.append((s, {"kind": "article", "id": art["id"], "title": art["title"],
                               "summary": art["summary"], "category": art["category"],
                               "route": art["route"]}))
    for f in _FAQ:
        fake: Article = {"id": f["id"], "category": f["category"], "title": f["q"],
                         "summary": f["a"][:120], "body": f["a"], "keywords": f["keywords"],
                         "route": "/"}
        s = _score(qt, fake)
        if s > 0:
            scored.append((s, {"kind": "faq", "id": f["id"], "title": f["q"],
                               "summary": f["a"], "category": f["category"], "route": "/"}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def retrieve_context(query: str, k: int = 4) -> list[Article]:
    """Top-k full articles for grounding the help agent (trusted text only)."""
    qt = set(_tokens(query))
    scored = [(_score(qt, a), a) for a in _ARTICLES]
    scored = [(s, a) for s, a in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [a for _, a in scored[:k]]
    if not top:  # always give the agent *something* trusted to ground on
        top = [a for a in _ARTICLES if a["id"] in ("getting-started", "navigation")]
    return top


def topics() -> list[dict]:
    """All articles grouped by category, for the Guides tab."""
    cats: dict[str, list[dict]] = {}
    for a in _ARTICLES:
        cats.setdefault(a["category"], []).append(
            {"id": a["id"], "title": a["title"], "summary": a["summary"],
             "body": a["body"], "route": a["route"]})
    return [{"category": c, "articles": arts} for c, arts in cats.items()]


def article(article_id: str) -> dict | None:
    for a in _ARTICLES:
        if a["id"] == article_id:
            return dict(a)
    return None


def faq() -> list[dict]:
    return [dict(f) for f in _FAQ]
