# autoagent-src Progress Tracking Patterns -- code-shiniyaya Improvement Findings

Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src
Targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md and memory/high-impact-patterns.md
Date: 2026-07-16

## Finding 1: Binary Resolution Signals with <solution> XML Tags

**Source**: autoagent/tools/inner.py:3-24, autoagent/main.py:6-28, autoagent/cli.py:295-299, autoagent/workflows/math_solver_workflow_flow.py:13-16
**Priority**: P0

**What it is**:
AutoAgent forces every agent to emit a binary termination signal via structured tool calls (`case_resolved` or `case_not_resolved`). The final answer is wrapped in `<solution>...</solution>` XML tags and extracted via `re.findall(r'<solution>(.*?)</solution>', text, re.DOTALL)`. Similarly, workflows use `extract_answer(response, key)` with `re.findall(r'<{key}>(.*?)</{key}>', response, re.DOTALL)`.

```python
# autoagent/tools/inner.py:3-13
@register_tool("case_resolved")
def case_resolved(result: str):
    """
    Use this function when the case is resolved and no further actions are needed.
    Please encapsulate your final answer (answer ONLY) within <solution> and </solution>.
    Example: case_resolved(`The answer to the question is <solution> 42 </solution>`)
    """
    return f"Case resolved. No further actions are needed. The result of the case resolution is: {result}"

# autoagent/workflows/math_solver_workflow_flow.py:13-16
def extract_answer(response: str, key: str):
    pattern = f"<{key}>(.*?)</{key}>"
    matches = re.findall(pattern, response, re.DOTALL)
    return matches[0] if len(matches) > 0 else None

# autoagent/cli.py:295-299 -- extraction in user-facing flow
if model_answer_raw.startswith('Case resolved'):
    model_answer = re.findall(r'<solution>(.*?)</solution>', model_answer_raw, re.DOTALL)
    if len(model_answer) == 0:
        model_answer = model_answer_raw
    else:
        model_answer = model_answer[0]
```

**Gap in code-shiniyaya**:
code-shiniyaya agents report verdicts as free-text (PASS, PARTIAL, FAIL) via log() strings, but there is NO structured extraction protocol. The journal.jsonl captures `type: "result"` entries but relies on natural language parsing. There is no standardized binary "done vs. not-done" signal that all agents MUST emit, and no structured XML tag for extracting the core finding from agent output. This means:
- Agent outputs are parsed ad-hoc rather than structurally
- The convergence tracking (CR formula) counts CRITICAL issues but relies on manual aggregation of free-text agent outputs
- When workflow is killed mid-execution, journal.jsonl parsing is fragile because there's no guarantee agents used a consistent format

**Fix for SKILL.md** -- add to the "Iterative Scan Workflow" section:

```
### Agent Structured Output Protocol (P0)

Every agent MUST output its result using one of two structured formats:

1. **Binary resolution** -- first line of agent output MUST be exactly one of:
   - `RESOLVED: <summary>` -- agent completed task successfully
   - `UNRESOLVED: <reason>` -- agent could not complete task
   
2. **Structured finding extraction** -- each individual finding MUST be wrapped:
   ```
   <finding severity="CRITICAL|HIGH|MEDIUM|LOW">
   <file>path/to/file</file>
   <line>42</line>
   <description>Concrete description of the issue</description>
   <fix>Suggestion for fix</fix>
   </finding>
   ```

3. **CC extracts findings with**:
   - Binary check: `result.startswith("RESOLVED:")` vs `result.startswith("UNRESOLVED:")`
   - XML extraction: `re.findall(r'<finding[^>]*>(.*?)</finding>', text, re.DOTALL)`
   - If no XML tags found, fall back to free-text (existing behavior)

4. **Journal format upgrade** -- each log() entry for agent result includes:
   - `resolution`: "RESOLVED" | "UNRESOLVED"
   - `extracted_findings_count`: parsed count from XML extraction
   - `raw`: original free-text (for debugging)

This ensures:
- Partial recovery after kill can structurally parse partial results
- Convergence tracking uses exact finding counts, not heuristics
- No ambiguity between "agent crashed" vs "agent found nothing"
```

---

## Finding 2: TaskStatus Enum -- Explicit Lifecycle State Machine

