# autoagent-src Deep Scan Findings -- code-shiniyaya Gap Analysis
# Date: 2026-07-16
# Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src
# Target: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md (v3.7.0)
# Dimension: Context management -- context_variables shared state bus, agent_teams dispatch dict, Result object with agent handoff

## P0: Critical Architectural Gaps (4 patterns)

### P0-1: context_variables Shared State Bus
**Source**: `autoagent/core.py:55`, `core.py:124-128`, `core.py:264-265`, `core.py:298-300`, `core.py:419`, `core.py:485`
**Pattern**: A `dict` (`context_variables`) that flows through every part of the MetaChain: injected into `Agent.instructions(context_variables)` for dynamic prompts, auto-injected into every tool call if the function signature has a `context_variables` parameter, accumulated from `Result.context_variables` returned by tools, carried in `Response.context_variables` for the caller.

Exact mechanism:
```python
# core.py:55
__CTX_VARS_NAME__ = "context_variables"

# core.py:124-128 -- dynamic instructions from context
context_variables = defaultdict(str, context_variables)
instructions = (
    agent.instructions(context_variables)
    if callable(agent.instructions)
    else agent.instructions
)

# core.py:264-265 -- auto-inject into tool calls
if __CTX_VARS_NAME__ in inspect.signature(func).parameters.keys():
    args[__CTX_VARS_NAME__] = context_variables

# core.py:298 -- tool can update context
partial_response.context_variables.update(result.context_variables)

# core.py:274 -- hide from model
params["properties"].pop(__CTX_VARS_NAME__, None)
if __CTX_VARS_NAME__ in params["required"]:
    params["required"].remove(__CTX_VARS_NAME__)

# core.py:489-493 -- Response carries context back
return Response(
    messages=history[init_len:],
    agent=active_agent,
    context_variables=context_variables,
)
```

**code-shiniyaya gap**: No shared state bus across the 7-step workflow. Each step generates data independently. Session JSON tracks `step` and `itemStates` but doesn't accumulate diagnostic findings, agent discoveries, or cross-step context. STEP 1 diagnosis results must be manually summarized and passed to STEP 2 via FOR_CODEX markdown. There is no programmatic context injection into agent prompts.

**Fix -- Add to SKILL.md** (new section after "状态文件"):

```markdown
## 工作流上下文总线 (v3.8.0)

`workflow_context` 是一个在7步流程中持久化的dict, 在所有Agent调用间共享。不同于会话JSON(只追踪状态), 上下文总线累积实际数据。

### 结构
```json
{
  "diagnosis": {
    "bugs": [{"id":"B1","file":"...","line":42,"severity":"P0","root_cause":"..."}],
    "agent_results": {"investigator":{"findings":[...]}, "debugging":{"stack_trace":"..."}}
  },
  "plan": {
    "phase_a": [{"bug_id":"B1","old_code":"...","new_code":"...","risk":"low"}],
    "phase_b": [...]
  },
  "codex": {
    "sent_at": "ISO8601", "response_received": false,
    "approved_items": [], "rejected_items": [], "new_findings": []
  },
  "execution": {
    "completed": ["B1"], "failed": [], "blocked": [],
    "applied_patches": {"B1":"git diff hash"}
  },
  "meta": {
    "mode": "normal", "degraded_reason": null,
    "round": 1, "disputed": false
  }
}
```

### 注入规则
1. Agent调用时: 将 `context_variables`(序列化为JSON) 追加到Agent系统提示词末尾, 以 `[WORKFLOW_CONTEXT]` 分隔。
2. Agent返回后: CC从Agent输出中解析任何 `CTX_UPDATE: {"key":"value"}` 行, 合并到workflow_context中。
3. 步骤转换时: 读取workflow_context, 传递给下一阶段Agent。
4. Agent不可见: workflow_context中的 `codex.sent_at` 等元数据字段在Agent注入时移除(类似core.py:140-143的隐藏逻辑)。

### 恢复时
从session JSON的 `workflow_context_snapshot` 恢复上下文总线, 确保中断恢复后Agent仍能获取已诊断的bug列表。
```

**Fix -- Add to anti-hang-v2.md** (new pattern):
```markdown
### Pattern: Context Bus Recovery
When workflow stalls and restarts: read `workflow_context_snapshot` from session JSON -->
pass to all re-spawned agents. Agents resume with accumulated knowledge,
not a cold start. Eliminates duplicate diagnosis after restart.
```

