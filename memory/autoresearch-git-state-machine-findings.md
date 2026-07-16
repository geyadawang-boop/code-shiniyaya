# autoresearch Git State Machine Patterns — Gap Analysis for code-shiniyaya

Source project: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src
Dimension: Git state machine: commits as state units, keep/reset decision, branch-per-run isolation
Scan date: 2026-07-16
Scanner: CC deep-scan (program.md, train.py, prepare.py, .gitignore, analysis.ipynb, README.md)

---

## Source Context

autoresearch (by @karpathy) is a fully autonomous LLM training experiment loop where an AI agent modifies `train.py`, runs a 5-minute training job, checks if val_bpb improved, and either keeps (git commit) or discards (git reset) each experiment. The git DAG itself IS the state machine — no JSON state files, no journal parsers, no progress trackers. Every experiment is one clean commit.

---

## Pattern Inventory (23 patterns extracted from autoresearch-src)

### DIMENSION A: Git as State Machine (program.md:91-105)

**A1. Commits as experiment units** (program.md:94-104, 8 lines)
```
LOOP FOREVER:
  1. Look at git state: current branch/commit
  2. Modify code with experimental idea
  3. git commit
  4. Run experiment
  5. Read results via grep
  6. Record in results.tsv (UNTRACKED)
  7. If improved → keep commit (advance branch)
  8. If equal/worse → git reset back to previous commit
```
Each experiment = exactly one git commit. The commit message IS the description. The commit hash IS the experiment ID. No need for a separate session-*.json state file — the git DAG stores state.

**A2. Binary keep/reset decision** (program.md:103-104)
Single rule: val_bpb improved → keep (branch advances). val_bpb equal or worse → `git reset` to previous HEAD. No partial keep, no conditional approval, no multi-dimensional scoring. One metric, binary decision, instant action.

**A3. Branch-per-run isolation** (program.md:92)
`autoresearch/<tag>` naming. Each run gets its own branch. If multiple GPUs: `autoresearch/<tag>-gpu0`, `autoresearch/<tag>-gpu1`. Complete filesystem isolation, no JSON-based session collision tracking needed.

**A4. Branch existence pre-flight check** (program.md:9)
"The branch `autoresearch/<tag>` must not already exist — this is a fresh run." Simple guard: branch name collision = run rejected. No 65K-concurrency-birthday-paradox math needed (SKILL.md line 163).

**A5. Reset sparingly, only when stuck** (program.md:106)
"If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever)." The primary mechanism is FORWARD iteration. Reset is exceptional, not the default.

### DIMENSION B: Results Logging (program.md:64-88)

**B1. Persistent flat-file results log** (program.md:67-88)
`results.tsv` — tab-separated, 5 columns: commit, val_bpb, memory_gb, status, description. Every experiment logged, including crashes (val_bpb=0.000000, memory_gb=0.0, status=crash). This is a chronological audit trail, not a state file.

**B2. Untracked results file** (program.md:102)
"do not commit the results.tsv file, leave it untracked by git." The code changes are git-tracked; the results metadata is git-untracked. This keeps commit history clean (only code changes) while preserving a full experiment log on disk.

**B3. Three-state outcome taxonomy** (program.md:77, 87)
Only 3 possible statuses: `keep`, `discard`, `crash`. No partial/conditionally-approved/interrupted/degraded states. Simplicity ensures the agent never gets confused about what to do next.

**B4. Crash distinction: 0.000000 sentinel** (program.md:75, 87)
Crashes use sentinel values (val_bpb=0.000000, memory=0.0) instead of a separate column or absent rows. Makes filtering and analysis trivial.

### DIMENSION C: Experiment Execution (program.md:97-109, train.py)

**C1. Output redirection + grep extraction** (program.md:99-100)
`uv run train.py > run.log 2>&1` — all output to file. `grep "^val_bpb:\|^peak_vram_mb:" run.log` — extract only the 2 metrics needed. Context window is never flooded with training logs.

**C2. Crash recovery: tail + fix or skip** (program.md:101)
"If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix." Fixed diagnosis budget: 50 lines, 1 grep. No multi-agent diagnostic scan.

