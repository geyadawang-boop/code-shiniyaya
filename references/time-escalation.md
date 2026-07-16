# Time-Based Escalation System for code-shiniyaya Agent Workflows

Designed 2026-07-15. Integrates with `SKILL.md` v3.2.0 error handling and `references/progress-tracking.md` workflow patterns.

---

## 1. Tier Escalation Table

| Property | TIER 1 - GREEN | TIER 2 - YELLOW | TIER 3 - ORANGE | TIER 4 - RED |
|---|---|---|---|---|
| **Name** | Normal | Slow | Suspicious | Stuck |
| **Trigger (wall-clock)** | Agent returns **under 120s** | Agent exceeds **120s**, under 300s | Agent exceeds **300s** (5 min) | Agent exceeds **600s** (10 min) |
| **Trigger (message count)** | N/A | N/A | Agent produces 0 log events for 180s | Agent produces 0 log events for 300s |
| **Trigger logic** | Implicit: tier-2 check fires and finds workflow already complete | wall-clock AND (% agents still running > 30% OR single agent > 120s elapsed) | wall-clock AND workflow not complete AND no `workflow_complete` in journal | wall-clock AND workflow not complete AND `agents_done < agents_launched` |
| **CC action** | None | Log warning to `journal.jsonl`; if >30% of agents are yellow, flag as "unusual — possible system load" | Notify user via `send_message` to parent session: "Agent {name} running for 5+ min — may be stuck. Continue waiting or skip?" | Auto-kill workflow via `TaskStop`; parse partial results from `journal.jsonl` |
| **User communication** | None (transparent) | None unless >30% yellow, then: "[!] {n}/{total} agents still running after 2 min — possible system load" | "Agent {name} running for 5+ min — may be stuck. Continue waiting or skip?" | "Killed stuck workflow. {n}/{total} agents completed. Proceeding with partial results. Missing agents: {list}" |
| **Recovery path** | N/A | Wait; agents expected to complete normally. If >30% persists past 300s, escalate to tier 3. | If user says "skip": `TaskStop(workflow_task_id)`, parse journal.jsonl for completed agent results, re-run ONLY failed/missing dimensions. If user says "continue": reset tier 3 check (re-arm another +300s `fireAt` task). | Recover partial results from journal.jsonl: collect all `type: "result"` entries, aggregate findings, proceed to fix phase. Missing agents logged as `"unavailable"` — do NOT block the iteration. |
| **Detection mechanism** | CronCreate `fireAt` task at +120s finds workflow already complete → self-dismiss | CronCreate `fireAt` task at +120s reads journal, finds agents still running, writes warning | CronCreate `fireAt` task at +300s reads journal, finds workflow incomplete, messages parent session | CronCreate `fireAt` task at +600s reads journal, finds workflow incomplete, calls `TaskStop` |

---

## 2. Detection: Wall-Clock vs Message Count

| Dimension | Wall-clock time | Message count (journal events) |
|---|---|---|
| **Used for** | Tier 2/3/4 primary triggers | Tier 3/4 secondary confirmation |
| **Why primary** | Agents can hang silently (no log events, no messages). Wall-clock directly measures user-experienced delay. | Message-count is the existing pattern in SKILL.md for Codex silence (N=4). For agent hangs, it is supplementary: if wall-clock > 300s AND no journal events in 180s, confidence of "stuck" is higher. |
| **Implementation** | `fireAt` timestamps computed from `workflow_start` | Tier check task reads journal.jsonl, finds `MAX(timestamp)` among `agent_start`/`agent_result` entries, computes gap from `now` |

**Decision: wall-clock is primary. Message/event gap is a confidence booster for tier 3/4, not a standalone trigger.**

---

## 3. CronCreate-Based Implementation

### 3.1 Architecture

```
Workflow Launch
  |
  +---> Write journal.jsonl: {"type": "workflow_start", "workflow_id": "wf-abc123", ...}
  |
  +---> Create 3 one-time scheduled tasks (fireAt):
  |       wf-abc123-tier2  →  now + 120s
  |       wf-abc123-tier3  →  now + 300s
  |       wf-abc123-tier4  →  now + 600s
  |
  +---> Launch agents in parallel
  |
  +---> On workflow completion:
          +---> CronDelete all 3 tier tasks
          +---> Write journal.jsonl: {"type": "workflow_complete", ...}

If CronCreate task fires before workflow completes:
  |
  +---> Task reads journal.jsonl
  +---> If workflow_complete found → exit silently (race condition safe)
  +---> If workflow still running → execute tier escalation action
```

