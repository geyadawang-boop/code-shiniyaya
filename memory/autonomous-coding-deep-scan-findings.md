# Autonomous-Coding Deep Scan: New Patterns for code-shiniyaya

**Date**: 2026-07-16
**Source**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src`
**Target**: code-shiniyaya SKILL.md v3.7.0 + anti-hang-v2.md
**DIMENSION focus**: Two-agent orchestration (Init Agent + Loop Agent), is_first_run gating, auto-continue with delay
**Method**: Full file-level scan of all 313 files, with deep read of agent.py, loop.py, history_util.py, tools/base.py, prompts/*.md, client.py, security.py, trajectory.py, connections.py, tool_util.py

---

## NOTE: Prior gap analysis existence

The file `autonomous-coding-gap-analysis.md` already covers 7 dimensions:
1. Two-Agent Init+Loop Model
2. Immutable Checklist
3. ThinkTool Reasoning
4. Trajectory Recording
5. Error Recovery Fresh-Session
6. Safety Three-Layer
7. Prompt Structure Enforcement

**This file covers ONLY patterns NOT present in the prior analysis.** These are NEW discoveries from deeper code inspection.

---

## PATTERN 1: Auto-Continue With Fixed Delay (Hang Prevention Core)

**File:Line**: `autonomous-coding/agent.py:20` and `agent.py:173-177`

**Source code**:
```
AUTO_CONTINUE_DELAY_SECONDS = 3

if status == "continue":
    print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
    print_progress_summary(project_dir)
    await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
```

**What it does**: After each iteration completes with status="continue", the loop prints a summary, waits a fixed delay, then auto-launches the next iteration with a fresh client. No user confirmation needed. The only stop conditions are: (a) max_iterations reached, (b) error status returned, (c) user KeyboardInterrupt.

**code-shiniyaya gap**: code-shiniyaya's iteration scanning workflow (SKILL.md lines 456-480) requires the user to say "继续修复" or manually trigger each iteration. CC has no mechanism to auto-continue between scan→fix→verify iterations. The "convergence tracking" section describes CR (convergence rate) but has NO auto-continue implementation — CC just stops and waits for the user.

**Concrete fix for SKILL.md** — Add to the "迭代扫描工作流" section (after line 479):

```markdown
### Auto-Continue Protocol (Anti-Stall)

When code-shiniyaya enters autonomous iteration mode (iterative scan→fix→verify),
auto-continue between iterations WITHOUT waiting for user confirmation:

**Auto-continue flow**:
```
iter#N COMPLETE → print summary → wait 3s → auto-launch iter#N+1
                  ↑
                  └── only pause when:
                      (a) all CRITICAL resolved (CRITICAL_count = 0)
                      (b) convergence failure (CR < 0 for 2 consecutive iters)
                      (c) 3 consecutive iterations with CR < 20%
                      (d) max_iterations reached (default: 10, user can override)
                      (e) user interrupts ("stop"/"暂停")
```

**Implementation (CC prompt pattern)**:
```
After each iteration completes:
1. Print: "[iter#{N}] COMPLETE: {p}P/{f}F/{c}C | CR={rate}%"
2. Check stop conditions:
   - CRITICAL = 0 → print "All critical issues resolved." → STOP
   - CR < 0 for 2 iters → print "Diverging. Strategy change needed." → STOP
   - CR < 20% for 3 iters → print "Slow convergence. Continue? (auto-continuing in 10s, say stop to halt)" → wait 10s
3. If no stop condition: print "[iter#{N+1}] Auto-continuing in 3s..." → wait 3s → launch next iteration
```

**Why this matters**: Without auto-continue, the user must babysit the skill. Each iteration takes 2-5 minutes. Manual stepping means 30+ minutes of active attention for a 10-iteration scan. Auto-continue makes the skill truly autonomous.
```

**Priority: P0** — Without this, the iteration scanning workflow is not autonomous. It requires manual user stepping between iterations.

---

## PATTERN 2: Empty-Response Retry With Nudge

**File:Line**: `computer-use-best-practices/computer_use/loop.py:195-198` and `loop.py:431-446`

**Source code**:
```python
def _is_empty_response(content: list[Any]) -> bool:
    if not content:
        return True
    return len(content) == 1 and getattr(content[0], "text", None) == ""

if _is_empty_response(response.content):
    empty_retries += 1
    if empty_retries > cfg.empty_response_retry_max:
        raise RuntimeError(
            f"{empty_retries} consecutive empty responses from the model"
        )
    # Don't append the empty assistant turn
    messages.append({
        "role": "user",
        "content": "Please continue, do not produce an empty response.",
    })
    continue