---

### P0-2: Result Object with Agent Handoff
**Source**: `autoagent/types.py:28-42`, `core.py:212-228`, `core.py:268`, `core.py:299-300`, `core.py:385-387`, `core.py:486-487`
**Pattern**: A `Result` Pydantic model with 4 fields: `value` (string result), `agent` (next agent to run, or None), `context_variables` (dict updates), `image` (optional base64). When a tool returns `Result(agent=next_agent)`, the MetaChain loop automatically switches `active_agent` to the returned agent. This is the handoff primitive.

Exact mechanism:
```python
# types.py:28-42
class Result(BaseModel):
    value: str = ""
    agent: Optional[Agent] = None
    context_variables: dict = {}
    image: Optional[str] = None

# core.py:212-228 -- handle_function_result
def handle_function_result(self, result, debug) -> Result:
    match result:
        case Result() as result:
            return result
        case Agent() as agent:
            return Result(value=json.dumps({"assistant": agent.name}), agent=agent)
        case _:
            try:
                return Result(value=str(result))
            except Exception as e:
                raise TypeError(...)

# core.py:298-300 -- after each tool call
partial_response.context_variables.update(result.context_variables)
if result.agent:
    partial_response.agent = result.agent

# core.py:385-387, 486-487 -- in the main loop
context_variables.update(partial_response.context_variables)
if partial_response.agent:
    active_agent = partial_response.agent
```

Combined with `system_triage_agent.py:39-54`:
```python
def transfer_to_filesurfer_agent(sub_task_description: str):
    return Result(value=sub_task_description, agent=filesurfer_agent)
def transfer_back_to_triage_agent(task_status: str):
    return Result(value=task_status, agent=system_triage_agent)
```

**code-shiniyaya gap**: CC agent batches are fire-and-forget. When STEP 1 launches 6+ agents in parallel, each agent runs independently. There is no mechanism for Agent A to say "I found something Agent B should investigate" during execution. Agent results are only merged post-hoc in the dedup step. No dynamic re-routing.

**Fix -- Add to SKILL.md** (add to "Agent编排" table):

```markdown
### HandoffResult协议 (v3.8.0)

每个Agent的输出必须以以下之一结尾:

```
HANDOFF: <target_agent_type> | <reason>
# 或
HANDOFF: none | <completion_status>
```

CC解析HANDOFF行:
- `HANDOFF: investigator | found cross-file import chain in src/utils/` --> 若investigator未达max_retries, 排队新investigator任务, 注入handoff上下文。
- `HANDOFF: none | completed` --> Agent完成, 不触发新任务。
- `HANDOFF: general-purpose | hit unknown pattern, falling back` --> 使用回退链(规则已有)但带显式原因。

HANDOFF目标Agent的提示词注入上一Agent的部分输出(最多800 tokens), 以 `[HANDOFF_CONTEXT from {source_agent}]` 为前缀。

### 批内Handoff限额
- 每个Agent最多触发1次handoff(防止无限链)。
- 同一目标Agent类型最多接收2次handoff/批次(防止过载)。
- Handoff产生的Agent计入总Agent上限(50)。
```

---

### P0-3: case_resolved / case_not_resolved Explicit Terminal Signals
**Source**: `autoagent/tools/inner.py:3-24`, `autoagent/main.py:7-28`, `main.py:50-52, 71-72`
**Pattern**: Two special tools that agents MUST call to terminate. The main loop (main.py:50-52) checks the LAST message content for `'Case resolved'` or `'Case not resolved'` to break the retry loop. This gives unambiguous terminal signals instead of relying on LLM to "just stop talking."

Exact mechanism:
```python
# inner.py:3-8
@register_tool("case_resolved")
def case_resolved(result: str):
    """...Please encapsulate your final answer (answer ONLY) within <solution> and </solution>."""
    return f"Case resolved. No further actions are needed. The result of the case resolution is: {result}"

# inner.py:15-24
@register_tool("case_not_resolved")
def case_not_resolved(failure_reason: str):
    return f"Case not resolved. No further actions are needed. The reason is: {failure_reason}"

# main.py:50-52 -- break condition
if 'Case resolved' in response.messages[-1]['content']:
    break
elif 'Case not resolved' in response.messages[-1]['content']:
    # escalate to meta-agent or append retry message
```

