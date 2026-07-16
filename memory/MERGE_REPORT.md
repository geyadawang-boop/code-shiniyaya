# MERGE_REPORT: Cross-Validated 20-Agent Findings vs. Existing Memory Files

Generated: 2026-07-16
Existing files checked (8):
1. autoagent-gap-analysis.md (15 patterns: 4 P0, 5 P1, 6 P2)
2. autodream-pattern-transfer.md (10 patterns: durable memory)
3. autodream-context-patterns.md (10 patterns: context caps)
4. staged-event-driven-patterns.md (11 patterns: event-driven orchestration)
5. high-impact-patterns.md (Top-10 cross-validated + 26 git patterns + provenance patterns)
6. autoagent-progress-patterns.md (9 patterns: progress tracking)
7. autoagent-security-patterns.md (8 patterns: security/anti-hang)
8. autoagent-error-recovery-patterns.md (10 patterns: error recovery)

---

## SECTION 1: CONFIRMED (Patterns already present in existing files)

These patterns appear in the cross-validated 20-agent findings AND already exist in at least one of the 8 memory files. They do NOT need new file creation -- only priority re-ranking.

### C1. Exponential Backoff Retry with Transient-vs-Permanent Error Classification (P0, 3 sources)
- **Cross-validation**: AutoAgent + autonomous-coding + autoresearch
- **Existing in**:
  - `autoagent-error-recovery-patterns.md` Pattern 1: Tenacity Exponential Backoff with Dual-Mode Error Classification (P0)
  - `autoagent-progress-patterns.md` Finding 8: `should_retry_error()` Transient vs. Permanent Error Classification (P1)
  - `autoagent-security-patterns.md`: references error classification in Pattern 7 context
- **Status**: CONFIRMED. Triple-covered across 3 existing files. The `autoagent-error-recovery-patterns.md` version is the most complete (type-based + message-substring-based classification, 10s/20s/40s/80s backoff schedule, separate retry counters).

### C2. max_turns Hard Loop Guard (P0, 2 sources)
- **Cross-validation**: AutoAgent + autonomous-coding
- **Existing in**:
  - `autoagent-security-patterns.md` Pattern 1: max_turns Hard Loop Guard (P0)
- **Status**: CONFIRMED. Covers STEP 6 (20 turns), STEP 1/4 (40 turns), iteration scan (30 turns) per-agent limits.

### C3. Structured Terminal Signals (RESOLVED/UNRESOLVED/case_resolved) (P0, 2 sources)
- **Cross-validation**: AutoAgent + autoresearch
- **Existing in** (HEAVILY duplicated -- 5 files):
  - `autoagent-gap-analysis.md` P0-3: case_resolved / case_not_resolved Explicit Terminal Signals
  - `staged-event-driven-patterns.md` Finding 1: case_resolved / case_not_resolved terminal signal protocol
  - `autoagent-progress-patterns.md` Finding 1: Binary Resolution Signals with XML Tags
  - `autoagent-error-recovery-patterns.md` Pattern 4: Dual-Ended Agent Completion Signals (FIXED/CANNOT_FIX/FATAL)
  - `autoagent-security-patterns.md` Pattern 6: Structured Termination Signals
- **Status**: CONFIRMED. Most duplicated pattern across all files. The `autoagent-error-recovery-patterns.md` version is the most actionable (FIXED/CANNOT_FIX/FATAL with category routing).

### C4. Immutable Checklist Extensions (P0, 2 sources)
- **Cross-validation**: autonomous-coding + autodream
- **Existing in**:
  - `high-impact-patterns.md` Pattern #3: Immutable Checklist
  - `autodream-pattern-transfer.md` Finding 1: checksum-based idempotent writes (complementary)
- **Status**: CONFIRMED. The cross-validation adds NEVER block enumeration, evidence-gated verified flip, and SHA-256 integrity anchor as extensions (see EXTENDED section).

### C5. Git as State Machine (P0, 2 sources)
- **Cross-validation**: autoresearch + autonomous-coding
- **Existing in**:
  - `high-impact-patterns.md` Pattern #2: Git as State Machine -- with 8 sub-patterns (2a-2h) and 8 additional patterns (19-26)
- **Status**: CONFIRMED. Most extensively documented pattern. 26 total sub-patterns across high-impact-patterns.md.

### C6. NEVER STOP / Full Autonomy (P0, 2 sources)
- **Cross-validation**: autoresearch + autonomous-coding
- **Existing in**:
  - `high-impact-patterns.md` Pattern #9: "NEVER STOP" instruction
  - Sub-pattern 25 in the git state machine section
- **Status**: CONFIRMED. Fix documented: replace convergence-failure=stop with strategy-change.

### C7. Crash Taxonomy with Differentiated Retry (P0, 2 sources)
- **Cross-validation**: autoresearch + autonomous-coding
- **Existing in**:
  - `high-impact-patterns.md` Pattern #4: Crash Taxonomy
  - `autoagent-error-recovery-patterns.md` Pattern 1 (error classification)
- **Status**: CONFIRMED. Type A (trivial: auto-fix in-place, no retry penalty) vs Type B (fundamental: counts toward 3-retry limit).

