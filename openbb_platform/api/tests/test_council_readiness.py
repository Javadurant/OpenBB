"""Council readiness: bounded-TTL cache + content-aware provider probing.

Entirely offline. Every provider response is mocked; no test in this module
opens a socket, reads the ledger, or touches SOTD scoring.

Two defects are pinned here:

  1. The capability cache had no expiry, so the first observation after process
     start was served for the whole process lifetime -- /api/ready kept saying
     "working: true" for providers that had been failing for days.
  2. The probe asked for max_tokens=1 and looked only at the HTTP status. A
     reasoning model spends its first tokens on reasoning and returns HTTP 200
     with EMPTY content, which the old probe scored as success.
  3. The round had no cumulative ceiling, so readiness latency grew with the
     provider count. /api/ready is a reliability endpoint and must not be held
     open by a slow provider set.
"""
from __future__ import annotations

import pathlib
import sys
import time
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import ai_providers as ap  # noqa: E402

SENTINEL_KEY = "SENTINEL-KEY-MUST-NEVER-APPEAR"


# ── helpers ────────────────────────────────────────────────────────────────
class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code: int, payload=None, *, unparseable: bool = False,
                 text: str = ""):
        self.status_code = status_code
        self.text = text            # chat() reads .text on non-200; keep the double faithful
        self._payload = payload
        self._unparseable = unparseable

    def json(self):
        if self._unparseable:
            raise ValueError("not json")
        return self._payload


def body(content):
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture(autouse=True)
def _reset_cache_and_env(monkeypatch):
    """Every test starts from a cold cache and a known single-provider registry."""
    monkeypatch.setattr(ap, "_COUNCIL_CAPS_CACHE", {}, raising=False)
    monkeypatch.setattr(ap, "_COUNCIL_CAPS_AT", 0.0, raising=False)
    for var in ("COUNCIL_CAPS_TTL_SEC", "COUNCIL_PROBE_MAX_TOKENS",
                "COUNCIL_PROBE_TIMEOUT_SEC", "COUNCIL_PROBE_ROUND_DEADLINE_SEC"):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def one_provider(monkeypatch):
    """Registry reduced to a single keyed provider, so assertions are exact."""
    only = {"groq": ap.Provider("groq", "https://example.invalid/v1",
                                "GROQ_API_KEY", "test-model")}
    monkeypatch.setattr(ap, "_reg", lambda: only)
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
    return only


def install_requests(monkeypatch, handler):
    """Replace the `requests` module the probe imports lazily."""
    import requests as real

    calls = {"n": 0, "kwargs": []}

    def post(url, **kwargs):
        calls["n"] += 1
        calls["kwargs"].append(kwargs)
        return handler(url, **kwargs)

    monkeypatch.setitem(sys.modules, "requests",
                        types.SimpleNamespace(post=post, Timeout=real.Timeout,
                                              RequestException=real.RequestException))
    return calls


