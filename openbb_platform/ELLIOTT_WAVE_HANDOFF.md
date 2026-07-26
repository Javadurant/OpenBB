# Elliott Wave Engine — Handoff & Next Steps

## STATUS (verified this session)
- FILE DEPLOYED: engine/structure/elliott_wave.py (603 lines)
  sha256 = 365298d182e825e9aee65c4c1061307d418b51e26a8d6527b7816afd57f377bb
- py_compile: OK under venv (venv/bin/python, has numpy)
- import: OK -> `from engine.structure import elliott_wave as ew`
- public entry: ew.analyze(high, low, close, labels, *, symbol, timeframe, as_of, min_bars=5, min_swing_pct=None) -> ElliottResult
- sourced constants confirmed: MIN_PIVOT_BARS=5, WAVE_RATIO_TOLERANCE=0.02

## WHAT THIS ENGINE IS
Deterministic 5-3 Elliott Wave detector. Pure functions, no I/O, provider-agnostic
(takes OHLC arrays e.g. from OBBject.to_df()). Dual-verified domain sourcing:
[PF] Frost & Prechter EWP 10th Ed. + [EWI] elliottwave.com Waveopedia. Nothing invented.
- P1 (Wave Principle Discipline): 3 absolute rules are HARD gates, never relaxed.
- P2 (Logical Validation): emits PREFERRED + ALTERNATE count ranked by guidelines satisfied.
- result.chart_label is NEVER blank — reports "Elliott: NO VALID COUNT — {reason}" when no count.

## WHY "Ask SENTRIQ" GAVE CIRCULAR ANSWERS (root cause, fixed by this engine)
The old Elliott answer was the RAG layer paraphrasing ELLIOTT_WAVE_VERIFIED_REFERENCE.docx
("Gemini Chart Analysis Edition" — an LLM vision-prompt, NOT an algorithm). There was no
actual wave computation feeding the chart. Harmonics ARE computed (PRZ shows); Elliott was not.

## NEXT STEPS (do these in Claude Cowork)
1. [TRANSFER] verify_elliott.py still needs to land on disk (self-contained checker:
   import check + 6 logic checks + optional live OpenBB test). It exists in the prior
   session's Claude sandbox only. In Cowork, recreate it directly on disk (Cowork has a
   real filesystem — no chunked base64 needed). Then run:
     venv/bin/python verify_elliott.py            # 6 offline checks
     venv/bin/python verify_elliott.py VOLV-B.ST  # live OpenBB test
2. [WIRE BACKEND] Call ew.analyze(...) from the endpoint that serves the symbol chart
   (the same one that returns the harmonic PRZ). Return result.chart_label + preferred/
   alternate + pivots, each carrying source + as_of.
3. [WIRE FRONTEND] Render result.chart_label UNDER the harmonic PRZ line in the chart
   component (sentriq/src/components/symbol/: OverviewTab.tsx / TechnicalTab.tsx / CandleChart.tsx).
4. [REWIRE ASK] Make "Ask SENTRIQ" cite the COMPUTED preferred/alternate counts instead of
   paraphrasing the .docx.

## OPEN DECISIONS (do NOT invent — your call)
- min_swing_pct threshold value (or leave off / ATR-based / rely on min_bars=5).
- Path A (self-contained pivots) vs Path B (consume engine/structure/swings.py find_pivots
  so harmonic PRZ and Elliott label agree on the SAME pivots — recommended for consistency).
- Diagonals: Rule 3 is strict, no auto-diagonal exception (honest, not stubbed). Later module?

## ENV NOTES (carry into Cowork)
- Repo root has a SPACE — always quote: "/Users/javadurant/Documents/Javad Trading Project/GitHub/OpenBB/openbb_platform"
- Project venv = venv/ (NOT .venv/), Python 3.11.14, has numpy. Use venv/bin/python.
- System python3 is 3.9.6; homebrew python3 is 3.14 — neither may have numpy. Always venv.
- Engine uses `from __future__ import annotations` so list[...]/tuple[...] hints are safe.


## SESSION LOG — 2026-06-04 (Cowork)
- [DONE] Step 1: verify_elliott.py recreated on disk at repo root.
    venv/bin/python verify_elliott.py            -> 22/22 offline checks PASS
    venv/bin/python verify_elliott.py VOLV-B.ST  -> live: 250 bars, 25 pivots,
      computed count FLAT_EXPANDED · Wave C · invalidation 328.7 (preferred+alternate).
    Confirms Elliott is now COMPUTED, not RAG-paraphrased.