**code-shiniyaya gap**: CC has no explicit terminal signal from agents. The workflow relies on CC parsing agent output to judge completion. Rule 7 defines "Agent异常终止或挂起" but "success" is inferred from output quality, not a structured signal. This leads to ambiguity: is the agent done or just pausing? Is a partial result a failure or an intermediate state?

**Fix -- Add to SKILL.md** (add to "Agent编排" table):

```markdown
### Agent终端信号 (v3.8.0)

所有Agent必须在输出的最后一行包含以下终端信号之一:

```
TERMINAL: RESOLVED | <summary of what was done>
TERMINAL: UNRESOLVED | <reason -- e.g., "source file not found", "permission denied", "ambiguous code">
TERMINAL: PARTIAL | <what was found> | <what needs follow-up>
```

CC解析规则:
- RESOLVED: Agent成功完成任务。结果进入正常流程。
- UNRESOLVED: Agent尝试但失败。触发规则7替换逻辑。
- PARTIAL: 部分完成。剩余部分排队到同一Agent类型的另一实例(若配额允许)。
- 无TERMINAL行: Agent输出不完整/被截断 --> 标记为TIMED_OUT, 触发规则7。
- 同一Agent 2次TERMINAL: UNRESOLVED后 --> 升级到general-purpose回退Agent。

### TERMINAL与规则集成
| 终端信号 | 规则7(失败替换) | 规则12(3次失败停止) |
|----------|----------------|---------------------|
| RESOLVED | 不触发 | 不触发 |
| UNRESOLVED | 替换Agent(每槽位最多2次) | 同文件UNRESOLVED 3次 --> 触发 |
| PARTIAL | 不替换, 排队补全 | 不触发 |
| 无TERMINAL | 标记超时, 替换 | 累计同Agent 3次无TERMINAL --> 触发 |
```

---

### P0-4: Event-Driven DAG Engine for Step Orchestration
**Source**: `autoagent/flow/core.py:17-175`, `flow/types.py:15-148`, `flow/dynamic.py:9-18`
**Pattern**: `EventEngineCls` with `listen_group()` decorator to declare dependencies between events, `invoke_event()` to execute the DAG with BFS + async parallel fan-out. Events are functions whose `parent_groups` define what must complete before they fire. `retrigger_type="all"` means ALL parents must complete. `already_sent_to_event_group` dedup prevents duplicate dispatch. `ReturnBehavior` enum enables GOTO (jump to another event), ABORT (terminate branch), DISPATCH (normal flow).

Exact mechanism:
```python
# flow/core.py:41-78 -- dependency declaration
def listen_group(self, group_markers, group_name=None, retrigger_type="all"):
    def decorator(func):
        group_markers_in_dict = {event.id: event for event in group_markers}
        new_group = EventGroup(group_name, group_hash, group_markers_in_dict, retrigger_type)
        func.parent_groups[new_group.hash()] = new_group
        return func
    return decorator

# flow/core.py:93-151 -- parallel dispatch within invoke_event
async def run_event(current_event_id, current_event_input):
    result = await current_event.solo_run(current_event_input, global_ctx)
    # Dedup: skip if already dispatched to this event+group
    if event_group_id in this_run_ctx[event_id]["already_sent_to_event_group"] and group.retrigger_type == "all":
        continue
    # Record dispatch to prevent re-trigger
    this_run_ctx[event_id]["already_sent_to_event_group"].add(event_group_id)
    # Queue dependent events
    queue.append((cand_event.id, build_input))

# flow/core.py:153-175 -- BFS parallel execution
while len(queue) or len(tasks):
    this_batch_events = queue[:max_async_events] if max_async_events else queue
    new_tasks = {asyncio.create_task(run_event(*args)) for args in this_batch_events}
    done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

# flow/dynamic.py:9-18 -- control flow
def goto_events(group_markers, any_return=None):
    return _SpecialEventReturn(behavior=ReturnBehavior.GOTO, returns=(group_markers, any_return))

def abort_this():
    return _SpecialEventReturn(behavior=ReturnBehavior.ABORT, returns=None)
```

**code-shiniyaya gap**: CC's 7-step pipeline is strictly linear. STEP 1 must complete before STEP 2, etc. STEP 1.5 is conditionally triggered but still linear. Within a step, agents run in parallel but with no dependency graph -- all agents in a batch are independent. There is no mechanism for "run Agent X only after Agents A, B, and C all complete."

**Fix -- Add to SKILL.md** (add to "迭代扫描工作流" section or as new section):

