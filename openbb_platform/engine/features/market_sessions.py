# engine/features/market_sessions.py
# QuantEdge — Global Market Session Clock
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# Tracks the 4 major equity sessions in real time using Python stdlib (zoneinfo).
# Zero external dependencies.
#
# Sessions:
#   Sydney / ASX   — Asia-Pacific session opener
#   Tokyo / TSE    — Asia session; Nikkei leads OMX Stockholm pre-market
#   London / LSE   — European session (includes OMX Stockholm 30)
#   New York / NYSE — US session; highest global liquidity
#
# Signal propagation logic:
#   Empirical observation (not a hard ratio):
#     Tokyo direction → ~60% correlation with early London open
#     London direction → ~65-70% correlation with New York open
#   These are stated as probabilistic patterns, not guarantees.
#
# <- NEW [market_sessions]: Real-time 4-session clock and propagation hints

import datetime
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import List
from typing import Optional
from typing import Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("QuantEdge.MarketSessions")


# ── Session definition ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SessionDef:
    """
    Static definition of a market session.
    open_h/open_m and close_h/close_m are in the session's LOCAL time.
    """
    name:     str
    timezone: str
    open_h:   int
    open_m:   int
    close_h:  int
    close_m:  int
    color:    str
    indices:  Tuple[str, ...]


# ── Session definitions ────────────────────────────────────────────────────────
# Times reflect equity market open/close windows.
# Sydney: ASX equities 10:00–16:00 AEST/AEDT
# Tokyo:  TSE  equities  9:00–15:30 JST (lunch break omitted for simplicity)
# London: LSE  equities  8:00–16:30 GMT/BST (OMX Stockholm: 9:00–17:30 CET, proxied here)
# New York: NYSE/NASDAQ  9:30–16:00 ET
SESSION_DEFINITIONS: Tuple[SessionDef, ...] = (
    SessionDef(
        name     = "Sydney / ASX",
        timezone = "Australia/Sydney",
        open_h   = 10, open_m  = 0,
        close_h  = 16, close_m = 0,
        color    = "#00BFFF",
        indices  = ("ASX 200", "S&P/ASX 50", "All Ords"),
    ),
    SessionDef(
        name     = "Tokyo / TSE",
        timezone = "Asia/Tokyo",
        open_h   = 9,  open_m  = 0,
        close_h  = 15, close_m = 30,
        color    = "#FF69B4",
        indices  = ("Nikkei 225", "TOPIX", "JPX-Nikkei 400"),
    ),
    SessionDef(
        name     = "London / LSE",
        timezone = "Europe/London",
        open_h   = 8,  open_m  = 0,
        close_h  = 16, close_m = 30,
        color    = "#FFD700",
        indices  = ("FTSE 100", "DAX 40", "CAC 40", "OMX Stockholm 30"),
    ),
    SessionDef(
        name     = "New York / NYSE",
        timezone = "America/New_York",
        open_h   = 9,  open_m  = 30,
        close_h  = 16, close_m = 0,
        color    = "#00FF88",
        indices  = ("S&P 500", "NASDAQ 100", "DJIA", "Russell 2000"),
    ),
)

# Session name → propagation order (lower = opens earlier)
_SESSION_ORDER: dict = {
    "Sydney / ASX":    0,
    "Tokyo / TSE":     1,
    "London / LSE":    2,
    "New York / NYSE": 3,
}


# ── Session status dataclass ──────────────────────────────────────────────────
@dataclass
class SessionStatus:
    """
    Runtime state of a single market session at a specific UTC moment.
    All time strings are pre-formatted for display — no computation in UI layer.
    """
    name:           str
    is_open:        bool
    local_time:     str           # HH:MM in session's local timezone
    utc_time:       str           # HH:MM UTC (same for all sessions in a call)
    opens_in_min:   int           # minutes until next open (0 if already open)
    closes_in_min:  int           # minutes until close (0 if already closed)
    color:          str
    indices:        Tuple[str, ...]
    is_session_lead: bool         # True if this is the earliest-open session right now


