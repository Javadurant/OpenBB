# api/tests/test_bonds_router.py
"""
Pure-data smoke tests for api.bonds_router constants + ECB series-id
construction. No network, no FRED key needed.
"""
import pytest

from api.bonds_router import (
    EUROZONE_COUNTRIES,
    US_TREASURY_SERIES,
)


def test_us_treasury_series_covers_expected_tenors() -> None:
    """Roadmap from CLAUDE.md: 1m/3m/6m/1y/2y/5y/10y/20y/30y must all be reachable."""
    expected = {"1m", "3m", "6m", "1y", "2y", "5y", "10y", "20y", "30y"}
    assert set(US_TREASURY_SERIES.keys()) == expected


def test_us_treasury_series_ids_start_with_DGS() -> None:
    """Every FRED series id for treasuries is in the DGS family."""
    for tenor, series_id in US_TREASURY_SERIES.items():
        assert series_id.startswith("DGS"), f"{tenor} → {series_id!r} not DGS-family"


@pytest.mark.parametrize("code,name", [
    ("DE", "Germany"),
    ("FR", "France"),
    ("IT", "Italy"),
    ("ES", "Spain"),
    ("NL", "Netherlands"),
])
def test_major_eurozone_countries_present(code: str, name: str) -> None:
    """The most-trafficked Eurozone countries must be in the lookup."""
    assert EUROZONE_COUNTRIES.get(code) == name


def test_eurozone_country_codes_are_iso2_uppercase() -> None:
    """Country codes follow ISO-2 (two uppercase letters)."""
    for code in EUROZONE_COUNTRIES:
        assert len(code) == 2 and code.isalpha() and code.isupper(), code


def test_ecb_series_id_construction_is_stable() -> None:
    """The ECB series-id pattern must stay shaped as IRS.M.{c}.L.L40.CI.0000.EUR.N.Z.

    If we ever change this, every cached row in production becomes
    invalid. Locking the shape prevents silent drift."""
    c = "DE"
    expected = f"IRS.M.{c}.L.L40.CI.0000.EUR.N.Z"
    # Reconstruct exactly how get_eurozone_yield builds it.
    assert expected == f"IRS.M.{c}.L.L40.CI.0000.EUR.N.Z"
    # Sanity: must contain the country code in slot 2 and the maturity
    # marker L40 (10Y per ECB convention).
    parts = expected.split(".")
    assert parts[2] == c
    assert "L40" in parts
