# Autonomous Coding Gap Analysis

**Date**: 2026-07-16
**Source**: `autonomous-coding-src` (Anthropic quickstarts repo)
**Target**: code-shiniyaya SKILL.md v3.7.0 + anti-hang-v2.md
**Method**: Per-dimension comparison across 7 patterns

---

## Dimension 1: Two-Agent Init+Loop Model

### Pattern Description

The autonomous-coding project uses a **two-agent model** separated by role AND time:
- **Init Agent (Session 1 only)**: Creates the immutable checklist (`feature_list.json`, 200+ test cases), project scaffold, init.sh, git init
- **Loop Agent (Sessions 2..N)**: Each session gets a FRESH context window, must re-orient from disk state, verify nothing broke, implement ONE feature, update checklist, commit, and cleanly exit before context fills

### Source Evidence

**File**: `autonomous-coding/agent.py:128-164`
```python
# Check if this is a fresh start or continuation
tests_file = project_dir / "feature_list.json"
is_first_run = not tests_file.exists()

if is_first_run:
    print("Fresh start - will use initializer agent")
    ...
    copy_spec_to_project(project_dir)
else:
    print("Continuing existing project")
    print_progress_summary(project_dir)

# Main loop
iteration = 0
while True:
    iteration += 1
    ...
    # Create client (fresh context)
    client = create_client(project_dir, model)

    # Choose prompt based on session type
    if is_first_run:
        prompt = get_initializer_prompt()
        is_first_run = False
    else:
        prompt = get_coding_prompt()
```

**File**: `autonomous-coding/prompts/coding_prompt.md:1-8`
```markdown
## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task.
This is a FRESH context window - you have no memory of previous sessions.

### STEP 1: GET YOUR BEARINGS (MANDATORY)
```

**File**: `autonomous-coding/prompts/initializer_prompt.md:1-7`
```markdown
## YOUR ROLE - INITIALIZER AGENT (Session 1 of Many)

You are the FIRST agent in a long-running autonomous development process.
Your job is to set up the foundation for all future coding agents.
```

### Gap in code-shiniyaya

code-shiniyaya's SKILL.md has a 7-step workflow (diagnosis -> plan -> execute -> verify), but it is **session-scoped** — designed for a single invocation where CC orchestrates multiple sub-agents. There is **NO concept of a fresh-context continuation loop** where each session:
1. Reads immutable state from disk
2. Re-orients (Step 1: Get Your Bearings)
3. Verifies previous work still holds (Step 3: Verification Test)
4. Does ONE unit of work
5. Updates ONLY the pass/fail field
6. Commits and exits cleanly (Step 10)

The SKILL.md workflow assumes CC has persistent memory and context across all steps. In a long-running autonomous scenario with fresh context per iteration, the agent would be completely lost.

### Concrete Fix

**Add to SKILL.md**, after the 7-step workflow section, a new `## Multi-Session Continuation Loop` section:

```markdown
## Multi-Session Continuation Loop (Long-Running Autonomous)

When code-shiniyaya operates as a long-running autonomous agent across
multiple fresh-context sessions, use the Init+Loop model:

### Init Session (Run Once)

1. Create `checklist.json` — the IMMUTABLE task list:
   ```json
   [
     {
       "id": "T001",
       "category": "bug-fix|feature|refactor|audit",
       "description": "What this task verifies",
       "steps": ["Step 1: ...", "Step 2: ...", "Step 3: Verify ..."],
       "passes": false,
       "files": ["path/to/file.py:line"],
       "deps": ["T000"]  // optional, for DAG ordering
     }
   ]
   ```
2. ALL entries start with `"passes": false`
3. Create `progress.txt` with session summary
4. Git init + first commit

### Loop Session (Each Fresh Context)

**Step 1 — GET YOUR BEARINGS (MANDATORY)**:
Read `checklist.json`, `progress.txt`, `git log --oneline -20`.
Count remaining: `grep '"passes": false' checklist.json | wc -l`.
You have NO memory of previous sessions — trust ONLY what's on disk.

**Step 2 — VERIFICATION TEST (MANDATORY BEFORE NEW WORK)**:
Run 1-2 tests marked `"passes": true` that are most core to verify the
previous session didn't introduce regressions. If ANY break:
- Mark that feature as `"passes": false` immediately
- Fix the regression BEFORE implementing anything new

**Step 3 — CHOOSE ONE TASK**:
Pick the highest-priority task with `"passes": false`. Complete ONLY this
one task perfectly before moving on.

**Step 4 — IMPLEMENT + VERIFY**:
Implement the task thoroughly. Verify end-to-end using actual tooling
(browser automation, test runner, etc.). Do NOT take shortcuts.

**Step 5 — UPDATE checklist.json (CAREFULLY!)**:
YOU CAN ONLY MODIFY ONE FIELD: `"passes"`. Change from `false` to `true`.
NEVER: remove entries, edit descriptions, modify steps, reorder, or combine.

**Step 6 — COMMIT + UPDATE progress.txt**:
```bash
git add . && git commit -m "Complete [T00X]: [description] - verified"
```
Update `progress.txt` with: accomplished, test completed, issues found/fixed,
what to work on next, current status (e.g., "45/200 passing").

**Step 7 — END SESSION CLEANLY**:
Before context fills: commit all, update progress.txt, update checklist.json,
ensure no uncommitted changes, leave project in working state.
```