### C8. Context Accumulation Across Retries (P0, 2 sources)
- **Cross-validation**: AutoAgent + autoresearch
- **Existing in**:
  - `autoagent-error-recovery-patterns.md` Pattern 2: 3-Tier Retry with feedback injection
  - `autoagent-progress-patterns.md` Finding 7: Per-Iteration Feedback Injection
- **Status**: CONFIRMED. Both files describe injecting prior failure context into replacement prompts.

### C9. Token Counting / Token Budget Enforcement (P0, 2 sources)
- **Cross-validation**: AutoAgent + autodream
- **Existing in**:
  - `autoagent-gap-analysis.md` P2-4: Token Counting with tiktoken for Precision
  - `autodream-context-patterns.md` Pattern 1: Explicit MAX_* Caps as Module-Level Constants
  - `autoagent-security-patterns.md` Pattern 7: Tool Output Truncation with Token Counting
  - `autoagent-error-recovery-patterns.md` Pattern 5: Tool Output Truncation with Token Budget
- **Status**: CONFIRMED. Quadruple-covered. tiktoken-based counting with gpt-4o encoding.

### C10. Head-Tail Truncation Function (60/40) (P0, 2 sources)
- **Cross-validation**: autodream + AutoAgent
- **Existing in**:
  - `autodream-context-patterns.md` Pattern 2: Head-Tail Truncation (truncate_for_prompt)
  - `autoagent-gap-analysis.md` P1-3: Tool-Result Truncation with File-Based Overflow
- **Status**: CONFIRMED. 60% head, 40% tail, "\n...\n" marker, applied at every data-source injection point.

### C11. Output Truncation + Anti-Flood Output Caps (P0, 3 sources)
- **Cross-validation**: autodream + autoresearch + AutoAgent
- **Existing in**:
  - `autodream-context-patterns.md` Patterns 1+4: Per-source capping at assembly time
  - `autoagent-security-patterns.md` Pattern 7: Agent output size limit 15000 chars
  - `autoagent-error-recovery-patterns.md` Pattern 5: Output truncation with 12000 token cap
- **Status**: CONFIRMED. All three files describe output redirection + inline summary pattern.

### C12. Config-Driven Named Module-Level Constants (P1, 2 sources)
- **Cross-validation**: autodream + autoresearch
- **Existing in**:
  - `autodream-context-patterns.md` Pattern 1: 16 MAX_* constants at module level
- **Status**: CONFIRMED. Fix: extract all repeated thresholds as named module-level constants.

### C13. Event-Driven DAG Engine (P0, single-source but heavily documented)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `autoagent-gap-analysis.md` P0-4: Event-Driven DAG Engine for Step Orchestration
  - `staged-event-driven-patterns.md` Findings 3, 4, 7, 11: First-completed dispatch, listen_group, GOTO/ABORT, dedup
  - `high-impact-patterns.md` Pattern #6: Event-Driven DAG Engine
- **Status**: CONFIRMED. Triple-covered in detail.

### C14. Hub-and-Spoke Agent Orchestration (P0, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `autoagent-gap-analysis.md` P0-2: Result Object with Agent Handoff
  - `staged-event-driven-patterns.md` Finding 5: Hub-and-Spoke Triage Routing
  - `high-impact-patterns.md` Pattern #1: Hub-and-Spoke Orchestration
- **Status**: CONFIRMED. Triple-covered.

### C15. Two-Phase Post-Workflow Reflection (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 3: Memory consolidation/dedup mechanism
  - `autodream-context-patterns.md` Pattern 6: Two-Phase Processing (Learn + Consolidation)
  - `high-impact-patterns.md` Pattern #7: Two-Phase Reflection Loop
- **Status**: CONFIRMED. Triple-covered.

### C16. Grounded vs Inferred Provenance (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 4: grounding/attribution tracking per-pattern
  - `high-impact-patterns.md` Pattern 11: Grounded vs Inferred provenance declaration
- **Status**: CONFIRMED. Double-covered.

### C17. Dual Representation Memory (Markdown + Vector DB) (P1, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` (entire file premise)
  - `high-impact-patterns.md` Pattern #5: Dual Representation Memory
- **Status**: CONFIRMED. Double-covered.

### C18. 3-Tier Retry Escalation with Meta-Agent (P0/P1, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `autoagent-gap-analysis.md` P1-1: 3-Tier Retry with Meta-Agent Upgrade
  - `staged-event-driven-patterns.md` Finding 6: 3-Tier Retry with Meta-Agent Escalation
  - `autoagent-progress-patterns.md` Finding 4: 3-Tier Retry with Error Feedback Injection
  - `autoagent-security-patterns.md` Pattern 3: 3-Tier Retry Escalation with Meta-Agent Failover
  - `autoagent-error-recovery-patterns.md` Pattern 2: 3-Tier Retry Escalation with Meta-Agent Handoff
  - `high-impact-patterns.md` Pattern #8: 3-Tier Retry Escalation
- **Status**: CONFIRMED. Most duplicated pattern (6 files). The `autoagent-error-recovery-patterns.md` version is the most complete with tier-level strategy changes.

### C19. Trajectory Recording (P0/P1, single-source)
- **Cross-validation**: autonomous-coding
- **Existing in**:
  - `high-impact-patterns.md` Pattern #10: Trajectory Recording