- [RESOLVED] Open decision — pivot path = PATH A (Elliott keeps its own high/low
    detect_pivots). Sourced from [EWI] Waveopedia: rules are stated by price
    territory/extremes, not close. swings.py is close-to-close -> unfit for Elliott.
    Future consistency upgrade = Path B+ (shared HIGH/LOW finder), NOT Path B.
- [RESOLVED] Open decision — min_swing_pct = None. [EWI] defines significance by
    DEGREE, not a fixed %, so no value invented. Rely on MIN_PIVOT_BARS=5.
- [DONE] CLAUDE.md: appended "Elliott Wave Domain" section with P1/P2 principles,
    the three absolute rules (with [EWI] citations), corrective taxonomy, and both
    resolved decisions.
- [NOTED, needs human approval before any change] RULE_2 source basis is
    *percentage* movement ([EWI] Motive Waves); engine currently checks arithmetic
    length ([PF]). DOMAIN change — do not alter without sign-off.

## REMAINING NEXT STEPS (unchanged, now unblocked)
2. [WIRE BACKEND] Call ew.analyze(...) from the symbol-chart endpoint (same one
   returning harmonic PRZ) using PATH A pivots + min_swing_pct=None. Return
   chart_label + preferred/alternate + pivots, each carrying source + as_of.
3. [WIRE FRONTEND] Render chart_label under the harmonic PRZ line.
4. [REWIRE ASK] Make "Ask SENTRIQ" cite the COMPUTED preferred/alternate counts.


## SESSION LOG — 2026-06-04 (Cowork) — STEP 2 BACKEND WIRED
- [DONE] Step 2: ew.analyze wired into engine/pipeline.py (ADDITIVE).
    - Imported `from engine.structure import elliott_wave as ew` (graceful None fallback).
    - Added AnalysisPipeline._run_elliott (PATH A pivots, min_swing_pct=None),
      ._elliott_to_dict, ._count_to_dict (JSON-safe; pivots + counts each carry
      source + as_of).
    - In run_deep_analysis loop: computes ew_result per timeframe; report now has
      a top-level "elliott" key and section_1_detection appends the computed
      chart_label. Legacy ElliottEngine + HarmonicEngine calls PRESERVED.
    - VERIFIED: py_compile OK; import OK; live VOLV-B.ST run_pipeline -> success,
      all 5 timeframes, "elliott" block present, 1d => "Elliott: IMPULSE · Wave 5
      (IN_PROGRESS) · invalidation 131.7"; ew_block JSON-serializable; pivots and
      preferred/alternate carry source + as_of.
- [PRE-EXISTING, out of Elliott scope — NOT changed] pipeline calls
    self.harmonics.detect(df) but HarmonicEngine only defines .scan(prices);
    getattr fallback -> harmonic_patterns always []. "Detected 0 patterns".
    Quick win if desired: wire scan() with swings.find_pivots+enforce_alternation.

## REMAINING NEXT STEPS
3. [WIRE FRONTEND] Render results[tf]["elliott"]["chart_label"] under the harmonic
   PRZ line (sentriq/src/components/symbol/: OverviewTab/TechnicalTab/CandleChart).
4. [REWIRE ASK] Make "Ask SENTRIQ" cite results[tf]["elliott"] preferred/alternate
   (count_type, current_wave, guideline_score, invalidation_level) instead of the .docx.


## SESSION LOG — 2026-06-04 (Cowork) — STEPS 3 & 4 (API + FRONTEND + ASK)
ARCHITECTURE FOUND: the React app (GitHub/sentriq) talks to a FastAPI gateway on
:8000 (Vite proxy). The real symbol payload is api/symbol_router.py:technical()
-> response["elliott"] (legacy analyse_elliott_waves: wave_phase/conf_pts).
pipeline.py (step 2) is a separate orchestrator; the FRONTEND reads symbol_router.

- [DONE] API wiring (api/symbol_router.py, ADDITIVE):
    - _computed_elliott_payload(symbol, df): runs ew.analyze on full high/low/close
      (PATH A, min_swing_pct=None), returns JSON-safe chart_label + preferred/
      alternate + pivots (each w/ source + as_of). Never raises.
    - _ew_cite_phrase(block): one-line citation of computed preferred (+alternate).
    - technical(): response["elliott"] now = {legacy fields…, "chart_label",
      "computed": <full block>}. Legacy preserved.
    - ai_narrative() ["Ask"/AI Snapshot]: now cites COMPUTED counts in both the
      Groq prompt and the no-key fallback; legacy phase kept parenthetically.
    - VERIFIED: py_compile OK; _computed_elliott_payload + _ew_cite_phrase exercised
      (IMPULSE Wave 5, alt ZIGZAG; no-count path OK). Engine regression 22/22.

