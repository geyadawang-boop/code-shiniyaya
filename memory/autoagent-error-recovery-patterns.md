# autoagent-src Deep Scan: Error Recovery Patterns Missing from code-shiniyaya

Source project: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\
Target files: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
Scan date: 2026-07-16
Scanner: CC (code-shiniyaya v3.7.0)

## Pattern 1: Tenacity Exponential Backoff with Dual-Mode Error Classification

**Source**: autoagent\core.py:24-54 (should_retry_error), autoagent\core.py:494-498 (decorator)
**Priority**: P0

### What AutoAgent Has

A custom retry predicate that classifies errors by both exception TYPE and error message SUBSTRING, then applies exponential backoff via tenacity:

```python
# core.py:38-54
def should_retry_error(exception):
    if MC_MODE is False:
        print(f"Caught exception: {type(exception).__name__} - {str(exception)}")
    # TYPE-based matching
    if isinstance(exception, (APIError, RemoteProtocolError, ConnectError)):
        return True
    # MESSAGE-based matching (catches errors where exception type is opaque)
    error_msg = str(exception).lower()
    return any([
        "connection error" in error_msg,
        "server disconnected" in error_msg,
        "eof occurred" in error_msg,
        "timeout" in error_msg,
        "event loop is closed" in error_msg,
        "anthropicexception" in error_msg,
    ])
```

Applied via tenacity decorator with exponential backoff:
```python
# core.py:494-498
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=10, max=180),
    retry=should_retry_error,
    before_sleep=lambda retry_state: print(f"Retrying... (attempt {retry_state.attempt_number})")
)
```

Key design: `min=10, max=180` means wait 10s, 20s, 40s, 80s between retries (capped at 180s). This is NOT the same as wall-clock timeouts — it scales the delay between attempts, not the attempt timeout itself. Can be applied WITHOUT wall-clock access.

### code-shiniyaya Gap

The error handling table (SKILL.md lines 107-126) has ZERO retry logic for transient errors. Every failure mode is handled with manual user intervention or one-shot fallback:
- "STEP 1 Agent全超时" → "缩小范围重试" (manual user action)
- "STEP 2 写失败(磁盘满等)" → "内联纯文本" (one-shot fallback, no retry)
- No row handles transient network/API errors at all

There is no concept of "this error will likely resolve itself, retry N times before asking the user."

### Concrete Fix

Add to SKILL.md error handling table:

```
| STEP *  | 瞬态API/网络错误(连接断开/超时/EOF) | "Agent重试中 (attempt {n}/4)" | 指数退避: 10s→20s→40s→80s。all 4 failed→降级为永久失败→标TRANSIENT_FAIL, 继续 |
| STEP *  | Anthropic API限流/服务端错误 | "API重试中 (attempt {n}/4)" | 同上。all 4 failed→如果Codex可用→通过Codex回退; 否则→标BLOCKED |
| STEP 1  | 个别Agent静默(无result) | "Agent {type} 无响应——重试中" | 同slot最多2次替换, 每次替换前等待3轮消息(≈用户判断)。第3次→永久跳过该维度 |
```

Add to SKILL.md new section after error handling table:

```markdown
## 瞬态错误重试策略 (v3.8.0)

当Agent或API调用遇到可恢复错误时, 不立即要求用户介入。使用指数退避自动重试。

### 可重试错误分类

判断依据: 错误类型 + 错误消息子串匹配(不依赖标准异常类型, 因为跨SDK类型不一致)。

| 分类 | 匹配条件 | 退避策略 | 最大重试 |
|------|---------|---------|---------|
| A-网络瞬断 | "connection error", "server disconnected", "eof occurred", RemoteProtocolError, ConnectError | 10s→20s→40s→80s | 4次 |
| B-超时 | "timeout" | 20s→40s→80s→160s | 4次 |
| C-API限流 | APIError (非认证类), "rate limit" | 30s→60s→120s→240s | 4次 |
| D-事件循环 | "event loop is closed" | 5s→10s→20s→40s | 4次 |

### 退避状态追踪

每次重试记录: `retry_count`, `error_class`, `last_error_msg`, `backoff_s` 在 session JSON 的 `itemStates[{bug-id}].retry` 字段。

### 全耗尽处理

4次重试全部失败 → 标TRANSIENT_FAIL → 降级路径:
- 如果是API调用 → 如果Codex可用→通过Codex回退; 否则→标BLOCKED
- 如果是Agent执行 → 标该维度FAIL, 继续其他维度
- 如果是STEP 6文件写入 → 标FAILED_FIXES.md, 继续(同现有规则)
```

