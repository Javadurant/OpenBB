"""api/firecrawl_client.py — Council research feed capability probe.

Firecrawl feeds the sandboxed, UNTRUSTED Council research context (see
FIRECRAWL_API_KEY comment in .env: "dormant until set, kill-switch
COUNCIL_RESEARCH=0"). This module only answers "does the key work" for
/api/ready -- it does not implement the research-feed fetch itself.

Auth confirmed 2026-07-19 via api.firecrawl.dev docs: Bearer token,
POST /v2/scrape. Key is read at call time and never logged, returned, or
included in any exception text.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_CAPS_CACHE: dict = {}


def firecrawl_key_present() -> bool:
    return bool(os.getenv("FIRECRAWL_API_KEY", "").strip())


def firecrawl_capabilities(force: bool = False) -> dict:
    """Probe one cheap, reliable scrape (example.com) to confirm the key
    actually authenticates. Booleans + HTTP reason only, never the key."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not key:
        _CAPS_CACHE = {"firecrawl_key_present": False, "firecrawl_working": False,
                       "firecrawl_reason": "FIRECRAWL_API_KEY not set"}
        return _CAPS_CACHE
    try:
        body = json.dumps({"url": "https://example.com", "formats": ["markdown"]}).encode()
        req = urllib.request.Request(
            "https://api.firecrawl.dev/v2/scrape", data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            json.loads(resp.read().decode("utf-8"))
        _CAPS_CACHE = {"firecrawl_key_present": True, "firecrawl_working": True,
                       "firecrawl_reason": None}
    except urllib.error.HTTPError as e:
        _CAPS_CACHE = {"firecrawl_key_present": True, "firecrawl_working": False,
                       "firecrawl_reason": f"HTTP {e.code}"}
    except Exception as exc:  # noqa: BLE001
        _CAPS_CACHE = {"firecrawl_key_present": True, "firecrawl_working": False,
                       "firecrawl_reason": type(exc).__name__}
    return _CAPS_CACHE
