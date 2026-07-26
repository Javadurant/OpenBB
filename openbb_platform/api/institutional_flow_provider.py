"""
api/institutional_flow_provider.py
====================================
Phase 2 Deliverable D — Institutional Flow Tracker (free, yfinance-backed).

Grounded in the /mnt/project/Institutional_Flow_Tracker.md skill.
The skill's preferred path was FMP API, but the user's FMP_API_KEY returns
HTTP 403 (key issue). yfinance ships the same data class FREE via the
Yahoo Finance backend — institutional_holders, mutualfund_holders,
major_holders, insider_transactions, insider_purchases, insider_roster_holders.

The endpoint /api/symbol/{ticker}/institutional consumes this module.
The frontend InstitutionalCard.tsx renders the normalized output.

Returns 6 buckets of "smart money" data:
  1. top_institutions    : 10 largest institutional holders + QoQ %change
  2. top_mutual_funds    : 10 largest mutual fund holders
  3. summary             : % insider, % institution, total institution count
  4. insider_roster      : current insiders + their direct holdings
  5. recent_transactions : last 25 insider Form 4 transactions
  6. insider_net         : last-6-month aggregate buy/sell summary

All grades follow the skill's reliability framework (A/B/C) by checking
data quality on the cohort.
"""
from __future__ import annotations
import logging
from typing import Any, Final, Optional, TypedDict

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


class InstitutionalHolder(TypedDict, total=False):
    holder:        str
    pct_held:      float    # % of shares outstanding
    shares:        int
    value:         float    # USD
    pct_change:    float    # QoQ change in shares held (1.0 = +100%, -0.05 = -5%)
    date_reported: str      # YYYY-MM-DD


class InsiderTransaction(TypedDict, total=False):
    insider:      str
    position:     str
    transaction:  str        # e.g. "Sale", "Stock Gift", "Conversion"
    start_date:   str        # YYYY-MM-DD
    shares:       int
    value:        float      # USD; 0 = no-cost transaction (gift, conversion)
    ownership:    str        # 'D' (direct) or 'I' (indirect)
    text:         str        # Narrative description from filing


class InsiderRosterEntry(TypedDict, total=False):
    name:                       str
    position:                   str
    most_recent_transaction:    str
    latest_transaction_date:    str
    shares_owned_directly:      int
    position_direct_date:       str


def _safe_float(x: Any) -> Optional[float]:
    """Convert pandas/numpy NaN to None; float-safe."""
    try:
        f = float(x)
        if f != f:  # NaN check (float != itself for NaN)
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(x: Any) -> Optional[int]:
    try:
        f = float(x)
        if f != f:
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    s = str(x)
    if s.lower() in ("nan", "nat", "none"):
        return default
    return s


def _df_to_records(df: Optional[pd.DataFrame], limit: int = 25) -> list[dict[str, Any]]:
    """Convert a yfinance DataFrame to JSON-safe list of dicts."""
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.head(limit).iterrows():
        rec = {}
        for col, val in row.items():
            key = str(col)
            if isinstance(val, (pd.Timestamp,)):
                rec[key] = val.strftime("%Y-%m-%d") if not pd.isna(val) else ""
            elif isinstance(val, float):
                f = _safe_float(val)
                rec[key] = f if f is not None else None
            else:
                rec[key] = _safe_str(val)
        out.append(rec)
    return out


def _normalize_holders(df: Optional[pd.DataFrame], limit: int) -> list[InstitutionalHolder]:
    """yfinance institutional_holders / mutualfund_holders → typed list."""
    if df is None or len(df) == 0:
        return []
    out: list[InstitutionalHolder] = []
    for _, row in df.head(limit).iterrows():
        date_val = row.get("Date Reported")
        date_str = ""
        if isinstance(date_val, pd.Timestamp) and not pd.isna(date_val):
            date_str = date_val.strftime("%Y-%m-%d")
        elif date_val is not None:
            date_str = str(date_val)[:10]
        entry: InstitutionalHolder = {
            "holder":        _safe_str(row.get("Holder")),
            "pct_held":      _safe_float(row.get("pctHeld")) or 0.0,
            "shares":        _safe_int(row.get("Shares")) or 0,
            "value":         _safe_float(row.get("Value")) or 0.0,
            "pct_change":    _safe_float(row.get("pctChange")) or 0.0,
            "date_reported": date_str,
        }
        out.append(entry)
    return out