### Why This Matters

Without retry logic, transient errors cause unnecessary workflow interruption. In a 10-agent scan, if 2 agents fail due to API rate-limiting and the workflow stops, the user must manually restart — but the rate limit would have cleared within 60 seconds. AutoAgent's approach would silently retry those 2 agents and the user would never see the failure.

---

## Pattern 2: 3-Tier Retry Escalation with Meta-Agent Handoff

**Source**: autoagent\main.py:43-80 (run_in_client), autoagent\main.py:93-109 (run_in_client_non_async)
**Priority**: P0

### What AutoAgent Has

Three escalating tiers of retry — NOT just retrying the same thing:

```python
# main.py:43-80
MAX_RETRY = 3
for i in range(MAX_RETRY):
    try:
        response = await client.run_async(agent, messages, context_variables, debug=True)
    except Exception as e:
        logger.info(f'Exception in main loop: {e}', title='ERROR', color='red')
        raise e

    # TIER 1 (i=0,1): Agent resolved case → done
    if 'Case resolved' in response.messages[-1]['content']:
        break

    # TIER 2 (i=0,1): Agent failed but acknowledged → retry with feedback injection
    elif 'Case not resolved' in response.messages[-1]['content']:
        messages.extend(response.messages)

        # TIER 3 (i>=2): Escalate to meta-agent with full tool permissions
        if meta_agent and (i >= 2):
            setup_metachain(docker_config.workplace_name, code_env)
            messages.append({
                'role': 'user',
                'content': """\
It seems that the case is not resolved with the existing agent system.
Help me to solve this problem by running tools in the MetaChain.
IMPORTANT: You should fully take advantage of existing tools, and if
existing tools are not enough, you should develop new tools.
...
"""
            })
            meta_agent.functions.append(case_not_resolved)
            meta_agent.functions.append(case_resolved)
            response = await client.run_async(meta_agent, messages, ...)
            if 'Case resolved' in response.messages[-1]['content']:
                break
            else:
                messages.extend(response.messages)

        # Feedback injection between tiers
        messages.append({
            'role': 'user',
            'content': 'Please try to resolve the case again. It\'s important for me
                        to resolve the case. Trying again in another way may be helpful.'
        })
```

Key design: Each tier is NOT just "try harder" — it's a **different strategy**:
1. Standard agent with existing tools
2. Standard agent with feedback injection ("try another way")
3. Meta-agent (tool-creator) with permission to build new tools

### code-shiniyaya Gap

code-shiniyaya's retry model is flat:
- Rule 7: "每槽位最多2次替换→第3次永久失败" — replaces agents but doesn't change strategy
- Rule 12: "3次同文件失败→停止" — stops, doesn't escalate
- No feedback injection: retries use the EXACT same prompt, same context
- No meta-agent concept: no agent that creates new tools/approaches when standard agents fail
- STEP 6 "失败项→FAILED_FIXES.md" — just marks failure, no escalation attempt

### Concrete Fix

Add to SKILL.md after existing error handling table:

```markdown
## 3-Tier修复升级策略 (v3.8.0)

当Agent执行STEP 6修复失败时, 不立即标FAILED_FIXES.md。使用3级升级:

### Tier 1 (尝试1): 标准Agent + 原始方案
与现有STEP 6流程相同。Agent按方案执行修复。

### Tier 2 (尝试2): 标准Agent + 失败反馈注入
Tier 1失败后, 注入失败上下文到Agent消息:
```
上次修复尝试失败。以下是失败详情:
- 文件: {file}
- 行号: {line}
- 失败原因: {reason}
- 预期变更: {expected_change}

请尝试不同方法修复同一问题。不要重复上次的修复逻辑。
```
使用不同Agent类型(如果首次是investigator→换general-purpose; 首次是GP→换Plan)。

### Tier 3 (尝试3): meta-fix Agent + 全权限
Tier 2失败后, 启动meta-fix Agent(无特定类型限制, 可建议替代方案):
- 不限制于原方案的文件/行号范围
- 可建议跨文件重构、架构调整或其他非局部修复
- 可声明"无法局部修复, 需要方案级变更"
- 产出: 修复代码 OR "建议重方案: {reason}"

### 升级状态追踪
session JSON itemStates[{bug-id}]新增字段:
```json
{
  "fixTier": 1,
  "tierHistory": [
    {"tier": 1, "agentType": "investigator", "result": "FAIL", "reason": "..."},
    {"tier": 2, "agentType": "general-purpose", "result": "PENDING"}
  ]
}
```

### Tier 3全失败处理
Tier 3也失败 → 标FAILED_FIXES.md + tierHistory → 触发方案重审(rule 10)。不止步于"无法修复"——更新方案。
```