# ── cache lifecycle ────────────────────────────────────────────────────────
def test_fresh_cache_is_reused_without_reprobing(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    first = ap.council_capabilities()
    second = ap.council_capabilities()
    assert calls["n"] == 1, "a fresh cache must not re-probe"
    assert first["groq"]["state"] == ap.STATE_WORKING
    assert second["groq"]["fresh"] is True


def test_ttl_expiry_triggers_a_single_reprobe(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    ap.council_capabilities()
    ap._COUNCIL_CAPS_AT -= ap.council_caps_ttl_sec() + 1.0   # age past the TTL
    ap.council_capabilities()
    assert calls["n"] == 2


def test_expired_cache_degrades_to_stale_and_never_claims_working(monkeypatch, one_provider):
    """If the refresh cannot run, the old answer must not be served as current."""
    install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    fresh = ap.council_capabilities()
    assert fresh["groq"]["working"] is True

    def boom():
        raise RuntimeError("probe unavailable")

    monkeypatch.setattr(ap, "_probe_council_providers", boom)
    ap._COUNCIL_CAPS_AT -= ap.council_caps_ttl_sec() + 1.0
    stale = ap.council_capabilities()
    assert stale["groq"]["state"] == ap.STATE_STALE
    assert stale["groq"]["working"] is False
    assert stale["groq"]["fresh"] is False


def test_force_refresh_bypasses_a_fresh_cache(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    ap.council_capabilities()
    ap.council_capabilities(force=True)
    assert calls["n"] == 2


def test_request_count_is_bounded_across_many_reads(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    for _ in range(50):
        ap.council_capabilities()
    assert calls["n"] == 1, "readiness must not probe on every request"


def test_age_sec_is_monotonic_and_non_negative(monkeypatch, one_provider):
    install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    ap.council_capabilities()
    ap._COUNCIL_CAPS_AT -= 5.0
    assert ap.council_capabilities()["groq"]["age_sec"] >= 5.0


# ── configuration clamps ───────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    (None, 900.0), ("5", 60.0), ("999999", 3600.0), ("abc", 900.0), ("", 900.0),
])
def test_ttl_is_clamped_against_unsafe_configuration(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("COUNCIL_CAPS_TTL_SEC", raising=False)
    else:
        monkeypatch.setenv("COUNCIL_CAPS_TTL_SEC", raw)
    assert ap.council_caps_ttl_sec() == expected


@pytest.mark.parametrize("raw,expected", [
    (None, 64), ("0", 1), ("9999", 64), ("xy", 64),
])
def test_probe_budget_is_clamped(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("COUNCIL_PROBE_MAX_TOKENS", raising=False)
    else:
        monkeypatch.setenv("COUNCIL_PROBE_MAX_TOKENS", raw)
    assert ap.council_probe_max_tokens() == expected


@pytest.mark.parametrize("raw,expected", [
    (None, 3.0), ("1.5", 1.5), ("60", 3.0), ("-1", 3.0), ("abc", 3.0),
])
def test_probe_timeout_never_exceeds_the_hard_ceiling(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("COUNCIL_PROBE_TIMEOUT_SEC", raising=False)
    else:
        monkeypatch.setenv("COUNCIL_PROBE_TIMEOUT_SEC", raw)
    assert ap.council_probe_timeout_sec() == expected


# ── latency: per-provider ceiling and hard cumulative round deadline ───────
def many_providers(monkeypatch, n):
    """n keyed providers, deterministic registry order p0..p{n-1}."""
    reg = {}
    for i in range(n):
        reg[f"p{i}"] = ap.Provider(f"p{i}", f"https://p{i}.invalid/v1", f"P{i}_KEY", "m")
        monkeypatch.setenv(f"P{i}_KEY", SENTINEL_KEY)
    monkeypatch.setattr(ap, "_reg", lambda: reg)
    return reg


def sleep_then_timeout(monkeypatch):
    """Every provider consumes its whole allotted slice, then times out."""
    import requests as real

    def slow(url, **kwargs):
        connect, read = kwargs["timeout"]
        time.sleep(connect + read)
        raise real.Timeout("ReadTimeout")

    return install_requests(monkeypatch, slow)


@pytest.mark.parametrize("raw,expected", [
    (None, 9.0), ("2", 2.0), ("60", 9.0), ("-1", 9.0), ("abc", 9.0), ("", 9.0),
])
def test_round_deadline_can_be_lowered_but_never_raised(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", raising=False)
    else:
        monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", raw)
    assert ap.council_probe_round_deadline_sec() == expected


def test_declared_bound_is_the_tighter_of_the_two_ceilings(monkeypatch):
    many_providers(monkeypatch, 2)
    assert ap.council_probe_round_bound_sec() == 2 * 3.0     # per-provider wins
    many_providers(monkeypatch, 7)
    assert ap.council_probe_round_bound_sec() == 9.0         # round deadline wins


def test_unkeyed_providers_cost_no_wall_clock(monkeypatch):
    """A provider with no key is resolved without a request, so it cannot
    contribute to the round's latency bound."""
    monkeypatch.setattr(ap, "_reg", lambda: {
        "groq": ap.Provider("groq", "https://example.invalid/v1", "GROQ_API_KEY", "m"),
        "nokey": ap.Provider("nokey", "https://example.invalid/v1", "ABSENT_KEY", "m"),
    })
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
    monkeypatch.delenv("ABSENT_KEY", raising=False)
    assert ap.council_probe_round_bound_sec() == 1 * 3.0


def test_slice_never_exceeds_the_per_provider_ceiling_or_the_remaining_budget():
    """The (connect, read) pair exists because requests applies a SCALAR
    timeout to each phase independently -- a scalar cannot bound one
    provider's total wall clock, a summed pair can."""
    for remaining in (0.4, 1.0, 2.5, 3.0, 8.9, 100.0):
        connect, read = ap._slice_timeout(remaining)
        assert connect >= 0 and read >= 0
        assert connect + read == pytest.approx(min(3.0, remaining))
        assert connect <= ap.COUNCIL_PROBE_CONNECT_CAP_SEC


def test_remaining_budget_shrinks_monotonically_across_providers(monkeypatch):
    """Each provider must be handed a slice no larger than what is left."""
    many_providers(monkeypatch, 4)
    monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", "1.0")
    calls = sleep_then_timeout(monkeypatch)
    ap.council_capabilities()
    totals = [c["timeout"][0] + c["timeout"][1] for c in calls["kwargs"]]
    assert totals == sorted(totals, reverse=True), "slices must not grow"
    assert sum(totals) <= 1.0 + 1e-6


def test_providers_past_the_deadline_are_unknown_not_probed(monkeypatch):
    many_providers(monkeypatch, 5)
    monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", "1.0")
    calls = sleep_then_timeout(monkeypatch)
    caps = ap.council_capabilities()
    exhausted = [n for n, e in caps.items() if e["reason"] == ap.REASON_ROUND_EXHAUSTED]
    assert exhausted, "the budget must actually run out with 5 hanging providers"
    assert calls["n"] == 5 - len(exhausted), "skipped providers must send no request"
    for name in exhausted:
        assert caps[name]["state"] == ap.STATE_UNKNOWN
        assert caps[name]["working"] is False
        assert caps[name]["key_present"] is True


def test_hard_round_deadline_is_enforced_mechanically(monkeypatch):
    """The whole round must finish inside the deadline no matter how many
    providers hang. This is the proof, not the declaration."""
    many_providers(monkeypatch, 8)
    monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", "1.0")
    sleep_then_timeout(monkeypatch)
    started = time.monotonic()
    caps = ap.council_capabilities()
    elapsed = time.monotonic() - started
    assert elapsed <= 1.0 + 0.5, f"round overran its deadline: {elapsed:.2f}s"
    assert len(caps) == 8, "every provider must still be reported"
    assert not any(e["working"] for e in caps.values())


def test_deadline_exhaustion_never_manufactures_a_working_provider(monkeypatch):
    many_providers(monkeypatch, 6)
    monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", "1.0")
    sleep_then_timeout(monkeypatch)
    caps = ap.council_capabilities()
    assert all(e["state"] == ap.STATE_UNKNOWN for e in caps.values())
    assert not any(e["working"] for e in caps.values())


def test_deterministic_serial_order_is_preserved_under_the_deadline(monkeypatch):
    many_providers(monkeypatch, 5)
    monkeypatch.setenv("COUNCIL_PROBE_ROUND_DEADLINE_SEC", "1.0")
    sleep_then_timeout(monkeypatch)
    first = list(ap.council_capabilities().keys())
    ap._COUNCIL_CAPS_AT = 0.0
    ap._COUNCIL_CAPS_CACHE = {}
    second = list(ap.council_capabilities().keys())
    assert first == second == [f"p{i}" for i in range(5)]


def test_a_fast_round_is_not_truncated(monkeypatch):
    """The deadline must only bite when providers are actually slow."""
    many_providers(monkeypatch, 7)
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    caps = ap.council_capabilities()
    assert calls["n"] == 7, "healthy providers must all be probed"
    assert all(e["state"] == ap.STATE_WORKING for e in caps.values())


def test_readiness_adds_no_thread_scheduler_or_async_subsystem():
    source = pathlib.Path(ap.__file__).read_text()
    for forbidden in ("import threading", "concurrent.futures", "ThreadPool",
                      "asyncio.create_task", "sched.scheduler", "multiprocessing"):
        assert forbidden not in source


# ── content-aware classification ───────────────────────────────────────────
@pytest.mark.parametrize("resp,state,working", [
    (FakeResponse(200, body("hello")),                 "WORKING",      True),
    (FakeResponse(200, body("")),                      "BROKEN",       False),
    (FakeResponse(200, body("   ")),                   "BROKEN",       False),
    (FakeResponse(200, body(None)),                    "BROKEN",       False),
    (FakeResponse(200, {"choices": []}),               "BROKEN",       False),
    (FakeResponse(200, {}),                            "BROKEN",       False),
    (FakeResponse(200, None, unparseable=True),        "BROKEN",       False),
    (FakeResponse(404, {}),                            "BROKEN",       False),
    (FakeResponse(429, {}),                            "RATE_LIMITED", False),
    (FakeResponse(401, {}),                            "BROKEN",       False),
    (FakeResponse(402, {}),                            "BROKEN",       False),
    (FakeResponse(500, {}),                            "BROKEN",       False),
])
def test_provider_state_classification(monkeypatch, one_provider, resp, state, working):
    install_requests(monkeypatch, lambda u, **k: resp)
    entry = ap.council_capabilities()["groq"]
    assert entry["state"] == state
    assert entry["working"] is working


def test_timeout_is_unknown_not_broken(monkeypatch, one_provider):
    import requests as real

    def timeout(url, **kwargs):
        raise real.Timeout("ReadTimeout")

    install_requests(monkeypatch, timeout)
    entry = ap.council_capabilities()["groq"]
    assert entry["state"] == ap.STATE_UNKNOWN
    assert entry["working"] is False


def test_transport_error_is_unknown(monkeypatch, one_provider):
    import requests as real

    def die(url, **kwargs):
        raise real.RequestException("connection reset")

    install_requests(monkeypatch, die)
    assert ap.council_capabilities()["groq"]["state"] == ap.STATE_UNKNOWN


def test_missing_key_is_unknown_not_broken(monkeypatch):
    monkeypatch.setattr(ap, "_reg", lambda: {
        "groq": ap.Provider("groq", "https://example.invalid/v1", "GROQ_API_KEY", "m")})
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    entry = ap.council_capabilities()["groq"]
    assert entry["state"] == ap.STATE_UNKNOWN
    assert entry["key_present"] is False
    assert entry["reason"] == "no key"


# ── isolation, failure, secrecy ────────────────────────────────────────────
def test_provider_states_are_isolated(monkeypatch):
    monkeypatch.setattr(ap, "_reg", lambda: {
        "good": ap.Provider("good", "https://good.invalid/v1", "GOOD_KEY", "m"),
        "bad":  ap.Provider("bad",  "https://bad.invalid/v1",  "BAD_KEY",  "m"),
        "slow": ap.Provider("slow", "https://slow.invalid/v1", "SLOW_KEY", "m"),
    })
    for var in ("GOOD_KEY", "BAD_KEY", "SLOW_KEY"):
        monkeypatch.setenv(var, SENTINEL_KEY)
    import requests as real

    def handler(url, **kwargs):
        if "good" in url:
            return FakeResponse(200, body("ok"))
        if "bad" in url:
            return FakeResponse(429, {})
        raise real.Timeout("ReadTimeout")

    install_requests(monkeypatch, handler)
    caps = ap.council_capabilities()
    assert caps["good"]["state"] == ap.STATE_WORKING
    assert caps["bad"]["state"] == ap.STATE_RATE_LIMITED
    assert caps["slow"]["state"] == ap.STATE_UNKNOWN


def test_total_provider_failure_yields_no_working_provider(monkeypatch):
    monkeypatch.setattr(ap, "_reg", lambda: {
        "a": ap.Provider("a", "https://a.invalid/v1", "A_KEY", "m"),
        "b": ap.Provider("b", "https://b.invalid/v1", "B_KEY", "m"),
    })
    monkeypatch.setenv("A_KEY", SENTINEL_KEY)
    monkeypatch.setenv("B_KEY", SENTINEL_KEY)
    install_requests(monkeypatch, lambda u, **k: FakeResponse(500, {}))
    caps = ap.council_capabilities()
    assert not any(e["working"] for e in caps.values())
    assert all(e["state"] == ap.STATE_BROKEN for e in caps.values())


def test_total_provider_failure_returns_none_not_fabricated_analysis(monkeypatch):
    """The chat path must degrade to None -- never invent an answer."""
    monkeypatch.setattr(ap, "_reg", lambda: {
        "a": ap.Provider("a", "https://a.invalid/v1", "A_KEY", "m")})
    monkeypatch.setenv("A_KEY", SENTINEL_KEY)
    install_requests(monkeypatch, lambda u, **k: FakeResponse(500, {}))
    assert ap.chat([{"role": "user", "content": "x"}]) is None


def test_readiness_payload_never_discloses_the_key(monkeypatch, one_provider):
    install_requests(monkeypatch, lambda u, **k: FakeResponse(401, {}))
    rendered = repr(ap.council_capabilities())
    assert SENTINEL_KEY not in rendered
    assert "Bearer" not in rendered
    assert "Authorization" not in rendered


def test_reason_never_carries_a_response_body(monkeypatch, one_provider):
    leak = "account_id=ACC-123 secret=" + SENTINEL_KEY
    install_requests(monkeypatch, lambda u, **k: FakeResponse(403, {"error": leak}))
    entry = ap.council_capabilities()["groq"]
    assert entry["reason"] == "HTTP 403"
    assert SENTINEL_KEY not in repr(entry)


# ── probe request shape ────────────────────────────────────────────────────
def test_probe_sends_a_fixed_neutral_prompt_and_bounded_budget(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    ap.council_capabilities()
    sent = calls["kwargs"][0]
    assert sent["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["json"]["max_tokens"] == 64
    assert sent["json"]["temperature"] == 0
    connect, read = sent["timeout"]
    assert connect + read == pytest.approx(3.0)


def test_probe_carries_no_trading_or_personal_data(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(200, body("ok")))
    ap.council_capabilities()
    payload = repr(calls["kwargs"][0]["json"])
    for forbidden in ("INVE", ".ST", "ledger", "setup", "target_price", "portfolio"):
        assert forbidden not in payload


def test_probe_does_not_retry(monkeypatch, one_provider):
    calls = install_requests(monkeypatch, lambda u, **k: FakeResponse(500, {}))
    ap.council_capabilities()
    assert calls["n"] == 1, "a failing provider must be probed exactly once"


# ── invariants the correction must not disturb ─────────────────────────────
def test_provider_order_and_fallback_are_unchanged():
    assert ap._DEFAULT_ORDER == ["groq", "sambanova", "fireworks",
                                 "ollama_cloud", "together", "deepinfra", "ollama"]
    assert ap._COUNCIL_DEFAULT == ["groq", "sambanova", "ollama_cloud"]


def test_registry_endpoints_and_key_names_are_unchanged():
    reg = ap._reg()
    assert reg["groq"].base_url == "https://api.groq.com/openai/v1"
    assert reg["groq"].env_key == "GROQ_API_KEY"
    assert reg["fireworks"].base_url == "https://api.fireworks.ai/inference/v1"
    assert reg["fireworks"].env_key == "FIREWORKS_API_KEY"


def test_chat_falls_back_to_the_next_provider_in_order(monkeypatch):
    monkeypatch.setattr(ap, "_reg", lambda: {
        "groq": ap.Provider("groq", "https://groq.invalid/v1", "GROQ_API_KEY", "m"),
        "fireworks": ap.Provider("fireworks", "https://fw.invalid/v1",
                                 "FIREWORKS_API_KEY", "m")})
    monkeypatch.setattr(ap, "_order", lambda: ["groq", "fireworks"])
    monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("FIREWORKS_API_KEY", SENTINEL_KEY)
    install_requests(monkeypatch, lambda u, **k:
                     FakeResponse(500, {}) if "groq" in u else FakeResponse(200, body("fw")))
    assert ap.chat([{"role": "user", "content": "x"}]) == "fw"


def test_readiness_module_imports_no_ledger_or_scoring_module():
    """Readiness must stay clear of deterministic trading state."""
    source = pathlib.Path(ap.__file__).read_text()
    for forbidden in ("setup_ledger", "setup_scanner", "phase2_router",
                      "symbol_backtest", "sentriq_ledger"):
        assert forbidden not in source
