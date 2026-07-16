# AutoAgent Security/Anti-Hang Patterns for code-shiniyaya
# Cross-source analysis: AutoAgent → code-shiniyaya SKILL.md + anti-hang-v2.md
# Date: 2026-07-16 | Source: autoagent-src deep scan | DIMENSION: Container isolation + task cancellation + max_turns guard

## PATTERN 1 (P0): max_turns Hard Loop Guard

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\core.py:319, 425, 609`
```python
# core.py:319 (run_and_stream)
while len(history) - init_len < max_turns:
    ...

# core.py:425 (run)
while len(history) - init_len < max_turns and active_agent:
    ...

# core.py:609 (run_async)
while len(history) - init_len < max_turns and active_agent:
    ...
```
Default is `float("inf")`, but callers can set a finite limit. The guard is checked on EVERY loop iteration — absolute, not dependent on timeouts.

### Gap in code-shiniyaya
code-shiniyaya SKILL.md has NO max_turns guard anywhere. The STEP 6 execution loop, agent orchestration loops, and iterative scanning all have no turn-bounded termination. An agent stuck in a tool-call loop (e.g., LLM hallucinating `read_file` → `write_file` → `read_file` cyclically) would run indefinitely until wall-clock timeout or user intervention.

### Concrete Fix
Add a new hard rule to SKILL.md after existing Rule 12:

```markdown
### max_turns Guard (v3.8.0)
12b. **max_turns硬上限**: 每个Agent执行循环内, 最大turn数 = 40 (LLM调用次数)。超限 → 强制终止该Agent slot, 标记为 `max_turns_exceeded`, 记录最后5条消息到ERRORS.md。
   - STEP 6逐项执行: 每项修复最多20 turns。超限 → BLOCKED, 原因=`max_turns_exceeded`, 不消耗3次失败计数。
   - STEP 1/1.5/4诊断Agent: 每Agent最多40 turns。超限 → 该维度标FAIL, 不替换Agent(区别于规则7的超时替换)。
   - 迭代扫描工作流: 每Agent最多30 turns。超限 → 同slot最多重试1次(用更低turn limit=20), 仍超限→永久跳过。
   - turn定义: 一次 LLM API 调用+工具执行 = 1 turn。不计入用户消息轮次。
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → after line 84 (Rule 12), as `Rule 12b` or as a new section in "硬规则".
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory/high-impact-patterns.md` → add as pattern entry.

---

## PATTERN 2 (P0): asyncio.CancelledError Cleanup Chain

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:170-174`
```python
try:
    while len(queue) or len(tasks):
        ...  # main dispatch loop
except asyncio.CancelledError:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    raise
```
When the event engine is cancelled, it propagates cancellation to ALL pending tasks, waits for them to finish (suppressing their CancelledError), then re-raises. This prevents orphaned tasks and partial state.

### Gap in code-shiniyaya
code-shiniyaya's `TaskStop` workflow (anti-hang-v2.md:43) just calls `TaskStop(background_task_id)` with no cleanup chain — orphaned agent tasks are left dangling. The resume protocol in iteration scanning recovery (SKILL.md:426-428) handles partial results post-hoc but does NOT prevent orphans during cancellation.

### Concrete Fix
Add cleanup protocol to the iteration scanning workflow section and the error handling table:

```markdown
### CancelledError Cleanup Chain (v3.8.0)

**工作流取消时**(用户说"终止"或TaskStop触发):
1. CC调用 TaskStop(background_task_id)
2. TaskStop返回后, CC立即检查journal.jsonl → 解析所有已完成Agent的 `type:"result"` 行
3. 对每个 `type:"started"` 但无对应 `type:"result"` 的Agent → 标记为 `orphaned_on_cancel`
4. 仅重跑 `orphaned_on_cancel` 和 `timed_out` 维度(而非所有未覆盖维度)
5. 已完成维度(PASS/PARTIAL/FAIL)直接保留, 不重跑

错误表新增行:
| 迭代扫描(workflow) | 用户终止/TaskStop | "工作流已终止——{N}个Agent已完成, {M}个被取消" | 解析journal.jsonl→仅重跑orphaned维度 |
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → in the iteration scanning workflow section (after line 428).
`C:\Users\shiniyaya\Desktop\code-shiniyaya\references\anti-hang-v2.md` → update Partial Recovery section.

---

## PATTERN 3 (P0): 3-Tier Retry Escalation with Meta-Agent Failover

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\main.py:43-80`
```python
MAX_RETRY = 3
for i in range(MAX_RETRY):
    response = await client.run_async(agent, messages, context_variables, debug=True)
    if 'Case resolved' in response.messages[-1]['content']:
        break
    elif 'Case not resolved' in response.messages[-1]['content']:
        messages.extend(response.messages)
        if meta_agent and (i >= 2):  # Tier 3: escalate to meta-agent
            setup_metachain(...)
            messages.append({'role': 'user', 'content': """\
It seems that the case is not resolved with the existing agent system.
Help me to solve this problem by running tools in the MetaChain.
IMPORTANT: You should fully take advantage of existing tools, and if existing
tools are not enough, you should develop new tools.
IMPORTANT: You can not stop with `case_not_resolved` after you try your best.
IMPORTANT: You should ONLY interact with the environment provided AND NEVER ASK FOR HUMAN HELP."""})
            meta_agent.functions.append(case_not_resolved)
            meta_agent.functions.append(case_resolved)
            response = await client.run_async(meta_agent, messages, ...)
            if 'Case resolved' in response.messages[-1]['content']:
                break
        # Tier 1-2: retry with same agent + feedback
        messages.append({'role': 'user', 'content': 'Please try to resolve the case again...'})
```
Three tiers:
- **Tier 1-2** (i=0,1): Same agent retried with "try differently" prompt. Fast retry.
- **Tier 3** (i=2): Escalate to meta_agent with full tool creation authority. Meta-agent gets `case_resolved`/`case_not_resolved` tools. Cannot self-terminate without either resolving or documenting failure.
- **All tiers fail**: `case_not_resolved(failure_reason, take_away_message)` captures structured failure for post-mortem.

### Gap in code-shiniyaya
code-shiniyaya Rule 7: "Agent异常终止或挂起→替换, 每槽位最多2次→第3次永久失败". This is FLAT replacement — same agent type, no escalation to higher-authority agent, no structured failure documentation. When an agent slot fails 3 times at the same task, the dimension is just permanently failed with no root-cause analysis.

### Concrete Fix
Replace Rule 7 with 3-tier escalation:

```markdown
7. **3-Tier Agent升级链**(替换原规则7):
   - **Tier 1** (1st attempt): 首选Agent类型(按Agent选择矩阵)。失败→记录错误消息。
   - **Tier 2** (2nd attempt): 同类型Agent + 注入上次错误作为feedback("上次尝试失败: {error}. 换一种方法重试.")。
   - **Tier 3** (3rd attempt): 升级到general-purpose Agent(通用回退) + 注入完整失败链 + "你可以创建新的分析工具。不得在未解决问题的情况下自行终止."
   - **全部失败**: 该维度标 `escalation_exhausted`, 写入 `ESCALATION_LOG.md`(含: 维度名, 3次尝试的错误链, 最后状态, 建议人工介入方向)。
   - Agent返回结构化终止信号(见Pattern 6)时消费1次尝试; Agent挂起/超时时由CC的落后检测消费1次尝试。
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → replace lines 74-75 (Rule 7).
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory/high-impact-patterns.md` → update pattern #8 (3-Tier retry) with concrete code.

---

## PATTERN 4 (P1): Graceful Shutdown Signal with Cooperative Abort

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\environment\shutdown_listener.py:1-66`
```python
_should_exit = None

def _register_signal_handler(sig):
    original_handler = None
    def handler(sig_, frame):
        global _should_exit
        _should_exit = True
        if original_handler:
            original_handler(sig_, frame)
    original_handler = signal.signal(sig, handler)

def should_exit() -> bool:
    _register_signal_handlers()
    return bool(_should_exit)

def should_continue() -> bool:
    return not _should_exit

def sleep_if_should_continue(timeout: float):
    if timeout <= 1:
        time.sleep(timeout)
        return
    start_time = time.time()
    while (time.time() - start_time) < timeout and should_continue():
        time.sleep(1)
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\environment\tenacity_stop.py:1-11`
```python
class stop_if_should_exit(stop_base):
    """Stop if the should_exit flag is set."""
    def __call__(self, retry_state):
        return should_exit()
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\environment\browser_env.py:383-387`
```python
@tenacity.retry(
    wait=tenacity.wait_fixed(1),
    stop=tenacity.stop_after_attempt(5) | stop_if_should_exit(),
    retry=tenacity.retry_if_exception_type(BrowserInitException),
)
def init_browser(self):
```
The shutdown listener provides: (a) a global `_should_exit` flag set by signal handlers, (b) `sleep_if_should_continue()` that wakes up every 1s to check the flag, (c) `stop_if_should_exit()` that integrates with tenacity retry so retry loops abort early on shutdown.

### Gap in code-shiniyaya
code-shiniyaya anti-hang-v2.md explicitly documents that CC "has no event loop, no wall clock, cannot poll." But the cooperative shutdown pattern can still apply: (a) code-shiniyaya's workflow steps could check a STOP flag between items, (b) the stop-line (Rule 13) is binary — stop NOW — with no "stop soon, after finishing current item" option.

### Concrete Fix
Add cooperative stop to SKILL.md stop rule area:

```markdown
### Cooperative Stop (v3.8.0)