- **Status**: CONFIRMED.

### C20. Source Context Tracking (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 4: source_context_ids, source_first_prompts, source_memory_ids
  - `high-impact-patterns.md` Patterns 12, 13
- **Status**: CONFIRMED.

### C21. Taxonomy: Rules vs Facts (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 9: Taxonomy differentiation
  - `high-impact-patterns.md` Pattern 14: Taxonomy -- Rules (.promptinclude.md) vs Facts (.md)
- **Status**: CONFIRMED.

### C22. Schema Version Independent from Skill Version (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 2: State lifecycle with schema versioning
- **Status**: CONFIRMED.

### C23. Interleave_user Anti-Loop Guard (P0, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `autoagent-gap-analysis.md` P2-1: interleave_user_into_messages Anti-Loop Protection
- **Status**: CONFIRMED.

### C24. First-Completed Async Dispatch / Incremental Processing (P0, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `staged-event-driven-patterns.md` Finding 3: First-completed async dispatch
  - `autoagent-error-recovery-patterns.md` Pattern 7: FIRST_COMPLETED Scheduling + Cancel Propagation
- **Status**: CONFIRMED.

### C25. Per-Run Dedup Cache (already_sent_to_event_group) (P1, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `staged-event-driven-patterns.md` Finding 11: already_sent_to_event_group Deduplication
  - `autoagent-security-patterns.md` Pattern 8: Event Dispatch Dedup
- **Status**: CONFIRMED.

### C26. GOTO/ABORT Dynamic Flow Control (P1, single-source)
- **Cross-validation**: AutoAgent
- **Existing in**:
  - `staged-event-driven-patterns.md` Finding 7: GOTO and ABORT dynamic control flow
  - `autoagent-error-recovery-patterns.md` Pattern 9: GOTO/ABORT Flow Control Primitives
- **Status**: CONFIRMED.

### C27. Checksum-Based Idempotent Writes (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 1: checksum-based idempotent writes
  - `autodream-context-patterns.md` Pattern 5: Checksum-Based Idempotency
- **Status**: CONFIRMED.

### C28. Memory Consolidation / Dedup (P0, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 3: memory consolidation/dedup mechanism
  - `high-impact-patterns.md` Pattern 16: Consolidation Phase
- **Status**: CONFIRMED.

### C29. Standardized Memory Frontmatter (P1, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 5: memory file frontmatter with provenance
  - `high-impact-patterns.md` Pattern 18: Standardized Memory Frontmatter
- **Status**: CONFIRMED.

### C30. Cross-Session Fingerprinting (P1, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `high-impact-patterns.md` Pattern 15: Cross-Session Fingerprinting
- **Status**: CONFIRMED.

### C31. Orphan Candidate Detection (P1, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-pattern-transfer.md` Finding 10: orphan candidate detection
  - `high-impact-patterns.md` Pattern 17: Orphan Candidate Detection
- **Status**: CONFIRMED.

### C32. Utility Model for Cost-Efficient Background Reflection (P2, single-source)
- **Cross-validation**: autodream
- **Existing in**:
  - `autodream-context-patterns.md` Pattern 10: Utility Model Pre-Summarization
- **Status**: CONFIRMED.

### C33. Simplicity Criterion (P0, single-source)
- **Cross-validation**: autoresearch
- **Existing in**:
  - `high-impact-patterns.md` Pattern #2 sub-pattern 2b (binary keep/reset) and 2e (three-outcome taxonomy)
- **Status**: CONFIRMED.

### C34. Fixed Budget as Proxy (P0, single-source)
- **Cross-validation**: autoresearch
- **Existing in**:
  - `high-impact-patterns.md` Pattern #2 sub-patterns and budget-aware patterns
- **Status**: CONFIRMED.

### C35. Results TSV Append-Only Cumulative Log (P0, single-source)
- **Cross-validation**: autoresearch
- **Existing in**:
  - `high-impact-patterns.md` Pattern 21: Flat-file fix log (results.tsv equivalent)
- **Status**: CONFIRMED.

### C36. Fast-Fail Inline Sentinel (P0, single-source)
- **Cross-validation**: autoresearch
- **Existing in**:
  - `high-impact-patterns.md` Pattern 24: In-flight code fast-fail self-abort (NaN detection + exit(1))
- **Status**: CONFIRMED.

### C37. Three-Layer Security Model (P0, single-source)
- **Cross-validation**: autonomous-coding
- **Existing in**: The cross-validation references `autonomous-coding-security-findings.md` which is NOT one of the 8 existing files. However, the three-layer security concept is briefly mentioned in `autoagent-security-patterns.md` as "NOT Transferred" patterns (Docker Container Isolation).
- **Status**: PARTIAL. The concept is noted but not fully documented in the 8 files.

### C38. Bash Command Allowlist (P0, single-source)
- **Cross-validation**: autonomous-coding
- **Existing in**: Not in any of the 8 files. Referenced in cross-validation as being in `autonomous-coding-security-findings.md`.
- **Status**: PARTIAL. Not in the 8 existing files.

