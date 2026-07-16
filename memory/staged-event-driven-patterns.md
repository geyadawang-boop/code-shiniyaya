# code-shiniyaya -- Event-Driven Orchestration Gap Findings (AutoAgent deep scan)

source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src
targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
scan date: 2026-07-16
dimension: Agent orchestration -- event-driven DAG engine, hub-and-spoke triage, transfer-back pattern, case_resolved/case_not_resolved signals

## Summary

code-shiniyaya v3.7.0 orchestrates agents through a hardcoded 7-step linear pipeline (diagnosis -> plan -> codex -> verify -> approve -> execute -> verify). Parallel fan-out exists only within steps (STEP 1 launches 6+ agents, STEP 4 launches 10+ agents), but step-to-step transitions are monolithic: all agents in a step must finish before the next step begins. AutoAgent provides a fundamentally different model: an event-driven DAG engine where steps declare their upstream dependencies, the engine fans out parallel work naturally, and downstream steps fire as soon as their upstream dependencies are satisfied (not when ALL parallel work completes).

Below are the concrete patterns AutoAgent implements that code-shiniyaya does NOT have, ranked by impact.

---

## P0 -- Critical Gaps (should add to SKILL.md immediately)

### Finding 1: case_resolved / case_not_resolved terminal signal protocol

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\tools\inner.py:4-24
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\main.py:50-80

**Pattern**: Agents explicitly signal terminal state via two structured tools:
- `case_resolved(result)` -- "work is done, here is the answer"
- `case_not_resolved(failure_reason, take_away_message)` -- "I tried everything and cannot solve this"

The main loop (main.py:50-72) checks the last message for these signals to decide: break (resolved), retry with error feedback (not resolved, attempt 1-2), escalate to meta-agent (not resolved, attempt 3+), or give up (all attempts exhausted).

**What code-shiniyaya lacks**: Agents in STEP 1 and STEP 4 produce verdicts (PASS/PARTIAL/FAIL) and issues arrays, but there is no formal "I am done and this is final" vs "I cannot proceed, my results are incomplete" signal. The orchestrator infers completion from the absence of ongoing agents, which is fragile -- a hung agent looks the same as an agent still working. The anti-hang-v2.md system detects stragglers by message-count gaps, but has no in-band signal from agents themselves.

**Concrete fix for SKILL.md** -- Add to the Agent Orchestration table and STEP 1/4 execution sections:

```
### Agent Terminal Signal Protocol

Every agent MUST return one of three terminal signals in its structured output:

1. `case_resolved` -- Work complete, findings are final. Equivalent to "I stand by these results."
2. `case_not_resolved` -- Cannot complete. MUST include `failure_reason` (why) and `partial_findings` (what was discovered before failure).
3. `case_interrupted` -- Agent was killed/stopped mid-work. Partial results may exist in journal but are not guaranteed complete.

**Orchestrator behavior on signal**:
- case_resolved + verdict=PASS -> mark slot complete, proceed
- case_resolved + verdict=FAIL/PARTIAL -> record findings, proceed
- case_not_resolved -> if another agent covers same dimension: discard; if unique dimension: flag for manual review OR retry with escalated prompt (max 1 retry)
- case_interrupted -> add to retry queue (max 2 retries per slot, per existing rule 7)
- NO signal after 3+ other agents complete -> STRAggler (anti-hang-v2.md detection)

**Integration with existing DAG (dag-{sessionId}.json)**: Add `signal` field to each edge's metadata:
```json
{
  "edges": [
    {"from": "bug-0", "to": "bug-1", "type": "blocks", "signal": "case_resolved"}
  ]
}
```
Only propagate dependencies when the blocking item's agent returns `case_resolved`.
```

**Priority**: P0 -- This replaces implicit "agent stopped producing output = done" with explicit termination signals, preventing the orchestrator from mistaking a hung agent for one still working.

---

### Finding 2: transfer-back completion pattern for agent handoff

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\agents\system_agent\system_triage_agent.py:49-63

**Pattern**: When a sub-agent finishes its sub-task, it explicitly calls `transfer_back_to_triage_agent(task_status)` to yield control back to the orchestrator. The triage agent then decides the next action (dispatch to another specialist, or signal completion). The transfer-back function is **dynamically appended** to each sub-agent's tool set at runtime (line 61-63):
```python
filesurfer_agent.functions.append(transfer_back_to_triage_agent)
websurfer_agent.functions.append(transfer_back_to_triage_agent)
coding_agent.functions.append(transfer_back_to_triage_agent)
```

