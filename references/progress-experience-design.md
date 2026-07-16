# Progress Experience Design for code-shiniyaya Iterative Workflows

> Design document for user-facing checkpoint outputs, heartbeat, hang detection, and anti-spam rules.
> Version: 1.0.0 | 2026-07-16

---

## 1. Design Principles

1. **Never make the user wonder "is it stuck or just slow?"** -- every silent gap >60s gets filled with a status line.
2. **Report at batch granularity, not per-agent** -- with 8+ agents, per-agent notifications are noise. Report when a batch completes OR when the heartbeat fires, whichever is first.
3. **Structured, predictable format at every checkpoint** -- the user learns the rhythm and can scan in half a second.
4. **Verdict distribution in every update** -- the user always knows the score without checking a dashboard.
5. **Hang detection is explicit and actionable** -- not "something might be wrong", but "Agent X has been running Ys, options: [wait / skip / kill-all]".

---

## 2. Checkpoint Output Templates

### 2.1 WORKFLOW START

Emitted once, at the top of an iteration, before any agents are launched.

```
============================================================
code-shiniyaya 迭代 #2 启动
============================================================
扫描范围: src/parser.py, src/validator.py, src/api/handlers.py (3 文件, ~850 LOC)
Agent 数量: 8 (可用性×2, 逻辑×2, 安全×1, 压力×2, 交叉引用×1)
预计耗时: ~90-180s (8 Agent 并行, 单Agent超时=300s)
批次: 单批全并行 (batch_size=8)
模式: normal (Codex 双批准)
------------------------------------------------------------
[启动中...]
```

**Rules:**
- `扫描范围` lists the files being scanned. If >5 files, show count + top 3 by LOC + "...".
- `Agent 数量` lists the type distribution (from progress-tracking.md: usability, logic, security, stress, xref).
- `预计耗时` is a range: best case (all agents finish in ~90s) to worst case before timeout (300s).
- `批次` shows batch_size and whether agents are split across batches.
- `模式` shows normal | degraded (from session JSON mode field).

### 2.2 DURING EXECUTION -- Heartbeat + Batch Completion

Two triggers for a progress update during execution:
- **Heartbeat**: every 60s, a minimal status line.
- **Batch completion**: all agents in the current batch have returned (or timed out).

**Priority rule**: if a batch completes before the 60s heartbeat, emit the batch-completion message and reset the heartbeat timer. If the heartbeat fires while agents are still running, emit the heartbeat line. Never emit both within the same 10s window.

#### 2.2.1 Heartbeat (every 60s)

```
[迭代#2 心跳 60s] 扫描中: 5/8 Agent完成 | PASS=2 PARTIAL=2 FAIL=1 | 运行中: usability-2, logic-1, stress-2
```

Format:
```
[迭代#{N} 心跳 {elapsed}s] 扫描中: {done}/{total} Agent完成 | {verdict_distribution} | 运行中: {running_agent_keys}
```

**Rules:**
- `{elapsed}s` is wall-clock seconds since workflow start.
- `{verdict_distribution}` shows only the verdicts of completed agents. Format: `PASS=p PARTIAL=pt FAIL=f`. Omit verdicts that are 0.
- `{running_agent_keys}` lists the keys of agents still running (from the TASKS array). If >3 running, show first 3 + `等{N}个`.
- If 0 agents have completed yet, show: `扫描中: 0/8 Agent完成 | 运行中: usability-1, usability-2, logic-1, logic-2, ...`
- Heartbeat is suppressed if the last user-visible message was <10s ago (anti-spam).

#### 2.2.2 Batch Completion

```
[迭代#2 批次完成 85s] 8/8 Agent完成 | PASS=4 PARTIAL=2 FAIL=2 | CRITICAL=1 HIGH=3 MEDIUM=5 LOW=2
```

Format:
```
[迭代#{N} 批次完成 {elapsed}s] {done}/{total} Agent完成 | {verdict_distribution} | {severity_counts}
```

**Rules:**
- `{elapsed}s` is actual wall-clock time for this batch.
- `{severity_counts}` shows CRITICAL/HIGH/MEDIUM/LOW counts aggregated across all agent results. Omit levels that are 0.
- If any agents timed out (returned null): append `| 超时: {timed_out_keys}`.
- This message replaces (not supplements) the heartbeat that would have fired at the same time.