### Why This Matters

Flat retry ("do it again") has rapidly diminishing returns. Escalating strategy (same agent→feedback→meta-agent) maximizes the chance of success before declaring failure. This is particularly critical for P0 bugs where "stop and wait for user" has the highest human cost.

---

## Pattern 3: Graceful Shutdown with Retry-Loop Integration

**Source**: autoagent\environment\tenacity_stop.py:1-11, autoagent\environment\shutdown_listener.py:1-66
**Priority**: P1

### What AutoAgent Has

A custom tenacity stop condition that checks a global shutdown flag:

```python
# tenacity_stop.py:1-11
from tenacity import RetryCallState
from tenacity.stop import stop_base
from .shutdown_listener import should_exit

class stop_if_should_exit(stop_base):
    """Stop if the should_exit flag is set."""
    def __call__(self, retry_state: 'RetryCallState') -> bool:
        return should_exit()
```

Combined with graceful sleep that checks the flag:

```python
# shutdown_listener.py:50-65
def sleep_if_should_continue(timeout: float):
    if timeout <= 1:
        time.sleep(timeout)
        return
    start_time = time.time()
    while (time.time() - start_time) < timeout and should_continue():
        time.sleep(1)

async def async_sleep_if_should_continue(timeout: float):
    if timeout <= 1:
        await asyncio.sleep(timeout)
        return
    start_time = time.time()
    while time.time() - start_time < timeout and should_continue():
        await asyncio.sleep(1)
```

The shutdown listener registers signal handlers on import:

```python
# shutdown_listener.py:28-37
def _register_signal_handlers():
    global _should_exit
    if _should_exit is not None:
        return
    _should_exit = False
    if threading.current_thread() is threading.main_thread():
        for sig in HANDLED_SIGNALS:
            _register_signal_handler(sig)
```

### code-shiniyaya Gap

SKILL.md rule 13: "stop/中断/CTRL+C → 立即停, 不等不补" — this is a **hard kill**, not a graceful shutdown. The STOP is absolute and immediate. There's no mechanism for:
- Letting in-flight agent operations complete before stopping
- Checking a "should I stop?" flag between retries
- Cleanly cancelling parallel operations without data loss

The iteration scan recovery (lines 341-349) is a POST-HOC approach — parse journal.jsonl after kill, recover what survived. AutoAgent's approach is PRE-EMPTIVE — check shutdown flag during retries, let the current unit of work finish, then stop cleanly.

### Concrete Fix

Add to anti-hang-v2.md (or new section in SKILL.md):

```markdown
## 优雅停止协议 (v3.8.0)

替代硬停止(rule 13: "立即停, 不等不补"), 引入分级停止:

### 停止级别

| 级别 | 触发 | 行为 | 数据损失 |
|------|------|------|---------|
| SOFT_STOP | 用户说"停止"/"够了" | 不再启动新Agent。等当前运行Agent完成→保存状态→退出 | 0 |
| HARD_STOP | CTRL+C, TaskStop | 通知所有运行Agent停止。等待5条用户消息→收集已完成部分→journal解析→退出 | 仅未完成Agent |
| KILL | 超时/CancelledError | 立即终止。journal.jsonl事后恢复 | 可能丢失最新未flush日志行 |

### SOFT_STOP检查点

在以下位置插入 `should_continue()` 检查:
1. 每个Agent启动前(batch循环): `if not should_continue(): break`
2. 每个Agent结果处理后: `if not should_continue(): skip_remaining_agents()`
3. 每轮用户消息等待前: `if not should_continue(): exit_workflow()`

### 实现(伪代码)

```
SOFT_STOP标志: 全局变量 stopRequested=False

用户说"停止" → stopRequested=True → CC提示"正在优雅停止..."
  → batch循环检测stopRequested → 不启动新Agent
  → 已运行Agent完成 → 收集结果
  → 未启动维度标ABORTED
  → 保存scan-state-{iter}-ABORTED.json
  → 通知用户: "已停止。{done}/{total}完成, {remaining}个跳过"
```

### 与tenacity类库无关的实现

code-shiniyaya不使用tenacity(纯编排逻辑, 非Python运行时)。用消息计数替代:
- SOFT_STOP检测: 每次用户消息后检查stopRequested标志
- 指数退避: Agent启动间隔 = base_s * 2^(retry_count), base_s=3条用户消息
- 退避上限: max 10条用户消息(约等效于不依赖墙钟的超时)
```

