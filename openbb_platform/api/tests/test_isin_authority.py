"""
Tests for the ISIN-authority bugfix (2026-05-11 council).

The bug:
    yfinance returns wrong ISINs for some Nordic-listed but foreign-issued
    securities. KAMBI.ST → yfinance reports `PLCTHQM00018` (Polish prefix)
    but the authoritative Nasdaq Nordic source returns `MT0000780107`
    (Kambi is incorporated in Malta).

The fix:
    omnisearch_router.symbology() now PREFERS the Nasdaq Nordic ISIN for
    any Nordic-suffix ticker (.ST/.CO/.IC), keeping yfinance's claim in
    a new `isin_yfinance` audit field. `isin_source` field indicates
    provenance: "nasdaq_nordic" | "yfinance".

These tests use the live FastAPI process — they exercise the full code
path end-to-end. Skipped cleanly if the API isn't running.
"""
import urllib.error
import urllib.request
import json
from pathlib import Path

import pytest

CACHE_PATH = Path("/tmp/sentriq_nasdaq_nordic.json")
API_BASE = "http://localhost:8000"


def _api_call(path: str) -> dict:
    """Try the live API. Skip the test if it's not reachable."""
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=5) as r:
            return json.load(r)
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        pytest.skip(f"FastAPI not reachable at {API_BASE}: {e}")


@pytest.fixture(autouse=True)
def _skip_if_no_cache():
    if not CACHE_PATH.exists():
        pytest.skip(f"Nasdaq Nordic cache missing at {CACHE_PATH}")


# ── KAMBI.ST authoritative ISIN ───────────────────────────────────────────
class TestKambiISINAuthority:
    def test_kambi_returns_maltese_isin_not_polish(self):
        """The exact bug. KAMBI returned PLCTHQM00018 before the fix."""
        d = _api_call("/api/omni/symbology/KAMBI.ST")
        assert d["isin"] == "MT0000780107", (
            f"Expected Maltese ISIN; got {d.get('isin')!r}"
        )

    def test_kambi_isin_source_marked_nasdaq_nordic(self):
        d = _api_call("/api/omni/symbology/KAMBI.ST")
        assert d.get("isin_source") == "nasdaq_nordic"

    def test_kambi_audit_trail_preserves_yfinance_claim(self):
        """The buggy ISIN must still surface in the audit field so we can
        compare. This proves the override is intentional, not silent.

        yfinance's wrong ISIN drifts over time (PLCTHQM00018, later
        PLCRTCH00017), so assert the audit-trail invariant instead of a
        pinned value: the field is present/non-empty and differs from the
        authoritative ISIN."""
        d = _api_call("/api/omni/symbology/KAMBI.ST")
        yf_claim = d.get("isin_yfinance")
        assert yf_claim, (
            f"Audit trail missing — got {yf_claim!r}"
        )
        assert yf_claim != d.get("isin"), (
            "Audit field should only be set when yfinance disagrees with "
            f"the authority; both are {yf_claim!r}"
        )


# ── Non-cross-listed Nordic tickers should agree with both sources ────────
class TestAgreementOnNativeSwedishIssuers:
    @pytest.mark.parametrize("sym,isin", [
        ("EVO.ST",     "SE0012673267"),
        ("VOLV-B.ST",  "SE0000115446"),
        ("ASSA-B.ST",  "SE0007100581"),
    ])
    def test_native_swedish_issuer_uses_se_isin(self, sym, isin):
        d = _api_call(f"/api/omni/symbology/{sym}")
        assert d["isin"] == isin
        assert d.get("isin_source") == "nasdaq_nordic"
        # No audit-trail-mismatch when both sources agree
        assert d.get("isin_yfinance") is None


# ── US tickers should never go through Nordic logic ───────────────────────
class TestUSTickersUseYFinance:
    def test_aapl_isin_source_is_yfinance(self):
        d = _api_call("/api/omni/symbology/AAPL")
        assert d.get("isin_source") == "yfinance"

    def test_aapl_isin_yfinance_is_none_for_audit(self):
        """If we didn't override, there's nothing to audit. Field is None."""
        d = _api_call("/api/omni/symbology/AAPL")
        assert d.get("isin_yfinance") is None