### 3.2 Exact fireAt Expressions

`fireAt` uses ISO 8601 with timezone offset. Computed at workflow launch:

```javascript
var now = new Date()

var tier2FireAt = new Date(now.getTime() + 120000).toISOString()
// Example: "2026-07-15T14:02:00.000+08:00"

var tier3FireAt = new Date(now.getTime() + 300000).toISOString()
// Example: "2026-07-15T14:05:00.000+08:00"

var tier4FireAt = new Date(now.getTime() + 600000).toISOString()
// Example: "2026-07-15T14:10:00.000+08:00"
```

**Why `fireAt` (not `cronExpression`):** These are one-shot checks. Using `cronExpression` would create recurring tasks that fire every day at the same wall-clock time — wrong semantics. `fireAt` gives us a single fire at the exact boundary computed from workflow start.

### 3.3 Task IDs and Lifecycle

| Task ID pattern | `fireAt` | Action on fire | Deleted when |
|---|---|---|---|
| `wf-{workflow_id}-tier2` | `start + 120s` | Read journal, log warning if >30% still running | Workflow completes naturally OR tier 2 task fires and self-dismisses |
| `wf-{workflow_id}-tier3` | `start + 300s` | Read journal, send_message to parent session if workflow incomplete | Workflow completes naturally OR user responds to tier 3 notification |
| `wf-{workflow_id}-tier4` | `start + 600s` | Read journal, TaskStop + parse partial results if still running | Workflow completes naturally OR tier 4 task fires and kills workflow |

**Cleanup on natural completion:**
```javascript
// In workflow completion handler:
delete_scheduled_task("wf-" + workflow_id + "-tier2")
delete_scheduled_task("wf-" + workflow_id + "-tier3")
delete_scheduled_task("wf-" + workflow_id + "-tier4")
```

### 3.4 Self-Dismissal Pattern

Each tier check task is idempotent and self-dismissing. When it fires:

1. Read `journal.jsonl` for the workflow
2. Search for `{"type": "workflow_complete", "workflow_id": "..."}`
3. If found → exit silently (workflow finished before this check fired). The `delete_scheduled_task` from step 3.3 may have run already, so `delete_scheduled_task` here is best-effort.
4. If NOT found → execute tier escalation action
5. After executing escalation action, best-effort `delete_scheduled_task` on itself (prevents zombie tasks)

---

## 4. journal.jsonl Extended Format

Extend the journal format to support tier escalation checks:

```jsonl
{"type":"workflow_start","workflow_id":"wf-abc123","workflow_name":"code-shiniyaya-v3-iter4-scan","total_agents":8,"parent_session_id":"sess-xyz789","background_task_id":"task-bg001","start_time":"2026-07-15T14:00:00.000+08:00","tier_tasks":["wf-abc123-tier2","wf-abc123-tier3","wf-abc123-tier4"]}
{"type":"agent_start","workflow_id":"wf-abc123","agent_key":"usability-1","agent_type":"Explore","timestamp":"2026-07-15T14:00:01.123+08:00"}
{"type":"agent_result","workflow_id":"wf-abc123","agent_key":"usability-1","verdict":"PASS","issues_count":2,"duration_ms":45230,"timestamp":"2026-07-15T14:00:46.353+08:00"}
{"type":"agent_start","workflow_id":"wf-abc123","agent_key":"logic-1","agent_type":"general-purpose","timestamp":"2026-07-15T14:00:01.456+08:00"}
{"type":"escalation","workflow_id":"wf-abc123","tier":"yellow","agents_running":5,"total_agents":8,"percent_running":62.5,"message":">30% agents still running after 120s","timestamp":"2026-07-15T14:02:00.000+08:00"}
{"type":"escalation","workflow_id":"wf-abc123","tier":"orange","agents_running":3,"agents_done":5,"stuck_agents":["logic-1","security","stress-2"],"user_response":null,"timestamp":"2026-07-15T14:05:00.000+08:00"}
{"type":"escalation","workflow_id":"wf-abc123","tier":"red","action":"auto_kill","agents_done":5,"total_agents":8,"killed":true,"timestamp":"2026-07-15T14:10:00.000+08:00"}
{"type":"workflow_complete","workflow_id":"wf-abc123","status":"killed_by_tier4","agents_done":5,"agents_launched":8,"agents_failed":0,"agents_hung":3,"duration_ms":600000,"timestamp":"2026-07-15T14:10:00.500+08:00"}
```

