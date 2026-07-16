# Autonomous Coding Error Handling Patterns — code-shiniyaya Gap Analysis

**Date**: 2026-07-16
**Source**: `code-shiniyaya\autonomous-coding-src\` (Anthropic quickstarts repo, computer-use-best-practices + autonomous-coding + browser-use-demo)
**Target**: code-shiniyaya SKILL.md v3.7.0 + anti-hang-v2.md
**Dimension**: Error handling — recoverable vs unrecoverable classification, empty response recovery, keyboard interrupt handling, synthetic assistant turn insertion, and adjacent patterns

---

## Pattern 1: Recoverable vs Unrecoverable API Error Classification

**Source**: `computer-use-best-practices\computer_use\loop.py:84-113`

```python
_UNRECOVERABLE = (
    anthropic.BadRequestError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.UnprocessableEntityError,
)

def _is_recoverable(e: Exception) -> bool:
    if isinstance(e, _UNRECOVERABLE):
        return False
    if isinstance(e, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return True
    if isinstance(e, anthropic.APIStatusError) and 500 <= e.status_code < 600:
        return True
    return "overloaded" in str(e).lower()

def _call_with_retry(fn: Callable[[], T]) -> T:
    for attempt in range(cfg.api_retry_max_attempts):
        try:
            return fn()
        except Exception as e:
            if not _is_recoverable(e) or attempt + 1 >= cfg.api_retry_max_attempts:
                raise
            delay = cfg.api_retry_base_delay * (2**attempt) + random.uniform(0, 1)
            render.retry(attempt + 1, cfg.api_retry_max_attempts, e, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")
```

### code-shiniyaya Gap

SKILL.md 规则7 (Agent失败替换) says "Agent异常终止或挂起→替换, 每槽位最多2次→第3次永久失败" -- but there is **no classification** of which failures are transient (worth retrying) vs. permanent (should abort immediately). All failures are treated identically: replace and retry up to 2 times. The retry has **no exponential backoff** (it's immediate replacement), wasting Agent slots on unrecoverable errors (e.g., authentication, permission denied, bad request).

The error handling table (SKILL.md lines 106-126) has 15 rows of failure modes, but none classify errors by recoverability.

### Priority: P0

### Fix for SKILL.md

Add after the error handling table (after line 126):

```markdown
## 错误分类与重试策略

### 可恢复 vs 不可恢复分类

| 类别 | 错误类型 | 示例 | 动作 |
|------|---------|------|------|
| UNRECOVERABLE | 认证/权限/请求格式 | 401, 403, 400 Bad Request, 文件不存在(源文件) | 立即终止, 不重试. 标 PERMANENTLY_FAILED |
| RECOVERABLE | 速率限制/连接/5xx/过载 | 429, 502, 503, ConnectionError, "overloaded" | 指数退避重试, 最多3次 |
| UNKNOWN | 其他异常 | ValueError, 自定义异常 | 1次重试, 再失败→标 UNKNOWN+人工审查 |

### 指数退避算法

```
delay = base_delay * (2 ^ attempt) + random(0, 1)
base_delay: 1.0s (默认), 可通过 CODE_SHINIYAYA_RETRY_BASE_DELAY 环境变量覆盖
max_attempts: 3 (默认), 可通过 CODE_SHINIYAYA_RETRY_MAX_ATTEMPTS 环境变量覆盖

attempt 0: ~1-2s  delay
attempt 1: ~2-3s  delay
attempt 2: ~4-5s  delay  → 失败后永久终止
```

### 规则7修订 (Agent失败替换)

**旧**: Agent异常终止或挂起→替换, 每槽位最多2次→第3次永久失败

**新**: Agent失败→分类:
  (a) UNRECOVERABLE → 立即标 PERMANENTLY_FAILED, 不重试, 不占用槽位
  (b) RECOVERABLE → 指数退避重试, 最多3次, 每次退避后启动替换Agent
  (c) 3次RECOVERABLE重试均失败 → 标 PERMANENTLY_FAILED
  (d) Agent挂起(非异常退出) → 标记为 STALLED, 保持槽位, 启动旁路Agent(不替换原Agent——原Agent可能仍在产出)
```

### Fix for anti-hang-v2.md

In the Optimal Batching section, add:

```markdown
### Agent Failure Classification (imported from autonomous-coding loop.py)

- **Recoverable failures** (rate limit, 5xx, connection): exponential backoff retry with jitter
- **Unrecoverable failures** (auth, permission, bad request): immediate kill, flag slot as PERMANENTLY_FAILED
- **Overloaded detection**: check error message for "overloaded" substring → treat as recoverable
- **Backoff formula**: delay = 1.0 * (2^attempt) + random(0,1) seconds
```

---

## Pattern 2: Empty Response Recovery with Nudges

**Source**: `computer-use-best-practices\computer_use\loop.py:195-199, 431-448`

```python
def _is_empty_response(content: list[Any]) -> bool:
    if not content:
        return True
    return len(content) == 1 and getattr(content[0], "text", None) == ""

# In sampling_loop:
empty_retries = 0
...
if _is_empty_response(response.content):
    empty_retries += 1
    if empty_retries > cfg.empty_response_retry_max:
        raise RuntimeError(
            f"{empty_retries} consecutive empty responses from the model"
        )
    # Don't append the empty assistant turn: a non-final assistant
    # message with empty content is rejected by the API with a 400,
    # which would defeat this retry on its very next request.
    messages.append(
        {
            "role": "user",
            "content": "Please continue, do not produce an empty response.",
        }
    )
    continue
empty_retries = 0
```

**Config**: `constants.py:122` — `empty_response_retry_max: int = 3`

### code-shiniyaya Gap

code-shiniyaya has **zero handling for empty/silent model responses**. The Codex silence mechanism (N=4 message count, rule 13) tracks **human Codex user** not responding -- it is not about an AI model returning empty output. When an Agent produces no output, code-shiniyaya has no:

1. Detection: identify that an Agent returned empty/blank content
2. Recovery: inject a nudge prompt asking the Agent to try again
3. Bounding: limit nudge retries (max 3), then escalate to failure
4. API correctness: ensure empty assistant turns are NOT appended (they cause 400 errors)

This is especially critical for STEP 4 (10+ Agent Codex verification) and STEP 7 (CC 6+ Agent self-verification), where Agent silence can cause undetected partial results.

### Priority: P0

### Fix for SKILL.md

Add after the error handling table, before the 错误分类 section:

```markdown
## 空响应检测与渐进式唤醒

### 检测

Agent返回以下任一情况视为空响应:
- 空content列表 `[]`
- 仅含一个空文本块 `[{"type":"text","text":""}]`
- output_tokens=0 且无tool_use块

### 三级唤醒 (Empty Response Nudge Escalation)

| 尝试 | 唤醒文本 | 说明 |
|------|---------|------|
| 1 | "请继续, 不要输出空响应. 直接给出你的分析结果." | 温和提醒 |
| 2 | "你的上一次响应为空. 这是第2次提醒. 必须输出有效的分析结果, 包含file:line引用. 如果不确定, 请说明不确定的原因." | 强调后果 |
| 3 | "这是最后一次提醒(第3次). 如果仍然输出空响应, 此Agent将被标记为FAILED并替换." | 最终警告 |

- 3次空响应→标 FAILED_EMPTY_RESPONSE → 替换Agent
- **重要**: 空助手消息**不得**追加到消息历史(API会400). 仅追加用户唤醒消息.
- 每次非空响应→emptyRetryCount 重置为0

### 集成到现有错误表

| 步骤 | 失败模式 | 用户消息 | 恢复 |
|------|---------|---------|------|
| 全部 | Agent空响应 | "Agent #{id} 空响应第{n}次, 已唤醒" | 三级唤醒→3次后替换 |
```

### Fix for anti-hang-v2.md

After Agent Selection Matrix, add:

```markdown
## Empty Response Detection (from autonomous-coding loop.py)

Agents that return empty content are a silent failure mode -- not caught by stall detection
because they complete quickly (just with no output). Detection:

1. After each agent result: check if content is `[]` or `[{"text":""}]`
2. If empty: inject nudge "Please continue, do not produce an empty response."
3. Track `empty_retries` per agent slot. Max 3.
4. After max: flag slot as FAILED_EMPTY_RESPONSE, launch replacement.
5. CRITICAL: Do NOT append empty assistant turns to message history -- the API rejects them with 400.
```

---

## Pattern 3: KeyboardInterrupt Graceful Handling

**Source**: `computer-use-best-practices\computer_use\loop.py:322-328, 421-423, 490-498`

```python
def _interrupted_result(tool_use_id: str) -> ToolResultBlockParam:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": [{"type": "text", "text": "[interrupted by user]"}],
    }

# Catch 1: During streaming
try:
    response = _call_with_retry(...)
except KeyboardInterrupt:
    render.interrupted()
    break  # Discard partial response

# Catch 2: During tool execution
try:
    for tu in tool_uses:
        res = tools.run(tu.name, tu.input)
        ...
except KeyboardInterrupt:
    render.interrupted()
    done_ids = {r["tool_use_id"] for r in results}
    for tu in tool_uses:
        if tu.id not in done_ids:
            results.append(_interrupted_result(tu.id))
    messages.append({"role": "user", "content": results})
    trajectory.record("user", results)
    break
```

### code-shiniyaya Gap

SKILL.md 规则13 says "stop/中断/CTRL+C → 立即停, 等下条消息. 完成项保留(逐项确认保证), 未开始项待恢复." and the 停止线 section says "stop/中断/CTRL+C → 立即停, 不等不补."

But there is **no infrastructure-level handling** for what happens when a workflow is actually interrupted:
1. No mechanism to fill outstanding/in-progress tool_use blocks with "[interrupted]" sentinel values to keep the message list valid.
2. No differentiation between "interrupted during streaming" (discard partial) vs "interrupted during tool execution" (fill remaining slots with error results).
3. In STEP 6 (逐项执行), if Ctrl-C happens mid-fix-execution, the last item's state is ambiguous — was the Write committed? Was the ast.parse done? No sentinel records the interruption point.

### Priority: P1

### Fix for SKILL.md

Revise the 停止线 section:

```markdown
## 停止线 (修订)

- stop/中断/CTRL+C → 立即停, 不等不补
- **中断位置感知**:
  | 中断时机 | 动作 | 状态标记 |
  |---------|------|---------|
  | Agent流式输出中 | 丢弃部分响应, 不追加助手消息 | INTERRUPTED_DURING_STREAMING |
  | Agent工具执行中 | 对已完成的tool_use块保留结果; 未完成的追加 `[interrupted by user]` 错误结果, 保持消息列表API有效 | INTERRUPTED_DURING_TOOLS (N/M tools completed) |
  | STEP 6逐项执行中 | 当前项: 检查Write是否已commit(git status/diff)→已完成则mark done; 未完成则mark INTERRUPTED_MID_FIX. 后续项: PENDING | 逐项独立 |
- Write/Edit成功=完成 → 不Read
- ast.parse 1次通过 → 标完成
- 中断 → 保存JSON状态(含中断位置+in-flight状态) → 等下条消息
- 第2轮双向仍有争议 → "DISPUTED" → 用户裁决
- Codex不可用 > 连续5条用户消息 → 自动降级 → 不再等待
```

---

## Pattern 4: Synthetic Assistant Turn Insertion

**Source**: `computer-use-best-practices\computer_use\loop.py:503-516`

```python
# The for-loop can exit with messages ending in a user-role entry (Ctrl-C
# during streaming, Ctrl-C during tool execution, or max_iters reached on
# a tool-calling turn). Appending a follow-up user message on top of that
# would 400; insert a synthetic assistant turn so the API stays valid.
if messages and messages[-1].get("role") == "user":
    messages.append(
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "[stopped before completing]"}],
        }
    )
    trajectory.record(
        "assistant", [{"type": "text", "text": "[stopped before completing]"}]
    )