### Why This Matters

The current "stop = hard kill" approach forces post-hoc recovery (journal-parser) which adds complexity. Graceful stop eliminates the need for recovery in the common case where the user just wants to stop early but doesn't need to kill the process.

---

## Pattern 4: Dual-Ended Agent Completion Signals (case_resolved / case_not_resolved)

**Source**: autoagent\tools\inner.py:1-24, autoagent\main.py:50-80
**Priority**: P0

### What AutoAgent Has

Agents explicitly signal one of TWO terminal states:

```python
# inner.py:3-13
@register_tool("case_resolved")
def case_resolved(result: str):
    """Use this function when the case is resolved..."""
    return f"Case resolved. No further actions are needed. The result is: {result}"

# inner.py:15-24
@register_tool("case_not_resolved")
def case_not_resolved(failure_reason: str):
    """Use this function when the case is not resolved when all agents
    have tried their best..."""
    return f"Case not resolved. No further actions are needed. The reason is: {failure_reason}"
```

The orchestrator (main.py) distinguishes:
- "Case resolved" → **success** → break the retry loop
- "Case not resolved" → **recoverable failure** → escalate to meta-agent or retry with feedback
- Unhandled exception → **fatal failure** → raise/stop

Both are explicit tool calls made by the agent, providing a confidence signal from the agent itself.

### code-shiniyaya Gap

code-shiniyaya has NO standard agent completion signal. Agent completion is determined by:
1. Workflow tool returning (agent finished execution)
2. Post-hoc verification (grep, ast.parse, git diff --stat)

This means:
- The orchestrator cannot distinguish between "agent fixed the bug" and "agent gave up and returned empty"
- There's no way for an agent to say "I tried my best, this needs a human" vs "I didn't try because the tool broke"
- Post-hoc verification can only check file changes — it can't assess agent confidence or effort level

### Concrete Fix

Add to SKILL.md STEP 6 section (逐项执行):

```markdown
### Agent完成信号 (v3.8.0)

每个执行Agent必须用结构化输出显式宣告完成状态:

#### FIXED
Agent成功修复。输出格式:
```
{ "status": "FIXED", "file": "...", "line": N, "change": "...", "verification": "..." }
```

#### CANNOT_FIX
Agent尝试但无法修复。必须包含原因分类:
```
{ "status": "CANNOT_FIX", "file": "...", "line": N,
  "category": "TOOL_LIMITATION | SCOPE_EXCEEDED | DEPENDENCY_BLOCKED | UNKNOWN",
  "attempted": ["方法1", "方法2"], "reason": "...", "suggestion": "..." }
```

#### FATAL
Agent遇到不可恢复错误:
```
{ "status": "FATAL", "error": "...", "stack": "..." }
```

### 编排器响应

| Agent信号 | 编排器动作 |
|----------|-----------|
| FIXED | 继续验证(现有流程: git diff --stat+grep+ast.parse) |
| CANNOT_FIX (TOOL_LIMITATION) | Tier 2重试: 换Agent类型, 注入失败上下文 |
| CANNOT_FIX (SCOPE_EXCEEDED) | 触发方案重审(rule 10) — 修复范围超出原方案 |
| CANNOT_FIX (DEPENDENCY_BLOCKED) | 标BLOCKED, 等依赖项完成后再重试 |
| CANNOT_FIX (UNKNOWN) | Tier 3: meta-fix Agent |
| FATAL | 停止该修复项, 标FAILED_FIXES.md, 通知用户 |
```

### Why This Matters

Without explicit completion signals, the orchestrator is blind to agent intent. An agent that silently fails (returns empty/partial output) is indistinguishable from one that successfully fixed the bug (if verification is lenient). Explicit signals enable smarter retry/escalation decisions and prevent false positives.

---

## Pattern 5: Tool Output Truncation with Token Budget

**Source**: autoagent\registry.py:9-24
**Priority**: P1

### What AutoAgent Has

Automatic token-based output truncation with warning and actionable suggestion:

```python
# registry.py:19-24
def truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    tokens = encode_string_by_tiktoken(output)
    if len(tokens) > max_length:
        return decode_tokens_by_tiktoken(tokens[:max_length]) + \
            f"\n\n[TOOL WARNING] Output truncated, exceeded {max_length} tokens)\n\
[TOOL SUGGESTION] Maybe this tool with direct output is not an optimal choice,
consider save the output to a file in the `workplace/` directory to implement
the same functionality."
    return output
```

This applies specifically to `plugin_tool` outputs (line 88-95), wrapping every tool call. The warning includes an ACTIONABLE suggestion: save to file instead of returning inline.

