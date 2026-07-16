# Progress Tracking System for code-shiniyaya Iterative Workflows

Version: 2.0.0 | 2026-07-16 | 5-agent collaborative design

## Core Architecture

```
Workflow Launch
├── CronCreate fireAt: +120s (tier2 check), +300s (tier3 check), +600s (tier4 kill)
├── 8 agents launched in ONE parallel block (no phase gates)
├── Watchdog agent: heartbeat log lines every 30s
├── log() calls: agent start/result/timeout, heartbeat, graduated response
└── On completion: CronDelete all 3 tier tasks, compute summary, persist STATE_JSON

Between tool calls, CC reads log() output and emits user-visible progress (see Checkpoint Templates below).
```

## Empirical Timing Data (754 agent notifications analyzed)

| Metric | Value | Implication |
|--------|-------|-------------|
| P50 duration | 116s | Half of agents finish under 2 min |
| 81.6% within | 300s (5 min) | Vast majority complete fast |
| P95 duration | 864s (14.4 min) | 5% tail |
| P99 duration | 1,157s (19.3 min) | 1% extreme tail |
| Max observed | 3,141s (52.3 min) | Full dynamic workflow |
| Token/duration correlation | r=0.053 | **Zero** — token count does NOT predict duration |
| Prompt length/duration correlation | r=0.184 | **Negligible** — short prompts can also hang |
| Overall hang rate | 9.5% | ~1 in 10 agents will hang |
| Catastrophic failure rate | 1/13 workflows | Complete collapse: all 8 agents die silently |

### Agent Type Reliability

| Agent Type | Hang Rate | P50 Duration | Recommended Timeout |
|-----------|-----------|-------------|---------------------|
| general-purpose | ~5% (est) | 104s | **600s** |
| Explore | ~6% (est) | ~110s | **600s** |
| cavecrew-investigator | ~3% (est) | ~90s | **600s** |
| Plan | ~8% (est) | 391s | **1,200s** |
| verify (cross-ref) | ~10% (est) | 132s | **1,500s** |
| workflow-subagent | 6.9% | 595s | **3,600s** |
| **universal default** | 9.5% | 116s | **900s** |

### Key Insight
81.6% finish within 5 min, but 9.5% hang. A **two-tier strategy** works best:
- **Soft timeout at 300s**: log warning, wait (95% will complete)
- **Hard timeout at 900s**: kill agent, recover partial (covers remaining 4%)

## Graduated Time-Based Escalation (4 Tiers)

| Tier | Name | Trigger | CC Action | User Communication |
|------|------|---------|-----------|-------------------|
| **1** GREEN | Normal | Agent returns < 120s | None | None (transparent) |
| **2** YELLOW | Slow | >120s AND >30% agents still running | Log warning to journal; if >30% flag as "possible system load" | "[!] {n}/{total} agents still running after 2 min" |
| **3** ORANGE | Suspicious | >300s (5 min) AND workflow not complete | Send message to parent: "continue or skip?" | "Agent {name} running 5+ min — may be stuck. Continue waiting or skip?" |
| **4** RED | Stuck | >600s (10 min) AND workflow not complete | Auto-kill via TaskStop; parse partial results; report missing agents | "Killed stuck workflow. {n}/{total} agents completed. Proceeding with partial results." |

**Implementation**: 3 one-shot `fireAt` CronCreate tasks at workflow launch (+120s, +300s, +600s). All 3 deleted via `CronDelete` when workflow completes naturally. Each check first looks for `workflow_complete` in journal — exits silently if found (race-condition safe).

**Primary trigger**: wall-clock from `fireAt` timestamps. **Secondary**: journal event gap (no log events in 180s → confidence boost for tier 3/4, not standalone trigger).

## Resumability Protocol

### State File (`{project}/.claude/memory/code-shiniyaya/workflow-state.json`)

```json
{
  "schemaVersion": "2.0.0",
  "lastRunId": "wf_1265a73c-bdf",
  "phase": "scan",
  "iteration": 3,
  "agents": { "launched": 8, "completed": 5, "timedOut": 2, "skipped": 1 },
  "slots": {
    "usability-1": { "status": "done", "verdict": "PARTIAL" },
    "usability-2": { "status": "done", "verdict": "PASS" },
    "logic-1":     { "status": "done", "verdict": "FAIL" },
    "logic-2":     { "status": "done", "verdict": "PASS" },
    "security":    { "status": "timeout", "verdict": null },
    "stress-1":    { "status": "done", "verdict": "PASS" },
    "stress-2":    { "status": "timeout", "verdict": null },
    "xref":        { "status": "skipped", "verdict": null }
  },
  "summary": { "pass": 4, "partial": 1, "fail": 1, "critical": 2, "high": 5 },
  "medianCompletionS": 62,
  "timestamp": "2026-07-16T14:30:00Z",
  "checksum": "<sha256>"
}
```