12c. **合作式停止**: 除立即停止(stop/中断/CTRL+C)外, 增加"软停止"——完成当前处理项后停止, 不开始下一项。
   - 用户说"stop after this" / "这项做完停" → 设置 `session JSON: cooperativeStop = true`
   - 每项执行前检查 `cooperativeStop` flag
   - True → 完成当前项→保存JSON状态→"已完成{current_item}, 剩余{remaining}项待处理." → 停止
   - 区别于规则13的立即停止: 规则13保护数据安全(已完成项保留), 合作式停止避免破坏执行连贯性(当前项执行到一半不中断)

12d. **重试打断**: 在执行3-Tier升级链(规则7)期间, 用户说"skip" → 该slot直接标 `escalation_exhausted_by_user` + 跳过 → 不等待全部3次重试完成。
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → after Rule 12 (line 84), alongside Pattern 1's max_turns guard.
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory/high-impact-patterns.md` → add as new entry.

---

## PATTERN 5 (P1): ABORT / RETURN Behavior in Workflow Steps

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\dynamic.py:16-18`
```python
def abort_this():
    return _SpecialEventReturn(behavior=ReturnBehavior.ABORT, returns=None)
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:112-113`
```python
if result.behavior == ReturnBehavior.ABORT:
    return  # stop processing this branch immediately
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\types.py:15-18`
```python
class ReturnBehavior(Enum):
    DISPATCH = "dispatch"  # normal: continue dispatching to listeners
    GOTO = "goto"          # jump to another event node
    ABORT = "abort"        # stop this branch immediately
    INPUT = "input"         # user input entry point
```

### Gap in code-shiniyaya
code-shiniyaya SKILL.md has "stop" handling (Rule 13) but it's user-triggered only. There is no programmatic ABORT: an Agent cannot signal "this branch of investigation is a dead end, stop and don't dispatch my results." The iteration scanning workflow (SKILL.md line 413) has "stall detection" but no agent-initiated abort.

### Concrete Fix
Add ABORT as a valid agent output type:

```markdown
### Agent输出约定 (v3.8.0)

诊断/扫描Agent必须返回以下三种终止信号之一:
- **PASS**: 该维度无问题发现。输出: `{"verdict":"PASS", "summary":"..."}`
- **FAIL**: 该维度有问题发现。输出: `{"verdict":"FAIL", "issues":[...], "severity":"P0|P1|P2"}`
- **ABORT**: 该维度分析路径为死胡同(如: 假设错误, 源文件不适用, 工具链路断裂)。输出: `{"verdict":"ABORT", "reason":"...", "dead_end_at":"..."}` 
  - ABORT不计为失败(不消耗重试配额)。CC不重试该Agent slot(不同于超时)。
  - 该维度结果不参与去重合并——ABORT维度被排除在最终issue列表之外。

**STEP 6执行终止信号**:
- `{"action":"STOP_SUCCESS"}` — 修复成功, 继续下一项
- `{"action":"STOP_FAILED", "reason":"..."}` — 修复失败, 进入FAILED_FIXES.md
- `{"action":"STOP_BLOCKED", "blocked_by":"<bug-id>"}` — 被依赖项阻断, 进入BLOCKED状态
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → in "Agent编排" section (after line 316) or in a new "Agent输出约定" section.

---

## PATTERN 6 (P1): Structured Termination Signals (case_resolved / case_not_resolved)

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\tools\inner.py:1-26`
```python
@register_tool("case_resolved")
def case_resolved(result: str):
    """Use this function when the case is resolved. Encapsulate final answer within <solution> and </solution>."""
    return f"Case resolved. No further actions are needed. The result is: {result}"

@register_tool("case_not_resolved")
def case_not_resolved(failure_reason: str):
    """Use this function when the case is not resolved when all agents have tried their best.
    [IMPORTANT] Please do not use this function unless all of you have tried your best."""
    return f"Case not resolved. The reason is: {failure_reason}"
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\main.py:18-28`
```python
def case_not_resolved(failure_reason: str, take_away_message: str):
    """Use this tool to indicate that the case is not resolved when all agents have tried their best.
    [IMPORTANT] Please do not use this function unless all of you have tried your best.
    You should give the failure reason and the take away message to tell which information you gain."""
    return f"Case not resolved. The reason is: {failure_reason}. But though creating new tools, I gain some information: {take_away_message}"
```