**Source**: autoagent/flow/types.py:22-26, autoagent/flow/types.py:115-120
**Priority**: P1

**What it is**:
```python
# autoagent/flow/types.py:22-26
class TaskStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"

# autoagent/flow/types.py:115-120
@dataclass
class Task:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    upated_at: datetime = field(default_factory=datetime.now)
```

Every task (agent execution) transitions through a formal lifecycle: PENDING -> RUNNING -> SUCCESS/FAILURE. The `updated_at` timestamp is always maintained. This enables:
- Query "which agents are still PENDING?" without parsing logs
- Detect stalled agents by comparing `updated_at` to current time
- Know exactly how many agents haven't started vs. started but not finished

**Gap in code-shiniyaya**:
code-shiniyaya's `workflow-state.json` tracks per-slot status as strings (`done`, `timeout`, `skipped`) but there is NO distinction between "not yet started" (PENDING) and "started but still running" (RUNNING). The current system can't differentiate between:
- Agent that was launched but is taking a long time (RUNNING -- should wait)
- Agent that never got launched because workflow died early (PENDING -- should relaunch)
- Agent that finished (SUCCESS/FAILURE -- done)

Without RUNNING state, the stall detection in anti-hang-v2.md relies on "no log() event for N turns" which conflates "agent running silently" with "agent never launched."

**Fix for anti-hang-v2.md** -- add a formal TaskStatus section:

```
### Task Lifecycle State Machine

Every agent slot follows this formal lifecycle:

PENDING --> RUNNING --> SUCCESS | FAILURE

- PENDING: slot created but agent not yet launched (for recovery: relaunch)
- RUNNING: agent launched via Workflow tool, log() line "Agent {key} launched" sent
- SUCCESS: agent returned non-null result (for recovery: keep, don't relaunch)
- FAILURE: agent returned null OR was killed via TaskStop (for recovery: relaunch)

State tracking in workflow-state.json:
```json
{
  "slots": {
    "security": {
      "status": "RUNNING",
      "startedAt": "2026-07-16T14:30:00Z",
      "resolution": null,
      "verdict": null,
      "findingCount": 0
    }
  }
}
```

Stall detection now uses exact state:
- Agent in RUNNING + 3+ other agents SUCCESS + no result yet = STRAGGLER
- Agent in PENDING + 5+ user turns = workflow may have crashed before launch
- Agent in FAILURE + re-launch count < 2 = eligible for retry
```

---

## Finding 3: MetaChainLogger -- Structured Log Categories with Dual Output

**Source**: autoagent/logger.py:9-137
**Priority**: P1

**What it is**:
The MetaChainLogger categorizes all output into distinct structured sections:
- `Tool Execution` -- tool name + result content (logger.py:63-75)
- `Assistant Message` -- sender + message content (logger.py:76-92)
- `Tool Calls` -- function name + arguments (logger.py:93-112)
- `Info` -- generic messages with timestamp + title + color (logger.py:29-44)

Each category has paired `_save_X()` (file) and `_print_X()` (console) methods. The LoggerManager is a singleton (logger.py:138-175) so all components share one logger instance.

**Gap in code-shiniyaya**:
code-shiniyaya's `log()` output is unstructured free-text. There are no categories, no per-agent-type log sections, and no paired console+file output. The current log format makes it hard to:
- Filter logs by category (agent launch vs. agent result vs. error vs. heartbeat)
- Format agent results differently from status updates
- Find all tool executions across one agent run

**Fix for anti-hang-v2.md** -- add structured log categories:

```
### Structured Log Categories

Replace free-text log() calls with categorized entries:

1. AGENT_LAUNCH: `log('AGENT_LAUNCH key={key} type={type}')`
2. AGENT_RESULT: `log('AGENT_RESULT key={key} resolution={RESOLVED|UNRESOLVED} verdict={PASS|PARTIAL|FAIL} findingCount={n}')`
3. AGENT_TIMEOUT: `log('AGENT_TIMEOUT key={key} elapsed={s}s hangCount={n}')`
4. WORKFLOW_HEARTBEAT: `log('HEARTBEAT iter={N} done={d}/{t} pass={p} fail={f} crit={c}')`
5. WORKFLOW_DONE: `log('WORKFLOW_DONE iter={N} elapsed={s}s pass={p} fail={f} crit={c} timedOut={t} goalAchieved={bool}')`
6. ERROR: `log('ERROR key={key} message={msg}')`

Each category enables:
- CC can regex-extract structured fields: `re.match(r'AGENT_RESULT key=(\S+) resolution=(\S+) verdict=(\S+) findingCount=(\d+)', line)`
- Journal-parser.py can group by category for summary computation
- Recovery can filter AGENT_RESULT lines for completed slots
```