### Recovery Flow
1. New workflow launched with `resumeFromRunId`
2. Read `workflow-state.json`
3. Filter TASKS to only `{status: "timeout"}` and `{status: "skipped"}` slots
4. Launch replacement agents ONLY for those slots
5. Merge new results with existing partial results
6. Update `workflow-state.json`

### Post-Mortem: Parse journal.jsonl for partial results
```python
import json
with open('journal.jsonl') as f:
    results = [json.loads(l) for l in f if json.loads(l).get('type') == 'result']
ok = [r for r in results if (r.get('value') or r.get('result')) is not None]
# Aggregate findings from ok
```

## Progress Checkpoint Templates

### 1. WORKFLOW START
```
============================================================
code-shiniyaya 迭代 #{N} 启动
============================================================
扫描范围: {files}
Agent: 8 (可用性×2, 逻辑×2, 安全×1, 压力×2, 交叉引用×1)
预计: ~90-180s | 单Agent超时=300s | 工作流硬上限=600s
模式: {normal|degraded}
------------------------------------------------------------
[启动中...]
```

### 2. HEARTBEAT (every 60s, suppressed if another message in last 10s)
```
[迭代#{N} 💓 {elapsed}s] 扫描中: {done}/{total}完成 | PASS={p} PARTIAL={pt} FAIL={f}
```

### 3. AGENT HANG (tier 3, >300s per agent)
```
[!] Agent {name} 已运行 {elapsed}s — 可能卡住
选项: [继续等待 / 跳过此Agent / 终止工作流]
(120s无响应 → 自动按方案2处理: 跳过, 收集部分结果)
```

### 4. WORKFLOW COMPLETE
```
[迭代#{N} 扫描完成] {elapsed}s | {done}/{total} Agent返回 ({timedOut}超时)
PASS={p} PARTIAL={pt} FAIL={f} | CRITICAL={c} HIGH={h} MEDIUM={m} LOW={l}
{p0_count} P0问题待修复 → 启动修复阶段
```

### 5. FIX PHASE START
```
[迭代#{N} 修复阶段] 修复 {bug_count} 问题
Phase A (立即): {a_items}项 | Phase B (优先): {b_items}项
{cross_file_count}跨文件冲突 → 顺序执行
```

### 6. ITERATION COMPLETE (before/after comparison)
```
[迭代#{N} 完成] 本轮: PASS={p} FAIL={f} CRITICAL={c} HIGH={h}
vs 上轮: PASS={prev_p} FAIL={prev_f} CRITICAL={prev_c} HIGH={prev_h}
趋势: {converging|stable|diverging}
{f_remaining} FAIL + {c_remaining} CRITICAL + {h_remaining} HIGH 剩余
{goal_achieved ? '目标达成!' : '→ 下一个迭代'}
```

### 7. GOAL ACHIEVED (CRITICAL=0 AND HIGH=0)
```
============================================================
🎉 code-shiniyaya 零Bug达成!
============================================================
总迭代: {total_iterations} | 总耗时: {total_duration}
最终: PASS={final_p} FAIL=0 CRITICAL=0 HIGH=0
产物: {skill_path} | 报告: {report_paths}
============================================================
```

## Anti-Spam Rules
1. No progress message if another progress message was sent <10s ago
2. Report at batch completion, not per-agent (with 8 agents, per-agent = noise)
3. T+30s "first result" reassurance if 0 agents complete by then: "Agent仍在初始化, 稍等..."
4. Hang alerts bypass spam filter (always delivered) but fire only ONCE per agent
5. If all agents complete within 45s, use compact mode (no heartbeats, single summary)

## Workflow Script Template (integrated)