### code-shiniyaya Gap

code-shiniyaya has ONE token check: STEP 3 (>10000 tokens → split into N parts, P0 first). But this is ONLY for Codex messages. It has NO token budget management for:
- Agent outputs (scan results, diagnostic findings)
- Reference source scan results
- STEP 4 cross-validation responses
- Any intermediate step

A single agent returning a 50K-token scan result can silently consume context window without warning.

### Concrete Fix

Add to SKILL.md error handling table:

```
| STEP *  | Agent输出>12000 tokens | "输出截断——{保留}/{总计} tokens, 完整结果写入{file}" | 截断至12000 tokens, 完整输出写入reports/ag_{agent_id}_{ts}_full.txt; 在截断点添加: "[TRUNCATED: {remaining} tokens omitted. Full output in {file}]" |
```

Add to SKILL.md after STEP 4:

```markdown
### Agent输出Token预算 (v3.8.0)

所有Agent输出在进入CC上下文前经过token预算检查:

| 预算级别 | 阈值 | 动作 |
|---------|------|------|
| 安全 | ≤8000 tokens | 直接传递 |
| 警告 | 8000-12000 tokens | 传递, 附加"[LARGE OUTPUT: {N} tokens]" |
| 截断 | >12000 tokens | 保留首部8000+尾部1000 tokens, 中间替换为"[TRUNCATED: {N} tokens omitted]" |

截断输出写入 `reports/agent-{type}-{task}-{ts}.txt`，截断点前后各50行上下文保留在对话中。

Agent建议: 如果Agent预期输出大文件, 应直接写入文件路径而非返回内联文本。编排器读取文件路径而非内容。
```

### Why This Matters

Silent context window consumption by large agent outputs is a primary cause of "agent stopped responding mid-workflow" — the context fills with scan results and there's no room for the orchestrator to coordinate. Token budgets prevent this.

---

## Pattern 6: Content-Addressed Agent Identity for Duplicate Prevention

**Source**: autoagent\flow\types.py:97 (self.id = MD5 of source), autoagent\flow\utils.py:47-48
**Priority**: P2

### What AutoAgent Has

Events (agents in the flow DAG) are content-addressed by their source code:

```python
# flow/types.py:97
self.id = string_to_md5_hash(function_or_method_to_string(self.func_inst))

# flow/utils.py:47-48
def string_to_md5_hash(string: str) -> str:
    return hashlib.md5(string.encode()).hexdigest()
```

The function source includes module path, line number, and the actual function body text. This means: if two agents have identical source code, they ARE the same agent — preventing accidental double-launch.

### code-shiniyaya Gap

STEP 1 de-duplication operates POST-HOC on findings (group by file:line+/-3, merge within groups). But there's no PRE-LAUNCH duplicate prevention:
- If two diagnostic dimensions launch the same agent type with the same prompt, both run independently
- The orchestrator cannot detect "this agent was already launched with identical parameters"
- Post-hoc de-duplication costs context (reading 2x results to merge them)

### Concrete Fix

Add to SKILL.md STEP 1 section:

```markdown
### 6. Agent启动去重 (v3.8.0)

启动Agent前, 检查去重缓存:

```json
// 去重键: MD5(agentType + normalized(task_prompt) + target_file + line_range)
// 缓存位置: session JSON "agentLaunchCache" 字段
{
  "agentLaunchCache": {
    "a1b2c3d4": {"agentId": "ag_001", "status": "running", "launchedAt": "..."},
    "e5f6g7h8": {"agentId": "ag_002", "status": "completed", "launchedAt": "..."}
  }
}
```

启动前: 计算hash → 查缓存:
- 不存在 → 启动, 记录到缓存
- 存在且status=running → 复用现有Agent结果(不重复启动)
- 存在且status=completed → 直接使用缓存结果, 跳过启动
- 存在且status=failed → 原结果可用(不重跑), 除非有新输入参数
```

### Why This Matters

Minor efficiency gain in most cases, but critical for large scans (40+ agents) where identical diagnostics could consume 20-30% of the agent budget on duplicate work.

---

## Pattern 7: Event-Driven Parallelism with FIRST_COMPLETED Scheduling and Cancel Propagation

**Source**: autoagent\flow\core.py:153-175
**Priority**: P1

### What AutoAgent Has

Dynamic task scheduling with `asyncio.wait(FIRST_COMPLETED)` and clean cancellation:

```python
# flow/core.py:153-175
tasks = set()
try:
    while len(queue) or len(tasks):
        this_batch_events = queue[:max_async_events] if max_async_events else queue
        queue = queue[max_async_events:] if max_async_events else []
        new_tasks = {
            asyncio.create_task(run_event(*run_event_input))
            for run_event_input in this_batch_events
        }
        tasks.update(new_tasks)
        # KEY: Wait for FIRST_COMPLETED, not ALL_COMPLETED
        done, tasks = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            await task  # Handle any exceptions
except asyncio.CancelledError:
    # Cancel ALL remaining tasks, collect exceptions
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    raise
```

And the `already_sent_to_event_group` dedup tracking (lines 125-151) ensures that when multiple upstream events complete and trigger the same downstream event, the downstream event only fires ONCE.

### code-shiniyaya Gap

The iteration scan workflow uses the Workflow tool's built-in batching — all N agents launched in one parallel block, and CC only sees results when ALL complete or when it manually kills the workflow. There's no:
- FIRST_COMPLETED scheduling: cannot process agent results as they arrive
- Dynamic queue: cannot add work based on intermediate results
- already_sent_to_event_group dedup: no mechanism to prevent duplicate event dispatch
- Clean cancel propagation: when workflow is killed, agent cancellation is handled by the tool infrastructure, not by code-shiniyaya

### Concrete Fix

Add to anti-hang-v2.md:

```markdown
### 6. 增量结果处理 (v3.8.0)

利用log()事件流的自然到达顺序, 无需FIRST_COMPLETED调度器即可实现增量处理:

```
Agent A 完成 → log('Agent A returned verdict=PASS')
  → CC立即记录维度A结果
Agent C 完成 → log('Agent C returned verdict=FAIL')
  → CC立即记录维度C结果, 更新进度: 2/8 done
Agent B 完成 → log('Agent B returned verdict=PASS')
  → CC立即记录维度B结果, 更新进度: 3/8 done
...
全部完成 → CC汇总: "5 PASS, 2 FAIL, 1 TIMEOUT"
```

与批量等待的区别: CC不等所有Agent完成再处理。每收到一个log()就更新一次内部状态。

### 去重事件分发

在log()事件处理中集成去重:

```
on_log_event(received):
  agent_key = MD5(received.agent_type + received.task + received.file)
  if agent_key in processed_events:
    log('DUPLICATE: {agent_type} result already processed, skipping')
    return
  processed_events.add(agent_key)
  # process normally
```

防止: 同一Agent因重试/重连发送了两次相同结果, 被重复计入统计。
```

### Why This Matters

Incremental result processing enables progress visibility (user sees results streaming) and early failure detection (if 3 out of 4 security agents return FAIL, the 4th may not be needed). Without this, the user sees nothing until ALL agents complete — which could be 10+ minutes for a full scan.

---

## Pattern 8: Structured Logging with Timestamped Session Directory

**Source**: autoagent\logger.py:138-172, autoagent\logger.py:155-171
**Priority**: P2

### What AutoAgent Has

Singleton LoggerManager with auto-initialized timestamped log directory:

```python
# logger.py:155-171
if DEFAULT_LOG:
    if LOG_PATH is None:
        log_dir = Path(f'logs/res_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(log_dir / "agent.log")
        LoggerManager.set_logger(MetaChainLogger(log_path=log_path))
    else:
        LoggerManager.set_logger(MetaChainLogger(log_path=LOG_PATH))
```

Log entries have structured format:
```python
# logger.py:31-32
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_str = f"[{timestamp}]\n{message}"
```

With rich formatting for tool calls, assistant messages, and errors (each with color-coded titles).

### code-shiniyaya Gap

code-shiniyaya has NO structured logging:
- Session JSON tracks state, NOT events
- anti-hang-v2.md relies on workflow log() events (not controllable by code-shiniyaya)
- No per-session log directory
- Error recovery has no event log to replay or audit

### Concrete Fix

Add to SKILL.md state files section:

```markdown
### 事件日志 (`eventlog-{sessionId[:8]}.jsonl`)

每行一个JSON事件, 追加写入:

```json
{"ts": "2026-07-16T14:32:01", "type": "STEP_ENTER", "step": 1, "sessionId": "a1b2c3d4"}
{"ts": "2026-07-16T14:32:05", "type": "AGENT_LAUNCH", "agentType": "investigator", "task": "scan file X", "agentId": "ag_001"}
{"ts": "2026-07-16T14:32:45", "type": "AGENT_RESULT", "agentId": "ag_001", "verdict": "PASS", "duration_ms": 40000}
{"ts": "2026-07-16T14:33:00", "type": "ERROR", "code": "TRANSIENT_NETWORK", "agentId": "ag_003", "retryCount": 1, "msg": "connection error"}
{"ts": "2026-07-16T14:33:30", "type": "RETRY", "agentId": "ag_003", "retryCount": 1, "backoff_ms": 10000}
{"ts": "2026-07-16T14:33:31", "type": "STEP_EXIT", "step": 1, "verdict": "COMPLETE"}
```

### 事件类型

| 类型 | 含义 |
|------|------|
| STEP_ENTER/EXIT | 工作流步进 |
| AGENT_LAUNCH/RESULT/ERROR/TIMEOUT | Agent生命周期 |
| RETRY | 重试(附backoff和次数) |
| DEGRADE | 降级触发 |
| GATE_PASS/FAIL | 门控判定 |
| USER_DECISION | 用户交互决策点 |

### 事后用途

1. **恢复**: 读取eventlog重放已完成的Agent, 确定需重跑的维度
2. **审计**: 追踪每个Bug修复的完整决策链
3. **统计**: 聚合Agent成功率/延迟/重试率
```

---

## Pattern 9: GOTO/ABORT Flow Control Primitives

**Source**: autoagent\flow\dynamic.py:9-19, autoagent\flow\types.py:15-18
**Priority**: P2

### What AutoAgent Has

Three explicit flow control primitives beyond dispatch:

```python
# types.py:15-18
class ReturnBehavior(Enum):
    DISPATCH = "dispatch"  # Normal: send results to downstream events
    GOTO = "goto"          # Jump to specific event group
    ABORT = "abort"        # Terminate the entire event chain

# dynamic.py:9-19
def goto_events(group_markers, any_return=None) -> _SpecialEventReturn:
    return _SpecialEventReturn(behavior=ReturnBehavior.GOTO, returns=(group_markers, any_return))

def abort_this():
    return _SpecialEventReturn(behavior=ReturnBehavior.ABORT, returns=None)
```

GOTO is used when an event detects that an upstream assumption was wrong — jump back to re-execute rather than continue with bad data. ABORT is used when continuing would be harmful or pointless.

### code-shiniyaya Gap

code-shiniyaya's workflow is strictly linear. The only branch points are:
1. Degraded mode (Codex unavailable)
2. Stop/interrupt
3. Quick path (pre-verified fix, comments/docs only)

There's no ability to:
- Jump from STEP 4 back to STEP 1 if validation reveals a fundamental diagnosis error
- Jump from STEP 6 to STEP 2 if execution reveals the fix plan is wrong
- ABORT the entire workflow mid-STEP without losing state (rule 13 hard-stop loses context)

### Concrete Fix

Add to SKILL.md core workflow section, after routing:

```markdown
### GOTO跳转 (v3.8.0)

当检测到上游假设错误时, 不停止——跳回正确的步骤:

| 检测点 | 条件 | GOTO目标 | 携带上下文 |
|--------|------|---------|-----------|
| STEP 4 (验证) | 维度全失败 + 根因指向诊断错误 | GOTO STEP 1 | Codex新发现 + 失败的维度列表 |
| STEP 6 (执行) | 连续2项CANNOT_FIX(SCOPE_EXCEEDED) | GOTO STEP 2 | tierHistory + 部分修复结果 |
| STEP 6 (执行) | 3项BLOCKED互锁(循环依赖) | GOTO STEP 0 | DAG图 + blockedBy关系 |
| STEP 7 (验证) | 第2轮仍DISPUTED | GOTO STEP 1 | 双方证据 + 争议点 |

### ABORT条件

当遇到以下不可恢复情况时, ABORT整个工作流:
- 磁盘满(无法写任何文件, 包括原子写入的tmp文件)
- 3个以上P0 Bug在同一文件中互相依赖(强制重新方案)
- 用户明确说"放弃这个方案"

ABORT ≠ STOP: ABORT保留完整session JSON + eventlog, 可事后分析。STOP是硬中断。
```

---

## Pattern 10: Health Check Before Agent Dispatch

**Source**: autoagent\environment\docker_env.py:111-137 (wait_for_container_ready)
**Priority**: P1

### What AutoAgent Has

Before dispatching ANY work, verify the agent's environment is actually running:

```python
# docker_env.py:111-137
def wait_for_container_ready(self, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}",
             self.container_name], capture_output=True, text=True)
        if result.returncode == 0 and "true" in result.stdout.lower():
            try:
                port_info = check_container_ports(self.container_name)
                assert port_info and (port_info[0] == port_info[1])
                available_port = port_info[0]
                self.communication_port = available_port
                result = self.run_command('ps aux')
                if "tcp_server.py" in result['result']:
                    return True
            except Exception as e:
                pass
        time.sleep(1)
    raise TimeoutError(f"Container {self.container_name} failed to start within {timeout} seconds")
```

