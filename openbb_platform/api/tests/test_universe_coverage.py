"""
Universe-coverage honesty tests for Setup of the Day.

SENTRIQ product rule: the scanner must NEVER imply it searched the whole market
when it ranks within a curated watchlist. These tests pin the coverage-labelling
contract added to phase2_router so a future edit cannot silently start claiming
'full market' coverage for a hand-curated list. Pure — no network.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from api.phase2_router import (  # noqa: E402
    SETUP_UNIVERSE, UNIVERSE_SOURCE, _coverage_label_for, _universe_counts,
)

# The taxonomy the product is allowed to report. The "full_*" / "broad_*"
# labels are DELIBERATELY excluded here for a curated list: claiming them
# requires provider-list verification the current universe does not have.
CURATED_ALLOWED = {"small_watchlist_fallback", "curated_fallback", "data_limited"}
WHOLE_MARKET_CLAIMS = {"full_provider_market", "full_exchange_market"}


def test_universe_source_is_honest_not_whole_market():
    # A hardcoded tuple list is a curated watchlist, never a full market claim.
    assert UNIVERSE_SOURCE == "curated_watchlist"
    assert UNIVERSE_SOURCE not in WHOLE_MARKET_CLAIMS


def test_coverage_label_thresholds():
    assert _coverage_label_for(0) == "data_limited"
    assert _coverage_label_for(1) == "small_watchlist_fallback"
    assert _coverage_label_for(12) == "small_watchlist_fallback"   # matches "12 scanned" card
    assert _coverage_label_for(15) == "small_watchlist_fallback"
    assert _coverage_label_for(16) == "curated_fallback"
    assert _coverage_label_for(400) == "curated_fallback"          # still curated, not "full market"


def test_counts_sum_to_universe_and_match_curated_buckets():
    counts = _universe_counts()
    total = sum(n for region in counts.values() for n in region.values())
    assert total == len(SETUP_UNIVERSE)
    # The two flagship equity boxes are 12-name curated watchlists today.
    assert counts["Swedish"]["equity"] == 12
    assert counts["International"]["equity"] == 12


def test_every_bucket_label_is_honestly_curated():
    counts = _universe_counts()
    for region, by_ac in counts.items():
        for ac, discovered in by_ac.items():
            label = _coverage_label_for(discovered)
            assert label in CURATED_ALLOWED, f"{region}/{ac} -> {label}"
            assert label not in WHOLE_MARKET_CLAIMS


# ── Discovery-report endpoint (network-free: registry is monkeypatched) ──

def _fake_discover(exch, **_kw):
    return {
        "exchange": exch, "source_provider": "eodhd",
        "coverage_label": "full_exchange_market", "discovered": 3, "cached": True,
        "symbols": [
            {"asset_class": "equity"}, {"asset_class": "equity"},
            {"asset_class": "etf"},
        ],
        "error": None,
    }


def test_universe_coverage_report(monkeypatch):
    import api.universe_registry as reg
    monkeypatch.setattr(reg, "discover_exchange", _fake_discover)
    from api.phase2_router import universe_coverage

    d = universe_coverage()
    assert d["status"] == "ok"
    assert d["curated_universe_total"] > 0
    for exch, region in (("ST", "Swedish"), ("US", "International")):
        e = d["exchanges"][exch]
        assert e["coverage_label"] == "full_exchange_market"
        assert e["discovered"] == 3
        assert e["by_asset_class"] == {"equity": 2, "etf": 1}
        assert e["region"] == region
        # Cross-reference to the curated scan is present so the UI can show "N of M".
        assert "equity" in e["curated_scanned"]
        assert isinstance(e["curated_scanned"]["equity"], int)
        assert isinstance(e["discovered"], int)