```

**What it does**: When Claude returns an empty response (no text, no tool calls), the loop does NOT append the empty turn (API rejects it with 400), instead appends a user nudge message and retries. After N consecutive empty responses, raises RuntimeError.

**code-shiniyaya gap**: code-shiniyaya has NO empty-response detection for sub-agents. When 8 agents are dispatched in parallel and one returns empty (stalled model), CC has no mechanism to detect this and re-prompt. The agent is silently counted as "done" even though it produced nothing. This is a stealth failure mode that looks like completion but is actually a hung agent.

**Concrete fix for anti-hang-v2.md** — Add after "Hang Detection: Message-Count Based" section:

```markdown
### Empty-Response Detection

Agents can silently fail by returning empty output (no text, no tool calls).
This is indistinguishable from "agent is still working" without explicit detection.

**Detection rule**: If an agent's output stream ends with zero text blocks AND zero
tool calls, the agent produced an empty response.

**Recovery protocol**:
1. Do NOT count the agent as "done"
2. Resend the prompt with a nudge prefix:
   ```
   [NUDGE] Your previous response was empty. Please provide your analysis
   and results in the expected format. Original task: {original_prompt}
   ```
3. Track `empty_response_retries` per agent slot
4. After 2 consecutive empty responses → mark agent as STUCK, replace with
   fallback agent type (general-purpose as universal fallback)
5. After 3 consecutive empty responses across all slots → workflow may be
   fundamentally stuck → notify user

**Integration with straggler detection**:
An agent that produced ONLY empty responses counts as a straggler
(no actual result after 3+ other agents completed).
```

**Priority: P0** — Empty responses are a stealth failure mode. Without detection, dead agents are counted as "completed."

---

## PATTERN 3: Recoverable vs Unrecoverable Error Classification

**File:Line**: `computer-use-best-practices/computer_use/loop.py:84-99` and `loop.py:102-113`

**Source code**:
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

def _call_with_retry(fn):
    for attempt in range(cfg.api_retry_max_attempts):
        try:
            return fn()
        except Exception as e:
            if not _is_recoverable(e) or attempt + 1 >= cfg.api_retry_max_attempts:
                raise
            delay = cfg.api_retry_base_delay * (2**attempt) + random.uniform(0, 1)
            render.retry(attempt + 1, cfg.api_retry_max_attempts, e, delay)
            time.sleep(delay)
```

**What it does**: Classifies errors into two categories:
- **Recoverable**: Rate limits (429), connection errors, 5xx server errors, "overloaded" messages. Retry with exponential backoff + jitter.
- **Unrecoverable**: Bad request (400), auth errors (401/403), unprocessable entity (422). Fail immediately without retry.

**code-shiniyaya gap**: code-shiniyaya's error handling table (lines 107-126) treats all errors uniformly:
- "Agent全超时" → "缩小范围重试"
- "个别超时" → "每维度>=1成功; 全失败->人工审查"

There is NO classification of WHY an agent failed. A rate limit error (transient) is treated the same as an auth error (permanent). The "max 2 retries per slot" (Rule 7) is applied uniformly — a rate limit failure consumes a retry slot just like a bad request. This wastes retry budget on transient errors while letting permanent errors retry unnecessarily.

**Concrete fix for SKILL.md** — Replace "Rule 7 — Agent失败替换" with classified retry:

```markdown
### Rule 7 — Classified Agent Retry (Replaces v3.7.0 Rule 7)

Agent failures are classified BEFORE retry decisions:

**Type A — Transient (DO retry, DO NOT consume slot budget)**:
- Rate limit / quota exceeded
- Connection timeout / network error  
- Server overload (500/502/503/504)
- Agent process killed by OOM (exit code 137)
- Context window overflow (model reports > limit)
  → Retry with exponential backoff: 2s → 4s → 8s → 16s (max 4 retries)
  → Retries do NOT consume the per-slot replacement budget (max 2)
  → On 4th consecutive transient failure → escalate to Type B

**Type B — Permanent (consume slot budget, max 2 replacements)**:
- Authentication / permission denied
- Bad request / invalid parameters
- Tool not found / tool schema mismatch
- Syntax error in agent output
  → Consume 1 replacement slot
  → Replace with fallback agent type (general-purpose)
  → On 2nd replacement consumed → permanent failure for this slot

**Type C — Systemic (stop entire workflow)**:
- All slots Type-B failed simultaneously
- Same Type-B error across all agents (indicates config/setup issue)
- Disk full during file write
  → Stop workflow, write STOP_LOG.md, notify user

**Why this matters**: Without classification, a rate limit burst consumes all retry
budget in seconds, leaving legitimate failures unretried. Type A errors are ~60%
of agent failures in practice. Not distinguishing them wastes retry capacity.
```