### Gap in code-shiniyaya
code-shiniyaya has no structured termination protocol. Agents return whatever the LLM outputs. The error table has generic entries like "Agent全超时" / "个别超时" but no structured success/failure signaling from the agent itself.

### Concrete Fix
This is already partially covered by Pattern 5 (ABORT). Add to the same section:

```markdown
### 结构化终止信号约定
- `case_resolved(result)` — 等价于 PASS + 结果。Result中 `<solution>...</solution>` 标签包裹最终答案。
- `case_not_resolved(failure_reason, take_away_message)` — 等价于 FAIL + 根因。`failure_reason` 记录为什么失败, `take_away_message` 记录从失败中学到的信息(如: 哪些工具不可用, 哪些假设错误)。
- CC解析: 查找 `Case resolved` / `Case not resolved` 字符串前缀。不依赖工具调用名(因为CC不使用function calling)。
- 同Pattern 5的 `ABORT` 一起构成完整的三态终止模型。
```

### Where to Add
Same section as Pattern 5.

---

## PATTERN 7 (P2): Tool Output Truncation with Token Counting

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\registry.py:7-24`
```python
MAX_OUTPUT_LENGTH = 12000

def encode_string_by_tiktoken(content: str, model_name: str = "gpt-4o"):
    ENCODER = tiktoken.encoding_for_model(model_name)
    tokens = ENCODER.encode(content)
    return tokens

def truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    """Truncate output if it exceeds max_length"""
    tokens = encode_string_by_tiktoken(output)
    if len(tokens) > max_length:
        return decode_tokens_by_tiktoken(tokens[:max_length]) + \
            f"\n\n[TOOL WARNING] Output truncated, exceeded {max_length} tokens)\n" + \
            "[TOOL SUGGESTION] Maybe this tool with direct output is not an optimal choice, " + \
            "consider save the output to a file in the `workplace/` directory."
    return output
```
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\registry.py:88-97`:
```python
if type == "plugin_tool":
    @functools.wraps(original_func)
    def wrapped_func(*args, **kwargs):
        result = original_func(*args, **kwargs)
        if isinstance(result, str):
            return truncate_output(result)
        return result
```
All `plugin_tool`-registered tools automatically get output truncation. The warning also gives a suggestion (save to file instead).

### Gap in code-shiniyaya
code-shiniyaya has no output size guard. Large diagnostic outputs from agents (e.g., reading a 5000-line source file) could consume significant context. The only relevant guard is STEP 3's ">10000 tokens → 分N部分" which is about Codex messages, not agent tool output.

### Concrete Fix
Add output truncation guidance to agent instructions:

```markdown
### Agent输出大小限制 (v3.8.0)

诊断/扫描Agent的输出限制:
- 单Agent单次返回 ≤ 15000字符(约4000 tokens)。超限 → 截断 + 追加警告: "[OUTPUT TRUNCATED at {N} chars. Use file write for full output.]"
- Agent需要输出大量数据时(如: 完整文件内容, diff输出) → 先写入 `{workflow_dir}/agent-{id}-output.txt`, 返回中仅包含文件路径 + 前500字符摘要。
- CC读取agent输出时: 检查是否有 `[OUTPUT TRUNCATED]` 标记 → 有则读取完整文件, 不依赖截断版本。

实现方式(CC侧):
```
agent_output = agent_response.text
if len(agent_output) > 15000:
    truncated = agent_output[:15000] + f"\n[OUTPUT TRUNCATED at 15000 chars. Full output at: {workflow_dir}/agent-{agent_id}-full.txt]"
    Write(f"{workflow_dir}/agent-{agent_id}-full.txt", agent_output)
    return truncated
```
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → "Agent编排" section or "DO/DON'T" section.
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory/high-impact-patterns.md` → add as new entry.

---

## PATTERN 8 (P2): Event Dispatch Dedup with already_sent_to_event_group