### C39. Clean Exit Protocol (P0, single-source)
- **Cross-validation**: autonomous-coding
- **Existing in**: Not explicitly in any of the 8 files.
- **Status**: PARTIAL.

### C40. Init+Loop Two-Agent Model (P1, single-source)
- **Cross-validation**: autonomous-coding
- **Existing in**:
  - `high-impact-patterns.md` Pattern #1 mentions "Init Agent + Loop Agent" briefly
- **Status**: CONFIRMED (mentioned but not deeply documented).

---

## SECTION 2: EXTENDED (New scan adds material to existing patterns)

These patterns exist in at least one memory file, but the cross-validated 20-agent scan adds new dimensions, sources, or implementation details that were not previously documented.

### E1. IMMUTABLE CHECKLIST -- New Extensions (P0)

**Existing base**: `high-impact-patterns.md` Pattern #3, `autodream-pattern-transfer.md` Finding 1 (checksum-based writes).

**New detail from cross-validation**:
- **NEVER block enumeration**: The cross-validation adds an explicit denylist of prohibited mutations (remove items, edit descriptions, modify scan steps, consolidate/combine tasks, reorder tasks) that is NOT in the existing files. Current documentation only has an allowlist ("only flip verified flag").
- **Evidence-gated verified flip**: The cross-validation adds the requirement that `verified: true` MUST be accompanied by an `evidence` field containing the verification method and result. Current documentation only says "only verified flag can change."
- **SHA-256 integrity anchor**: The cross-validation adds a SHA-256 checksum of the scan-plan JSON to detect tampering. Current documentation has checksums for memory files (autodream-pattern-transfer.md Finding 1) but NOT for the scan-plan itself.

**Files to update**: `high-impact-patterns.md` Pattern #3 -- add NEVER block, evidence field, SHA-256 anchor.

### E2. CRASH TAXONOMY -- Retry Backoff Timing (P0)

**Existing base**: `high-impact-patterns.md` Pattern #4, `autoagent-error-recovery-patterns.md` Pattern 1.

**New detail from cross-validation**:
- **Concrete backoff timing**: The cross-validation adds the exact AutoAgent tenacity schedule: 10s/40s/180s with multiplier=1, min=10, max=180. The existing `autoagent-error-recovery-patterns.md` Pattern 1 already has this (10s->20s->40s->80s). The cross-validation confirms and adds the autoresearch `exit(1)` convention for crash vs. completion.
- **Exit-code-based classification**: The cross-validation adds `exit(1)` vs `exit(0)` as a crash-detection mechanism from autoresearch. Not in existing error-recovery files.
- **Trivial fix in-place, no state reset**: The cross-validation adds the rule from autoresearch that Type A (trivial) fixes are applied in-place on the current branch, with no git reset and no retry penalty. The existing crash taxonomy mentions the Type A/B distinction but does not explicitly state "no state reset for Type A."

**Files to update**: `autoagent-error-recovery-patterns.md` Pattern 1 -- add exit-code-based classification and "no state reset for trivial fixes" rule.

### E3. 3-TIER RETRY -- Adds Dual-Signal Prerequisite (P0)

**Existing base**: `high-impact-patterns.md` Pattern #8, `autoagent-error-recovery-patterns.md` Pattern 2, `autoagent-security-patterns.md` Pattern 3, `autoagent-progress-patterns.md` Finding 4, `staged-event-driven-patterns.md` Finding 6.

**New detail from cross-validation**:
- **Dual-signal protocol as prerequisite**: The cross-validation frames the retry escalation as requiring BOTH a pre-action [REASON] gate AND a post-action TERMINAL signal, making the retry escalation the middle tier of a three-layer protocol. None of the existing files frame it this way.
- **Context accumulation from prior attempts explicitly modeled**: The cross-validation makes explicit that `messages.extend(response.messages)` from AutoAgent main.py:52-79 is a required mechanism. The existing files mention "feedback injection" but do not specify the exact mechanism of extending the message history.

**Files to update**: `high-impact-patterns.md` Pattern #8 -- add dual-signal prerequisite and explicit context-accumulation mechanism.

### E4. NEVER STOP -- Concrete Stop-Conditions-Only List (P0)

**Existing base**: `high-impact-patterns.md` Pattern #9, sub-pattern 25.

**New detail from cross-validation**:
- **Explicit stop-conditions-only list**: The cross-validation adds that the agent must NEVER self-terminate; only stop conditions are: (a) all items done, (b) 3 consecutive crashes on the same bug, (c) user interrupt. The existing Pattern #9 mentions this in general but the cross-validation enumerates it precisely.
- **Replacement of convergence-failure=stop**: The cross-validation explicitly identifies SKILL.md line 433 ("CRITICAL连续2次迭代上升->强制停止+策略变更") as the specific code-shiniyaya line that contradicts NEVER STOP. The existing Pattern #9 does not cite the exact conflicting line.

**Files to update**: `high-impact-patterns.md` Pattern #9 -- add concrete stop-conditions enumeration and conflicting SKILL.md line reference.

### E5. EVENT-DRIVEN DAG -- Adds Self-Growing Queue Aspect (P0)

**Existing base**: `high-impact-patterns.md` Pattern #6, `autoagent-gap-analysis.md` P0-4, `staged-event-driven-patterns.md` Findings 3, 4, 7, 11.