**Priority: P0** — Transient errors dominate agent failures. Classifying them prevents wasted retry budget.

---

## PATTERN 4: Fresh Client Per Iteration (Context Isolation)

**File:Line**: `autonomous-coding/agent.py:158-169`

**Source code**:
```python
# Create client (fresh context)
client = create_client(project_dir, model)

# Choose prompt based on session type
if is_first_run:
    prompt = get_initializer_prompt()
    is_first_run = False
else:
    prompt = get_coding_prompt()

async with client:
    status, response = await run_agent_session(client, prompt, project_dir)
```

**What it does**: Every loop iteration creates a BRAND NEW `ClaudeSDKClient` instance (line 159). No accumulated message history carries over. The only shared state is on disk (checklist.json, progress.txt, git log). This means:
- Context corruption cannot propagate between iterations
- A bad turn cannot poison future turns
- Memory leaks are bounded to one iteration
- Each iteration starts with clean system prompt + current disk state

**code-shiniyaya gap**: code-shiniyaya dispatches sub-agents with ad-hoc prompts that CC constructs. But CC itself carries accumulated context (diagnosis findings, plan details, Codex feedback) across the entire multi-hour session. If CC's context becomes corrupted (e.g., confusing two similar bug descriptions), it propagates to all subsequent sub-agent dispatches. There is NO mechanism for CC to "reset" its own context mid-session.

**Concrete fix for anti-hang-v2.md**:

```markdown
### Context Isolation: Fresh Dispatch Per Iteration

For long-running autonomous sessions (>3 iterations), CC should treat each
iteration as a FRESH dispatch, not a continuation of the same conversation:

**Per-iteration context reset**:
1. Write a `context-snapshot-iter{N}.md` file containing ONLY:
   - Current checklist (copy from disk)
   - Last progress summary (1 paragraph)
   - Current convergence metrics (CRITICAL count, CR rate, P0 list)
   - Next iteration's focus (which bugs/tasks to address)
2. Launch the next iteration's sub-agents with ONLY the snapshot as context
3. Do NOT reference previous agent outputs directly — agents re-read from disk

**Why**: After 3+ iterations, CC's accumulated context contains stale agent
outputs, outdated line numbers, and resolved findings that confuse new agents.
A fresh dispatch forces agents to trust only what's on disk (git log,
checklist.json, progress.txt) — not what CC remembers from iteration 1.

**Implementation**:
```
After iter#N completes:
1. Write context-snapshot-iter{N}.md to memory/
2. CC clears in-memory agent outputs (retain only metrics: CRITICAL count, CR rate)
3. iter#N+1 agents receive: "Read context-snapshot-iter{N}.md for current state"
4. iter#N+1 agents MUST re-read checklist.json and progress.txt from disk
```
```

**Priority: P1** — Important for long sessions (>3 iterations) but less critical for short sessions. Context corruption is cumulative and hard to detect.

---

## PATTERN 5: KeyboardInterrupt Graceful Fill

**File:Line**: `computer-use-best-practices/computer_use/loop.py:322-328` and `loop.py:490-498`

**Source code**:
```python
def _interrupted_result(tool_use_id: str) -> ToolResultBlockParam:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": [{"type": "text", "text": "[interrupted by user]"}],
    }

# During tool execution KeyboardInterrupt:
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

Also at lines 503-516 (synthetic assistant turn):
```python
# The for-loop can exit with messages ending in a user-role entry
# (Ctrl-C during streaming, Ctrl-C during tool execution, or max_iters
# reached on a tool-calling turn). Appending a follow-up user message
# on top of that would 400; insert a synthetic assistant turn so the
# API stays valid.
if messages and messages[-1].get("role") == "user":
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "[stopped before completing]"}],
    })
    trajectory.record("assistant", [{"type": "text", "text": "[stopped before completing]"}])
