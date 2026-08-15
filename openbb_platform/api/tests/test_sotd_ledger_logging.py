"""Authorised SOTD trust-ledger logging: POST gate, GET silence, secret hygiene.

TEST-ONLY, deterministic, offline.

SAFETY DESIGN:
  - setup_ledger.log_setup is ALWAYS stubbed. No test can write a real ledger.
  - The credential is a dummy string created inside the test process via
    monkeypatch.setenv. No real token is generated, read, or revealed, and the
    real .env is never read or modified.
  - The router is mounted on a throwaway FastAPI app so no startup hook fires.
  - Shared state (_SETUP_CACHE, _LEDGER_LOG_HITS, token env) is snapshotted and
    restored before AND after every test, so results are order-independent.
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

# Dummy credential — exists only in this process. NOT a real token.
DUMMY_TOKEN = "test-only-dummy-credential-not-a-real-secret"
HDR = "X-Sentriq-Ledger-Token"

# Exact top-level keys of the GET result dict (phase2_router lines 1401-1426).
_EXPECTED_GET_KEYS = {
    "status", "as_of", "cached", "market_regime", "boxes", "structure_watch",
    "structure_watch_counts", "structure_watch_max_age_bars", "total_scored",
    "universe_source", "universe_total", "coverage_note",
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
    """Starlette's TestClient defaults its ASGI peer to ("testclient", 50000),
    which the loopback gate correctly REFUSES. We present a genuine loopback
    peer so the harness matches a real local call. The production gate is left
    strict — 'testclient' is never added to _LOOPBACK_HOSTS."""
    app = FastAPI()
    app.include_router(pr.router)
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Reset every piece of shared state BEFORE and AFTER each test."""
    cache_snapshot = dict(pr._SETUP_CACHE)
    hits_snapshot = list(pr._LEDGER_LOG_HITS)

    def _reset():
        pr._SETUP_CACHE.clear()
        pr._SETUP_CACHE.update({"key": None, "at": 0.0, "data": None})
        pr._LEDGER_LOG_HITS.clear()

    monkeypatch.delenv(pr._LEDGER_LOG_TOKEN_ENV, raising=False)
    _reset()
    yield
    _reset()
    pr._SETUP_CACHE.clear()
    pr._SETUP_CACHE.update(cache_snapshot)
    pr._LEDGER_LOG_HITS[:] = hits_snapshot


@pytest.fixture(autouse=True)
def _never_write_a_real_ledger(monkeypatch):
    """Default: any log_setup call is a loud failure. Tests that expect logging
    override this with their own counting stub."""
    def _boom(*a, **k):  # pragma: no cover - must never run by default
        raise AssertionError("a real ledger write was attempted")
    monkeypatch.setattr(sl, "log_setup", _boom)


@pytest.fixture
def offline_scan(monkeypatch):
    """Cache-miss scan with no network: empty universe + static regime."""
    monkeypatch.setattr(pr, "SETUP_UNIVERSE", [])
    monkeypatch.setattr(pr, "_market_regime_map",
                        lambda: {"Swedish": None, "International": None})


@pytest.fixture
def token_configured(monkeypatch, tmp_path):
    """Configure the dummy credential and satisfy the .env mode gate by
    pointing the check at a 0600 temp file — the real .env is never touched."""
    monkeypatch.setenv(pr._LEDGER_LOG_TOKEN_ENV, DUMMY_TOKEN)
    monkeypatch.setattr(pr, "_env_file_mode_check", lambda: None)


def _scan_fixture():
    """A minimal scan payload with two loggable top setups."""
    return {
        "status": "ok",
        "cached": False,
        "boxes": {
            "Swedish": {"equity": {"top_setup": {"symbol": "TEST-A.ST", "grade": "B"}}},
            "International": {"equity": {"top_setup": {"symbol": "TEST-B", "grade": "C"}}},
        },
    }


# ── GET stays silent on every path ───────────────────────────────────────────
def test_get_cache_hit_is_read_only(client):
    pr._SETUP_CACHE.update({"key": "setup_v3.9", "at": _t.time(),
                            "data": {"status": "ok", "boxes": {}}})
    r = client.get("/api/discover/setup-of-the-day")
    assert r.status_code == 200 and r.json().get("cached") is True