```markdown
## STEP DAG 依赖图 (v3.8.0)

部分步骤可并行执行。以下DAG声明步骤间的依赖关系:

```
STEP 1 (诊断) ──┬──> STEP 2 (方案)
                │
                └──> STEP 1.5 (参考源扫描, 与STEP 2并行)
                          │
                          └──> STEP 2 合并(等待1.5结果后最终确定方案)
```

### 步内Agent依赖声明

批量Agent启动时, CC可以声明依赖:

```
AGENT_DEPENDS: agent_a, agent_b | agent_c
```

含义: agent_c在agent_a和agent_b都完成后才启动(类似listen_group retrigger_type="all")。

### 去重协议(步内)

同一`already_sent`集合避免重复分发: 若Agent A和Agent B都对同一`file:line`报告问题, Agent C(验证)只接收一次合并后的输入, 而非两次独立通知。

### 步间GOTO

若STEP 4(Codex验证)发现需要重新诊断的根本问题:
```
GOTO: STEP_1 | reason: "Codex found uncaught crash path in src/core.py:200-250, need re-diagnosis of this range"
```
此GOTO重置workflow_context中受影响的diagnosis条目, 重新排队STEP 1(只扫描指定范围), 然后从STEP 2继续。
```

---

## P1: Significant Correctness/Robustness Gaps (5 patterns)

### P1-1: 3-Tier Retry with Meta-Agent Upgrade
**Source**: `autoagent/main.py:43-80`
**Pattern**: MAX_RETRY=3 with escalation. Attempts 0-1: same agent. Attempt 2: if `meta_agent` is available, switch to it with expanded toolset (`setup_metachain()` + append `case_resolved`/`case_not_resolved`). The meta-agent gets a specialized prompt: "It seems that the case is not resolved with the existing agent system. Help me to solve this problem by running tools in the MetaChain... You should fully take advantage of existing tools, and if existing tools are not enough, you should develop new tools."

```
Tier 1 (attempt 0-1): original agent --> if case_not_resolved: retry same agent
Tier 2 (attempt 2): meta_agent with full toolset --> if still not resolved: append "try again differently" message
Tier 3 (attempt 3): final retry with "try again in another way may be helpful" prompt
```

**code-shiniyaya gap**: Rule 7 limits to 2 replacements per slot, then permanent failure. There's no "upgrade" tier -- just retry the same agent type. No meta-agent with broader permissions.

**Fix -- Add to SKILL.md** (modify Rule 7):

```markdown
### 规则7增强: 3层重试升级 (v3.8.0)

| 尝试 | Agent类型 | 权限 | 提示词注入 |
|------|----------|------|-----------|
| 1 | 原始类型(如investigator) | 标准 | 无 |
| 2 | 原始类型 | 标准 | 注入上次失败原因作为反馈 |
| 3 | general-purpose(升级) | 全部文件读取 + 全部Skill | "原Agent 2次尝试失败。失败原因: {reason}。请使用不同方法解决。你可以访问所有文件和使用所有工具。" |

第3次升级后仍失败 --> 标记PERMANENTLY_FAILED, 写入ERRORS.md, 不重试。
若原始类型已是general-purpose: 升级到Plan Agent(架构视角)。
```

---

### P1-2: agent_teams Dispatch Dictionary
**Source**: `autoagent/types.py:19`, `system_triage_agent.py:55-59`
**Pattern**: Each `Agent` carries an `agent_teams: Dict[str, Callable]` mapping sub-agent names to their transfer functions. The triage agent populates this at construction time. This creates a discoverable dispatch table.

```python
# types.py:19
agent_teams: Dict[str, Callable] = {}

# system_triage_agent.py:55-59
system_triage_agent.agent_teams = {
    filesurfer_agent.name: transfer_to_filesurfer_agent,
    websurfer_agent.name: transfer_to_websurfer_agent,
    coding_agent.name: transfer_to_coding_agent
}
```

**code-shiniyaya gap**: CC's 5 agent types have implicit relationships (回退链: investigator --> Explore --> general-purpose) but no explicit dispatch table. If an investigator agent discovers a runtime-only bug, CC has to manually decide to spawn a debugging agent. There's no automated "I found this --> delegate to that" routing.

**Fix -- Add to SKILL.md** (add to "Agent编排" table):