```

### code-shiniyaya Gap

code-shiniyaya's message protocol between CC and Codex is human-mediated (copy-paste), not API-mediated, so there is no direct "user-role → user-role 400 error" equivalent.

However, the **logic is transferable**: when the CC↔Codex workflow is interrupted (stop, Ctrl-C, or Codex silence → degraded mode), code-shiniyaya does not insert a *closure marker* to seal the incomplete state. This causes ambiguity on resume:

1. After interrupt, the session JSON state says `step: 6, itemStates: {..., "BUG-03": "in_progress"}` but there's no record of what the last CC action was (a Write? a Read? waiting for user approval?).
2. The equivalent of "[stopped before completing]" would be a synthetic turn that records the exact interrupt boundary.

### Priority: P1

### Fix for SKILL.md

In the itemStates schema, add an `interrupt_marker` field:

```markdown
### 中断标记 (itemStates扩展)

每个item在中断时记录:

```json
{
  "BUG-03": {
    "status": "INTERRUPTED",
    "substep": "6.1-symbol-analysis",
    "interruptMarker": {
      "lastAction": "Write completed, ast.parse pending",
      "lastActionTime": "2026-07-16T14:32:00",
      "filesWritten": ["src/parser.py:142"],
      "filesRead": ["src/parser.py:1-200"],
      "pendingAction": "ast.parse src/parser.py",
      "messageListState": "last_role=assistant, last_content='[stopped before ast.parse verification]'"
    }
  }
}
```

