# Security Findings: autonomous-coding-src -> code-shiniyaya STEP 6

Source project: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src`
Target files to improve: `C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md`, `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md`
Date: 2026-07-16 | Scanner: CC | DIMENSION: Security

---

## Executive Summary

code-shiniyaya v3.7.0 has **zero security infrastructure** for bash command execution. SKILL.md declares `shell: true` with no allowlist, no sandbox, no PreToolUse hooks, no command validation, and no defense-in-depth. The autonomous-coding-src project implements a production-grade three-layer security model (sandbox + permissions + PreToolUse hooks) with shlex-based tokenization, per-command validators, and a comprehensive test suite. All 10 P0 patterns below are essential additions.

---

## P0: Critical Security Gaps (10 patterns)

### Pattern 1: Three-Layer Security Model (Sandbox + Permissions + Hooks)

- **Source**: `autonomous-coding-src/autonomous-coding/client.py:51-55` (docstring describing 3 layers), `client.py:67-85` (settings dict)
- **code-shiniyaya gap**: SKILL.md line 13 declares `shell: true` with no restrictions. No layered defense at all. Any Bash command from any agent executes directly on the host OS.
- **Fix**: Add to SKILL.md after the metadata block (after line 28):

```markdown
## Security: Three-Layer Defense Model

All agent Bash execution MUST pass through three independent security layers.
Failure at any layer blocks the command. No single layer may be bypassed.

**Layer 1 — OS Sandbox** (autonomous-coding-src/computer-use-best-practices/computer_use/tools/shell.py:28-40)
- Bash commands execute under sandbox-exec (macOS) or equivalent OS isolation
- Scratch directory: agent writes go to `{project_root}/.claude/scratch/{sessionId}/`
- Network: denied by default for all code execution
- Timeout: 30s wall-clock per command; killed on expiry
- Output cap: 64 KiB max; truncated with warning after cap

**Layer 2 — Filesystem Permissions** (autonomous-coding-src/autonomous-coding/client.py:67-85)
- Read/Write/Edit/Glob/Grep restricted to project root only (`./**`)
- Path traversal (`..`, absolute paths) rejected before filesystem access
- Secret paths blocked: `~/.ssh`, `~/.aws`, `~/.gnupg`, `.env`, `credentials.*`
- Permission `defaultMode: "acceptEdits"` within allowed paths only

**Layer 3 — PreToolUse Hooks** (autonomous-coding-src/autonomous-coding/client.py:113-116)
- Bash commands validated against explicit allowlist BEFORE execution
- Unparseable commands → blocked (fail-safe, not fail-open)
- Sensitive commands require per-command validator approval
- Compound commands split into segments; each validated independently

**Verification**: Every 20th agent session, run security hook self-test
(`python -m autonomous-coding.test_security`) and verify all tests pass.
```

- **Priority**: P0

---

### Pattern 2: Bash Allowlist with Explicit ALLOWED_COMMANDS Set

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:15-41`
- **code-shiniyaya gap**: No allowlist; any command can run. This is the single largest security gap.
- **Fix**: Add to SKILL.md after Pattern 1, and directly to high-impact-patterns.md:

**For SKILL.md** (add in the Security section):

```markdown
### Bash Allowlist (EXACT set from autonomous-coding-src)

Only these commands may be executed. Any command not in this set is blocked:

```python
ALLOWED_COMMANDS = {
    # File inspection
    "ls", "cat", "head", "tail", "wc", "grep",
    # File operations
    "cp", "mkdir", "chmod",  # chmod requires extra validation
    # Directory
    "pwd",
    # Node.js development
    "npm", "node",
    # Python development
    "python", "pip", "uv",
    # Version control
    "git",
    # Process management
    "ps", "lsof", "sleep",
    "pkill",  # requires extra validation
    # Script execution
    "init.sh",  # requires extra validation
}

COMMANDS_NEEDING_EXTRA_VALIDATION = {"pkill", "chmod", "init.sh"}
```

Even if a command is in the allowlist, commands in COMMANDS_NEEDING_EXTRA_VALIDATION
must pass per-command validation (Pattern 6).
```