```markdown
### TEAM_DISPATCH 表 (v3.8.0)

| 发现类型 | 源Agent类型 | 目标Agent类型 | 触发条件 |
|---------|------------|-------------|---------|
| 跨文件引用链 | investigator | Explore | 引用跨越3+文件 |
| 逻辑不一致 | investigator | general-purpose | 字节级正确但语义可疑 |
| 架构异味 | general-purpose | Plan | 影响3+模块的设计问题 |
| 竞态/死锁 | general-purpose | debugging | 并发代码路径 |
| 内存泄漏 | debugging | investigator | 需要跟踪分配调用点 |
| AST验证失败 | Plan | cavecrew-reviewer | 执行后验证阶段 |

CC在Agent输出中检测到 `HANDOFF: <target_type>` 时自动路由(见P0-2)。
```

---

### P1-3: Tool-Result Truncation with File-Based Overflow
**Source**: `autoagent/registry.py:19-24`, `autoagent/tools/tool_utils.py:6-24`
**Pattern**: `truncate_output()` caps tool results at `MAX_OUTPUT_LENGTH` tokens (12000). Exceeded results get truncated with a warning suggesting the agent use file output instead. `truncate_by_tokens()` goes further: saves full output to a file (`workplace/console_output/truncated_output_{timestamp}.txt`) and returns truncated head+tail plus the file path reference.

```python
# registry.py:19-24
def truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    tokens = encode_string_by_tiktoken(output)
    if len(tokens) > max_length:
        return decode_tokens_by_tiktoken(tokens[:max_length]) + \
            f"\n\n[TOOL WARNING] Output truncated, exceeded {max_length} tokens)\n" + \
            f"[TOOL SUGGESTION] Maybe this tool with direct output is not an optimal choice, " + \
            f"consider save the output to a file in the `workplace/` directory to implement the same functionality."
    return output

# tool_utils.py:15-23 -- save-to-file overflow
output_path = f"{env.docker_workplace}/console_output/truncated_output_{timestamp}.txt"
create_msg = create_file(output_path, content=text, context_variables={'code_env': env})
truncated_tokens_bos = tokens[:max_tokens//2]
truncated_tokens_eos = tokens[-(max_tokens - len(truncated_tokens_bos)):]
return encoding.decode(truncated_tokens_bos) + "\n...\n" + encoding.decode(truncated_tokens_eos) + \
    f"\n\nThe full console output is too long, so it is saved in the file: {output_path}"
```

**code-shiniyaya gap**: No output truncation. When diagnostic agents produce large results (e.g., full file dumps, crash stack traces with 100+ frames), the entire output enters CC's context. This causes context overflow in STEP 3 (Codex message generation) and STEP 4 (10+ agent cross-verification).

**Fix -- Add to SKILL.md** (add to "反模式" or new section):

```markdown
### TRUNCATION_PROTOCOL (v3.8.0)

Agent输出 > 4000 tokens时:
1. 保留头部2000 tokens + 尾部2000 tokens。
2. 完整输出写入 `reports/agent-output/{agent_type}_{timestamp}.md`。
3. 截断文本末尾追加:
   ```
   [... truncated N tokens ...]
   Full output: reports/agent-output/{agent_type}_{timestamp}.md
   ```
4. CC在后续步骤中引用此文件路径, 而非携带完整输出。
5. STEP 3 Codex消息中: 若FOR_CODEX文件 > 10000 tokens, 用相同截断逻辑, 完整版保存为 `FOR_CODEX_{描述}_full.md`。

### Token计数
使用 `tiktoken` (gpt-4o encoding) 精确计算, 而非字数估算。
```

---

### P1-4: sender Tag in Messages for Audit Trail
**Source**: `autoagent/core.py:323`, `core.py:437`, `core.py:621`
**Pattern**: Every assistant message carries `"sender": active_agent.name`. When agents hand off, the new agent's name becomes the sender. This creates an automatic audit trail showing which agent said what, even across handoffs.

```python
# core.py:323 -- stream mode
message = {"content": "", "sender": agent.name, "role": "assistant", ...}

# core.py:437 -- sync mode
message: Message = completion.choices[0].message
message.sender = active_agent.name

# core.py:621 -- async mode
message.sender = active_agent.name
```

**code-shiniyaya gap**: Multi-agent batches produce results but without sender attribution metadata. The dedup merge (STEP 1.4) collapses by file:line, losing which agent found what. When 2 agents disagree about the same line, there's no way to trace back to which agent said what.

