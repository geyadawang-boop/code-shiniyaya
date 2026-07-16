# Anti-Hang System v2.2 — CC Constraints + Crash Classification + Context Caps

Cross-validated from 4 OS sources (AutoAgent, autodream, autoresearch, autonomous-coding).
Key insight: **CC has no event loop, cannot poll, cannot read files mid-workflow, cannot track wall-clock time.** The system must work WITH these constraints, not against them.

## Core Design Shift: Workflow-Inline Progress

BEFORE (broken): Workflow launches → CC polls status.json every 60s → CC detects hangs → CC calls TaskStop
AFTER (works): Workflow logs ALL progress inline → CC reads log() output naturally → hang detection based on message count + log gap

## v2.2 New: Input Caps (from autodream MAX_* constants)

Every data source entering any agent prompt MUST have explicit bounds. Capped at prompt assembly time, not collection time.

| Cap constant | Value | Applies to |
|---|---|---|
| MAX_FINDINGS_PER_DIMENSION | 8 | Agent findings per verification dimension |
| MAX_FINDING_CHARS | 600 | Per-finding character limit (head-tail truncated) |
| MAX_SOURCE_FILE_CHARS | 2000 | Per source file loaded for cross-reference |
| MAX_CODEX_FEEDBACK_CHARS | 8000 | Total Codex feedback pasted by user |
| MAX_VERIFY_PROMPT_CHARS | 12000 | Total assembled STEP 4 prompt |

## v2.2 New: Head-Tail Truncation

```python
def truncate_for_prompt(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 9
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()
```

60% head (context), 40% tail (conclusions). "\n...\n" marker signals LLM that content was elided.

## v2.2 New: Crash Classification (from autoresearch + autonomous-coding)

Two-category taxonomy integrated with retry logic:

- **Type A (Trivial)**: Typos, missing imports, syntax errors → auto-fix + retry, does NOT consume retry quota
- **Type B (Fundamental)**: OOM, architecture broken, permission denied → consumes retry quota, 3 strikes → terminate

Classification check (from autonomous-coding loop.py:84-113): check error type + error message substring against known patterns.

## v2.2 New: Exponential Backoff on Agent API Errors

Agent API call failure → retry with backoff:
- Attempt 1: immediate
- Attempt 2: 10s delay
- Attempt 3: 30s delay
- Attempt 4: 180s delay

Match error types: APIError, ConnectionError, Timeout, RateLimitError.
Non-matching errors (permission denied, invalid request): fail immediately, no retry.
All 4 attempts fail → escalate to general-purpose agent (3-tier retry).

## What Actually Works

### 1. Inline Progress via log()

Workflow scripts MUST use `log()` on every agent start, every agent result, and on any anomaly. CC reads these naturally as part of conversation flow.

```
log('Agent cold starting')
log('Agent cold returned verdict=PASS')
log('Agent silent starting')
log('Agent silent returned verdict=FAIL')
...
log('FINAL: 0P/2I/6F/20C/36H | goal=NO')
```

No status.json. No polling. No CronCreate. CC sees progress as text in conversation.

### 2. Hang Detection: Message-Count Based (same as Codex silence)

- No log() event with an agent result for 3+ consecutive agent completions by other agents → that agent is a STRAggler
- Workflow produces no log() events for 5+ user turns → workflow is STALLED
- These are the SAME mechanism as Codex silence detection (N=4 threshold)

### 3. What CC Actually Does (Manual, Same as Codex)

- After workflow launch: "8 agents scanning. Results will appear as they complete."
- When agent results arrive via log(): natural conversation flow, CC summarizes when all done
- If user asks "is it stuck?": CC checks if any agents launched but not returned (from log history). Reports stragglers.
- If all agents done and goal=NO: CC extracts findings, applies fixes, launches next iteration
- If workflow seems stalled (5 user turns, no results): "Workflow may be stalled. Continue waiting or kill+retry?"

### 4. Partial Recovery (After Manual Kill)

User says "kill it" → CC calls TaskStop(background_task_id) → journal.jsonl has partial results → journal-parser.py extracts them → continuation-planner.py identifies uncovered slots → new workflow launched with resumeFromRunId

### 5. Convergence Tracking

Same formula: CR = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1} × 100
But tracked BY CC across iterations, not by workflow scripts.
CR < 0 two times → CC auto-switches strategy (different agent types, different scan dimensions) WITHOUT stopping iteration or waiting for user. Per SKILL.md rule 15 + 趋同检测 section (see SKILL.md 趋同速率 formula near end of file).

## Agent Selection Matrix

| Task | Primary | Fallback | Timeout | Notes |
|------|---------|----------|---------|-------|
| File scan | caveman:cavecrew-investigator | general-purpose | 300s | Fastest |
| Cross-reference | general-purpose | caveman:cavecrew-investigator | 600s | **Never Explore** |
| Logic/security | general-purpose | caveman:cavecrew-investigator | 600s | Deep thinking |
| Stress test | general-purpose | caveman:cavecrew-investigator | 600s | Simulation |
| Simple verify | caveman:cavecrew-investigator | general-purpose | 120s | Fast check |

**Explore Exclusion**: Never for xref/multi-file/dependency tasks (>10% hang rate).

## Optimal Batching

- Agent count per workflow = batch_size = max(4, min(16, cpu_cores-2)), cpu_cores via `python -c "import os; print(os.cpu_count() or 4)"`, fallback=4
- Total agent cap: 50
- Start all 8 in 1 parallel block (no phase gates)
- Dynamic replacement: after manual kill, re-launch only uncovered slots
- Max 2 retries per slot

## KEEP List (files that still work)

1. journal-parser.py — partial result extraction
2. continuation-planner.py — uncovered slot identification
3. resume-protocol.md — procedural documentation

## DEFERRED/KEEP List (from v4.2.6 cleanup)

All 5 files below remain on disk and are actively referenced by SKILL.md. Deletion deferred pending SKILL.md reference cleanup.

1. time-escalation.md — CronCreate-based, impossible without timers → DEFERRED
2. progress-experience-design.md — 7 checkpoint templates assuming CC can poll → DEFERRED
3. progress-tracking.md — workflow script template now superseded by inline log() → DEFERRED
4. anti-hang-v2.md — **NOT deleted: still authoritative for SKILL.md references** → KEEP
5. scan-state.schema.json — **NOT deleted: actively referenced by SKILL.md L768, journal-parser.py, continuation-planner.py** → KEEP

## What CC Tells the User (3 messages only)

### At launch
```
[iter#{N}] 8 agents scanning v{V}. Results will stream as agents complete.
```

### When all done (natural log() output provides per-agent timing)
```
[iter#{N}] COMPLETE: {p}P/{pt}I/{f}F/{c}C/{h}H | goal={YES/NO}
```

### If user inquires about progress
```
[iter#{N}] {done}/8 done. Running: {still_running_keys}. No stragglers exceeding 3-message gap.
```

## Constraints Accepted (Not Fought)

1. CC has no event loop → no polling, no CronCreate, no ScheduleWakeup
2. CC has no wall-clock → no time-based timeouts
3. CC cannot read workflow output mid-execution → rely on log() events
4. Workflow scripts cannot use Date.now() → no timestamps in logs
5. TaskStop needs background_task_id → CC must capture the task_id from Workflow tool result