**C3. Fast-fail abort in running code** (train.py:570-572)
```python
if math.isnan(train_loss_f) or train_loss_f > 100:
    print("FAIL")
    exit(1)
```
The process detects its own divergence and exits immediately. This is NOT an agent decision — it's embedded in the running code. The agent just reads the exit code/grep output.

**C4. Fixed time budget** (program.md:23, prepare.py:31)
`TIME_BUDGET = 300` (5 minutes). Every experiment has the same wall-clock budget regardless of what the agent changes. This makes experiments directly comparable and bounds worst-case agent wait time.

**C5. Timeout kill** (program.md:108)
"If a run exceeds 10 minutes, kill it and treat it as a failure." Double the normal budget as a safety net. No exponential backoff, no retry loop — just kill and move on.

### DIMENSION D: Scope Constraint (program.md:26-31)

**D1. Single-editable-file constraint** (program.md:26, README.md:14)
Agent can ONLY modify `train.py`. `prepare.py` is read-only. This removes entire categories of errors: cross-file inconsistencies, import chain breaks, evaluation harness corruption.

**D2. Immutable evaluation harness** (program.md:31, prepare.py:27)
"The `evaluate_bpb` function in `prepare.py` is the ground truth metric." The evaluation is sacred — the agent can change anything about how it trains but NOT how success is measured. This prevents metric hacking.

**D3. Package freeze** (program.md:30, pyproject.toml)
"Install new packages or add dependencies. You can only use what's already in `pyproject.toml`." No dependency drift, no import errors from missing packages.

### DIMENSION E: Agent Autonomy (program.md:112-113)

**E1. NEVER STOP instruction** (program.md:112)
"do NOT pause to ask the human if you should continue. Do NOT ask 'should I keep going?' or 'is this a good stopping point?'" The agent runs indefinitely until manually interrupted. No checkpoint approvals, no "continue?" prompts, no per-experiment confirmation.

**E2. Idle-time optimization** (program.md:113-114)
"As an example use case, a user might leave you running while they sleep. If each experiment takes you ~5 minutes then you can run approx 12/hour, for a total of about 100 over the duration of the average human sleep." The system is designed for unattended operation with predictable throughput.

**E3. Simplicity criterion** (program.md:37)
"A 0.001 val_bpb improvement that adds 20 lines of hacky code? Probably not worth it. An improvement of ~0 but much simpler code? Keep." The agent is instructed to value code simplicity alongside metric improvement.

### DIMENSION F: Analysis (analysis.ipynb)

**F1. Cumulative minimum frontier** (cell 79jh74veqg9)
`running_min = kept_bpb.cummin()` — tracks the best result achieved at any point, forming a monotonic improvement curve. code-shiniyaya has CR (convergence rate) but no cumulative-minimum frontier tracking.

**F2. Delta vs previous kept** (cell q86hxu10djk)
Each improvement is measured as the delta from the previous kept experiment, NOT from the baseline. This means the metric captures incremental contribution, not absolute distance from start.

**F3. Keep rate as efficiency metric** (cell 0v37bji707o)
`n_keep / (n_keep + n_discard)` — what fraction of experiments actually improved the result? This is the primary agent-efficiency metric. code-shiniyaya has no equivalent efficiency metric.

---

## Gap Analysis: What code-shiniyaya Lacks

### GAP 1 (P0) — Git commits as fix iteration units, replacing journal-parser for simple fixes

**What code-shiniyaya has today:**
- JSON state files (session-*.json, pending-*.json, dag-*.json) track fix progress
- journal.jsonl parsed by journal-parser.py for workflow recovery
- `git diff --stat` + `grep -n` used as verification step (rule 9), not as iteration unit
- CR (convergence rate) tracks aggregate improvement

**What autoresearch does:**
Each fix = one atomic git commit. No journal files. No JSON state. The git DAG IS the state:
```
git commit -m "fix: {bug-id}: {change description}"
run verification
if fix works → keep commit, advance branch
if fix fails/equal → git reset HEAD~1
```

