"""
api/help_router.py  — <- NEW [HELP/ROUTER]: endpoints for the Smart Help system.

  GET  /api/help/topics                         -> guides grouped by category
  GET  /api/help/faq                            -> FAQ list
  GET  /api/help/article/{id}                   -> one article
  GET  /api/help/search?q=&limit=               -> KB + FAQ search hits
  POST /api/help/ask        {question}          -> grounded, cited AI answer (rate-limited)
  POST /api/help/feedback   {target_type,...}   -> record a star / helpful vote
  GET  /api/help/feedback/{target_type}/{id}    -> aggregate for a target

Security: /ask runs the secure help_agent (gatekeeper + KB grounding + scrubber).
Feedback stores no PII. A small in-process per-IP limiter protects /ask.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Final, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import feedback_store, help_agent, help_kb

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/help", tags=["help"])

# ── Simple in-process per-IP rate limiter for /ask (LLM-backed) ─────────────
_RATE_WINDOW_S: Final = 60.0
_RATE_MAX: Final = 20
_rate_lock: Final = threading.Lock()
_rate_hits: Final[dict[str, list[float]]] = {}


def _rate_ok(client_ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(client_ip, []) if now - t < _RATE_WINDOW_S]
        if len(hits) >= _RATE_MAX:
            _rate_hits[client_ip] = hits
            return False
        hits.append(now)
        _rate_hits[client_ip] = hits
        return True


# ── Request models ──────────────────────────────────────────────────────────
class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=600)


class FeedbackBody(BaseModel):
    target_type: str = Field(..., max_length=20)
    target_id: str = Field(..., max_length=160)
    stars: Optional[int] = Field(None, ge=1, le=5)
    helpful: Optional[bool] = None


# ── Read endpoints ────────────────────────────────────────────────────────
@router.get("/topics")
def get_topics() -> dict:
    return {"topics": help_kb.topics()}


@router.get("/faq")
def get_faq() -> dict:
    return {"faq": help_kb.faq()}


@router.get("/article/{article_id}")
def get_article(article_id: str) -> dict:
    a = help_kb.article(article_id)
    if a is None:
        raise HTTPException(status_code=404, detail="article not found")
    return a


@router.get("/search")
def get_search(q: str = "", limit: int = 6) -> dict:
    lim = max(1, min(int(limit), 20))
    return {"query": q, "hits": help_kb.search(q, lim)}


# ── AI ask (secure, rate-limited) ───────────────────────────────────────────
@router.post("/ask")
def post_ask(body: AskBody, request: Request) -> dict:
    client_ip = (request.client.host if request.client else "unknown")
    if not _rate_ok(client_ip):
        raise HTTPException(status_code=429, detail="Too many questions — please wait a moment.")
    try:
        result = help_agent.answer(body.question)
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.error("help_router: /ask failed: %s", exc)
        raise HTTPException(status_code=503, detail="Assistant is unavailable right now.")
    return dict(result)


# ── Feedback / ratings (no PII) ─────────────────────────────────────────────
@router.post("/feedback")
def post_feedback(body: FeedbackBody) -> dict:
    try:
        agg = feedback_store.record(
            body.target_type, body.target_id, stars=body.stars, helpful=body.helpful)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OSError:
        raise HTTPException(status_code=503, detail="Could not save your rating.")
    return dict(agg)


@router.get("/feedback/{target_type}/{target_id:path}")
def get_feedback(target_type: str, target_id: str) -> dict:
    return dict(feedback_store.aggregate(target_type, target_id))