This means agents operating within a team context gain the transfer-back tool, but the same agent running standalone does not have it -- the capability is context-dependent.

**What code-shiniyaya lacks**: code-shiniyaya launches agents in parallel batches, collects results after all agents finish (or timeout), then proceeds to the next step. There is no concept of an agent explicitly yielding control back to the orchestrator mid-execution. The orchestrator is passive -- it waits, then collects. This means:
- A fast agent that finishes in 30s must wait for the slowest agent (possibly 300s+) before its results are processed.
- If an agent discovers a blocking issue that should abort the entire batch, there is no way for it to signal this in-band.
- The orchestrator cannot dynamically re-route based on intermediate findings.

**Concrete fix for SKILL.md** -- Add after the "Agent Types" table:

```
### Agent Handoff Protocol (transfer-back)

Every agent in a managed batch gains an implicit `transfer_back` capability:

```
transfer_back(signal: "case_resolved" | "case_not_resolved" | "escalate",
              findings: str,
              recommendation: "continue" | "abort_batch" | "replan")
```

**Orchestrator behavior on transfer_back**:
- signal="case_resolved" + recommendation="continue" -> mark slot done, if all slots done -> next step
- signal="case_resolved" + recommendation="abort_batch" -> immediately signal remaining agents to stop, proceed with partial results
- signal="case_not_resolved" + recommendation="replan" -> mark slot failed, if >= 50% slots fail -> abort batch, re-enter STEP 2 (replan)
- signal="escalate" -> pause batch, present findings to user for manual decision

**First-completed fast path**: When ANY agent calls transfer_back with recommendation="abort_batch", the orchestrator immediately:
1. Calls TaskStop on all remaining agent task_ids in the batch
2. Processes the aborting agent's findings
3. Presents findings to user: "Agent {name} recommends aborting batch. Reason: {reason}. Continue with partial results?"
```

**Priority**: P0 -- This is the single biggest architectural gap. It transforms code-shiniyaya from batch-wait-then-process to stream-process-as-agents-complete.

---

### Finding 3: First-completed async dispatch (don't wait for slowest agent)

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:153-175

**Pattern**: The event engine uses `asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)` to process results incrementally. When any single task completes, its results are immediately dispatched to downstream events that depend on it. Other tasks continue running. New tasks (triggered by the completed event) are added to the active set. This is fundamentally different from a barrier model where all parallel work must finish before downstream work begins.

```python
# flow/core.py:153-175 (simplified)
tasks = set()
while len(queue) or len(tasks):
    this_batch_events = queue[:max_async_events] if max_async_events else queue
    queue = queue[max_async_events:] if max_async_events else []
    new_tasks = {asyncio.create_task(run_event(*run_event_input))
                 for run_event_input in this_batch_events}
    tasks.update(new_tasks)
    done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        await task  # handle exceptions
```

**What code-shiniyaya lacks**: STEP 1 launches 6+ agents, then waits for ALL to complete before proceeding to dedup/merge and STEP 2. STEP 4 launches 10+ agents, then waits for ALL before proceeding to STEP 5. This means the critical path is gated by the slowest agent, even though most agents finish quickly (P50=116s per progress-tracking.md).

**Concrete fix for SKILL.md** -- Add to the iteration scan workflow section and STEP 1/4 execution:

```
### First-Completed Dispatch (Streaming Step Transition)

Instead of: Launch N agents -> wait for ALL -> process -> next step
Use: Launch N agents -> process each as it completes -> trigger downstream work incrementally

**Implementation for STEP 1 (Diagnosis)**:
1. Launch 6+ agents in one parallel block
2. As each agent returns (log() event received):
   a. Extract findings immediately
   b. Dedup against already-received findings (same file:line+/-3 tolerance)
   c. If this agent's findings change the diagnosis materially (e.g., reveals a P0 crash):
      - Immediately begin STEP 2 plan generation for that P0 item
      - Do NOT wait for remaining agents
   d. If all agents return without new P0 discoveries:
      - Wait for remaining straggler check (3-message gap per anti-hang-v2.md)

**Implementation for STEP 4 (Codex Verification)**:
1. Launch 10+ agents across 7 dimensions
2. As each dimension's first agent returns:
   a. Mark that dimension as "covered"
   b. If Codex claim is FALSIFIED by any single dimension -> immediately flag as "Codex Gate FAIL"
   c. Do NOT wait for remaining dimensions -- Byzantine Codex defense triggers on first false claim
3. Remaining dimensions continue for completeness, but gating decision is made on first falsification

**Orchestrator pseudocode**:
```
pending = set(agent_task_ids)
results = {}
while pending:
    # CC reads log() output; each agent completion is a log event
    for completed_agent in newly_completed_agents():
        results[completed_agent.key] = completed_agent.verdict
        pending.remove(completed_agent.task_id)
        
        # Immediate dispatch check
        if completed_agent.verdict == "FAIL" and completed_agent.severity == "CRITICAL":
            trigger_downstream("STEP_2_PLAN", {"bug": completed_agent.issues[0]})
        if completed_agent.signal == "case_not_resolved":
            pending.add(retry_slot(completed_agent.key))  # max 2 retries
    
    # Straggler check (anti-hang-v2.md)
    if len(newly_completed) == 0 and message_gap >= 3:
        flag_stragglers(pending)