**Benefit for code-shiniyaya:**
- STEP 6 execution becomes `git commit → verify → keep/reset` instead of manual diff verification
- Atomic rollback: `git reset` undoes a bad fix in one command instead of manual undo
- Native audit trail: `git log` shows every fix attempt with commit message as description
- Crash recovery: branch state is the committed state — no "lastFileHash" checks needed
- Eliminates journal-parser.py dependency for simple fix iterations

**Specific code-shiniyaya gap:**
The high-impact-patterns.md (lines 58-59) already references this as "Pattern 2: Git状态机" but describes it only as "替代journal-parser用于简单修复" — it doesn't show the concrete mechanism of commit-as-fix-unit with keep/reset, which is the heart of the pattern.

### GAP 2 (P0) — Branch-per-fix-session isolation

**What code-shiniyaya has today:**
- Session ID-based file naming: `{sessionId[:8]}` in filenames for concurrency
- "65K concurrent sessions birthday paradox ≈ 50%" analysis (SKILL.md:163)
- Conflict detection via versionVector comparison (SKILL.md:164)

**What autoresearch does:**
Each run = dedicated git branch (`autoresearch/<date-tag>`):
- Complete filesystem isolation — zero collision risk
- Branch existence check blocks accidental overwrite (program.md:9)
- GPU-suffix variants for parallel runs (`autoresearch/mar5-gpu0`)
- Branch history is the run history — no versionVector, no checksum verification

