# Autonomous Coding Tool Patterns — Deep Scan Findings

**Date**: 2026-07-16
**Source**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src`
**Target files**: SKILL.md (v3.7.0), anti-hang-v2.md (v2.1), high-impact-patterns.md
**Dimension**: Tool patterns — ThinkTool, parallel execution with error isolation, tool collection dispatch, Base Tool class with to_dict serialization
**Method**: File-by-file deep read of all agents/tools/*, agents/utils/*, browser_use_demo/tools/*, autonomous-coding/*

---

## Overview

The autonomous-coding project implements a **tool abstraction layer** entirely absent from code-shiniyaya.
code-shiniyaya dispatches sub-agents procedurally through a 7-step workflow with ad-hoc descriptions.
autonomous-coding defines tools as structured objects with serialization, dispatch, error isolation,
and lifecycle management. This document identifies 10 patterns code-shiniyaya currently lacks.

Existing `autonomous-coding-gap-analysis.md` covers 7 dimensions (Init+Loop model, Immutable Checklist,
ThinkTool, Trajectory Recording, Error Recovery, Safety, Prompt Structure) but misses the
**tool infrastructure layer** — the actual mechanisms for dispatching, isolating, serializing,
and managing sub-agent tool capabilities.

---

## Pattern 1: Parallel Tool Execution with Per-Tool Error Isolation

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\utils\tool_util.py:7-39`

```python
async def _execute_single_tool(
    call: Any, tool_dict: dict[str, Any]
) -> dict[str, Any]:
    """Execute a single tool and handle errors."""
    response = {"type": "tool_result", "tool_use_id": call.id}

    try:
        # Execute the tool directly
        result = await tool_dict[call.name].execute(**call.input)
        response["content"] = str(result)
    except KeyError:
        response["content"] = f"Tool '{call.name}' not found"
        response["is_error"] = True
    except Exception as e:
        response["content"] = f"Error executing tool: {str(e)}"
        response["is_error"] = True

    return response


async def execute_tools(
    tool_calls: list[Any], tool_dict: dict[str, Any], parallel: bool = True
) -> list[dict[str, Any]]:
    """Execute multiple tools sequentially or in parallel."""

    if parallel:
        return await asyncio.gather(
            *[_execute_single_tool(call, tool_dict) for call in tool_calls]
        )
    else:
        return [
            await _execute_single_tool(call, tool_dict) for call in tool_calls
        ]
```

### What This Is

Each tool execution is wrapped in its own try/except so **one failing tool never blocks other tools from reporting results**. Parallel execution via `asyncio.gather` allows all tools to run simultaneously while each maintains independent error handling.

### code-shiniyaya Gap

When CC dispatches multiple sub-agents in STEP 1 (6+ agents) or STEP 4 (10+ agents), all agents are launched in parallel but there is **no per-agent error isolation wrapper**. SKILL.md Rule 7 says "Agent异常终止或挂起→替换, 每槽位最多2次" but this is a CC-side manual process, not an automated isolation mechanism. If one agent hangs, CC must manually detect and replace it — there is no `_execute_single_agent()` wrapper that catches exceptions and returns partial results for the remaining agents.

Additionally, code-shiniyaya has no `parallel` vs `sequential` mode switch. All agents are launched in parallel batches always. The autonomous-coding pattern supports both modes with a simple boolean parameter, enabling sequential execution when shared-file dependencies exist (Rule 8).

### Concrete Fix

**Add to anti-hang-v2.md**, under the Agent Selection Matrix section:

```markdown
## Per-Agent Error Isolation Wrapper

### Problem
When dispatching N agents in parallel, one agent's crash/exception can block
CC from receiving results from the other N-1 agents. The current approach
(manual detection + replacement per Rule 7) is slow and lossy.

### Solution: Wrapped Agent Dispatch

When launching parallel sub-agents, wrap each dispatch in an isolation layer:

```
async def dispatch_agent_isolated(agent_spec, slot_id):
    """Execute one agent; failure never blocks other agents."""
    try:
        result = await launch_sub_agent(agent_spec)
        return {"slot": slot_id, "status": "completed", "result": result}
    except AgentNotFoundError:
        # Agent type unavailable — use fallback chain
        fallback = get_fallback_agent(agent_spec.type)
        try:
            result = await launch_sub_agent(fallback)
            return {"slot": slot_id, "status": "fallback", "result": result}
        except Exception as e:
            return {"slot": slot_id, "status": "failed", "error": str(e)}
    except TimeoutError:
        return {"slot": slot_id, "status": "timeout", "error": "Agent exceeded time limit"}
    except Exception as e:
        return {"slot": slot_id, "status": "failed", "error": str(e)}

# Dispatch: all agents run, errors don't cascade
results = await gather_all([dispatch_agent_isolated(spec, i) for i, spec in enumerate(agent_specs)])

# Report: successes separate from failures
completed = [r for r in results if r["status"] in ("completed", "fallback")]
failed    = [r for r in results if r["status"] in ("failed", "timeout")]
```

### Key Properties
1. **Failure isolation**: One agent crash = one error entry, not a batch abort
2. **Fallback chain integrated**: Type-unavailable automatically triggers fallback (investigator→Explore→general-purpose)
3. **Structured result**: Every slot returns `{slot, status, result/error}` regardless of outcome
4. **No silent loss**: Failed slots are explicitly listed, not silently missing from output
5. **Parallel + sequential modes**: `gather_all()` = parallel; `dispatch_sequential()` = serial for shared-file cases

### Integration with Existing Rules
- Rule 7 (failed agent replacement): `_execute_single_agent` catches the first failure,
  triggers fallback chain internally, reports both attempts
- Rule 5 (batch_size): `gather_all` respects batch_size ceiling via chunking
- Rule 12 (3x same-file failure): Failed slot count per file tracked across isolation wrappers
```

**Priority: P0** — This is the single highest-impact tool pattern. Without per-agent error isolation, code-shiniyaya's multi-agent reliability is fundamentally limited. Every parallel dispatch currently risks losing results from N-1 agents when 1 agent fails.

---

