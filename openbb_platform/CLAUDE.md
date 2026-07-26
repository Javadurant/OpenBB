# Ruflo — Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- NEVER add a `Co-Authored-By` trailer to user commits unless this project's `.claude/settings.json` has `attribution.commit` set (#2078). The Claude Code Bash tool may suggest one in its default commit-message template — ignore it. `Co-Authored-By` is semantic authorship attribution under git/GitHub convention; the tool is the facilitator, not a co-author.
- Keep files under 500 lines
- Validate input at system boundaries

## Agent Comms (SendMessage-First Coordination)

Named agents coordinate via `SendMessage`, not polling or shared state.

```
Lead (you) ←→ architect ←→ developer ←→ tester ←→ reviewer
              (named agents message each other directly)
```

### Spawning a Coordinated Team

```javascript
// ALL agents in ONE message, each knows WHO to message next
Agent({ prompt: "Research the codebase. SendMessage findings to 'architect'.",
  subagent_type: "researcher", name: "researcher", run_in_background: true })
Agent({ prompt: "Wait for 'researcher'. Design solution. SendMessage to 'coder'.",
  subagent_type: "system-architect", name: "architect", run_in_background: true })
Agent({ prompt: "Wait for 'architect'. Implement it. SendMessage to 'tester'.",
  subagent_type: "coder", name: "coder", run_in_background: true })
Agent({ prompt: "Wait for 'coder'. Write tests. SendMessage results to 'reviewer'.",
  subagent_type: "tester", name: "tester", run_in_background: true })
Agent({ prompt: "Wait for 'tester'. Review code quality and security.",
  subagent_type: "reviewer", name: "reviewer", run_in_background: true })

// Kick off the pipeline
SendMessage({ to: "researcher", summary: "Start", message: "[task context]" })
```

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Pipeline** | A → B → C → D | Sequential dependencies (feature dev) |
| **Fan-out** | Lead → A, B, C → Lead | Independent parallel work (research) |
| **Supervisor** | Lead ↔ workers | Ongoing coordination (complex refactor) |

### Rules

- ALWAYS name agents — `name: "role"` makes them addressable
- ALWAYS include comms instructions in prompts — who to message, what to send
- Spawn ALL agents in ONE message with `run_in_background: true`
- After spawning: STOP, tell user what's running, wait for results
- NEVER poll status — agents message back or complete automatically

## Swarm & Routing

### Config
- **Topology**: hierarchical-mesh (anti-drift)
- **Max Agents**: 15
- **Memory**: hybrid
- **HNSW**: Enabled
- **Neural**: Enabled

```bash
npx @claude-flow/cli@latest swarm init --topology hierarchical --max-agents 8 --strategy specialized
```

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

### 3-Tier Model Routing

| Tier | Handler | Use Cases |
|------|---------|-----------|
| 1 | Agent Booster (WASM) | Simple transforms — skip LLM, use Edit directly |
| 2 | Haiku | Simple tasks, low complexity |
| 3 | Sonnet/Opus | Architecture, security, complex reasoning |

## Memory & Learning

### Before Any Task
```bash
npx @claude-flow/cli@latest memory search --query "[task keywords]" --namespace patterns
npx @claude-flow/cli@latest hooks route --task "[task description]"
```

### After Success
```bash
npx @claude-flow/cli@latest memory store --namespace patterns --key "[name]" --value "[what worked]"
npx @claude-flow/cli@latest hooks post-task --task-id "[id]" --success true --store-results true
```

### MCP Tools (use `ToolSearch("keyword")` to discover)

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Bridge** | `memory_import_claude`, `memory_bridge_status` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### Background Workers

| Worker | When |
|--------|------|
| `audit` | After security changes |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |

```bash
npx @claude-flow/cli@latest hooks worker dispatch --trigger audit
```

## Agents