```

**Benefit**: For a 6-agent batch where P50=116s but max=600s, first-completed dispatch allows the orchestrator to begin STEP 2 work at ~120s instead of ~600s, a 5x reduction in critical path latency.
```

**Priority**: P0 -- Combined with Finding 2 (transfer-back), this enables streaming orchestration that processes results as they arrive rather than waiting for the slowest agent.

---

## P1 -- Important Gaps (should plan for next version)

### Finding 4: listen_group declarative step dependency

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:41-78

**Pattern**: Steps declare which upstream events they depend on via declarative decorators:

```python
# flow/core.py:41-78 (conceptual usage)
@engine.make_event
async def step_1_diagnose(event_input, global_ctx):
    ...  # run diagnosis agents

@engine.make_event
async def step_2_plan(event_input, global_ctx):
    ...  # generate plans

@engine.listen_group([step_1_diagnose], retrigger_type="all")
@engine.make_event
async def step_3_codex_text(event_input, global_ctx):
    ...  # only fires after step_1_diagnose completes
```

The engine automatically:
- Tracks which upstream events have fired
- Fires downstream events when all (or any) upstream dependencies are satisfied
- Prevents double-firing via `already_sent_to_event_group` dedup

`retrigger_type="all"` means the downstream event fires only after ALL upstream events complete (AND-gate). `retrigger_type="any"` means it fires after ANY upstream event completes (OR-gate).

**What code-shiniyaya lacks**: STEP transitions are hardcoded in prose (STEP 0 -> STEP 1 -> STEP 2 -> ...). There is no machine-readable dependency graph. The orchestrator must manually check "is STEP 1 done?" before entering STEP 2. This means:
- If a new intermediate step is added (e.g., STEP 2.5), every downstream step reference must be manually updated
- Conditional branching (e.g., "if Codex approved, skip STEP 5") is expressed as prose, not executable logic
- The DAG file (`dag-{sessionId}.json`) is populated after the fact for execution ordering, not used for step orchestration

**Concrete fix for SKILL.md** -- Add as a new section "Step Dependency Model":

```
### Declarative Step Dependency Model (replaces hardcoded STEP transitions)

Each step declares its upstream dependencies. The orchestrator resolves the DAG and executes steps as their dependencies are satisfied.

```
STEP_1_DIAGNOSE:
  depends_on: [STEP_0_PRECHECK]
  trigger: all  # fire after STEP_0 completes
  agents: 6+

STEP_2_PLAN:
  depends_on: [STEP_1_DIAGNOSE]
  trigger: all  # fire after all diagnosis agents complete
  agents: 3 (compare)

STEP_3_CODEX_TEXT:
  depends_on: [STEP_2_PLAN]
  trigger: all

STEP_4_CODEX_VERIFY:
  depends_on: [STEP_3_CODEX_TEXT]
  trigger: any  # fire as soon as Codex response received (don't wait for user acknowledgment)

STEP_5_GATE:
  depends_on: [STEP_4_CODEX_VERIFY, USER_APPROVAL]
  trigger: all  # requires both Codex verification AND user approval

STEP_6_EXECUTE:
  depends_on: [STEP_5_GATE]
  trigger: any  # execute each approved item as soon as its dependencies are met

STEP_7_VERIFY:
  depends_on: [STEP_6_EXECUTE]
  trigger: all  # verify after all fixes applied