**Key fields for escalation checks:**

| Field | Purpose |
|---|---|
| `parent_session_id` | Tier 3/4 tasks use `send_message` to notify this session |
| `background_task_id` | Tier 4 uses `TaskStop` with this ID to kill the hung workflow |
| `start_time` | Compute elapsed wall-clock time (`now - start_time`) |
| `tier_tasks` | List of CronCreate task IDs for cleanup |
| `timestamp` on `agent_start`/`agent_result` | Compute per-agent elapsed time and event gap |

---

## 5. Tier Check Task Prompts (Self-Contained)

Each CronCreate task is created with a fully self-contained prompt — the scheduled session has no memory of the parent conversation.

### 5.1 TIER 2 Check Prompt

```
Task: code-shiniyaya TIER 2 escalation check for workflow {workflow_id}.

Read the journal file at {journal_path}.

1. Search for entry: {"type": "workflow_complete", "workflow_id": "{workflow_id}"}
   - If found: exit silently. Workflow already completed.

2. Count entries where type="agent_result" and workflow_id="{workflow_id}".
   Let this be `agents_done`.

3. Count entries where type="agent_start" and workflow_id="{workflow_id}".
   Let this be `agents_launched`.

4. Compute: agents_running = agents_launched - agents_done.
   Compute: percent_running = (agents_running / agents_launched) * 100.

5. If percent_running > 30:
   - Write escalation entry to journal:
     {"type":"escalation","workflow_id":"{workflow_id}","tier":"yellow","agents_running":{agents_running},"total_agents":{agents_launched},"percent_running":{percent_running},"message":">30% agents still running after 120s","timestamp":"{now_iso}"}
   - If parent_session_id is "{parent_session_id}" and it is not empty:
     Send message to session "{parent_session_id}": "[!] {agents_running}/{agents_launched} agents still running after 2 min — possible system load."

6. If percent_running <= 30:
   - Exit silently. Acceptable slow-agent rate.

7. Best-effort: delete_scheduled_task("{workflow_id}-tier2").
```

### 5.2 TIER 3 Check Prompt

```
Task: code-shiniyaya TIER 3 escalation check for workflow {workflow_id}.

Read the journal file at {journal_path}.

1. Search for entry: {"type": "workflow_complete", "workflow_id": "{workflow_id}"}
   - If found: exit silently. Workflow already completed.

2. Search for entry: {"type": "escalation", "workflow_id": "{workflow_id}", "tier": "orange"}
   - If found AND user_response field is not null: exit. Already handled.

3. Count agents_done and agents_launched from journal (same as tier 2).

4. Identify agents still running:
   - Collect all agent_key values from type="agent_start" entries.
   - Collect all agent_key values from type="agent_result" entries.
   - Stuck agents = set difference.
   - Compute: last_event_gap = now - MAX(timestamp from any journal entry for this workflow).

5. If agents_running > 0:
   - Write escalation entry to journal:
     {"type":"escalation","workflow_id":"{workflow_id}","tier":"orange","agents_running":{agents_running},"agents_done":{agents_done},"stuck_agents":[{stuck_list}],"last_event_gap_ms":{gap},"user_response":null,"timestamp":"{now_iso}"}

   - Send message to session "{parent_session_id}":
     "Agent(s) {stuck_list} running for 5+ min — may be stuck. Last journal event was {gap}s ago. Continue waiting or skip?
     - Reply 'skip' → kill workflow, collect partial results, re-run only failed dimensions.
     - Reply 'continue' → keep waiting (will check again at 10 min mark).
     - No reply → tier 4 will auto-kill at 10 min."

6. Best-effort: delete_scheduled_task("{workflow_id}-tier3").

USER RESPONSE: When the parent session receives the message and the user responds:
  - "skip" → call TaskStop("{background_task_id}"), read journal for partial results, report to user
  - "continue" → update journal escalation entry with user_response: "continue", then create a NEW tier 3 task with fireAt = now + 300s (re-arm). Do NOT create a new tier 4 — the original one still fires.
```

