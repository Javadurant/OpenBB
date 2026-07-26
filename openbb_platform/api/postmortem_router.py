# api/postmortem_router.py
"""
Trade postmortem generator.

POST /api/postmortem/generate

Two phases:

  1. Mechanical pre-classification — pure function, no LLM. Determines
     `category` (TRUE_POSITIVE / FALSE_POSITIVE / BREAK_EVEN), `pnl_pct`,
     `hit_target`, `hit_stop`. These facts are derived solely from the
     numeric inputs and never come from the LLM.

  2. Narrative synthesis — Groq (llama-3.3-70b-versatile, the existing
     project default) writes structured `what_worked` / `what_failed` /
     `lessons_learned` arrays plus a one-paragraph `synthesis`. The LLM
     is given the pre-classified facts so its commentary cannot
     contradict the math.

If GROQ_API_KEY is not configured (or the call fails), fall back to a
deterministic heuristic that produces short, factual strings — never
fabricated commentary. Per CLAUDE.md ground rule: "When a commercial
source isn't wired, return null + a provider_required marker."

Methodology source: SKILL_Signal_Postmortem.md. The full skill defines
four categories (TRUE_POSITIVE, FALSE_POSITIVE, MISSED_OPPORTUNITY,
REGIME_MISMATCH); the latter two require additional inputs (alternate
universes, regime snapshots) that aren't available at trade-close time,
so v1 ships with the three single-trade categories only.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("postmortem")
router = APIRouter(prefix="/api/postmortem", tags=["postmortem"])

Category = Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "BREAK_EVEN"]
Direction = Literal["long", "short"]

BREAK_EVEN_PCT_TOLERANCE = 0.5    # |pnl_pct| <= 0.5% → BREAK_EVEN
HIT_PRICE_TOLERANCE_PCT  = 1.0    # |exit - target/stop| / target/stop <= 1% → "hit"


# ── Pydantic I/O ──────────────────────────────────────────────────────────
class PostmortemRequest(BaseModel):
    symbol:          str
    direction:       Direction
    thesis:          str
    entry_price:     float
    exit_price:      float
    stop_price:      float | None = None
    target_price:    float | None = None
    size:            float | None = None
    days_held:       int | None   = None
    user_postmortem: str | None   = None


class PostmortemResponse(BaseModel):
    status:           str = "ok"
    category:         Category
    hit_target:       bool
    hit_stop:         bool
    pnl_pct:          float
    what_worked:      list[str]
    what_failed:      list[str]
    lessons_learned: list[str]
    synthesis:        str
    ai_powered:       bool
    user_postmortem: str | None = None


# ── Pure mechanical classification ────────────────────────────────────────
def classify(req: PostmortemRequest) -> dict[str, Any]:
    """
    Direction-adjusted P&L and hit detection.
    Pure function — given identical inputs, always returns identical output.
    """
    if req.entry_price <= 0:
        raise ValueError("entry_price must be > 0")

    direction_mult = 1.0 if req.direction == "long" else -1.0
    pnl_pct = ((req.exit_price - req.entry_price) / req.entry_price) * 100.0 * direction_mult

    if abs(pnl_pct) <= BREAK_EVEN_PCT_TOLERANCE:
        category: Category = "BREAK_EVEN"
    elif pnl_pct > 0:
        category = "TRUE_POSITIVE"
    else:
        category = "FALSE_POSITIVE"

    hit_target = False
    if req.target_price is not None and req.target_price > 0:
        diff_pct = abs(req.exit_price - req.target_price) / req.target_price * 100.0
        hit_target = diff_pct <= HIT_PRICE_TOLERANCE_PCT

    hit_stop = False
    if req.stop_price is not None and req.stop_price > 0:
        diff_pct = abs(req.exit_price - req.stop_price) / req.stop_price * 100.0
        hit_stop = diff_pct <= HIT_PRICE_TOLERANCE_PCT

    return {
        "category":   category,
        "pnl_pct":    round(pnl_pct, 4),
        "hit_target": hit_target,
        "hit_stop":   hit_stop,
    }


# ── Heuristic fallback (no LLM, no fabrication) ──────────────────────────
def heuristic_narrative(req: PostmortemRequest, facts: dict[str, Any]) -> dict[str, list[str] | str]:
    """
    Deterministic strings derived from the numeric facts. Never invents
    commentary about cause, market regime, or timing.
    """
    cat = facts["category"]
    pnl = facts["pnl_pct"]
    what_worked: list[str] = []
    what_failed: list[str] = []
    lessons: list[str]     = []

    if cat == "TRUE_POSITIVE":
        what_worked.append(f"Direction-adjusted P&L of {pnl:+.2f}% confirms the {req.direction} thesis paid out.")
        if facts["hit_target"]:
            what_worked.append("Exit landed within 1% of the pre-defined target — the plan was followed.")
        else:
            what_failed.append("Closed before reaching the pre-defined target — review whether the exit was discretionary.")
    elif cat == "FALSE_POSITIVE":
        what_failed.append(f"Direction-adjusted P&L of {pnl:+.2f}% means the {req.direction} thesis did not play out.")
        if facts["hit_stop"]:
            what_worked.append("Stop was honored within 1% — risk limit was respected.")
        else:
            what_failed.append("Closed without reaching the pre-defined stop — review whether the exit was discretionary.")
    else:  # BREAK_EVEN
        what_worked.append(f"P&L of {pnl:+.2f}% within break-even band — capital preserved.")
        what_failed.append("No edge realized; thesis neither confirmed nor invalidated by price.")

    if req.days_held is not None:
        lessons.append(f"Held {req.days_held} day(s) — log this against your average holding-period for the strategy.")
    if req.target_price is None:
        lessons.append("No target was set on entry — define one upfront to enable mechanical exit decisions.")
    if req.stop_price is None:
        lessons.append("No stop was set on entry — define one upfront to bound downside.")

    synthesis = (
        f"{req.symbol} {req.direction} closed at {pnl:+.2f}% ({cat}). "
        f"{'Plan followed.' if (cat == 'TRUE_POSITIVE' and facts['hit_target']) or (cat == 'FALSE_POSITIVE' and facts['hit_stop']) else 'Discretionary exit — review against plan.'}"
    )

    return {
        "what_worked":     what_worked,
        "what_failed":     what_failed,
        "lessons_learned": lessons,
        "synthesis":       synthesis,
    }


# ── LLM narrative via Groq ────────────────────────────────────────────────
_PROMPT = """You are a disciplined trading-postmortem analyst. Produce a structured
review of a closed trade. The mechanical facts (category, pnl_pct, hit_target,
hit_stop) are pre-computed and authoritative — DO NOT recompute or contradict
them. Comment only on what the trader's thesis got right or wrong, given those
facts.

