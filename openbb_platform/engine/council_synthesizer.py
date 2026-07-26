"""
engine/council_synthesizer.py

QuantEdge — Council Synthesis Layer (Phase C)
Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH

ARCHITECTURE:
  After the 5 advisors invoke their tools and capture data via
  /council/execute, the synthesizer reads all 5 advisor outputs and
  asks Groq LLaMA 3.3 70B to produce a structured trading verdict.

  Output schema:
    verdict:    "BUY" | "HOLD" | "SELL"
    confidence: int (0-100)
    headline:   str (one-line summary)
    reasoning:  str (multi-paragraph rationale tied to advisor data)
    risks:      List[str] (concrete risks flagged by Contrarian/First Principles)
    actions:    List[str] (concrete next steps from Executor/Expansionist)

WHY THIS LAYER EXISTS:
  Raw advisor data (account, positions, health) is not a decision.
  The synthesizer is the moment where 5 perspectives become 1 actionable
  recommendation. This is the "Transparent Signal Hub" product promise.

INTEGRITY GUARDS:
  - Temperature pinned to 0.2 for reproducibility
  - Max tokens capped to prevent runaway costs
  - JSON-mode requested for parseable output
  - Fallback to structured error on Groq failure
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from groq import Groq  # type: ignore
    GROQ_AVAILABLE = True
except ImportError:  # pragma: no cover - defensive
    Groq = None  # type: ignore
    GROQ_AVAILABLE = False

logger = logging.getLogger("QuantEdge.CouncilSynthesizer")

# ── Model + sampling configuration ────────────────────────────────────
GROQ_MODEL: str          = "llama-3.3-70b-versatile"
TEMPERATURE_DEFAULT: float = 0.2  # low for reproducibility
MAX_TOKENS_DEFAULT: int    = 1024
TOP_P_DEFAULT: float       = 0.9

# ── Valid verdicts ────────────────────────────────────────────────────
VALID_VERDICTS: tuple = ("BUY", "HOLD", "SELL")


# ── System prompt: the synthesis role ─────────────────────────────────
SYSTEM_PROMPT: str = (
    "You are the Council Synthesizer for SENTRIQ, an AI-powered trading platform.\n"
    "You receive structured outputs from 5 distinct advisors:\n"
    "  • CONTRARIAN — finds risks, asks what could go wrong\n"
    "  • FIRST_PRINCIPLES — strips assumptions, asks what is actually known\n"
    "  • EXPANSIONIST — sees the big play, asks what could go bigger\n"
    "  • OUTSIDER — reads the human signal, what is actually being requested\n"
    "  • EXECUTOR — time math + risk analysis, what ships fastest\n\n"
    "Your job is to synthesize their tool outputs into ONE actionable trading verdict.\n"
    "Output STRICT JSON only — no preamble, no markdown fences.\n\n"
    "JSON schema (every field required):\n"
    "{\n"
    '  "verdict": "BUY" | "HOLD" | "SELL",\n'
    '  "confidence": <integer 0-100>,\n'
    '  "headline": "<one-line summary, under 100 chars>",\n'
    '  "reasoning": "<2-3 paragraphs tying conclusion to advisor data>",\n'
    '  "risks": ["<concrete risk 1>", "<concrete risk 2>", ...],\n'
    '  "actions": ["<next step 1>", "<next step 2>", ...]\n'
    "}\n\n"
    "RULES:\n"
    "  1. Cite specific values from advisor data (equity, positions, prices) in your reasoning.\n"
    "  2. HOLD is the default when data is insufficient or signals are mixed.\n"
    "  3. BUY/SELL require confidence ≥ 60.\n"
    "  4. risks and actions must each contain at least 1 item.\n"
    "  5. Never invent data — only use what advisors provided.\n"
)


def _build_user_message(
    decision_type: str,
    query: str,
    deliberation: List[Dict[str, Any]],
) -> str:
    """Format the council deliberation as a user message for the LLM."""
    sections: List[str] = []
    sections.append(f"DECISION TYPE: {decision_type}")
    if query:
        sections.append(f"USER QUERY: {query}")
    sections.append("")
    sections.append("=== ADVISOR DELIBERATION ===")

    for entry in deliberation:
        advisor = entry.get("advisor", "UNKNOWN")
        rationale = entry.get("rationale", "")
        tool_results = entry.get("tool_results", [])

        sections.append(f"\n── {advisor} ──")
        sections.append(f"Role: {rationale[:200]}")

        if not tool_results:
            sections.append("Data: (no tools invoked)")
            continue

        for tr in tool_results:
            if tr.get("success"):
                # Pretty-print the data (compact JSON)
                data = tr.get("data", {})
                tool_name = tr.get("tool", "?")
                sections.append(f"  Tool [{tool_name}] returned:")
                sections.append(f"    {json.dumps(data, default=str)[:500]}")
            else:
                sections.append(
                    f"  Tool [{tr.get('tool','?')}] failed: {tr.get('error','unknown')}"
                )

    sections.append("\n=== END DELIBERATION ===")
    sections.append("\nProduce the JSON verdict now.")
    return "\n".join(sections)


def _validate_synthesis(payload: Dict[str, Any]) -> Optional[str]:
    """Return error string if payload is invalid, else None."""
    required_keys = {"verdict", "confidence", "headline", "reasoning", "risks", "actions"}
    missing = required_keys - set(payload.keys())
    if missing:
        return f"missing keys: {sorted(missing)}"

    verdict = payload.get("verdict")
    if verdict not in VALID_VERDICTS:
        return f"invalid verdict '{verdict}' (must be one of {VALID_VERDICTS})"

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 100):
        return f"invalid confidence '{confidence}' (must be 0-100)"

    if not isinstance(payload.get("risks"), list) or len(payload["risks"]) == 0:
        return "risks must be a non-empty list"

    if not isinstance(payload.get("actions"), list) or len(payload["actions"]) == 0:
        return "actions must be a non-empty list"

    return None


def synthesize_deliberation(
    decision_type: str,
    query: str,
    deliberation: List[Dict[str, Any]],
    *,
    api_key: Optional[str] = None,
    model: str = GROQ_MODEL,
    temperature: float = TEMPERATURE_DEFAULT,
    max_tokens: int = MAX_TOKENS_DEFAULT,
) -> Dict[str, Any]:
    """
    Synthesize a 5-advisor deliberation into a single trading verdict.

    Args:
        decision_type: One of RISK_CHECK, OPPORTUNITY_SCAN, etc.
        query:         User-supplied context (ticker, scenario, etc.)
        deliberation:  Output from /council/execute deliberation array
        api_key:       Optional explicit Groq key (defaults to GROQ_API_KEY env)
        model:         Groq model name
        temperature:   Sampling temperature (default 0.2)
        max_tokens:    Cap on output length

    Returns:
        Dict with keys: success, verdict, confidence, headline, reasoning,
        risks, actions, model, error (when failed).
    """
    if not GROQ_AVAILABLE:
        return {
            "success":     False,
            "error":       "groq SDK not installed; run `pip install groq`",
            "verdict":     "HOLD",
            "confidence":  0,
            "headline":    "Synthesis unavailable",
            "reasoning":   "",
            "risks":       ["Groq SDK missing"],
            "actions":     ["Install groq package"],
            "model":       model,
        }

    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        return {
            "success":     False,
            "error":       "GROQ_API_KEY not in environment",
            "verdict":     "HOLD",
            "confidence":  0,
            "headline":    "Synthesis unavailable",
            "reasoning":   "",
            "risks":       ["Groq API key missing from env"],
            "actions":     ["Set GROQ_API_KEY in .env"],
            "model":       model,
        }

    user_msg = _build_user_message(decision_type, query, deliberation)

    try:
        client = Groq(api_key=key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=TOP_P_DEFAULT,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or ""
        logger.info("Groq synthesis returned %d chars", len(raw))
    except Exception as exc:
        logger.exception("Groq API call failed")
        return {
            "success":     False,
            "error":       f"Groq API error: {exc}",
            "verdict":     "HOLD",
            "confidence":  0,
            "headline":    "Synthesis failed",
            "reasoning":   "",
            "risks":       [f"Groq API unreachable: {exc}"],
            "actions":     ["Check network and GROQ_API_KEY"],
            "model":       model,
        }

    # Parse and validate
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Groq returned non-JSON: %s", raw[:200])
        return {
            "success":     False,
            "error":       f"Non-JSON response: {exc}",
            "verdict":     "HOLD",
            "confidence":  0,
            "headline":    "Synthesis parse error",
            "reasoning":   raw[:400],
            "risks":       ["LLM returned malformed JSON"],
            "actions":     ["Retry with simpler query"],
            "model":       model,
        }

    validation_error = _validate_synthesis(payload)
    if validation_error:
        logger.warning("Validation failed: %s — payload=%s", validation_error, payload)
        # Still return what we got, but flag it
        return {
            "success":     False,
            "error":       f"Schema validation failed: {validation_error}",
            "verdict":     payload.get("verdict", "HOLD") if payload.get("verdict") in VALID_VERDICTS else "HOLD",
            "confidence":  int(payload.get("confidence", 0)) if isinstance(payload.get("confidence"), (int, float)) else 0,
            "headline":    str(payload.get("headline", "Validation failed")),
            "reasoning":   str(payload.get("reasoning", "")),
            "risks":       list(payload.get("risks", ["Schema validation failed"])),
            "actions":     list(payload.get("actions", ["Review output"])),
            "model":       model,
        }

    # Success
    return {
        "success":     True,
        "error":       "",
        "verdict":     payload["verdict"],
        "confidence":  int(payload["confidence"]),
        "headline":    payload["headline"],
        "reasoning":   payload["reasoning"],
        "risks":       payload["risks"],
        "actions":     payload["actions"],
        "model":       model,
    }
