"""
engine/council_stream.py

QuantEdge — Council STREAMING Layer (Phase D, May 20 2026)
Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH

WHAT THIS ADDS:
  The existing /council/synthesize endpoint returns the full verdict in one
  blocking HTTP response. This module streams the deliberation token-by-token
  over a WebSocket so the UI can show each advisor "thinking" in real time,
  then the final synthesis verdict assembling live.

ARCHITECTURE:
  stream_council() is an async generator that yields structured event dicts:

    {"type": "session_start", "advisors": [...], "decision_type", "query"}
    {"type": "advisor_start", "advisor", "lens"}
    {"type": "advisor_token", "advisor", "text"}          (many)
    {"type": "advisor_done",  "advisor", "stance", "text"}
    ... (repeated per advisor) ...
    {"type": "synthesis_start"}
    {"type": "synthesis_token", "text"}                    (many)
    {"type": "synthesis_done", "verdict", "confidence", "headline",
                               "reasoning", "risks", "actions"}
    {"type": "session_done"}
    {"type": "error", "stage", "message"}                  (on any failure)

  Each advisor analyses the SAME deliberation data through their distinct lens
  (Contrarian = risk, First Principles = assumptions, etc.). Their reasoning is
  free-text and streamed; they end with "STANCE: <BULLISH|BEARISH|CAUTION|NEUTRAL>"
  which we parse for the per-advisor badge.

  Synthesis uses JSON mode so the final verdict is parseable; tokens still stream
  for the "assembling verdict" animation, but only the complete JSON is parsed.

INTEGRITY GUARDS:
  - Advisor temperature 0.3 (some voice variety); synthesis pinned to 0.2.
  - Per-advisor token cap prevents runaway cost.
  - No invented data — prompts instruct advisors to use only provided values.
  - Every failure path yields a structured {"type":"error"} event, never throws
    into the WebSocket handler (which would close the socket abruptly).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    from groq import AsyncGroq  # type: ignore
    ASYNC_GROQ_AVAILABLE = True
except ImportError:  # pragma: no cover
    AsyncGroq = None  # type: ignore
    ASYNC_GROQ_AVAILABLE = False

logger = logging.getLogger("QuantEdge.CouncilStream")

# ── Model + sampling ──────────────────────────────────────────────────
GROQ_MODEL: str               = "llama-3.3-70b-versatile"
ADVISOR_TEMPERATURE: float    = 0.3
ADVISOR_MAX_TOKENS: int       = 400
SYNTHESIS_TEMPERATURE: float  = 0.2
SYNTHESIS_MAX_TOKENS: int     = 1024
TOP_P: float                  = 0.9

VALID_VERDICTS: tuple = ("BUY", "HOLD", "SELL")
VALID_STANCES: tuple  = ("BULLISH", "BEARISH", "CAUTION", "NEUTRAL")

# ── Per-advisor lens: the distinct thinking style each one applies ──────
ADVISOR_LENS: Dict[str, str] = {
    "CONTRARIAN":
        "You are the CONTRARIAN. Your job is to find what could go wrong. "
        "Scrutinise exposure, drawdown risk, crowded positioning, and downside "
        "scenarios. Be skeptical of the obvious bull case. Ask 'what is everyone missing?'",
    "FIRST_PRINCIPLES":
        "You are FIRST PRINCIPLES. Strip away assumptions and narrative. "
        "Reason only from what the data literally shows. Ask 'what do we actually "
        "know for certain, and what is just a story we are telling ourselves?'",
    "EXPANSIONIST":
        "You are the EXPANSIONIST. Find the asymmetric upside. If the case is "
        "strong, ask 'what if we go bigger?' Identify the bull scenario and the "
        "catalyst that unlocks it. Be ambitious but grounded in the data.",
    "OUTSIDER":
        "You are the OUTSIDER. You have no prior context and no position to defend. "
        "Read the plain signal in the data. Catch the curse of knowledge — name "
        "complexity that experts have talked themselves into but that isn't really there.",
    "EXECUTOR":
        "You are the EXECUTOR. You care about the actionable path. Given the data, "
        "what is the single fastest, cleanest action — entry, exit, size, or wait? "
        "Translate analysis into a concrete next step with risk controls.",
}

# ── System prompt for the per-advisor streaming pass ────────────────────
_ADVISOR_SYSTEM = (
    "You are one advisor on the SENTRIQ trading Council. You will be given the "
    "decision context and the data captured for this deliberation.\n"
    "Analyse it ONLY through your assigned lens. Be concise — 3 to 5 sentences of "
    "sharp reasoning, not an essay. Cite specific numbers from the data when present.\n"
    "Never invent data. If the data is thin, say so plainly.\n"
    "End your response with EXACTLY one line in this format:\n"
    "STANCE: BULLISH    (or BEARISH, CAUTION, NEUTRAL)\n"
)

# ── Synthesis system prompt (JSON mode) ─────────────────────────────────
_SYNTHESIS_SYSTEM = (
    "You are the Council Synthesizer for SENTRIQ. You receive the streamed "
    "opinions of all advisors plus the underlying data. Synthesise them into ONE "
    "actionable verdict. Output STRICT JSON only — no markdown, no preamble.\n\n"
    "Schema (all fields required):\n"
    "{\n"
    '  "verdict": "BUY" | "HOLD" | "SELL",\n'
    '  "confidence": <integer 0-100>,\n'
    '  "headline": "<one line, under 100 chars>",\n'
    '  "reasoning": "<2-3 paragraphs tying the conclusion to advisor opinions and data>",\n'
    '  "risks": ["<concrete risk>", ...],\n'
    '  "actions": ["<concrete next step>", ...]\n'
    "}\n\n"
    "RULES:\n"
    "  1. Weigh the advisor stances. Genuine disagreement lowers confidence.\n"
    "  2. HOLD is the default when signals are mixed or data is thin.\n"
    "  3. BUY/SELL require confidence >= 60.\n"
    "  4. risks and actions each need at least one item.\n"
    "  5. Cite specific advisor opinions and data values. Never invent data.\n"
)


def _format_deliberation(deliberation: List[Dict[str, Any]]) -> str:
    """Render the per-advisor tool data into a compact text block for prompts."""
    if not deliberation:
        return "(no tool data was captured for this deliberation)"
    lines: List[str] = []
    for entry in deliberation:
        advisor = entry.get("advisor", "?")
        tools = entry.get("tools", []) or entry.get("tool_results", [])
        lines.append(f"## {advisor}")
        if isinstance(tools, list) and tools:
            for t in tools:
                if isinstance(t, dict):
                    name = t.get("tool", "?")
                    ok = t.get("success", True)
                    data = t.get("data")
                    if ok and isinstance(data, dict):
                        compact = ", ".join(f"{k}={v}" for k, v in list(data.items())[:8])
                        lines.append(f"  - {name}: {compact}")
                    elif ok:
                        lines.append(f"  - {name}: ok")
                    else:
                        lines.append(f"  - {name}: FAILED ({t.get('error', 'unknown')})")
        else:
            lines.append("  (no tools invoked)")
    return "\n".join(lines)


def _parse_stance(text: str) -> str:
    """Extract the STANCE: line an advisor emits. Defaults to NEUTRAL."""
    if not text:
        return "NEUTRAL"
    for line in reversed(text.strip().splitlines()):
        upper = line.strip().upper()
        if "STANCE:" in upper:
            for stance in VALID_STANCES:
                if stance in upper:
                    return stance
    # Fallback heuristic if the model forgot the STANCE line
    upper_all = text.upper()
    for stance in VALID_STANCES:
        if stance in upper_all:
            return stance
    return "NEUTRAL"


def _validate_verdict(payload: Dict[str, Any]) -> Optional[str]:
    """Return an error string if the synthesis payload is malformed, else None."""
    if not isinstance(payload, dict):
        return "synthesis is not a JSON object"
    v = payload.get("verdict")
    if v not in VALID_VERDICTS:
        return f"invalid verdict '{v}'"
    c = payload.get("confidence")
    if not isinstance(c, (int, float)) or not (0 <= c <= 100):
        return f"invalid confidence '{c}'"
    for field in ("headline", "reasoning"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            return f"missing/empty field '{field}'"
    for field in ("risks", "actions"):
        arr = payload.get(field)
        if not isinstance(arr, list) or len(arr) == 0:
            return f"field '{field}' must be a non-empty list"
    return None


async def stream_council(
    decision_type: str,
    query: str,
    deliberation: List[Dict[str, Any]],
    advisors: List[str],
    *,
    api_key: Optional[str] = None,
    model: str = GROQ_MODEL,
    market_context: Optional[str] = None,  # <- NEW [Council-enrichment]: live symbol data, fetched once, shared
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async generator that streams the full Council deliberation as event dicts.

    Args:
        decision_type: e.g. 'RISK_CHECK', 'OPPORTUNITY_SCAN'
        query:         user context (ticker, scenario)
        deliberation:  per-advisor tool data (from /council/execute)
        advisors:      ordered advisor names to stream
        api_key:       optional Groq key override
        model:         Groq model name

    Yields:
        Structured event dicts (see module docstring).
    """
    if not ASYNC_GROQ_AVAILABLE:
        yield {"type": "error", "stage": "init", "message": "groq SDK not installed"}
        return

    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        yield {"type": "error", "stage": "init", "message": "GROQ_API_KEY not in environment"}
        return

    client = AsyncGroq(api_key=key)
    data_block = _format_deliberation(deliberation)
    # <- NEW [Council-enrichment]: shared live market data (all advisors + synthesis see the same real values)
    market_block = (
        f"\n\nLIVE MARKET DATA (real values - anchor your analysis to these; never invent numbers):\n{market_context}"
        if market_context else ""
    )

    yield {
        "type": "session_start",
        "decision_type": decision_type,
        "query": query,
        "advisors": advisors,
    }

    # <- NEW [multi-model]: assign each advisor a distinct provider/model from the curated
    #    working pool (groq/sambanova/fireworks/ollama_cloud). Disable via COUNCIL_MULTIMODEL=0.
    #    Synthesis stays on the proven Groq JSON path. Degrades to Groq-for-all on any failure.
    _aip = None
    _assignments: List[tuple] = []
    if os.getenv("COUNCIL_MULTIMODEL", "1").strip().lower() not in ("0", "false", "no", ""):
        try:
            import ai_providers as _aip  # type: ignore
            _assignments = _aip.council_model_assignments(len(advisors))
        except Exception as exc:  # noqa: BLE001 - fall back to single-model Groq
            logger.warning("multi-model council unavailable (%s); using Groq for all advisors", exc)
            _aip = None
            _assignments = []

    advisor_opinions: List[Dict[str, str]] = []

    # ── Phase 1: each advisor deliberates, streaming token by token ──────
    for _idx, advisor in enumerate(advisors):
        lens = ADVISOR_LENS.get(advisor, f"You are {advisor}.")
        yield {"type": "advisor_start", "advisor": advisor, "lens": lens}

        user_msg = (
            f"{lens}\n\n"
            f"DECISION TYPE: {decision_type}\n"
            f"QUERY: {query}\n\n"
            f"DATA CAPTURED FOR THIS DELIBERATION:\n{data_block}{market_block}\n\n"
            f"Give your analysis through your lens, then the STANCE line."
        )

        _msgs = [
            {"role": "system", "content": _ADVISOR_SYSTEM},
            {"role": "user",   "content": user_msg},
        ]

        full_text = ""
        used_provider = "groq"                                                      # <- NEW [multi-model]
        used_model = model                                                          # <- NEW [multi-model]
        prov, mdl = (_assignments[_idx] if _idx < len(_assignments) else (None, None))  # <- NEW [multi-model]

        # 1) Try the advisor's assigned provider via the multi-provider streaming layer.  # <- NEW
        if _aip is not None and prov:
            try:
                async for delta in _aip.achat_stream(
                    _msgs, provider=prov, model=mdl,
                    temperature=ADVISOR_TEMPERATURE, max_tokens=ADVISOR_MAX_TOKENS,
                ):
                    if delta:
                        full_text += delta
                        yield {"type": "advisor_token", "advisor": advisor, "text": delta}
                if full_text.strip():
                    used_provider, used_model = prov, mdl
            except Exception as exc:  # noqa: BLE001 - degrade to Groq below
                logger.warning("advisor %s provider %s stream failed (%s); falling back to Groq",
                               advisor, prov, exc)
                if not full_text.strip():
                    full_text = ""

        # 2) Fallback / default: the proven Groq streaming path (runs only if nothing emitted).  # <- NEW
        if not full_text.strip():
            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=_msgs,
                    temperature=ADVISOR_TEMPERATURE,
                    max_tokens=ADVISOR_MAX_TOKENS,
                    top_p=TOP_P,
                    stream=True,
                )
                async for chunk in stream:
                    delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                    if delta:
                        full_text += delta
                        yield {"type": "advisor_token", "advisor": advisor, "text": delta}
                used_provider, used_model = "groq", model
            except Exception as exc:  # noqa: BLE001 - stream must degrade gracefully
                logger.exception("advisor stream failed for %s", advisor)
                yield {"type": "error", "stage": f"advisor:{advisor}", "message": str(exc)}
                continue

        stance = _parse_stance(full_text)
        advisor_opinions.append({"advisor": advisor, "stance": stance, "text": full_text,
                                 "provider": used_provider, "model": used_model})    # <- NEW: provenance
        yield {"type": "advisor_done", "advisor": advisor, "stance": stance,
               "text": full_text, "provider": used_provider, "model": used_model}    # <- NEW: provenance

    # ── Phase 2: synthesis (JSON mode), tokens streamed for the animation ─
    yield {"type": "synthesis_start"}

    opinions_block = "\n\n".join(
        f"### {o['advisor']} (stance: {o['stance']})\n{o['text']}" for o in advisor_opinions
    ) or "(no advisor opinions were produced)"

    synth_user = (
        f"DECISION TYPE: {decision_type}\n"
        f"QUERY: {query}\n\n"
        f"UNDERLYING DATA:\n{data_block}{market_block}\n\n"
        f"ADVISOR OPINIONS:\n{opinions_block}\n\n"
        f"Synthesise into the strict-JSON verdict now."
    )

    raw = ""
    try:
        synth_stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYNTHESIS_SYSTEM},
                {"role": "user",   "content": synth_user},
            ],
            temperature=SYNTHESIS_TEMPERATURE,
            max_tokens=SYNTHESIS_MAX_TOKENS,
            top_p=TOP_P,
            stream=True,
            response_format={"type": "json_object"},
        )
        async for chunk in synth_stream:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                raw += delta
                yield {"type": "synthesis_token", "text": delta}
    except Exception as exc:  # noqa: BLE001
        logger.exception("synthesis stream failed")
        yield {"type": "error", "stage": "synthesis", "message": str(exc)}
        yield {"type": "session_done"}
        return

    # Parse + validate the assembled JSON
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("synthesis non-JSON: %s", raw[:200])
        yield {"type": "error", "stage": "synthesis_parse", "message": f"non-JSON: {exc}"}
        yield {"type": "session_done"}
        return

    err = _validate_verdict(payload)
    if err:
        yield {"type": "error", "stage": "synthesis_validate", "message": err}
        yield {"type": "session_done"}
        return

    yield {
        "type":       "synthesis_done",
        "verdict":    payload["verdict"],
        "confidence": int(payload["confidence"]),
        "headline":   payload["headline"],
        "reasoning":  payload["reasoning"],
        "risks":      payload["risks"],
        "actions":    payload["actions"],
        "model":      model,
        "stances":    {o["advisor"]: o["stance"] for o in advisor_opinions},
        "advisor_models": {o["advisor"]: o.get("model") for o in advisor_opinions},  # <- NEW: multi-model provenance
    }
    yield {"type": "session_done"}