### 2.3 AGENT HANG DETECTED

Emitted when an agent has been running >300s (the timeout threshold from progress-tracking.md rule 2), or when the ScheduleWakeup fires and detects agents stuck.

```
------------------------------------------------------------
[!] AGENT 挂起检测
------------------------------------------------------------
Agent:     usability-2 (类型: usability)
已运行:    320s (超时阈值: 300s)
状态:      无响应 -- 未返回结果，未报错
当前批次:   6/8 Agent完成, usability-2 + stress-2 仍在运行

选项:
  [1] 继续等待 (再等120s后重新检查)
  [2] 跳过此Agent (标记为超时，使用已有6个Agent的结果继续)
  [3] 终止本轮扫描 (保存部分结果，进入修复阶段)
------------------------------------------------------------
等待用户选择 [1/2/3] 或 120s后自动选择 [2]...
```

**Rules:**
- The hang alert triggers at 300s (agent timeout threshold per progress-tracking.md rule 2).
- If the user does not respond within 120s, auto-select option [2] (skip).
- After auto-skip: emit `[自动] usability-2 已跳过 (超时 420s)。继续使用 7/8 Agent结果。`
- If ALL remaining agents are hung, offer options [2] and [3] only (option [1] is useless).
- The alert is only emitted ONCE per hung agent (not repeated every 60s).

### 2.4 WORKFLOW COMPLETE (Scan Phase)

Emitted after all agents in the scan phase have returned (or been skipped).

```
============================================================
迭代 #2 扫描完成 (总耗时: 145s)
============================================================
Agent 结果:  8 启动 | 7 完成 | 1 超时 (usability-2)

判 verdict 分布:
  PASS      4  (50.0%)  usability-1, logic-1, stress-1, xref
  PARTIAL   2  (25.0%)  logic-2, security
  FAIL      1  (12.5%)  usability-2 [超时--结果不可用]
  (空)      1  (12.5%)  stress-2 [超时--结果不可用]

问题严重度汇总:
  CRITICAL  1   parser.py:142  竞态条件可能导致数据丢失
  HIGH      3   validator.py:88, handlers.py:210, parser.py:56
  MEDIUM    5   (详情见 MULTI_AGENT_BUGS.md)
  LOW       2   (详情见 MULTI_AGENT_BUGS.md)

待修复项: 11 个问题 (1 CRITICAL, 3 HIGH, 5 MEDIUM, 2 LOW)
下一步:   修复方案生成 (STEP 2) -- 预计 3-5 Agent 并行设计
============================================================
```

**Rules:**
- The table shows each agent's key and verdict. Agents that timed out are marked with `[超时]`.
- If an agent returned `null` (timeout/skip), its verdict is shown as `(空)` and its issues are excluded from the severity summary.
- The severity summary shows the top CRITICAL + HIGH issues with file:line + description. MEDIUM and LOW are aggregated with a reference to the detailed report.
- `待修复项` counts unique issues (after deduplication per progress-tracking.md rule: group by file:line+/-3).
- `下一步` tells the user what happens next and how many agents will work on it.

### 2.5 FIX PHASE START

Emitted when transitioning from diagnosis to fix design/execution.

```
============================================================
修复阶段启动 -- 基于迭代 #2 扫描结果
============================================================
修复目标:   11 个问题 (1 CRITICAL, 3 HIGH, 5 MEDIUM, 2 LOW)
修复策略:
  Phase A (立即):  1 项  parser.py:142 竞态条件 [CRITICAL]
  Phase B (优先):  3 项  validator.py:88, handlers.py:210, parser.py:56 [HIGH]
  Phase C (随后):  5 项  [MEDIUM]
  Phase D (评估):  2 项  [LOW]

Agent 分配:  5 Agent 并行设计修复方案
  - Agent-1: parser.py:142 (CRITICAL, 独立文件)
  - Agent-2: parser.py:56 (HIGH, 同文件串行于 Agent-1)
  - Agent-3: validator.py:88 (HIGH, 独立文件)
  - Agent-4: handlers.py:210 (HIGH, 独立文件)
  - Agent-5: MEDIUM 批量 (5项, 低风险微改动)

共享文件约束: parser.py 由 Agent-1 -> Agent-2 顺序执行
预计耗时:    ~120-300s (取决于 Phase A 修复复杂度)
------------------------------------------------------------
[启动修复Agent...]
```

