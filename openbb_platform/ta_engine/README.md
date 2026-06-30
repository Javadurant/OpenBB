# ta_engine — rule-gated Elliott Wave engine (clean-room)

A pure-stdlib, I/O-free detection engine that operates on ZigZag pivots. Built to
address the open Elliott defects from `AUDIT-elliott-harmonic-2026-06-27.md`
(E1 window myopia, E2 mis-encoded Rule 2, E3 no diagonal handling, E4 no
invalidation / no alternates).

## Source of truth

Every rule and ratio is sourced to the user's verified reference document
**"ELLIOTT WAVE VERIFIED REFERENCE"** → Frost & Prechter, *Elliott Wave
Principle* (10th Ed.), Ch.2 pp.21–90. No rule or ratio appears here that is not
in that document. Rule citations `[PF] p.21` are reproduced in `elliott.py`.

## What it does

`analyze(swings) -> ElliottAnalysis`

- `swings`: list of `(bar_index, price)` tuples (exactly `compute_zigzag`'s output)
  or `Pivot` objects.
- Slides a **6-pivot window** (start-W1 … end-W5) across the *entire* series — so
  an impulse that completed earlier, and Wave 5 itself, are in scope **(fixes E1)**.
- Each window is gated by `classify()` → `classify_impulse()`:
  - **SHAPE** — must alternate like a 5-wave impulse; W3 must exceed the W1 extreme.
  - **RULE_1** — Wave 2 never retraces ≥100% of Wave 1.
  - **RULE_2** — Wave 3 never the shortest of W1/W3/W5 **by length** (price
    distance, not endpoint price) **(fixes E2)**.
  - **RULE_3** — Wave 4 never enters Wave 1 territory; the **diagonal exception**
    re-reads an overlap-only failure as a contracting-wedge `DIAGONAL` **(fixes E3)**.
- Returns ranked valid counts: `preferred` (most recent) + `alternates`, each with
  `direction`, `invalidation` (Wave 1 origin), `failed_rules`, `notes`, and the
  window `pivots` **(fixes E4)**.

Rejected windows are not silently dropped at the rule layer — `classify_impulse`
returns the exact `failed_rules` so a debug view can show *why* a count was rejected.

## Tests

`./.venv/bin/python -m pytest ta_engine -q` → 14 tests, all rule/shape/diagonal/
scan behaviors, TDD (test-first). Run from `openbb_platform/`.

## Covered vs. NOT yet covered (honest scope)

Covered: impulse detection with all 3 absolute rules + shape gate, contracting
diagonal exception, per-count invalidation, preferred/alternate ranking, full-
series scan, rule-failure logging.

**Not yet implemented** (documented for the next slice, not silently missing):
- Corrective classification: zigzag / regular-expanded-running flat / triangle /
  WXY / WXYXZ (reference Part 3 ratios are ready to encode).
- Leading-vs-ending diagonal sub-typing (needs positional context from the scan).
- Sub-wave internal structure (5-3-5 etc.).
- Guideline-fit confidence score (current ranking is recency only).
- RSI/MACD divergence evidence at Wave 5; Fibonacci-relationship reporting.

## Wiring into the app (next step — additive, not yet applied)

The engine is standalone and committed in isolation. To surface it without
touching the legacy `analyse_elliott_waves` (zero-regression posture):

```python
# pages/ai_trading_agent.py (app root = openbb_platform, so ta_engine is importable)
from ta_engine.elliott import analyze as elliott_rule_analyze

swings = compute_zigzag(df["close"])          # existing call
ew = elliott_rule_analyze(swings)             # new rule-gated counts
# expose ew.preferred / ew.alternates additively via api/symbol_router.py,
# preferring this over the legacy heuristic in the UI once shadow-tested.
```

This is an outward-facing API change and is intentionally left for explicit
sign-off before editing `symbol_router.py`.