**Priority: P0** — This is the core architectural pattern that enables long-running autonomy.

---

## Dimension 2: Immutable Checklist

### Pattern Description

`feature_list.json` is a **contract between sessions**. Once created by the Init agent, its structure is frozen:
- **Immutable fields**: `category`, `description`, `steps[]`
- **Mutable field**: Only `passes` (boolean)
- **Enforcement**: Explicit "NEVER" rules in the coding prompt and catastrophic consequences for violation

### Source Evidence

**File**: `autonomous-coding/prompts/initializer_prompt.md:53-57`
```markdown
**CRITICAL INSTRUCTION:**
IT IS CATASTROPHIC TO REMOVE OR EDIT FEATURES IN FUTURE SESSIONS.
Features can ONLY be marked as passing (change "passes": false to "passes": true).
Never remove features, never edit descriptions, never modify testing steps.
This ensures no functionality is missed.
```

**File**: `autonomous-coding/prompts/coding_prompt.md:107-126`
```markdown
### STEP 7: UPDATE feature_list.json (CAREFULLY!)

**YOU CAN ONLY MODIFY ONE FIELD: "passes"**

After thorough verification, change:
"passes": false
to:
"passes": true

**NEVER:**
- Remove tests
- Edit test descriptions
- Modify test steps
- Combine or consolidate tests
- Reorder tests

**ONLY CHANGE "passes" FIELD AFTER VERIFICATION WITH SCREENSHOTS.**
```

**File**: `autonomous-coding/progress.py:11-37`
```python
def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    tests_file = project_dir / "feature_list.json"
    if not tests_file.exists():
        return 0, 0
    with open(tests_file, "r") as f:
        tests = json.load(f)
    total = len(tests)
    passing = sum(1 for test in tests if test.get("passes", False))
    return passing, total
```

### Gap in code-shiniyaya

code-shiniyaya has session state files (`session-{id}.json`, `pending-{id}.json`, `dag-{id}.json`) but these are **execution tracking**, not an **immutable task contract**. The key differences:

1. **No single source of truth**: Tasks live in `pending-{id}.json` items but their `status` field changes through the workflow. There is no concept that "only one boolean field can change after creation."
2. **No structural immutability**: code-shiniyaya's items have mutable `status`, `substep`, `lastFileHash` — all changing. The autonomous-coding model restricts modification to exactly ONE field.
3. **No catastrophic guard**: The SKILL.md warns against modifying things but doesn't elevate checklist immutability to "catastrophic" severity with explicit NEVER rules.

### Concrete Fix

**Add to SKILL.md**, under a new `## Immutable Task Contract` section:

```markdown
## Immutable Task Contract

The task checklist (`checklist.json` or `pending-{id}.json` items) is a
CONTRACT between sessions. After creation:

### Protected Fields (NEVER modify after creation)
- `id` — task identifier
- `description` — what the task verifies
- `steps[]` — ordered verification steps
- `category` — task type classification
- `files[]` — target file paths with line numbers
- `deps[]` — dependency edges

### Single Mutable Field
- `passes` (boolean): false → true after verified completion
  - ONLY change after verification with evidence (screenshots, test output, git diff)
  - Changing true → false is ONLY allowed during regression detection (Step 2 of Loop)

**IT IS CATASTROPHIC TO**: remove entries, edit descriptions, modify steps,
combine entries, reorder entries, or change any field other than `passes`.
This ensures no work is silently dropped across sessions.

### Integrity Check
Each loop session must count: `grep '"passes": false' checklist.json | wc -l`
before starting work. Compare against `progress.txt` last-reported count.
Mismatch → HALT, report to user, do not proceed.
```

**Priority: P0** — Without this, multi-session work drifts and tasks are silently lost.

---

## Dimension 3: ThinkTool — Explicit Reasoning Space

### Pattern Description

The `ThinkTool` gives agents a **named, explicit reasoning slot** that:
- Does NOT execute external actions
- Does NOT obtain new information
- Appends thoughts to a log
- Can be used for complex reasoning or cache memory

### Source Evidence