## Pattern 2: Base Tool Class with to_dict Serialization

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\tools\base.py:7-27`

```python
@dataclass
class Tool:
    """Base class for all agent tools."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert tool to Claude API format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    async def execute(self, **kwargs) -> str:
        """Execute the tool with provided parameters."""
        raise NotImplementedError(
            "Tool subclasses must implement execute method"
        )
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\browser-use-demo\browser_use_demo\tools\base.py:8-70`

```python
class BaseAnthropicTool(metaclass=ABCMeta):
    """Abstract base class for Anthropic-defined tools."""

    @abstractmethod
    def __call__(self, **kwargs) -> Any:
        """Executes the tool with the given arguments."""
        ...

    @abstractmethod
    def to_params(self) -> BetaToolUnionParam:
        raise NotImplementedError


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""
    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None

    def __bool__(self):
        return any(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: "ToolResult"):
        # Combines two ToolResults by concatenating fields
        ...

    def replace(self, **kwargs):
        """Returns a new ToolResult with the given fields replaced."""
        return replace(self, **kwargs)


class ToolError(Exception):
    """Raised when a tool encounters an error."""
    def __init__(self, message):
        self.message = message
```

### What This Is

A structured, serializable type system for tool capabilities. Every tool has:
1. **Structured identity** (name, description, input_schema) — not ad-hoc text
2. **Standard serialization** (to_dict/to_params) — converts to API format in one call
3. **Typed results** (ToolResult with output/error/base64_image/system fields) — not raw strings
4. **Typed errors** (ToolError) — distinguishable from generic exceptions
5. **Composability** (ToolResult.__add__, ToolResult.replace) — results can be merged

The browser-use-demo extends this with `ToolFailure`, `CLIResult` — result types carry semantics, not just data.

### code-shiniyaya Gap

code-shiniyaya's agent types are described in a Markdown table (SKILL.md lines 347-359):

```markdown
| 阶段 | 最少 | 类型 | 说明 |
|------|------|------|------|
| 诊断 | 6+ | Inv+Exp+GP+Plan+Debug(5类型) | 并行, 5+维度 |
```

These are **prose descriptions**, not structured objects. There is no:
1. **Serialization format**: How does CC convert "investigator" into a sub-agent prompt? No `to_dict()` or `to_prompt()` method exists.
2. **Input schema**: What parameters does each agent type accept? What does it return? Undefined.
3. **Result typing**: Agent results are unstructured text. No `ToolResult` equivalent with typed fields.
4. **Error typing**: Agent failures are ad-hoc. No `AgentError` type hierarchy.
5. **Composability**: Cannot merge results from multiple agents programmatically — done manually in the "去重合并" step.

### Concrete Fix

**Add to SKILL.md**, under the Agent Orchestration table (after line 359):

```markdown
## Agent Type Schema (Structured, Serializable)

Each agent type MUST be defined as a structured object, not prose:

```python
@dataclass
class AgentType:
    """Structured definition of a sub-agent type."""
    name: str                    # e.g., "investigator"
    description: str             # What this agent does
    input_schema: dict           # Parameters it accepts (JSON Schema)
    output_schema: dict          # What it returns (JSON Schema)
    system_prompt_template: str  # Template with {placeholders}
    fallback_chain: list[str]    # Ordered fallback types
    timeout_ms: int              # Max execution time
    max_retries: int             # Per-slot retry limit

    def to_prompt(self, **kwargs) -> str:
        """Serialize to a complete agent prompt with filled parameters."""
        return self.system_prompt_template.format(**kwargs)

    def to_dict(self) -> dict:
        """Serialize for logging/dispatch."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


@dataclass
class AgentResult:
    """Typed result from a sub-agent execution."""
    slot_id: str
    agent_type: str
    status: Literal["completed", "fallback", "timeout", "failed"]
    findings: list[dict]   # Each: {file, line, severity, grounding, evidence}
    errors: list[str]
    fallback_used: bool
    fallback_type: str | None

    def merge(self, other: "AgentResult") -> "AgentResult":
        """Merge two agent results (for dedup)."""
        # Combine findings, deduplicate by file:line±3, keep highest severity
        ...

    @property
    def is_success(self) -> bool:
        return self.status in ("completed", "fallback") and not self.errors
```

### Agent Type Definitions (Replaces current table)

| Type | Description | Input Schema | Output Schema | Timeout | Fallback |
|------|-------------|-------------|---------------|---------|----------|
| investigator | Byte-level code scan | `{files: [str], scan_depth: int}` | `AgentResult` | 300s | general-purpose |
| explore | Coverage gap detection | `{files: [str], reference_sources: [str]}` | `AgentResult` | 600s | general-purpose |
| general-purpose | Logic + syntax analysis | `{task: str, files: [str]}` | `AgentResult` | 600s | (terminal fallback) |
| plan | Architecture review | `{files: [str], architecture_docs: [str]}` | `AgentResult` | 600s | general-purpose |
| debugging | Runtime analysis | `{test_command: str, files: [str]}` | `AgentResult` | 600s | general-purpose |
| cavecrew-builder | Code modification | `{task: str, files: [str], old: str, new: str}` | `AgentResult` | 300s | general-purpose |
| cavecrew-reviewer | Diff review | `{diff: str, files: [str]}` | `AgentResult` | 300s | general-purpose |
```

### Key Benefits
1. **API-format dispatch**: `[agent.to_dict() for agent in self.agents]` replaces ad-hoc prompt construction
2. **Typed results enable programmatic dedup**: `result1.merge(result2)` instead of manual prose merging
3. **Fallback chain is data, not prose**: `agent.fallback_chain` is machine-readable, not "investigator→Explore→general-purpose(通用回退)"
4. **Testable**: Each agent type's to_prompt() output can be validated against expected templates
```

**Priority: P0** — Without structured agent type definitions, code-shiniyaya cannot programmatically dispatch, merge, or validate agent results. The current prose-based approach makes every dispatch a manual string-construction exercise.

---

## Pattern 3: Tool Collection with Name-Indexed Dispatch

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\browser-use-demo\browser_use_demo\tools\collection.py:8-17`

```python
class ToolCollection:
    """Collection of tools for browser automation."""

    def __init__(self, *tools: BaseAnthropicTool):
        self.tools = tools
        self.tool_map = {tool.name: tool for tool in tools}

    def to_params(self) -> list[BetaToolUnionParam]:
        """Convert all tools to API parameters."""
        return [tool.to_params() for tool in self.tools]
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\browser-use-demo\browser_use_demo\message_handler.py:82-131`

```python
async def execute_tools(
    self,
    tool_uses: list[dict[str, Any]],
    tool_collection: ToolCollection,
    tool_output_callback: Optional[Callable[[ToolResult, str], None]] = None
) -> list[BetaToolResultBlockParam]:
    """Execute tools and collect results."""
    tool_results = []

    for tool_use in tool_uses:
        tool_id = tool_use["id"]
        tool_name = tool_use["name"]
        tool_input = tool_use["input"]

        try:
            tool = tool_collection.tool_map.get(tool_name)
            if not tool:
                raise ValueError(f"Unknown tool: {tool_name}")

            result = await tool(**tool_input)

            if tool_output_callback:
                tool_output_callback(result, tool_id)

            tool_result = self._build_tool_result(result, tool_id)
            tool_results.append(tool_result)

        except Exception as e:
            error_result = BetaToolResultBlockParam(
                type="tool_result",
                tool_use_id=tool_id,
                is_error=True,
                content=[{"type": "text", "text": str(e)}]
            )
            tool_results.append(error_result)
```