```

**Engine pseudocode (CC-compatible, no async runtime)**:
```
def resolve_next_steps(completed_steps, dag):
    ready = []
    for step in dag.steps:
        if step.status == "done":
            continue
        upstream_done = all(dep in completed_steps for dep in step.depends_on)
        if step.trigger == "any":
            upstream_done = any(dep in completed_steps for dep in step.depends_on)
        if upstream_done:
            ready.append(step)
    return ready
```

**Integration with existing DAG file**: The dag-{sessionId}.json currently stores edges for execution ordering. Extend it to also store step-level edges:
```json
{
  "steps": {
    "STEP_1_DIAGNOSE": {"depends_on": ["STEP_0"], "trigger": "all", "status": "done"},
    "STEP_2_PLAN": {"depends_on": ["STEP_1_DIAGNOSE"], "trigger": "all", "status": "pending"}
  }
}
```
```

**Priority**: P1 -- Declarative dependencies make the orchestrator more maintainable and enable the streaming dispatch from Findings 2-3. Without this, first-completed dispatch must be hand-coded per step.

---

### Finding 5: Hub-and-Spoke Triage Routing

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\agents\system_agent\system_triage_agent.py:8-64

**Pattern**: A central "System Triage Agent" receives the user's request, determines which specialist agent is best suited, transfers the task to that specialist, receives the result via transfer-back, and either dispatches to another specialist or signals completion. The triage agent has access to `case_resolved` and `case_not_resolved` tools.

Specialist agents do NOT need to know about each other -- they only know about the triage agent (via `transfer_back_to_triage_agent`).

**What code-shiniyaya lacks**: code-shiniyaya always launches ALL agent types in parallel for STEP 1 (investigator + Explore + general-purpose + Plan + debugging). There is no intelligent routing. This wastes capacity -- if the bug is a simple null-pointer, the Plan agent's architectural analysis is unnecessary. If the bug is a design-level issue, the investigator's byte-level scan is low-value.

code-shiniyaya has a "type unavailability" fallback chain (investigator -> Explore -> general-purpose), but this is about agent availability, not about task-appropriate routing.

**Concrete fix for SKILL.md** -- Add to the Agent Orchestration section:

```
### Hub-and-Spoke Triage Routing (replaces always-launch-all)

**Model**: One triage agent + N specialist agents. Triage routes tasks; specialists execute and transfer back.

**STEP 1 (Diagnosis) with Triage**:
1. CC launches 1 triage agent with the full bug context
2. Triage agent analyzes the bug and decides which specialist(s) to invoke:
   - Null-pointer / type error / syntax issue -> investigator (byte-level)
   - Missing feature / logic gap -> general-purpose (logic)
   - Cross-file dependency / architectural -> Plan (architecture)
   - Runtime crash / hang -> debugging (runtime)
   - Multi-domain concern -> multiple specialists sequentially
3. Triage dispatches to first specialist via `transfer_to_{specialist}(sub_task_description)`
4. Specialist works, then calls `transfer_back_to_triage_agent(task_status)`
5. Triage evaluates result, decides: done? dispatch to another specialist? escalate?
6. Triage signals `case_resolved` or `case_not_resolved` to CC

**When to use triage vs. parallel launch**:
- P0 crash/security bug -> parallel launch (speed trumps efficiency; every perspective matters)
- P1/P2 bug -> triage routing (efficiency; targeted analysis sufficient)
- Unknown scope -> triage first, expand to parallel if triage can't determine scope

**Triage agent prompt template**:
```
You are a bug triage specialist. Given a bug report, determine which specialist(s) to invoke.

Available specialists:
- investigator: byte-level code analysis, null-pointer, type errors, syntax
- general-purpose: logic errors, missing features, algorithm issues  
- Plan: architectural issues, cross-file dependencies, design patterns
- debugging: runtime crashes, hangs, memory issues

For each bug:
1. Classify the bug type
2. Select the most appropriate specialist
3. If uncertain, start with general-purpose (widest coverage)
4. After specialist returns, evaluate: is this sufficient? If not, dispatch to another.
5. When analysis is complete, call case_resolved with consolidated findings.

NEVER launch all specialists "just to be safe." Be targeted.
```

**Benefit**: For P1/P2 bugs, triage routing uses 1-2 agent invocations instead of 6+, reducing cost by 60-80% per diagnosis cycle.
```

**Priority**: P1 -- Not as critical as Findings 1-3 because the parallel-launch-all approach does work correctly (just inefficiently). However, for cost-conscious operation, triage routing is a major efficiency gain.