**Rules:**
- `修复目标` is the count from the scan completion, broken down by severity.
- `修复策略` shows the Phase breakdown (from SKILL.md STEP 2 definitions).
- `Agent 分配` shows which agent handles which file(s). Same-file items are serialized (per DAG rules).
- `共享文件约束` calls out any serialization constraints explicitly so the user knows why some items take longer.
- If in degraded mode: append `模式: degraded (Codex不可用, 用户单批准)`.

### 2.6 ITERATION COMPLETE

Emitted after one full iteration (scan + fix + verify) completes. Shows before/after comparison.

```
============================================================
迭代 #2 完成 -- 前后对比
============================================================
指标              迭代 #1         迭代 #2         变化
------------------------------------------------------------
Agent PASS         3 (37.5%)      5 (62.5%)      +2
Agent PARTIAL      3 (37.5%)      2 (25.0%)      -1
Agent FAIL         2 (25.0%)      1 (12.5%)      -1
CRITICAL 问题      3               1               -2 (已修复)
HIGH 问题          5               3               -2 (已修复)
MEDIUM 问题        7               5               -2 (已修复)
LOW 问题           4               2               -2 (已修复)
总问题数           19              11              -8
修复应用           8/8 已应用      进行中          --
------------------------------------------------------------
状态: 收敛中 (问题数 -42%, PASS率 +25pp)
剩余 CRITICAL: parser.py:142 竞态条件 (修复方案设计中, Phase A)
建议: 完成 parser.py:142 修复后进入迭代 #3
============================================================
```

**Rules:**
- The table compares the PREVIOUS iteration's final state with the CURRENT iteration's final state.
- `修复应用` shows how many planned fixes were actually applied (from STEP 6 execution tracking).
- `状态` gives a one-line assessment: "收敛中" (improving), "停滞" (no change), "倒退" (worse), or "完成" (all clear).
- `剩余` lists the highest-severity unresolved items.
- `建议` gives a concrete next action.
- For iteration #1, the "迭代 #0" column shows the initial baseline (pre-scan state). If no baseline, show `(基线)` in the iteration #1 column and `N/A` in the prior column.

### 2.7 GOAL ACHIEVED

Emitted when all CRITICAL + HIGH issues are resolved and the iteration loop terminates.

```
============================================================
[完成] code-shiniyaya 迭代工作流达成目标
============================================================
总迭代次数:   3
总耗时:       约 18 分钟
扫描Agent:   24 启动 | 22 完成 | 2 超时
修复Agent:   15 启动 | 15 完成 | 0 失败

最终状态:
  CRITICAL  0  (初始: 3)  全部已修复
  HIGH      0  (初始: 5)  全部已修复
  MEDIUM    2  (初始: 7)  5已修复, 2降级为LOW (低影响, 用户确认跳过)
  LOW       3  (初始: 4)  1已修复, 3已知且接受

Agent PASS 率演进:
  迭代 #1:  37.5% (3/8)
  迭代 #2:  62.5% (5/8)
  迭代 #3:  87.5% (7/8)

产物:
  - reports/FOR_CODEX_迭代3_扫描完成.md
  - reports/MULTI_AGENT_BUGS.md (最终去重清单)
  - reports/MANUAL_FIXES.md (2项已知且接受)
  - .claude/memory/code-shiniyaya/session-a1b2c3d4.json (会话归档)

[code-shiniyaya v3.2.0] CC<-->Codex 双重检验工作流完成。
============================================================
```

**Rules:**
- Only emitted when CRITICAL=0 AND HIGH=0 (the definition of "goal achieved").
- `总耗时` is wall-clock time across all iterations (sum of iteration elapsed times).
- `Agent PASS 率演进` shows the trend across iterations.
- `产物` lists all persistent output files with paths.
- If any MEDIUM/LOW issues remain, they are listed with justification (user accepted risk, deferred, etc.).
- If goal is achieved in a single iteration: show a compact version without the PASS-rate evolution table.