- [DONE] Frontend (GitHub/sentriq, ADDITIVE):
    - src/hooks/useApi.ts: added ElliottComputed/ElliottCount/ElliottPivot/ElliottLeg/
      ElliottRuleCheck types; ElliottWaveAnalysis gains chart_label? + computed?.
    - OverviewTab.tsx: renders computed Elliott label DIRECTLY UNDER the harmonic
      PRZ basis line (uses tech.elliott.chart_label + alternate; daily basis).
    - TechnicalTab.tsx: Elliott Wave card gains a "Computed (EWI rules)" block:
      chart_label, preferred (type/wave/status, guideline score, invalidation),
      alternate, source. Legacy phase/swings/conf preserved.
    - VERIFIED: tsc --noEmit exit 0.

STATUS: Steps 1-4 COMPLETE. Computed Elliott now flows engine -> FastAPI -> React,
renders under the PRZ line, and is what the AI narrative cites (not the .docx).

## OPTIONAL FOLLOW-UPS (not done; your call)
- Harmonic detect/scan gap in engine/pipeline.py (pre-existing; "0 patterns").
- RULE_2 percentage-vs-arithmetic basis (DOMAIN change — needs approval).
- Triangles / running flats / combinations (engine gaps, currently honest).
- Live end-to-end test against a running :8000 gateway (needs the server up + GROQ key).