恢复时读取interruptMarker→从pendingAction继续→无需重新诊断.
```

---

## Pattern 5: Config-Driven Error Parameters (Feature Toggles + Retry Knobs)

**Source**: `computer-use-best-practices\constants.py:68-179`

```python
@dataclass(frozen=True)
class Config:
    api_retry_max_attempts: int = 5
    api_retry_base_delay: float = 1.0
    empty_response_retry_max: int = 3
    max_shell_output_bytes: int = 64 * 1024
    default_max_iters: int = 200
    image_prune_strategy: ImagePruneStrategy = "interval"
    enable_computer_use_tools: bool = True
    enable_browser_use_tools: bool = True
    enable_editor_tool: bool = True
    enable_advisor_tool: bool = False
    enable_autocompaction: bool = True
    ...

    @classmethod
    def load(cls, toml_path, **overrides) -> "Config":
        """Build from defaults -> toml -> CU_* env vars -> overrides."""
```

4-tier config hierarchy: dataclass defaults → TOML file → `CU_*` env vars → CLI `--set FIELD=VALUE`

### code-shiniyaya Gap

All code-shiniyaya parameters are **hardcoded** in SKILL.md prose:
- `batch_size = max(4, min(16, cpu_cores-2))` (line 72)
- `N=4` silence threshold (line 35)
- `Agent上限=50` (line 72)
- `3次同文件失败→停止` (line 82)
- `max_iters=200` equivalent not even specified

There is no config file, no env var overrides, no CLI overrides. Users who want different behavior (e.g., smaller batches on low-RAM machines, more aggressive silence thresholds) have to manually edit SKILL.md.

### Priority: P2

### Fix for SKILL.md

Add a Config section:

```markdown
## 可配置参数