**Fix -- Add to SKILL.md** (modify STEP 1 agent output format):

```markdown
### Agent输出标头 (v3.8.0)

每个Agent输出的第一行必须包含:
```
AGENT: {agent_id}:{type}:{timestamp_iso}
```

agent_id = 批内UUID前8字符。

STEP 1去重合并时保留agent source信息:
```json
{
  "file:line": "src/core.py:42",
  "severity": "P0",
  "root_cause": "null dereference from uninitialized field",
  "sources": [
    {"agent_id": "a1b2c3d4", "type": "investigator", "confidence": "high"},
    {"agent_id": "e5f6g7h8", "type": "general-purpose", "confidence": "medium"}
  ]
}
```

当2个Agent给出冲突诊断时: 保留双方观点, 标注CONFLICT, 在STEP 4 Codex验证中提请裁决。
```

---

### P1-5: Singleton Logger Manager for Unified Logging
**Source**: `autoagent/logger.py:138-172`
**Pattern**: `LoggerManager` singleton with class-level `_instance` and `_logger`. `set_logger()` globally replaces the logger. All components (MetaChain, tools, REPL) share one logger. Logs go to both file and console with Rich formatting, timestamps, and color coding. Default log auto-creates timestamped directory: `logs/res_{YYYYMMDD}_{HHMMSS}/agent.log`.

```python
class LoggerManager:
    _instance = None
    _logger: MetaChainLogger = None

    @classmethod
    def get_logger(cls):
        return cls.get_instance()._logger

    @classmethod
    def set_logger(cls, new_logger):
        cls.get_instance()._logger = new_logger

# Auto-initialize
if DEFAULT_LOG:
    log_dir = Path(f'logs/res_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / "agent.log")
    LoggerManager.set_logger(MetaChainLogger(log_path=log_path))
```

**code-shiniyaya gap**: No unified logging. Session JSON tracks state, error messages go to STDERR, agent outputs go to reports. No single log that captures "at 14:32:15, investigator agent a1b2c3d4 started scanning src/core.py" and "at 14:32:47, agent returned TERMINAL: RESOLVED." Debugging a failed workflow requires piecing together 3+ sources.

**Fix -- Add to SKILL.md** (add to "状态文件" section):

```markdown
### WORKFLOW_LOG (v3.8.0)

工作流启动时自动创建日志文件:
`{project_root}/.claude/memory/code-shiniyaya/workflow-{sessionId[:8]}-{YYYYMMDD_HHMMSS}.jsonl`

每行一个JSON事件:
```jsonl
{"ts":"2026-07-16T14:32:15.123","event":"agent_start","agent_id":"a1b2c3d4","type":"investigator","file":"src/core.py"}
{"ts":"2026-07-16T14:32:47.456","event":"agent_end","agent_id":"a1b2c3d4","terminal":"RESOLVED","tokens_used":3421}
{"ts":"2026-07-16T14:33:01.789","event":"step_transition","from":1,"to":2,"context_snapshot_hash":"sha256:abc123"}
{"ts":"2026-07-16T14:35:20.012","event":"codex_timeout","silent_msg_count":4,"degraded":true}
```

### 事件类型
- agent_start / agent_end / agent_error
- step_transition (from step N to step M)
- codex_sent / codex_received / codex_timeout
- approval (user / codex / dual)
- context_update (workflow_context修改)
- state_save (会话JSON写入)
- error (任何错误, 含完整traceback)

### 日志保留
- 正常完成: 保留7天, 然后自动清理。
- 中断/失败: 永久保留(用于事后分析)。
- ENV WORKFLOW_LOG_DIR 覆盖日志目录(默认: .claude/memory/code-shiniyaya/)。
```

---

## P2: Nice-to-Have Improvements (6 patterns)

### P2-1: interleave_user_into_messages Anti-Loop Protection
**Source**: `autoagent/fn_call_converter.py:837-848`
**Pattern**: When two consecutive messages are both `role=assistant`, some LLMs get stuck in a reinforcement loop. Solution: insert an empty `role=user` message with "Please think twice and take the next action according to your previous actions and observations."

```python
def interleave_user_into_messages(messages):
    new_messages = []
    for idx, message in enumerate(messages):
        if message["role"] == "assistant" and messages[idx-1]["role"] == "assistant":
            new_messages.append({
                "role": "user",
                "content": "Please think twice and take the next action according to your previous actions and observations."
            })
        new_messages.append(message.copy())
    new_messages.append({"role": "user", "content": "Please think twice..."})
    return new_messages
```