**For high-impact-patterns.md** (add new entry after line 144, pattern 26):

```markdown
### Pattern 27: Bash Allowlist for Agent Security
- **Source**: `autonomous-coding-src/autonomous-coding/security.py:15-41`
- **Pattern**: Explicit allowlist of allowed commands. Blocked by default. Only listed commands pass.
- **Fix**: Add ALLOWED_COMMANDS set to SKILL.md security section. CC must verify every bash command against the allowlist before agent execution.
```

- **Priority**: P0

---

### Pattern 3: shlex.split() for Proper Shell Tokenization

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:105` (`tokens = shlex.split(segment)`)
- **code-shiniyaya gap**: No shell tokenization. Simple string matching would be trivially bypassed by quoting tricks (`ls`$'\x20'-la), variable expansion, or escaped characters.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Shell Tokenization: shlex.split() (MANDATORY)

All command parsing MUST use Python's `shlex.split()`, never regex or simple string
matching. shlex handles quoting, escaping, and POSIX shell semantics correctly.

```python
import shlex

def extract_commands(command_string: str) -> list[str]:
    """Extract command names, handling pipes, chaining, and shell keywords."""
    commands = []
    segments = command_string.split(";")  # pre-split on semicolons
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Unclosed quotes / malformed → block (fail-safe)
            return []  # empty = all-blocked
        if not tokens:
            continue
        expect_command = True
        for token in tokens:
            if token in ("|", "||", "&&", "&"):
                expect_command = True; continue
            if token in ("if","then","else","elif","fi","for","while",
                         "until","do","done","case","esac","in","!","{","}"):
                continue  # shell keywords
            if token.startswith("-"):  # flags
                continue
            if "=" in token and not token.startswith("="):  # VAR=value
                continue
            if expect_command:
                commands.append(os.path.basename(token))  # strip paths
                expect_command = False
    return commands
```

**WHY NOT REGEX**: `re.split(r'\s+', cmd)` breaks on `'my command'`, misses
`$()` injection, fails on escaped spaces. shlex is the ONLY correct parser for
POSIX shell syntax.
```

- **Priority**: P0

---

### Pattern 4: Fail-Safe on Unparseable Commands

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:105-109`
- **code-shiniyaya gap**: No handling for unparseable commands; they would pass through unvalidated.
- **Fix**: Add to SKILL.md:

```markdown
### Fail-Safe Rule: Unparseable = Block

```python
try:
    tokens = shlex.split(command_string)
except ValueError:
    # Malformed command (unclosed quotes, invalid escape, etc.)
    # BLOCK immediately — never allow unparseable commands
    return {"decision": "block", "reason": f"Could not parse: {command_string}"}
```

If `extract_commands()` returns an empty list, the command is blocked:
```python
if not commands:
    return {"decision": "block", "reason": "No parseable commands found"}
```

**Rationale**: Unparseable commands are the most common vector for injection attacks.
Attacker crafts input that confuses the parser → parser gives up → command passes
through unvalidated. This MUST be fail-safe (block on any parse failure).
```

- **Priority**: P0

---

### Pattern 5: PreToolUse Hooks (HookMatcher for Bash)

- **Source**: `autonomous-coding-src/autonomous-coding/client.py:113-116`
- **code-shiniyaya gap**: No hook infrastructure for security. SKILL.md mentions hooks for workflow (on_error, before_start, after_complete) but not PreToolUse security hooks.
- **Fix**: Add to SKILL.md Security section:

```markdown
### PreToolUse Hook Configuration

Security hooks must be registered BEFORE any agent session starts. The hook
intercepts every Bash tool call and validates the command against the allowlist.

```python
from claude_code_sdk.types import HookMatcher
from security import bash_security_hook

client = ClaudeSDKClient(
    hooks={
        "PreToolUse": [
            HookMatcher(
                matcher="Bash",           # only intercept Bash tool calls
                hooks=[bash_security_hook]  # validate command
            ),
        ],
    },
)
```