所有参数有默认值，可通过 `CODE_SHINIYAYA_CONFIG` 环境变量指向TOML文件覆盖，
或通过 `CODE_SHINIYAYA_<PARAM>` 环境变量单独覆盖:

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| silence_threshold_n | 4 | CODE_SHINIYAYA_SILENCE_N | Codex静默检测阈值(用户消息数) |
| agent_retry_max | 3 | CODE_SHINIYAYA_RETRY_MAX | Agent失败重试次数(RECOVERABLE) |
| agent_retry_base_delay | 1.0 | CODE_SHINIYAYA_RETRY_DELAY | 指数退避基础延迟(秒) |
| empty_response_retry_max | 3 | CODE_SHINIYAYA_EMPTY_RETRY_MAX | 空响应唤醒最大次数 |
| batch_size_max | 16 | CODE_SHINIYAYA_BATCH_MAX | 单批次Agent上限 |
| agent_cap | 50 | CODE_SHINIYAYA_AGENT_CAP | 总Agent上限 |
| dag_max_hops | 1 | CODE_SHINIYAYA_DAG_HOPS | DAG传递依赖最大跳数 |
| fix_retry_max | 3 | CODE_SHINIYAYA_FIX_RETRY | 同文件修复失败最大次数 |

TOML配置示例:
```toml
# code-shiniyaya.toml
silence_threshold_n = 3
agent_retry_max = 5
empty_response_retry_max = 2
```
```

---

## Pattern 6: Tool Execution Error Isolation (Per-Tool Catch + Graceful Degradation)

**Source**: `computer-use-best-practices\computer_use\tools\base.py:89-110`, `tools\result.py:36-64`

```python
class ToolResult:
    output: str | None = None
    error: str | None = None
    base64_image: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