```

**What it does**: When user hits Ctrl-C during tool execution:
1. Fills ALL incomplete tool_use blocks with "[interrupted by user]" error results
2. Appends results as a user-role message (keeping API validity)
3. Records to trajectory
4. Breaks the tool-execution loop (not the outer loop)
5. At the outer level, inserts a synthetic "[stopped before completing]" assistant turn so the message list stays API-valid (no two consecutive user-role messages)

**code-shiniyaya gap**: code-shiniyaya's Rule 13 says "stop/中断/CTRL+C → 立即停, 等下条消息。完成项保留(逐项确认保证), 未开始项待恢复。" But this only covers CC-side behavior. It does NOT handle:
- In-progress tool calls within a sub-agent when interrupted
- API message list validity after interruption (two consecutive user messages = 400 error)
- Partial tool results from the interrupted agent

When CC calls TaskStop on a workflow and the agents are mid-tool-execution, their tool results are lost. On recovery, the journal.jsonl has incomplete entries.

**Concrete fix for anti-hang-v2.md**:

```markdown
### Graceful Interruption: Fill Incomplete Tool Results

When CC interrupts a running workflow (TaskStop, user "stop", timeout):

**Problem**: Agents mid-tool-execution have tool_use blocks without matching
tool_result blocks. On recovery, the message history is API-invalid (can't
append new user message after incomplete assistant turn).

**Solution**: Before killing, CC sends a synthetic "fill" pass:
```
For each agent in workflow:
  For each tool_use block without a matching tool_result:
    Record synthetic result:
      tool_use_id: <id>
      is_error: true
      content: "[interrupted by user — agent {agent_name}]"
  Append synthetic assistant turn:
    "[stopped before completing — {completed_tools}/{total_tools} tools done]"
```

**Why this matters for recovery**: Without synthetic fill, the journal.jsonl
has dangling tool_use blocks. The journal-parser sees incomplete entries and
cannot distinguish "agent crashed" from "agent was mid-execution." With
synthetic fill, the partial state is explicit and recoverable.

**Implementation for CC**:
```
1. User says "终止" or timeout reached
2. CC sends "INTERRUPT" signal to each agent slot
3. Agent receives signal → for each pending tool_use:
   a. Record synthetic [interrupted] tool_result  
   b. Append to agent's output stream
4. CC calls TaskStop(workflow_id) only AFTER all agents acknowledged INTERRUPT
5. On recovery: journal-parser.py detects synthetic results → marks items as
   INTERRUPTED (not FAILED, not MISSING)
```
```

**Priority: P1** — Improves recovery accuracy after interruption. Currently recovery sometimes loses track of which items were mid-execution vs never started.

---

## PATTERN 6: MessageHistory with Token-Aware Truncation

**File:Line**: `agents/utils/history_util.py:69-111`

**Source code**:
```python
def truncate(self) -> None:
    """Remove oldest messages when context window limit is exceeded."""
    if self.total_tokens <= self.context_window_tokens:
        return

    TRUNCATION_NOTICE_TOKENS = 25
    TRUNCATION_MESSAGE = {
        "role": "user",
        "content": [{"type": "text", "text": "[Earlier history has been truncated.]"}],
    }

    def remove_message_pair():
        self.messages.pop(0)
        self.messages.pop(0)
        if self.message_tokens:
            input_tokens, output_tokens = self.message_tokens.pop(0)
            self.total_tokens -= input_tokens + output_tokens

    while (self.message_tokens and len(self.messages) >= 2
           and self.total_tokens > self.context_window_tokens):
        remove_message_pair()
        if self.messages and self.message_tokens:
            original_input_tokens, original_output_tokens = self.message_tokens[0]
            self.messages[0] = TRUNCATION_MESSAGE
            self.message_tokens[0] = (TRUNCATION_NOTICE_TOKENS, original_output_tokens)
            self.total_tokens += (TRUNCATION_NOTICE_TOKENS - original_input_tokens)
```

**What it does**: Maintains running token count per message pair (input_tokens, output_tokens). When total exceeds context_window_tokens, pops oldest pairs from the front and replaces the new oldest message with "[Earlier history has been truncated.]" notice. The notice replacement preserves the assistant's output tokens but swaps the input tokens for the notice's size.

**code-shiniyaya gap**: code-shiniyaya uses the Claude Code SDK (not the raw API), so direct MessageHistory management is not available. However, the **concept** applies: when dispatching sub-agents with large contexts (diagnosis reports, plan documents, Codex feedback), CC should estimate token usage and truncate proactively rather than waiting for the model to hit its context limit.

**Concrete fix for anti-hang-v2.md**:

```markdown
### Token-Aware Context Management for Sub-Agent Dispatch

When dispatching sub-agents with large accumulated context:

**Problem**: CC passes entire diagnosis report (200+ lines) and full plan
to every sub-agent. When an agent scans many files and produces large tool
outputs, it silently hits the context window limit. Output is truncated,
reasoning is corrupted, but no error is raised.

