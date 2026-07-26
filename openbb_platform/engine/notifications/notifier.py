# engine/notifications/notifier.py
# QuantEdge — Notification Dispatch Engine
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# Channels:
#   Telegram Bot API — free, no cost, HTTPS-only, instant delivery
#   Gmail SMTP TLS   — free, requires app password (not account password)
#
# Signal types: ENTER_NOW, EXIT_NOW, TRADE_OPENED, TRADE_CLOSED, RISK_WARNING
#
# SECURITY (Gurpreet Singh):
#   Bot token transmitted over HTTPS only — never logged, never stored in session_state
#   Gmail uses STARTTLS (port 587) with ssl.create_default_context() — no SSLv3/TLS1.0
#   No credentials stored in this module — callers supply from st.secrets or env vars
#
# <- NEW [notifications]: Telegram + Gmail alert dispatcher

import logging
import smtplib
import ssl
from dataclasses import dataclass
from dataclasses import field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Dict
from typing import List
from typing import Optional

import requests

logger = logging.getLogger("QuantEdge.Notifier")

# ── Telegram API ────────────────────────────────────────────────────────────
_TELEGRAM_BASE: str = "https://api.telegram.org/bot{token}/sendMessage"
_TELEGRAM_TIMEOUT: int = 8   # seconds — fast enough for trading alerts

# ── Signal type enum ────────────────────────────────────────────────────────
class SignalType(Enum):
    """All signal types that trigger notifications. Values are display labels."""
    ENTER_NOW     = "🚀 ENTER NOW"
    EXIT_NOW      = "🔻 EXIT NOW"
    TRADE_OPENED  = "✅ TRADE OPENED"
    TRADE_CLOSED  = "🔒 TRADE CLOSED"
    RISK_WARNING  = "⚠️ RISK WARNING"


# ── Configuration dataclass ─────────────────────────────────────────────────
@dataclass
class NotificationConfig:
    """
    Configuration for all notification channels.
    All secret fields (token, password) must be supplied by the caller
    from st.secrets or os.environ — never hardcoded, never stored in session_state.

    Fields:
        telegram_token:   BotFather token. Format: 123456:ABC-DEF...
        telegram_chat_id: Chat or channel ID. Obtain by messaging @userinfobot.
        email_smtp_host:  SMTP host. Default: smtp.gmail.com
        email_smtp_port:  SMTP port. Default: 587 (STARTTLS)
        email_from:       Sender address (must match SMTP credentials).
        email_password:   Gmail app password (16-char, not account password).
        email_to:         Recipient address.
        channels:         List of active channel names: ["telegram"], ["email"], or both.
    """
    telegram_token:   str       = ""
    telegram_chat_id: str       = ""
    email_smtp_host:  str       = "smtp.gmail.com"
    email_smtp_port:  int       = 587
    email_from:       str       = ""
    email_password:   str       = ""
    email_to:         str       = ""
    channels:         List[str] = field(default_factory=lambda: ["telegram"])


# ── Alert payload dataclass ─────────────────────────────────────────────────
@dataclass
class TradeAlert:
    """
    Typed payload for a single trade alert.
    All price fields are floats. No float == comparisons made here — this is
    a data container only; comparison logic lives in order_manager.py.
    """
    signal_type:       SignalType
    ticker:            str
    current_price:     float
    entry_low:         float
    entry_high:        float
    target_1:          float
    target_2:          float
    target_3:          float
    stop_loss:         float
    confluence_score:  int
    confidence_pct:    float
    rr_ratio:          float
    execution_mode:    str        # "SUPERVISED" or "AUTONOMOUS"
    currency:          str = "USD"
    extra_note:        str = ""