---

## 3. ScheduleWakeup Pattern

### 3.1 Concept

After launching a workflow (spawning agents), CC does not block waiting. Instead, CC schedules a wakeup callback at T+120s. When the wakeup fires:

- **If workflow completed**: report results immediately (checkpoint 2.4).
- **If still running**: report progress (checkpoint 2.2.1 heartbeat variant) + schedule another wakeup at T+120s.
- **If stuck** (no new agent completions since last wakeup): escalate (checkpoint 2.3).

### 3.2 Implementation Sketch

The ScheduleWakeup pattern is implemented within a single CC turn using the `loop` skill or a background bash sleep+poll pattern. Since CC does not have a native `setTimeout`-equivalent, the pattern uses a two-phase approach:

**Phase A -- Launch (current turn):**
1. Spawn all agents in one parallel block (per progress-tracking.md rule 1).
2. Record `workflow_start_ts = now()`.
3. Output checkpoint 2.1 (WORKFLOW START).
4. The parallel block returns when ALL agents complete or timeout (this is the blocking part).

**Phase B -- Monitor (runs concurrently with agent execution):**

Since CC agents run asynchronously via the Agent tool, the parallel block's `await` covers the wait. The heartbeat and hang detection logic runs inside the workflow script itself (in the progress-tracking.md Javascript template), not in the CC orchestration layer. This means:

- The `log()` function in the workflow template IS the heartbeat mechanism.
- Hang detection is done by the workflow runtime (agents have a 300s timeout per Bash tool passthrough).
- CC receives the complete result when the parallel block resolves.

**Revised ScheduleWakeup for CC orchestration layer:**

For phases where CC orchestrates multiple sequential steps (e.g., STEP 1 diagnosis -> STEP 2 plan -> STEP 3 codex text), the ScheduleWakeup pattern applies BETWEEN steps:

```
CC turn N:
  1. Launch STEP 1 agents (parallel block)
  2. Output: "诊断扫描中... [调度: 120s后唤醒检查进度]"
  3. Wait for parallel block to resolve (this is blocking within the turn)

CC turn N+1 (after parallel block resolves):
  4. If all agents completed: proceed to checkpoint 2.4
  5. If some agents hung: proceed to checkpoint 2.3
```

The "wakeup" is implicit -- CC's turn resumes when the parallel block completes. The 120s is the heartbeat interval for LOG MESSAGES within the workflow, not for CC-turn scheduling.

### 3.3 Practical Implementation in progress-tracking.md Workflow Template

```javascript
// Inside the workflow template, add heartbeat and hang detection:

var WORKFLOW_START = Date.now()
var HEARTBEAT_INTERVAL = 60000  // 60s
var HANG_THRESHOLD = 300000     // 300s
var lastHeartbeat = 0
var lastProgressCount = 0

// Track per-agent start times
var agentStartTimes = {}

// Wrapper around agent() that tracks timing
function monitoredAgent(prompt, key, schema) {
  agentStartTimes[key] = Date.now()
  log('Agent ' + key + ' 启动')

  var result = agent(prompt, { label: key, phase: 'All', schema: schema })

  var elapsed = Date.now() - agentStartTimes[key]
  if (result === null) {
    log('Agent ' + key + ' 超时/跳过 (运行 ' + (elapsed/1000).toFixed(0) + 's)')
  } else {
    log('Agent ' + key + ' 完成 (运行 ' + (elapsed/1000).toFixed(0) + 's, verdict=' + result.verdict + ')')
  }
  return result
}

// Heartbeat function -- called periodically
function heartbeat(completedCount, totalCount) {
  var now = Date.now()
  if (now - lastHeartbeat < HEARTBEAT_INTERVAL) return  // anti-spam: max 1 per 60s
  if (now - lastHeartbeat < 10000) return  // anti-spam: no heartbeat within 10s of last message

  lastHeartbeat = now

  // Count verdicts from completed agents
  var verdicts = { PASS: 0, PARTIAL: 0, FAIL: 0 }
  var running = []
  for (var key in agentStartTimes) {
    var agentResult = /* check if agent has returned -- workflow-runtime specific */ null
    if (agentResult === undefined) {
      running.push(key)
    } else if (agentResult !== null) {
      verdicts[agentResult.verdict] = (verdicts[agentResult.verdict] || 0) + 1
    }
  }

  var vd = []
  if (verdicts.PASS > 0) vd.push('PASS=' + verdicts.PASS)
  if (verdicts.PARTIAL > 0) vd.push('PARTIAL=' + verdicts.PARTIAL)
  if (verdicts.FAIL > 0) vd.push('FAIL=' + verdicts.FAIL)

  var runningStr = running.length > 0 ? ' | 运行中: ' + running.slice(0,3).join(', ') + (running.length > 3 ? ' 等' + running.length + '个' : '') : ''

  log('[迭代#N 心跳 ' + Math.floor((now - WORKFLOW_START)/1000) + 's] 扫描中: ' + completedCount + '/' + totalCount + ' Agent完成 | ' + vd.join(' ') + runningStr)

  // Hang detection
  for (var key in agentStartTimes) {
    if (/* agent still running */ true && (now - agentStartTimes[key]) > HANG_THRESHOLD) {
      log('[!] Agent ' + key + ' 挂起检测: 已运行 ' + Math.floor((now - agentStartTimes[key])/1000) + 's (阈值=' + (HANG_THRESHOLD/1000) + 's)')
    }
  }
}
```