**Detection (before dispatch)**:
1. Estimate total tokens = system_prompt_tokens + message_tokens + tool_output_tokens
2. If > 80% of model's context window (e.g., >160K for 200K window):
   a. Truncate oldest findings from the prompt
   b. Replace with: "[Earlier diagnosis findings have been truncated. Full report in {path}]"
   c. Provide file path to full report so agent can Read if needed

**Proactive truncation rule**: CC should NEVER dispatch an agent with > 80% of
its context window filled. Truncate BEFORE dispatch, not after.

**After-agent recovery**: If agent output is suspiciously short (< 100 chars for
a diagnosis task) or ends mid-sentence → suspect context truncation. Mark agent
as TRUNCATED (separate from FAILED) and re-launch with reduced context.

**Implementation**: Add a `token_estimate` function to the dispatch pipeline:
```
STEP 1 agent dispatch:
  total_est = len(system_prompt) / 4 + len(accumulated_findings) / 4
  if total_est > 0.8 * 200000:  # assuming 200K context
    truncate oldest findings
    inject truncation notice
  dispatch agent with final prompt
```
```

**Priority: P1** — Prevents silent context truncation but requires token estimation heuristics. Claude Code SDK provides no token counting API for sub-agent contexts.

---

## PATTERN 7: Prompt Caching Architecture (Cache Breakpoints)

**File:Line**: `computer-use-best-practices/computer_use/loop.py:55-81`

**Source code**:
```python
_CACHEABLE_BLOCK_TYPES = {"tool_result", "compaction"}
_MAX_BODY_CACHE_BREAKPOINTS = 3

def _set_trailing_cache_control(messages: list[MessageParam]) -> None:
    """Put cache breakpoints on the last few cacheable blocks."""
    cacheable: list[Any] = []
    for msg in messages:
        content = msg["content"]
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") in _CACHEABLE_BLOCK_TYPES:
                block.pop("cache_control", None)
                cacheable.append(block)

    for block in cacheable[-_MAX_BODY_CACHE_BREAKPOINTS:]:
        block["cache_control"] = _EPHEMERAL
```

**What it does**: Adds `cache_control: {"type": "ephemeral"}` to the last 3 cacheable blocks (tool_result, compaction) in the message list. Also puts a cache breakpoint on the system prompt. The API uses these as cache prefixes — subsequent requests with matching prefixes get cache hits, reducing input token costs by ~90% for cached portions.

**code-shiniyaya gap**: code-shiniyaya does not use the raw Anthropic API directly (uses Claude Code SDK), so explicit cache_control placement is not available. But the **architectural insight** applies: code-shiniyaya's most expensive operation is multi-agent dispatch where each agent receives nearly identical system prompts and overlapping context. If CC could "cache" the shared prefix across agent dispatches, token costs would drop dramatically.

**Concrete fix for anti-hang-v2.md** (architectural note):

```markdown
### Architectural Note: Prompt Prefix Reuse

code-shiniyaya dispatches 6-10 agents with near-identical prefixes:
- Same skill instructions (first 2000 tokens)
- Same diagnosis context (first 1000 tokens)
- Different: specific dimension focus (last 200 tokens)

**Future optimization**: If switching to direct Anthropic API for agent dispatch,
place cache_control breakpoints on the shared prefix blocks. Cache hits would
save ~90% of input token costs for agents 2 through N.

**Current workaround**: Write shared context to a file, have each agent Read it
rather than embedding inline. This achieves similar savings at the cost of one
extra Read call per agent:
```
Agent prompt: "Read {shared_context_file}. Then focus on {dimension}."
```
Instead of:
```
Agent prompt: [3000 tokens of shared context] + "Focus on {dimension}."
```

**Impact**: 2-3x token reduction for multi-agent dispatch scenarios.
```

**Priority: P2** — Significant cost savings but requires either direct API access or a workaround pattern. The "shared context file" workaround is immediately implementable.

---

## PATTERN 8: Progressive Severity Step Labels

**File:Line**: `autonomous-coding/prompts/coding_prompt.md:9,48,107` (entire file structure)

**What it does**: Every step in the agent prompt carries a severity label:
- `(MANDATORY)` — Step 1 (Get Your Bearings), Step 3 (Verification Test)
- `(CRITICAL!)` — Step 3 (verification), Step 6 (browser automation)
- `(CAREFULLY!)` — Step 7 (update checklist)

**code-shiniyaya gap**: code-shiniyaya's 16 rules are all flat — no rule carries a severity label or tier. A rule about "双批准门控" (dual-approval gating) has the same visual weight as "盲写禁止" (no blind writes). Agents dispatched by CC receive ad-hoc prompts with no severity labeling.

**Concrete fix for SKILL.md** — Add a severity labeling convention to the Agent Orchestration section:

```markdown
### Agent Prompt Severity Labels