**Core**: `coder`, `reviewer`, `tester`, `planner`, `researcher`
**Architecture**: `system-architect`, `backend-dev`, `mobile-dev`
**Security**: `security-architect`, `security-auditor`
**Performance**: `performance-engineer`, `perf-analyzer`
**Coordination**: `hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`
**GitHub**: `pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

Any string works as a custom agent type.

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing

```bash
npm run build && npm test
```

## CLI Quick Reference

```bash
npx @claude-flow/cli@latest init --wizard           # Setup
npx @claude-flow/cli@latest swarm init --v3-mode     # Start swarm
npx @claude-flow/cli@latest memory search --query "" # Vector search
npx @claude-flow/cli@latest hooks route --task ""    # Route to agent
npx @claude-flow/cli@latest doctor --fix             # Diagnostics
npx @claude-flow/cli@latest security scan            # Security scan
npx @claude-flow/cli@latest performance benchmark    # Benchmarks
```

26 commands, 140+ subcommands. Use `--help` on any command for details.

## Setup

```bash
claude mcp add claude-flow -- npx -y @claude-flow/cli@latest
npx @claude-flow/cli@latest daemon start
npx @claude-flow/cli@latest doctor --fix
```

**Agent tool** handles execution (agents, files, code, git). **MCP tools** handle coordination (swarm, memory, hooks). **CLI** is the same via Bash.


## Elliott Wave Domain (engine/structure/elliott_wave.py)

Source of truth (dual-verified, nothing invented):
- [PF] Frost & Prechter — *Elliott Wave Principle: Key to Market Behavior* (10th Ed.)
- [EWI] Elliott Wave International — Waveopedia: https://www.elliottwave.com/waveopedia/
  (Home, Impulse, Motive Waves, Corrective Waves, Fibonacci Relationships — fetched 2026-06-04)

### Two mandated principles (governing all wave work)

**P1 — Wave Principle Discipline.** All wave labeling and pattern identification
must strictly adhere to the rules and guidelines in EWI's Waveopedia. The three
absolute rules below are HARD gates and are NEVER relaxed. [EWI] Impulse:
"A rule should never be disregarded." A count violating any rule is discarded.

**P2 — Logical Validation.** Before proposing a wave count, perform a
"guidelines vs. rules" check: identify the PREFERRED count and at least one
viable ALTERNATE count, prioritizing the interpretation that respects the
largest number of Elliott Wave guidelines. [EWI] Home: "The analyst usually
considers as 'preferred' the one that satisfies the largest number of
guidelines. The top 'alternate' is the one that satisfies the next largest."


### The three absolute rules (HARD gates — [EWI] Motive Waves / Impulse)

1. RULE_1 — Wave 2 never retraces 100%+ of Wave 1. "wave 2 always retraces
   less than 100% of wave 1." Make-or-break: a move below the start of wave 1
   instantly invalidates the count. [EWI] Motive Waves / Home.
2. RULE_2 — Wave 3 is never the shortest of waves 1, 3, 5. "wave 3 ... never
   the shortest among the three actionary waves ... As long as wave 3 undergoes
   a greater percentage movement than either wave 1 or 5, this rule is
   satisfied." [EWI] Motive Waves. (NOTE: source basis is *percentage*
   movement; it "almost always holds on an arithmetic basis as well." The engine
   currently checks arithmetic length per [PF]. Switching to a percentage basis
   is a DOMAIN change — requires human approval, do not silently alter.)
3. RULE_3 — Wave 4 never enters the price territory of Wave 1 (no overlap).
   "wave 4 does not enter the price territory of (i.e., 'overlap') wave 1."
   [EWI] Impulse. (Cash markets; futures may briefly overlap — diagonal
   exception is NOT auto-applied.)

Supporting rule also stated by source (not yet a separate engine gate, candidate
guideline): "wave 4 always retraces less than 100% of wave 3" and "wave 3 always
travels beyond the end of wave 1." [EWI] Motive Waves.

Corrective taxonomy ([EWI] Corrective Waves): "corrections are never fives."
Zigzag (5-3-5), Flat (3-3-5: regular/expanded/running), Triangle (3-3-3-3-3),
Combinations (double/triple three). Engine implements zigzag + regular/expanded
flat today; triangles, running flats, and combinations are NOT yet implemented
(honest gap, not stubbed).

Fibonacci ratios ([EWI] Fibonacci Relationships): common retracements .382, .50,
.618; Golden Ratio 1.618. Used only for guideline SCORING (P2), never as gates.


### Sourced decisions (derived from [EWI] Waveopedia — June 2026)

**Pivot source = PATH A (Elliott uses its own high/low full-swing-extreme
pivots via `elliott_wave.detect_pivots`).**
Rationale: every Waveopedia rule is stated in terms of *price territory /
extremes*, not closing prices — "wave 4 does not enter the price territory of
wave 1"; make-or-break levels are price highs/lows ("below the level of the
beginning of wave 1"). `engine/structure/swings.py:find_pivots` is close-to-close
(EWM-smoothed `close` via `argrelextrema`) and is therefore an unfit basis for
Elliott labeling. Keep the harmonic PRZ on `swings.py`; keep Elliott on
`detect_pivots`. If the chart later requires the harmonic and Elliott layers to
mark identical pivots, upgrade to a shared HIGH/LOW pivot finder (Path B+) — do
NOT feed Elliott the close-to-close basis (Path B), which would contradict
the source.

**RULE_2 basis = PERCENTAGE movement (RESOLVED 2026-06-05, human-approved).**
Implemented in `_check_rules`: RULE_2 ("Wave 3 never the shortest") now gates on
percentage movement (`|end-start|/|start|`) per [EWI] Motive Waves — "as long as
wave 3 undergoes a greater percentage movement than either wave 1 or 5, this rule
is satisfied." Arithmetic lengths are retained in the rule detail string. Covered
by verify_elliott.py check L7.

**Backtest finding (engine/backtest_signals.py, 2026-06-05, ~10y daily):**
Walk-forward, no-look-ahead expectancy of the computed Elliott signals at 2R:
- IMPULSE-reversal (fading completed trends) = NEGATIVE edge everywhere
  (AAPL -0.10R, SPY -0.25R, GOOGL -0.09R). Do NOT trade.
- Corrective-CONTINUATION (trade WITH the trend after a correction completes) =
  POSITIVE/neutral (SPY +0.29R PF1.5, GOOGL +0.88R PF3.3, AAPL ~0). This is the edge.
TRADE RULE: prefer continuation signals (enable_continuation), suppress reversal.
Samples are small (n=6-14/symbol) — widen across symbols/timeframes before sizing.
Past expectancy != future results.

**`min_swing_pct` = None (no fixed percentage filter).**
Rationale: Waveopedia defines wave significance by *degree* (relative/fractal
hierarchy), never by an absolute price-percentage swing threshold. No sourced
numeric value exists, so none is invented (DOMAIN VALUE PROTOCOL). Rely on the
N-bar fractal confirmation (`MIN_PIVOT_BARS = 5`, [PF] protocol). If swing
filtering is later required, prefer a degree-relative or ATR-multiple approach
with the multiple supplied explicitly by the user — still never invented here.
