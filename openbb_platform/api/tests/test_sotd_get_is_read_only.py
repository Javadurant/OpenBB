"""EMERGENCY CONTAINMENT: the Setup-of-the-Day GET must never write the ledger.

Offline and deterministic. setup_ledger.log_setup is replaced by a spy that
RAISES if called, so any surviving write path fails loudly rather than silently
appending. The scan universe and the market-regime fetch are stubbed so the
cache-miss paths run without network access.

No test writes the live or eval ledger.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time as _t

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import api.phase2_router as pr                    # noqa: E402
import api.setup_ledger as sl                     # noqa: E402

LIVE = ROOT / "sentriq_ledger.jsonl"
EVAL = ROOT / "sentriq_ledger_v33_eval.jsonl"

# The EXACT top-level keys of _setup_of_the_day_impl's result dict, read from
# api/phase2_router.py lines 1401-1426. Not guessed - containment must not
# change the response schema by even one key.
_EXPECTED_KEYS = {
    "status",
    "as_of",
    "cached",
    "market_regime",
    "boxes",
    "structure_watch",
    "structure_watch_counts",
    "structure_watch_max_age_bars",
    "total_scored",
    "universe_source",
    "universe_total",
    "coverage_note",
}


def _sha(p: pathlib.Path):
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(pr.router)          # throwaway app: no startup hooks fire
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Snapshot/restore the scan cache so this file cannot leak state."""
    snapshot = dict(pr._SETUP_CACHE)
    pr._SETUP_CACHE.clear()
    pr._SETUP_CACHE.update({"key": None, "at": 0.0, "data": None})
    yield
    pr._SETUP_CACHE.clear()
    pr._SETUP_CACHE.update(snapshot)


@pytest.fixture(autouse=True)
def _log_setup_must_never_be_called(monkeypatch):
    """Any ledger write during a GET is an immediate, loud failure."""
    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("GET /api/discover/setup-of-the-day wrote the ledger")
    monkeypatch.setattr(sl, "log_setup", _boom)


@pytest.fixture
def offline_scan(monkeypatch):
    """Let a cache-miss scan complete with no network: empty universe + a static
    market regime. Everything else in the impl degrades honestly on failure."""
    monkeypatch.setattr(pr, "SETUP_UNIVERSE", [])
    monkeypatch.setattr(pr, "_market_regime_map",
                        lambda: {"Swedish": None, "International": None})


# ── 1. Cache hit ─────────────────────────────────────────────────────────────
def test_cache_hit_get_never_calls_log_setup(client):
    pr._SETUP_CACHE.update({"key": "setup_v3.9", "at": _t.time(),
                            "data": {"status": "ok", "boxes": {}}})
    r = client.get("/api/discover/setup-of-the-day")
    assert r.status_code == 200
    assert r.json().get("cached") is True


# ── 2. Cache miss ────────────────────────────────────────────────────────────
def test_cache_miss_get_never_calls_log_setup(client, offline_scan):
    r = client.get("/api/discover/setup-of-the-day")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ── 3. refresh=true ──────────────────────────────────────────────────────────
def test_refresh_true_get_never_calls_log_setup(client, offline_scan):
    """A primed cache is deliberately bypassed. NOTE: with an empty universe the
    impl's zero-scored guard (lines 1431-1437) returns the last good cached scan
    rather than an empty one - that path still runs THROUGH the former write
    site, so the spy remains the meaningful assertion here."""
    pr._SETUP_CACHE.update({"key": "setup_v3.9", "at": _t.time(),
                            "data": {"status": "ok", "boxes": {}}})
    r = client.get("/api/discover/setup-of-the-day?refresh=true")
    assert r.status_code == 200


# ── Structural backstop: the symbol is gone from the module entirely ─────────
def test_log_setup_symbol_absent_from_the_get_implementation():
    """Stronger than any single path: if the identifier does not exist in the
    GET implementation, no branch - reachable by test or not - can call it.

    Scoped to _setup_of_the_day_impl rather than the whole module because the
    AUTHORISED POST endpoint (setup_of_the_day_log) legitimately calls
    log_setup. The invariant under test is 'GET never writes', not 'the module
    never writes'."""
    import inspect
    get_impl_src = inspect.getsource(pr._setup_of_the_day_impl)
    assert "log_setup" not in get_impl_src


# ── 4. Response schema unchanged ─────────────────────────────────────────────
def test_response_schema_unchanged(client, offline_scan):
    body = client.get("/api/discover/setup-of-the-day").json()
    assert set(body) == _EXPECTED_KEYS, (
        f"schema drift - missing={sorted(_EXPECTED_KEYS - set(body))} "
        f"unexpected={sorted(set(body) - _EXPECTED_KEYS)}")


# ── 5. No ledger drift ───────────────────────────────────────────────────────
def test_no_ledger_drift_across_this_module(client, offline_scan):
    before = (_sha(LIVE), _sha(EVAL))
    client.get("/api/discover/setup-of-the-day")
    client.get("/api/discover/setup-of-the-day?refresh=true")
    assert (_sha(LIVE), _sha(EVAL)) == before