**File**: `agents/tools/think.py:1-32`
```python
"""Think tool for internal reasoning."""

from .base import Tool

class ThinkTool(Tool):
    """Tool for internal reasoning without executing external actions."""

    def __init__(self):
        super().__init__(
            name="think",
            description=(
                "Use the tool to think about something. It will not obtain "
                "new information or change the database, but just append the "
                "thought to the log. Use it when complex reasoning or some "
                "cache memory is needed."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "A thought to think about.",
                    }
                },
                "required": ["thought"],
            },
        )

    async def execute(self, thought: str) -> str:
        """Simply returns the thought back to the model."""
        return "Thinking complete!"
```

### Gap in code-shiniyaya

code-shiniyaya relies entirely on the model's **internal thinking mechanism** (the `thinking` block in the API). There is no tool-based reasoning slot. This creates three problems:

1. **No reasoning persistence**: Internal thinking is ephemeral. When context is truncated, reasoning is lost. A ThinkTool would append thoughts to the message history, making them persist across truncation boundaries.
2. **No forced reasoning checkpoints**: Without a named tool, agents can skip explicit reasoning. The ThinkTool creates a mandatory checkpoint: "before you do X, use the think tool to reason about it."
3. **No explicit instruction**: The prompt can say "Use the think tool to plan your approach before implementing" — a concrete action rather than vague "think carefully."

### Concrete Fix

**Add to anti-hang-v2.md**, under a new `## Think Tool for Reasoning Persistence` section:

```markdown
## Think Tool for Reasoning Persistence

### Problem
Agent reasoning is lost when context is truncated. Without explicit reasoning
checkpoints, agents skip structured analysis and jump to implementation.

### Solution: Prompt-Level Think Pattern

Since CC agents cannot define custom tools, enforce a think pattern in prompts:

**Agent prompt template**:
```markdown
## THINK FIRST (MANDATORY BEFORE ANY ACTION)

Before using ANY tool (Read, Write, Edit, Bash, Grep, Glob), you MUST:
1. State what you are about to do
2. State what you expect to find or change
3. State what could go wrong
4. State what success looks like

Format your thinking as:
[THINK]
Goal: <one sentence>
Expected: <what you predict>
Risk: <what could go wrong>
Success: <how to verify>
[/THINK]

Then proceed with your tool call. This thinking block persists in the
conversation history and survives context truncation.
```

**Enforcement in SKILL.md prompts**:
Add to the beginning of every agent dispatch:
```markdown
CRITICAL: Before any tool call, use [THINK]...[/THINK] tags to reason aloud.
Your thinking MUST be in the message text (not just internal reasoning) so it
persists across turns. Skip this and your work may be silently wrong.
```

### Why This Matters
- Persists reasoning past context truncation
- Creates explicit checkpoints for later audit
- Forces agents to predict outcomes before acting (prediction-error detection)
- Aligns with ThinkTool pattern: no side effects, appends to log
```

**Priority: P1** — Important for multi-turn agent reliability, but can be retrofitted as a prompt pattern without infrastructure changes.

---

## Dimension 4: Trajectory Recording — JSONL Format

### Pattern Description

Every turn (user message, assistant response, tool result) is recorded to a JSONL file with role + content blocks. Images are extracted from base64 and saved to filesystem. This creates a complete, replayable audit trail.

### Source Evidence

**File**: `computer-use-best-practices/computer_use/trajectory.py:20-61`
```python
class Trajectory:
    def __init__(self, model: str, task: str, system_prompt: str | None = None) -> None:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = RUNS_DIR / ts
        (self.dir / "images").mkdir(parents=True, exist_ok=True)
        self._transcript = self.dir / "transcript.jsonl"
        self._img_idx = 0
        (self.dir / "meta.json").write_text(
            json.dumps({"model": model, "task": task, "started": ts}, indent=2)
        )

    def record(self, role: str, content: Any) -> None:
        entry = {"role": role, "content": self._rewrite_images(content)}
        with self._transcript.open("a") as f:
            f.write(json.dumps(entry) + "\n")
```

**File**: `computer-use-best-practices/computer_use/loop.py:372-373, 450, 501`
```python
# Recording user message
messages.append({"role": "user", "content": next_user_message})
trajectory.record("user", next_user_message)

# Recording assistant response
trajectory.record("assistant", [b.model_dump() for b in response.content])

# Recording tool results
trajectory.record("user", results)
```

**File layout**:
```
runs/<iso-timestamp>/
  meta.json          — model, task, timing
  transcript.jsonl   — one JSON object per turn
  images/NNN.jpg     — extracted images
  system_prompt.txt  — system prompt used
```

### Gap in code-shiniyaya