**New detail from cross-validation**:
- **Self-growing BFS work queue / emergent parallelism**: The cross-validation adds the specific observation that the queue GROWS during execution (when completed events trigger downstream dispatch, `queue.append(...)` adds new items mid-loop). The existing files describe the DAG dispatch loop but do NOT explicitly call out the "self-growing" or "emergent parallelism" property where total work set is unknown at launch.
- **code-shiniyaya-specific fix**: After each agent result arrives, evaluate "Does this finding suggest a dimension not covered by the current batch?" If yes, queue a new agent slot (up to cap of 12 per iteration).

**Files to update**: `staged-event-driven-patterns.md` Finding 3 -- add self-growing queue aspect and the specific code-shiniyaya fix for dynamic slot allocation.

### E6. OUTPUT CAPS -- Adds Post-Action Dual-Signal Protocol (P1)

**Existing base**: `autodream-context-patterns.md`, `autoagent-security-patterns.md` Pattern 7, `autoagent-error-recovery-patterns.md` Pattern 5.

**New detail from cross-validation**:
- **Dual-signal protocol (Pre-Action + Post-Action)**: The cross-validation frames output caps as part of a broader protocol where every agent MUST emit TWO signals: (1) [REASON] before first tool call, (2) TERMINAL line as last output. Missing REASON -> findings 0.5x weight. Missing TERMINAL -> TIMED_OUT. This is a new framing not present in any existing file.
- **Pre-action reasoning gate combined with output caps**: The cross-validation unifies the context-capping pattern with the reasoning-gating pattern as a single "dual-signal" protocol.

**Files to update**: `autodream-context-patterns.md` -- add dual-signal framing. Also create joint reference in `staged-event-driven-patterns.md` or a new combined pattern.

### E7. CONTEXT ACCUMULATION -- Adds Injection Block Format (P0)

**Existing base**: `autoagent-error-recovery-patterns.md` Pattern 2, `autoagent-progress-patterns.md` Finding 7.

**New detail from cross-validation**:
- **Specific injection block format**: The cross-validation specifies that replacement prompts should receive a `[CONTEXT FROM PRIOR ATTEMPT]` summary block containing the last 3 tool calls, partial findings, and failure mode from `agent-{agentId}.jsonl`. The existing files say "inject previous failure context" but do not specify the exact format, source file, or content structure.

**Files to update**: `autoagent-error-recovery-patterns.md` Pattern 2 -- add specific injection block format.

---

## SECTION 3: NEW (Patterns NOT in any of the 8 existing files)

These patterns appear in the cross-validated 20-agent findings but have NO corresponding entry in any of the 8 existing memory files.

### N1. Pre-Action Reasoning Gate / ThinkTool Pattern (P1, 2 sources)

**Sources**: autonomous-coding + AutoAgent

**Pattern**: Every dispatched agent MUST reason explicitly before its first tool call. ThinkTool (autonomous-coding `think.py`) is a named tool with no side effects that appends reasoning to a log. AutoAgent (`fn_call_converter.py:837-848`) injects "Please think twice..." between consecutive assistant messages.

**Specific mechanism**:
- Before using ANY tool, agent must output a [REASON] block with: Goal, Expected, Risk, Success criteria
- Agents that skip [REASON] -> findings downgraded to 0.5x weight
- AutoAgent's interleave_user is a related but distinct mechanism (anti-loop injection, not pre-action gating)

**Why not in existing files**: The existing files cover post-action TERMINAL signals extensively but have zero mention of pre-action reasoning gates. The ThinkTool pattern from autonomous-coding was identified in `autonomous-coding-gap-analysis.md` (not one of the 8 files in this merge set).

**Fix for code-shiniyaya**:
```
Add to Agent dispatch prompt template:
  [REASON]
  Goal: <one sentence>
  Expected: <what you predict to find>
  Risk: <what could go wrong>
  Success: <how to verify your result>
  [/REASON]

Add to SKILL.md: Agents that skip [REASON] -> findings 0.5x weight.
Add to anti-hang-v2.md: Missing [REASON] + missing TERMINAL = double-fault -> immediate slot replacement.
```

**Target file**: Create new `memory/pre-action-reasoning-patterns.md` OR add to `staged-event-driven-patterns.md`.

### N2. Regression Gate Before New Work (P1, 2 sources)

**Sources**: autonomous-coding + autoresearch

**Pattern**: Before starting any new fix work, verify 1-2 previously-passing items still pass. autonomous-coding `coding_prompt.md:48-67` mandates "STEP 3: VERIFICATION TEST (CRITICAL!) -- run 1-2 previously-passing tests before anything new." autoresearch `program.md:39` establishes a baseline commit before any experimentation.

**Specific mechanism**:
- Before each STEP 6 fix: verify 1-2 previously `verified: true` scan-plan items still pass
- If any break: flip `verified: false`, add to queue ahead of new work
- If the gap-analysis files had this, it was only in `autonomous-coding-gap-analysis.md` (not in the 8 merge files)

**Why not in existing files**: The existing files cover git state machines and immutable checklists but do not describe the specific "regression gate" pattern: verifying OLD passing items before starting NEW work. This is a distinct sequencing pattern, not covered by the git-commit-as-unit model.