### 3.4 CC Orchestration-Level ScheduleWakeup

For multi-step workflows where CC orchestrates between steps, use the `loop` skill or explicit sleep:

```
# Pattern: CC launches workflow, schedules self-wakeup

Turn N (CC):
  1. Spawn agents via Agent tool (parallel, run_in_background=true for each)
  2. Write workflow state to session JSON
  3. Output checkpoint 2.1 (WORKFLOW START)
  4. Schedule: Bash "sleep 120 && echo 'WAKEUP'" run_in_background=true

Turn N+1 (triggered by sleep completion OR all agents completing):
  5. Read workflow state
  6. If all agents done: emit checkpoint 2.4 (WORKFLOW COMPLETE)
  7. If still running: emit checkpoint 2.2.1 (heartbeat) + goto step 4
  8. If stuck: emit checkpoint 2.3 (AGENT HANG DETECTED)
```

---

## 4. Anti-Spam Rules

### 4.1 The Core Rule

**"Report when a batch completes, or every 60s, whichever comes first. Never both within 10s."**

### 4.2 Specific Rules

| Rule | Description |
|------|-------------|
| **R1: Batch > Heartbeat** | If a batch completes at T+55s, emit the batch-completion message and suppress the heartbeat that would have fired at T+60s. |
| **R2: Heartbeat > Batch** | If a heartbeat fires at T+60s and the batch completes at T+65s, emit both (they are >10s apart and convey different information). |
| **R3: Minimum gap** | No two progress messages within 10s of each other. If a heartbeat would fire within 10s of a batch completion, skip it. |
| **R4: No per-agent spam** | Never emit a message for a single agent completing. Aggregate at batch level. |
| **R5: First-result exception** | If 30s pass with 0 agents completed, emit: `[迭代#N] 首批Agent仍在扫描中... (已等待30s, 8 Agent并行运行)` to reassure the user that work is happening. |
| **R6: Hang alert is always immediate** | Hang detection (checkpoint 2.3) bypasses all anti-spam rules. It is always emitted immediately. |
| **R7: Duplicate hang suppression** | A hang alert for agent X is emitted exactly once. Subsequent heartbeats mention "usability-2 仍在挂起 (已超时 420s)" as a suffix, not a full alert. |

### 4.3 Decision Matrix

```
Event at time T         | Last message at | Action
------------------------|-----------------|--------
Batch completes         | T-65s (heartbeat)| EMIT batch-completion
Batch completes         | T-5s (heartbeat) | SUPPRESS (gap <10s)
Heartbeat due           | T-8s (batch done)| SUPPRESS (gap <10s)
Heartbeat due           | T-65s (batch done)| EMIT heartbeat
Agent hang detected     | any              | EMIT immediately (R6)
First agent completes   | T-0s (workflow start)| SUPPRESS (wait for batch or heartbeat)
30s with 0 completions  | T-0s (workflow start)| EMIT first-result reassurance (R5)
```

---