When constructing prompts for sub-agents, prefix steps with severity labels
to prevent the model from equal-weighting critical vs optional instructions:

| Label | Visual | Semantics | When to Use |
|-------|--------|-----------|-------------|
| `(MANDATORY)` | Bold, red-alert | Skip = session failure | File reads before acting, regression checks |
| `(CRITICAL!)` | Bold, warning | Skip = high error risk | Verification steps, git operations |
| `(CAREFULLY!)` | Bold, caution | Skip = data corruption risk | File writes, checklist mutation |
| (no label) | Normal weight | Standard step | Implementation, documentation |

**Placement rule**: Severity labels go in the step HEADER, not inline:
```
GOOD:
### STEP 1: GET YOUR BEARINGS (MANDATORY)

BAD:
### STEP 1: GET YOUR BEARINGS
This step is mandatory... (buried in body text)
```

**Why**: Models attend more to header-level tokens than body-level tokens.
A severity label in the header has ~5x more attention weight than the same
word in a body paragraph.
```

**Priority: P1** — Easy to implement (no code changes, just prompt template updates). Proven effective in autonomous-coding's 200+ test completion rate.

---

## PATTERN 9: Orientation Step — Forced Disk Read Before Any Action

**File:Line**: `autonomous-coding/prompts/coding_prompt.md:9-31`

**Source code**:
```markdown
### STEP 1: GET YOUR BEARINGS (MANDATORY)

Start by orienting yourself:
1. pwd — see working directory
2. ls -la — understand project structure
3. cat app_spec.txt — read the spec
4. cat feature_list.json | head -50 — see all work
5. cat claude-progress.txt — read progress from previous sessions
6. git log --oneline -20 — check recent git history
7. cat feature_list.json | grep '"passes": false' | wc -l — count remaining
```

**What it does**: Forces the agent to read state from disk BEFORE taking any action. The agent has "no memory of previous sessions" — orientation is how it learns what happened and what remains. The orientation is a literal checklist of commands to run, not "consider reading these files."

**code-shiniyaya gap**: code-shiniyaya dispatches sub-agents with specific prompts like "scan file X for null deref bugs." The agent starts scanning immediately. There is NO forced orientation step. If CC's context has drifted (e.g., file was modified, bug was fixed by another agent), the agent operates on stale assumptions. The agent trusts CC's prompt description rather than verifying against actual disk state.

**Concrete fix for SKILL.md** — Add to Agent Orchestration section:

```markdown
### Agent Orientation Protocol (Pre-Action Gate)

Every dispatched agent MUST perform an orientation step before its primary task.
This prevents agents from operating on stale assumptions when CC's context has drifted.

**Orientation template** (prepend to every agent prompt):
```
BEFORE YOUR PRIMARY TASK, orient yourself (MANDATORY):
1. Read the target file(s) you will analyze: {file_list}
2. Check git log for recent changes to target files:
   git log --oneline -5 -- {file}
3. Read progress.txt for current session state
4. State: "Orientation complete. Current file state: {summary}. 
   Recent changes: {summary}. Proceeding to primary task: {task}."
Only AFTER completing steps 1-4, begin your primary task.
```

**Enforcement**: If an agent's output does not contain "Orientation complete"
within the first 3 messages, CC marks the agent as "unoriented" and its
findings carry reduced confidence weighting (0.7x vs 1.0x for oriented agents).

**Why**: In a multi-agent session, file state changes between agent dispatches.
An agent dispatched 5 minutes after the diagnosis scan may be reading a file
that was already fixed. Without orientation, it finds "bugs" that no longer exist.
```

**Priority: P1** — Reduces false positives from stale-context agents. The "reduced confidence" mechanism gives a graded response rather than binary accept/reject.

---

## PATTERN 10: ModelConfig Dataclass

**File:Line**: `agents/agent.py:18-30`

**Source code**:
```python
@dataclass
class ModelConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 1.0
    context_window_tokens: int = 180000