**Fix for code-shiniyaya**:
```
REGRESSION GATE (P0 -- before each STEP 6 fix):
1. Select 1-2 items with verified: true from scan-plan-{iter}.json
2. Re-run their verification scripts
3. If still pass -> proceed with new fix
4. If any fail -> flip verified: false, prepend to current iteration queue, emit REGRESSION_DETECTED warning
```

**Target file**: Add to `high-impact-patterns.md` as Pattern #27 or create `memory/regression-gate-patterns.md`.

### N3. Asymmetric Persistence Guards (File-Always vs Console-Gated) (P1, 1 source)

**Source**: AutoAgent `logger.py:29-57`

**Pattern**: `info()` always writes to file but only prints to console if `debug=True`; `lprint()` prints to console but NEVER touches files. Three reliability tiers: file+console, file-only, console-only.

**Specific mechanism**:
- File log: unconditional (always persisted, for forensic analysis)
- Console output: gated by verbosity flag (for developer visibility)
- `lprint()`: structurally incapable of polluting permanent logs

**Why not in existing files**: `autoagent-gap-analysis.md` P1-5 describes the Singleton Logger Manager but focuses on the singleton pattern and log directory creation, NOT on the asymmetric persistence gating between file and console. `autoagent-progress-patterns.md` Finding 3 describes structured log categories but doesn't capture the tiered persistence.

**Fix for code-shiniyaya**:
```
Decouple workflow event log (always-on, persistent, JSONL) from console progress report (gated by --verbose/--quiet).
File log unconditionally; console output respects verbosity flag.
Three tiers:
  1. eventlog-{sessionId}.jsonl: ALWAYS written (AGENT_RESULT, STEP_TRANSITION, ERROR, GATE_PASS/FAIL)
  2. Console progress: ONLY when --verbose (AGENT_LAUNCH, HEARTBEAT, progress bars)
  3. Console debug: ONLY when --debug (AGENT_THOUGHT, intermediate reasoning)
```

**Target file**: Add to `autoagent-error-recovery-patterns.md` as Pattern 11.

### N4. MC_MODE / Environment-Aware Output Degradation (P1, 1 source)

**Source**: AutoAgent `logger.py:34-103`

**Pattern**: Every render method checks `if MC_MODE: color = "grey58"`, producing pipe-friendly monochrome output in headless/embedded environments. ANSI color codes, Rich formatting, Unicode arrows, and emoji are replaced with plain ASCII equivalents when output is not a TTY.

**Specific mechanism**:
- `os.isatty(sys.stdout.fileno())` detection at startup
- Non-TTY: strip ANSI/Rich markup, ASCII-only progress bars, `-->` replacing Unicode arrows, suppress emoji
- TTY: full Rich formatting with colors and Unicode

**Why not in existing files**: No existing file addresses output format degradation for non-TTY environments. `autoagent-gap-analysis.md` P2-5 covers feature detection (git, python, tiktoken availability) but not output mode detection.

**Fix for code-shiniyaya**:
```
Add OUTPUT_MODE detection:
  os.isatty(sys.stdout.fileno()) -> TTY vs PIPE
  TTY: Rich formatting, ANSI colors, Unicode, emoji
  PIPE: Plain ASCII, no color codes, ASCII arrows, no emoji
  
Apply at all log() and progress-report sites.
```

**Target file**: Add to `autoagent-gap-analysis.md` as new P2 entry.

### N5. Transient Debug-Only Log Channel (lprint equivalent) (P2, 1 source)

**Source**: AutoAgent `logger.py:45-57`

**Pattern**: `lprint()` is a console-only output method structurally incapable of polluting permanent logs. All agent diagnostic output has zero file persistence, keeping persistent logs clean.

**Specific mechanism**:
- Separate by event type: `AGENT_RESULT` entries go to both file and console; `AGENT_THOUGHT` entries go to console_debug only
- Console_debug channel: rendered inline for developer visibility but EXCLUDED from persistent `eventlog-{sessionId}.jsonl`

**Why not in existing files**: Existing logging patterns describe structured logging categories but assume all categories go everywhere. No existing file describes a channel that is structurally excluded from persistent storage.

**Fix for code-shiniyaya**:
```
Add console_debug channel:
  - AGENT_RESULT, STEP_TRANSITION, ERROR -> both file (eventlog) AND console
  - AGENT_THOUGHT, intermediate_reasoning -> console_debug only (NEVER touches eventlog)
  
This keeps eventlog clean for forensic analysis while allowing verbose debugging.
```

**Target file**: Add to `autoagent-error-recovery-patterns.md` as Pattern 12.

### N6. Clean Engine Reset for Re-Invocation (P1, 1 source)

**Source**: AutoAgent `flow/core.py:24`

**Pattern**: `reset()` empties `__event_maps = {}` enabling fresh DAG execution without recreating the engine object. This prevents stale state from iteration N contaminating iteration N+1.

**Specific mechanism**:
- At each new iteration start: archive previous results to `itemStatesArchive.iter{N}` and clear active `itemStates`
- CR (convergence rate) reads from current iteration only
- Prevents stale agent results from distorting convergence tracking