### What This Is

A **collection** is:
1. An ordered container of tool instances
2. A name-indexed **dispatch map** (`tool_map`) for O(1) lookup
3. A single-point **serializer** (`to_params()`) that converts everything to API format
4. The dispatch loop iterates tool_use blocks, looks up by name, calls `tool(**input)`, collects results

This is the **two-layer dispatch pattern**: Collection holds tools, dispatch loop routes calls to tools. The browser-use-demo's `message_handler.py` adds result building (`_build_tool_result`) with typed ToolResult → BetaToolResultBlockParam conversion.

### code-shiniyaya Gap

code-shiniyaya has an "agent type" concept but **no collection abstraction**. The agent types are listed in a Markdown table (lines 347-359) and dispatched by CC reading the table and constructing prompts. There is no:

1. **AgentCollection**: A container holding all available agent types with name-indexed lookup
2. **to_prompts()**: Single-call serialization of all agent definitions to dispatch-ready prompts
3. **Agent dispatch loop**: A reusable loop that routes tasks to agent types by name
4. **Result collection**: Standardized collection of typed AgentResult objects from multiple agents

This means every STEP 1/4 dispatch requires CC to:
- Manually decide which agent types to use
- Construct prompts for each
- Track which agents returned
- Manually merge results

Replaceable with: `agent_collection.to_prompts(task)` → dispatch → `collect_results()`.

### Concrete Fix

**Add to SKILL.md**, after the new Agent Type Schema section:

```markdown
## Agent Collection — Name-Indexed Dispatch

### Problem
Currently, each agent dispatch batch requires CC to manually select types,
construct prompts, track completion, and merge results. This is repetitive
and error-prone.

### Solution: AgentCollection Pattern

```python
class AgentCollection:
    """Collection of available agent types with name-indexed dispatch."""

    def __init__(self, *agent_types: AgentType):
        self.agent_types = list(agent_types)
        self.agent_map = {at.name: at for at in agent_types}

    def get(self, name: str) -> AgentType | None:
        """O(1) lookup by agent type name."""
        return self.agent_map.get(name)

    def dispatch_all(self, task_spec: dict) -> list[AgentType]:
        """Select agent types relevant to this task."""
        # Returns agents whose input_schema matches the task
        return [at for at in self.agent_types
                if self._matches(task_spec, at.input_schema)]

    def to_dispatch_specs(self, task_spec: dict, files: list[str]) -> list[dict]:
        """Convert selected agents to dispatch-ready specifications."""
        selected = self.dispatch_all(task_spec)
        return [
            {
                "agent_type": at.name,
                "prompt": at.to_prompt(files=files, task=task_spec),
                "timeout_ms": at.timeout_ms,
                "fallback_chain": at.fallback_chain,
            }
            for at in selected
        ]


# Usage in STEP 1 (Diagnosis):
collection = AgentCollection(
    investigator,
    explore,
    general_purpose,
    plan,
    debugging,
)

dispatch_specs = collection.to_dispatch_specs(
    task_spec={"goal": "diagnose", "files": bug_files},
    files=bug_files,
)

# All agents dispatched with uniform spec format
results = await dispatch_parallel(dispatch_specs)

# Collect and merge results by type
merged = AgentResult.merge_all(results)
```

### Integration with Current Workflow

| Current (Manual) | New (Collection-based) |
|-----------------|----------------------|
| CC reads table, picks types | `collection.dispatch_all(task_spec)` |
| CC constructs prompts per agent | `agent.to_prompt(files=..., task=...)` |
| CC tracks which returned | `results = await dispatch_parallel(specs)` — all tracked |
| CC manually merges results | `AgentResult.merge_all(results)` |
```

**Priority: P1** — The collection pattern simplifies agent dispatch significantly, but is layered on top of the Base Tool class (Pattern 2). Implement after Pattern 2.

---

## Pattern 4: Agent Loop with tool_dict Dispatch

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\agent.py:96-155`

```python
async def _agent_loop(self, user_input: str) -> list[dict[str, Any]]:
    """Process user input and handle tool calls in a loop"""
    if self.verbose:
        print(f"\n[{self.name}] Received: {user_input}")
    await self.history.add_message("user", user_input, None)

    tool_dict = {tool.name: tool for tool in self.tools}

    while True:
        self.history.truncate()
        params = self._prepare_message_params()

        # Merge headers
        default_headers = {"anthropic-beta": "code-execution-2025-05-22"}
        if "extra_headers" in params:
            custom_headers = params.pop("extra_headers")
            merged_headers = {**default_headers, **custom_headers}
        else:
            merged_headers = default_headers

        response = self.client.messages.create(
            **params,
            extra_headers=merged_headers
        )
        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]

        # Verbose logging per content block
        if self.verbose:
            for block in response.content:
                if block.type == "text":
                    print(f"\n[{self.name}] Output: {block.text}")
                elif block.type == "tool_use":
                    params_str = ", ".join(
                        [f"{k}={v}" for k, v in block.input.items()]
                    )
                    print(
                        f"\n[{self.name}] Tool call: "
                        f"{block.name}({params_str})"
                    )

        await self.history.add_message(
            "assistant", response.content, response.usage
        )

        if tool_calls:
            tool_results = await execute_tools(
                tool_calls,
                tool_dict,
            )
            if self.verbose:
                for block in tool_results:
                    print(
                        f"\n[{self.name}] Tool result: "
                        f"{block.get('content')}"
                    )
            await self.history.add_message("user", tool_results)
        else:
            return response