**Benefit for code-shiniyaya:**
- Replace session-ID-file-naming with branch-per-fix-session
- Zero collision risk (git won't let you create a branch that already exists)
- Branch creation is the pre-flight check — no need for versionVector or conflict.json files
- Parallel CC sessions each get their own branch — no shared-state corruption possible

### GAP 3 (P1) — Persistent fix log (results.tsv equivalent)

**What code-shiniyaya has today:**
- FAILED_FIXES.md for failed fixes
- STOP_LOG.md for 3-failures-same-file stops
- No persistent audit trail of EVERY fix attempt (success, failure, skipped)

**What autoresearch does:**
`results.tsv` logs every single experiment with 5 columns:
```
commit    val_bpb    memory_gb    status    description
```
Three categories cover everything: `keep`, `discard`, `crash`.
File is deliberately UNTRACKED by git — results metadata is separate from code history.

**Benefit for code-shiniyaya:**
- Chronological audit trail of every fix attempt
- Analysis: keep rate, cumulative improvement, most impactful fixes
- Crash entries prevent repeated attempts of same broken approach
- Flat file — no parsing, no JSON schema, readable by humans and pandas

### GAP 4 (P1) — Output redirection + grep extraction

**What code-shiniyaya has today:**
- Agent output streams through the conversation
- Some agents log to journal.jsonl
- No pattern for redirecting agent output to file + extracting only needed fields

**What autoresearch does:**
`uv run train.py > run.log 2>&1` — redirect ALL output.
`grep "^val_bpb:\|^peak_vram_mb:" run.log` — extract exactly 2 metrics.
Context window stays clean; only the metrics enter the conversation.

**Benefit for code-shiniyaya:**
- Agent scan output goes to file, not conversation
- CC extracts only findings count, severity distribution, P0 list
- Drastically reduces token consumption in large agent scans
- Applicable to STEP 1 diagnostics and STEP 4 Codex verification

### GAP 5 (P1) — Fast-fail self-abort in verification scripts

**What code-shiniyaya has today:**
- Verification: `ast.parse`, `git diff --stat`, `grep -n` — but all run AFTER the fix is written
- No embedded self-abort logic in verification scripts

**What autoresearch does:**
The training script itself detects failure (NaN loss, loss>100) and calls `exit(1)` before wasting more time. The agent never sees the 5 minutes of garbage output — it gets a clean FAIL signal.

**Benefit for code-shiniyaya:**
- Verification scripts can self-abort: `git diff --stat` shows 0 files changed → exit 1 immediately
- Syntax check fails → exit 1 immediately, don't continue to the next check
- Saves agent context from processing irrelevant verification output

### GAP 6 (P2) — NEVER STOP / indefinite autonomy

**What code-shiniyaya has today:**
- Per-step user confirmation gates
- "stop/中断/CTRL+C → 立即停" stop line (rule 13)
- Silent threshold N=4 → ask user "继续等/跳过?"

**What autoresearch does:**
"NEVER STOP: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue."

**Benefit for code-shiniyaya:**
- Minor pattern: for iterative scanning workflows specifically, suppress "continue?" prompts
- code-shiniyaya already has this in the 迭代扫描工作流 section (lines 411-434) but it's scoped to agent workflows, not to the fix-iteration loop

### GAP 7 (P2) — Single-editable-file constraint for agent scope

**code-shiniyaya has:** Plan-Code Gap rules (rules 9-10) that detect when a fix modifies unexpected files. This is reactive — the gap is detected after the fact.

**autoresearch has:** A proactive constraint — the agent is explicitly told it can ONLY edit `train.py`. This prevents entire categories of errors before they happen.

**Benefit:** For STEP 6 per-item execution, code-shiniyaya could optionally scope individual fix agents to a single target file, removing the need for Plan-Code Gap detection entirely for those items.

### GAP 8 (P2) — Cumulative minimum frontier tracking

**code-shiniyaya has:** CR (convergence rate) = `(CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1}` — this tracks per-iteration change but doesn't track the all-time best result.

**autoresearch has:** `running_min = kept_bpb.cummin()` — a monotonic curve showing the best result achieved so far. This is the real "are we making progress?" metric, not the per-step delta.

**Benefit:** Add a `best_so_far` field to the convergence tracking in SKILL.md line 431-433 to complement CR.

---

## Concrete Fixes

### Fix 1: Add "Git as Iteration State Machine" to STEP 6 (SKILL.md, P0)

**File to modify:** C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md
**Location:** After line 282 (STEP 6 header), before line 283 (DAG pre-work)

**Text to add:**

```markdown
### STEP 6.0 — Git State Machine Mode (optional, for independent fixes)

When all pending items are independent (no shared files, no DAG edges), use git as the iteration state machine instead of manual tracking:

1. **Pre-flight**: `git rev-parse --verify fixes/{sessionId[:8]}` — branch must not exist
2. **Create branch**: `git checkout -b fixes/{sessionId[:8]}`
3. **Fix loop** (for each item):
   a. `git commit -m "fix({bug-id}): {description}"` — each fix = one atomic commit
   b. Run verification (`ast.parse`, tests, `grep -n` confirmation)
   c. If verification passes → keep commit, advance
   d. If verification fails → `git reset --hard HEAD~1`, retry or mark BLOCKED
4. **Log all attempts** to `.claude/memory/code-shiniyaya/fix-log-{sessionId[:8]}.tsv`:
   ```
   commit	bug_id	status	description
   a1b2c3d	BUG-01	keep	fix null deref in parser
   d4e5f6g	BUG-02	discard	wrong approach, retry
   h7i8j9k	BUG-03	crash	syntax error in fix
   ```
   This file is git-untracked (add to .gitignore).
5. **On completion**: merge branch back to original, `git branch -d fixes/{sessionId[:8]}`

**Decision rule**: Binary keep/reset — fix works → keep commit; fix fails → reset. No partial-keep states. Crashes logged with status=crash, 0 for any numeric columns.
```

### Fix 2: Add "Branch Isolation" to Session Isolation section (SKILL.md, P0)

**File to modify:** C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md
**Location:** After line 164 (end of session isolation section), before line 166 (core workflow header)

**Text to add:**

```markdown
### Git Branch Isolation (alternative to file-name session IDs)

For fix-execution sessions (STEP 6), use git branches instead of filename-based session IDs:

- **Branch naming**: `fixes/{sessionId[:8]}` — guaranteed unique by git
- **Pre-flight check**: `git rev-parse --verify fixes/{id}` exits non-zero = branch available
- **Parallel sessions**: Each CC session = one branch. Zero collision risk (enforced by git, not checksums)
- **Recovery**: Branch state IS the committed fix state. No `lastFileHash` recalculation needed.
- **Cleanup**: Merge then delete branch. If unresolved, branch remains as audit trail.

**tradeoff**: Branch isolation only works for independent fixes that don't share files. For interleaved fixes with DAG dependencies, use the existing session-*.json tracking (file-name based isolation).
```

### Fix 3: Add "Fix Outcome Log" to high-impact-patterns.md (high-impact-patterns.md, P1)

**File to modify:** C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
**Location:** After line 61 (end of integration priority table), before line 63 (new dimension section)

**Text to add:**

```markdown

## Git State Machine Patterns — Integration Detail (from autoresearch)

### Pattern 19: Fix Log TSV (Results Audit Trail)
- **Source**: `autoresearch-src/program.md:67-88`
- **Pattern**: Every fix attempt (success or failure) is logged to a tab-separated flat file with columns: commit, outcome, metric, status, description. File is git-untracked to keep repo history clean.
- **code-shiniyaya gap**: No persistent audit trail of EVERY fix attempt. FAILED_FIXES.md only captures final failures, not the full attempt history.
- **Fix**: Add `fix-log-{sessionId[:8]}.tsv` to `.claude/memory/code-shiniyaya/`, updated atomically after each fix attempt. Schema: `commit | bug_id | status(keep|discard|crash) | description`.
- **Priority**: P1

### Pattern 20: Commit-as-Iteration-Unit
- **Source**: `autoresearch-src/program.md:94-104`
- **Pattern**: Each experiment = one git commit. Commit message IS the description. Branch history IS the experiment log. `git reset` undoes a bad experiment.
- **code-shiniyaya gap**: STEP 6 uses manual `git diff --stat` + `grep -n` for verification, not git commits as iteration units. Pending item tracking uses JSON state files instead of branch history.
- **Fix**: For independent fixes: each fix = one commit. Branch `fixes/{sessionId[:8]}` tracks the fix lineage. Keep/reset based on verification pass/fail. This replaces journal-parser for simple fix workflows.
- **Priority**: P0 (already listed as Pattern 2 but without concrete mechanism)

### Pattern 21: Branch Existence Pre-flight
- **Source**: `autoresearch-src/program.md:9-10`
- **Pattern**: Before creating a new experiment branch, verify the branch name doesn't already exist. Simple guard prevents accidental overwrite of previous work.
- **code-shiniyaya gap**: Session ID collision analysis (SKILL.md:163) uses probabilistic reasoning. Git branch existence check is absolute — no math needed.
- **Fix**: Before creating `fixes/{id}` branch, run `git rev-parse --verify fixes/{id}`. Non-zero exit = branch available. Zero exit = different session ID needed.
- **Priority**: P1

### Pattern 22: Output Redirection for Context Efficiency
- **Source**: `autoresearch-src/program.md:99-100`
- **Pattern**: Redirect all process output to file (`> run.log 2>&1`), then grep only the specific metrics needed. Context window never flooded with raw output.
- **code-shiniyaya gap**: Agent results stream through conversation. Large diagnostic scans can flood context with hundreds of lines.
- **Fix**: For STEP 1 diagnostics and STEP 4 Codex verification, route agent output to `.claude/memory/code-shiniyaya/scan-output-{sessionId}.log` then grep for findings count, severity distribution, and P0 list only.
- **Priority**: P2

### Pattern 23: Fast-Fail Self-Abort in Running Code
- **Source**: `autoresearch-src/train.py:570-572`
- **Pattern**: The running process detects its own divergence and calls `exit(1)` immediately. The agent checks the exit code rather than parsing output for error patterns.
- **code-shiniyaya gap**: Verification is done by CC reading output — no embedded self-abort in verification scripts.
- **Fix**: Add fast-fail gates to verification scripts: `ast.parse` fails → `exit(1)`; diff empty → `exit(1)`; test fails → `exit(1)`. Agent checks exit code, not full output.
- **Priority**: P2

### Pattern 24: NEVER STOP — Suppress Per-Iteration Prompts
- **Source**: `autoresearch-src/program.md:112-113`
- **Pattern**: "do NOT pause to ask the human if you should continue." The agent runs indefinitely until manually interrupted. Designed for unattended overnight operation.
- **code-shiniyaya gap**: The 迭代扫描工作流 section (SKILL.md:411-434) has stall detection and user prompts. For unattended fix loops, these prompts should be suppressed.
- **Fix**: When STEP 6 is in git-state-machine mode, suppress "continue?" prompts. Only stop on: (a) all items complete, (b) 3 consecutive crashes same item, (c) user interrupt.
- **Priority**: P2

### Pattern 25: Cumulative Minimum Frontier
- **Source**: `autoresearch-src/analysis.ipynb` (cell 79jh74veqg9)
- **Pattern**: `running_min = kept_bpb.cummin()` — monotonic curve of best result achieved so far. Complement to per-step delta.
- **code-shiniyaya gap**: CR (convergence rate) tracks per-iteration change but doesn't track the all-time best state.
- **Fix**: Add `best_so_far` field to convergence tracking. When CRITICAL_n < previous best, update `best_so_far` and record the iteration that achieved it. Display as "Best: {best_so_far} (iteration {iter})".
- **Priority**: P2

### Pattern 26: Three-State Outcome Taxonomy
- **Source**: `autoresearch-src/program.md:77`
- **Pattern**: Only 3 statuses: keep, discard, crash. No partial, conditional, degraded, interrupted. Simplicity ensures agent never gets confused.
- **code-shiniyaya gap**: itemStates have status: "pending/in_progress/completed/blocked/interrupted/degraded" — 6+ states.
- **Fix**: For git-state-machine mode, reduce fix outcomes to 3: keep (verification passed), discard (verification failed, reset), crash (fix caused syntax error or 3+ retries).
- **Priority**: P2
```

---

## Integration Priority Summary

| # | Pattern | Source file:line | Priority | Target | Expected Impact |
|---|---------|-----------------|----------|--------|-----------------|
| 19 | Fix Log TSV | program.md:67-88 | P1 | high-impact-patterns.md | Full audit trail of fix attempts |
| 20 | Commit-as-Iteration-Unit | program.md:94-104 | P0 | SKILL.md STEP 6 | Replace journal-parser for simple fixes |
| 21 | Branch Existence Pre-flight | program.md:9-10 | P1 | SKILL.md session isolation | Zero-collision branch isolation |
| 22 | Output Redirection | program.md:99-100 | P2 | high-impact-patterns.md | Context efficiency for agent scans |
| 23 | Fast-Fail Self-Abort | train.py:570-572 | P2 | high-impact-patterns.md | Faster failure detection |
| 24 | NEVER STOP | program.md:112-113 | P2 | high-impact-patterns.md | Unattended fix loop support |
| 25 | Cumulative Minimum | analysis.ipynb cell 79jh74veqg9 | P2 | SKILL.md convergence tracking | Better progress visibility |
| 26 | Three-State Taxonomy | program.md:77 | P2 | high-impact-patterns.md | Simpler fix outcome model |

---

## Key Design Insight

The fundamental architectural difference: **autoresearch uses git as a state machine so it doesn't need JSON state files.** Every state transition is a git operation (commit, reset, branch). code-shiniyaya uses JSON state files to track identical state transitions (session-*.json, pending-*.json, dag-*.json). The git-native approach:

1. Eliminates journal-parser.py (branch history = experiment log)
2. Eliminates lastFileHash checks (git objects are content-addressed)
3. Eliminates versionVector conflict detection (git branches are isolated)
4. Eliminates checksum verification (git objects have built-in SHA-1)
5. Eliminates atomic write protocol (git operations are atomic)

**The tradeoff**: git branches work for independent fixes with clean boundaries. For deeply interleaved fixes with DAG dependencies that span files, JSON state files remain necessary. The optimal design is a hybrid: git-state-machine for independent fixes (80% of cases), JSON tracking for complex multi-file interleaved fixes (20% of cases).