### 5.3 TIER 4 Check Prompt

```
Task: code-shiniyaya TIER 4 escalation check for workflow {workflow_id}.

Read the journal file at {journal_path}.

1. Search for entry: {"type": "workflow_complete", "workflow_id": "{workflow_id}"}
   - If found: exit silently. Workflow already completed.

2. Count agents_done and agents_launched from journal.

3. Identify stuck agents (set difference, same as tier 3).

4. AUTO-KILL SEQUENCE:
   a. Write escalation entry to journal:
      {"type":"escalation","workflow_id":"{workflow_id}","tier":"red","action":"auto_kill","agents_done":{agents_done},"total_agents":{agents_launched},"killed":true,"timestamp":"{now_iso}"}

   b. Call TaskStop("{background_task_id}").
      - If TaskStop succeeds: continue to step c.
      - If TaskStop fails (workflow already dead): log failure, continue to step c.

   c. Parse journal.jsonl for all type="agent_result" entries for this workflow_id.
      Aggregate findings: count PASS/PARTIAL/FAIL verdicts, count CRITICAL/HIGH/MEDIUM/LOW issues.

   d. Write workflow_complete entry:
      {"type":"workflow_complete","workflow_id":"{workflow_id}","status":"killed_by_tier4","agents_done":{agents_done},"agents_launched":{agents_launched},"agents_hung":{hung_count},"hung_agents":[{stuck_list}],"duration_ms":600000,"timestamp":"{now_iso}"}

   e. Send message to session "{parent_session_id}":
      "Killed stuck workflow '{workflow_name}'. {agents_done}/{agents_launched} agents completed.
      Missing: {stuck_list}
      Findings summary: {pass} PASS / {partial} PARTIAL / {fail} FAIL
      Critical issues: {critical_count}, High issues: {high_count}
      Proceeding with partial results — missing agents logged as 'unavailable' but do not block the iteration."

5. Best-effort: delete_scheduled_task("{workflow_id}-tier2"), delete_scheduled_task("{workflow_id}-tier3"), delete_scheduled_task("{workflow_id}-tier4").
```

---

## 6. Modified Workflow Template

Integrate escalation creation into the workflow launch sequence:

