"""api/apify_client.py — Apify Actor platform capability probe.

Auth confirmed 2026-07-19 via docs.apify.com: Bearer token,
GET /v2/users/me is the canonical lightweight auth-check endpoint (returns
account info, costs nothing, no Actor run triggered). Key is read at call
time and never logged, returned, or included in any exception text.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("apify")

_CAPS_CACHE: dict = {}
_RUN_SYNC_TIMEOUT_S = 120  # actor cold starts are slow; sync endpoint blocks
_MAX_DATASET_ITEMS = 25


def apify_key_present() -> bool:
    return bool(os.getenv("APIFY_API_TOKEN", "").strip())


def apify_capabilities(force: bool = False) -> dict:
    """Probe GET /v2/users/me to confirm the token authenticates.
    Booleans + HTTP reason only, never the token."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        _CAPS_CACHE = {"apify_key_present": False, "apify_working": False,
                       "apify_reason": "APIFY_API_TOKEN not set"}
        return _CAPS_CACHE
    try:
        req = urllib.request.Request(
            "https://api.apify.com/v2/users/me",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _CAPS_CACHE = {"apify_key_present": True, "apify_working": bool(data.get("data")),
                       "apify_reason": None}
    except urllib.error.HTTPError as e:
        _CAPS_CACHE = {"apify_key_present": True, "apify_working": False,
                       "apify_reason": f"HTTP {e.code}"}
    except Exception as exc:  # noqa: BLE001
        _CAPS_CACHE = {"apify_key_present": True, "apify_working": False,
                       "apify_reason": type(exc).__name__}
    return _CAPS_CACHE


# ── v3.7: generic synchronous actor runner (research-pipeline plumbing) ────
# ACTOR SELECTION IS A HUMAN DECISION. This module deliberately ships NO
# default actor id — which Apify actor to run (and against which targets) is
# a product/spend decision, not something the code invents. Once an actor is
# chosen, callers pass its exact id ("username~actor-name") and input.

def apify_run_actor(actor_id: str, run_input: Optional[dict] = None,
                    timeout_s: int = _RUN_SYNC_TIMEOUT_S) -> Optional[list]:
    """Run an actor synchronously and return its dataset items (capped at
    _MAX_DATASET_ITEMS), or None on ANY failure. Uses the canonical
    POST /v2/acts/{actor_id}/run-sync-get-dataset-items endpoint.
    Consumes real Apify compute credits. Token never logged — failures
    reduce to HTTP code / exception class name."""
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token or not actor_id:
        return None
    try:
        body = json.dumps(run_input or {}).encode()
        req = urllib.request.Request(
            f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
            data=body, method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list):
            return data[:_MAX_DATASET_ITEMS]
        return None
    except urllib.error.HTTPError as e:
        logger.debug("apify run %s failed: HTTP %s", actor_id, e.code)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("apify run %s failed: %s", actor_id, type(exc).__name__)
        return None