def test_get_cache_miss_is_read_only(client, offline_scan):
    r = client.get("/api/discover/setup-of-the-day")
    assert r.status_code == 200 and r.json().get("status") == "ok"


def test_get_refresh_true_is_read_only(client, offline_scan):
    pr._SETUP_CACHE.update({"key": "setup_v3.9", "at": _t.time(),
                            "data": {"status": "ok", "boxes": {}}})
    assert client.get("/api/discover/setup-of-the-day?refresh=true").status_code == 200


def test_get_schema_unchanged_uncached(client, offline_scan):
    body = client.get("/api/discover/setup-of-the-day").json()
    assert set(body) == _EXPECTED_GET_KEYS, (
        f"schema drift - missing={sorted(_EXPECTED_GET_KEYS - set(body))} "
        f"unexpected={sorted(set(body) - _EXPECTED_GET_KEYS)}")


def test_get_schema_unchanged_cached(client, offline_scan):
    """Cached responses carry the same keys plus the cache markers only."""
    first = client.get("/api/discover/setup-of-the-day").json()
    second = client.get("/api/discover/setup-of-the-day").json()
    assert second.get("cached") is True
    assert set(second) - set(first) <= {"cache_age_sec"}


# ── POST fails closed ────────────────────────────────────────────────────────
def test_post_unconfigured_fails_closed(client):
    r = client.post("/api/discover/setup-of-the-day/log")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_NOT_CONFIGURED"


def test_post_missing_credential_rejected(client, token_configured):
    r = client.post("/api/discover/setup-of-the-day/log")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_FORBIDDEN"


def test_post_wrong_credential_rejected(client, token_configured):
    r = client.post("/api/discover/setup-of-the-day/log",
                    headers={HDR: "wrong-credential"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_FORBIDDEN"


def test_post_non_loopback_peer_denied(token_configured):
    """request.client absent or non-loopback => refuse. Unit-level, because
    TestClient always presents a loopback peer."""
    assert pr._ledger_logging_authorised(DUMMY_TOKEN, "203.0.113.9") == (False, "remote_denied")
    assert pr._ledger_logging_authorised(DUMMY_TOKEN, None) == (False, "remote_denied")


def test_post_ignores_forwarding_headers(client, token_configured):
    """A spoofed X-Forwarded-For must not influence the decision. The real peer
    is loopback here, so the request proceeds past the loopback gate on the
    peer's merit, never on the header's."""
    r = client.post("/api/discover/setup-of-the-day/log",
                    headers={HDR: "wrong", "X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_FORBIDDEN"


def test_env_permission_failure_fails_closed(client, monkeypatch):
    monkeypatch.setenv(pr._LEDGER_LOG_TOKEN_ENV, DUMMY_TOKEN)

    def _raise(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(pr._os, "stat", _raise)
    r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_ENV_CHECK_FAILED"
    body = r.text
    assert "PermissionError" not in body and "/Users" not in body and ".env" not in body


def test_insecure_env_mode_fails_closed(client, monkeypatch, tmp_path):
    monkeypatch.setenv(pr._LEDGER_LOG_TOKEN_ENV, DUMMY_TOKEN)
    monkeypatch.setattr(pr, "_env_file_mode_check", lambda: "insecure_env_permissions")
    r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LEDGER_LOGGING_INSECURE_ENV_PERMISSIONS"


# ── Rate limiting precedes credential validation ─────────────────────────────
def test_invalid_attempts_are_rate_limited_before_validation(client, token_configured):
    """7 rapid WRONG-token POSTs: the last must be 429, proving the counter runs
    before the credential check."""
    codes = [client.post("/api/discover/setup-of-the-day/log",
                         headers={HDR: "wrong"}).status_code for _ in range(7)]
    assert codes[-1] == 429
    assert codes.count(403) == pr._LEDGER_LOG_RATE_MAX


def test_rate_limit_is_order_independent(client, token_configured):
    """The autouse reset clears _LEDGER_LOG_HITS, so the limit is reachable
    again in a later test regardless of execution order."""
    codes = [client.post("/api/discover/setup-of-the-day/log",
                         headers={HDR: "wrong"}).status_code for _ in range(7)]
    assert codes[-1] == 429


# ── Authorised logging ───────────────────────────────────────────────────────
def test_authorised_post_invokes_stubbed_log_setup(client, monkeypatch, token_configured):
    calls = []
    monkeypatch.setattr(sl, "log_setup", lambda s, **k: (calls.append(s), True)[1])
    monkeypatch.setattr(pr, "_setup_of_the_day_impl", lambda refresh=False: _scan_fixture())

    r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})

    assert r.status_code == 200
    body = r.json()["ledger_logging"]
    assert body["candidates"] == 2 and body["written"] == 2
    assert body["not_written"] == 0 and body["logged"] is True
    assert body["idempotency_key"] == "date:symbol:grade"
    assert len(calls) == 2


def test_repeated_authorised_post_is_idempotent(client, monkeypatch, token_configured):
    """Second run: log_setup returns False for every already-present key."""
    monkeypatch.setattr(sl, "log_setup", lambda s, **k: False)
    monkeypatch.setattr(pr, "_setup_of_the_day_impl", lambda refresh=False: _scan_fixture())

    r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})

    assert r.status_code == 200
    body = r.json()["ledger_logging"]
    assert body["written"] == 0 and body["not_written"] == 2
    assert body["logged"] is False
    assert "not distinguishable" in body["not_written_note"]


def test_not_written_is_not_labelled_duplicate(client, monkeypatch, token_configured):
    """Governance requirement: never imply every False is a duplicate."""
    monkeypatch.setattr(sl, "log_setup", lambda s, **k: False)
    monkeypatch.setattr(pr, "_setup_of_the_day_impl", lambda refresh=False: _scan_fixture())
    body = client.post("/api/discover/setup-of-the-day/log",
                       headers={HDR: DUMMY_TOKEN}).json()["ledger_logging"]
    assert "duplicate" not in [k.lower() for k in body]
    assert body["identity_note"].startswith("shared credential")


# ── Secret hygiene ───────────────────────────────────────────────────────────
def test_token_never_appears_in_success_response_or_logs(client, monkeypatch,
                                                         token_configured, caplog):
    monkeypatch.setattr(sl, "log_setup", lambda s, **k: True)
    monkeypatch.setattr(pr, "_setup_of_the_day_impl", lambda refresh=False: _scan_fixture())
    with caplog.at_level("DEBUG"):
        r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})
    assert DUMMY_TOKEN not in r.text
    assert DUMMY_TOKEN not in str(dict(r.headers))
    assert DUMMY_TOKEN not in caplog.text


