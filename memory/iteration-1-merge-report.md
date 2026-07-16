# Iteration #1 Merge Report — 20 Agent Cross-Validation Scan

**Date**: 2026-07-16
**Workflow**: `wf_680a8f37-575`
**Raw findings**: 208 (67 P0, 76 P1, 65 P2)
**Cross-validated unique patterns**: 21 P0, 14 P1, 8 P2
**Sources**: AutoAgent (15 patterns), autodream (12), autoresearch (9), autonomous-coding (7)

## Cross-Source Confirmed Patterns (>=2 sources)

| # | Pattern | Sources | Priority |
|---|---------|---------|----------|
| 1 | case_resolved/case_not_resolved terminal signals | AutoAgent + autonomous-coding | P0 |
| 2 | 3-Tier retry with meta-agent escalation | AutoAgent + autonomous-coding | P0 |
| 3 | context_variables shared state bus | AutoAgent | P0 |
| 4 | MAX_* explicit caps + head-tail truncation | autodream + AutoAgent | P0 |
| 5 | Checksum-based idempotent writes | autodream | P0 |
| 6 | Git-as-state-machine | autoresearch + autonomous-coding | P0 |
| 7 | Crash classification (trivial vs fundamental) | autoresearch + autonomous-coding | P0 |
| 8 | NEVER STOP / auto-continue | autoresearch + autonomous-coding | P0 |
| 9 | Immutable checklist | autonomous-coding + autodream | P0 |
| 10 | TSV append-only results log | autoresearch | P0 |
| 11 | Init+Loop two-agent model | autonomous-coding | P0 |
| 12 | Dual-phase post-hoc reflection (Learn+Consolidate) | autodream | P0 |
| 13 | Three-layer security model (sandbox+permissions+hooks) | autonomous-coding | P0 |
| 14 | Mandatory regression gate before new work | autonomous-coding + autoresearch | P0 |
| 15 | Per-agent error isolation in parallel dispatch | AutoAgent + autonomous-coding | P0 |
| 16 | Fast-fail sentinel in loop body | autoresearch | P0 |
| 17 | Config-driven thresholds with per-project override | autodream | P0 |
| 18 | Grounding attribution (grounded vs inferred) | autodream + autonomous-coding | P0 |
| 19 | Clean exit protocol before context fill | autonomous-coding | P0 |
| 20 | max_turns hard loop guard | AutoAgent | P0 |
| 21 | Agent output provenance declaration (sender tag) | AutoAgent | P0 |

## FINAL PRIORITY LIST — Fix Order

### Tier 1: Apply Immediately (highest cross-source consensus)

1. **Terminal signal protocol** — Every agent MUST output TERMINAL: RESOLVED|UNRESOLVED|PARTIAL
2. **Workflow context bus** — context_variables dict flowing through all 7 steps
3. **MAX_* caps + head-tail truncation** — Explicit bounds on every LLM input source
4. **3-Tier retry with escalation** — Rule 7 enhancement: same agent → feedback injection → meta-agent
5. **Crash classification** — Rule 12 split: Type A (trivial, auto-fix) vs Type B (fundamental, count retry)
6. **Git-as-state-machine** — Git commits as fix state units, git reset for rollback
7. **Immutable checklist** — Init creates checklist, Loop only flips pass/fail
8. **Init+Loop model** — For iteration scanning: Init creates scan plan, Loop executes one scan→fix→verify per iteration

### Tier 2: Apply in Next Pass

9. **NEVER STOP / auto-continue** — Remove agent permission to ask "continue?"
10. **TSV results log** — Append-only cumulative results tracking
11. **Dual-phase reflection** — STEP 7.5: Learn (analyze) + Consolidate (merge)
12. **Regression gate** — STEP 4.0 + STEP 6.0.5: verify previous work before new work
13. **Per-agent error isolation** — One agent crash doesn't block N-1 results
14. **Config-driven thresholds** — All numeric limits as named constants with override
15. **Grounding attribution** — Every finding declares grounded vs inferred

### Tier 3: Apply When Stable

16. **Three-layer security model** — Sandbox + permissions + hooks (CC integration)
17. **Clean exit protocol** — Agent must signal clean exit before context fills
18. **max_turns loop guard** — Hard cap on agent LLM API calls
19. **Fast-fail sentinel** — Self-monitoring exit in loop body
20. **Provenance declaration** — Agent output header with agent_id:type
21. **Warmup exclusion window** — Skip initial steps for metric stability

## Integration Map (which file gets what)

| Pattern | Target File |
|---------|-------------|
| Terminal signals, context bus, 3-tier retry, crash classification, git-state-machine, immutable checklist, Init+Loop, NEVER STOP, regression gate, error isolation, max_turns, grounding, provenance | SKILL.md |
| MAX_* caps, head-tail truncation, config-driven thresholds, clean exit, fast-fail, warmup | anti-hang-v2.md |
| Checksum writes, TSV log, dual-phase reflection, security model | Both |