**code-shiniyaya gap**: No loop protection at the agent prompt level.

**Fix**: Add to anti-hang-v2.md:
```markdown
### Pattern: Reflection Injection on Retry
If same agent type retries the same file:line twice: inject a reflection prompt before the 3rd attempt:
"Previous 2 attempts at fixing src/core.py:42 failed. Before trying again, analyze what went wrong in the previous attempts. Then propose a DIFFERENT approach."
```

---

### P2-2: FunctionInfo Registry with Multiple Categories
**Source**: `autoagent/registry.py:26-224`
**Pattern**: Singleton `Registry` with 5 categories (tools, agents, plugin_tools, plugin_agents, workflows). Each entry has `FunctionInfo` dataclass capturing source code, args, docstring, return type, file path. Enables introspection and programmatic agent discovery.

**code-shiniyaya gap**: No registry of available agents. The 5 agent types are listed as prose.

**Fix**: Add to SKILL.md:
```markdown
### AGENT_REGISTRY (v3.8.0)

| type | capability | max_retries | fallback_to | parallel_safe |
|------|-----------|-------------|-------------|---------------|
| investigator | byte/encoding analysis | 3 | Explore | yes |
| Explore | cross-file reference scanning | 2 | general-purpose | yes |
| general-purpose | logic/diagnosis (universal fallback) | 3 | Plan | yes |
| Plan | architecture/design review | 2 | general-purpose | yes |
| debugging | runtime/stack trace analysis | 3 | general-purpose | yes |
| cavecrew-builder | code modification | 2 | general-purpose | no (serial) |
| cavecrew-reviewer | diff/code review | 2 | Plan | yes |
```

---

### P2-3: adapt_tools_for_gemini Model-Specific Tool Adaptation
**Source**: `autoagent/core.py:58-94`
**Pattern**: `adapt_tools_for_gemini()` checks if the model name contains "gemini" and adapts tool parameter schemas: Gemini requires non-empty `properties` for OBJECT types, so a `dummy` property is injected.

```python
def adapt_tools_for_gemini(tools):
    for tool in tools:
        if "parameters" in adapted_tool["function"]:
            params = adapted_tool["function"]["parameters"]
            if params.get("type") == "object":
                if "properties" not in params or not params["properties"]:
                    params["properties"] = {"dummy": {"type": "string", ...}}
    return adapted_tools
```

**code-shiniyaya gap**: CC assumes all agents use the same model interface.

**Fix**: Add to SKILL.md:
```markdown
### MODEL_ADAPT (v3.8.0)

若Agent后端模型需特殊工具格式: CC在启动Agent前检查模型名称并应用适配:
- "gemini" --> 空OBJECT属性 --> 注入dummy属性(见autoagent/core.py:58-94)
- 其他模型 --> 标准OpenAI function calling格式
```

---

### P2-4: Token Counting with tiktoken for Precision
**Source**: `autoagent/registry.py:6-24`
**Pattern**: Uses `tiktoken.encoding_for_model("gpt-4o")` to get precise token counts, not character estimates. `encode_string_by_tiktoken()` returns token list; `decode_tokens_by_tiktoken()` reconstructs string from token range.

**code-shiniyaya gap**: STEP 3's ">10000 tokens" check is a fuzzy estimate.

**Fix**: Add to SKILL.md item (STEP 3):
```markdown
Token计数方法: `python -c "import tiktoken; enc=tiktoken.encoding_for_model('gpt-4o'); print(len(enc.encode(open('FOR_CODEX_file.md').read())))"` . 字符估算仅在tiktoken不可用时作为回退(1 token ~= 4 chars English, ~= 1.5 chars Chinese).
```

---

### P2-5: Environment Variable-Driven Feature Detection
**Source**: `autoagent/constant.py:67-85`
**Pattern**: At module load, the constant module auto-detects model capabilities by checking model name against known lists (`NOT_USE_FN_CALL`, `MUST_ADD_USER`, etc.) and sets boolean flags (`FN_CALL`, `ADD_USER`, `NON_FN_CALL`).

```python
if FN_CALL is None:
    FN_CALL = True
    for model in NOT_USE_FN_CALL:
        if model in COMPLETION_MODEL:
            FN_CALL = False
            break
```

**code-shiniyaya gap**: No startup capability detection. Hardcoded values.