```

### What This Is

This is the **canonical agent loop pattern**: a `while True` that alternates between API calls and tool execution until the model produces a text-only response (no more tool calls). Key mechanisms:

1. **tool_dict pre-built**: `{tool.name: tool for tool in self.tools}` — built ONCE before the loop, O(1) lookup
2. **truncate() on every iteration**: Before each API call, check context window and truncate if needed
3. **Header merging**: Default headers merged with custom headers (defense-in-depth for API params)
4. **Structured response parsing**: Extract tool_use blocks explicitly; text blocks are logged
5. **History append on every turn**: Assistant response + tool results both appended to MessageHistory
6. **Natural termination**: When the model returns text-only (no tool_use blocks), the loop exits
7. **Verbose mode**: Per-block logging for debugging without changing the loop structure

### code-shiniyaya Gap

code-shiniyaya's 7-step workflow is **procedural, not loop-based**. Each step is a linear sequence:

```
STEP 0 → STEP 1 → STEP 2 → ... → STEP 7
```

There is no concept of a **dispatch loop** where:
- Agents are dispatched
- Results collected
- New agents dispatched based on results
- Loop continues until a termination condition

The closest equivalent is the iteration scanning workflow (SKILL.md lines 456-479), which describes a `log()`-based progress loop. But this is CC-orchestrated at the meta level, not a reusable loop pattern for individual agent dispatch.

Specifically missing:
1. **No while-True dispatch loop**: Agents run once and CC waits. There's no "dispatch → collect → decide if more → dispatch again" pattern.
2. **No built-once dispatch map**: Agent types are looked up from a Markdown table, not from a pre-built `agent_map` dict.
3. **No per-turn truncation**: No proactive context management during agent execution.
4. **No natural termination condition**: The loop ends when the model produces no more tool calls. code-shiniyaya has explicit step boundaries instead.

### Concrete Fix

**Add to anti-hang-v2.md**, after the Agent Selection Matrix:

```markdown
## Agent Dispatch Loop Pattern (from agent.py _agent_loop)

### Pattern
Instead of dispatching all agents at once and waiting, use a loop:

```
while not termination_condition:
    1. truncate context (prevent overflow)
    2. dispatch agent(s) with current prompt + history
    3. collect results
    4. append to history
    5. check if more work needed
        → yes: build next prompt from results, continue
        → no: return collected results
```

### code-shiniyaya Adaptation

For STEP 1 (diagnosis), use a dispatch loop instead of single-batch:

```
# Build agent dispatch map ONCE
agent_map = {
    "investigator": investigator_agent,
    "explore": explore_agent,
    "general-purpose": general_purpose_agent,
    "plan": plan_agent,
    "debugging": debugging_agent,
}

# Dispatch loop
findings = []
dispatched_types = set()

while len(findings) < target_coverage:
    # Choose next agent type not yet dispatched
    next_type = pick_next_agent_type(dispatched_types, findings)
    if next_type is None:
        break  # All types exhausted or coverage sufficient

    # Truncate if needed (prevent context overflow)
    truncate_context_if_needed()

    # Dispatch
    result = await dispatch_agent_isolated(
        agent_map[next_type],
        slot_id=next_type,
    )

    # Collect
    dispatched_types.add(next_type)
    if result.status in ("completed", "fallback"):
        findings.extend(result.findings)

    # Deduplicate and check coverage
    findings = deduplicate(findings)
    if coverage_sufficient(findings):
        break

return findings
```

### Why This Is Better Than Single-Batch

| Aspect | Single-Batch (Current) | Dispatch Loop |
|--------|----------------------|---------------|
| Agent selection | All at once (blind) | Adaptive (based on findings so far) |
| Context pressure | All agents loaded simultaneously | One at a time, truncated between |
| Error recovery | Full batch restart | Single agent retry |
| Coverage | Guess at start | Check after each agent, stop when sufficient |
| Termination | Fixed batch size | Natural (coverage-based) |
```

**Priority: P0** — The dispatch loop pattern fundamentally improves agent orchestration by making it adaptive rather than fixed-batch. This directly addresses the stall/hang problems described in anti-hang-v2.md.

---

## Pattern 5: Token-Aware Context Truncation

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\utils\history_util.py:69-111`

```python
def truncate(self) -> None:
    """Remove oldest messages when context window limit is exceeded."""
    if self.total_tokens <= self.context_window_tokens:
        return

    TRUNCATION_NOTICE_TOKENS = 25
    TRUNCATION_MESSAGE = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "[Earlier history has been truncated.]",
            }
        ],
    }

    def remove_message_pair():
        self.messages.pop(0)
        self.messages.pop(0)

        if self.message_tokens:
            input_tokens, output_tokens = self.message_tokens.pop(0)
            self.total_tokens -= input_tokens + output_tokens

    while (
        self.message_tokens
        and len(self.messages) >= 2
        and self.total_tokens > self.context_window_tokens
    ):
        remove_message_pair()

        if self.messages and self.message_tokens:
            original_input_tokens, original_output_tokens = (
                self.message_tokens[0]
            )
            self.messages[0] = TRUNCATION_MESSAGE
            self.message_tokens[0] = (
                TRUNCATION_NOTICE_TOKENS,
                original_output_tokens,
            )
            self.total_tokens += (
                TRUNCATION_NOTICE_TOKENS - original_input_tokens
            )
```

### What This Is

A **sliding-window truncation** that:
1. Tracks cumulative token count across all message pairs
2. When total exceeds `context_window_tokens`, removes oldest user+assistant pairs
3. Injects a `[Earlier history has been truncated.]` notice so the model knows context was lost
4. Updates token counts after truncation (subtracts removed, adds truncation notice tokens)
5. Uses the actual Anthropic token counting API for accuracy (with character-count fallback)

### code-shiniyaya Gap

code-shiniyaya has NO proactive context truncation mechanism. The SKILL.md mentions token limits only for OUTPUT formatting (STEP 3: ">10000 tokens → N部分, P0优先, ≤8000/部分"). There is no mechanism to:

1. **Track context usage** during agent execution
2. **Detect approaching overflow** before it happens
3. **Truncate oldest messages** to free context space
4. **Notify the agent** that truncation occurred

Without this, agents can silently hit context limits, producing truncated or broken output with no warning. The current approach relies entirely on the model/API to handle overflow, which is unreliable.

### Concrete Fix

**Add to anti-hang-v2.md**, under the Token-Aware Truncation section from the existing gap analysis (expand it with the exact mechanism):

```markdown
## Token-Aware Context Truncation — Exact Mechanism

### Tracking

Before dispatching a sub-agent, estimate initial tokens:
```python
system_tokens = estimate_tokens(system_prompt)  # ~chars/4 fallback
total_tokens = system_tokens
message_tokens = []  # List of (input_tokens, output_tokens) per turn
```

After each assistant response:
```python
if response.usage:
    turn_input = response.usage.input_tokens - total_tokens
    turn_output = response.usage.output_tokens
    message_tokens.append((turn_input, turn_output))
    total_tokens += turn_input + turn_output
```

### Truncation Trigger

On every loop iteration (BEFORE dispatching):
```python
def truncate_if_needed():
    if total_tokens <= context_window_tokens:
        return  # Under limit, no action

    while total_tokens > context_window_tokens and len(messages) >= 2:
        # Remove oldest user+assistant pair
        messages.pop(0)  # user
        messages.pop(0)  # assistant
        if message_tokens:
            in_tok, out_tok = message_tokens.pop(0)
            total_tokens -= in_tok + out_tok

    # Inject truncation notice as first message
    if messages:
        messages[0] = {
            "role": "user",
            "content": "[Earlier history has been truncated.]"
        }
        # Adjust token count for the much shorter truncation notice
