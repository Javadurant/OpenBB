"""
ai_providers.py
===============
Unified multi-provider LLM client for SENTRIQ (LLM Council, May 24 2026).

Adds an OpenAI-compatible fallback chain across Groq, Fireworks, Together,
DeepInfra, SambaNova (cloud) and Ollama (local). Every provider here exposes
an OpenAI-style /chat/completions endpoint, so ONE code path serves them all.

Why: SENTRIQ's AI calls ran on Groq alone (single point of failure on the free
tier, single "voice" for the LLM Council). This layer gives resilience
(automatic failover) and enables a genuinely multi-model Council.

Keys live in OpenBB/openbb_platform/.env (absent/placeholder providers are
skipped silently): GROQ_API_KEY, FIREWORKS_API_KEY, TOGETHER_API_KEY,
DEEPINFRA_API_KEY, SAMBANOVA_API_KEY. Ollama is local and needs NO key
(OLLAMA_BASE_URL default http://localhost:11434/v1).

Order override: AI_PROVIDER_ORDER="groq,fireworks,together,deepinfra,sambanova,ollama"
Per-provider model override: <NAME>_MODEL (e.g. FIREWORKS_MODEL=...).

Design: lazy key reads (import-order safe), PASTE_ placeholders treated as
absent, no bare except, graceful degradation (a dead provider is skipped, never
crashes the chain). No float comparisons. requests (sync) + httpx (async) only.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Final, Optional

logger = logging.getLogger("ai_providers")


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    env_key: Optional[str]      # None => no key required (Ollama)
    default_model: str


def _reg() -> dict[str, Provider]:
    """Build the registry at call time so OLLAMA_BASE_URL / *_MODEL env overrides
    are always honoured regardless of import order."""
    return {
        "groq":      Provider("groq",      "https://api.groq.com/openai/v1",        "GROQ_API_KEY",      os.getenv("GROQ_MODEL",      "openai/gpt-oss-20b")),
        "fireworks": Provider("fireworks", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/gpt-oss-120b")),
        "together":  Provider("together",  "https://api.together.xyz/v1",           "TOGETHER_API_KEY",  os.getenv("TOGETHER_MODEL",  "meta-llama/Llama-3.3-70B-Instruct-Turbo")),
        "deepinfra": Provider("deepinfra", "https://api.deepinfra.com/v1/openai",   "DEEPINFRA_API_KEY", os.getenv("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct")),
        "sambanova": Provider("sambanova", "https://api.sambanova.ai/v1",           "SAMBANOVA_API_KEY", os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct")),
        "ollama_cloud": Provider("ollama_cloud", os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1"), "OLLAMA_API_KEY", os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b-cloud")),  # <- FIXED v3.7: cloud models require the -cloud suffix (per user Ollama docs 2026-07-21); gemma3:27b had no cloud tag -> 410. Bearer auth already handled by _headers().
        "ollama":    Provider("ollama",    os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), None, os.getenv("OLLAMA_MODEL", "llama3.2:3b")),
    }

_DEFAULT_ORDER: Final = ["groq", "sambanova", "fireworks", "ollama_cloud", "together", "deepinfra", "ollama"]
# <- NEW: curated multi-model Council pool — verified to return content at low/zero cost.
# Excludes no-credit providers (together/deepinfra) and the weak 3B local fallback (ollama).
# Override via env COUNCIL_PROVIDERS (comma-separated).
_COUNCIL_DEFAULT: Final = ["groq", "sambanova", "ollama_cloud"]
DEFAULT_TIMEOUT: Final = 45.0
DEFAULT_MAX_TOKENS: Final = 1024
DEFAULT_TEMPERATURE: Final = 0.2


def _key_for(p: Provider) -> Optional[str]:
    """Lazy key read. '' => keyless (Ollama). PASTE_ placeholders => treated absent."""
    if p.env_key is None:
        return ""
    v = os.getenv(p.env_key)
    if not v or v.startswith("PASTE_"):
        return None
    return v


def _order() -> list[str]:
    reg = _reg()
    raw = os.getenv("AI_PROVIDER_ORDER", "")
    names = [n.strip() for n in raw.split(",") if n.strip()] or _DEFAULT_ORDER
    return [n for n in names if n in reg]


def provider_names() -> list[str]:
    """All known provider names (registry keys)."""
    return list(_reg().keys())


def available_providers() -> list[str]:
    """Providers usable right now (key present, or keyless Ollama). No network probe."""
    reg = _reg()
    out: list[str] = []
    for name in _order():
        p = reg[name]
        if p.env_key is None or _key_for(p):
            out.append(name)
    return out


def provider_status() -> dict[str, Any]:
    reg = _reg()
    avail = available_providers()
    return {
        "available": avail,
        "count": len(avail),
        "order": _order(),
        "default": avail[0] if avail else None,
        "registry": {n: {"model": reg[n].default_model, "keyed": reg[n].env_key is not None,
                         "ready": (reg[n].env_key is None or bool(_key_for(reg[n])))}
                     for n in reg},
    }


def _headers(key: Optional[str]) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def chat(messages: list[dict], *, model: Optional[str] = None,
         temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS,
         provider: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """Synchronous chat completion with provider fallback. Returns text or None.
    `provider` pins one provider; `model` overrides that provider's default."""
    import requests
    reg = _reg()
    names = [provider] if provider else _order()
    last_err: Optional[str] = None
    for name in names:
        p = reg.get(name)
        if p is None:
            continue
        key = _key_for(p)
        if key is None:
            continue
        body = {"model": model or p.default_model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens, "stream": False}
        try:
            r = requests.post(f"{p.base_url}/chat/completions",
                              headers=_headers(key), json=body, timeout=timeout)
            if r.status_code != 200:
                last_err = f"{name}: HTTP {r.status_code} {r.text[:160]}"
                logger.warning("ai_providers %s", last_err)
                continue
            txt = (r.json().get("choices") or [{}])[0].get("message", {}).get("content")
            if txt:
                logger.info("ai_providers: %s answered (model=%s)", name, body["model"])
                return txt
            last_err = f"{name}: empty content"
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            last_err = f"{name}: {exc}"
            logger.warning("ai_providers %s failed: %s", name, exc)
            continue
    logger.error("ai_providers: all providers failed (%s)", last_err)
    return None