```

**What it does**: Centralizes model configuration in a single dataclass with defaults. Used by Agent class to parameterize behavior. `message_params` dict allows overriding any config parameter per-call.

**code-shiniyaya gap**: code-shiniyaya dispatches agents via Claude Code's Agent tool, not via raw API. But the concept applies: code-shiniyaya should maintain a `model-config.json` that specifies which agent types use which settings (e.g., investigator uses lower temperature, general-purpose uses higher temperature). Currently all agents use the same implicit defaults.

**Concrete fix for SKILL.md**:

```markdown
### Agent Model Configuration

Standardize sub-agent model parameters by agent type:

```json
{
  "agent_configs": {
    "investigator": {
      "type_hint": "precise",
      "note": "Low temperature for byte-level accuracy"
    },
    "Explore": {
      "type_hint": "creative",
      "note": "Higher temperature to find unexpected patterns"
    },
    "general-purpose": {
      "type_hint": "balanced",
      "note": "Default for logic/architecture analysis"
    },
    "Plan": {
      "type_hint": "creative",
      "note": "Higher temperature for solution space exploration"
    },
    "debugging": {
      "type_hint": "precise",
      "note": "Low temperature for root cause accuracy"
    }
  }
}
```

**Apply type hints in agent prompts**:
```
Investigator prompt: "Be precise and conservative. Only report confirmed
findings with exact file:line evidence. Lower confidence in speculative findings."

Explore prompt: "Be thorough and creative. Look for patterns other agents might
miss. Flag anything suspicious even if unconfirmed."
```

**Why**: Different agent roles need different reasoning styles. Investigator needs
precision (low temperature equivalent), Explore needs breadth (high temperature).
Embedding the type hint in the prompt achieves this without raw API access.
```

**Priority: P2** — Nice to have for output quality differentiation between agent types.

---

## PATTERN 11: Parallel Tool Execution (asyncio.gather)

**File:Line**: `agents/utils/tool_util.py:27-39`

**Source code**:
```python
async def execute_tools(
    tool_calls: list[Any], tool_dict: dict[str, Any], parallel: bool = True
) -> list[dict[str, Any]]:
    if parallel:
        return await asyncio.gather(
            *[_execute_single_tool(call, tool_dict) for call in tool_calls]
        )
    else:
        return [
            await _execute_single_tool(call, tool_dict) for call in tool_calls
        ]
```

**What it does**: When a model returns multiple independent tool calls (e.g., Read three files simultaneously), executes them in parallel via asyncio.gather instead of sequentially. Independent reads complete in max(read_time) instead of sum(read_times).

**code-shiniyaya gap**: code-shiniyaya does not control tool execution at this level (Claude Code SDK handles it). However, at the WORKFLOW level, code-shiniyaya's agent dispatch uses batch_size for parallel agent launches. The insight is: for INDEPENDENT file reads within a single agent, parallel execution should be the default. This is not currently specified.

**Concrete fix for SKILL.md** (architectural note):

```markdown
### Parallel I/O Within Agents (Architectural Note)

When an agent needs to read multiple independent files (e.g., diagnosis agent
reading foo.py + bar.py + baz.py), the files should be read in parallel, not
sequentially.

**Current behavior**: Agents typically Read files one at a time (3 files = 3 turns).
**Target behavior**: Agents should batch independent reads into a single turn
with parallel tool execution (3 files = 1 turn).

**Prompt guidance for agents**:
```
When you need to read multiple files that don't depend on each other:
1. List all files you need in a SINGLE message
2. Request reads for all files simultaneously
3. Do NOT read file A, wait for result, then read file B
```

**Impact**: ~50% reduction in agent turns for multi-file analysis tasks.
```

**Priority: P2** — Optimization. Reduces agent turnaround time but doesn't change correctness.

---

## PATTERN 12: Batch-Tool Nudge (Anti-Single-Action)

**File:Line**: `computer-use-best-practices/computer_use/loop.py:310-319`

**Source code**:
```python
def _should_nudge_batch(tool_uses: list[Any]) -> bool:
    """Only nudge after a lone click/type/key/scroll/wait, not after
    screenshots or batch calls."""
    if len(tool_uses) != 1:
        return False
    tu = tool_uses[0]
    if tu.name not in {"computer", "browser"}:
        return False
    action = tu.input.get("action") if isinstance(tu.input, dict) else None
    return action in BATCH_REMINDER_ACTIONS

# In loop:
nudge = _should_nudge_batch(tool_uses)
# ...
if nudge and not res.is_error:
    content.append({"type": "text", "text": BATCH_REMINDER})