**Hook return protocol**:
- Return `{}` — command passes ALL validation layers → allowed
- Return `{"decision": "block", "reason": "..."}` — blocked; reason shown to user

**Hook ordering**: PreToolUse fires BEFORE the tool executes. The hook cannot be
bypassed by agent trickery — it runs in the SDK layer, not the agent's context.
```

- **Priority**: P0

---

### Pattern 6: Per-Command Validators (validate_pkill, validate_chmod, validate_init.sh)

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:161-276` (three validator functions)
- **code-shiniyaya gap**: No per-command validation. Allowlist alone is insufficient — `pkill` is allowlisted but `pkill -9 init` would kill the system; `chmod` is allowlisted but `chmod 777 /etc/passwd` would be catastrophic.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Per-Command Validators

Even allowlisted commands may have dangerous parameter combinations.
These validators intercept specific commands and approve/reject based on arguments.

#### validate_pkill_command
```python
def validate_pkill_command(command_string: str) -> tuple[bool, str]:
    """
    Only allow killing DEV-RELATED processes.
    Blocks: pkill bash, pkill chrome, pkill python, pkill -9 anything
    """
    ALLOWED_PROCESS_NAMES = {"node", "npm", "npx", "vite", "next", "python", "uv"}
    tokens = shlex.split(command_string)
    if not tokens:
        return False, "Empty pkill command"
    args = [t for t in tokens[1:] if not t.startswith("-")]
    if not args:
        return False, "pkill requires a process name"
    target = args[-1]
    if " " in target:
        target = target.split()[0]  # pkill -f "node server.js" → "node"
    # BLOCK -9 (SIGKILL) — always use default SIGTERM first
    if "-9" in tokens or "--signal=9" in tokens or "-KILL" in tokens:
        return False, "pkill -9 (SIGKILL) is not allowed; use default signal"
    if target in ALLOWED_PROCESS_NAMES:
        return True, ""
    return False, f"pkill only allowed for dev processes: {ALLOWED_PROCESS_NAMES}"
```

#### validate_chmod_command
```python
def validate_chmod_command(command_string: str) -> tuple[bool, str]:
    """
    ONLY allow +x (make executable). Blocks ALL numeric modes (777, 755, etc.),
    all write/read changes, and all recursive (-R) flags.
    """
    tokens = shlex.split(command_string)
    for token in tokens[1:]:
        if token.startswith("-"):  # -R, --recursive → BLOCK
            return False, "chmod flags (-R, --recursive) are not allowed"
    mode = None
    for token in tokens[1:]:
        if not token.startswith("-") and mode is None:
            mode = token; break
    if mode is None:
        return False, "chmod requires a mode"
    if not re.match(r"^[ugoa]*\+x$", mode):
        return False, f"chmod only allowed with +x, got: {mode}"
    return True, ""
```

#### validate_init_script
```python
def validate_init_script(command_string: str) -> tuple[bool, str]:
    """
    Only allow ./init.sh execution. Blocks all other scripts,
    bash/sh wrappers, and command chaining injection.
    """
    tokens = shlex.split(command_string)
    if not tokens:
        return False, "Empty command"
    script = tokens[0]
    # Allow: ./init.sh, /path/to/init.sh
    # Block: ./setup.sh, bash init.sh, ./init.sh; rm -rf /
    if script == "./init.sh" or script.endswith("/init.sh"):
        # Extra: reject if tokens contain ;, &&, || (chaining injection)
        if any(t in (";", "&&", "||") for t in tokens):
            return False, "No command chaining allowed with init.sh"
        return True, ""
    return False, f"Only ./init.sh is allowed, got: {script}"
```
```

- **Priority**: P0

---

### Pattern 7: Command Chaining Split (Compound Command Segmentation)

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:47-74` (`split_command_segments()`)
- **code-shiniyaya gap**: No handling of compound commands. `ls && rm -rf /` would pass if only `ls` is checked.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Compound Command Segmentation

Commands chained with `&&`, `||`, `;` MUST be split into individual segments.
Each segment is independently validated. If ANY segment fails, the ENTIRE
command is blocked.