```javascript
export const meta = {
  name: 'code-shiniyaya-v{V}-iter{N}',
  description: '{N}-agent scan with hang detection',
  phases: [{ title: 'All', detail: 'All agents + watchdog in one parallel block' }],
}

var AGENT_TIMEOUT_S = 300       // 5 min soft timeout per agent
var WORKFLOW_CAP_S = 600        // 10 min hard cap
var HEARTBEAT_S = 30            // 30 sec watchdog polling
var MAX_AGENTS = 8
var SKILL = 'C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya\\SKILL.md'

var F = {
  type: 'object', required: ['verdict', 'issues'],
  properties: {
    verdict: { type: 'string', enum: ['PASS','PARTIAL','FAIL'] },
    issues: { type: 'array', items: { type: 'object', required: ['severity','description'],
      properties: { severity: { type: 'string', enum: ['CRITICAL','HIGH','MEDIUM','LOW'] }, description: { type: 'string' } } } },
  },
}

phase('All')

var TASKS = [/* 8 agent prompts */]
var startTime = Date.now()
var agentStartTimes = {}
var hangCount = 0

log('WORKFLOW_START iteration={N} agents=' + TASKS.length + ' timeout=' + AGENT_TIMEOUT_S + 's')

var results = await parallel(TASKS.map(function(t) {
  return function() {
    agentStartTimes[t.key] = Date.now()
    log('Agent ' + t.key + ' launched')

    var r = agent(t.prompt, { label: t.key, phase: 'All', schema: F })

    var elapsed = ((Date.now() - agentStartTimes[t.key]) / 1000).toFixed(1)

    if (r === null) {
      hangCount++
      log('[HANG] Agent ' + t.key + ' TIMED OUT after ' + elapsed + 's (hangCount=' + hangCount + ')')
    } else {
      log('Agent ' + t.key + ' verdict=' + r.verdict + ' elapsed=' + elapsed + 's')
    }
    return r
  }
}))

var ok = results.filter(Boolean)
var timedOut = TASKS.length - ok.length
var totalS = ((Date.now() - startTime) / 1000).toFixed(0)

// Compute verdict summary
var p=0, pt=0, f=0, c=0, h=0, m=0, l=0
ok.forEach(function(r) {
  if (r.verdict === 'PASS') p++
  if (r.verdict === 'PARTIAL') pt++
  if (r.verdict === 'FAIL') f++
  if (r.issues) r.issues.forEach(function(i) {
    if (i.severity === 'CRITICAL') c++
    if (i.severity === 'HIGH') h++
    if (i.severity === 'MEDIUM') m++
    if (i.severity === 'LOW') l++
  })
})

log('WORKFLOW_DONE iteration={N} elapsed=' + totalS + 's pass=' + p + ' partial=' + pt + ' fail=' + f + ' crit=' + c + ' high=' + h + ' timedOut=' + timedOut)

return { pass:p, partial:pt, fail:f, critical:c, high:h, medium:m, low:l, timedOut:timedOut, totalS:totalS, goalAchieved:(f===0 && c===0 && h===0) }
```

## Graduated Response Heuristics

| # | Heuristic | Formula | Threshold | Action |
|---|-----------|---------|-----------|--------|
| D1 | Agent null return | `r === null` | N/A | HANG (confirmed) |
| D2 | Single straggler | `agent_elapsed > median * 2 AND remaining === 1` | `median * 2` | SLOW (wait) |
| D3 | Multiple stragglers | `agent_elapsed > median * 2 AND remaining >= 2` | `median * 2` | HANG (partial collect) |
| D4 | All slow | `remaining > 0 AND all(elapsed > median * 3)` | `median * 3` | HANG (abort all) |
| D5 | Journal silence | `now - last_result > 120s AND remaining > 0` | 120s | HANG (escalate) |
| D6 | Workflow cap | `total_elapsed > WORKFLOW_CAP_S` | 600s | HANG (hard stop) |
| D7 | Repeated timeout | `same_key timed out 2+ consecutive runs` | 2 runs | SLOT (permanent fail) |

## Integration with code-shiniyaya SKILL.md

When the iterative scan+fix loop is invoked, CC SHALL:
1. Launch the workflow as a background task
2. Set `ScheduleWakeup` for 60s to check progress
3. On each wakeup: read workflow output file, emit appropriate checkpoint template
4. If tier 3/4 escalation fires: follow the escalation table
5. On workflow completion: emit WORKFLOW COMPLETE template, determine if goal achieved
6. If goal NOT achieved: extract findings, launch 5-agent fix phase, re-scan
7. If goal achieved: emit GOAL ACHIEVED template, stop

## Key Anti-Patterns Avoided
- NO phase() gates — all agents in one parallel block (silent hang = other dimensions still complete)
- NO CronCreate polling loop — one-shot fireAt tasks only (no recurring cron pollution)
- NO per-agent progress spam — batch-level granularity with anti-spam timing
- NO wall-clock dependency in CC logic — timeouts handled by infrastructure (CronCreate fireAt + Agent tool timeout)
- NO manual journal parsing by user — STATE_JSON auto-generated at workflow completion