Trade:
  Symbol:        {symbol}
  Direction:     {direction}
  Entry price:   {entry_price}
  Exit price:    {exit_price}
  Target price:  {target_price}
  Stop price:    {stop_price}
  Size:          {size}
  Days held:     {days_held}

Pre-classified facts (authoritative):
  Category:      {category}
  P&L pct:       {pnl_pct:+.2f}%
  Hit target:    {hit_target}
  Hit stop:      {hit_stop}

Original thesis (verbatim):
  \"\"\"{thesis}\"\"\"

Trader's own postmortem note (may be empty):
  \"\"\"{user_postmortem}\"\"\"

Return ONLY valid JSON, no prose, no markdown fences. Schema:
{{
  "what_worked":     ["short bullet", ...],   // 1-4 items, each <= 22 words
  "what_failed":     ["short bullet", ...],   // 1-4 items, each <= 22 words
  "lessons_learned": ["short bullet", ...],   // 1-3 items, each <= 22 words
  "synthesis":       "single paragraph, 2-4 sentences"
}}

Ground rules:
- Speak only to what the supplied thesis text and pre-classified facts justify.
- Do NOT invent indicators, regimes, or news catalysts that aren't in the inputs.
- If the trader's thesis is vague, say so in lessons_learned.
- Each array must contain at least one item. Use empty arrays only if truly nothing applies, but prefer one honest item over none.
"""


def _strip_code_fence(text: str) -> str:
    """Some LLM outputs wrap JSON in ```json ... ``` — strip if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def llm_narrative(req: PostmortemRequest, facts: dict[str, Any]) -> dict[str, list[str] | str] | None:
    """
    Returns LLM-authored narrative or None if Groq is unavailable / fails.
    Caller falls back to heuristic_narrative on None.
    """
    try:
        from env_config import cfg
        if not cfg.GROQ_API_KEY:
            return None
    except Exception as e:
        logger.warning("env_config import failed in postmortem: %s", e)
        return None

    try:
        from data_clients import groq_client
        client = groq_client()
        prompt = _PROMPT.format(
            symbol=req.symbol,
            direction=req.direction,
            entry_price=req.entry_price,
            exit_price=req.exit_price,
            target_price=req.target_price if req.target_price is not None else "(not set)",
            stop_price=req.stop_price if req.stop_price is not None else "(not set)",
            size=req.size if req.size is not None else "(not specified)",
            days_held=req.days_held if req.days_held is not None else "(not specified)",
            category=facts["category"],
            pnl_pct=facts["pnl_pct"],
            hit_target=facts["hit_target"],
            hit_stop=facts["hit_stop"],
            thesis=req.thesis.strip() or "(no thesis recorded)",
            user_postmortem=(req.user_postmortem or "").strip() or "(none)",
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        parsed = json.loads(_strip_code_fence(raw))
    except Exception as e:
        logger.warning("Groq postmortem failed for %s: %s", req.symbol, e)
        return None

    def _strs(v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    out: dict[str, list[str] | str] = {
        "what_worked":     _strs(parsed.get("what_worked")),
        "what_failed":     _strs(parsed.get("what_failed")),
        "lessons_learned": _strs(parsed.get("lessons_learned")),
        "synthesis":       str(parsed.get("synthesis", "")).strip(),
    }
    if not out["synthesis"]:
        return None
    return out


# ── Endpoint ──────────────────────────────────────────────────────────────
@router.post("/generate", response_model=PostmortemResponse)
def generate(req: PostmortemRequest) -> PostmortemResponse:
    try:
        facts = classify(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("classify failed")
        raise HTTPException(status_code=500, detail=str(e))

    narrative = llm_narrative(req, facts)
    ai_powered = narrative is not None
    if narrative is None:
        narrative = heuristic_narrative(req, facts)

    return PostmortemResponse(
        status="ok",
        category=facts["category"],
        hit_target=facts["hit_target"],
        hit_stop=facts["hit_stop"],
        pnl_pct=facts["pnl_pct"],
        what_worked=narrative["what_worked"],            # type: ignore[arg-type]
        what_failed=narrative["what_failed"],            # type: ignore[arg-type]
        lessons_learned=narrative["lessons_learned"],    # type: ignore[arg-type]
        synthesis=narrative["synthesis"],                # type: ignore[arg-type]
        ai_powered=ai_powered,
        user_postmortem=req.user_postmortem,
    )