---

## Finding 4: 3-Tier Retry with Error Feedback Injection and Meta-Agent Escalation

**Source**: autoagent/main.py:43-80
**Priority**: P0

**What it is**:
```python
# autoagent/main.py:43-80
MAX_RETRY = 3
for i in range(MAX_RETRY):
    try:
        response: Response = await client.run_async(agent, messages, ...)
    except Exception as e:
        logger.info(f'Exception in main loop: {e}', title='ERROR', color='red')
        raise e
    if 'Case resolved' in response.messages[-1]['content']:
        break
    elif 'Case not resolved' in response.messages[-1]['content']:
        messages.extend(response.messages)
        if meta_agent and (i >= 2):  # <-- ATTEMPT 3: ESCALATE TO META-AGENT
            setup_metachain(...)
            messages.append({
                'role': 'user',
                'content': """It seems that the case is not resolved with the existing agent system.
Help me to solve this problem by running tools in the MetaChain.
IMPORTANT: You should fully take advantage of existing tools...
IMPORTANT: You can not stop with `case_not_resolved` after you try your best...
NEVER ASK FOR HUMAN HELP."""
            })
            meta_agent.functions.append(case_not_resolved)
            meta_agent.functions.append(case_resolved)
            response = await client.run_async(meta_agent, messages, ...)
        messages.append({
            'role': 'user',
            'content': 'Please try to resolve the case again. Trying again in another way may be helpful.'
        })
```

Three tiers:
1. **Attempts 1-2**: Same agent, but the previous conversation (including error/failure) is injected via `messages.extend(response.messages)`, followed by "try again differently"
2. **Attempt 3**: Escalate to `meta_agent` which has access to ALL tools (full tool access, can create new tools, can modify the system)
3. **All failed**: `case_not_resolved` with complete failure chain

**Gap in code-shiniyaya**:
code-shiniyaya Rule 7 says "Agent failure replacement: 2 retries per slot, then permanent fail." But:
- Retries do NOT inject the previous error/failure context into the new attempt
- There is NO escalation to a different, more powerful agent type on the 3rd attempt
- Each retry is a clean slate with the same prompt -- the agent has no idea it failed before

**Fix for SKILL.md** -- update Rule 7 and the error handling table:

```
### Rule 7 -- Agent Failure Escalation (updated)

Retry Tiers:
- Tier 1 (attempt 1): Launch agent with original prompt
- Tier 2 (attempt 2): Same agent type, BUT inject previous failure:
  ```
  "Your previous attempt returned: {previous_result}.
   This was insufficient because: {gap_analysis}.
   Try a DIFFERENT approach this time."
  ```
- Tier 3 (attempt 3): Escalate to higher-capability agent:
  - investigator -> general-purpose
  - Explore -> general-purpose  
  - general-purpose -> Plan (broader context)
  - Plan -> cavecrew-investigator (more hands-on)
  - cavecrew-builder -> cavecrew-reviewer (different perspective)
- Permanent fail only after all 3 tiers exhausted

### Error table addition:
| STEP 1 | Agent 3-tier escalation exhausted | "Slot {key} permanently failed after 3 escalation tiers" | Mark FAILURE, continue other slots |
```

---

## Finding 5: Event-Driven DAG with `already_sent_to_event_group` Dedup

**Source**: autoagent/flow/core.py:119-151
**Priority**: P1

**What it is**:
```python
# autoagent/flow/core.py:119-151
if_current_event_trigger = current_event.id in group.events
if_ctx_cover = all([event_id in this_run_ctx for event_id in group.events])
event_group_id = f"{cand_event.id}:{group_hash}"
if if_current_event_trigger and if_ctx_cover:
    if (any([event_group_id in this_run_ctx[event_id]["already_sent_to_event_group"]
             for event_id in group.events])
        and group.retrigger_type == "all"):
        # some events already dispatched to this event and group, skip
        logger.debug(f"Skip {cand_event} for {current_event}")
        continue
    this_group_returns = {event_id: this_run_ctx[event_id]["result"] for event_id in group.events}
    for event_id in group.events:
        this_run_ctx[event_id]["already_sent_to_event_group"].add(event_group_id)
    build_input = EventInput(group_name=group.name, results=this_group_returns)
    queue.append((cand_event.id, build_input))
```