# ── Status computation ─────────────────────────────────────────────────────────
def get_session_statuses(
    reference_utc: Optional[datetime.datetime] = None,
) -> List[SessionStatus]:
    """
    Returns current status for all 4 sessions relative to reference_utc.

    Args:
        reference_utc: UTC datetime to evaluate (defaults to now).
                       Supply a fixed value in tests to get deterministic output.

    Returns:
        List[SessionStatus] in definition order: Sydney, Tokyo, London, New York.
    """
    if reference_utc is None:
        reference_utc = datetime.datetime.now(datetime.timezone.utc)

    statuses: List[SessionStatus] = []
    utc_str = reference_utc.strftime("%H:%M UTC")

    for sdef in SESSION_DEFINITIONS:
        tz       = ZoneInfo(sdef.timezone)
        local_dt = reference_utc.astimezone(tz)

        local_open  = local_dt.replace(
            hour=sdef.open_h, minute=sdef.open_m, second=0, microsecond=0
        )
        local_close = local_dt.replace(
            hour=sdef.close_h, minute=sdef.close_m, second=0, microsecond=0
        )

        is_open = local_open <= local_dt < local_close

        if is_open:
            opens_in_min  = 0
            closes_in_min = max(0, int((local_close - local_dt).total_seconds() / 60))
        else:
            closes_in_min = 0
            if local_dt < local_open:
                opens_in_min = int((local_open - local_dt).total_seconds() / 60)
            else:
                # Session closed for today — compute time to tomorrow's open
                tomorrow_open = local_open + datetime.timedelta(days=1)
                opens_in_min  = int((tomorrow_open - local_dt).total_seconds() / 60)

        statuses.append(SessionStatus(
            name           = sdef.name,
            is_open        = is_open,
            local_time     = local_dt.strftime("%H:%M"),
            utc_time       = utc_str,
            opens_in_min   = opens_in_min,
            closes_in_min  = closes_in_min,
            color          = sdef.color,
            indices        = sdef.indices,
            is_session_lead = False,   # set after all are computed
        ))

    # Mark the earliest-opening session among those currently open
    open_list = [s for s in statuses if s.is_open]
    if open_list:
        lead = min(open_list, key=lambda s: _SESSION_ORDER.get(s.name, 99))
        # Find in statuses list and replace (frozen dataclass workaround)
        for i, s in enumerate(statuses):
            if s.name == lead.name:
                statuses[i] = SessionStatus(
                    name           = s.name,
                    is_open        = s.is_open,
                    local_time     = s.local_time,
                    utc_time       = s.utc_time,
                    opens_in_min   = s.opens_in_min,
                    closes_in_min  = s.closes_in_min,
                    color          = s.color,
                    indices        = s.indices,
                    is_session_lead = True,
                )
                break

    return statuses


# ── Signal propagation hints ───────────────────────────────────────────────────
def get_propagation_hints(statuses: List[SessionStatus]) -> List[str]:
    """
    Returns actionable signal propagation hints based on which sessions are open.

    Hints are empirical pattern observations — not guarantees or hard ratios.
    Each hint is a single-line string suitable for UI display.

    Returns:
        List of hint strings. Empty list if no relevant context.
    """
    open_names  = {s.name for s in statuses if s.is_open}
    hints: List[str] = []

    if not open_names:
        soonest = min(
            (s for s in statuses if s.opens_in_min > 0),
            key=lambda s: s.opens_in_min,
            default=None,
        )
        if soonest:
            hints.append(
                f"⏱ All sessions closed. "
                f"{soonest.name} opens in {soonest.opens_in_min} min."
            )
        return hints

    # Sydney lead → Asia-Pacific tone
    if "Sydney / ASX" in open_names and "Tokyo / TSE" not in open_names:
        hints.append(
            "🌏 Sydney session leads. ASX 200 direction sets Asia-Pacific tone "
            "before Tokyo open."
        )

    # Tokyo open → OMX pre-market correlation
    if "Tokyo / TSE" in open_names:
        hints.append(
            "🌸 Tokyo open. Nikkei 225 direction shows ~60% historical correlation "
            "with OMX Stockholm 30 pre-market."
        )

    # London open, New York not yet open
    if "London / LSE" in open_names and "New York / NYSE" not in open_names:
        hints.append(
            "🇬🇧 London session active. FTSE/DAX momentum has ~65% correlation "
            "with S&P 500 open direction (empirical, not guaranteed)."
        )

    # London + New York overlap — maximum liquidity
    if "London / LSE" in open_names and "New York / NYSE" in open_names:
        hints.append(
            "⚡ London + New York overlap (13:00–16:30 GMT). "
            "Highest global liquidity window — signals carry maximum weight."
        )
        # Check if London is closing soon
        london = next((s for s in statuses if s.name == "London / LSE"), None)
        if london and london.is_open and 0 < london.closes_in_min <= 90:
            hints.append(
                f"⚠️ London closes in {london.closes_in_min} min. "
                "Expect volume drop and potential direction shift as European desks close."
            )

    # New York only (after London close)
    if "New York / NYSE" in open_names and "London / LSE" not in open_names:
        hints.append(
            "🗽 New York session active (post-London). "
            "US-driven momentum. Watch macro data releases and Fed speakers."
        )

    return hints


# ── OMX-specific session context ───────────────────────────────────────────────
def get_omx_context(statuses: List[SessionStatus]) -> str:
    """
    Returns a concise OMX Stockholm trading context string.
    OMX Stockholm: opens 09:00 CET / 08:00 UTC, closes 17:30 CET / 16:30 UTC.
    Proxied by London session status.
    """
    london = next((s for s in statuses if s.name == "London / LSE"), None)
    if london is None:
        return "OMX context unavailable."
    if london.is_open:
        return (
            f"OMX Stockholm 30 session active. "
            f"London/CET closes in {london.closes_in_min} min."
        )
    return (
        f"OMX Stockholm 30 closed. "
        f"London session opens in {london.opens_in_min} min."
    )