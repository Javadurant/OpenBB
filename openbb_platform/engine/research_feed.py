"""
engine/research_feed.py
=======================
SANDBOXED, UNTRUSTED external research feed for the LLM Council (Firecrawl).

DECISION PROVENANCE (LLM Council, Gurpreet-led, May 26 2026):
  Advisors benefit from recent qualitative context (news/catalysts), but web
  text is hostile by default. This module treats every byte from Firecrawl as
  UNTRUSTED DATA and enforces a strict sandbox:

SECURITY RULES (non-negotiable):
  - EGRESS MINIMISATION: only PUBLIC inputs leave the box - the ticker and the
    company name. No account, portfolio, position, or PII data is ever sent.
  - INJECTION DEFENSE: returned text is sanitized - instruction-like lines are
    dropped (e.g. "ignore previous", "system prompt", "STANCE:", "api key"),
    control chars stripped, and a hard length cap applied.
  - LABELLING: the caller wraps the digest in an explicit UNTRUSTED banner so the
    Council never executes instructions found inside it.
  - DORMANT BY DEFAULT: inactive unless FIRECRAWL_API_KEY is set; kill-switch
    COUNCIL_RESEARCH=0. Never raises to the caller - any failure returns None.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Final, Optional

import httpx

logger = logging.getLogger("research_feed")

_FIRECRAWL_SEARCH_URL: Final = "https://api.firecrawl.dev/v1/search"
_MAX_RESULTS: Final = 3
_MAX_CHARS:   Final = 900        # hard cap on the returned research digest
_TIMEOUT_SEC: Final = 12.0

# Instruction / injection patterns neutralized in untrusted web text.
_INJECTION_PATTERNS: Final = re.compile(
    r"(?i)\b(ignore\s+(all|any|previous|prior)|disregard\s+(the\s+)?(above|previous)|"
    r"system\s+prompt|you\s+(are|must|should)\s+now|new\s+instructions?|act\s+as|"
    r"stance\s*:|verdict\s*:|confidence\s*:|jailbreak|developer\s+mode|"
    r"override|api[_\- ]?key|password|secret\s+key)\b"
)
_CTRL: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _key() -> Optional[str]:
    """Return the Firecrawl key, or None if absent/placeholder (dormant)."""
    k = (os.getenv("FIRECRAWL_API_KEY", "") or "").strip()
    if not k or k.upper().startswith("PASTE_") or k.upper().startswith("FC-REPLACE"):
        return None
    return k


def is_enabled() -> bool:
    """True only if a real key is present AND COUNCIL_RESEARCH is not disabled."""
    if os.getenv("COUNCIL_RESEARCH", "1").strip().lower() in ("0", "false", "no", ""):
        return False
    return _key() is not None


def _sanitize(text: str) -> str:
    """Neutralize injection-like lines and control chars in untrusted web text."""
    if not text:
        return ""
    text = _CTRL.sub(" ", text)
    safe: list[str] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if _INJECTION_PATTERNS.search(ln):
            continue  # drop instruction-like lines entirely
        safe.append(ln)
    return " ".join(safe)


async def fetch_research(symbol: str, name: Optional[str] = None) -> Optional[str]:
    """Return a short, sanitized, UNTRUSTED research digest for ``symbol``, or None.

    Only the public ticker and company name are sent to Firecrawl. Never raises.
    """
    if not is_enabled():
        return None
    key = _key()
    company = (name or symbol or "").strip()
    query = f"{company} {symbol} stock recent news catalysts analyst".strip()
    payload = {"query": query, "limit": _MAX_RESULTS}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as c:
            r = await c.post(_FIRECRAWL_SEARCH_URL, json=payload, headers=headers)
            if r.status_code != 200:
                logger.warning("firecrawl search HTTP %s", r.status_code)
                return None
            data = r.json()
    except Exception as exc:  # noqa: BLE001 - graceful: research is optional
        logger.warning("firecrawl search failed: %s", exc)
        return None

    items = data.get("data") or data.get("results") or []
    if not isinstance(items, list) or not items:
        return None
    snippets: list[str] = []
    for it in items[:_MAX_RESULTS]:
        if not isinstance(it, dict):
            continue
        title = _sanitize(str(it.get("title") or ""))[:120]
        desc = _sanitize(str(it.get("description") or it.get("snippet") or ""))[:200]
        piece = (title + " - " + desc).strip(" -")
        if piece:
            snippets.append(piece)
    if not snippets:
        return None
    return " | ".join(snippets)[:_MAX_CHARS]
