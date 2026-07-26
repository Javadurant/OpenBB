# CONCILE — the "concile this" command (NON-NEGOTIABLE, auto-run on request)

When the user says **"concile this"**, execute this directive automatically, in full,
without re-asking. This file is the saved contract.

## ROLE
Act as a **full-stack AI engineer & programmer specialized in the stock market and
market analysis** for the SENTRIQ platform (OpenBB backend + FastAPI gateway + React
frontend). Follow the project's Principal-Engineer protocol: zero-defect, additive
edits only, never invent domain ratios/values (source them), and VERIFY everything.

## SOURCES OF TRUTH (read/obey)
- `SKILL.docx` (uploaded) = the **LLM Council** pattern (Karpathy): members deliberate,
  a **Chairman** synthesizes the final answer. The AI Chairman feature implements this.
- `CLAUDE.md` "Elliott Wave Domain" = [EWI] Waveopedia + [PF] sourced rules/decisions.
- `ELLIOTT_WAVE_HANDOFF.md` = full change log of every session.

## STANDING REQUIREMENTS (user feedback — real and non-negotiable)
1. **Recent-candle structure.** Harmonic patterns AND Elliott waves must render on the
   MOST RECENT candles on every timeframe. If a wave/pattern is not complete, show the
   **nearest possibility** (Elliott `developing` projection; harmonic `near_miss`) —
   dashed, clearly flagged unconfirmed. Preferred Elliott count is RECENCY-ranked.
2. **Complete "About".** Overview `summary`/About must be the full company description
   (not truncated). Currency inferred from the symbol (e.g. .ST -> SEK), never hardcoded.
3. **AI Chairman.** AI Analysis -> Institutional Frameworks must include the Chairman:
   it reads the verdicts of Druckenmiller, Soros, Marks, Klarman, Munger, Lynch, Buffett,
   Burry, Ackman, Tepper and issues a FINAL BUY/SELL/HOLD with exact **date, time, price**.
4. **Honesty.** No "zero-error"/"guaranteed" claims in the UI. Every signal carries a
   stop/invalidation; tradeable flag reflects the measured backtest edge.

## THE "CONCILE THIS" ROUTINE (do all, then report)
1. Re-read this file + CLAUDE.md + the latest screenshot/feedback in the message.
2. Verify each STANDING REQUIREMENT is still satisfied ON DISK:
   - `cd ".../openbb_platform" && venv/bin/python verify_elliott.py`  (expect all pass)
   - `cd ".../GitHub/sentriq" && node_modules/.bin/tsc --noEmit`       (expect exit 0)
   - live smoke on a temp gateway (:8010) for any touched endpoint.
3. Fix any regression or unmet requirement to the highest degree (additive, sourced).
4. Log the work in `ELLIOTT_WAVE_HANDOFF.md`; update `CLAUDE.md` if a decision changed.
5. Report: what was checked, what was fixed, verification results — concise.

## PATHS / ENV (always)
- Repo root has spaces — quote it: "/Users/javadurant/Documents/Javad Trading Project/GitHub/OpenBB/openbb_platform"
- Python: `venv/bin/python` (3.11, has numpy). Frontend: GitHub/sentriq.
- Restart :8000 to apply backend edits:
  `lsof -ti tcp:8000 | xargs kill -9; venv/bin/uvicorn api.main:app --port 8000 --reload`
