# engine/execution/order_manager.py
# QuantEdge — Order Execution Engine
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# Broker routing:
#   US tickers     → Alpaca REST API v2 (free tier, paper + live, market orders)
#   OMX (.ST)      → Yfinance-backed paper simulation (no free OMX live API exists)
#
# Execution modes:
#   SUPERVISED:  score >= supervised_threshold → show one-click confirm button in UI
#   AUTONOMOUS:  score >= autonomous_threshold → execute immediately, then notify
#
# Position sizing:
#   Risk-based:  shares = (capital × risk_pct) / abs(entry − stop)
#   Fixed:       shares = floor(fixed_amount / entry_price)
#   Hard cap:    never exceeds max_position_usd / max_position_sek
#
# FX: live USD/SEK from Frankfurter API (free, no key required)
#
# SECURITY (Gurpreet Singh):
#   API keys in headers only — never in URL, never logged
#   Paper mode is the default; live requires explicit BrokerType.ALPACA_LIVE
#
# <- NEW [execution]: Order manager with Alpaca REST and OMX simulation

import logging
import math
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import TypedDict

import requests

logger = logging.getLogger("QuantEdge.OrderManager")

# ── URL constants ────────────────────────────────────────────────────────────
ALPACA_PAPER_URL: str  = "https://paper-api.alpaca.markets/v2"
ALPACA_LIVE_URL:  str  = "https://api.alpaca.markets/v2"
FRANKFURTER_URL:  str  = "https://api.frankfurter.app/latest"
REQUEST_TIMEOUT:  int  = 10   # seconds

# ── Default thresholds ──────────────────────────────────────────────────────
# Panel decision: SUPERVISED ≥ 50, AUTONOMOUS ≥ 80
SUPERVISED_THRESHOLD_DEFAULT:  int   = 50
AUTONOMOUS_THRESHOLD_DEFAULT:  int   = 80
CAPITAL_USD_DEFAULT:           float = 10_000.0
RISK_PER_TRADE_PCT_DEFAULT:    float = 0.02    # 2% of capital per trade
MAX_POSITION_PCT_DEFAULT:      float = 0.10    # 10% of capital max position
MAX_POSITION_USD_DEFAULT:      float = 2_000.0


# ── Enums ────────────────────────────────────────────────────────────────────
class ExecutionMode(Enum):
    """
    SUPERVISED:  signal displayed with confirm button; user clicks to execute.
    AUTONOMOUS:  auto-executes when score >= autonomous_threshold.
    """
    SUPERVISED = "SUPERVISED"
    AUTONOMOUS = "AUTONOMOUS"


class OrderSide(Enum):
    BUY  = "buy"
    SELL = "sell"


class BrokerType(Enum):
    """
    ALPACA_PAPER: Alpaca paper trading account (default, no real money).
    ALPACA_LIVE:  Alpaca live account (requires real API keys, real money).
    SIMULATED:    Yfinance-price-based simulation for OMX or no-key fallback.
    """
    ALPACA_PAPER = "ALPACA_PAPER"
    ALPACA_LIVE  = "ALPACA_LIVE"
    SIMULATED    = "SIMULATED"


# ── Configuration dataclass ──────────────────────────────────────────────────
@dataclass
class OrderConfig:
    """
    User-configurable execution parameters. All fields have safe defaults
    that prevent accidental live trading.

    Secrets (alpaca_key, alpaca_secret) must be supplied from st.secrets
    or os.environ — never hardcoded.
    """
    mode:                 ExecutionMode = ExecutionMode.SUPERVISED
    broker:               BrokerType    = BrokerType.ALPACA_PAPER
    alpaca_key:           str           = ""
    alpaca_secret:        str           = ""
    supervised_threshold: int           = SUPERVISED_THRESHOLD_DEFAULT
    autonomous_threshold: int           = AUTONOMOUS_THRESHOLD_DEFAULT
    capital_usd:          float         = CAPITAL_USD_DEFAULT
    capital_sek:          float         = 0.0          # 0.0 = auto-convert from USD
    max_position_pct:     float         = MAX_POSITION_PCT_DEFAULT
    max_position_usd:     float         = MAX_POSITION_USD_DEFAULT
    max_position_sek:     float         = 0.0          # 0.0 = auto-convert
    risk_per_trade_pct:   float         = RISK_PER_TRADE_PCT_DEFAULT
    use_fixed_amount:     bool          = False        # True = fixed size, False = risk-based