The DAG engine tracks which downstream events have already fired for each input group using `already_sent_to_event_group` (a set of `{event_id}:{group_hash}` strings). When `retrigger_type="all"`, if any upstream event already dispatched to the same downstream event+group combo, the dispatch is skipped. This prevents double-firing of downstream events when upstream events complete out of order.

**Gap in code-shiniyaya**:
code-shiniyaya's iterative scan recovery (resume protocol) can double-count findings across iterations because:
- When a workflow is killed and resumed, the continuation planner identifies uncovered slots and relaunches them
- But if the same finding was already reported by a completed agent in the previous run AND by the relaunched agent, it gets counted twice
- The convergence tracking (CR formula) becomes unreliable because double-counted findings inflate the CRITICAL count

**Fix for anti-hang-v2.md and SKILL.md iteration scan section**:

```
### Cross-Iteration Dedup Protocol

When resuming from a killed workflow, findings from the new run are merged with findings from the previous partial run:

1. **Finding ID**: hash of `{file}:{line}:{severity}:{description[:80]}` for each finding
2. **Dedup on merge**: 
   - New run findings whose ID matches any ID from the previous partial run -> SKIP (already counted)
   - New findings -> ADD
   - Previous findings with no match in new run -> KEEP (agent may have missed it this time)
3. **Summary recomputation**: re-aggregate after dedup, not before
4. **Journal format**: each finding line includes `finding_id={md5_hash}` for cross-iteration matching

This prevents convergence distortion from double-counted findings across runs.
```

---

## Finding 6: Structured Answer Extraction with `extract_answer()` Pattern

**Source**: autoagent/workflows/math_solver_workflow_flow.py:13-16, autoagent/tools/meta/edit_workflow.py:26-29
**Priority**: P1

**What it is**:
```python
# autoagent/workflows/math_solver_workflow_flow.py:13-16
def extract_answer(response: str, key: str):
    pattern = f"<{key}>(.*?)</{key}>"
    matches = re.findall(pattern, response, re.DOTALL)
    return matches[0] if len(matches) > 0 else None
```

Every workflow event uses this function to extract structured output from agent responses. Combined with the output definition system (`outputs = [{'key': 'gpt4_solution', 'description': '...', 'action': {'type': 'RESULT'}}]`), the DAG engine can decide what to do based on which tag was found: RESULT (store in global_ctx), ABORT (stop), GO_TO (jump to another event).

**Gap in code-shiniyaya**:
code-shiniyaya has no equivalent structured extraction function. Agent outputs are parsed ad-hoc by CC reading the log() text. This means:
- When Codex replies are parsed in STEP 4, there's no programmatic extraction of specific findings
- Journal-parser.py parses `type: "result"` lines but doesn't extract sub-fields from the result content
- The convergence CR formula relies on manual counting of CRITICAL issues from natural language

**Fix for SKILL.md** -- add to the "Iterative Scan Workflow" section:

```
### Structured Agent Output Extraction

All agent prompts MUST include this instruction:

```
YOUR OUTPUT FORMAT:
1. First line: exactly "RESOLVED" or "UNRESOLVED"
2. Each finding wrapped in: <finding severity="X"><f>path</f><l>NN</l><d>description</d></finding>
3. Severity must be one of: CRITICAL, HIGH, MEDIUM, LOW
4. If no findings, output: <no-findings/>
```

CC extraction method (pseudocode):
```
resolution = "RESOLVED" if text.startswith("RESOLVED") else "UNRESOLVED"
findings = [(m.group(1), m.group(2), m.group(3)) 
            for m in re.finditer(r'<finding severity="([^"]*)"><f>(.*?)</f><l>(\d+)</l><d>(.*?)</d></finding>', text, re.DOTALL)]
finding_count = len(findings)
```

This enables:
- Programmatic extraction without LLM re-parsing
- Cross-agent dedup by (file, line, severity) tuple
- Exact convergence tracking (count findings, not free-text mentions)
```