**Why not in existing files**: The iteration scanning and state management patterns discuss state files but do not describe the engine-level reset that clears in-process state between iterations. The existing files assume state is always read from disk; this pattern describes clearing in-memory state.

**Fix for code-shiniyaya**:
```
At each new iteration start:
1. Archive: itemStates -> itemStatesArchive/iter{N}.json
2. Clear: itemStates = {}
3. Reset: convergence tracking counters to 0
4. CR reads from current iteration itemStates only
```

**Target file**: Add to `staged-event-driven-patterns.md` as Finding 12.

### N7. Dual-Signal Protocol (Pre-Action + Post-Action Combined) (P1, 2 sources) -- NEW as combined framing

**Sources**: autonomous-coding + AutoAgent

**Pattern**: This is the COMBINATION of N1 (Pre-Action Reasoning Gate) and C3 (Post-Action TERMINAL Signal) as a unified protocol. While both components exist separately (C3 is heavily confirmed in existing files, N1 is new), the COMBINED framing as a "dual-signal protocol" where every agent MUST emit TWO signals is not present in any existing file.

**Specific mechanism**:
- Signal 1 (PRE): [REASON] block before first tool call (Goal/Expected/Risk/Success)
- Signal 2 (POST): TERMINAL line as last output (RESOLVED/UNRESOLVED/PARTIAL)
- Missing REASON -> findings 0.5x weight
- Missing TERMINAL -> TIMED_OUT
- Missing BOTH -> immediate slot replacement, no retry

**Why not in existing files**: Existing files treat terminal signals and reasoning as separate concerns. No file frames them as a unified two-phase protocol.

**Fix for code-shiniyaya**:
```
Every agent MUST emit TWO signals:
1. [REASON] before first tool call
2. TERMINAL as last output line

Enforcement:
- Missing REASON -> findings weight 0.5x (downgrade confidence)
- Missing TERMINAL -> mark TIMED_OUT, trigger Rule 7 replacement
- Missing BOTH -> immediate permanent failure (no retry)
```

**Target file**: Add to `staged-event-driven-patterns.md` as Finding 13 or create `memory/dual-signal-protocol.md`.

---

## SECTION 4: FINAL_PRIORITY_LIST

Given all evidence from both the 8 existing memory files AND the cross-validated 20-agent scan, re-ranked by implementation priority.

### Tier 0 -- Already Documented, Needs Integration (no new research needed)

These patterns are fully documented in existing memory files with exact file:line references, concrete fix code, and implementation instructions. They need SKILL.md integration, not more analysis.

| # | Pattern | Primary Source File | SKILL.md Target |
|---|---------|-------------------|-----------------|
| T0-1 | Structured Terminal Signals (RESOLVED/UNRESOLVED/PARTIAL) | `autoagent-error-recovery-patterns.md` Pattern 4 | STEP 6 Agent完成信号 |
| T0-2 | max_turns Hard Loop Guard | `autoagent-security-patterns.md` Pattern 1 | Rule 12b |
| T0-3 | 3-Tier Retry Escalation with Meta-Agent | `autoagent-error-recovery-patterns.md` Pattern 2 | Rule 7 replacement |
| T0-4 | Exponential Backoff + Error Classification | `autoagent-error-recovery-patterns.md` Pattern 1 | Error handling table |
| T0-5 | Context Accumulation Across Retries | `autoagent-error-recovery-patterns.md` Pattern 2 (feedback injection) | Agent dispatch |
| T0-6 | Head-Tail Truncation (60/40) | `autodream-context-patterns.md` Pattern 2 | STEP 4, all prompt assembly |
| T0-7 | Explicit MAX_* Caps as Named Constants | `autodream-context-patterns.md` Pattern 1 | STEP 4 Input Caps |
| T0-8 | Output Truncation + Anti-Flood Caps | `autoagent-error-recovery-patterns.md` Pattern 5 | All agent output |

### Tier 1 -- Cross-Source P0, New or Extension, Deploy Immediately

| # | Pattern | Type | Sources | Key File to Create/Update |
|---|---------|------|---------|--------------------------|
| T1-1 | Immutable Checklist Extensions (NEVER block + evidence gate + SHA-256 anchor) | EXTENDED | autonomous-coding + autodream | Update `high-impact-patterns.md` Pattern #3 |
| T1-2 | Crash Taxonomy: Exit-Code Classification + No-Reset for Trivial Fixes | EXTENDED | autoresearch + autonomous-coding | Update `autoagent-error-recovery-patterns.md` Pattern 1 |
| T1-3 | NEVER STOP: Concrete Stop-Conditions List + Conflicting SKILL.md Line | EXTENDED | autoresearch + autonomous-coding | Update `high-impact-patterns.md` Pattern #9 |
| T1-4 | Dual-Signal Protocol (Pre-Action + Post-Action Combined) | NEW | autonomous-coding + AutoAgent | Create `memory/dual-signal-protocol.md` |
| T1-5 | Pre-Action Reasoning Gate (ThinkTool Pattern) | NEW | autonomous-coding + AutoAgent | Create `memory/pre-action-reasoning-patterns.md` |
| T1-6 | Regression Gate Before New Work | NEW | autonomous-coding + autoresearch | Add to `high-impact-patterns.md` as Pattern #27 |
| T1-7 | Event-Driven DAG: Self-Growing Queue / Emergent Parallelism | EXTENDED | AutoAgent | Update `staged-event-driven-patterns.md` Finding 3 |