## 5. Integration with code-shiniyaya SKILL.md

### 5.1 Where Each Checkpoint Maps to STEPS

| Checkpoint | SKILL.md STEP | Trigger |
|------------|---------------|---------|
| 2.1 WORKFLOW START | STEP 1 (诊断扫描) 或 STEP 4 (Codex验证) | Agent 并行块即将启动 |
| 2.2 DURING EXECUTION | STEP 1, STEP 1.5, STEP 4, STEP 7 | Agent 运行中 (心跳/批次完成) |
| 2.3 AGENT HANG | 任何有 Agent 并行块的 STEP | 单 Agent >300s 无响应 |
| 2.4 WORKFLOW COMPLETE | STEP 1 结束, STEP 4 结束 | 所有 Agent 返回/超时 |
| 2.5 FIX PHASE START | STEP 2 (方案生成) 或 STEP 6 (逐项执行) | 诊断完成 -> 修复开始 |
| 2.6 ITERATION COMPLETE | STEP 7 (双向验证) 结束 | 一轮完整迭代结束 |
| 2.7 GOAL ACHIEVED | 工作流终止 | CRITICAL=0 && HIGH=0 |

### 5.2 Session JSON Extensions

Add progress-tracking fields to `session-{sessionId[:8]}.json`:

```json
{
  "schemaVersion": "3.2.0",
  "sessionId": "...",
  "step": 1,
  "itemStates": {},
  "mode": "normal|degraded",
  "silentMsgCount": 0,
  "waitRounds": 0,
  "version": "v3.2.0",
  "checksum": "<sha256>",

  "progress": {
    "iteration": 2,
    "phase": "scan",
    "agentsLaunched": 8,
    "agentsCompleted": 5,
    "agentsTimedOut": 0,
    "verdictDistribution": { "PASS": 2, "PARTIAL": 2, "FAIL": 1 },
    "severityCounts": { "CRITICAL": 1, "HIGH": 3, "MEDIUM": 5, "LOW": 2 },
    "lastHeartbeatAt": "2026-07-16T14:32:05Z",
    "workflowStartedAt": "2026-07-16T14:30:00Z",
    "hangAlerts": [
      { "agentKey": "usability-2", "detectedAt": "2026-07-16T14:35:00Z", "duration": 300, "resolved": false }
    ],
    "previousIteration": {
      "verdictDistribution": { "PASS": 3, "PARTIAL": 3, "FAIL": 2 },
      "severityCounts": { "CRITICAL": 3, "HIGH": 5, "MEDIUM": 7, "LOW": 4 }
    }
  }
}
```

### 5.3 Progress State Machine

```
                    +---> HUNG (alert emitted, waiting for user)
                    |
START --> RUNNING --+---> BATCH_COMPLETE (all agents done or timed out)
  |         |                     |
  |         +---> HEARTBEAT       +---> COMPLETE (verdict table emitted)
  |         |                     |
  |         +---> (60s loop)      +---> FIX_PHASE (transition to STEP 2 or 6)
  |
  +---> (first 30s, 0 completions) --> REASSURANCE
```

---

## 6. Full Example: Iteration #2 Timeline