def _normalize_transactions(df: Optional[pd.DataFrame], limit: int) -> list[InsiderTransaction]:
    """yfinance insider_transactions → typed list."""
    if df is None or len(df) == 0:
        return []
    out: list[InsiderTransaction] = []
    for _, row in df.head(limit).iterrows():
        date_val = row.get("Start Date")
        date_str = ""
        if isinstance(date_val, pd.Timestamp) and not pd.isna(date_val):
            date_str = date_val.strftime("%Y-%m-%d")
        elif date_val is not None:
            date_str = str(date_val)[:10]
        entry: InsiderTransaction = {
            "insider":     _safe_str(row.get("Insider")),
            "position":    _safe_str(row.get("Position")),
            "transaction": _safe_str(row.get("Transaction")),
            "start_date":  date_str,
            "shares":      _safe_int(row.get("Shares")) or 0,
            "value":       _safe_float(row.get("Value")) or 0.0,
            "ownership":   _safe_str(row.get("Ownership")),
            "text":        _safe_str(row.get("Text"))[:240],
        }
        out.append(entry)
    return out


def _normalize_roster(df: Optional[pd.DataFrame], limit: int) -> list[InsiderRosterEntry]:
    """yfinance insider_roster_holders → typed list."""
    if df is None or len(df) == 0:
        return []
    out: list[InsiderRosterEntry] = []
    for _, row in df.head(limit).iterrows():
        ltd = row.get("Latest Transaction Date")
        ltd_str = ""
        if isinstance(ltd, pd.Timestamp) and not pd.isna(ltd):
            ltd_str = ltd.strftime("%Y-%m-%d")
        elif ltd is not None:
            ltd_str = str(ltd)[:10]
        pdd = row.get("Position Direct Date")
        pdd_str = ""
        if isinstance(pdd, pd.Timestamp) and not pd.isna(pdd):
            pdd_str = pdd.strftime("%Y-%m-%d")
        elif pdd is not None:
            pdd_str = str(pdd)[:10]
        entry: InsiderRosterEntry = {
            "name":                    _safe_str(row.get("Name")),
            "position":                _safe_str(row.get("Position")),
            "most_recent_transaction": _safe_str(row.get("Most Recent Transaction")),
            "latest_transaction_date": ltd_str,
            "shares_owned_directly":   _safe_int(row.get("Shares Owned Directly")) or 0,
            "position_direct_date":    pdd_str,
        }
        out.append(entry)
    return out


def _classify_signal(top_institutions: list[InstitutionalHolder]) -> tuple[str, str]:
    """
    Apply the skill's signal-strength framework to QoQ ownership changes.
    Returns (signal, reasoning).

    Strong Bullish: top holders increasing >15% QoQ
    Moderate Bullish: 5-15%
    Neutral: <5% in absolute
    Moderate Bearish: -5 to -15%
    Strong Bearish: < -15%
    """
    if not top_institutions:
        return ("UNKNOWN", "No institutional data available.")

    # Weight by shares — small holders shouldn't move the signal
    weighted_change = 0.0
    total_shares = 0
    for h in top_institutions:
        s = h.get("shares", 0)
        c = h.get("pct_change", 0.0)
        # Cap weird outliers (yfinance returns 1.0 for new positions)
        c_capped = max(min(c, 0.50), -0.50)
        weighted_change += c_capped * s
        total_shares += s

    if total_shares == 0:
        return ("UNKNOWN", "Insufficient holder data.")

    avg_change = weighted_change / total_shares
    pct = avg_change * 100.0

    if pct > 15.0:
        signal, reason = "STRONG BULLISH", f"Top institutions accumulating aggressively (avg +{pct:.1f}% QoQ)."
    elif pct > 5.0:
        signal, reason = "MODERATE BULLISH", f"Top institutions adding to positions (avg +{pct:.1f}% QoQ)."
    elif pct > -5.0:
        signal, reason = "NEUTRAL", f"Top institutions stable (avg {pct:+.1f}% QoQ)."
    elif pct > -15.0:
        signal, reason = "MODERATE BEARISH", f"Top institutions reducing positions (avg {pct:.1f}% QoQ)."
    else:
        signal, reason = "STRONG BEARISH", f"Top institutions distributing aggressively (avg {pct:.1f}% QoQ)."
    return signal, reason