### Tier 2 -- Cross-Source P1, Valuable but Not Blocking

| # | Pattern | Type | Sources | Key File to Create/Update |
|---|---------|------|---------|--------------------------|
| T2-1 | Context Accumulation Injection Block Format | EXTENDED | AutoAgent + autoresearch | Update `autoagent-error-recovery-patterns.md` Pattern 2 |
| T2-2 | Asymmetric Persistence Guards (File vs Console) | NEW | AutoAgent | Add to `autoagent-error-recovery-patterns.md` as Pattern 11 |
| T2-3 | MC_MODE / Environment-Aware Output Degradation | NEW | AutoAgent | Add to `autoagent-gap-analysis.md` as new P2 entry |
| T2-4 | Clean Engine Reset for Re-Invocation | NEW | AutoAgent | Add to `staged-event-driven-patterns.md` as Finding 12 |

### Tier 3 -- P2, Nice-to-Have, Quality of Life

| # | Pattern | Type | Sources | Key File to Create/Update |
|---|---------|------|---------|--------------------------|
| T3-1 | Transient Debug-Only Log Channel (lprint equivalent) | NEW | AutoAgent | Add to `autoagent-error-recovery-patterns.md` as Pattern 12 |
| T3-2 | Output Caps: Per-Source Capping Order Refinement | EXTENDED | autodream + autoresearch + AutoAgent | Update `autodream-context-patterns.md` |

---

## SECTION 5: SUMMARY STATISTICS

| Category | Count |
|----------|-------|
| Total cross-validated patterns examined | ~45 (including single-source unique) |
| CONFIRMED (already in >=1 existing file) | 35 |
| EXTENDED (existing but new material added) | 7 |
| NEW (not in any of the 8 existing files) | 7 |
| HEAVILY DUPLICATED (in 5+ files) | 3 (Terminal Signals, 3-Tier Retry, Token Counting) |
| SINGLY COVERED (in only 1 file) | 8 |

### Heavily Duplicated Patterns (Opportunity for Consolidation)

These patterns appear in 4+ files with overlapping but slightly different descriptions. They are candidates for consolidation into a single authoritative file:

1. **Structured Terminal Signals** (5 files): autoagent-gap-analysis.md, staged-event-driven-patterns.md, autoagent-progress-patterns.md, autoagent-error-recovery-patterns.md, autoagent-security-patterns.md.
   - **Recommendation**: Consolidate into `autoagent-error-recovery-patterns.md` Pattern 4 as the canonical version. Add cross-references from other files.

2. **3-Tier Retry Escalation** (6 files): autoagent-gap-analysis.md, staged-event-driven-patterns.md, autoagent-progress-patterns.md, autoagent-security-patterns.md, autoagent-error-recovery-patterns.md, high-impact-patterns.md.
   - **Recommendation**: Consolidate into `autoagent-error-recovery-patterns.md` Pattern 2 as the canonical version. Add cross-references from other files.

3. **Token Counting / Output Truncation** (4 files): autoagent-gap-analysis.md, autodream-context-patterns.md, autoagent-security-patterns.md, autoagent-error-recovery-patterns.md.
   - **Recommendation**: Consolidate into `autodream-context-patterns.md` Patterns 1+2 as the canonical version (it has the most complete caps table and truncation function spec). Add cross-references from other files.

### Files That Should Be Created (New Patterns)

1. `C:/Users/shiniyaya/Desktop/code-shiniyaya/memory/pre-action-reasoning-patterns.md` -- ThinkTool pattern, [REASON] block format, enforcement rules (T1-5)
2. `C:/Users/shiniyaya/Desktop/code-shiniyaya/memory/dual-signal-protocol.md` -- Combined pre-action + post-action protocol, weight penalties, escalation rules (T1-4)
3. `C:/Users/shiniyaya/Desktop/code-shiniyaya/memory/regression-gate-patterns.md` -- Regression gate before new work, baseline verification, broken-item re-queuing (T1-6)

### Files That Should Be Updated (Extended Patterns)

1. `high-impact-patterns.md` -- Update Pattern #3 (Immutable Checklist: add NEVER block, evidence field, SHA-256), Pattern #9 (NEVER STOP: add concrete conditions list), add Pattern #27 (Regression Gate)
2. `autoagent-error-recovery-patterns.md` -- Update Pattern 1 (add exit-code classification, no-reset rule), Pattern 2 (add injection block format), add Patterns 11 (Asymmetric Persistence Guards) and 12 (Transient Debug Channel)
3. `staged-event-driven-patterns.md` -- Update Finding 3 (add self-growing queue aspect), add Findings 12 (Clean Engine Reset) and 13 (Dual-Signal Protocol reference)
4. `autodream-context-patterns.md` -- Add dual-signal framing to context cap patterns
5. `autoagent-gap-analysis.md` -- Add new P2 entry for MC_MODE / Environment-Aware Output Degradation