```python
import re

def split_command_segments(command_string: str) -> list[str]:
    """
    Split on &&, ||, and ; that aren't inside quotes.
    Returns individual command segments for independent validation.
    """
    # Split on && and ||
    segments = re.split(r"\s*(?:&&|\|\|)\s*", command_string)
    # Further split on semicolons (not inside quotes)
    result = []
    for segment in segments:
        sub_segments = re.split(r'(?<!["\'])\s*;\s*(?!["\'])', segment)
        for sub in sub_segments:
            sub = sub.strip()
            if sub:
                result.append(sub)
    return result
```

**Validation logic**:
```python
segments = split_command_segments(command)
for segment in segments:
    commands_in_segment = extract_commands(segment)
    for cmd in commands_in_segment:
        if cmd not in ALLOWED_COMMANDS:
            return BLOCK  # any segment fails → whole command blocked
```

**Example**: `"ls -la && rm -rf /"` → segments = `["ls -la", "rm -rf /"]` →
`extract_commands("rm -rf /")` = `["rm"]` → `"rm" not in ALLOWED_COMMANDS` → BLOCKED.
```

- **Priority**: P0

---

### Pattern 8: Base Command Extraction (Strip Full Paths)

- **Source**: `autonomous-coding-src/autonomous-coding/security.py:152-155` (`cmd = os.path.basename(token)`)
- **code-shiniyaya gap**: Full paths (`/usr/bin/rm`, `/bin/sh`) would bypass simple string matching if the allowlist only checks the raw token.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Path-Neutral Command Extraction

Commands may be specified as full paths (`/usr/bin/node`) or bare names (`node`).
The extractor MUST normalize to basename before checking the allowlist.

```python
import os

# Inside extract_commands loop:
if expect_command:
    cmd = os.path.basename(token)  # /usr/bin/node → node
    commands.append(cmd)
    expect_command = False
```

**Example**: `/bin/bash -c "evil"` → `os.path.basename("/bin/bash")` → `"bash"` →
`"bash" not in ALLOWED_COMMANDS` → BLOCKED.

Without this normalization, `/bin/bash` would not match any string in the allowlist
but bash itself would still execute if the check was skipped for unrecognized tokens.
```

- **Priority**: P0

---

### Pattern 9: Filesystem Permission Restriction (Project Root Only)

- **Source**: `autonomous-coding-src/autonomous-coding/client.py:67-85` (permissions allow list)
- **code-shiniyaya gap**: SKILL.md line 12-16 declares file-read:true, file-write:true with NO path restrictions. Agents can read/write anywhere on the filesystem.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Filesystem Permission Sandbox

All file operations (Read, Write, Edit, Glob, Grep) MUST be restricted to the
project root directory. This is configured via the permissions block:

```python
security_settings = {
    "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
    "permissions": {
        "defaultMode": "acceptEdits",
        "allow": [
            "Read(./**)",     # only within project directory
            "Write(./**)",    # only within project directory
            "Edit(./**)",     # only within project directory
            "Glob(./**)",     # only within project directory
            "Grep(./**)",     # only within project directory
            "Bash(*)",        # bash is allowlisted but hooks validate commands
        ],
    },
}
```

**Path traversal prevention**: Any path containing `..` or starting with `/` is
rejected by the permission system BEFORE hitting the filesystem.

```python
def validate_path(path: str, project_root: Path) -> bool:
    """Reject paths that escape the project root."""
    resolved = (project_root / path).resolve()
    return resolved.is_relative_to(project_root.resolve())
```

**Secret path blacklist** (from shell.py L5-8): These paths are ALWAYS denied:
- `~/.ssh/`, `~/.aws/`, `~/.gnupg/`, `~/.claude/credentials/`
- `*.env`, `.env.*`, `credentials.json`, `secrets.yaml`
- Any file matching `*secret*` or `*credential*` outside project root
```

- **Priority**: P0

---

### Pattern 10: Shell Output Size and Time Caps

- **Source**: `autonomous-coding-src/computer-use-best-practices/computer_use/tools/shell.py:28-73`, `constants.py:115`
- **code-shiniyaya gap**: No resource limits on shell execution. An agent could run `yes` (infinite output) and fill RAM, or run an infinite loop and hang forever.
- **Fix**: Add to SKILL.md Security section:

```markdown
### Shell Execution Resource Limits

