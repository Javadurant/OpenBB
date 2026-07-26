"""api/coindesk_client.py — CoinDesk digital-asset data capability probe.

IMPORTANT PROTOCOL FACT (from user-supplied CoinDesk docs, 2026-07-21):
the documented CoinDesk data streamer is WEBSOCKET-ONLY, not REST:
  wss://data-streamer.coindesk.com/?api_key={KEY}
On connect the server sends a Session Welcome frame:
  TYPE 4000  -> connection authenticated OK  (key valid)
  TYPE 4011  -> Authentication Warning: invalid key, fell back to IP limits
So a valid-key probe = connect, read first frame, check TYPE.

Key read at call time, passed only over wss (encrypted), never logged or
returned. Uses websocket-client (confirmed installed) with a hard timeout
so a hang can never stall /api/ready.
"""
from __future__ import annotations

import json
import os

_CAPS_CACHE: dict = {}


def coindesk_key_present() -> bool:
    return bool(os.getenv("COINDESK_API_KEY", "").strip())


def coindesk_capabilities(force: bool = False) -> dict:
    """Open a short-lived WS, read the welcome frame, classify by TYPE.
    Booleans + reason only, never the key."""
    global _CAPS_CACHE
    if _CAPS_CACHE and not force:
        return _CAPS_CACHE
    key = os.getenv("COINDESK_API_KEY", "").strip()
    if not key:
        _CAPS_CACHE = {"coindesk_key_present": False, "coindesk_working": False,
                       "coindesk_reason": "COINDESK_API_KEY not set"}
        return _CAPS_CACHE
    try:
        import websocket  # websocket-client
        ws = websocket.create_connection(
            f"wss://data-streamer.coindesk.com/?api_key={key}", timeout=10)
        try:
            raw = ws.recv()
        finally:
            ws.close()
        msg = json.loads(raw) if raw else {}
        mtype = str(msg.get("TYPE", ""))
        if mtype == "4000":
            _CAPS_CACHE = {"coindesk_key_present": True, "coindesk_working": True,
                           "coindesk_reason": None}
        elif mtype == "4011":
            _CAPS_CACHE = {"coindesk_key_present": True, "coindesk_working": False,
                           "coindesk_reason": "auth warning 4011 (invalid key -> IP fallback)"}
        else:
            _CAPS_CACHE = {"coindesk_key_present": True, "coindesk_working": False,
                           "coindesk_reason": f"unexpected welcome TYPE {mtype or 'none'}"}
    except Exception as exc:  # noqa: BLE001 - never crash /api/ready
        _CAPS_CACHE = {"coindesk_key_present": True, "coindesk_working": False,
                       "coindesk_reason": type(exc).__name__}
    return _CAPS_CACHE