```

### Integration with code-shiniyaya Agent Dispatch

All parallel agent dispatches MUST call `truncate_if_needed()` before launch.
All sequential agent dispatches MUST call `truncate_if_needed()` between agents.

### Why This Prevents Silent Failures

Without truncation:
- Agent accumulates context across turns
- Hits context window limit
- API returns truncated/broken response
- CC receives partial output, can't distinguish truncation from other errors

With truncation:
- Agent proactively frees space before overflow
- Injects notice so model knows context was lost
- Model can request re-reading of truncated content if needed
- CC never receives silently-truncated output
```

**Priority: P0** — Context overflow causes silent, hard-to-detect agent failures (partial output that looks valid). This pattern prevents the entire class of context-overflow bugs.

---

## Pattern 6: Message History with Prompt Caching

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\utils\history_util.py:113-124`

```python
def format_for_api(self) -> list[dict[str, Any]]:
    """Format messages for Claude API with optional caching."""
    result = [
        {"role": m["role"], "content": m["content"]} for m in self.messages
    ]

    if self.enable_caching and self.messages:
        result[-1]["content"] = [
            {**block, "cache_control": {"type": "ephemeral"}}
            for block in self.messages[-1]["content"]
        ]
    return result
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\browser-use-demo\browser_use_demo\loop.py:116-123`

```python
if enable_prompt_caching:
    betas.append(PROMPT_CACHING_BETA_FLAG)
    # Add cache control to system prompt
    system = BetaTextBlockParam(
        type="text",
        text=system["text"],
        cache_control=BetaCacheControlEphemeralParam(type="ephemeral"),
    )
```

### What This Is

Prompt caching marks the **system prompt** and **last message's content blocks** with `cache_control: {type: "ephemeral"}`. This tells the Claude API to cache these blocks, so repeated API calls with identical system prompts and similar conversation prefixes are significantly cheaper and faster. The `betas` list includes the `"prompt-caching-2024-07-31"` flag to enable the feature.

### code-shiniyaya Gap

code-shiniyaya dispatches sub-agents with identical or near-identical system prompts. For example, all 6 agents in STEP 1 share the same core instructions plus type-specific additions. Without prompt caching:
- Each sub-agent API call re-processes the entire system prompt
- Token costs are duplicated across parallel agents
- Latency is higher for repeated calls

The SKILL.md has no mention of prompt caching as an optimization, and no mechanism to add `cache_control` to agent prompts.

### Concrete Fix

**Add to anti-hang-v2.md**, under a new `## Prompt Caching for Repeated Agent Dispatches` section:

```markdown
## Prompt Caching for Repeated Agent Dispatches

### When to Use
When dispatching multiple agents with the same or similar system prompts,
cache the shared portion to reduce cost and latency:

1. **System prompt**: Identical across all agents → cache once
2. **Shared instruction blocks**: e.g., "You are an agent in the code-shiniyaya framework..." → cache
3. **Reference documents**: Source files read by multiple agents → cache

### How to Apply

For sub-agents dispatched through the Claude API:
```python
# In _prepare_message_params():
system_prompt_with_cache = {
    "type": "text",
    "text": system_prompt,
    "cache_control": {"type": "ephemeral"}  # <-- Mark for caching
}

# In API call:
response = client.beta.messages.create(
    model=model,
    system=[system_prompt_with_cache],
    messages=messages,
    betas=["prompt-caching-2024-07-31"],  # <-- Enable caching beta
    ...
)
```

### Cost Impact
For STEP 1 (6 agents sharing the same code-shiniyaya system prompt):
- Without caching: 6 × full system prompt tokens charged
- With caching: 1 × system prompt tokens charged (cached), 5 × cache-read (90% discount)
- Typical savings: ~45-60% on system prompt tokens for parallel batches

### Where NOT to Use
- Single-agent dispatch (no reuse benefit)
- Per-agent prompts that are all different (no shared content to cache)
```

**Priority: P1** — Cost optimization for parallel agent dispatches. Important for production use but not a correctness issue.

---

## Pattern 7: Fresh-Context Tool Initialization with AsyncExitStack

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\agent.py:157-169`

```python
async def run_async(self, user_input: str) -> list[dict[str, Any]]:
    """Run agent with MCP tools asynchronously."""
    async with AsyncExitStack() as stack:
        original_tools = list(self.tools)

        try:
            mcp_tools = await setup_mcp_connections(
                self.mcp_servers, stack
            )
            self.tools.extend(mcp_tools)
            return await self._agent_loop(user_input)
        finally:
            self.tools = original_tools
```

### What This Is

A resource lifecycle pattern using Python's `AsyncExitStack`:
1. **Save original state**: `original_tools = list(self.tools)`
2. **Initialize dynamic resources**: `mcp_tools = await setup_mcp_connections(...)`
3. **Extend capabilities**: `self.tools.extend(mcp_tools)`
4. **Always restore on exit**: `finally: self.tools = original_tools`

This ensures that MCP tools loaded for one session don't leak into the next session. The `AsyncExitStack` handles cleanup of all async context managers (MCP connections) regardless of whether the agent loop succeeds or fails.

### code-shiniyaya Gap

code-shiniyaya has no resource lifecycle management for agent sessions. When CC dispatches sub-agents:
1. **No save/restore pattern**: Agent state isn't isolated between dispatches
2. **No AsyncExitStack equivalent**: No guaranteed cleanup of resources
3. **No dynamic capability loading**: All agent capabilities are fixed at dispatch time

This means if an agent loads a reference file or establishes a connection, that state can persist into the next agent dispatch without explicit cleanup.

### Concrete Fix

**Add to anti-hang-v2.md**, after the dispatch loop section:

```markdown
## Agent Resource Lifecycle (AsyncExitStack Pattern)

### Problem
When dispatching agents with dynamic resources (loaded reference files,
MCP connections, temporary workspaces), those resources can leak across
dispatch boundaries without explicit cleanup.

### Solution: Save/Restore Pattern

```
# Save original state
original_files = list(agent.loaded_files)
original_context = dict(agent.context)

try:
    # Load dynamic resources for this dispatch
    ref_files = await load_reference_sources(task.reference_sources)
    agent.loaded_files.extend(ref_files)

    # Execute
    result = await agent.execute(task)

    return result

finally:
    # ALWAYS restore original state (even if execute() raised)
    agent.loaded_files = original_files
    agent.context = original_context
    # Cleanup temp files
    for f in ref_files:
        if f.is_temp:
            os.remove(f.path)
```

