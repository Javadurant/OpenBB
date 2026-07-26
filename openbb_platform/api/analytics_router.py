"""
api/analytics_router.py
========================
Phase 3 Deliverable B (May 19, 2026) — Backend Amplitude proxy.

Receives events from src/lib/analytics.ts and forwards to Amplitude HTTP V2 API.
Keeps AMPLITUDE_API_KEY server-side so it never lands in browser bundles.

Endpoints:
    POST /api/analytics/event        — single event
    POST /api/analytics/event/batch  — batched events (offline queue replay)
    GET  /api/analytics/status       — diagnostic: configured? events sent today?

When AMPLITUDE_API_KEY is unset, requests are accepted but logged-only.
This means you can wire instrumentation into the UI now and turn on
Amplitude later by pasting the key into .env.
"""
from __future__ import annotations
import logging
import os
import time
from typing import Any, Final, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_AMPLITUDE_URL: Final = "https://api.amplitude.com/2/httpapi"
_EU_AMPLITUDE_URL: Final = "https://api.eu.amplitude.com/2/httpapi"

# Simple in-memory counter for diagnostic
_events_sent_today = 0
_events_failed_today = 0
_last_reset = time.time()


def _maybe_reset_counters() -> None:
    global _events_sent_today, _events_failed_today, _last_reset
    if time.time() - _last_reset > 86400:
        _events_sent_today = 0
        _events_failed_today = 0
        _last_reset = time.time()


class EventIn(BaseModel):
    event:      str = Field(..., min_length=1, max_length=80)
    properties: dict[str, Any] = Field(default_factory=dict)
    ts:         int   # ms since epoch
    user_id:    str = Field(..., min_length=1, max_length=50)


class BatchIn(BaseModel):
    events: list[EventIn]


def _amplitude_key() -> Optional[str]:
    return os.getenv("AMPLITUDE_API_KEY", "").strip() or None


def _use_eu() -> bool:
    """User's profile says Stockholm — likely EU data residency."""
    return os.getenv("AMPLITUDE_REGION", "eu").strip().lower() == "eu"


async def _forward_to_amplitude(events: list[dict[str, Any]]) -> bool:
    """Send events to Amplitude HTTP V2. Returns True on success."""
    key = _amplitude_key()
    if not key:
        logger.info("analytics: %d events received but AMPLITUDE_API_KEY unset (no-op)", len(events))
        return False

    payload = {
        "api_key": key,
        "events": [
            {
                "user_id":          e["user_id"],
                "event_type":       e["event"],
                "event_properties": e.get("properties", {}),
                "time":             e["ts"],
            }
            for e in events
        ],
    }

    url = _EU_AMPLITUDE_URL if _use_eu() else _AMPLITUDE_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.warning("analytics: amplitude forward failed: %s", e)
        return False


@router.post("/event")
async def track_event(evt: EventIn) -> dict[str, Any]:
    """Single-event tracker. Fire-and-forget from the browser."""
    global _events_sent_today, _events_failed_today
    _maybe_reset_counters()

    ok = await _forward_to_amplitude([evt.model_dump()])
    if ok:
        _events_sent_today += 1
    else:
        _events_failed_today += 1
    # Always 200 — analytics is best-effort, never blocks the UI
    return {"status": "ok", "forwarded": ok}


@router.post("/event/batch")
async def track_event_batch(batch: BatchIn) -> dict[str, Any]:
    """Batched event tracker for offline queue replay."""
    global _events_sent_today, _events_failed_today
    _maybe_reset_counters()

    if not batch.events:
        return {"status": "ok", "forwarded": False, "count": 0}

    # Cap at 100 per request to limit blast radius
    events = [e.model_dump() for e in batch.events[:100]]
    ok = await _forward_to_amplitude(events)
    if ok:
        _events_sent_today += len(events)
    else:
        _events_failed_today += len(events)
    return {"status": "ok", "forwarded": ok, "count": len(events)}


@router.get("/status")
async def analytics_status() -> dict[str, Any]:
    """Diagnostic — Amplitude configuration + today's counters."""
    _maybe_reset_counters()
    return {
        "status":              "ok",
        "amplitude_configured": _amplitude_key() is not None,
        "region":               "eu" if _use_eu() else "us",
        "events_sent_today":    _events_sent_today,
        "events_failed_today":  _events_failed_today,
    }