## SESSION LOG — 2026-06-04 (Cowork) — LIVE TEST + HARMONIC GAP FIX
- [DONE] Live gateway smoke test: user's FastAPI is up on :8000 but was serving
    PRE-EDIT code (no reload). Spun a temp instance on :8010 from current code:
    * GET /api/symbol/AAPL/technical -> elliott now has chart_label
      ("IMPULSE · Wave 5 (IN_PROGRESS) · invalidation 265.3") + computed block
      (preferred IMPULSE, 46 pivots, source+as_of); legacy wave_phase preserved.
    * GET /api/symbol/AAPL/ai-narrative -> Groq cites the COMPUTED count verbatim
      ("...IMPULSE Wave 5 ... satisfied 2 guidelines ... invalidation $265.32.
      This computed wave count..."). Step 4 confirmed end-to-end.
    Temp instance shut down. ACTION FOR USER: restart the :8000 gateway to pick up
    the edits (it is not running with --reload).
- [DONE] Harmonic detect/scan gap (engine/pipeline.py, ADDITIVE):
    Root cause: loop called getattr(self.harmonics,'detect') but HarmonicEngine
    only defines .scan(prices) -> always [] ("0 patterns"). Added
    AnalysisPipeline._detect_harmonics(df): swings.find_pivots + enforce_alternation
    -> scan(prices) -> adapts typed PatternResult into report dicts
    (name/type/points/stop_loss/prz=None). Wired into the loop. Degrades to [].
    VERIFIED: py_compile OK; run_pipeline('AAPL') -> "Detected 11 patterns" (was 0)
    AND elliott.chart_label present. Consumed by pages/harmonics_ui.py (Streamlit).
    NOTE: pipeline does not compute a confluence PRZ (prz=None); that lives in the
    API's compute_prz_confluence. Engine regression verify_elliott.py still 22/22.


## SESSION LOG — 2026-06-05 (Cowork) — CLICKABLE OVERLAYS + RULE_2
- [DONE] Backend geometry (api/symbol_router.py, ADDITIVE):
    * _computed_elliott_payload now takes x_labels + timeframe; legs carry
      chart-aligned start_label/end_label dates so they map onto the candle axis.
    * /technical: passes x_labels=[str(i)[:10]]; elliott shape = {chart_label, computed}.
    * /chart (tf-aware): adds "elliott": {chart_label, computed} (same shape) AND
      "pivot_prices" on each harmonic (X=pivot_dates, Y=pivot_prices) for polylines.
    VERIFIED live (:8010): /chart?tf=daily AAPL -> preferred IMPULSE, 5 legs each
      with date labels + prices (W1 2025-09-10 ... W5), 46 pivots.
- [DONE] Frontend overlays (GitHub/sentriq, ADDITIVE):
    * useApi.ts: ElliottLeg +start_label/end_label; HarmonicPattern +pivot_dates/
      pivot_prices; ChartResp +elliott{chart_label,computed}.
    * CandleChart.tsx: draws the PREFERRED Elliott count as a polyline with
      1-2-3-4-5 / A-B-C markers (createSeriesMarkers, lavender #C9A8FF); draws the
      first FOUND harmonic as an X-A-B-C-D polyline + PRZ band (dir-colored). Both
      gated by showElliott / showHarmonicDraw; wrapped in try/catch (never break chart).
    * OverviewTab.tsx: the harmonic basis line is now a clickable button
      ("▶ show pattern on chart" / "◉ pattern on chart"); a NEW clickable Elliott line
      sits under it ("▶ show waves on chart" / "◉ waves on chart"), tf-aware via
      chart.elliott. Toggles plumb into CandleChart per timeframe.
    * TechnicalTab.tsx: chart now draws the computed wave path (showElliott, daily).
    VERIFIED: tsc --noEmit exit 0 (createSeriesMarkers valid in lightweight-charts 5.2).
- [DONE] RULE_2 percentage basis (engine/structure/elliott_wave.py, human-approved):
    _check_rules RULE_2 gates on percentage movement per [EWI] Motive Waves; arith
    kept in detail. verify_elliott.py -> 26 passed, 0 failed (added L7).
- COPY/UX: CTAs use plain, honest verbs ("show … on chart"); NO "guaranteed"/
    "zero-error" claims in UI — signals are probabilistic, markets carry risk.

## RESTART COMMAND FOR :8000 (VS Code terminal, picks up all edits, enables hot-reload)
    cd "/Users/javadurant/Documents/Javad Trading Project/GitHub/OpenBB/openbb_platform" && \
      lsof -ti tcp:8000 | xargs kill -9 2>/dev/null; \
      venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

## STILL OPEN (need sourcing/approval; not done)
- Triangles (3-3-3-3-3), running flats, combinations (double/triple three) — engine
  gaps; honest "no count" today. Building to "highest degree" needs careful [EWI]/[PF]
  sourcing per pattern. Recommend as the next dedicated work block.
- Harmonic polyline on /technical-only views has no geometry (pivot_prices only on
  /chart); Technical tab shows the top-left harmonic label instead. Fine as-is.


## SESSION LOG — 2026-06-05 (Cowork) — TRIANGLES
- [DONE] Triangle detection (engine/structure/elliott_wave.py, ADDITIVE, [EWI] Triangles):
    * CountType += TRIANGLE_CONTRACTING / TRIANGLE_BARRIER / TRIANGLE_EXPANDING.
    * _build_triangle(six): A-B-C-D-E from 6 pivots. Classified purely by boundary
      geometry — highs vs lows lines converge (contracting), diverge (expanding),
      or one is horizontal (barrier, WAVE_RATIO_TOLERANCE for 'flat'). Clean
      contraction (each subwave smaller) and running-triangle (B exceeds A start)
      add guideline matches. CORRECTIVE_UNCLASSIFIED when not a triangle (never forced).
      targets={'thrust_distance': widest leg} per [EWI] (thrust ~ widest part).
    * Wired into analyze() over 6-pivot windows alongside impulse/corrective.
    * Frontend needs NO change — overlay draws preferred.legs generically (A-E markers).
    VERIFIED: verify_elliott.py -> 31 passed, 0 failed (added L8: contracting +
      expanding classified, 5 legs A-E, trending impulse is NOT a triangle).
      Live :8010 /technical AAPL regression OK (RULE_2 cites EWI percentage basis).
- STILL OPEN (deliberately deferred — would risk false signals if rushed):
    * Running flats (FLAT_RUNNING) — needs [EWI] Flats thresholds fetched & sourced.
    * Combinations (double/triple three, W-X-Y / W-X-Y-X-Z) — compositions linked by
      X waves; require the simpler corrective set first + X-wave detection. Recommend
      a dedicated block; building it half-right contradicts the zero-false-signal goal.


## SESSION LOG — 2026-06-05 (Cowork) — DEVELOPING WAVE + CLICKABLE NEAR-MISS
- [DONE] Elliott "developing" projection (engine/structure/elliott_wave.py, ADDITIVE):
    * ElliottResult.developing (dict|None): the in-progress / nearest swing from the
      last confirmed pivot to the LIVE bar, labelled by motive-corrective alternation
      ([EWI]): impulse done -> Wave A; correction done -> Wave 1; triangle -> thrust.
      Carries invalidation + 'developing/unconfirmed' note. Degenerate (flat) -> None.
    * _build_developing(); populated on success AND no-count paths so the most recent
      candles ALWAYS carry an Elliott read. chart_label appends "· developing Wave X"
      (or shows "developing … nearest possibility" when no complete count).
    * verify_elliott.py -> 36 passed, 0 failed (L9 developing checks).
- [DONE] Backend: _computed_elliott_payload returns developing; /chart near_miss now
    carries pivot_dates + pivot_prices (drawable). py_compile OK.
- [DONE] Frontend (ADDITIVE): types ElliottDeveloping + NearMiss pivots; CandleChart
    draws developing leg DASHED to the last bar (wave marker "A?/1?") and draws the
    near-miss polyline (dashed, greyed) + PRZ when no confirmed harmonic; OverviewTab
    near-miss line is now a clickable button ("▶ show nearest on chart") on every tf;
    Elliott line drawable when preferred OR developing exists. tsc --noEmit exit 0.
    LIVE (:8010) AAPL: weekly -> developing Wave 1 → 2026-06-01; daily -> developing
    Wave A → 2026-06-05; near_miss 4 drawable pts both tf.
- HONESTY: no "zero-error/guaranteed" copy in UI. Developing waves are flagged
    unconfirmed; harmonic near-miss flagged "nearest, ratio off by X". Invalidation
    levels on every read so risk is always defined.


## SESSION LOG — 2026-06-05 (Cowork) — BACKTEST / EXPECTANCY HARNESS
- [DONE] engine/backtest_signals.py (NEW): walk-forward, NO look-ahead backtest of the
    computed Elliott signals. At decision bar i the engine sees only bars[:i+1]; trades
    simulated strictly after i; one position at a time; scored in R-multiples.
    Trade model (documented modeling choice, not an [EWI] rule): entry=decision close;
    stop=structural extreme (Wave5/C/E); target=fixed Nx R. Metrics: win rate,
    expectancy (R/trade), profit factor, max DD (R), losing streak, by-outcome, BY-SETUP.
    Flags: enable_reversal / enable_continuation.
- [DONE] backtest_run.py (NEW CLI): venv/bin/python backtest_run.py SYMBOL [interval] [target_r] [mode]
    mode = all | cont | rev. Offline self-test when no symbol.
- KEY FINDING (~10y daily, 2R):
    * IMPULSE reversal (fade trend) = NEGATIVE edge (AAPL -0.10R, SPY -0.25R, GOOGL -0.09R).
    * Corrective CONTINUATION (with-trend after correction) = POSITIVE
      (SPY +0.29R PF1.5, GOOGL +0.88R PF3.3, AAPL ~0). Continuation-only flips edge +.
    * => Recommended live rule: trade continuation signals, suppress reversal.
    * Samples small (n=6-14/sym). Widen across symbols/timeframes before sizing real risk.
- HONESTY: harness exists to REJECT negative-edge setups and size positions, not to
    promise profit. Past expectancy != future results (printed in every report).
- NEXT (recommended): (1) wire a CACHED /api/symbol/{sym}/backtest endpoint + an
    "Edge / Expectancy" UI card (backtest is ~15-30s/symbol -> must be cached/scheduled,
    not synchronous); (2) make the live Elliott payload tag continuation signals
    "tradeable" vs reversal "informational"; (3) add harmonic-PRZ backtest the same way.


## SESSION LOG — 2026-06-05 (Cowork) — EDGE WIRED INTO LIVE SIGNALS
- [DONE] ew.signal_for_count(count) (engine/structure/elliott_wave.py, public, ADDITIVE):
    canonical classifier encoding the BACKTEST policy — corrective CONTINUATION ->
    {bias LONG/SHORT, kind 'continuation', tradeable True, stop=terminal pivot};
    IMPULSE -> {reversal, tradeable False (informational)}. Documented as backtest-
    derived policy, not [EWI], not financial advice. backtest_signals._signal_from_count
    refactored to use it (single source of truth).
- [DONE] API: elliott payload now carries "signal" (technical + chart). py_compile OK.
- [DONE] Frontend (tsc exit 0): ElliottSignal type; OverviewTab Elliott line shows a
    badge — green/red "▲ TRADEABLE LONG/SHORT · stop X" for continuation, grey
    "ⓘ BIAS (informational)" for reversal; TechnicalTab Computed card shows the
    signal + rationale. Users are steered to act ONLY on positive-edge (continuation) setups.
    LIVE (:8010) GOOGL daily+weekly: IMPULSE -> SHORT, tradeable False (correctly suppressed).
- VERIFIED: verify_elliott.py 36/36; backtest self-test +2R; API signal present.
- HONESTY: 'tradeable' reflects measured edge on SMALL samples; rationale shown on hover;
    every signal carries a stop so risk is defined. Not a profit guarantee.
- NEXT (recommended): cached /api/symbol/{sym}/backtest + "Edge/Expectancy" UI card so
    the badge is backed by the symbol's own live expectancy number; widen the study.


## SESSION LOG — 2026-06-06 (Cowork) — CONCILE + 3 FEEDBACK ITEMS + AI CHAIRMAN
- [DONE] CONCILE.md created: saved "concile this" command (role, sources of truth incl.
    SKILL.docx=LLM Council, 4 standing requirements, the routine, paths). Auto-run on
    user saying "concile this".
- [DONE] #1 RECENCY (engine/structure/elliott_wave.py): preferred count now RECENCY-ranked
    (terminal pivot index primary, then guideline score, then impulse) so waves render on
    the most recent candles; the textbook best-guideline count becomes ALTERNATE.
    Combined with developing projection -> structure now reaches the latest candles.
    verify_elliott.py still 36/36.
- [DONE] #2 ABOUT + CURRENCY: real cap was pages/ai_trading_agent.py:_fetch_info
    description [:500] -> [:4000]; overview summary [:4000]; currency inferred via
    _currency_for(symbol,info) (.ST->SEK etc.), not hardcoded USD. Frontend OverviewTab
    dropped the hardcoded trailing "…" + whitespace-pre-line. LIVE SEB-A.ST: about 1972
    chars full, currency SEK.
- [DONE] #3 AI CHAIRMAN (api/symbol_router.py): GET /api/symbol/{sym}/chairman — runs all
    10 investor lenses in parallel (ThreadPoolExecutor), tallies verdicts, then a Chairman
    AI synthesis -> FINAL BUY/SELL/HOLD + conviction + rationale + decision_date/time(UTC)
    + price-at-decision + the board. Deterministic majority-vote fallback w/o GROQ.
    Helpers: _symbol_facts, _parse_fw, _chair_synthesis. Frontend: useChairman hook +
    ChairmanResp type + "AI Chairman — Final Verdict" card in AITab ("Convene the board").
    LIVE AAPL: BUY conviction 83 @ $307.34, 2026-06-06 19:24 UTC, 8/1/1, 10 members.
- VERIFIED: py_compile OK; verify_elliott 36/36; tsc --noEmit exit 0; live overview+chairman.
- ACTION FOR USER: restart :8000 to load backend edits (uvicorn --reload).


## SESSION LOG — 2026-06-06 (Cowork) — FIX: yfinance 404 spam (VOLV_B)
- SYMPTOM: ERROR:yfinance 404 "Quote not found for symbol: VOLV_B" on every
  POST /api/omni/quotes. Non-fatal (endpoint returned 200) but log spam.
- ROOT CAUSE: a malformed symbol "VOLV_B" (underscore; not a valid Yahoo ticker —
  Yahoo uses letters/digits and . - ^ =) was posted by the frontend (a STALE saved
  alert / recently-viewed entry in browser storage; NOT generated by current code —
  grep of sentriq src found no such producer). quotes() forwarded it straight to
  yf.download -> 404.
- FIX (api/omnisearch_router.py quotes(), ADDITIVE, zero-defect): pre-filter to
  Yahoo-resolvable tickers via _yf_ok() (rejects "_" and other invalid chars); only
  those go to yf.download; invalid ones return a null-price slot (frontend already
  renders these gracefully) and are logged at INFO, not ERROR. Fixes the whole CLASS
  of malformed-symbol spam, not just VOLV_B.
- VERIFIED on live :8000 (auto-reloaded): POST {AAPL, VOLV_B, VOLV-B.ST} ->
  AAPL 307.34/USD, VOLV_B price=null (no yfinance call, no ERROR), VOLV-B.ST 321.5/SEK.
- USER NOTE: the stale "VOLV_B" still shows as an empty slot until removed from the
  saved alert/recent list in the UI; it is now harmless (no error).