---

## Finding 7: MAX_RETRY with Per-Iteration Binary Check

**Source**: autoagent/cli_utils/metachain_meta_agent.py:34-47, 92-108, 110-160
**Priority**: P0

**What it is**:
```python
# autoagent/cli_utils/metachain_meta_agent.py:34-47
MAX_RETRY = 3
for i in range(MAX_RETRY):
    try:
        output_xml_form = extract_agents_content(output_xml_form)
        assert output_xml_form is not None, "No <agents>...</agents> tag found"
        agent_form = parse_agent_form(output_xml_form)
        break
    except Exception as e:
        print(f"Error parsing XML to agent form: {e}. Retry {i+1}/{MAX_RETRY}")
        messages.append({"role": "user", "content": 
            f"Error parsing XML to agent form: {e}\n"
            f"Note that there are some special restrictions for creating agent form, please try again."})
        response = client.run(agent_former, messages, context_variables, debug=debug)
        output_xml_form = response.messages[-1]["content"]
        messages.extend(response.messages)
```

Each retry:
1. Checks binary condition (extract XML -> parse -> assert)
2. If fail, injects the EXACT error message into the next prompt
3. Adds specific guidance ("there are some special restrictions...")
4. Appends the previous conversation (including failed attempt) so agent has full context

Similarly for tool_editing and agent_editing: binary check via `content.startswith("Case resolved")`, inject failure reason on retry.

**Gap in code-shiniyaya**:
code-shiniyaya's iteration scanning (the core iterative fix loop) uses the convergence rate formula to decide when to stop, but each iteration launches agents with the same prompt template. The prompt does NOT include:
- What the previous iteration found (so agents may re-discover the same issues)
- What went wrong in the previous fix attempt (so agents may repeat the same mistake)
- Specific guidance on what to focus on based on diminishing returns

**Fix for SKILL.md** -- add to iteration scan workflow:

```
### Per-Iteration Feedback Injection

Each iteration's agent prompts MUST include context from the previous iteration:

```
ITERATION CONTEXT:
- Previous iteration (#{N-1}): found {prev_critical} CRITICAL, {prev_high} HIGH
- Issues fixed in previous iteration: {fixed_count}
- Issues remaining after fix: {remaining_count}
- Remaining issues (focus on these): {remaining_issues_summary}
- Previous fix failures (avoid repeating these mistakes): {failed_fix_summary}
```

For retry within the same iteration:
```
RETRY CONTEXT:
- Previous attempt #{N} failed because: {error_or_gap}
- Try a DIFFERENT approach. Do not repeat the same strategy.
```

This closes the loop: agents learn from previous failures instead of starting fresh each time.
```

---

## Finding 8: `should_retry_error()` -- Transient vs. Permanent Error Classification

**Source**: autoagent/core.py:38-54
**Priority**: P1

**What it is**:
```python
# autoagent/core.py:38-54
def should_retry_error(exception):
    if MC_MODE is False: 
        print(f"Caught exception: {type(exception).__name__} - {str(exception)}")
    
    if isinstance(exception, (APIError, RemoteProtocolError, ConnectError)):
        return True
    
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

Combined with tenacity `@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=10, max=180))`, transient errors (network, timeout, API) trigger automatic retry with exponential backoff. Permanent errors (logic bugs, file-not-found, syntax errors) do NOT retry.

**Gap in code-shiniyaya**:
code-shiniyaya Rule 12 says "3 same-file failures -> STOP" but doesn't distinguish between:
- Transient failures (API timeout, network blip) -- SHOULD retry
- Permanent failures (logic error, incorrect file path) -- should NOT retry

This means a workflow could hit STOP on a transient network issue that would resolve on its own. Conversely, it could waste 3 retries on a permanent logic bug.

**Fix for SKILL.md** -- update Rule 12:

```
### Rule 12 -- Error Classification (updated)

Before applying the "3 same-file failures -> STOP" rule, classify the error:

Transient (auto-retry, do NOT count toward STOP):
- "connection error", "server disconnected", "eof occurred"
- "timeout", "event loop is closed"  
- Any httpx.RemoteProtocolError, httpx.ConnectError
- litellm APIError (rate limit, server overload)
- Agent tool infrastructure timeout (not logic timeout)

