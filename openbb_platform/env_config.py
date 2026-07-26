"""
env_config.py
=============
Central API key loader for the entire QuantEdge platform.
Import this in EVERY Python file that needs an API key.

Usage:
    from env_config import cfg
    client = Groq(api_key=cfg.GROQ_API_KEY)
    openai_client = OpenAI(api_key=cfg.OPENAI_API_KEY)
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load from project root .env — works from any subdirectory
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

@dataclass(frozen=True)
class _Config:
    # ── AI / ML ───────────────────────────────────────────────────────────
    GROQ_API_KEY:         Optional[str] = None
    OPENAI_API_KEY:       Optional[str] = None
    ANTHROPIC_API_KEY:    Optional[str] = None

    # ── Financial Data ────────────────────────────────────────────────────
    FMP_API_KEY:          Optional[str] = None
    ALPHA_VANTAGE_API_KEY:Optional[str] = None
    TIINGO_API_KEY:       Optional[str] = None
    FRED_API_KEY:         Optional[str] = None
    EODHD_API_KEY:        Optional[str] = None
    POLYGON_API_KEY:      Optional[str] = None
    FINNHUB_API_KEY:      Optional[str] = None
    COINDESK_API_KEY:     Optional[str] = None

    # ── Council LLM providers (v3.7) ────────────────────────────────────────
    FIREWORKS_API_KEY:    Optional[str] = None
    TOGETHER_API_KEY:     Optional[str] = None
    DEEPINFRA_API_KEY:    Optional[str] = None
    SAMBANOVA_API_KEY:    Optional[str] = None
    OLLAMA_API_KEY:       Optional[str] = None

    # ── Other services (v3.7) ────────────────────────────────────────────────
    LUMIN_API_KEY:        Optional[str] = None
    FIRECRAWL_API_KEY:    Optional[str] = None
    APIFY_API_TOKEN:      Optional[str] = None
    BIGDATA_API_KEY:      Optional[str] = None
    TVREMIX_API_KEY:      Optional[str] = None

    # ── Infrastructure ────────────────────────────────────────────────────
    SECRET_KEY:           Optional[str] = None
    DATABASE_URL:         Optional[str] = None
    OBSIDIAN_VAULT_PATH:  Optional[str] = None

    def validate(self, key_name: str) -> str:
        """Return a key value or raise a clear error with fix instructions."""
        value = getattr(self, key_name, None)
        if not value:
            sources = {
                "GROQ_API_KEY":          "https://console.groq.com/keys",
                "OPENAI_API_KEY":        "https://platform.openai.com/api-keys",
                "ANTHROPIC_API_KEY":     "https://console.anthropic.com/account/keys",
                "FMP_API_KEY":           "https://financialmodelingprep.com/developer/docs",
                "ALPHA_VANTAGE_API_KEY": "https://www.alphavantage.co/",
                "TIINGO_API_KEY":        "https://www.tiingo.com/account/api/token",
                "FRED_API_KEY":          "https://fred.stlouisfed.org/docs/api/",
            }
            url = sources.get(key_name, "your .env file")
            raise ValueError(
                f"❌ {key_name} is not set.\n"
                f"   Add it to: {_PROJECT_ROOT}/.env\n"
                f"   Get it at: {url}"
            )
        return value

    def status(self) -> dict:
        """Returns which keys are configured (True/False — never exposes values)."""
        return {
            "GROQ_API_KEY":          bool(self.GROQ_API_KEY),
            "OPENAI_API_KEY":        bool(self.OPENAI_API_KEY),
            "ANTHROPIC_API_KEY":     bool(self.ANTHROPIC_API_KEY),
            "FMP_API_KEY":           bool(self.FMP_API_KEY),
            "ALPHA_VANTAGE_API_KEY": bool(self.ALPHA_VANTAGE_API_KEY),
            "TIINGO_API_KEY":        bool(self.TIINGO_API_KEY),
            "FRED_API_KEY":          bool(self.FRED_API_KEY),
            "EODHD_API_KEY":         bool(self.EODHD_API_KEY),
            "POLYGON_API_KEY":       bool(self.POLYGON_API_KEY),
            "FINNHUB_API_KEY":       bool(self.FINNHUB_API_KEY),
            "COINDESK_API_KEY":      bool(self.COINDESK_API_KEY),
            "FIREWORKS_API_KEY":     bool(self.FIREWORKS_API_KEY),
            "TOGETHER_API_KEY":      bool(self.TOGETHER_API_KEY),
            "DEEPINFRA_API_KEY":     bool(self.DEEPINFRA_API_KEY),
            "SAMBANOVA_API_KEY":     bool(self.SAMBANOVA_API_KEY),
            "OLLAMA_API_KEY":        bool(self.OLLAMA_API_KEY),
            "LUMIN_API_KEY":         bool(self.LUMIN_API_KEY),
            "FIRECRAWL_API_KEY":     bool(self.FIRECRAWL_API_KEY),
            "APIFY_API_TOKEN":       bool(self.APIFY_API_TOKEN),
            "BIGDATA_API_KEY":       bool(self.BIGDATA_API_KEY),
            "TVREMIX_API_KEY":       bool(self.TVREMIX_API_KEY),
        }

# Single import for the entire platform
cfg = _Config(
    GROQ_API_KEY=         os.getenv("GROQ_API_KEY",         "").strip().strip('"').strip("'") or None,
    OPENAI_API_KEY=       os.getenv("OPENAI_API_KEY",       "").strip().strip('"').strip("'") or None,
    ANTHROPIC_API_KEY=    os.getenv("ANTHROPIC_API_KEY",    "").strip().strip('"').strip("'") or None,
    FMP_API_KEY=          os.getenv("FMP_API_KEY",          "").strip().strip('"').strip("'") or None,
    ALPHA_VANTAGE_API_KEY=os.getenv("ALPHA_VANTAGE_API_KEY","").strip().strip('"').strip("'") or None,
    TIINGO_API_KEY=       os.getenv("TIINGO_API_KEY",       "").strip().strip('"').strip("'") or None,
    FRED_API_KEY=         os.getenv("FRED_API_KEY",         "").strip().strip('"').strip("'") or None,
    EODHD_API_KEY=        os.getenv("EODHD_API_KEY",        "").strip().strip('"').strip("'") or None,
    POLYGON_API_KEY=      os.getenv("POLYGON_API_KEY",      "").strip().strip('"').strip("'") or None,
    FINNHUB_API_KEY=      os.getenv("FINNHUB_API_KEY",      "").strip().strip('"').strip("'") or None,
    COINDESK_API_KEY=     os.getenv("COINDESK_API_KEY",     "").strip().strip('"').strip("'") or None,
    FIREWORKS_API_KEY=    os.getenv("FIREWORKS_API_KEY",    "").strip().strip('"').strip("'") or None,
    TOGETHER_API_KEY=     os.getenv("TOGETHER_API_KEY",     "").strip().strip('"').strip("'") or None,
    DEEPINFRA_API_KEY=    os.getenv("DEEPINFRA_API_KEY",    "").strip().strip('"').strip("'") or None,
    SAMBANOVA_API_KEY=    os.getenv("SAMBANOVA_API_KEY",    "").strip().strip('"').strip("'") or None,
    OLLAMA_API_KEY=       os.getenv("OLLAMA_API_KEY",       "").strip().strip('"').strip("'") or None,
    LUMIN_API_KEY=        os.getenv("LUMIN_API_KEY",        "").strip().strip('"').strip("'") or None,
    FIRECRAWL_API_KEY=    os.getenv("FIRECRAWL_API_KEY",    "").strip().strip('"').strip("'") or None,
    APIFY_API_TOKEN=      os.getenv("APIFY_API_TOKEN",      "").strip().strip('"').strip("'") or None,
    BIGDATA_API_KEY=      os.getenv("BIGDATA_API_KEY",      "").strip().strip('"').strip("'") or None,
    TVREMIX_API_KEY=      os.getenv("TVREMIX_API_KEY",      "").strip().strip('"').strip("'") or None,
    SECRET_KEY=           os.getenv("SECRET_KEY",           "").strip() or None,
    DATABASE_URL=         os.getenv("DATABASE_URL",         "").strip() or None,
    OBSIDIAN_VAULT_PATH=  os.getenv("OBSIDIAN_VAULT_PATH",  "").strip() or None,
)

if __name__ == "__main__":
    print("\n🔑 API Key Status:")
    for k, v in cfg.status().items():
        icon = "✅" if v else "❌"
        print(f"  {icon} {k}")
    print()