def complete(prompt: str, *, system: Optional[str] = None, **kw: Any) -> Optional[str]:
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return chat(msgs, **kw)


async def achat_stream(messages: list[dict], *, model: Optional[str] = None,
                       provider: Optional[str] = None, temperature: float = DEFAULT_TEMPERATURE,
                       max_tokens: int = DEFAULT_MAX_TOKENS,
                       timeout: float = DEFAULT_TIMEOUT) -> AsyncIterator[str]:
    """Async streaming completion (OpenAI SSE). Yields text deltas. Tries providers
    in order; first to connect wins (no mid-stream failover)."""
    import httpx
    reg = _reg()
    names = [provider] if provider else _order()
    for name in names:
        p = reg.get(name)
        if p is None:
            continue
        key = _key_for(p)
        if key is None:
            continue
        body = {"model": model or p.default_model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                async with c.stream("POST", f"{p.base_url}/chat/completions",
                                    headers=_headers(key), json=body) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        logger.warning("ai_providers stream %s HTTP %s", name, resp.status_code)
                        continue
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            return
                        try:
                            delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta:
                            yield delta
                    return
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ai_providers stream %s failed: %s", name, exc)
            continue
    logger.error("ai_providers: no streaming provider available")
    return


def council_model_assignments(
    n_advisors: int = 5,
    providers: list[str] | None = None,   # <- NEW: explicit allowlist (intersected with keyed providers)
) -> list[tuple[str, str]]:
    """Distribute advisors across providers for genuine multi-model deliberation.
    Returns [(provider, model), ...] of length n_advisors. One provider -> all share
    it (graceful); many -> round-robin.

    Provider selection precedence (so advisors never get a hard-failing provider):
      1. explicit ``providers`` arg
      2. ``COUNCIL_PROVIDERS`` env var (comma-separated)
      3. curated ``_COUNCIL_DEFAULT`` (verified low/zero-cost working providers)
    The chosen candidates are intersected with ``available_providers()`` (keyed,
    non-placeholder), dropping e.g. no-credit together/deepinfra if they were listed.
    """
    reg = _reg()
    avail = available_providers()
    if not avail:
        return []
    if providers:
        cand = providers
    else:
        raw = os.getenv("COUNCIL_PROVIDERS", "").strip()
        cand = [n.strip() for n in raw.split(",") if n.strip()] or list(_COUNCIL_DEFAULT)
    pool = [p for p in cand if p in avail] or avail   # <- NEW: never empty; fall back to all available
    return [(pool[i % len(pool)], reg[pool[i % len(pool)]].default_model)
            for i in range(n_advisors)]

# ── Council readiness: bounded TTL, explicit states, content-aware probe ───
# A cached probe result is a point-in-time observation, not a standing fact:
# keys get revoked, credits run out, models get retired and rate limits engage
# between probes. With no expiry the first observation after process start was
# served for the entire process lifetime, so /api/ready could keep asserting
# "working: true" for a provider that had been failing for days.
COUNCIL_CAPS_TTL_DEFAULT_SEC: Final = 900.0     # 15 minutes
COUNCIL_CAPS_TTL_MIN_SEC: Final = 60.0          # rate-safety floor
COUNCIL_CAPS_TTL_MAX_SEC: Final = 3600.0        # freshness ceiling

# Probe budget. max_tokens=1 was not a valid readiness test: a reasoning model
# spends its first tokens on reasoning, so it returns HTTP 200 with an EMPTY
# message content and the old probe scored that as success. 64 is the budget
# at which Groq was observed to return usable content.
COUNCIL_PROBE_MAX_TOKENS_DEFAULT: Final = 64
COUNCIL_PROBE_MAX_TOKENS_MIN: Final = 1
COUNCIL_PROBE_MAX_TOKENS_MAX: Final = 64

# Per-provider wall-clock ceiling.
COUNCIL_PROBE_TIMEOUT_SEC: Final = 3.0
COUNCIL_PROBE_TIMEOUT_MAX_SEC: Final = 3.0      # hard ceiling, not configurable up

# Hard cumulative ceiling for the COMPLETE round. /api/ready is a reliability
# endpoint: N providers x per-provider timeout is not an acceptable bound, so
# the round carries its own monotonic deadline and simply stops probing when
# the budget is gone. Providers never reached are reported UNKNOWN -- honestly
# unobserved, never assumed healthy.
COUNCIL_PROBE_ROUND_DEADLINE_SEC: Final = 9.0
COUNCIL_PROBE_ROUND_DEADLINE_MAX_SEC: Final = 9.0   # hard ceiling, may only be lowered

# `requests` applies a SCALAR timeout to the connect phase and the read phase
# INDEPENDENTLY, so a scalar cannot bound one provider's total wall clock -- a
# slow connect followed by a slow read can take ~2x. A (connect, read) tuple
# whose parts sum to the slice is what actually makes the deadline hard.
COUNCIL_PROBE_CONNECT_CAP_SEC: Final = 1.0

# Fixed neutral probe prompt. No production prompt, symbol, market data,
# ledger content, account information or personal data is ever sent here.
COUNCIL_PROBE_PROMPT: Final = "hi"
REASON_ROUND_EXHAUSTED: Final = "not probed: round budget exhausted"

# Readiness states. `working` stays in the payload as a plain boolean for
# backward compatibility; `state` carries the precise answer.
STATE_WORKING: Final = "WORKING"                # answered with usable content
STATE_RATE_LIMITED: Final = "RATE_LIMITED"      # provider throttled us (HTTP 429)
STATE_BROKEN: Final = "BROKEN"                  # answered, but not usably
STATE_UNKNOWN: Final = "UNKNOWN"                # no key, unobserved, or indeterminate
STATE_STALE: Final = "STALE"                    # cached observation past its TTL

_COUNCIL_CAPS_CACHE: dict = {}
_COUNCIL_CAPS_AT: float = 0.0                   # time.monotonic() of last probe


def _clamped_env_float(var: str, default: float, lo: float, hi: float) -> float:
    """Read a float from env and clamp it. Malformed or non-positive input
    falls back to the default rather than disabling a safety bound."""
    raw = os.getenv(var, "").strip()
    try:
        val = float(raw) if raw else default
    except ValueError:
        val = default
    if val <= 0:
        val = default
    return max(lo, min(hi, val))


def council_caps_ttl_sec() -> float:
    """TTL for the readiness cache, clamped to a safe band.

    COUNCIL_CAPS_TTL_SEC is clamped rather than trusted: too short spams the
    providers (rate-limit risk), too long recreates the unbounded-cache defect
    this replaces.
    """
    return _clamped_env_float("COUNCIL_CAPS_TTL_SEC", COUNCIL_CAPS_TTL_DEFAULT_SEC,
                              COUNCIL_CAPS_TTL_MIN_SEC, COUNCIL_CAPS_TTL_MAX_SEC)


def council_probe_timeout_sec() -> float:
    """Per-provider timeout. Env may lower it but never raise it above the
    hard ceiling -- readiness latency is a safety property, not a preference."""
    return _clamped_env_float("COUNCIL_PROBE_TIMEOUT_SEC", COUNCIL_PROBE_TIMEOUT_SEC,
                              0.0, COUNCIL_PROBE_TIMEOUT_MAX_SEC)


def council_probe_round_deadline_sec() -> float:
    """Hard cumulative ceiling for one complete round. Env may only lower it."""
    return _clamped_env_float("COUNCIL_PROBE_ROUND_DEADLINE_SEC",
                              COUNCIL_PROBE_ROUND_DEADLINE_SEC,
                              0.0, COUNCIL_PROBE_ROUND_DEADLINE_MAX_SEC)


def council_probe_max_tokens() -> int:
    """Probe token budget, clamped. Bounded on both sides: too small cannot
    prove usable output, too large turns readiness into real spend."""
    raw = os.getenv("COUNCIL_PROBE_MAX_TOKENS", "").strip()
    try:
        n = int(raw) if raw else COUNCIL_PROBE_MAX_TOKENS_DEFAULT
    except ValueError:
        n = COUNCIL_PROBE_MAX_TOKENS_DEFAULT
    return max(COUNCIL_PROBE_MAX_TOKENS_MIN,
               min(COUNCIL_PROBE_MAX_TOKENS_MAX, n))


def council_probe_round_bound_sec() -> float:
    """Worst-case wall clock for one complete round.

    Two ceilings apply and the tighter one wins: the per-provider timeout
    summed over the providers that actually reach the network, and the hard
    round deadline. Exposed so the bound is asserted in tests, not assumed.
    """
    reg = _reg()
    probed = sum(1 for p in reg.values() if _key_for(p) is not None)
    return min(probed * council_probe_timeout_sec(),
               council_probe_round_deadline_sec())


def _slice_timeout(remaining: float) -> tuple[float, float]:
    """Split the remaining round budget into a (connect, read) pair.

    The parts sum to at most the per-provider ceiling AND at most the budget
    left in the round, so no single provider can overrun the deadline.
    """
    total = min(council_probe_timeout_sec(), remaining)
    connect = min(COUNCIL_PROBE_CONNECT_CAP_SEC, total / 2.0)
    return (connect, total - connect)


def _probe_content(payload: Any) -> str:
    """Assistant text from an OpenAI-shaped response, or '' if absent.
    Never raises: a malformed body is simply 'no usable content'."""
    try:
        choices = payload.get("choices") or []
        message = (choices[0] or {}).get("message") or {}
        return (message.get("content") or "").strip()
    except (AttributeError, IndexError, TypeError):
        return ""


def _state_from_status(status: int) -> tuple[str, str]:
    """Map an HTTP status onto a readiness state.

    The reason is the status code alone -- never a response body or header,
    which can echo back the request, the credential or account information.
    """
    if status == 200:
        return STATE_WORKING, "HTTP 200"
    if status == 429:
        return STATE_RATE_LIMITED, "HTTP 429"
    if status == 404:
        # A retired or misnamed model answers 404 here. That is the exact
        # shape of the Groq model retirement, so it is called out explicitly
        # rather than left to the catch-all.
        return STATE_BROKEN, "HTTP 404"
    return STATE_BROKEN, f"HTTP {status}"


def _probe_council_providers() -> dict:
    """One bounded probe per provider, under a hard cumulative round deadline.

    Serial and deterministic: registry order is preserved and no thread, worker,
    scheduler or async subsystem is involved. Providers are isolated -- a
    failure in one never aborts the round and never alters another's verdict.
    Once the round budget is gone the remaining providers are reported UNKNOWN
    rather than probed, so the endpoint's latency is bounded by construction.
    """
    import requests
    reg = _reg()
    max_tokens = council_probe_max_tokens()
    deadline = time.monotonic() + council_probe_round_deadline_sec()
    out: dict = {}
    for name, p in reg.items():
        key = _key_for(p)
        if key is None:
            out[name] = {"key_present": False, "working": False,
                         "state": STATE_UNKNOWN, "reason": "no key"}
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Unobserved is not unhealthy, and it is certainly not healthy.
            out[name] = {"key_present": True, "working": False,
                         "state": STATE_UNKNOWN, "reason": REASON_ROUND_EXHAUSTED}
            continue
        try:
            r = requests.post(
                f"{p.base_url}/chat/completions",
                headers=_headers(key) if key else {"Content-Type": "application/json"},
                json={"model": p.default_model,
                      "messages": [{"role": "user", "content": COUNCIL_PROBE_PROMPT}],
                      "max_tokens": max_tokens, "temperature": 0},
                timeout=_slice_timeout(remaining),
            )
            state, reason = _state_from_status(r.status_code)
            if state == STATE_WORKING:
                # HTTP 200 alone is not readiness. A provider that accepts the
                # request and returns nothing usable cannot serve the Council,
                # so it is BROKEN, not WORKING.
                try:
                    body = r.json()
                except ValueError:
                    state, reason = STATE_BROKEN, "HTTP 200 (unparseable body)"
                else:
                    if not _probe_content(body):
                        state, reason = STATE_BROKEN, "HTTP 200 (empty content)"
        except requests.Timeout as exc:
            # Transport gave no verdict. Unknown is the safe reading: explicitly
            # not a success, and explicitly not proof of breakage.
            state, reason = STATE_UNKNOWN, type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - never crash /api/ready
            state, reason = STATE_UNKNOWN, type(exc).__name__
        out[name] = {"key_present": bool(key),
                     "working": state == STATE_WORKING,
                     "state": state, "reason": reason}
    return out


def _caps_view(caps: dict, age_sec: float, *, stale: bool) -> dict:
    """Copy the cache stamped with freshness.

    When the observation has expired no provider may keep asserting success:
    an expired "working" is not a weaker yes, it is an unknown.
    """
    view: dict = {}
    for name, entry in caps.items():
        e = dict(entry)
        e["age_sec"] = round(age_sec, 1)
        e["fresh"] = not stale
        if stale:
            e["state"] = STATE_STALE
            e["working"] = False
        view[name] = e
    return view


def council_capabilities(force: bool = False) -> dict:
    """Live capability probe for every Council LLM provider (booleans, states
    and HTTP status only -- the key NEVER appears in the output).

    This exists because provider_status()/available_providers() only check
    whether a key string is non-empty -- they never make a real call. A key can
    be present and still be revoked, malformed, retired or out of credits;
    'present' and 'working' are different facts. This function checks the
    second one, live, and requires usable content before calling it working.

    Results are cached for a bounded TTL (see council_caps_ttl_sec) rather than
    for the process lifetime, so at most one probe round per TTL reaches the
    network, and each round is capped by a hard cumulative deadline.
    force=True refreshes immediately.
    """
    global _COUNCIL_CAPS_CACHE, _COUNCIL_CAPS_AT
    age = time.monotonic() - _COUNCIL_CAPS_AT
    if _COUNCIL_CAPS_CACHE and not force and age < council_caps_ttl_sec():
        return _caps_view(_COUNCIL_CAPS_CACHE, age, stale=False)
    try:
        caps = _probe_council_providers()
    except Exception as exc:  # noqa: BLE001 - never crash /api/ready
        # The refresh itself could not run. Serving the previous answer as if
        # it were current would be a lie, so it degrades to STALE instead.
        logger.warning("ai_providers: council probe unavailable (%s)",
                       type(exc).__name__)
        return _caps_view(_COUNCIL_CAPS_CACHE, age, stale=True)
    _COUNCIL_CAPS_CACHE = caps
    _COUNCIL_CAPS_AT = time.monotonic()
    return _caps_view(caps, 0.0, stale=False)