Permanent (count toward STOP):
- ast.parse failure (syntax error)
- FileNotFoundError (wrong path)
- ImportError (missing module)
- AssertionError on expected output shape
- Any non-transient Python exception

Retry policy:
- Transient: retry up to 4 times with exponential backoff (10s, 40s, 180s)
- Permanent: no retry, immediately report to user
- Mixed (transient on first 2, permanent on 3rd): count only permanent
```

---

## Finding 9: Registry with FunctionInfo for Live Agent Discoverability

**Source**: autoagent/registry.py:26-48, 48-207
**Priority**: P2

**What it is**:
```python
# autoagent/registry.py:26-36
@dataclass
class FunctionInfo:
    name: str
    func_name: str
    func: Callable
    args: List[str]
    docstring: Optional[str]
    body: str
    return_type: Optional[str]
    file_path: Optional[str]
```

Every registered tool, agent, and workflow has metadata stored in a singleton Registry. The registry tracks:
- Function name, source file path, arguments, docstring, function body text
- Separate categories: tools, agents, plugin_tools, plugin_agents, workflows
- `display_*_info` properties for serialization

This enables `list_agents()`, `list_workflows()`, and `list_tools()` to return structured metadata without importing every module.

**Gap in code-shiniyaya**:
code-shiniyaya's agent types are defined in the agent selection matrix (anti-hang-v2.md) as a static list: investigator, Explore, general-purpose, Plan, debugging, cavecrew-builder, cavecrew-reviewer. The hang rates are manually estimated (~3%, ~6%, ~5%, ~8%, ~5%, N/A, N/A). There's no live tracking of:
- Which agent types are currently available (some may be offline/unavailable)
- Actual hang rate per agent type from recent runs
- Which agent types performed best for specific bug categories

**Fix for high-impact-patterns.md** -- add registry concept:

```
### 11. Live Agent Type Registry with Performance Tracking

Modeled after AutoAgent's FunctionInfo + Registry pattern.

Track per agent type:
- name, last_10_hang_rate, avg_duration_s, best_for_categories
- Updated after each workflow run

```python
# Pseudocode for CC-maintained registry (in memory, written to state JSON)
AGENT_REGISTRY = {
    "investigator": {
        "hang_rate_last_10": 0.03,
        "p50_duration_s": 90,
        "best_for": ["file_scan", "byte_level", "simple_verify"],
        "available": True
    },
    "general-purpose": {
        "hang_rate_last_10": 0.05,
        "p50_duration_s": 104,
        "best_for": ["logic", "security", "architecture"],
        "available": True
    },
    ...
}
```

This enables:
- Dynamic agent selection: prefer lower-hang-rate types when multiple can handle a task
- Adaptive timeouts: set timeout proportional to recent p95 duration, not fixed 300s
- Availability checking: skip agent types known to be unavailable
```

---

## Summary: Integration Priority

| # | Pattern | Priority | Target File | Expected Impact |
|---|---------|----------|-------------|-----------------|
| 1 | Binary Resolution + XML Extraction | P0 | SKILL.md | Eliminates free-text ambiguity; enables structural partial recovery |
| 4 | 3-Tier Retry with Error Feedback | P0 | SKILL.md (Rule 7) | Dramatically improves retry success rate |
| 7 | Per-Iteration Feedback Injection | P0 | SKILL.md | Closes the learning loop across iterations |
| 2 | TaskStatus Lifecycle State Machine | P1 | anti-hang-v2.md | Distinguishes PENDING/RUNNING/SUCCESS/FAILURE for precise recovery |
| 3 | Structured Log Categories | P1 | anti-hang-v2.md | Enables programmatic log parsing instead of free-text heuristics |
| 5 | Cross-Iteration Dedup Protocol | P1 | anti-hang-v2.md, SKILL.md | Prevents convergence distortion from double-counted findings |
| 6 | `extract_answer()` Extraction Pattern | P1 | SKILL.md | Programmatic finding extraction without LLM re-parsing |
| 8 | Transient vs. Permanent Error Classifier | P1 | SKILL.md (Rule 12) | Prevents unnecessary STOP on transient errors |
| 9 | Agent Type Registry | P2 | high-impact-patterns.md | Dynamic agent selection based on live performance data |
