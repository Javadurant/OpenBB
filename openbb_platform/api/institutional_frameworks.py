"""
api/institutional_frameworks.py
================================
10 institutional investor frameworks for the AITab "Institutional Frameworks" panel.

Each entry contains a system prompt that grounds the LLM in that investor's
PUBLISHED methodology — no invented principles. The prompts are designed to be
combined with live ticker data (price, fundamentals, technicals) and submitted
to Groq LLaMA 3.3 70B via data_clients.ai_analyze().

The frontend SENTRIQ/src/components/symbol/AITab.tsx triggers
GET /api/symbol/{ticker}/framework/{name}; this module supplies the lens.

Constitutional rules respected:
- ZERO invented domain values (methodologies are public knowledge)
- WHITELIST-based name validation (prevents arbitrary prompt injection)
- Each framework's "lens" reflects publicly documented investment philosophy
"""
from __future__ import annotations
from typing import Dict, Final, List

# ── 10 INSTITUTIONAL FRAMEWORKS ──────────────────────────────────────────────
# Each value is a SYSTEM PROMPT FRAGMENT for Groq. Combined at runtime with
# ticker-specific live data to produce a structured analysis.
INSTITUTIONAL_FRAMEWORKS: Final[Dict[str, Dict[str, str]]] = {
    "Druckenmiller": {
        "display_name": "Stanley Druckenmiller",
        "key_lens": "Top-down macro liquidity + concentrated asymmetric bets",
        "horizon": "12-24 months",
        "source_book":   "Schwager, J. (1992). The New Market Wizards (Druckenmiller interview chapter)",
        "key_principle": "When macro liquidity, fundamentals, and price action align, bet large.",
        "source_url":    "https://en.wikipedia.org/wiki/Stanley_Druckenmiller",
        "system_prompt": (
            "You are analyzing a stock through Stanley Druckenmiller's published lens:\n"
            "- TOP-DOWN: macro liquidity (Fed policy, money supply, real yields) drives flows\n"
            "- CONCENTRATION: 'When you see it, bet the ranch' — high conviction = large size\n"
            "- ASYMMETRY: identify setups where upside vastly exceeds downside\n"
            "- BUSINESS MOMENTUM: alongside macro, prefer accelerating revenue/earnings\n"
            "- TIME HORIZON: 12-24 months typical hold\n"
            "Output: assess whether liquidity tailwinds AND business momentum align."
        ),
    },
    "Soros": {
        "display_name": "George Soros",
        "key_lens": "Reflexivity — perception drives fundamentals which drive perception",
        "horizon": "Cycle-dependent (months to years)",
        "source_book":   "Soros, G. (1987). The Alchemy of Finance",
        "key_principle": "Markets are reflexive — perception influences fundamentals, which then influence perception.",
        "source_url":    "https://en.wikipedia.org/wiki/Reflexivity_(social_theory)",
        "system_prompt": (
            "You are analyzing through George Soros's published reflexivity framework:\n"
            "- BOOM-BUST CYCLE: where is the underlying narrative — early acceleration, "
            "plateau, or terminal blow-off?\n"
            "- REFLEXIVE FEEDBACK: identify self-reinforcing loops between price action "
            "and fundamentals\n"
            "- ASYMMETRIC SIZING: 'It's not whether you're right or wrong, but how much "
            "you make when right and lose when wrong'\n"
            "- THESIS INVALIDATION: at what price does the reflexive cycle break?\n"
            "Output: locate the cycle stage and the reflexive trigger that defines next move."
        ),
    },
    "Marks": {
        "display_name": "Howard Marks",
        "key_lens": "Second-level thinking + market cycle position",
        "horizon": "Multi-year, cycle-driven",
        "source_book":   "Marks, H. (2011). The Most Important Thing + Oaktree Memos",
        "key_principle": "Apply second-level thinking — go beyond consensus to identify where the crowd may be wrong.",
        "source_url":    "https://www.oaktreecapital.com/insights/memos",
        "system_prompt": (
            "You are analyzing through Howard Marks's published second-level thinking:\n"
            "- CONSENSUS GAP: what does the crowd believe, and where might they be wrong?\n"
            "- RISK-REWARD: at THIS price, is the expected loss bounded relative to gain?\n"
            "- CYCLE POSITION: market psychology — euphoric, complacent, anxious, capitulating?\n"
            "- WHAT YOU DON'T KNOW: explicitly state what could invalidate this view\n"
            "Output: state the consensus, the second-level edge, and the risk-reward setup."
        ),
    },
    "Klarman": {
        "display_name": "Seth Klarman",
        "key_lens": "Margin of safety — buy $1 of value for ≤ 50c",
        "horizon": "Patient, catalyst-driven",
        "source_book":   "Klarman, S. (1991). Margin of Safety",
        "key_principle": "Buy assets at a substantial discount to estimated intrinsic value.",
        "source_url":    "https://en.wikipedia.org/wiki/Seth_Klarman",
        "system_prompt": (
            "You are analyzing through Seth Klarman's published margin-of-safety framework:\n"
            "- INTRINSIC VALUE: estimate a conservative floor for this business's worth\n"
            "- DISCOUNT: is the market price ≤ 50% of that intrinsic value? (margin of safety)\n"
            "- DOWNSIDE FIRST: what's the worst-case loss if thesis is wrong?\n"
            "- CATALYST: what specific event will close the value-price gap?\n"
            "- CONTRARIAN/SPECIAL SITUATION: is this neglected or misunderstood?\n"
            "Output: quantify intrinsic vs. market, downside, and catalyst."
        ),
    },
    "Munger": {
        "display_name": "Charlie Munger",
        "key_lens": "Mental models + business quality + inversion",
        "horizon": "Long-term (decade+)",
        "source_book":   "Kaufman, P. (ed.) (2005). Poor Charlie's Almanack",
        "key_principle": "Use a multi-disciplinary mental-model lattice and the inversion principle.",
        "source_url":    "https://en.wikipedia.org/wiki/Charlie_Munger",
        "system_prompt": (
            "You are analyzing through Charlie Munger's published mental-models framework:\n"
            "- MOAT: what is the durable competitive advantage? (brand, scale, network, switching cost)\n"
            "- MANAGEMENT QUALITY: capital allocation track record\n"
            "- INVERSION: 'Invert, always invert' — what would destroy this business?\n"
            "- QUALITY vs PRICE: 'A great business at a fair price beats a fair business at a great price'\n"
            "- INTELLIGIBILITY: is this within your circle of competence?\n"
            "Output: assess moat, management, what could kill it, and quality-vs-price tradeoff."
        ),
    },
    "Lynch": {
        "display_name": "Peter Lynch",
        "key_lens": "Growth at reasonable price (GARP) + business intelligibility",
        "horizon": "2-3 years",
        "source_book":   "Lynch, P. (1989). One Up on Wall Street",
        "key_principle": "Buy what you understand at a reasonable price relative to growth (PEG <= 1).",
        "source_url":    "https://en.wikipedia.org/wiki/Peter_Lynch",
        "system_prompt": (
            "You are analyzing through Peter Lynch's published GARP framework:\n"
            "- PEG RATIO: P/E divided by earnings growth rate — target ≤ 1.0\n"
            "- CATEGORY: classify as Stalwart, Fast Grower, Slow Grower, Cyclical, Turnaround, or Asset Play\n"
            "- 'BUY WHAT YOU KNOW': is the business model intelligible to a layperson?\n"
            "- STORY DURABILITY: can the growth story last 2-3 years?\n"
            "- BALANCE SHEET: avoid heavy debt unless it's an Asset Play\n"
            "Output: PEG number, category, story strength, balance-sheet check."
        ),
    },
    "Buffett": {
        "display_name": "Warren Buffett",
        "key_lens": "Economic moat + owner earnings + intrinsic value",
        "horizon": "Forever (or until thesis breaks)",
        "source_book":   "Berkshire Hathaway Annual Letters (1965-present)",
        "key_principle": "Own businesses with durable economic moats and trustworthy management at fair prices.",
        "source_url":    "https://www.berkshirehathaway.com/letters/letters.html",
        "system_prompt": (
            "You are analyzing through Warren Buffett's published economic-moat framework:\n"
            "- MOAT: pricing power, brand, network effects, regulation, cost advantage\n"
            "- OWNER EARNINGS: free cash flow that's truly available to shareholders, not GAAP earnings\n"
            "- ROE DURABILITY: is the business earning ≥15% on equity consistently for 10+ years?\n"
            "- INTRINSIC VALUE: estimate using owner earnings × multiple appropriate for moat quality\n"
            "- MARGIN OF SAFETY: 'Be greedy when others are fearful' — buy below intrinsic\n"
            "- HOLDING PERIOD: 'Our favorite holding period is forever' — does this business compound?\n"
            "Output: moat description, ROE history, intrinsic-vs-price, holding-period verdict."
        ),
    },
    "Burry": {
        "display_name": "Michael Burry",
        "key_lens": "Deep-value contrarian + market structure dysfunction",
        "horizon": "Multi-year (patience required)",
        "source_book":   "Scion Asset Management 13F filings + Lewis, M. (2010). The Big Short",
        "key_principle": "Hunt for deep-value contrarian setups with structural mispricing.",
        "source_url":    "https://en.wikipedia.org/wiki/Michael_Burry",
        "system_prompt": (
            "You are analyzing through Michael Burry's published deep-value contrarian framework:\n"
            "- CONSENSUS DYSFUNCTION: where is the crowd structurally / mathematically wrong?\n"
            "- DEEP VALUE: book value, replacement cost, sum-of-parts — is price disconnected?\n"
            "- ASYMMETRIC PAYOFF: short setups with bounded loss, long setups with multi-bagger potential\n"
            "- PATIENCE: thesis may take 2-5 years to play out — short-term pain expected\n"
            "- MARKET STRUCTURE: is there a forced-seller or forced-buyer dynamic creating mispricing?\n"
            "Output: state the dysfunction, the asymmetry, and the time horizon required."
        ),
    },
    "Ackman": {
        "display_name": "Bill Ackman",
        "key_lens": "Activist-value + capital allocation catalysts",
        "horizon": "1-3 years (catalyst-driven)",
        "source_book":   "Pershing Square Capital Management investor letters",
        "key_principle": "Concentrated activist value — high-quality businesses where management improvements unlock value.",
        "source_url":    "https://pershingsquareholdings.com/investor-information/quarterly-and-annual-reports/",
        "system_prompt": (
            "You are analyzing through Bill Ackman's published activist-value framework:\n"
            "- HIGH-QUALITY BUSINESS: dominant, predictable, simple-to-understand\n"
            "- CAPITAL ALLOCATION: how is management deploying free cash flow — buybacks, M&A, dividends?\n"
            "- CATALYST: specific event in 1-3 years (restructuring, separation, buyback, activism)\n"
            "- CONCENTRATION: would this be a top-5 position in a 10-12 stock portfolio?\n"
            "- REASONABLE PRICE: not 'cheap' — willing to pay fair for quality + catalyst\n"
            "Output: business quality, capital-allocation read, specific catalyst, sizing verdict."
        ),
    },
    "Tepper": {
        "display_name": "David Tepper",
        "key_lens": "Distressed / cyclical + 'balls-to-the-wall' conviction",
        "horizon": "6-18 months (cycle-driven)",
        "source_book":   "Schwager, J. (2012). Hedge Fund Market Wizards (Tepper interview)",
        "key_principle": "Distressed/cyclical investing — buy when the world feels like it's ending.",
        "source_url":    "https://en.wikipedia.org/wiki/David_Tepper",
        "system_prompt": (
            "You are analyzing through David Tepper's published distressed/cyclical framework:\n"
            "- CYCLE POSITION: 'When the world is ending, buy stocks' — is sentiment at extremes?\n"
            "- POLICY TAILWIND: is government / central bank action creating a floor?\n"
            "- CONVICTION SIZING: when the setup aligns — 'balls to the wall' (large concentrated position)\n"
            "- ASYMMETRY: at distressed prices, downside is limited and upside is several-bagger\n"
            "- CATALYST: macro pivot, earnings inflection, or sector rotation\n"
            "Output: cycle position, policy backdrop, conviction-sizing verdict, catalyst horizon."
        ),
    },
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def list_frameworks() -> List[str]:
    """Return the whitelist of valid framework names (for input validation)."""
    return list(INSTITUTIONAL_FRAMEWORKS.keys())


def get_framework(name: str) -> Dict[str, str]:
    """
    Return the framework dict for a given name.
    Raises KeyError if name not in whitelist — caller should handle as 404.
    """
    if name not in INSTITUTIONAL_FRAMEWORKS:
        raise KeyError(f"Unknown framework: {name}")
    return INSTITUTIONAL_FRAMEWORKS[name]


def build_framework_prompt(
    name: str,
    company_name: str,
    ticker: str,
    price: float,
    facts: Dict[str, str],
) -> str:
    """
    Build the full Groq prompt: framework system prompt + live ticker facts.

    Returns a single string ready to pass to data_clients.ai_analyze().

    Args:
        name:         framework key (validated upstream via WHITELIST)
        company_name: human-readable name (e.g., "Apple Inc.")
        ticker:       symbol (e.g., "AAPL")
        price:        last price (already pre-validated as finite float)
        facts:        dict of free-text facts (e.g., {"P/E": "36.3",
                      "ROE": "141%", "RSI": "75.6"}) — caller builds this
                      from real engine outputs.
    """
    fw = get_framework(name)
    facts_block = "\n".join(f"  - {k}: {v}" for k, v in facts.items())
    return (
        f"{fw['system_prompt']}\n\n"
        f"TARGET: {company_name} ({ticker}) at ${price:.2f}\n"
        f"TIME HORIZON: {fw['horizon']}\n"
        f"LIVE FACTS:\n{facts_block}\n\n"
        "RESPOND IN EXACTLY THIS FORMAT (one line each):\n"
        "VERDICT: BUY | HOLD | SELL | AVOID\n"
        "SCORE: 0-100 (your conviction)\n"
        "THESIS: 3-5 sentence analysis through this specific investor's lens. "
        "Be SPECIFIC to this lens — do not write a generic analysis.\n"
        "KEY_RISK: one sentence — the single biggest threat to this thesis."
    )