def test_token_never_appears_on_refusal(client, token_configured, caplog):
    with caplog.at_level("DEBUG"):
        r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN + "x"})
    assert r.status_code == 403
    assert DUMMY_TOKEN not in r.text and DUMMY_TOKEN not in caplog.text


# ── Error envelope shape ─────────────────────────────────────────────────────
def test_all_failures_use_the_shared_error_envelope(client, token_configured):
    r = client.post("/api/discover/setup-of-the-day/log", headers={HDR: "wrong"})
    body = r.json()
    assert body["ok"] is False
    assert set(body["error"]) == {"code", "message", "details", "retryable",
                                  "source", "timestamp", "request_id"}


def test_structured_error_delegation_preserves_503_contract():
    """_structured_error must still emit 503 + retryable=True after delegation."""
    resp = pr._structured_error("X_FAILED", ValueError("boom"), "unit", "rid123")
    assert resp.status_code == 503
    import json as _json
    body = _json.loads(resp.body)
    assert body["ok"] is False
    assert body["error"]["retryable"] is True
    assert body["error"]["details"] == "ValueError"
    assert body["error"]["request_id"] == "rid123"


# ── No ledger drift ──────────────────────────────────────────────────────────
def test_no_real_ledger_drift(client, monkeypatch, token_configured, offline_scan):
    before = (_sha(LIVE), _sha(EVAL))
    monkeypatch.setattr(sl, "log_setup", lambda s, **k: True)
    monkeypatch.setattr(pr, "_setup_of_the_day_impl", lambda refresh=False: _scan_fixture())
    client.get("/api/discover/setup-of-the-day")
    client.post("/api/discover/setup-of-the-day/log", headers={HDR: DUMMY_TOKEN})
    assert (_sha(LIVE), _sha(EVAL)) == before