### Source
`C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\autoagent\flow\core.py:99-151`
```python
this_run_ctx[current_event.id] = {
    "result": result,
    "already_sent_to_event_group": set(),
}
...
for cand_event in self.__event_maps.values():
    for group_hash, group in cand_event_parents.items():
        event_group_id = f"{cand_event.id}:{group_hash}"
        if if_current_event_trigger and if_ctx_cover:
            if (any([event_group_id in this_run_ctx[event_id]["already_sent_to_event_group"]
                     for event_id in group.events])
                and group.retrigger_type == "all"):
                # skip — already dispatched
                continue
            for event_id in group.events:
                this_run_ctx[event_id]["already_sent_to_event_group"].add(event_group_id)
            queue.append((cand_event.id, build_input))
```
Each event tracks which event-groups it has already been dispatched to. When `retrigger_type="all"` and the group was already sent for ANY of the group's events, the dispatch is skipped. This prevents infinite dispatch loops in fan-in patterns.

### Gap in code-shiniyaya
code-shiniyaya STEP 1 has dedup (group by `file:line±3`, merge within groups) but it operates on RESULTS, not on DISPATCH. If two agents should trigger the same downstream analysis (e.g., both find a bug in the same file), the dedup happens after both have run, wasting agent capacity. AutoAgent's pattern prevents the dispatch itself.

### Concrete Fix
Enhance STEP 1 dedup to include dispatch-level prevention:

```markdown
### Agent Dispatch Dedup (增强规则5)

STEP 1去重增强:
(a) **调度前去重**: 在派发Agent前, 检查是否有2+Agent被分配到相同的 `(file_path, function_name)` 组合。如有 → 合并为1个Agent slot, 提示词包含合并后的指令("检查 {file}.{func} 的以下方面: {aspect1}, {aspect2}")。
(b) **结果去重**(已有): group by `file:line±3`, 组内合并。
(c) **event_group_id 等效**: 每个Agent slot分配一个 `slot_key = sha256(file + ":" + dimension)`. 调度前检查 `slot_key` 是否已分配 → 已有则跳过, 不重复派发。

实现:
```python
# 伪代码: STEP 1 dispatch dedup
dispatched_slot_keys = set()
for bug_hypothesis in hypotheses:
    for dimension in dimensions:
        slot_key = hashlib.sha256(f"{bug_hypothesis.file}:{dimension}".encode()).hexdigest()
        if slot_key in dispatched_slot_keys:
            continue  # 已有Agent覆盖此(file, dim)组合
        dispatched_slot_keys.add(slot_key)
        dispatch_agent(bug_hypothesis, dimension)
```
```

### Where to Add
`C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` → STEP 1 section (lines 207-216), enhance the dedup bullet.
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory/high-impact-patterns.md` → add or enhance pattern #6.

---

## Summary: Integration Priority

| # | Pattern | Priority | Target File | Line After |
|---|---------|----------|-------------|------------|
| 1 | max_turns Loop Guard | P0 | SKILL.md | Line 84 |
| 2 | CancelledError Cleanup Chain | P0 | SKILL.md + anti-hang-v2.md | Line 428 + Section 4 |
| 3 | 3-Tier Retry Escalation | P0 | SKILL.md | Lines 74-75 (replace Rule 7) |
| 4 | Cooperative Stop | P1 | SKILL.md | Line 84 |
| 5 | ABORT Behavior | P1 | SKILL.md | After line 316 |
| 6 | Structured Termination Signals | P1 | SKILL.md | After line 316 |
| 7 | Tool Output Truncation | P2 | SKILL.md | After line 316 |
| 8 | Dispatch Dedup | P2 | SKILL.md | Lines 212-214 |

## Patterns NOT Transferred (with Reasons)

- **Docker Container Isolation** (`docker_env.py`): CC has no Docker access. Pattern absorbed as principle ("each agent gets isolated context") but cannot be implemented as container isolation.
- **Shutdown Signal Listener** (`shutdown_listener.py`): CC sandboxes OS signals. Pattern adapted to "Cooperative Stop" instead (Pattern 4).
- **atexit Resource Cleanup** (`browser_env.py:370`): CC sessions auto-cleanup. The multi-tier force kill pattern is documented in Pattern 2.
- **Tenacity Exponential Backoff** (`core.py:38-54`): CC's Agent infrastructure handles API retries. Pattern is useful for Agent slot replacement timing but not directly implementable.
- **Registry Singleton** (`registry.py:48-68`): Useful for tool/agent discovery but code-shiniyaya operates in SKILL.md which is not a Python runtime.
- **Multi-process Pipe Isolation** (`browser_env.py:357`): CC cannot spawn processes. Pattern absorbed as principle ("agent results isolated, no shared mutable state") but already implemented via "no shared files" rule (Rule 8).