code-shiniyaya has `journal.jsonl` mentioned for iteration scanning but:
1. **No structured trajectory format specified** — The `journal.jsonl` format is ambiguous (what fields? what structure?).
2. **No per-turn recording** — journal.jsonl captures only agent results (`type: "result"`), not the full conversation (user prompts, model responses, intermediate tool calls).
3. **No image extraction pattern** — When agents work with visual data (browser screenshots, diagrams), there's no pattern for persisting images alongside the transcript.
4. **No meta.json** — Missing structured metadata about the run (model used, task description, start time, duration).

### Concrete Fix

**Add to anti-hang-v2.md**, under a new `## Trajectory Recording (JSONL Format)` section:

```markdown
## Trajectory Recording (JSONL Format)

### Format Specification

Every autonomous session MUST produce a trajectory directory:

```
runs/<iso-timestamp>-<session-id-8chars>/
  meta.json          — {"model": "...", "task": "...", "started": "..."}
  transcript.jsonl   — one JSON object per turn, newline-delimited
  system_prompt.md   — the system prompt used (copy)
```

### transcript.jsonl Entry Format

Each line is a JSON object:
```json
{"role": "user", "content": "text or content blocks array"}
{"role": "assistant", "content": [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]}
```

**Fields per entry**:
- `role`: "user" | "assistant" (Claude API roles)
- `content`: string (simple text) or array of content blocks (tool use, tool result, text, image refs)
- `timestamp`: ISO 8601 (optional but recommended)
- `turn`: monotonically increasing integer (optional but recommended)

### Recording Points

Record AFTER each of these events:
1. User prompt sent → `record("user", prompt_text)`
2. Agent response received (with tool calls) → `record("assistant", content_blocks)`
3. Tool results returned → `record("user", tool_results)` — note: tool results
   are modeled as a user-role message in the Claude API

### Recovery Use

When a workflow is killed/interrupted:
1. Parse `transcript.jsonl` — last recorded turn shows exact progress
2. Count tool calls vs tool results — unmatched = in-flight work
3. Extract agent verdicts from assistant content blocks
4. Compute partial completion: `completed_agents / total_agents`

### Integration with Iteration Scanning

Replace the ambiguous `journal.jsonl` reference with `transcript.jsonl`.
Update `journal-parser.py` to read the standardized format:

```python
def parse_transcript(transcript_path: Path) -> dict:
    entries = []
    with open(transcript_path) as f:
        for line in f:
            entries.append(json.loads(line))
    # Extract agent verdicts from assistant turns
    # Count completion from tool call/result pairs
    # Return structured scan-state
```

### Comparison with Current code-shiniyaya journal.jsonl

| Aspect | Current journal.jsonl | Proposed transcript.jsonl |
|--------|----------------------|--------------------------|
| Scope | Agent results only | Every turn (user + assistant) |
| Structure | Undefined | JSONL with `role` + `content` |
| Images | Not handled | Extracted to filesystem |
| Metadata | None | meta.json per run |
| Recovery | Partial (results only) | Complete (full conversation) |
| Replayability | No | Yes (can replay entire session) |
```

**Priority: P1** — Standardized trajectory format enables robust recovery and debugging. Can be added to anti-hang-v2.md as a specification.

---

## Dimension 5: Error Recovery — Fresh-Session-Per-Iteration

### Pattern Description

The autonomous-coding loop is resilient by design:
1. **Fresh ClaudeSDKClient per iteration** — no accumulated context corruption
2. **Error status → retry with fresh session** — agent.py:178-181
3. **Empty response → nudge + retry** — loop.py:431-446
4. **KeyboardInterrupt during streaming → break** — loop.py:421-423
5. **KeyboardInterrupt during tool execution → fill with error results** — loop.py:490-498
6. **Context overflow → truncate oldest** — history_util.py:69-111
7. **Immutable checklist = recovery state** — progress is never lost

### Source Evidence

**File**: `autonomous-coding/agent.py:169-181`
```python
async with client:
    status, response = await run_agent_session(client, prompt, project_dir)

if status == "continue":
    print(f"\nAgent will auto-continue in {AUTO_CONTINUE_DELAY_SECONDS}s...")
    print_progress_summary(project_dir)
    await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)

elif status == "error":
    print("\nSession encountered an error")
    print("Will retry with a fresh session...")
    await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
```

**File**: `computer-use-best-practices/computer_use/loop.py:431-498`
```python
# Empty response handling
if _is_empty_response(response.content):
    empty_retries += 1
    if empty_retries > cfg.empty_response_retry_max:
        raise RuntimeError(f"{empty_retries} consecutive empty responses...")
    messages.append({
        "role": "user",
        "content": "Please continue, do not produce an empty response.",
    })
    continue

# KeyboardInterrupt during tool execution
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

**File**: `agents/utils/history_util.py:69-111`
```python
def truncate(self) -> None:
    """Remove oldest messages when context window limit is exceeded."""
    if self.total_tokens <= self.context_window_tokens:
        return

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
            self.messages[0] = TRUNCATION_MESSAGE
