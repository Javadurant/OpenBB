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
        "groq":      Provider("groq",      "https://api.groq.com/openai/v1",        "GROQ_API_KEY",      os.getenv("GROQ_MODEL",      "llama-3.3-70b-versatile")),
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

def council_capabilities(force: bool = False) -> dict:
    """Live capability probe for every Council LLM provider (booleans + HTTP
    reason only, key NEVER in output). One tiny 1-token completion per keyed
    provider, cached per process like fmp_capabilities/polygon_capabilities.

    This exists because provider_status()/available_providers() only check
    whether a key string is non-empty -- they never make a real call. A key
    can be present and still be revoked, malformed, or out of credits;
    'present' and 'working' are different facts. This function checks the
    second one, live."""
    global _COUNCIL_CAPS_CACHE
    if _COUNCIL_CAPS_CACHE and not force:
        return _COUNCIL_CAPS_CACHE
    import requests
    reg = _reg()
    out: dict = {}
    for name, p in reg.items():
        key = _key_for(p)
        if key is None:
            out[name] = {"key_present": False, "working": False, "reason": "no key"}
            continue
        try:
            r = requests.post(
                f"{p.base_url}/chat/completions",
                headers=_headers(key) if key else {"Content-Type": "application/json"},
                json={"model": p.default_model,
                      "messages": [{"role": "user", "content": "hi"}],
                      "max_tokens": 1, "temperature": 0},
                timeout=10,
            )
            if r.status_code == 200:
                out[name] = {"key_present": bool(key), "working": True, "reason": None}
            else:
                out[name] = {"key_present": bool(key), "working": False,
                              "reason": f"HTTP {r.status_code}"}
        except Exception as exc:  # noqa: BLE001 - never crash /api/ready
            out[name] = {"key_present": bool(key), "working": False,
                          "reason": type(exc).__name__}
    _COUNCIL_CAPS_CACHE = out
    return out


_COUNCIL_CAPS_CACHE: dict = {}