Every bash command execution MUST have hard resource limits:

```python
# From shell.py:28-73
_TIMEOUT_S = 30              # wall-clock timeout; kill process on expiry
MAX_OUTPUT_BYTES = 64 * 1024 # 64 KiB cap; truncate with warning

def run_sandboxed(argv: list[str], scratch: Path) -> ToolResult:
    proc = subprocess.Popen(cmd, stdout=PIPE, stderr=STDOUT, cwd=scratch)
    buf = bytearray()
    deadline = time.monotonic() + _TIMEOUT_S
    truncated = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.kill()
            proc.wait()
            return ToolResult(error=f"timed out after {_TIMEOUT_S}s")
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.5))
        if ready:
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_OUTPUT_BYTES:
                truncated = True
                proc.kill()
                break
        elif proc.poll() is not None:
            buf.extend(proc.stdout.read())
            break
    # ...
```

**These limits apply to ALL agent bash execution, not just sandboxed**:
- Timeout: 30s default, configurable per command type (max 120s for npm install)
- Output: 64 KiB default; truncated output appended with `[truncated at 65536 bytes]`
- Memory: OS sandbox limits virtual memory
- Network: denied (sandbox-exec profile or equivalent)
```

- **Priority**: P0

---

## P1: Important Security Gaps (5 patterns)

### Pattern 11: Scratch Directory Isolation

- **Source**: `autonomous-coding-src/computer-use-best-practices/computer_use/tools/shell.py:87-102` (`_SandboxedTool.__init__`, `scratch_dir`)
- **code-shiniyaya gap**: Agent writes go anywhere; no isolated working directory.
- **Fix**: Add to SKILL.md:

```markdown
### Scratch Directory Isolation

Each agent session gets its own scratch directory for temporary files:
`{project_root}/.claude/scratch/{sessionId[:8]}/`

- Created on first write, cleaned up on session completion
- Agent cannot write outside scratch (enforced by sandbox)
- Scratch survives tool calls within a session (persistent state)
- Scratch is deleted on session cleanup (audit trail expires)
```

- **Priority**: P1

---

### Pattern 12: Configurable Shell Limits (config dataclass)

- **Source**: `autonomous-coding-src/computer-use-best-practices/constants.py:68-179` (Config dataclass with `max_shell_output_bytes`, `_TIMEOUT_S`)
- **code-shiniyaya gap**: Hardcoded constants; no config file for security parameters.
- **Fix**: Add to SKILL.md:

```markdown
### Security Configuration (configurable per project)

Security parameters are configurable via a TOML file or environment variables:

```toml
# .claude/security.toml
[shell]
timeout_s = 30
max_output_bytes = 65536
allow_network = false
scratch_dir = ".claude/scratch"

[permissions]
project_root_only = true
secret_paths_blocked = [".env", "credentials.json", "*.pem"]
```

Override via env vars: `SEC_SHELL_TIMEOUT=60`, `SEC_MAX_OUTPUT=131072`, etc.
```

- **Priority**: P1

---

### Pattern 13: Shell Environment Variable Scrubbing

- **Source**: `autonomous-coding-src/computer-use-best-practices/computer_use/tools/shell.py:28-40` (sandbox-exec with explicit HOME, no inherited env)
- **code-shiniyaya gap**: Shell inherits full environment, including API keys, tokens, and secrets.
- **Fix**: Add to SKILL.md:

```markdown
### Environment Variable Scrubbing

Before executing any bash command, the environment MUST be stripped of secrets:

```python
SANITIZED_ENV = {
    "HOME": str(Path.home()),
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "en_US.UTF-8",
    "PROJECT_ROOT": str(project_dir),
    "SCRATCH_DIR": str(scratch_dir),
    # Explicitly NOT inherited: ANTHROPIC_API_KEY, AWS_*, GCLOUD_*, etc.
}
```