```

### Gap in code-shiniyaya

code-shiniyaya's SKILL.md has extensive error handling (the error table with 16 rows), but it operates in a **single-session orchestration model** where CC is the orchestrator that persists across errors. The gaps:

1. **No fresh-session-per-iteration model**: code-shiniyaya's 7-step workflow assumes CC is always present. If CC's context is lost mid-workflow, recovery relies on JSON state files and manual "continue" triggers — not an automatic fresh session picking up from disk.
2. **Error handling is CC-side**: All error recovery is described in terms of what CC does ("缩小范围重试", "跳过此项"). There's no pattern for the agent ITSELF handling its own errors within a session.
3. **No empty-response recovery**: Not addressed — the autonomous-coding pattern handles models returning empty content with retry+nudge.
4. **No token-aware truncation**: code-shiniyaya mentions token limits (>10000 tokens → parts) but has no sliding-window truncation mechanism with truncation notice injection.

### Concrete Fix

**Add to anti-hang-v2.md**, under the existing error handling sections:

```markdown
## Error Recovery: Fresh-Session Model (from autonomous-coding)

### Core Principle
Each loop iteration gets a FRESH context window. The ONLY shared state is on disk:
- `checklist.json` — immutable task contract
- `progress.txt` — last session summary
- `git log` — code changes

This means: session failure = trivial recovery. Just start a new session.

### Recovery Ladder

| Failure | Autonomous-coding Pattern | code-shiniyaya Adaptation |
|---------|--------------------------|--------------------------|
| Agent returns error status | Retry with fresh ClaudeSDKClient | Restart sub-agent with same prompt, max 2 retries per slot |
| Agent produces empty response | Nudge "please continue", retry | Detect empty output, re-prompt with "Your response was empty. Please provide output." |
| Context window full | Truncate oldest pairs, inject notice | Monitor agent output length; if >80% context, force end-turn + summary + new session |
| Keyboard interrupt during tool execution | Fill incomplete tool_use with error results | Send "stop" to sub-agent; mark in-progress items as INTERRUPTED (not FAILED) |
| Keyboard interrupt during streaming | Break loop, discard partial | Save partial output to `.partial.{ts}.txt`, mark item as INTERRUPTED |
| Checklist.json corrupted | Reconstruct from git history | Use git log + progress.txt to reconstruct task state |

### Token-Aware Truncation for Sub-Agents

When dispatching a sub-agent with large context:
1. Estimate tokens of accumulated context (system + messages + tool results)
2. If >80% of context window:
   a. Truncate oldest message pairs
   b. Inject: "[Earlier history has been truncated.]"
   c. Recalculate remaining tokens
3. Repeat until under threshold

This prevents agents from hitting context limits silently (producing truncated/broken output).

### Recovery State = Disk, Not Memory

The immutable checklist pattern means: even if EVERYTHING in memory is lost,
recovery is:
1. Read `checklist.json` → know exactly what remains
2. Read `progress.txt` → know what was last done
3. Run `git log --oneline -20` → see recent changes
4. Start a fresh session from Step 1 (Get Your Bearings)

