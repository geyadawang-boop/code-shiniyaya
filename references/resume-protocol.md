# Multi-Agent Scan RESUME Protocol v1.0.0

Design for recovering partial results from killed/stuck multi-agent scan workflows and enabling incremental continuation without re-running already-verified dimensions.

## Problem Statement

When a 10-agent scan workflow is killed mid-way (e.g., 7 agents returned results, 3 hung), the partial results in `journal.jsonl` are lost to the orchestrator. Without a recovery mechanism, the next iteration must re-launch all 10 agents, wasting API cost and time on already-verified dimensions.

## Journal Format (observed from real CC workflow directories)

Each workflow directory under `{session}/subagents/workflows/{wf_id}/` contains:

```
wf_d93815ef-cfe/
  journal.jsonl           # Workflow-level event log (started/result pairs)
  agent-{agentId}.jsonl   # Full agent conversation transcript
  agent-{agentId}.meta.json  # {"agentType":"workflow-subagent","spawnDepth":1}
```

### journal.jsonl line types

**`type: "started"`** — Agent launched:
```json
{"type":"started","key":"v2:<sha256-hash>","agentId":"a3badee85e3e20804"}
```

**`type: "result"`** — Agent returned structured output:
```json
{"type":"result","key":"v2:<sha256-hash>","agentId":"ab1b50f44f591827a",
 "result":{"verdict":"PASS|PARTIAL|FAIL","issues":[...]}}
```

Key properties:
- The `key` field is a v2-hash that uniquely identifies the agent task. Same key appears in both `started` and `result` lines.
- The `result` field is only present on `type: "result"` lines.
- Gap between `started` count and `result` count = number of hung/killed agents.
- Hung agents have NO `type: "result"` line — they simply stop mid-conversation.
- The agent's per-file journal (`agent-{id}.jsonl`) contains the full prompt and partial conversation if the agent was mid-work when killed.

### Real-world examples

| Workflow | Started | Result | Gap | Status |
|----------|---------|--------|-----|--------|
| wf_1d6b8bed-f25 | 4 | 3 | 1 | 1 hung |
| wf_3cbfdace-b8d | 10 | 10 | 0 | Clean complete |
| wf_3d7d4cc5-03c | 8 | 0 | 8 | All killed immediately |
| wf_d93815ef-cfe | 8 | 4 | 4 | 4 hung mid-scan |

## Protocol Design

### 1. Post-Mortem Analysis: journal-parser.py

Parses a workflow's `journal.jsonl` to:
1. Extract all completed agent results (verdict + issues)
2. Identify hung agents (started but no result)
3. Compute summary statistics
4. Generate a `scan-state-{iter}.json` file for continuation

**Recovery algorithm:**
```
1. Read journal.jsonl line by line
2. Build a map: key -> {started, result}
3. For each key with a result: extract verdict, issues, agentId
4. For each key with only started: mark as TIMED_OUT
5. Compute summary: pass/partial/fail counts, severity distribution
6. Generate continuation plan: retryKeys = keys with no result
7. Write scan-state-{iter}.json
```

### 2. scan-state-{iter}.json Schema

Tracks per-dimension status across iterations, enabling:
- Incremental re-scan (only re-run hung/failed dimensions)
- Accumulation of issues across iterations
- Audit trail of which dimensions were verified when

### 3. Continuation Pattern

When resuming a killed workflow:
```
IF scan-state-{iter}.json exists:
  completedKeys = state.continuation.completedKeys
  retryKeys = state.continuation.retryKeys

  IF retryKeys is empty:
    All dimensions complete. Aggregate final results.
  ELSE:
    Launch new workflow with ONLY retryKeys (not all 10).
    New workflow produces scan-state-{iter+1}.json
    Merge: new state inherits completedKeys from previous + adds own results
```

### 4. Incremental Iteration Loop

```
Iteration 1: Launch 10 agents -> 7 return, 3 hung
  -> scan-state-1.json: 7 clean, 3 pending

Iteration 2: Launch 3 agents (only pending dimensions) -> all 3 return
  -> scan-state-2.json: 10 clean, 0 pending

Final aggregation: merge scan-state-1 + scan-state-2 completed dimensions
```

### 5. Integration with code-shiniyaya SKILL.md v3.2

The existing stop/interrupt mechanism (rules 12-14, error handling table rows for STEP 1) handles item-level recovery within a session. The RESUME protocol extends this to **workflow-level recovery across sessions** — when an entire workflow is killed by `TaskStop` or exceeds the 600s timeout.

See `resume-workflow.md` for the workflow template and `journal-parser.py` for the recovery script.