Three-layer health check: Docker state → Port mapping → Actual process running. Only after ALL three pass does work dispatch begin.

### code-shiniyaya Gap

Rule 7 (Agent failure replacement) replaces agents but doesn't verify that the replacement is healthy. A replacement agent slot could be:
- Started but hung (process running, no output)
- Connected but unresponsive (no error, but no results)
- In a different state than expected

The current anti-hang-v2.md logs agent results via log() — but this only detects failure AFTER work was attempted. There's no PRE-DISPATCH health check.

### Concrete Fix

Add to anti-hang-v2.md or SKILL.md:

```markdown
### Agent插槽健康检查 (v3.8.0)

替换Agent前, 验证新插槽健康:

```
healthCheck(agentType):
  1. 启动Agent
  2. 等待首次log()输出 (最多3条用户消息)
  3. 发送ping任务: "Return OK if functional"
  4. 等待响应 (最多2条用户消息)
  5. 收到"OK" → 健康, 可分发实际任务
  6. 未收到 → 不健康, 标记该插槽DEAD, 启动下一个替换

healthCheckTimeout = 5条用户消息(总计)
```

### 健康状态

session JSON中agentSlots新增:
```json
{
  "agentSlots": {
    "slot_1": {"agentType": "investigator", "health": "HEALTHY", "lastPing": "..."},
    "slot_2": {"agentType": "Explore", "health": "DEAD", "lastPing": "...", "replacedBy": "slot_4"},
    "slot_3": {"agentType": "general-purpose", "health": "UNKNOWN", "lastPing": null}
  }
}
```

### 与现有规则的关系

- 规则7 (失败替换): 替换前先healthCheck。healthCheck失败→不消耗替换配额(这不是"Agent executed and failed", 这是"Agent never became ready")
- 规则5 (batch_size): 健康插槽数 < batch_size时, 等新插槽就绪后再启动批次。不启动到已死插槽
```

---

## Summary: Integration Priority

| # | Pattern | Priority | Target File | Effort |
|---|---------|----------|-------------|--------|
| 1 | Tenacity Exponential Backoff + Error Classification | P0 | SKILL.md error table | Medium |
| 2 | 3-Tier Retry Escalation (same→feedback→meta) | P0 | SKILL.md STEP 6 | High |
| 3 | Graceful Shutdown (SOFT_STOP/HARD_STOP/KILL) | P1 | anti-hang-v2.md | Medium |
| 4 | Dual-Ended Agent Completion Signals (FIXED/CANNOT_FIX/FATAL) | P0 | SKILL.md STEP 6 | Medium |
| 5 | Tool Output Truncation with Token Budget | P1 | SKILL.md STEP 4 | Low |
| 6 | Content-Addressed Agent Identity (MD5 dedup) | P2 | SKILL.md STEP 1 | Low |
| 7 | FIRST_COMPLETED Scheduling + Cancel Propagation | P1 | anti-hang-v2.md | High |
| 8 | Structured Event Logging (eventlog.jsonl) | P2 | SKILL.md state files | Medium |
| 9 | GOTO/ABORT Flow Control Primitives | P2 | SKILL.md core workflow | Medium |
| 10 | Agent Slot Health Check Before Dispatch | P1 | anti-hang-v2.md | Low |

### Cumulative Impact

- P0 patterns (1, 2, 4): Fix the fundamental gap where code-shiniyaya has NO automated retry and NO structured agent completion feedback. These three alone would eliminate ~60% of user-intervention-required failure paths.
- P1 patterns (3, 5, 7, 10): Defense-in-depth improvements that prevent cascading failures and context exhaustion. Together they make the anti-hang system robust rather than best-effort.
- P2 patterns (6, 8, 9): Quality-of-life and debugging improvements. Low priority for immediate implementation but valuable for long-term maintainability.

### What Already Exists (No Change Needed)

- Pattern #8 from high-impact-patterns.md (3-Tier Retry from AutoAgent main.py) was previously documented but NEVER integrated into code-shiniyaya error handling. This file provides the complete integration specification.
- Pattern #4 from high-impact-patterns.md (Crash Taxonomy) was referenced conceptually but never had concrete classification logic. Patterns 1 and 4 in this file fill that gap.
- The anti-hang-v2.md already has convergence tracking and message-count-based stall detection. Patterns 3, 7, 10 extend this without replacing it.