```
T+0s    [CC] ============================================================
        [CC] code-shiniyaya 迭代 #2 启动
        [CC] ============================================================
        [CC] 扫描范围: src/parser.py, src/validator.py, src/api/handlers.py
        [CC] Agent 数量: 8 (可用性x2, 逻辑x2, 安全x1, 压力x2, 交叉引用x1)
        [CC] 预计耗时: ~90-180s
        [CC] 批次: 单批全并行 (batch_size=8)
        [CC] 模式: normal (Codex 双批准)
        [CC] ------------------------------------------------------------
        [CC] [启动中...]

T+30s   [CC] [迭代#2] 首批Agent仍在扫描中... (已等待30s, 8 Agent并行运行)

T+60s   [CC] [迭代#2 心跳 60s] 扫描中: 3/8 Agent完成 | PASS=2 FAIL=1 | 运行中: usability-2, logic-1, logic-2, stress-1, stress-2

T+120s  [CC] [迭代#2 心跳 120s] 扫描中: 6/8 Agent完成 | PASS=3 PARTIAL=2 FAIL=1 | 运行中: usability-2, stress-2

T+180s  [CC] [迭代#2 心跳 180s] 扫描中: 7/8 Agent完成 | PASS=4 PARTIAL=2 FAIL=1 | 运行中: usability-2 (仍挂起, 已运行185s)

T+240s  [CC] [迭代#2 心跳 240s] 扫描中: 7/8 Agent完成 | PASS=4 PARTIAL=2 FAIL=1 | usability-2 仍在挂起 (已超时 245s)

T+300s  [CC] ------------------------------------------------------------
        [CC] [!] AGENT 挂起检测
        [CC] ------------------------------------------------------------
        [CC] Agent:     usability-2 (类型: usability)
        [CC] 已运行:    305s (超时阈值: 300s)
        [CC] 状态:      无响应
        [CC] 当前批次:   7/8 Agent完成, usability-2 仍在运行
        [CC]
        [CC] 选项:
        [CC]   [1] 继续等待 (再等120s)
        [CC]   [2] 跳过此Agent (使用已有7个Agent结果)
        [CC]   [3] 终止本轮扫描
        [CC] ------------------------------------------------------------

T+310s  [User] 2

T+310s  [CC] [自动] usability-2 已跳过 (超时 310s)。继续使用 7/8 Agent结果。

T+310s  [CC] [迭代#2 批次完成 310s] 7/8 Agent完成 (1超时) | PASS=4 PARTIAL=2 FAIL=1 | CRITICAL=1 HIGH=3 MEDIUM=5 LOW=2 | 超时: usability-2

T+310s  [CC] ============================================================
        [CC] 迭代 #2 扫描完成 (总耗时: 310s)
        [CC] ============================================================
        [CC] Agent 结果:  8 启动 | 7 完成 | 1 超时 (usability-2)
        [CC]
        [CC] 判 verdict 分布:
        [CC]   PASS      4  (57.1%)  usability-1, logic-1, stress-1, xref
        [CC]   PARTIAL   2  (28.6%)  logic-2, security
        [CC]   FAIL      1  (14.3%)  stress-2
        [CC]   (超时)    1  (  -- )  usability-2
        [CC]
        [CC] 问题严重度汇总:
        [CC]   CRITICAL  1   parser.py:142  竞态条件可能导致数据丢失
        [CC]   HIGH      3   validator.py:88, handlers.py:210, parser.py:56
        [CC]   MEDIUM    5   (详情见 MULTI_AGENT_BUGS.md)
        [CC]   LOW       2   (详情见 MULTI_AGENT_BUGS.md)
        [CC]
        [CC] 待修复项: 11 个问题 (1 CRITICAL, 3 HIGH, 5 MEDIUM, 2 LOW)
        [CC] 下一步:   修复方案生成 (STEP 2)
        [CC] ============================================================

T+310s  [CC] ============================================================
        [CC] 修复阶段启动 -- 基于迭代 #2 扫描结果
        [CC] ============================================================
        [CC] 修复目标:   11 个问题 (1 CRITICAL, 3 HIGH, 5 MEDIUM, 2 LOW)
        [CC] 修复策略:
        [CC]   Phase A (立即):  1 项  parser.py:142
        [CC]   Phase B (优先):  3 项  validator.py:88, handlers.py:210, parser.py:56
        [CC]   Phase C (随后):  5 项  [MEDIUM]
        [CC]   Phase D (评估):  2 项  [LOW]
        [CC]
        [CC] Agent 分配:  5 Agent 并行设计修复方案
        [CC] 共享文件约束: parser.py Agent-1 -> Agent-2 顺序
        [CC] 预计耗时:    ~120-300s
        [CC] ------------------------------------------------------------
        [CC] [启动修复Agent...]

        ... (fix phase heartbeat + completion messages follow same pattern) ...

T+520s  [CC] ============================================================
        [CC] 迭代 #2 完成 -- 前后对比
        [CC] ============================================================
        [CC] 指标              迭代 #1         迭代 #2         变化
        [CC] ------------------------------------------------------------
        [CC] Agent PASS         3 (37.5%)      4 (57.1%)      +1
        [CC] Agent PARTIAL      3 (37.5%)      2 (28.6%)      -1
        [CC] Agent FAIL         2 (25.0%)      1 (14.3%)      -1
        [CC] CRITICAL 问题      3               1               -2
        [CC] HIGH 问题          5               3               -2
        [CC] MEDIUM 问题        7               5               -2
        [CC] LOW 问题           4               2               -2
        [CC] 总问题数           19              11              -8
        [CC] ------------------------------------------------------------
        [CC] 状态: 收敛中 (问题数 -42%)
        [CC] 剩余 CRITICAL: parser.py:142 (修复方案设计中)
        [CC] 建议: 完成 parser.py:142 修复后进入迭代 #3
        [CC] ============================================================

        ... (iteration #3) ...

T+1080s [CC] ============================================================
        [CC] [完成] code-shiniyaya 迭代工作流达成目标
        [CC] ============================================================
        [CC] 总迭代次数:   3
        [CC] 总耗时:       约 18 分钟
        [CC] 扫描Agent:   24 启动 | 22 完成 | 2 超时
        [CC] 修复Agent:   15 启动 | 15 完成 | 0 失败
        [CC]
        [CC] 最终状态:
        [CC]   CRITICAL  0  (初始: 3)  全部已修复
        [CC]   HIGH      0  (初始: 5)  全部已修复
        [CC]   MEDIUM    2  (初始: 7)  5已修复, 2降级 (用户确认跳过)
        [CC]   LOW       3  (初始: 4)  1已修复, 3已知且接受
        [CC]
        [CC] Agent PASS 率演进:
        [CC]   迭代 #1:  37.5% (3/8)
        [CC]   迭代 #2:  57.1% (4/7)
        [CC]   迭代 #3:  87.5% (7/8)
        [CC]
        [CC] 产物:
        [CC]   - reports/FOR_CODEX_迭代3_扫描完成.md
        [CC]   - reports/MULTI_AGENT_BUGS.md
        [CC]   - reports/MANUAL_FIXES.md
        [CC]
        [CC] [code-shiniyaya v3.2.0] CC<-->Codex 双重检验工作流完成。
        [CC] ============================================================
```