# ── Typed result contracts ────────────────────────────────────────────────────
class OrderResult(TypedDict):
    """Return type for all order submission functions."""
    success:    bool
    order_id:   str
    ticker:     str
    side:       str
    qty:        int
    price:      float
    total_usd:  float
    total_sek:  float
    broker:     str
    mode:       str
    error:      str


class PositionSizeResult(TypedDict):
    """Return type for position sizing calculation."""
    shares:           int
    cost_usd:         float
    cost_sek:         float
    risk_usd:         float
    fx_rate:          float
    capital_used_pct: float


# ── FX rate ───────────────────────────────────────────────────────────────────
def get_usd_sek_rate() -> float:
    """
    Fetches live USD/SEK exchange rate from Frankfurter API.
    Free, no API key, sourced from European Central Bank data.
    Falls back to 10.50 on any failure — caller is warned via return value context.
    Never raises.
    """
    try:
        resp = requests.get(
            FRANKFURTER_URL,
            params={"from": "USD", "to": "SEK"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            rate = float(resp.json()["rates"]["SEK"])
            logger.debug("USD/SEK rate: %.4f", rate)
            return rate
        logger.warning("Frankfurter API HTTP %d", resp.status_code)
    except Exception as exc:
        logger.warning("FX rate unavailable (%s) — using 10.50 fallback", exc)
    return 10.50   # approximate fallback; UI displays warning when this is used


# ── Ticker routing ─────────────────────────────────────────────────────────────
def is_swedish_ticker(ticker: str) -> bool:
    """Returns True for OMX symbols. Detection: .ST suffix (case-insensitive)."""
    return ticker.upper().endswith(".ST")


def _resolve_broker(ticker: str, config: OrderConfig) -> BrokerType:
    """
    Routes Swedish OMX tickers to SIMULATED regardless of config.broker.
    US tickers use the configured broker.
    """
    if is_swedish_ticker(ticker):
        return BrokerType.SIMULATED
    if not config.alpaca_key:
        return BrokerType.SIMULATED
    return config.broker


# ── Position sizer ─────────────────────────────────────────────────────────────
def compute_position_size(
    entry_price: float,
    stop_loss:   float,
    config:      OrderConfig,
    fx_rate:     float,
    is_sek:      bool = False,
) -> PositionSizeResult:
    """
    Computes share count using risk-based or fixed-amount sizing.

    Risk-based formula (default):
        risk_amount = capital × risk_per_trade_pct
        shares      = floor(risk_amount / abs(entry − stop))
        capped at:  min(max_position_pct × capital, max_position_usd/sek)

    Fixed-amount formula (config.use_fixed_amount = True):
        shares = floor(fixed_amount / entry_price)
        where fixed_amount = min(max_position_pct × capital, max_position_usd/sek)

    All float comparisons use abs() — no == comparisons anywhere.
    math.floor() used for share count (whole shares only).

    Args:
        entry_price: Proposed entry price in the ticker's native currency.
        stop_loss:   Stop-loss price (used for risk-based sizing only).
        config:      OrderConfig with capital and limit parameters.
        fx_rate:     Live USD/SEK rate from get_usd_sek_rate().
        is_sek:      True for OMX tickers (SEK denomination).

    Returns:
        PositionSizeResult with shares, costs in both currencies, and risk.
    """
    empty: PositionSizeResult = {
        "shares": 0, "cost_usd": 0.0, "cost_sek": 0.0,
        "risk_usd": 0.0, "fx_rate": fx_rate, "capital_used_pct": 0.0,
    }

    if entry_price < 1e-10:
        logger.error("Position size: entry_price is zero or negative.")
        return empty

    price_diff = abs(entry_price - stop_loss)

    # Determine working capital and position cap in trade currency
    if is_sek:
        capital = (
            config.capital_sek
            if config.capital_sek > 1e-10
            else config.capital_usd * fx_rate
        )
        max_pos = (
            config.max_position_sek
            if config.max_position_sek > 1e-10
            else config.max_position_usd * fx_rate
        )
    else:
        capital = config.capital_usd
        max_pos = config.max_position_usd

    pct_cap = config.max_position_pct * capital

    if config.use_fixed_amount:
        position_value = min(max_pos, pct_cap)
    else:
        # Risk-based: only valid when stop_loss is meaningfully different from entry
        if price_diff < 1e-10:
            logger.warning("Position size: entry ≈ stop_loss — refusing to compute.")
            return empty
        risk_amount    = capital * config.risk_per_trade_pct
        shares_by_risk = risk_amount / price_diff
        position_value = min(shares_by_risk * entry_price, max_pos, pct_cap)

    shares = math.floor(position_value / entry_price)
    if shares < 1:
        logger.debug("Position size computed as 0 shares — capital/risk settings too tight.")
        return empty

    actual_cost = shares * entry_price

    if is_sek:
        cost_sek = actual_cost
        cost_usd = actual_cost / fx_rate if fx_rate > 1e-10 else 0.0
        risk_usd = (shares * price_diff) / fx_rate if fx_rate > 1e-10 else 0.0
    else:
        cost_usd = actual_cost
        cost_sek = actual_cost * fx_rate
        risk_usd = shares * price_diff

    capital_used_pct = (actual_cost / capital * 100.0) if capital > 1e-10 else 0.0

    return {
        "shares":           shares,
        "cost_usd":         round(cost_usd, 2),
        "cost_sek":         round(cost_sek, 2),
        "risk_usd":         round(risk_usd, 2),
        "fx_rate":          round(fx_rate, 4),
        "capital_used_pct": round(capital_used_pct, 1),
    }


# ── Alpaca REST order submission ───────────────────────────────────────────────
def _submit_alpaca_order(
    ticker: str,
    side:   OrderSide,
    qty:    int,
    config: OrderConfig,
) -> OrderResult:
    """
    Submits a market day-order to Alpaca REST API v2.

    Authentication: APCA-API-KEY-ID and APCA-API-SECRET-KEY headers.
    Keys never appear in URL, never logged in full.
    Paper URL used unless config.broker == ALPACA_LIVE.

    Args:
        ticker: US equity symbol (not OMX — those go to _submit_simulated_order).
        side:   OrderSide.BUY or OrderSide.SELL.
        qty:    Number of whole shares (from compute_position_size).
        config: OrderConfig with Alpaca credentials.

    Returns:
        OrderResult with success status, order_id, and fill details.
    """
    base_url = (
        ALPACA_LIVE_URL
        if config.broker == BrokerType.ALPACA_LIVE
        else ALPACA_PAPER_URL
    )
    headers = {
        "APCA-API-KEY-ID":     config.alpaca_key,
        "APCA-API-SECRET-KEY": config.alpaca_secret,
        "Content-Type":        "application/json",
    }
    payload = {
        "symbol":        ticker,
        "qty":           str(qty),
        "side":          side.value,
        "type":          "market",
        "time_in_force": "day",
    }

    try:
        resp = requests.post(
            f"{base_url}/orders",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()

        if resp.status_code in (200, 201):
            filled_avg = float(data.get("filled_avg_price") or 0.0)
            limit_px   = float(data.get("limit_price") or 0.0)
            price      = filled_avg if filled_avg > 1e-10 else limit_px
            order_id   = str(data.get("id", ""))
            logger.info("Alpaca order submitted: %s %s ×%d id=%s…",
                        side.value.upper(), ticker, qty, order_id[:8])
            return {
                "success":   True,
                "order_id":  order_id,
                "ticker":    ticker,
                "side":      side.value,
                "qty":       qty,
                "price":     price,
                "total_usd": round(price * qty, 2),
                "total_sek": 0.0,   # caller converts using fx_rate
                "broker":    config.broker.value,
                "mode":      config.mode.value,
                "error":     "",
            }

        err_msg = data.get("message") or data.get("error") or resp.text[:200]
        logger.error("Alpaca rejected order [%s %s]: %s", ticker, side.value, err_msg)
        return {
            "success":   False, "order_id": "", "ticker": ticker,
            "side":      side.value, "qty": qty, "price": 0.0,
            "total_usd": 0.0, "total_sek": 0.0,
            "broker":    config.broker.value, "mode": config.mode.value,
            "error":     err_msg,
        }

    except requests.RequestException as exc:
        logger.error("Alpaca request exception [%s]: %s", ticker, exc)
        return {
            "success":   False, "order_id": "", "ticker": ticker,
            "side":      side.value, "qty": qty, "price": 0.0,
            "total_usd": 0.0, "total_sek": 0.0,
            "broker":    config.broker.value, "mode": config.mode.value,
            "error":     str(exc),
        }


# ── Simulated order (OMX / no-key fallback) ───────────────────────────────────
def _submit_simulated_order(
    ticker:      str,
    side:        OrderSide,
    qty:         int,
    entry_price: float,
    fx_rate:     float,
    config:      OrderConfig,
) -> OrderResult:
    """
    Paper simulation for Swedish OMX tickers or when no Alpaca key is set.
    Uses caller-supplied entry_price (from PRZ engine) as fill price.
    Generates a UUID-based order ID prefixed SIM- so it is unmistakably simulated.
    """
    sim_id   = f"SIM-{uuid.uuid4().hex[:8].upper()}"
    is_sek   = is_swedish_ticker(ticker)
    cost_sek = round(entry_price * qty, 2) if is_sek else 0.0
    cost_usd = (
        round(cost_sek / fx_rate, 2) if (is_sek and fx_rate > 1e-10)
        else round(entry_price * qty, 2)
    )
    logger.info("Simulated order: %s %s ×%d @ %.4f [%s]",
                side.value.upper(), ticker, qty, entry_price, sim_id)
    return {
        "success":   True,
        "order_id":  sim_id,
        "ticker":    ticker,
        "side":      side.value,
        "qty":       qty,
        "price":     entry_price,
        "total_usd": cost_usd,
        "total_sek": cost_sek,
        "broker":    BrokerType.SIMULATED.value,
        "mode":      config.mode.value,
        "error":     "",
    }


# ── Account query ──────────────────────────────────────────────────────────────
def get_alpaca_account(config: OrderConfig) -> Dict[str, Any]:
    """
    Fetches Alpaca account summary (equity, buying power, cash).
    Returns {"equity": 0.0, "buying_power": 0.0, "cash": 0.0, "error": ""}
    on any failure.
    """
    base_url = (
        ALPACA_LIVE_URL
        if config.broker == BrokerType.ALPACA_LIVE
        else ALPACA_PAPER_URL
    )
    headers = {
        "APCA-API-KEY-ID":     config.alpaca_key,
        "APCA-API-SECRET-KEY": config.alpaca_secret,
    }
    try:
        resp = requests.get(
            f"{base_url}/account",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "equity":        float(data.get("equity", 0.0)),
                "buying_power":  float(data.get("buying_power", 0.0)),
                "cash":          float(data.get("cash", 0.0)),
                "account_number": str(data.get("account_number", "")),
                "status":        str(data.get("status", "")),
                "error":         "",
            }
        return {"equity": 0.0, "buying_power": 0.0, "cash": 0.0,
                "account_number": "", "status": "", "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        logger.error("Alpaca account fetch: %s", exc)
        return {"equity": 0.0, "buying_power": 0.0, "cash": 0.0,
                "account_number": "", "status": "", "error": str(exc)}


def get_alpaca_positions(config: OrderConfig) -> Dict[str, Any]:
    """
    Fetches list of current open positions from Alpaca.
    Returns {"positions": [...], "error": ""} on success.
    Each position dict contains symbol, qty, current_price, unrealized_pl, side.
    """
    base_url = (
        ALPACA_LIVE_URL
        if config.broker == BrokerType.ALPACA_LIVE
        else ALPACA_PAPER_URL
    )
    headers = {
        "APCA-API-KEY-ID":     config.alpaca_key,
        "APCA-API-SECRET-KEY": config.alpaca_secret,
    }
    try:
        resp = requests.get(
            f"{base_url}/positions",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            raw = resp.json()
            positions = [
                {
                    "symbol":         p.get("symbol", ""),
                    "qty":            float(p.get("qty", 0)),
                    "avg_entry":      float(p.get("avg_entry_price", 0)),
                    "current_price":  float(p.get("current_price", 0)),
                    "unrealized_pl":  float(p.get("unrealized_pl", 0)),
                    "unrealized_plpc": float(p.get("unrealized_plpc", 0)) * 100.0,
                    "side":           p.get("side", ""),
                    "market_value":   float(p.get("market_value", 0)),
                }
                for p in raw
            ]
            return {"positions": positions, "error": ""}
        return {"positions": [], "error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        logger.error("Alpaca positions: %s", exc)
        return {"positions": [], "error": str(exc)}


# ── Public execution interface ─────────────────────────────────────────────────
def execute_order(
    ticker:      str,
    side:        OrderSide,
    entry_price: float,
    stop_loss:   float,
    config:      OrderConfig,
) -> Tuple[OrderResult, PositionSizeResult]:
    """
    Top-level order execution function. Orchestrates:
      1. FX rate fetch
      2. Broker routing (Alpaca US or Simulated OMX)
      3. Position size computation
      4. Order submission

    Args:
        ticker:      Equity symbol. OMX symbols must end in .ST
        side:        OrderSide.BUY or OrderSide.SELL
        entry_price: Entry price from PRZ engine (in ticker's native currency)
        stop_loss:   Stop-loss price (for risk-based sizing)
        config:      OrderConfig with execution parameters and credentials

    Returns:
        Tuple of (OrderResult, PositionSizeResult)
    """
    fx_rate = get_usd_sek_rate()
    is_sek  = is_swedish_ticker(ticker)
    broker  = _resolve_broker(ticker, config)

    pos = compute_position_size(
        entry_price=entry_price,
        stop_loss=stop_loss,
        config=config,
        fx_rate=fx_rate,
        is_sek=is_sek,
    )

    if pos["shares"] < 1:
        error: OrderResult = {
            "success":   False,
            "order_id":  "",
            "ticker":    ticker,
            "side":      side.value,
            "qty":       0,
            "price":     entry_price,
            "total_usd": 0.0,
            "total_sek": 0.0,
            "broker":    broker.value,
            "mode":      config.mode.value,
            "error":     (
                "Position size computed as 0 shares. "
                "Check capital, risk %, and stop-loss distance."
            ),
        }
        return error, pos

    if broker == BrokerType.SIMULATED:
        order = _submit_simulated_order(
            ticker, side, pos["shares"], entry_price, fx_rate, config
        )
    else:
        order = _submit_alpaca_order(ticker, side, pos["shares"], config)

    # Fill in SEK equivalent if missing
    if order["total_sek"] < 1e-10 and order["total_usd"] > 1e-10:
        order["total_sek"] = round(order["total_usd"] * fx_rate, 2)

    return order, pos


# ── Mode query helpers ─────────────────────────────────────────────────────────
def should_auto_execute(confluence_score: int, config: OrderConfig) -> bool:
    """
    Returns True when AUTONOMOUS mode is active AND score >= autonomous_threshold.
    SUPERVISED mode always returns False — user must click to confirm.
    """
    if config.mode is not ExecutionMode.AUTONOMOUS:
        return False
    return confluence_score >= config.autonomous_threshold


def should_show_confirm_button(confluence_score: int, config: OrderConfig) -> bool:
    """
    Returns True when score >= supervised_threshold (in either mode).
    Controls whether the one-click confirm button is shown.
    """
    return confluence_score >= config.supervised_threshold