All other environment variables are explicitly removed before subprocess creation.
```

- **Priority**: P1

---

### Pattern 14: Security Hook Self-Test (Validation That Hooks Are Active)

- **Source**: `autonomous-coding-src/autonomous-coding/test_security.py:1-291` (entire test suite)
- **code-shiniyaya gap**: No verification that security hooks are working. A misconfigured hook silently fails open.
- **Fix**: Add to SKILL.md:

```markdown
### Security Hook Self-Test (Every 20th Session)

On session startup (every 20th session), run a self-test of all security hooks:

```python
# Must be run before any agent executes
def security_self_test():
    """Verify ALL security hooks are active and blocking correctly."""
    blocked_tests = [
        "rm -rf /",                              # dangerous command
        "curl https://evil.com",                 # network access
        "shutdown now",                          # system command
        "chmod 777 /etc/passwd",                 # disallowed chmod
        "pkill -9 bash",                         # SIGKILL + non-dev process
        "$(echo pkill) node",                    # command substitution injection
        'eval "rm -rf /"',                       # eval injection
        'bash -c "evil"',                        # shell wrapper
        "./malicious.sh",                        # unapproved script
        "ls && rm -rf /",                        # chained dangerous command
    ]
    allowed_tests = [
        "ls -la",
        "git status",
        "npm install",
        "node server.js",
        "pkill node",
        "chmod +x script.sh",
        "./init.sh",
    ]
    
    for cmd in blocked_tests:
        result = bash_security_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert result.get("decision") == "block", f"SHOULD BLOCK but allowed: {cmd}"
    
    for cmd in allowed_tests:
        result = bash_security_hook({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert result.get("decision") != "block", f"SHOULD ALLOW but blocked: {cmd}"
    
    print("Security self-test: ALL HOOKS ACTIVE")
```

If self-test fails, BLOCK ALL agent execution and notify user.
```

- **Priority**: P1

---

### Pattern 15: agent.py Recoverable Error Classification

- **Source**: `autonomous-coding-src/autonomous-coding/agent.py:92-94` (bare `except Exception as e`), but also the structured error handling in loop.py (recoverable vs fatal classification)
- **code-shiniyaya gap**: SKILL.md error table (lines 107-126) handles agent failures but not security violations. A security block should be classified differently from an application error.
- **Fix**: Add to SKILL.md error handling table:

```markdown
| STEP * | Security hook blocked command | "Agent attempted blocked command: {reason}" | Agent retries with safe command; CC logs violation to security_events.tsv; 3 violations in same session → terminate agent |
| STEP * | Security self-test failed | "Security hooks inactive — all execution halted" | Hard stop; all agents terminated; user must manually verify and re-enable |
```

- **Priority**: P1

---

## P2: Good-to-Have Improvements (2 patterns)

### Pattern 16: Automatic Sandbox Profile Generation

- **Source**: `autonomous-coding-src/computer-use-best-practices/sandbox/default.sb` (referenced at constants.py:31)
- **code-shiniyaya gap**: No sandbox profile file. Sandbox configuration is manual and environment-specific.
- **Fix**: Bundle a default `.claude/sandbox/default.sb` profile with the skill:

```bash
;; .claude/sandbox/default.sb — Agent execution sandbox profile
(version 1)
(deny default)
(allow file-read* (subpath (param "SCRATCH")))
(allow file-write* (subpath (param "SCRATCH")))
(allow file-read* (subpath (param "HOME") ".claude"))
(deny file-read* (subpath (param "HOME") ".ssh"))
(deny file-read* (subpath (param "HOME") ".aws"))
(deny file-read* (subpath (param "HOME") ".gnupg"))
(deny network*)
```

- **Priority**: P2

---

### Pattern 17: Security Violation Audit Log

- **Source**: analogous to `autonomous-coding-src/autonomous-coding/progress.py` (progress tracking), extended with security dimension
- **code-shiniyaya gap**: No audit trail for blocked commands or security events.
- **Fix**: Add to SKILL.md:

```markdown
### Security Audit Log