class ToolCollection:
    def run(self, name: str, tool_input: object) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(error=f"Unknown tool: {name}")
        if not isinstance(tool_input, dict):
            return ToolResult(error=f"tool input must be an object, got {type(tool_input).__name__}")
        try:
            return tool.execute(**tool_input)
        except Exception as e:
            return ToolResult(error=f"{type(e).__name__}: {e}")

    def close(self) -> None:
        for tool in self._tools.values():
            close = getattr(tool, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
```

### code-shiniyaya Gap

SKILL.md 规则7 says "Agent异常终止或挂起→替换" -- but **every failed agent loses its partial results entirely**. There is no `ToolResult` equivalent that captures:
1. `output`: what the agent did produce before failing
2. `error`: what went wrong
3. `is_error`: flag to distinguish success from failure

Without this structure, the journal-parser can only extract results from completed agents (type: "result" lines). A partial result (agent started work, produced some findings, then crashed) is completely lost.

Also, the `close()` with `suppress(Exception)` pattern -- when cleaning up agent resources (STEP 6 git checkout back, temp file removal), one cleanup failure should never block others.

### Priority: P1

### Fix for SKILL.md

Add to Agent编排 section:

```markdown
### Agent结果结构 (统一ToolResult模式)

每个Agent返回统一结构, 无论成功或失败:

```
{
  "agentId": "str",
  "agentType": "investigator|Explore|general-purpose|Plan|debugging",
  "status": "COMPLETED|FAILED|TIMED_OUT|STALLED",
  "output": "str | null",       // 成功时的产出
  "error": "str | null",        // 失败时的错误信息
  "is_error": true|false,
  "findings": [...],            // 部分成功时: 已完成的发现(即使agent最终失败)
  "completedDimensions": [...], // 已扫描的维度
  "failedDimensions": [...],    // 未完成的维度
  "partialResult": true|false   // 是否有可恢复的部分结果
}
```

**规则**: 即使Agent异常终止, 已产出的findings必须保留并合并到结果集。
`partialResult=true` 的Agent → 未完成维度排入重跑队列, 已完成维度正常合并.

### 清理隔离 (Resource Cleanup Isolation)

Agent/工作流清理时: 每个资源的清理操作独立进行, 一个失败不阻塞其他:
```
for resource in resources_to_cleanup:
    try:
        resource.close()
    except Exception:
        pass  // 记录但继续
```
```

---

## Pattern 7: Prompt Caching / Context Management as Error Prevention

**Source**: `computer-use-best-practices\computer_use\loop.py:58-81` + `formatters.py:55-94`

```python
_CACHEABLE_BLOCK_TYPES = {"tool_result", "compaction"}
_MAX_BODY_CACHE_BREAKPOINTS = 3

def _set_trailing_cache_control(messages):
    """Put cache breakpoints on the last few cacheable blocks."""
    # Clears old breakpoints first, then sets new ones on the last 3 blocks

class StripImagesAtIntervals:
    """Cache-friendly: keeps ((total % interval) + min_images) images.
    Only changes the removed set every `interval` turns, so prompt cache
    stays valid for interval-1 consecutive calls."""
    
    def __call__(self, messages):
        keep = ((total - self._offset) % self.interval) + self.min_images
        # ... force-prune fallback when message exceeds provider size cap
```

**Config parameters**: `image_prune_strategy`, `keep_n_most_recent_images`, `image_prune_min`, `image_prune_interval`, `PROVIDER_MAX_MESSAGE_MB`, `jpeg_quality`, `max_shell_output_bytes`

### code-shiniyaya Gap

code-shiniyaya has no concept of "context window pressure prevention." STEP 3 has a reactive token limit check (>10000 tokens → split), but there is **no proactive strategy** to:
1. Keep context size within bounds before it becomes a problem
2. Use a "stepped" approach where the same prefix is kept across multiple turns for cache efficiency
3. Force-prune when a hard provider limit is approached

For code-shiniyaya, the equivalent is: iterative scanning (SKILL.md 迭代扫描工作流 section) can accumulate agent output across iterations. With no pruning, agent context grows unboundedly across multiple scan iterations.

### Priority: P2

### Fix for SKILL.md and anti-hang-v2.md

Add to anti-hang-v2.md:

```markdown
### Context Pressure Prevention (from autonomous-coding formatters.py)

Multi-iteration scans accumulate agent output. Without bounds:

1. **Interval-based output retention**: Keep last N complete agent results + a sliding window
   of the current iteration's results. Older iterations' full output is replaced with summary
   blocks: `[Iter #N: 2P/3I/1F — summary in scan-state-N.json]`

2. **Force-prune fallback**: If serialized context exceeds a provider-specific cap:
   - Anthropic direct: ~200K tokens (~no practical limit with caching)
   - Vertex: estimated ~150K tokens
   - Drop oldest iteration summaries first, then oldest complete results, then alert.

3. **Cache-stable prefix**: When doing iterative scans over the same codebase, the system
   prompt + repository snapshot should be cache-stable. Only the per-iteration findings change.
   This is achieved by keeping the immutable checklist / scan target list in the prefix.
```

Add to SKILL.md STEP 1 (diagnostic scanning):

```markdown
### 迭代间上下文修剪

多轮迭代扫描时:
- 保留最近2轮完整结果 + 当前轮次进行中结果
- 更早轮次替换为摘要: `[Iter #N: {p}P/{i}I/{f}F → 详见 scan-state-N.json]`
- 硬上限: 单次API请求不超过 provider_size_cap (默认从provider检测, 回退=150K tokens)
- 超出上限→按轮次从旧到新强制修剪→仍超出→标ERROR+通知用户
```

---

## Pattern 8: Preflight Permission Checks (Fail-Fast Before Any Work)

**Source**: `computer-use-best-practices\computer_use\preflight.py:1-153`

```python
def check_and_warn(*, require: bool = True, open_settings: bool = True) -> bool:
    sr = screen_recording_granted()
    ax = accessibility_granted()
    if sr and ax:
        return True
    # Detailed error messages for each missing permission
    # Opens System Settings to the relevant pane
    # Exits with code 1 if require=True
```

### code-shiniyaya Gap

code-shiniyaya's STEP 0 (三Skill前置) does pre-checks, but does not verify **environmental prerequisites** before launching expensive multi-agent workflows:

1. No check that required tools (python, git, node) are available
2. No check that output directories are writable
3. No check that required skills (openspec-explore, using-superpowers) are installed
4. No check that sufficient disk space exists for agent output

If these fail mid-workflow (e.g., disk full at agent 7/10), partial work is lost and error recovery is messy.

### Priority: P2

### Fix for SKILL.md

Add to STEP 0:

```markdown
### STEP 0.1 — 环境前置检查 (Fail-Fast, 新增)

在启动任何Agent前, 运行最小检查:
1. `python -c "import ast"` → 验证Python可用
2. `git --version` → 验证Git可用(STEP 6需要)
3. 检查 `CODE_SHINIYAYA_REPORT_DIR` 或默认 `reports/` 目录可写:
   `touch reports/.write_test && rm reports/.write_test`
4. 检查可用磁盘空间 ≥ 100MB (Agent输出+日志):
   `python -c "import shutil; print(shutil.disk_usage('.').free)"`

任一失败→立即终止, 不启动Agent. 给出具体修复指引.
```

---

## Pattern 9: Batch Nudging (Real-Time Behavior Correction)

**Source**: `computer-use-best-practices\computer_use\loop.py:310-319, constants.py:380-397`

```python
def _should_nudge_batch(tool_uses: list[Any]) -> bool:
    if len(tool_uses) != 1:
        return False
    tu = tool_uses[0]
    if tu.name not in {"computer", "browser"}:
        return False
    action = tu.input.get("action") if isinstance(tu.input, dict) else None
    return action in BATCH_REMINDER_ACTIONS

# In loop: if nudge is needed, append reminder to tool_result content
if nudge and not res.is_error:
    content.append({"type": "text", "text": BATCH_REMINDER})
```

### code-shiniyaya Gap

code-shiniyaya has no mechanism for **in-session behavioral correction**. When an Agent exhibits suboptimal behavior (e.g., single-file scanning when it should do multi-file cross-referencing, outputting vague findings without file:line references), there is no nudge mechanism to correct it.

If Agent A returns findings without file:line references, code-shiniyaya's merge step (STEP 1.4) just drops them or marks them low-confidence. There is no feedback loop to tell the next batch of Agents "include file:line references."

### Priority: P2

### Fix for SKILL.md

Add to STEP 1 after the 去重合并 step:

```markdown
### Agent行为微调 (Nudge Injection)

根据上批次Agent的产出质量, 动态注入提示词微调:

| 检测模式 | 触发条件 | 微调注入 |
|---------|---------|---------|
| 无file:line引用 | >30% findings缺少file:line | "必须对每个发现给出具体的 file:line 引用. 格式: `src/parser.py:142`" |
| 笼统描述 | >30% findings描述<20字符 | "每个发现必须包含具体代码片段. 不要只说'存在bug'而不展示代码." |
| 无严重度 | >30% findings无P0/P1/P2 | "每个发现必须标注严重度: P0(崩溃/安全), P1(功能), P2(质量)" |
| 重复发现 | 与上批次去重率>50% | "以下发现已在上批次确认, 不需要重复报告: {list}. 专注于新发现." |

微调追加到下一批次Agent的系统提示词末尾, 作为 `<reminder>` 块.
```

---

## Pattern 10: `__init_subclass__` Schema Validation (Catch Spec Drift at Import Time)

**Source**: `computer-use-best-practices\computer_use\tools\base.py:34-53`

```python
def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    if inspect.isabstract(cls) or cls.validates_own_input:
        return
    props = set(cls.input_schema.get("properties", {}))
    required = set(cls.input_schema.get("required", []))
    params = inspect.signature(cls.execute).parameters
    execute_params = {k for k in params if k != "self"}
    missing = props - execute_params
    if missing:
        raise TypeError(f"{cls.__name__}.input_schema declares {sorted(missing)} but "
                         f"execute() does not accept them")
    for r in required:
        if params[r].default is not inspect.Parameter.empty:
            raise TypeError(f"{cls.__name__}.input_schema marks {r!r} required but "
                            f"execute() gives it a default")
```

### code-shiniyaya Gap

code-shiniyaya specifies Agent output schemas in prose (e.g., "Agent发现必须有 file, line, severity, description"). But there is **no enforcement** that Agents actually follow this schema. A finding missing `line` or `severity` silently enters the merge pipeline and may crash downstream processing or produce corrupted state files.

### Priority: P1

### Fix for SKILL.md

Add after STEP 1 去重合并:

```markdown
### Agent输出Schema校验 (入口门控)

每个Agent输出在合并前必须通过schema校验:

**必填字段 (所有发现)**:
- `file`: str, 源文件路径
- `severity`: "P0" | "P1" | "P2"
- `description`: str, ≥20字符

**可选字段**:
- `line`: int | null, 精确行号(无则为null)
- `fix`: str | null, 建议修复

**校验动作**:
- 缺失必填字段 → 发现被隔离到 `_SCHEMA_REJECTED` 组
- 连续2个Agent >50%发现被拒 → 该Agent类型标 `VALIDATES_OWN_OUTPUT=false` → 下一批次追加schema要求到其系统提示词
- schema被拒的发现不丢弃 → 写入 `schema-violations-{sessionId}.json` 供人工审查
```

---

## Summary: Priority Matrix

| # | Pattern | Priority | Target File | Impact |
|---|---------|----------|-------------|--------|
| 1 | Recoverable vs Unrecoverable Error Classification + Exponential Backoff | P0 | SKILL.md + anti-hang-v2.md | Eliminates wasted retries on permanent errors; adds jitter to prevent thundering herd |
| 2 | Empty Response Detection + Three-Level Nudge Escalation | P0 | SKILL.md + anti-hang-v2.md | Catches silent agent failures that stall detection misses; preserves API message validity |
| 3 | KeyboardInterrupt Position-Aware Handling (streaming vs tool execution) | P1 | SKILL.md | Prevents message-list corruption on interrupt; enables clean resume |
| 4 | Synthetic Assistant Turn Insertion (interrupt closure marker) | P1 | SKILL.md | Enables unambiguous resume from interrupt boundaries |
| 5 | Config-Driven Error Parameters (TOML + env vars) | P2 | SKILL.md | Allows runtime tuning without editing SKILL.md |
| 6 | ToolResult Error Isolation + Graceful Cleanup Degradation | P1 | SKILL.md | Preserves partial agent results; prevents cleanup cascade failures |
| 7 | Context Pressure Prevention (interval-based pruning + force-prune) | P2 | anti-hang-v2.md | Prevents unbounded context growth across scan iterations |
| 8 | Preflight Environment Checks (fail-fast before agent launch) | P2 | SKILL.md | Avoids mid-workflow failures from missing tools/permissions |
| 9 | Batch Nudging (real-time behavior correction) | P2 | SKILL.md | Improves agent output quality within same session |
| 10 | Agent Output Schema Validation (import-time style enforcement) | P1 | SKILL.md | Prevents malformed findings from corrupting downstream processing |