def _reliability_grade(top_institutions: list[InstitutionalHolder],
                       transactions: list[InsiderTransaction],
                       summary: dict[str, Any]) -> str:
    """
    Apply the skill's reliability grading (A/B/C) based on data completeness.
    A: full data, all categories returned
    B: partial data, some categories missing
    C: minimal data, only summary available
    """
    score = 0
    if len(top_institutions) >= 8:    score += 2
    if len(transactions) >= 10:       score += 2
    if summary.get("institutionsCount", 0) > 100:  score += 1
    if summary.get("institutionsPercentHeld", 0) > 0.1: score += 1

    if score >= 5:  return "A"
    if score >= 3:  return "B"
    return "C"


def fetch_institutional_flow(ticker: str) -> dict[str, Any]:
    """
    Pull all institutional flow buckets for a ticker. Free via yfinance.

    Returns a JSON-ready dict with status, signal, reliability_grade,
    summary, top_institutions, top_mutual_funds, insider_roster,
    recent_transactions, insider_net_summary.
    """
    ticker_upper = ticker.upper().strip()
    if not ticker_upper:
        return {"status": "error", "message": "ticker is required"}

    try:
        tk = yf.Ticker(ticker_upper)
    except Exception as e:
        logger.warning("yfinance Ticker init failed for %s: %s", ticker_upper, e)
        return {"status": "error", "message": str(e)}

    # 1. Institutional holders
    try:
        inst = _normalize_holders(tk.institutional_holders, limit=10)
    except Exception as e:
        logger.warning("institutional_holders failed for %s: %s", ticker_upper, e)
        inst = []

    # 2. Mutual fund holders
    try:
        mf = _normalize_holders(tk.mutualfund_holders, limit=10)
    except Exception as e:
        logger.warning("mutualfund_holders failed for %s: %s", ticker_upper, e)
        mf = []

    # 3. Major holders summary
    summary: dict[str, Any] = {}
    try:
        mh = tk.major_holders
        if mh is not None and len(mh) > 0:
            # major_holders returns a DataFrame with a single 'Value' column
            # indexed by 'Breakdown' key strings
            for idx, row in mh.iterrows():
                key = str(idx)
                val = _safe_float(row.get("Value"))
                if val is None:
                    continue
                if "insiders" in key.lower():
                    summary["insidersPercentHeld"] = val
                elif "institutionsfloatpercent" in key.lower():
                    summary["institutionsFloatPercentHeld"] = val
                elif "institutionspercent" in key.lower():
                    summary["institutionsPercentHeld"] = val
                elif "count" in key.lower():
                    summary["institutionsCount"] = int(val)
    except Exception as e:
        logger.warning("major_holders failed for %s: %s", ticker_upper, e)

    # 4. Insider roster
    try:
        roster = _normalize_roster(tk.insider_roster_holders, limit=12)
    except Exception as e:
        logger.warning("insider_roster_holders failed for %s: %s", ticker_upper, e)
        roster = []

    # 5. Recent transactions
    try:
        transactions = _normalize_transactions(tk.insider_transactions, limit=25)
    except Exception as e:
        logger.warning("insider_transactions failed for %s: %s", ticker_upper, e)
        transactions = []

    # 6. Insider net summary (last 6 months)
    insider_net: dict[str, Any] = {}
    try:
        ip = tk.insider_purchases
        if ip is not None and len(ip) > 0:
            for _, row in ip.iterrows():
                label = _safe_str(row.get("Insider Purchases Last 6m"))
                shares = _safe_int(row.get("Shares"))
                trans  = _safe_int(row.get("Trans"))
                if label:
                    insider_net[label] = {"shares": shares, "trans": trans}
    except Exception as e:
        logger.warning("insider_purchases failed for %s: %s", ticker_upper, e)

    # Signal + reliability grade
    signal, reasoning = _classify_signal(inst)
    grade = _reliability_grade(inst, transactions, summary)

    return {
        "status":              "ok",
        "symbol":              ticker_upper,
        "provider":            "yfinance",
        "signal":              signal,
        "signal_reasoning":    reasoning,
        "reliability_grade":   grade,
        "summary":             summary,
        "top_institutions":    inst,
        "top_mutual_funds":    mf,
        "insider_roster":      roster,
        "recent_transactions": transactions,
        "insider_net_6m":      insider_net,
    }