**Fix**: Add to SKILL.md:
```markdown
### CAPABILITY_DETECT (v3.8.0)

工作流启动时(STEP 0):
```
python -c "
import os, shutil, subprocess, json
caps = {
    'git_available': shutil.which('git') is not None,
    'python_version': subprocess.check_output(['python','--version']).decode().strip(),
    'cpu_cores': os.cpu_count() or 4,
    'disk_free_gb': round(shutil.disk_usage('.').free / (1024**3), 1),
    'tiktoken_available': __import__('importlib').util.find_spec('tiktoken') is not None
}
print(json.dumps(caps))
"
```
若tiktoken不可用: token计数回退到字符估算。磁盘<1GB: 减少报告写入, 内联优先。
```

---

### P2-6: get_chat_completion_async with Tenacity Retry
**Source**: `autoagent/core.py:494-499`
**Pattern**: Async completion wrapper with `@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=10, max=180), retry=should_retry_error)` -- exponential backoff from 10s to 180s, up to 4 attempts, catching APIError/RemoteProtocolError/ConnectError.

**code-shiniyaya gap**: Agent failures in CC are handled at the orchestration level (Rule 7) rather than at the API level.

**Fix**: Add to anti-hang-v2.md:
```markdown
### Pattern: Exponential Backoff on Agent API Errors
Agent API调用失败时: 第1次重试=立即, 第2次=10s后, 第3次=30s后, 第4次=180s后。匹配错误类型: APIError, ConnectionError, Timeout。非匹配错误(如权限错误): 立即失败, 不重试。4次全失败 --> Rule 7替换逻辑。
```

---

## 汇总: 按优先级排列

| # | 优先级 | 模式 | 源文件:行 | 改进目标 |
|---|--------|------|----------|---------|
| 1 | P0 | context_variables shared state bus | core.py:55,124-128,264-265,298-300,489-493 | SKILL.md: "工作流上下文总线" |
| 2 | P0 | Result + agent handoff | types.py:28-42, core.py:212-228,299-300,385-387 | SKILL.md: "HandoffResult协议" |
| 3 | P0 | case_resolved/case_not_resolved terminal | inner.py:3-24, main.py:50-52 | SKILL.md: "Agent终端信号" |
| 4 | P0 | Event-driven DAG engine | flow/core.py:41-175, flow/types.py:15-148 | SKILL.md: "STEP DAG依赖图" |
| 5 | P1 | 3-Tier retry with meta-agent | main.py:43-80 | SKILL.md: "规则7增强" |
| 6 | P1 | agent_teams dispatch dict | types.py:19, system_triage_agent.py:55-59 | SKILL.md: "TEAM_DISPATCH表" |
| 7 | P1 | Tool-result truncation + file overflow | registry.py:19-24, tool_utils.py:6-24 | SKILL.md: "TRUNCATION_PROTOCOL" |
| 8 | P1 | sender tag in messages | core.py:323,437,621 | SKILL.md: "Agent输出标头" |
| 9 | P1 | Singleton logger manager | logger.py:138-172 | SKILL.md: "WORKFLOW_LOG" |
| 10 | P2 | interleave_user anti-loop | fn_call_converter.py:837-848 | anti-hang-v2.md |
| 11 | P2 | FunctionInfo registry | registry.py:26-224 | SKILL.md: "AGENT_REGISTRY" |
| 12 | P2 | adapt_tools_for_gemini | core.py:58-94 | SKILL.md: "MODEL_ADAPT" |
| 13 | P2 | tiktoken token counting | registry.py:6-24 | SKILL.md: STEP 3 |
| 14 | P2 | Env var feature detection | constant.py:67-85 | SKILL.md: "CAPABILITY_DETECT" |
| 15 | P2 | Async retry with tenacity | core.py:494-499 | anti-hang-v2.md |

## 与现有high-impact-patterns.md的关系

现有Top-10中的 #6("事件驱动DAG引擎") 在此次扫描中得到深化: 不仅是概念, 现在有完整的 `listen_group` + `already_sent_to_event_group` dedup + `ReturnBehavior.GOTO/ABORT` 的具体机制。

现有Top-10中的 #1("Agent编排=Hub-and-Spoke") 在此次扫描中得到 `agent_teams` dispatch dict + `Result.agent` handoff的具体实现作为补充。

此扫描发现的15个模式中, 有11个是现有high-impact-patterns.md中没有覆盖的全新模式。