---

## 7. Summary of All CC Output Formats

| # | Checkpoint | Format Key | Frequency | Can Be Suppressed? |
|---|-----------|------------|-----------|-------------------|
| 1 | WORKFLOW START | Full banner with file list, agent count, ETA | Once per iteration | No |
| 2 | First-result reassurance | `[迭代#N] 首批Agent仍在扫描中... (已等待30s, N Agent并行运行)` | Once per iteration (at T+30s if 0 completions) | Yes (if any agent completes before T+30s) |
| 3 | Heartbeat | `[迭代#N 心跳 {elapsed}s] 扫描中: {done}/{total} Agent完成 \| {verdicts} \| 运行中: {keys}` | Every 60s during agent execution | Yes (if batch completes within 10s of heartbeat) |
| 4 | Batch completion | `[迭代#N 批次完成 {elapsed}s] {done}/{total} Agent完成 \| {verdicts} \| {severities}` | Once per batch | No (but may coalesce with heartbeat) |
| 5 | Agent hang alert | Full alert banner with agent name, duration, options [1/2/3] | Once per hung agent (at 300s) | No (bypasses all anti-spam) |
| 6 | WORKFLOW COMPLETE | Full banner with verdict table, severity summary, next step | Once per scan/fix phase | No |
| 7 | FIX PHASE START | Full banner with fix targets, phases, agent allocation | Once per fix phase | No |
| 8 | ITERATION COMPLETE | Before/after comparison table | Once per iteration | No |
| 9 | GOAL ACHIEVED | Final celebration banner with stats, PASS-rate evolution, artifacts | Once (at workflow termination) | No |

---

## 8. Compact Mode

For very fast iterations (all agents complete <30s), use a single combined message:

```
[迭代#N 完成 22s] 8/8 Agent完成 | PASS=7 PARTIAL=1 | CRITICAL=0 HIGH=0 MEDIUM=1 LOW=0 | 目标已达成
```

This replaces checkpoints 1, 2, 4, 6, and 7 with a single line when the entire iteration is fast enough that intermediate updates would be noise.

**Threshold**: if total iteration time <45s, use compact mode. Otherwise, use full checkpoint sequence.