---

### Finding 6: 3-Tier Retry with Meta-Agent Escalation

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\main.py:43-80

**Pattern**: When `case_not_resolved` is returned, the system retries with escalating strategies:

```
Tier 1 (attempt 1-2): Same agent, but inject last error as feedback
  -> messages.append({"role": "user", "content": "Please try again. Previous attempt: {error}"})

Tier 2 (attempt 3+): Escalate to meta-agent with full tool access
  -> meta_agent gets all tools + case_resolved/case_not_resolved
  -> meta_agent prompt: "Existing agents failed. Create new tools if needed. 
     Use existing tools where possible. NEVER give up with case_not_resolved 
     without trying to create new tools."

Tier 3 (meta-agent also fails): Final case_not_resolved with full failure chain
  -> Return to user with complete failure analysis
```

**What code-shiniyaya lacks**: Rule 7 handles agent failure by replacing the agent in the same slot (max 2 replacements, 3rd = permanent failure). But there is no escalation to a more powerful agent type, no injection of previous error as feedback, and no meta-agent tier that can create new tools to solve the problem.

**Concrete fix for SKILL.md** -- Extend Rule 7:

```
### Rule 7 (Extended) -- Agent Failure with Tiered Escalation

**Current (v3.7.0)**: Slot replacement, max 2 per slot, 3rd = permanent failure.

**Extended (v3.8.0)**:
- Tier 1 (attempt 1-2): Replace agent in same slot with same type, inject previous error as context:
  ```
  "The previous agent ({type}) failed on this task. Error: {failure_reason}.
   Please attempt a different approach. What they tried: {previous_approach}"
  ```
- Tier 2 (attempt 3): Escalate to meta-agent (general-purpose with all tools + agent creation capability):
  ```
  "Two {type} agents have failed on this task. You have full tool access and can 
   create new tools if needed. Failures so far: {failure_chain}. 
   You CANNOT return case_not_resolved -- you must find a solution or create one."
  ```
- Tier 3 (meta-agent fails): Permanent failure. Record in FAILED_FIXES.md with full escalation chain.
  Signal `case_not_resolved` to orchestrator with `failure_chain` and `take_away_message`.

**Integration with existing rule**: The "max 2 replacements" from rule 7 becomes Tier 1. Tier 2 is new. The existing "3rd = permanent" maps to Tier 3.
```

**Priority**: P1 -- This improves recovery from the 9.5% agent hang rate (per progress-tracking.md empirical data) by giving failed slots a second chance with a more capable agent, rather than just retrying the same type.

---

### Finding 7: GOTO and ABORT dynamic control flow

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\dynamic.py:1-18
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:80-81, 101-113

**Pattern**: Events can return `_SpecialEventReturn` with `ReturnBehavior.GOTO` or `ReturnBehavior.ABORT` to dynamically alter the execution flow:

```python
# flow/dynamic.py
def goto_events(group_markers, any_return=None):
    return _SpecialEventReturn(behavior=ReturnBehavior.GOTO, returns=(group_markers, any_return))

def abort_this():
    return _SpecialEventReturn(behavior=ReturnBehavior.ABORT, returns=None)
```

When an event returns `GOTO`, the engine jumps to the specified event group, bypassing the normal dispatch chain. When an event returns `ABORT`, the entire DAG execution terminates.

**What code-shiniyaya lacks**: The stop/interrupt mechanism (rule 13) handles external termination (user says "stop"), but there is no in-band mechanism for an agent to say "based on what I found, we should skip the next 3 steps and go directly to execution" or "this is unfixable, abort the entire workflow."

The 7-step pipeline is strictly linear. An agent in STEP 1 that discovers the bug is already fixed cannot signal "skip to STEP 7 for verification" -- it must wait for all agents to finish, then the orchestrator goes through STEPS 2-6 anyway.

**Concrete fix for SKILL.md** -- Add to the Agent Handoff Protocol section:

```
### Dynamic Flow Control (GOTO / ABORT)

Agents can return flow control directives in their transfer_back signal:

**GOTO(target_step, reason)**:
- Usage: Agent discovers information that makes intermediate steps unnecessary
- Example: STEP 1 agent finds the bug is already fixed in the current codebase -> 
  `transfer_back(signal="case_resolved", recommendation="goto:STEP_7", 
   reason="Bug already resolved in current HEAD -- skipping to verification")`
- Orchestrator behavior:
  1. Mark all skipped steps (STEP_2 through STEP_6) as SKIPPED with reason
  2. Immediately transition to target_step
  3. Log in session JSON: `{"goto": {"from": "STEP_1", "to": "STEP_7", "reason": "..."}}`

**ABORT(reason)**:
- Usage: Agent discovers unfixable condition
- Example: STEP 1 agent finds the bug requires a dependency that doesn't exist on this platform ->
  `transfer_back(signal="case_not_resolved", recommendation="abort", 
   reason="Required library not available on Windows -- cannot fix")`
- Orchestrator behavior:
  1. Immediately stop all running agents (TaskStop on all background_task_ids)
  2. Write ABORT_LOG.md with the aborting agent's full findings
  3. Present to user: "Workflow aborted. Reason: {reason}. See ABORT_LOG.md for details."
  4. Do NOT proceed to next step

**Safeguards**:
- GOTO can only skip forward (target_step > current_step) -- no backward jumps (infinite loop prevention)
- ABORT requires user confirmation before stopping other agents (unless P0 security issue)
- Both GOTO and ABORT are recorded in session JSON with full reasoning for auditability
```

**Priority**: P1 -- GOTO enables significant latency reduction (skip unnecessary steps) and ABORT prevents wasted work on unfixable issues. However, it requires the first-completed dispatch (Finding 3) to be useful -- without streaming dispatch, an agent's GOTO signal would be discovered too late.

---

## P2 -- Nice-to-Have Improvements

### Finding 8: Event Identity via Source Code Hash

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\types.py:84-99
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\utils.py:47-48

**Pattern**: Event IDs are deterministic MD5 hashes of the function source code:
```python
self.id = string_to_md5_hash(function_or_method_to_string(self.func_inst))
```

This means the same task always gets the same ID across sessions, making it possible to deduplicate work across sessions. If the same bug is diagnosed in two different sessions, the event ID is the same.

**What code-shiniyaya lacks**: Task/agent IDs are random (UUIDs or sequential indices). There is no way to recognize "we've already analyzed this exact code" across sessions.

**Concrete fix**: Extend `session-{id}.json` to include content-hash-based task deduplication:
```json
{
  "taskFingerprints": {
    "md5:bug-0+STEP_1": {"lastResult": "PASS", "lastSession": "a1b2c3d4", "lastTs": "..."}
  }
}
```
Before launching an agent for a known (file+line+step) combination, check if a recent fingerprint exists with the same git blob hash. If so, reuse the previous result (with user confirmation).

**Priority**: P2 -- Nice optimization for repeated scans of the same codebase.

---

### Finding 9: Global Context Passthrough

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:87, 96

**Pattern**: The `global_ctx` object is passed through every event invocation:
```python
result = await current_event.solo_run(current_event_input, global_ctx)
```

This allows events to read and write shared state without knowing about each other. The context accumulates results as the DAG executes.

**What code-shiniyaya lacks**: State is passed between steps via session JSON files written to disk. This is durable (survives crashes) but slow (disk I/O between every step). A hybrid approach -- in-memory context with periodic disk sync -- would be faster without sacrificing durability.

**Concrete fix**: Not a SKILL.md change; this is an implementation detail for the orchestrator. CC would maintain an in-memory `WorkflowContext` dict during a session, synced to `session-{id}.json` at step boundaries.

**Priority**: P2 -- Performance optimization, not functional.

---

### Finding 10: Runtime Tool Set Extension

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\agents\system_agent\system_triage_agent.py:60-63

**Pattern**: Sub-agents have their tool sets extended at runtime to include team-context tools:
```python
filesurfer_agent.functions.append(transfer_back_to_triage_agent)
```

This means the same agent definition can be used standalone (without transfer_back) or in a team context (with transfer_back). The capability is context-dependent, not hardcoded.

**What code-shiniyaya lacks**: Agent capabilities are statically defined by agent type. There's no mechanism to give an agent additional tools based on its role in the current workflow. For example, a Plan agent in STEP 1 (diagnosis) might benefit from having access to the DAG file, but the same Plan agent in STEP 2 (plan generation) doesn't need it.