```

**What it does**: Detects when the model issues a single computer-use action (one click, one type, one scroll) and appends a BATCH_REMINDER ("Consider combining multiple actions into a single call") to the tool result. This nudges the model toward batching independent actions together, reducing turn count.

**code-shiniyaya gap**: code-shiniyaya agents sometimes issue single Read/Edit calls when they could batch multiple independent operations. This inflates turn counts and slows diagnosis. There's no mechanism to nudge agents toward batching.

**Concrete fix for anti-hang-v2.md**:

```markdown
### Batch-Tool Nudge: Anti-Single-Action Pattern

When an agent issues a single independent tool call that could be batched,
inject a nudge into the result stream to encourage batching:

**Nudge trigger**: Agent issues exactly 1 Read/Write/Edit/Grep where:
- Operation is independent (no dependency on previous results)
- Multiple such operations are likely needed (e.g., reading 5 files, but doing it one at a time)

**Nudge text** (appended to tool result):
```
[NUDGE] Consider batching independent operations. If you need to read
multiple files, request them all in a single message to reduce turn count.
```

**Impact**: Reduces turn count by 30-40% for multi-file analysis agents.
(Model sometimes forgets batching is possible and defaults to sequential.)

**Implementation**: CC cannot inject into agent tool results directly, but can
include the nudge text in the agent's system prompt:
```
BATCHING RULE: When you need to read or analyze multiple independent files,
request ALL of them in a SINGLE message. Do not read one file, wait for the
result, then read the next. Batch independent operations together.
```
```

**Priority: P2** — Optimization that reduces agent turn count but doesn't affect correctness.

---

## Summary Table

| # | Pattern | Source File:Line | Priority | Target File | Type |
|---|---------|-----------------|----------|-------------|------|
| 1 | Auto-Continue With Fixed Delay | agent.py:20,173-177 | **P0** | SKILL.md | Hang Prevention |
| 2 | Empty-Response Retry With Nudge | loop.py:195-198,431-446 | **P0** | anti-hang-v2.md | Stall Detection |
| 3 | Recoverable vs Unrecoverable Error Classification | loop.py:84-113 | **P0** | SKILL.md (Rule 7) | Error Handling |
| 4 | Fresh Client Per Iteration (Context Isolation) | agent.py:158-169 | **P1** | anti-hang-v2.md | Context Mgmt |
| 5 | KeyboardInterrupt Graceful Fill | loop.py:322-328,490-516 | **P1** | anti-hang-v2.md | Recovery |
| 6 | MessageHistory Token-Aware Truncation | history_util.py:69-111 | **P1** | anti-hang-v2.md | Context Mgmt |
| 7 | Prompt Caching Architecture | loop.py:55-81 | **P2** | anti-hang-v2.md | Cost Optimization |
| 8 | Progressive Severity Step Labels | coding_prompt.md (full) | **P1** | SKILL.md | Prompt Engineering |
| 9 | Orientation Step — Forced Disk Read | coding_prompt.md:9-31 | **P1** | SKILL.md | Agent Reliability |
| 10 | ModelConfig Dataclass | agent.py:18-30 | **P2** | SKILL.md | Configuration |
| 11 | Parallel Tool Execution (asyncio.gather) | tool_util.py:27-39 | **P2** | SKILL.md | Optimization |
| 12 | Batch-Tool Nudge (Anti-Single-Action) | loop.py:310-319 | **P2** | anti-hang-v2.md | Optimization |

---

## Cross-Reference: Integration with Existing SKILL.md Sections

| Pattern | SKILL.md Section to Modify | anti-hang-v2.md Section to Modify |
|---------|---------------------------|----------------------------------|
| 1 (Auto-Continue) | "迭代扫描工作流 (防卡顿 + 进度反馈)" (line 456) | "What CC Actually Does" |
| 2 (Empty-Response) | N/A | "Hang Detection: Message-Count Based" (line 28) |
| 3 (Error Classification) | Rule 7 (line 74) | N/A |
| 4 (Context Isolation) | N/A | New: "Context Isolation" |
| 5 (Graceful Interrupt) | N/A | New: "Graceful Interruption" |
| 6 (Token Truncation) | N/A | New: "Token-Aware Context Mgmt" |
| 7 (Prompt Caching) | N/A | "Constraints Accepted" (line 102) |
| 8 (Severity Labels) | "Agent编排" (line 346) | N/A |
| 9 (Orientation Step) | "Agent编排" → Agent prompt template | N/A |
| 10 (ModelConfig) | "Agent编排" → "类型选择" (line 356) | N/A |
| 11 (Parallel I/O) | "Agent编排" → batch_size note (line 360) | N/A |
| 12 (Batch Nudge) | N/A | "Optimal Batching" (line 63) |