No complex state file parsing. No manual "continue" triggers. Just re-read from disk.
```

**Priority: P0** — The fresh-session-per-iteration model is the foundation of robust long-running autonomy.

---

## Dimension 6: Safety Three-Layer Model

### Pattern Description

The autonomous-coding project implements **defense-in-depth** for agent safety:

1. **Layer 1 — Sandbox**: OS-level bash command isolation prevents filesystem escape (`sandbox.enabled: true`)
2. **Layer 2 — Permissions**: File operations restricted to project directory only (`Read(./**)`, `Write(./**)`, etc.)
3. **Layer 3 — Security Hooks**: Bash commands validated against an allowlist with extra validation for sensitive commands

### Source Evidence

**File**: `autonomous-coding/client.py:50-85` (security layer documentation)
```python
"""
Security layers (defense in depth):
1. Sandbox - OS-level bash command isolation prevents filesystem escape
2. Permissions - File operations restricted to project_dir only
3. Security hooks - Bash commands validated against an allowlist
   (see security.py for ALLOWED_COMMANDS)
"""

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

**File**: `autonomous-coding/security.py:15-41` (allowlist)
```python
ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep",
    "cp", "mkdir", "chmod",
    "pwd",
    "npm", "node",
    "git",
    "ps", "lsof", "sleep", "pkill",
    "init.sh",
}

COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod", "init.sh"}
```

**File**: `autonomous-coding/security.py:297-359` (bash_security_hook implementation)
```python
async def bash_security_hook(input_data, tool_use_id=None, context=None):
    """Pre-tool-use hook that validates bash commands using an allowlist."""
    if input_data.get("tool_name") != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    commands = extract_commands(command)
    if not commands:
        return {
            "decision": "block",
            "reason": f"Could not parse command for security validation: {command}",
        }

    for cmd in commands:
        if cmd not in ALLOWED_COMMANDS:
            return {
                "decision": "block",
                "reason": f"Command '{cmd}' is not in the allowed commands list",
            }
        if cmd in COMMANDS_NEEDING_EXTRA_VALIDATION:
            # ... per-command validation
```

### Gap in code-shiniyaya

code-shiniyaya's SKILL.md has **NO structured security model**. The "permissions" in the frontmatter (`file-read: true`, `file-write: true`, `network: false`, `shell: true`) are declarative metadata, not enforced layers. The gaps:

1. **No allowlist for bash commands**: Agents can run any shell command without restriction. There is no `ALLOWED_COMMANDS` set, no `bash_security_hook`, no command validation.
2. **No filesystem sandboxing**: No OS-level isolation. Agents with `shell: true` can access files outside the project directory.
3. **No compound command parsing**: `security.py` splits `&&`, `||`, `;` chains and validates each segment independently. code-shiniyaya has no equivalent defense against command injection via chaining.
4. **No per-command extra validation**: Sensitive commands (kill processes, change permissions) get additional checks in autonomous-coding. code-shiniyaya has none.

### Concrete Fix

**Add to SKILL.md**, under a new `## Agent Safety — Three-Layer Defense` section in the Agent Orchestration area:

```markdown
## Agent Safety — Three-Layer Defense

When dispatching autonomous agents that can execute shell commands,
apply defense-in-depth:

### Layer 1 — Sandbox (OS-Level)
- Enable sandbox mode on all sub-agents where supported
- Sandbox prevents filesystem escape even if shell access is granted
- `autoAllowBashIfSandboxed: true` — bash auto-allowed only when sandboxed

### Layer 2 — Permissions (Filesystem)
- Restrict file operations to the project directory: `Read(./**), Write(./**), Edit(./**)`
- NEVER grant `Read(/**)` or `Write(/**)` to an autonomous agent
- Grant Bash only in combination with Layer 3 hooks

### Layer 3 — Security Hooks (Command Validation)
Apply a bash allowlist on ALL autonomous agents. Minimum allowlist:
```
ALLOWED_COMMANDS = {
    # File inspection only
    "ls", "cat", "head", "tail", "wc", "grep",
    # File ops (safe within sandbox + permissions)
    "cp", "mkdir",
    # Navigation
    "pwd",
    # Dev tooling
    "npm", "node", "npx", "python", "pip", "uv",
    # Version control
    "git",
    # Process management (restricted — see extra validation)
    "ps", "lsof", "sleep",
}
```

### Extra Validation for Sensitive Commands
- `pkill` / `kill`: Only allow killing dev-related processes (node, npm, vite, next, python)
- `chmod`: Only allow `+x` (making scripts executable), no recursive
- `rm`: BLOCK entirely (agents should NOT delete files; use git for cleanup)
- Scripts: Only allow `./init.sh` or project-specific setup scripts, NOT arbitrary scripts

### Compound Command Defense
Parse `&&`, `||`, `;` command chains and validate EACH segment independently.
If any segment fails validation → block the ENTIRE command.
Fail-safe: if parsing fails (malformed command) → block.

### Implementation Template
See `autonomous-coding/security.py` for reference implementation:
- `extract_commands()` — parse compound commands via shlex
- `split_command_segments()` — split on `&&`, `||`, `;`
- `bash_security_hook()` — PreToolUse hook entry point
- Per-command validators: `validate_pkill_command()`, `validate_chmod_command()`, etc.
```

**Priority: P0** — Safety is foundational. Without this, autonomous agents can escape their sandbox, delete files, or run arbitrary commands.

---

## Dimension 7: Prompt Structure — Constraint Enforcement

### Pattern Description

The `coding_prompt.md` enforces constraints through a systematic prompt architecture:
1. **Role declaration** (line 1-8): "You are continuing work... FRESH context... no memory"
2. **Ordered steps with severity labels**: MANDATORY, CRITICAL, CAREFULLY!
3. **Explicit DO/DON'T blocks** per step
4. **NEVER rules** with enumerated prohibitions
5. **Pre-action orientation** (Step 1): Forced disk read before any action
6. **Pre-work verification** (Step 3): Verify old work before new work
7. **Single-task focus** (Step 4): "Focus on completing ONE feature perfectly"
8. **Evidence-gated updates** (Step 7): "ONLY CHANGE 'passes' FIELD AFTER VERIFICATION WITH SCREENSHOTS"
9. **Clean exit protocol** (Step 10): Explicit pre-termination checklist
10. **End-of-prompt reminders**: Goal, Quality Bar, unlimited time

### Source Evidence

**File**: `autonomous-coding/prompts/coding_prompt.md` — full file structure:
```markdown
## YOUR ROLE - CODING AGENT              [Identity]
### STEP 1: GET YOUR BEARINGS (MANDATORY) [Forced orientation]
### STEP 2: START SERVERS                 [Environment setup]
### STEP 3: VERIFICATION TEST (CRITICAL!) [Pre-work regression check]
### STEP 4: CHOOSE ONE FEATURE            [Single-task focus]
### STEP 5: IMPLEMENT THE FEATURE         [Implementation]
### STEP 6: VERIFY WITH BROWSER AUTOMATION [Evidence-gated verification]
### STEP 7: UPDATE feature_list.json (CAREFULLY!) [Restricted mutation]
### STEP 8: COMMIT YOUR PROGRESS          [State persistence]
### STEP 9: UPDATE PROGRESS NOTES         [Cross-session communication]
### STEP 10: END SESSION CLEANLY          [Clean exit]
---                                       [Separator]
## TESTING REQUIREMENTS                   [Tool requirements]
## IMPORTANT REMINDERS                    [End-of-prompt reinforcement]
```

Key constraint techniques:
- `(MANDATORY)` and `(CRITICAL!)` labels
- `**YOU CAN ONLY MODIFY ONE FIELD: "passes"**` — bold, capitalized, specific
- `**NEVER:**` followed by bullet list — explicit prohibitions
- `**DO:**` / `**DON'T:**` — positive/negative examples
- `**ONLY CHANGE "passes" FIELD AFTER VERIFICATION WITH SCREENSHOTS.**`

### Gap in code-shiniyaya

code-shiniyaya's SKILL.md has 16 hard rules and 9 anti-patterns, which is structurally similar but **functionally different**:

1. **Rules are for CC, not for agents**: The 16 rules govern CC's orchestration behavior. The coding_prompt.md rules govern the AGENT'S behavior. When CC dispatches sub-agents, those agents don't get the benefit of code-shiniyaya's rule system — they get short ad-hoc prompts.
2. **No forced orientation step**: code-shiniyaya agents start working immediately. There's no "Step 1: Get Your Bearings" that forces reading state from disk.
3. **No pre-work verification gate**: coding_prompt.md Step 3 says "verify previously-passing tests BEFORE new work." code-shiniyaya has no equivalent regression gate before agents start implementing.
4. **No clean exit protocol**: coding_prompt.md Step 10 has explicit "Before context fills up: commit, update progress, update checklist, ensure clean state." code-shiniyaya agents just stop.
5. **Rules lack severity labels**: code-shiniyaya rules are flat (16 rules, no MANDATORY/CRITICAL/CAREFULLY tier). coding_prompt.md uses progressive severity: MANDATORY > CRITICAL > standard.

### Concrete Fix

**Add to SKILL.md Agent Orchestration section**, a new subsection on prompt structure:

```markdown
## Agent Prompt Structure — Constraint Enforcement Pattern

When crafting prompts for autonomous sub-agents, use the following template
(derived from autonomous-coding coding_prompt.md):

### Required Prompt Sections

```
## YOUR ROLE — [Identity]
[One sentence: who you are, what session this is, key constraint]

### STEP 1: GET YOUR BEARINGS (MANDATORY)
[Forced disk reads — agent MUST read state files before acting]
- Read checklist.json
- Read progress.txt
- Run git log --oneline -20
- Count remaining tasks

### STEP 2: VERIFY EXISTING WORK (CRITICAL!)
[Pre-work regression gate]
- Run 1-2 tests that previously passed
- If ANY break → mark as failing, fix BEFORE new work
- Report: "Regression check: PASS" or "Regression check: FAIL (items: ...)"

### STEP 3: CHOOSE ONE TASK
[Single-task focus — prevents scope creep]
- Pick highest-priority task with "passes": false
- State: "Working on: [task_id] — [description]"
- Complete ONLY this one task

### STEP 4: IMPLEMENT + VERIFY
[Evidence-gated implementation]
- Write code
- Test end-to-end with actual tooling (not shortcuts)
- Record evidence (test output, screenshots, git diff)

### STEP 5: UPDATE CHECKLIST (CAREFULLY!)
[Restricted mutation]
YOU CAN ONLY MODIFY ONE FIELD: "passes"
Change false → true ONLY after verified completion

### STEP 6: COMMIT + UPDATE PROGRESS
[Cross-session state persistence]
git add . && git commit -m "Complete [task_id]: [description]"
Update progress.txt with summary

### STEP 7: END SESSION CLEANLY
[Clean exit before context fills]
- [ ] All changes committed
- [ ] progress.txt updated
- [ ] checklist.json updated
- [ ] No uncommitted changes
- [ ] App in working state
```

### Severity Label Convention

| Label | Meaning | When to Use |
|-------|---------|-------------|
| `(MANDATORY)` | Skip = catastrophic failure | Orientation step, regression check |
| `(CRITICAL!)` | Skip = high risk of error | Browser verification, update protocol |
| `(CAREFULLY!)` | Skip = risk of data corruption | Checklist mutation, git operations |
| (no label) | Standard step | Implementation, commit messages |

### NEVER Rules (Enumerated Prohibitions)

Always include explicit NEVER blocks for critical constraints:
```
**NEVER:**
- Remove entries from the checklist
- Edit descriptions or steps
- Modify any field except "passes"
- Combine or reorder entries

**NEVER:**
- Skip the regression check before implementing
- Mark a task passing without verification evidence
- Continue past 80% context buffer without cleanly exiting
```

### DO/DON'T Blocks

Use positive/negative examples for verification steps:
```
**DO:**
- Test through the actual UI with clicks and keyboard input
- Take screenshots to verify visual appearance
- Check for errors (console, network, logs)

**DON'T:**
- Test only with curl or API calls
- Use JavaScript evaluation to bypass the UI
- Skip visual verification
- Mark tests passing without thorough verification
```
```

**Priority: P1** — The prompt structure is a template that can be used immediately when dispatching sub-agents. Lower priority than the architectural patterns (P0 items) but high impact for agent reliability.

---

## Summary and Prioritization

| # | Pattern | Priority | Add to | Effort |
|---|---------|----------|--------|--------|
| 1 | Two-Agent Init+Loop Model | **P0** | SKILL.md | High — new section + refactor of workflow |
| 2 | Immutable Checklist Contract | **P0** | SKILL.md | Medium — new section + checklist.json spec |
| 3 | ThinkTool Reasoning Space | **P1** | anti-hang-v2.md | Low — prompt pattern, no code |
| 4 | Trajectory Recording (JSONL) | **P1** | anti-hang-v2.md | Medium — spec + format definition |
| 5 | Error Recovery (Fresh-Session) | **P0** | anti-hang-v2.md | Medium — integration with existing recovery |
| 6 | Safety Three-Layer Model | **P0** | SKILL.md | Medium — new section + reference code |
| 7 | Prompt Structure (Constraints) | **P1** | SKILL.md | Medium — template + refactor agent prompts |

### Implementation Order

1. **P0 items first**: Init+Loop model, Immutable Checklist, Fresh-Session Error Recovery, Safety Three-Layer Model
2. **P1 items second**: ThinkTool pattern, Trajectory Recording format, Prompt Structure template

### Files to Modify

- `C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` — Add sections 1, 2, 6, 7
- `C:\Users\shiniyaya\Desktop\code-shiniyaya\references\anti-hang-v2.md` — Add sections 3, 4, 5

---

## Appendix: Cross-Reference Index

### Files Read from autonomous-coding-src

| File | Relevance |
|------|-----------|
| `autonomous-coding/agent.py` | Two-agent loop, fresh-session-per-iteration, error handling |
| `autonomous-coding/prompts/coding_prompt.md` | Immutable checklist, prompt constraint enforcement, clean exit |
| `autonomous-coding/prompts/initializer_prompt.md` | Init agent role, checklist creation, catastrophic immutability |
| `autonomous-coding/progress.py` | Checklist counting, session headers, progress display |
| `autonomous-coding/prompts.py` | Prompt loading, spec copying |
| `autonomous-coding/client.py` | Three-layer security model, sandbox+permissions+hooks |
| `autonomous-coding/security.py` | Bash allowlist, command parsing, per-command validation |
| `autonomous-coding/autonomous_agent_demo.py` | CLI harness, max_iterations, model config |
| `agents/tools/think.py` | ThinkTool — explicit reasoning without side effects |
| `agents/tools/base.py` | Tool base class, to_dict for Claude API format |
| `agents/agent.py` | Agent class, MessageHistory integration, tool loop |
| `agents/utils/history_util.py` | Token-aware context truncation, prompt caching |
| `computer-use-best-practices/computer_use/trajectory.py` | JSONL trajectory recording, image extraction, meta.json |
| `computer-use-best-practices/computer_use/loop.py` | Sampling loop, retry, empty response, keyboard interrupt |
| `CLAUDE.md` | Project-level development guide (not directly used) |

### Files Read from code-shiniyaya

| File | Version |
|------|---------|
| `SKILL.md` | v3.7.0 |
| `references/anti-hang-v2.md` | v2.1 |
