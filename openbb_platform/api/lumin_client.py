"""api/lumin_client.py — Lumin PDF/eSign capability probe.

Auth confirmed 2026-07-21 from user-supplied Lumin docs: X-API-KEY header,
GET https://api.luminpdf.com/v1/user/info is the canonical lightweight
auth check. Key read at call time, never logged/returned/in exceptions.

NOTE ON RELEVANCE: Lumin is an e-signature / PDF document API. It has no
market-data or trading-news capability. It's probed here only so /api/ready
reports the truth about the key; it does NOT feed any trading surface.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_CAPS_CACHE: dict = {}


def lumin_key_present() -> bool:
    return bool(os.getenv("LUMIN_API_KEY", "").strip())


def lumin_capabilities(force: bool = False) -> dict:
    """Probe GET /v1/user/info with X-API-KEY. Booleans + HTTP reason only."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    key = os.getenv("LUMIN_API_KEY", "").strip()
    if not key:
        _CAPS_CACHE = {"lumin_key_present": False, "lumin_working": False,
                       "lumin_reason": "LUMIN_API_KEY not set"}
        return _CAPS_CACHE
    try:
        req = urllib.request.Request(
            "https://api.luminpdf.com/v1/user/info",
            headers={"X-API-KEY": key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            json.loads(resp.read().decode("utf-8"))
        _CAPS_CACHE = {"lumin_key_present": True, "lumin_working": True,
                       "lumin_reason": None}
    except urllib.error.HTTPError as e:
        _CAPS_CACHE = {"lumin_key_present": True, "lumin_working": False,
                       "lumin_reason": f"HTTP {e.code}"}
    except Exception as exc:  # noqa: BLE001
        _CAPS_CACHE = {"lumin_key_present": True, "lumin_working": False,
                       "lumin_reason": type(exc).__name__}
    return _CAPS_CACHE