# ── Message formatter ────────────────────────────────────────────────────────
def _build_message(alert: TradeAlert) -> str:
    """
    Builds a Telegram MarkdownV2-compatible message from a TradeAlert.
    Entry / exit sections rendered conditionally based on signal type.
    All numeric values formatted to 4 decimal places for precision.
    """
    sig    = alert.signal_type.value
    ticker = alert.ticker
    ccy    = alert.currency

    lines: List[str] = [
        f"*QuantEdge — {sig}*",
        "",
        f"🏷 *Ticker:*  `{ticker}`",
        f"💵 *Price:*   `{alert.current_price:.4f} {ccy}`",
        f"📊 *Score:*   `{alert.confluence_score:+d}` | Confidence `{alert.confidence_pct:.1f}%`",
        f"🤖 *Mode:*    `{alert.execution_mode}`",
        "",
    ]

    if alert.signal_type in (SignalType.ENTER_NOW, SignalType.TRADE_OPENED):
        lines += [
            "─── *ENTRY ZONE* ───────────────────",
            f"📍 *Entry Range:* `{alert.entry_low:.4f} – {alert.entry_high:.4f}`",
            "",
            "─── *EXIT TARGETS (staged)* ────────",
            f"🎯 *T1 (50% exit):* `{alert.target_1:.4f}`",
            f"🎯 *T2 (30% exit):* `{alert.target_2:.4f}`",
            f"🎯 *T3 (20% exit):* `{alert.target_3:.4f}`",
            "",
            "─── *RISK* ─────────────────────────",
            f"🛑 *Stop Loss:*     `{alert.stop_loss:.4f}`",
            f"⚖️ *R:R Ratio:*    `{alert.rr_ratio:.1f}:1`",
        ]
    elif alert.signal_type in (SignalType.EXIT_NOW, SignalType.TRADE_CLOSED):
        lines += [
            "─── *EXIT* ─────────────────────────",
            f"📤 *Exit Price:* `{alert.current_price:.4f}`",
            f"🎯 *Was T1:*     `{alert.target_1:.4f}`",
            f"🎯 *Was T2:*     `{alert.target_2:.4f}`",
        ]
    elif alert.signal_type == SignalType.RISK_WARNING:
        lines += [
            "─── *WARNING* ───────────────────────",
        ]

    if alert.extra_note:
        lines += ["", f"📝 _{alert.extra_note}_"]

    lines += [
        "",
        "────────────────────────────────────",
        "_QuantEdge · Research only · Not financial advice_",
    ]
    return "\n".join(lines)


# ── Telegram sender ──────────────────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """
    Sends a Telegram message via Bot API over HTTPS.

    Args:
        token:   BotFather bot token. Never logged.
        chat_id: Target chat or channel ID.
        text:    Message body (Markdown supported).

    Returns:
        True on HTTP 200 success, False on any failure.
        Never raises — all errors are logged and swallowed.
    """
    if not token or not chat_id:
        logger.debug("Telegram not configured — no token or chat_id.")
        return False
    url     = _TELEGRAM_BASE.format(token=token)
    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=_TELEGRAM_TIMEOUT)
        if resp.status_code == 200:
            logger.info("Telegram alert delivered [chat=%s]", chat_id[:6] + "***")
            return True
        # Log only status code, not token in URL
        logger.warning("Telegram HTTP %d: %s", resp.status_code, resp.text[:150])
        return False
    except requests.RequestException as exc:
        logger.error("Telegram delivery failed: %s", exc)
        return False


# ── Email sender ──────────────────────────────────────────────────────────────
def send_email_alert(
    config:  NotificationConfig,
    subject: str,
    body:    str,
) -> bool:
    """
    Sends an email alert via SMTP with STARTTLS (port 587).

    Compatible with Gmail app passwords (requires 2FA enabled on Gmail account;
    generate at myaccount.google.com/apppasswords).
    Compatible with any standard SMTP server.

    Returns:
        True on successful send, False on any failure.
        Never raises.
    """
    if not config.email_from or not config.email_to or not config.email_password:
        logger.debug("Email not configured — missing from/to/password.")
        return False
    try:
        msg             = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = config.email_from
        msg["To"]       = config.email_to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        ctx = ssl.create_default_context()   # verifies server cert; no SSLv3/TLS1.0
        with smtplib.SMTP(config.email_smtp_host, config.email_smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(config.email_from, config.email_password)
            smtp.sendmail(config.email_from, config.email_to, msg.as_string())

        logger.info("Email alert sent to %s", config.email_to[:4] + "***")
        return True
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("Email auth failed (check app password): %s", exc)
        return False
    except smtplib.SMTPException as exc:
        logger.error("Email SMTP error: %s", exc)
        return False
    except OSError as exc:
        logger.error("Email connection error: %s", exc)
        return False


# ── Main dispatcher ───────────────────────────────────────────────────────────
def dispatch_alert(
    config: NotificationConfig,
    alert:  TradeAlert,
) -> Dict[str, bool]:
    """
    Dispatches a TradeAlert to all configured notification channels.

    Args:
        config: NotificationConfig with channel credentials.
        alert:  TradeAlert payload.

    Returns:
        Dict of channel name → delivery success bool.
        e.g. {"telegram": True, "email": False}
    """
    results: Dict[str, bool] = {}
    text = _build_message(alert)

    if "telegram" in config.channels and config.telegram_token:
        results["telegram"] = send_telegram(
            config.telegram_token,
            config.telegram_chat_id,
            text,
        )

    if "email" in config.channels and config.email_from:
        subject = f"QuantEdge [{alert.signal_type.value}] {alert.ticker}"
        # Plain text version: strip markdown markers
        plain = text.replace("*", "").replace("`", "").replace("_", "")
        results["email"] = send_email_alert(config, subject, plain)

    if not results:
        logger.debug("dispatch_alert: no channels active for alert %s/%s",
                     alert.ticker, alert.signal_type.name)

    return results