### Integration with Agent Dispatch

Before each sub-agent dispatch:
1. Snapshot agent state (files, context, connections)
2. Load task-specific resources
3. Execute agent
4. Restore snapshot (in finally block)

This prevents:
- Reference file accumulation across dispatches (context bloat)
- Stale connection leakage (memory/resource leak)
- Cross-task state contamination (Agent B sees Agent A's files)
```

**Priority: P1** — Important for long-running multi-agent sessions but can be retrofitted incrementally.

---

## Pattern 8: MCP Tool Integration (Connection Factory + Dynamic Loading)

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\utils\connections.py:93-150`

```python
def create_mcp_connection(config: dict[str, Any]) -> MCPConnection:
    """Factory function to create the appropriate MCP connection."""
    conn_type = config.get("type", "stdio").lower()

    if conn_type == "stdio":
        if not config.get("command"):
            raise ValueError("Command is required for STDIO connections")
        return MCPConnectionStdio(
            command=config["command"],
            args=config.get("args"),
            env=config.get("env"),
        )
    elif conn_type == "sse":
        if not config.get("url"):
            raise ValueError("URL is required for SSE connections")
        return MCPConnectionSSE(
            url=config["url"], headers=config.get("headers")
        )
    else:
        raise ValueError(f"Unsupported connection type: {conn_type}")


async def setup_mcp_connections(
    mcp_servers: list[dict[str, Any]] | None,
    stack: AsyncExitStack,
) -> list[MCPTool]:
    """Set up MCP server connections and create tool interfaces."""
    if not mcp_servers:
        return []

    mcp_tools = []
    for config in mcp_servers:
        try:
            connection = create_mcp_connection(config)
            await stack.enter_async_context(connection)
            tool_definitions = await connection.list_tools()

            for tool_info in tool_definitions:
                mcp_tools.append(
                    MCPTool(
                        name=tool_info.name,
                        description=tool_info.description
                        or f"MCP tool: {tool_info.name}",
                        input_schema=tool_info.inputSchema,
                        connection=connection,
                    )
                )
        except Exception as e:
            print(f"Error setting up MCP server {config}: {e}")

    print(f"Loaded {len(mcp_tools)} MCP tools from {len(mcp_servers)} servers.")
    return mcp_tools
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\tools\mcp_tool.py:8-36`

```python
class MCPTool(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        connection: "MCPConnection",
    ):
        super().__init__(
            name=name, description=description, input_schema=input_schema
        )
        self.connection = connection

    async def execute(self, **kwargs) -> str:
        """Execute the MCP tool with the given input_schema."""
        try:
            result = await self.connection.call_tool(
                self.name, arguments=kwargs
            )
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if getattr(item, "type", None) == "text":
                        return item.text
            return "No text content in tool response"
        except Exception as e:
            return f"Error executing {self.name}: {e}"
```

### What This Is

A complete **dynamic tool loading system**:
1. **Connection factory**: Creates stdio or SSE connections from config dicts
2. **Tool discovery**: `connection.list_tools()` queries the MCP server for available tools
3. **Dynamic wrapping**: Each discovered tool is wrapped in an `MCPTool` instance with its schema
4. **Per-server isolation**: Each MCP server gets its own connection, tools are scoped to their server
5. **Graceful degradation**: If one MCP server fails to load, other servers' tools still work
6. **Cleanup**: All connections registered with `AsyncExitStack` for guaranteed cleanup

### code-shiniyaya Gap

code-shiniyaya's agent capabilities are **statically defined** in the Markdown table. There is no mechanism to:
1. Dynamically discover available tools/agents at runtime
2. Load capabilities from external servers/packages
3. Gracefully degrade when a capability provider is unavailable
4. Scope capabilities to specific connections/sessions

The agent types (investigator, Explore, general-purpose, etc.) are hardcoded. If a new agent type is needed, the SKILL.md must be manually edited. There is no plugin architecture.

### Concrete Fix

**Add to SKILL.md**, under Agent Orchestration, as a future direction:

```markdown
## Dynamic Agent Capability Loading (Future)

### Current Limitation
Agent types are hardcoded in SKILL.md. Adding a new agent type requires
manual editing. Capability discovery is manual ("is this agent type available?").

### Future: MCP-Style Agent Plugins

Agent capabilities could be loaded dynamically from plugin servers:

```python
# Each agent type defined as an MCP-style tool server
agent_servers = [
    {"type": "stdio", "command": "cavecrew-investigator", "args": ["--serve"]},
    {"type": "stdio", "command": "cavecrew-explore", "args": ["--serve"]},
]

# Dynamic loading — available agents discovered at runtime
agent_tools = await setup_agent_connections(agent_servers, stack)
# agent_tools now contains all discovered agent capabilities
# Adding a new agent = installing a new CLI tool, no SKILL.md edit needed
```

### Graceful Degradation
If `cavecrew-explore` is not installed:
```
Error setting up MCP server {'command': 'cavecrew-explore'}: FileNotFoundError
Loaded 5 agents from 6 servers.  // Explore agent skipped, others work
```

This is superior to the current "全部失败→人工审查" approach because:
- Individual unavailable agents don't block the batch
- CC can detect which types are missing and report to user
- Fallback chain can be triggered automatically
```

**Priority: P2** — A future architectural improvement, not immediately actionable. Requires significant infrastructure changes.

---

## Pattern 9: message_params Override with Test Coverage

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\agent.py:80-94`

```python
def _prepare_message_params(self) -> dict[str, Any]:
    """Prepare parameters for client.messages.create() call.
    
    Returns a dict with base parameters from config, with any
    message_params overriding conflicting keys.
    """
    return {
        "model": self.config.model,
        "max_tokens": self.config.max_tokens,
        "temperature": self.config.temperature,
        "system": self.system,
        "messages": self.history.format_for_api(),
        "tools": [tool.to_dict() for tool in self.tools],
        **self.message_params,  # <-- Override: last wins
    }
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\agents\test_message_params.py:1-272`

A comprehensive test suite covering:
- Basic agent (no message_params) — backward compatibility
- Custom headers — extra_headers injection
- Beta headers — anthropic-beta feature flags
- Metadata — user_id tracking
- API parameters — top_k, top_p, temperature overrides
- Parameter override — message_params overrides config defaults
- Invalid metadata — proper error handling
- Combined parameters — all param types together

### What This Is

A **config override pattern** with exhaustive test coverage:
1. `ModelConfig` sets defaults (model, max_tokens, temperature)
2. `message_params` overrides any config value via `**message_params` unpacking
3. Test suite validates: basic functionality, override correctness, error handling, combination

This is a **quality assurance pattern** — the override mechanism is validated by 8 test cases covering normal, edge, and error conditions.

### code-shiniyaya Gap

code-shiniyaya has NO equivalent:
1. **No config override pattern**: Agent parameters (temperature, max_tokens, model) are not configurable per-dispatch
2. **No test coverage**: There are zero automated tests for agent dispatch parameters
3. **No metadata injection**: No mechanism to tag agent calls with session/user IDs

The SKILL.md frontmatter has metadata fields but they are used for documentation, not injected into agent API calls.

### Concrete Fix

**Add to anti-hang-v2.md**, as a quality section:

```markdown
## Agent Dispatch Parameter Override Pattern

### Problem
All sub-agents are dispatched with the same parameters (model, temperature,
max_tokens). Different agent types need different parameters:
- Investigator: low temperature (0.3), moderate max_tokens (4096)
- Explore: moderate temperature (0.7), high max_tokens (8192)
- Plan: high temperature (0.9) for creative solutions, high max_tokens

### Solution: Per-Type Parameter Override

Define default config per agent type:
```python
AGENT_TYPE_CONFIGS = {
    "investigator": {"temperature": 0.3, "max_tokens": 4096},
    "explore": {"temperature": 0.7, "max_tokens": 8192},
    "general-purpose": {"temperature": 0.5, "max_tokens": 8192},
    "plan": {"temperature": 0.9, "max_tokens": 8192},
    "debugging": {"temperature": 0.3, "max_tokens": 4096},
}

def prepare_dispatch_params(agent_type: str, task_specific: dict = None) -> dict:
    """Build dispatch parameters with defaults + overrides."""
    base = {
        "model": MODEL,
        "system": AGENT_SYSTEM_PROMPTS[agent_type],
        "tools": TOOL_COLLECTIONS[agent_type],
        **AGENT_TYPE_CONFIGS.get(agent_type, {}),
    }
    if task_specific:
        base.update(task_specific)  # Task-specific overrides
    return base
```

### Metadata Injection
Tag every agent dispatch with session context:
```python
base["metadata"] = {
    "session_id": session_id[:8],
    "agent_type": agent_type,
    "step": current_step,
    "dispatch_time": datetime.now().isoformat(),
}
```

This enables:
- Cost tracking per agent type
- Debugging: which agent produced which finding
- Session reconstruction: trace all agent dispatches in a session
```

**Priority: P2** — Quality-of-life improvement. Per-type parameter tuning would improve agent output quality but is not blocking.

---

## Pattern 10: Pre-Tool-Use Security Hook with Command Allowlist

### Source

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\autonomous-coding\client.py:50-122`

```python
# Security layers (defense in depth):
# 1. Sandbox - OS-level bash command isolation prevents filesystem escape
# 2. Permissions - File operations restricted to project_dir only
# 3. Security hooks - Bash commands validated against an allowlist

security_settings = {
    "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
    "permissions": {
        "defaultMode": "acceptEdits",
        "allow": [
            "Read(./**)",
            "Write(./**)",
            "Edit(./**)",
            "Glob(./**)",
            "Grep(./**)",
            "Bash(*)",
            *PUPPETEER_TOOLS,
        ],
    },
}

hooks={
    "PreToolUse": [
        HookMatcher(matcher="Bash", hooks=[bash_security_hook]),
    ],
},
```

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\autonomous-coding\security.py:15-41, 77-158, 297-359`

A full command validation system:
- `ALLOWED_COMMANDS`: 19 allowed commands (ls, cat, npm, git, etc.)
- `COMMANDS_NEEDING_EXTRA_VALIDATION`: 3 commands (pkill, chmod, init.sh)
- `extract_commands()`: Parses compound commands via shlex, handles `&&`, `||`, `;`, pipes, subshells
- `validate_pkill_command()`: Only allows killing dev processes (node, npm, vite, next)
- `validate_chmod_command()`: Only allows `+x` (making scripts executable), blocks recursive, blocks numeric modes
- `validate_init_script()`: Only allows `./init.sh` (not arbitrary scripts)
- `bash_security_hook()`: PreToolUse hook entry point, fails safe (blocks on parse failure)

### What This Is

A **defense-in-depth security model** for autonomous agents:
1. **Layer 1 (Sandbox)**: OS-level isolation — even if bash is allowed, filesystem escape is prevented
2. **Layer 2 (Permissions)**: File operations restricted to `./**` — cannot read/write outside project
3. **Layer 3 (Hooks)**: Bash commands validated against allowlist — unknown commands blocked, sensitive commands get extra validation

The system fails **safe**: if command parsing fails (malformed, unclosed quotes), the entire command is blocked.

### code-shiniyaya Gap

Already partially covered in `autonomous-coding-gap-analysis.md` Dimension 6 (Safety Three-Layer Model). The existing gap analysis correctly identifies the need but doesn't include the specific implementation mechanics. The concrete addition here is:

1. **Exact allowlist content**: The 19-command set + 3 extra-validation commands
2. **Compound command defense**: shlex-based parsing of `&&`, `||`, `;` chains
3. **Fail-safe design**: Parse failure = block (not allow)
4. **Per-command validators**: pkill restricted to dev processes, chmod restricted to +x only

### Concrete Fix

The existing gap analysis already provides a fix. This pattern reinforces it with the exact implementation reference. Add to the existing fix in SKILL.md:

```markdown
### Implementation Reference
See `autonomous-coding-src/autonomous-coding/security.py` for the complete
reference implementation. Key mechanisms to replicate:

1. **Allowlist**: `ALLOWED_COMMANDS = {"ls", "cat", "head", "tail", "wc", "grep",
   "cp", "mkdir", "chmod", "pwd", "npm", "node", "git", "ps", "lsof", "sleep",
   "pkill", "init.sh"}`

2. **Extra validation**: `COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod",
   "init.sh"}` — these pass the allowlist but need further checks

3. **Compound parsing**: `extract_commands()` uses shlex to tokenize, walks tokens
   tracking `expect_command` state, extracts base command names from paths

4. **Fail-safe**: If shlex.parse raises ValueError (malformed command, unclosed
   quotes), return empty list → block the command

5. **Per-command validators**: Separate functions for pkill (dev process names
   only), chmod (+x mode only, no -R), init.sh (exact path match)

6. **Test coverage**: `test_security.py` tests 79+ command variants covering
   allowed, blocked, edge cases, and injection attempts
```

**Priority: P0** — Already identified in existing gap analysis. This pattern provides the exact implementation reference to make the fix concrete.

---

## Summary: Tool Patterns Not Yet in code-shiniyaya

| # | Pattern | Source file:line | Priority | Add to | Gap |
|---|---------|-----------------|----------|--------|-----|
| 1 | Parallel execution with per-tool error isolation | `agents/utils/tool_util.py:7-39` | **P0** | anti-hang-v2.md | No per-agent try/except wrapper; one agent crash can block batch |
| 2 | Base Tool class with to_dict serialization | `agents/tools/base.py:7-27`, `browser_use_demo/tools/base.py:8-70` | **P0** | SKILL.md | Agent types are prose, not structured objects; no serialization format |
| 3 | Tool collection with name-indexed dispatch | `browser_use_demo/tools/collection.py:8-17` | **P1** | SKILL.md | No agent collection abstraction; manual type selection per dispatch |
| 4 | Agent loop with tool_dict dispatch | `agents/agent.py:96-155` | **P0** | anti-hang-v2.md | Procedural workflow, no adaptive dispatch loop |
| 5 | Token-aware context truncation | `agents/utils/history_util.py:69-111` | **P0** | anti-hang-v2.md | No proactive context management; agents can silently overflow |
| 6 | Message history with prompt caching | `agents/utils/history_util.py:113-124`, `browser_use_demo/loop.py:116-123` | **P1** | anti-hang-v2.md | No prompt caching optimization for repeated dispatches |
| 7 | Fresh-context tool init with AsyncExitStack | `agents/agent.py:157-169` | **P1** | anti-hang-v2.md | No resource lifecycle management; state can leak across dispatches |
| 8 | MCP tool integration (connection factory) | `agents/utils/connections.py:93-150`, `agents/tools/mcp_tool.py:8-36` | **P2** | SKILL.md | No dynamic capability loading; agent types are hardcoded |
| 9 | message_params override with test coverage | `agents/agent.py:80-94`, `agents/test_message_params.py:1-272` | **P2** | anti-hang-v2.md | No per-type parameter overrides; no automated tests for dispatch |
| 10 | Pre-tool-use security hook | `autonomous-coding/security.py:15-41,297-359`, `autonomous-coding/client.py:113-116` | **P0** | SKILL.md | Already in existing gap analysis Dimension 6; this adds exact implementation |

---

## Implementation Order

### Immediate (This Session) — P0 Items

1. **Pattern 1** (Per-tool error isolation): Add to anti-hang-v2.md — directly fixes multi-agent reliability
2. **Pattern 4** (Agent dispatch loop): Add to anti-hang-v2.md — replaces fixed-batch with adaptive dispatch
3. **Pattern 5** (Token-aware truncation): Add to anti-hang-v2.md — prevents silent context overflow
4. **Pattern 2** (Base Tool class): Add to SKILL.md — foundation for all other tool patterns
5. **Pattern 10** (Security hook): Add implementation reference to SKILL.md — completes existing gap analysis Dimension 6

### Next Session — P1 Items

6. **Pattern 3** (Tool collection): Add to SKILL.md — builds on Pattern 2
7. **Pattern 6** (Prompt caching): Add to anti-hang-v2.md — cost optimization
8. **Pattern 7** (AsyncExitStack lifecycle): Add to anti-hang-v2.md — resource management

### Future — P2 Items

9. **Pattern 8** (MCP integration): Add to SKILL.md as future direction
10. **Pattern 9** (message_params + tests): Add to anti-hang-v2.md as quality improvement

---

## Appendix: Complete File Index

### Files Read from autonomous-coding-src

| File | Lines | Key Pattern |
|------|-------|-------------|
| `agents/tools/base.py` | 1-27 | Base Tool dataclass, to_dict(), execute() |
| `agents/tools/think.py` | 1-33 | ThinkTool — named reasoning without side effects |
| `agents/tools/code_execution.py` | 1-19 | Server tool format (type+name, no input_schema) |
| `agents/tools/file_tools.py` | 1-278 | FileReadTool, FileWriteTool — full tool implementations |
| `agents/tools/web_search.py` | 1-38 | Server tool with optional params (allowed_domains, etc.) |
| `agents/tools/mcp_tool.py` | 1-36 | MCPTool — wraps MCP server tools with connection |
| `agents/tools/__init__.py` | 1-16 | Tool module exports |
| `agents/utils/tool_util.py` | 1-39 | Parallel execution with per-tool error isolation |
| `agents/utils/history_util.py` | 1-124 | Token tracking, truncation, prompt caching |
| `agents/utils/connections.py` | 1-150 | MCP connection factory, dynamic tool loading |
| `agents/agent.py` | 1-173 | Agent class, _agent_loop, run_async with AsyncExitStack |
| `agents/test_message_params.py` | 1-272 | 8-test suite for parameter override validation |
| `browser-use-demo/tools/base.py` | 1-70 | BaseAnthropicTool, ToolResult, ToolError, ToolFailure |
| `browser-use-demo/tools/collection.py` | 1-17 | ToolCollection — name-indexed dispatch, to_params() |
| `browser-use-demo/tools/browser.py` | 1-1277 | Full BrowserTool implementation (reference for complex tool) |
| `browser-use-demo/loop.py` | 1-210 | Sampling loop with prompt caching, provider switching |
| `browser-use-demo/message_handler.py` | 1-289 | ResponseProcessor, MessageBuilder, tool execution dispatch |
| `autonomous-coding/agent.py` | 1-207 | Two-agent loop, fresh-session-per-iteration, error recovery |
| `autonomous-coding/client.py` | 1-123 | Three-layer security, sandbox+permissions+hooks |
| `autonomous-coding/security.py` | 1-359 | Bash allowlist, command parsing, per-command validation |
| `autonomous-coding/progress.py` | 1-58 | Checklist counting, session headers, progress display |
| `autonomous-coding/prompts.py` | 1-38 | Prompt loading, spec copying |
| `autonomous-coding/test_security.py` | 1-291 | 79+ security test cases |
| `autonomous-coding/prompts/coding_prompt.md` | 1-198 | Immutable checklist, prompt constraint enforcement |
| `autonomous-coding/prompts/initializer_prompt.md` | 1-107 | Init agent role, checklist creation |

### Files Read from code-shiniyaya

| File | Lines | Version |
|------|-------|---------|
| `SKILL.md` | 1-480 | v3.7.0 |
| `references/anti-hang-v2.md` | 1-108 | v2.1 |
| `memory/high-impact-patterns.md` | 1-201 | Current |
| `memory/autonomous-coding-gap-analysis.md` | 1-1008 | Previous scan (7 dimensions) |