All security events are logged to `.claude/memory/code-shiniyaya/security_events.tsv`:

```
timestamp	session_id	agent_id	command	decision	reason
2026-07-16T10:30:01Z	a1b2c3d4	agent-07	"rm -rf /"	blocked	"Command 'rm' not in allowlist"
2026-07-16T10:30:15Z	a1b2c3d4	agent-07	"pkill -9 bash"	blocked	"pkill only allowed for dev processes"
```

- TSV format, one row per event
- Git-untracked (like fix-log.tsv)
- Rotation: new file when > 1000 lines
- Alert: if same agent triggers 3+ blocks in one session, log WARNING and notify user
```

- **Priority**: P2

---

## Integration Plan: What to Add to Each Target File

### SKILL.md additions (after line 28, metadata block):

1. New section: `## Security: Three-Layer Defense Model` (Patterns 1-10, ~200 lines)
2. New error table entry: security hook blocked (Pattern 15)
3. New state file: `security_events.tsv` (Pattern 17)
4. Update permissions block (line 12-16) to reference security layers

### high-impact-patterns.md additions:

Add after existing Pattern 26 (line 144):

```markdown
## New Dimension: Agent Security (autonomous-coding deep scan, 2026-07-16)

### Pattern 27: Bash Allowlist for Agent Security
### Pattern 28: shlex.split() Shell Tokenization
### Pattern 29: Fail-Safe Command Parsing
### Pattern 30: PreToolUse Security Hooks
### Pattern 31: Per-Command Validators
### Pattern 32: Command Chaining Segmentation
### Pattern 33: Path-Neutral Command Extraction
### Pattern 34: Filesystem Permission Sandbox
### Pattern 35: Shell Resource Limits (Timeout + Output Cap)
### Pattern 36: Security Self-Test on Session Startup
```

### anti-hang-v2.md additions:

No changes needed — security is orthogonal to anti-hang. However, the `agent.py` security-blocks handling (Pattern 15) intersects: a hung agent that triggers repeated security blocks should be terminated faster (reduce from 3-retry to 1-retry after security block).

```markdown
### Security Block Fast-Path Kill (add to anti-hang-v2.md Agent Selection Matrix)

| Trigger | Action | Timeout |
|---------|--------|---------|
| Agent security violation | Log, retry once with safe command | 30s |
| Agent 2nd security violation in same session | Immediate TaskStop, mark slot PERMANENTLY_FAILED | N/A |
| Security self-test failure | Hard stop all agents | Immediate |
```

---

## Count Summary

| Priority | Count | Patterns |
|----------|-------|----------|
| P0 | 10 | Three-layer model, Allowlist, shlex.split, Fail-safe, PreToolUse hooks, Per-command validators, Command chaining, Base command extraction, Filesystem sandbox, Shell limits |
| P1 | 5 | Scratch isolation, Configurable limits, Env scrubbing, Self-test, Error classification |
| P2 | 2 | Sandbox profile, Audit log |
| **Total** | **17** | |

---

## Cross-Reference: Which autonomous-coding-src files were scanned

| File | Lines | Key patterns |
|------|-------|--------------|
| `autonomous-coding/security.py` | 1-360 | Allowlist, shlex, validators, segmentation, fail-safe |
| `autonomous-coding/client.py` | 1-123 | Three-layer model, PreToolUse hooks, permission sandbox |
| `autonomous-coding/test_security.py` | 1-291 | Self-test, blocked/allowed test cases |
| `autonomous-coding/agent.py` | 1-207 | Error classification, session lifecycle |
| `computer-use-best-practices/computer_use/tools/shell.py` | 1-137 | Sandbox execution, timeout, output cap, scratch dir |
| `computer-use-best-practices/computer_use/tools/editor.py` | 1-169 | Path traversal prevention (is_relative_to) |
| `computer-use-best-practices/constants.py` | 1-398 | Configurable security params, secret path blocking |
| `computer-use-best-practices/computer_use/tools/batch.py` | 1-106 | Batch execution (indirect: batch stopping on error) |
