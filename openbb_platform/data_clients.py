"""
data_clients.py
===============
Ready-to-use API clients for all 7 data sources.
Import any client in any page or engine file.

Usage examples:
    from data_clients import groq_client, fmp_get, tiingo_get, fred_get, av_get

    # Groq AI analysis
    response = groq_client().chat.completions.create(...)

    # FMP stock data
    data = fmp_get("/v3/profile/AAPL")

    # Tiingo price data
    data = tiingo_get("/tiingo/daily/AAPL/prices")

    # FRED economic data
    data = fred_get("series/observations", series_id="GDP")

    # Alpha Vantage
    data = av_get(function="TIME_SERIES_DAILY", symbol="AAPL")
"""
import logging
from typing import Any, Dict, Optional
import requests
from env_config import cfg

logger = logging.getLogger(__name__)

_TIMEOUT = 20  # seconds

# ── Groq ──────────────────────────────────────────────────────────────────
def groq_client():
    """Returns an authenticated Groq client using GROQ_API_KEY."""
    from groq import Groq
    return Groq(api_key=cfg.validate("GROQ_API_KEY"))

# ── OpenAI ────────────────────────────────────────────────────────────────
def openai_client():
    """Returns an authenticated OpenAI client using OPENAI_API_KEY."""
    from openai import OpenAI
    return OpenAI(api_key=cfg.validate("OPENAI_API_KEY"))

# ── Anthropic (Claude) ────────────────────────────────────────────────────
def anthropic_client():
    """Returns an authenticated Anthropic client using ANTHROPIC_API_KEY."""
    import anthropic
    return anthropic.Anthropic(api_key=cfg.validate("ANTHROPIC_API_KEY"))

# ── FMP ───────────────────────────────────────────────────────────────────
_FMP_BASE = "https://financialmodelingprep.com/api"

def fmp_get(endpoint: str, **params) -> Any:
    """
    Fetch data from Financial Modeling Prep API.
    endpoint: e.g. "/v3/profile/AAPL"
    Returns parsed JSON or raises on error.
    """
    key = cfg.validate("FMP_API_KEY")
    url = f"{_FMP_BASE}{endpoint}"
    params["apikey"] = key
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

# ── Alpha Vantage ─────────────────────────────────────────────────────────
_AV_BASE = "https://www.alphavantage.co/query"

def av_get(function: str, **params) -> Dict[str, Any]:
    """
    Fetch data from Alpha Vantage API.
    function: e.g. "TIME_SERIES_DAILY", "GLOBAL_QUOTE"
    """
    key = cfg.validate("ALPHA_VANTAGE_API_KEY")
    params.update({"function": function, "apikey": key})
    resp = requests.get(_AV_BASE, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

# ── Tiingo ────────────────────────────────────────────────────────────────
_TIINGO_BASE = "https://api.tiingo.com"

def tiingo_get(endpoint: str, **params) -> Any:
    """
    Fetch data from Tiingo API.
    endpoint: e.g. "/tiingo/daily/AAPL/prices"
    """
    key = cfg.validate("TIINGO_API_KEY")
    url = f"{_TIINGO_BASE}{endpoint}"
    headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
    resp = requests.get(url, headers=headers, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

# ── FRED (Federal Reserve) ────────────────────────────────────────────────
_FRED_BASE = "https://api.stlouisfed.org/fred"

def fred_get(endpoint: str, **params) -> Dict[str, Any]:
    """
    Fetch data from FRED API.
    endpoint: e.g. "series/observations"
    params: e.g. series_id="GDP", observation_start="2020-01-01"
    """
    key = cfg.validate("FRED_API_KEY")
    url = f"{_FRED_BASE}/{endpoint}"
    params.update({"api_key": key, "file_type": "json"})
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

# ── Convenience: get any AI text response ────────────────────────────────
def ai_analyze(prompt: str, model: str = "groq", max_tokens: int = 1024) -> str:
    """
    Get AI analysis from Groq (default), OpenAI, or Anthropic.
    Automatically falls back to next available model.
    """
    if model == "groq" and cfg.GROQ_API_KEY:
        client = groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    elif model == "openai" and cfg.OPENAI_API_KEY:
        client = openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    elif model == "anthropic" and cfg.ANTHROPIC_API_KEY:
        client = anthropic_client()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    # <- NEW [provider-layer]: OpenAI-compatible providers (Fireworks/Together/
    #    DeepInfra/SambaNova/Ollama) via the unified ai_providers layer.
    try:
        import ai_providers
        if model in ai_providers.provider_names():
            out = ai_providers.chat(
                [{"role": "user", "content": prompt}],
                provider=model, temperature=0.1, max_tokens=max_tokens,
            )
            if out:
                return out
    except Exception as exc:  # graceful: fall through to the chain
        logger.warning("ai_providers branch failed for %s: %s", model, exc)

    # Fallback chain
    for fallback in ["groq", "openai", "anthropic"]:
        if fallback != model:
            try:
                return ai_analyze(prompt, model=fallback, max_tokens=max_tokens)
            except Exception:
                continue
    # <- NEW [provider-layer]: last-resort multi-provider fallback (any keyed/local)
    try:
        import ai_providers
        out = ai_providers.chat([{"role": "user", "content": prompt}],
                                temperature=0.1, max_tokens=max_tokens)
        if out:
            return out
    except Exception:
        pass
    raise RuntimeError("No AI API keys configured. Add at least one to .env")

if __name__ == "__main__":
    from env_config import cfg
    print("\n🔑 Data Client Status:")
    for k, v in cfg.status().items():
        icon = "✅" if v else "❌"
        print(f"  {icon} {k}")
    print()