```javascript
export const meta = {
  name: 'code-shiniyaya-v{X}-iter{N}-scan',
  description: '{N} agents: scan + stress test with time-based escalation',
  phases: [{ title: 'All', detail: 'All agents in one parallel block' }],
}

var SKILL = 'C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya\\SKILL.md'
var JOURNAL = 'C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya\\.claude\\memory\\code-shiniyaya\\journal.jsonl'

var F = {
  type: 'object', required: ['verdict', 'issues'],
  properties: {
    verdict: { type: 'string', enum: ['PASS','PARTIAL','FAIL'] },
    issues: { type: 'array', items: { type: 'object', required: ['severity','description'], properties: { severity: { type: 'string', enum: ['CRITICAL','HIGH','MEDIUM','LOW'] }, description: { type: 'string' } } } },
  },
}

phase('All')

var TASKS = [
  { key: 'usability-1', prompt: '...' },
  { key: 'usability-2', prompt: '...' },
  { key: 'logic-1',     prompt: '...' },
  { key: 'logic-2',     prompt: '...' },
  { key: 'security',    prompt: '...' },
  { key: 'stress-1',    prompt: '...' },
  { key: 'stress-2',    prompt: '...' },
  { key: 'xref',        prompt: '...' },
]

// --- ESCALATION SETUP ---
var workflowId = 'wf-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 6)
var parentSessionId = '{current_session_id}'  // injected at launch time
var backgroundTaskId = '{background_task_id}'  // injected at launch time
var now = new Date()
var startTimeIso = now.toISOString()

// Write workflow_start to journal
log('Workflow ' + workflowId + ' starting with ' + TASKS.length + ' agents')
// [CC appends to journal.jsonl atomically here]

// Create tier escalation tasks
var tier2FireAt = new Date(now.getTime() + 120000).toISOString()
var tier3FireAt = new Date(now.getTime() + 300000).toISOString()
var tier4FireAt = new Date(now.getTime() + 600000).toISOString()

// [CC calls create_scheduled_task 3 times with the prompts from section 5]
// Task IDs: wf-{workflowId}-tier2, wf-{workflowId}-tier3, wf-{workflowId}-tier4

var tierTaskIds = ['wf-' + workflowId + '-tier2', 'wf-' + workflowId + '-tier3', 'wf-' + workflowId + '-tier4']
// --- END ESCALATION SETUP ---

log('Starting ' + TASKS.length + ' agents in parallel (escalation: tier2@120s, tier3@300s, tier4@600s)')

var results = await parallel(TASKS.map(function(t) {
  return function() {
    log('Agent ' + t.key + ' launched')
    // [CC appends agent_start to journal]
    var r = agent(t.prompt, { label: t.key, phase: 'All', schema: F })
    if (r === null) log('Agent ' + t.key + ' TIMED OUT or was skipped')
    else log('Agent ' + t.key + ' returned verdict=' + (r ? r.verdict : 'null'))
    // [CC appends agent_result to journal]
    return r
  }
}))

// --- ESCALATION CLEANUP ---
// Delete all tier tasks — workflow completed naturally
tierTaskIds.forEach(function(tid) {
  // [CC calls delete_scheduled_task(tid)]
})
// Write workflow_complete to journal
// [CC appends workflow_complete entry]
// --- END ESCALATION CLEANUP ---

log('All agents completed: ' + results.length + ' total, ' + results.filter(Boolean).length + ' with results')

// Compute summary (unchanged)
var ok = results.filter(Boolean)
var p=0, pt=0, f=0, c=0, h=0
ok.forEach(function(r) {
  if (r.verdict==='PASS') p++
  if (r.verdict==='PARTIAL') pt++
  if (r.verdict==='FAIL') f++
  if (r.issues) r.issues.forEach(function(i) {
    if (i.severity==='CRITICAL') c++
    if (i.severity==='HIGH') h++
  })
})

log('SUMMARY: ' + p + ' PASS / ' + pt + ' PARTIAL / ' + f + ' FAIL / ' + c + ' CRITICAL / ' + h + ' HIGH')

return { pass:p, partial:pt, fail:f, critical:c, high:h, workflow_id: workflowId }
```

---

## 7. Tier 3 User Interaction Flow (Parent Session)

When the tier 3 CronCreate task sends a message to the parent session, the parent session receives it as a new user turn. The CC response logic:

```
Receive message: "Agent(s) {stuck_list} running for 5+ min..."

1. Acknowledge the notification to the user.
2. Display stuck agent names, elapsed time, and last event gap.
3. Ask: "Continue waiting or skip these agents?"

IF user says "skip":
   a. Call TaskStop({background_task_id})
   b. Read journal.jsonl for workflow {workflow_id}
   c. Collect all agent_result entries → aggregate findings
   d. Identify which dimensions succeeded and which failed
   e. Report to user: "{n}/{total} agents completed. Missing: {list}."
   f. Re-launch ONLY the failed/missing dimensions as a new workflow
      (smaller scope, same escalation pattern with its own tier tasks)
   g. Update journal escalation entry: user_response: "skip"

IF user says "continue":
   a. Tell user: "Keeping workflow alive. Will auto-kill at 10 min mark if still stuck."
   b. Update journal escalation entry: user_response: "continue"
   c. Create a NEW tier 3 task: fireAt = now + 300s (re-arm)
      Task ID: wf-{workflow_id}-tier3-r2
   d. Do NOT touch tier 4 task — it still fires at original +600s

IF user does not respond within 300s (i.e., tier 4 fires first):
   → Tier 4 auto-kill executes (no user input needed)
```

---

## 8. Edge Cases and Failure Modes

