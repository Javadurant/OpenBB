"""
Canonical Market Instrument Registry
------------------------------------
Single source of truth for asset identity, exchange, and data-source routing.
Metadata only. No fetch or execution logic.
"""

INSTRUMENTS = {
    "AVANZA_BANK": {
        "name": "Avanza Bank Holding AB",
        "asset_class": "equity",
        "ticker": "AZA.ST",
        "exchange": "Nasdaq Stockholm",
        "currency": "SEK",
        "data_sources": {
            "primary": "yahoo",
            "fallback": ["polygon", "stooq"],
        },
        "notes": "Swedish listed equity. Avanza API is NOT a market data source.",
    },

    "XAUUSD": {
        "name": "Gold Spot vs USD",
        "asset_class": "commodity",
        "ticker": "XAUUSD",
        "exchange": "OTC",
        "currency": "USD",
        "data_sources": {
            "primary": "oanda",
            "fallback": ["fxcm", "twelvedata"],
        },
        "notes": "Spot gold (LBMA reference). Do NOT substitute with GC=F futures.",
    },

    "AYAR_GOLD": {
        "name": "Ayar Gold Fund",
        "asset_class": "fund",
        "ticker": "AYAR",
        "exchange": "Tehran Stock Exchange",
        "currency": "IRR",
        "data_sources": {
            "primary": "tsetmc", 
            "fallback": [],
        },
        "notes": "Gold Fund. Requires manual data source or proxy if TSETMC is unavailable.",
    },
}

# ------------------------------------------------------------------
# Provider Resolution Helpers (Pure, Deterministic, Side-Effect Free)
# ------------------------------------------------------------------

def get_instrument(instrument_key: str) -> dict:
    return INSTRUMENTS[instrument_key]

def get_primary_provider(instrument_key: str) -> str | None:
    return INSTRUMENTS[instrument_key]["data_sources"]["primary"]

def get_fallback_providers(instrument_key: str) -> list[str]:
    return INSTRUMENTS[instrument_key]["data_sources"].get("fallback", [])

def is_tradable(instrument_key: str) -> bool:
    return INSTRUMENTS[instrument_key]["asset_class"] != "broker"