**Concrete fix**: Add to the Agent Orchestration table:
```
### Context-Dependent Tool Injection

Before launching an agent, the orchestrator injects context-specific tools:

| Context | Injected Tools |
|---------|---------------|
| STEP 1 (diagnosis) | read_dag, read_session_state, transfer_back |
| STEP 4 (codex verify) | read_codex_response, cross_reference, transfer_back |
| STEP 6 (execute) | read_dag, git_diff, ast_verify, transfer_back |
| Any batch context | transfer_back, report_straggler |

Tools are removed after the agent completes (not persisted to the agent definition).
```

**Priority**: P2 -- Enables cleaner agent prompts (agents don't need to know about tools they can't use).

---

### Finding 11: already_sent_to_event_group Deduplication

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:119-151

**Pattern**: The engine tracks which event groups have already been dispatched to each downstream event:
```python
this_run_ctx[current_event.id] = {
    "result": result,
    "already_sent_to_event_group": set(),  # tracks dispatched groups
}
```

When all upstream events for a group complete, the engine checks if this group was already dispatched. If so (and `retrigger_type="all"`), it skips to prevent double-firing.

**What code-shiniyaya lacks**: The dedup in STEP 1 (bug findings dedup by file:line+/-3) handles within-step deduplication of agent findings. But there is no cross-step dedup -- if the same issue triggers STEP 2 planning AND STEP 4 codex verification, there's no mechanism to prevent double-processing.

**Concrete fix**: Extend the DAG's edge dedup to include an `already_processed` set:
```json
{
  "edges": [...],
  "processedGroups": {
    "bug-0:STEP_2_PLAN": "2026-07-16T14:30:00Z",
    "bug-0:STEP_6_EXECUTE": "2026-07-16T14:35:00Z"
  }
}
```
Before processing a (bug, step) pair, check if it's already been processed. Skip if yes.

**Priority**: P2 -- Existing single-session usage makes this unlikely to trigger, but it becomes important with streaming dispatch (Finding 3) where downstream steps can be triggered multiple times.

---

## Consolidation: What to Actually Change

### Immediate (P0 -- add to SKILL.md v3.8.0)

1. **Agent Terminal Signal Protocol** (Finding 1) -- New section in SKILL.md under "Agent Orchestration." Replaces implicit completion detection with explicit `case_resolved`/`case_not_resolved` signals.

2. **Agent Handoff Protocol** (Finding 2) -- New section defining `transfer_back` semantics. Enables streaming orchestration.

3. **First-Completed Dispatch** (Finding 3) -- Extends the "Iterative Scan Workflow" section and STEP 1/4 execution. Replaces barrier-wait with incremental processing.

### Planned (P1 -- design for v3.9.0)

4. **Declarative Step Dependencies** (Finding 4) -- Replaces hardcoded STEP transitions. Requires Findings 1-3 as prerequisites.

5. **Hub-and-Spoke Triage** (Finding 5) -- Optional routing mode for P1/P2 bugs. Reduces agent cost.

6. **3-Tier Retry Escalation** (Finding 6) -- Extends Rule 7 with meta-agent tier.

7. **GOTO/ABORT Flow Control** (Finding 7) -- Dynamic step skipping. Requires Finding 3 as prerequisite.

### Backlog (P2 -- record in high-impact-patterns.md)

8. Content-hash task dedup (Finding 8)
9. Global context passthrough (Finding 9)
10. Runtime tool injection (Finding 10)
11. Cross-step dedup (Finding 11)

---

## Files to Update

| File | Section | Findings |
|------|---------|----------|
| SKILL.md | "Agent 编排" table | Add Terminal Signal column (F1) |
| SKILL.md | After Agent Orchestration table | Add "Agent Terminal Signal Protocol" (F1) |
| SKILL.md | After Agent Orchestration table | Add "Agent Handoff Protocol" (F2) |
| SKILL.md | "迭代扫描工作流" section | Add "First-Completed Dispatch" (F3) |
| SKILL.md | STEP 1, STEP 4 execution | Add streaming dispatch logic (F3) |
| SKILL.md | Rule 7 (Agent failure) | Extend with 3-tier escalation (F6) |
| SKILL.md | After Rule 13 (stop) | Add "Dynamic Flow Control" (F7) |
| SKILL.md | "Step Dependency Model" section | New section (F4) |
| SKILL.md | Agent Orchestration table | Add "Triage Routing" mode column (F5) |
| memory/high-impact-patterns.md | Pattern 6 (Event-Driven DAG) | Expand with F8-F11 details |
| memory/high-impact-patterns.md | Pattern 8 (3-Tier Retry) | Expand with escalation chain details |