| Edge case | Handling |
|---|---|
| **Workflow completes between tier check fire and its execution** | Each tier check reads journal first; exits if `workflow_complete` found. Race-condition-safe. |
| **CronCreate task itself fails to fire** | Tier N+1 task still fires independently. If tier 3 fails to fire, tier 4 still fires at 600s and auto-kills. No cascading dependency. |
| **Parent session is archived/closed when tier 3 fires** | `send_message` to closed session fails. Tier check task logs failure to journal, writes `user_response: "unreachable"`, delegates to tier 4 for auto-kill. |
| **TaskStop fails (workflow already dead)** | Tier 4 task logs the failure, proceeds to parse journal and report partial results anyway. |
| **journal.jsonl is corrupted or missing** | Tier check task writes error to separate log: `{journal_path}.escalation_errors.jsonl`. Falls back to: if 600s elapsed since task creation → assume hung → attempt TaskStop. |
| **Multiple workflows running concurrently** | Each workflow has unique `workflow_id` and its own set of tier tasks. journal.jsonl entries are filtered by `workflow_id`. No cross-contamination. |
| **User re-arms tier 3 (continue) multiple times** | Each re-arm gets a new task ID with incrementing suffix (`-r2`, `-r3`). Old tier 3 tasks self-dismiss (find prior escalation entry with non-null user_response). Tier 4 at original +600s is the hard deadline — re-arming tier 3 does not extend tier 4. |
| **Agents complete but workflow wrapper hangs** | journal shows all `agent_result` entries but no `workflow_complete`. Tier 4 fires → TaskStop kills wrapper → tier 4 task writes `workflow_complete` with `status: "wrapper_hung"`. |

---

## 9. Integration with SKILL.md Error Handling

The existing SKILL.md error handling table should reference this escalation system:

| SKILL.md entry | Escalation tier | Modification |
|---|---|---|
| "Agent全超时" (STEP 1) | Tier 4 → auto-kill | Add: "Tier 4 auto-kills at 600s; partial results from journal.jsonl are used." |
| "个别超时" (STEP 1) | Tier 2/3 | Add: "Yellow warning at 120s if >30% still running; orange notification at 300s." |
| "Codex超时" (STEP 7) | Message-count based (existing N=4) | Unchanged — Codex silence uses message count, not wall-clock. |
| progress-tracking.md "Stuck Agent Detection" point 4 | Tier 4 | Replace hardcoded "600s kill" with tier 4 escalation task. |

**New entry to add to SKILL.md error handling table:**

| 步骤 | 失败模式 | 用户消息 | 恢复 |
|------|---------|---------|------|
| ALL | Agent挂起 (wall-clock) | Tier 2 (>120s): 透明日志; Tier 3 (>300s): "继续等/跳过?"; Tier 4 (>600s): 自动kill | Tier 3用户skip→kill+部分结果+重跑失败维度; Tier 4自动kill→journal部分结果→继续迭代 |

---

## 10. Summary of All CronCreate Tasks

| Task ID | `fireAt` | Reads | Writes | Calls | Action |
|---|---|---|---|---|---|
| `wf-{id}-tier2` | `start + 120s` | journal.jsonl | `escalation.tier=yellow` (if >30%) | `send_message` (if >30%) | Log warning |
| `wf-{id}-tier3` | `start + 300s` | journal.jsonl | `escalation.tier=orange` | `send_message` to parent | Notify user |
| `wf-{id}-tier4` | `start + 600s` | journal.jsonl | `escalation.tier=red` + `workflow_complete` | `TaskStop` + `send_message` to parent | Auto-kill + recover |
| `wf-{id}-tier3-r{N}` | `user_continue + 300s` | journal.jsonl | same as tier 3 | same as tier 3 | Re-armed tier 3 |

---

## 11. Design Rationale: Why Hybrid (d), Not (a), (b), or (c)

| Option | Verdict | Reason |
|---|---|---|
| (a) CronCreate at tier boundaries | **Used for tiers 3 and 4** | Clean one-shot semantics. But alone misses tier 2 (wasteful to fire a task just for logging). |
| (b) Rely on workflow `duration_ms` | **Rejected as primary** | `duration_ms` is only available AFTER completion. Useless for detecting hangs in progress. Useful as post-hoc audit only. |
| (c) User-initiated "check progress" | **Used for tier 2 backing** | Good for on-demand visibility, but user may not know to ask. Cannot be the sole mechanism — tier 4 must be automatic. |
| (d) Hybrid | **Selected** | CronCreate `fireAt` for tiers 3 and 4 (automatic escalation). Tier 2 is logged by the tier 2 CronCreate task but is primarily informational — it also serves as a heartbeat confirming the escalation infrastructure is working. User-initiated `check progress` is always available as a supplement. |
