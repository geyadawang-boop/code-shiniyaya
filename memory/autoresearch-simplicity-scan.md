# autoresearch-src Deep Scan — Simplicity / Single-File / Anti-Flood Patterns for code-shiniyaya STEP 2/6

cross-scan date: 2026-07-16
source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src
targets to improve: SKILL.md (STEP 2/6), anti-hang-v2.md, high-impact-patterns.md
dimensions: Simplicity criterion | Single-file scope | Redirect-all anti-flood

## P0 — Must Adopt (direct STEP 2/6 impact, low risk, high gain)

### Pattern 1: Formal Simplicity Criterion as STEP 2 Decision Gate

- **source**: `program.md:37`
- **exact text**: "Simplicity criterion: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome -- that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude. A 0.001 val_bpb improvement that adds 20 lines of hacky code? Probably not worth it. A 0.001 val_bpb improvement from deleting code? Definitely keep. An improvement of ~0 but much simpler code? Keep."
- **gap in code-shiniyaya**: STEP 2 (方案生成) has 3-agent comparison (最小更改/长期最优/最低风险) but NO formal simplicity check. A fix that adds 50 lines to fix a P2 cosmetic bug passes STEP 2 without scrutiny. STEP 6 (逐项执行) writes code blindly — no check for "does this fix over-complicate the code?"
- **why this matters for STEP 2/6**: Without a simplicity gate, every finding generates an additive fix (add code, add guards, add fallbacks). Over time, the codebase bloats. The Simplicity criterion forces the agent to prefer deletion-based fixes (remove dead code, simplify logic) and reject over-engineered solutions.
- **concrete fix for SKILL.md STEP 2 section** — insert after Phase D definition:

```
**Phase S — Simplicity Gate (new, runs BEFORE Phase A-D classification)**

Each generated fix must pass a 3-question simplicity check:

1. **Deletion-first**: Can this be fixed by removing code instead of adding?
   - YES → prefer deletion-based fix, annotate with `simplicity: removal`
   - NO → proceed to question 2

2. **Cost/Benefit**: fix_lines_added vs bug_severity
   - P0: ≤50 added lines per fix, OR justified with `simplicity: override-reason`
   - P1: ≤20 added lines per fix, OR downgrade to P2
   - P2: ≤5 added lines per fix, OR mark `simplicity: deferred` (defer to later)

3. **Net-zero check**: Does fix add same or fewer lines than it removes?
   - YES → `simplicity: net-zero-or-better` (always approved)
   - NO → must include `simplicity: justification` with explicit complexity trade-off

Fixes that fail the simplicity gate are NOT discarded — they are annotated `simplicity: needs-simplification` and the 3-agent comparison must find a simpler alternative. If no simpler alternative exists, the fix proceeds with `simplicity: override` and the justification is preserved.
```

- **concrete fix for SKILL.md STEP 6 section** — insert before "每次执行: 符号影响分析":

```
**Simplicity pre-check (before Edit/Write)**:

Before writing code, verify the actual diff matches the simplicity plan from STEP 2:
- If actual added lines > planned: abort, re-evaluate simplicity gate
- If fix could be deletion but you're adding code: abort, rewrite as deletion
- Net lines added > net lines removed + 10: warn user, require explicit approval

This is the `simplicity: enforce` gate — STEP 6 is the LAST chance to prevent unnecessary complexity from entering the codebase.
```

- **concrete fix for high-impact-patterns.md** — add as Pattern 19:

```markdown
### 模式 19: 正式简洁性准则作为方案决策门控 (autoresearch)

- **源**: autoresearch-src `program.md:37`
- **模式**: 每个改动前强制检查: 删除优先 / 成本收益比 / 净行数。拒绝过度工程化方案。
- **code-shiniyaya 差距**: STEP 2 无简洁性检查; STEP 6 盲写代码。
- **修复**: STEP 2 新增 Phase S(简洁性门控); STEP 6 新增简洁性预检查。
```

- **priority**: P0

---

### Pattern 2: Single-File Modification Scope as Hard Boundary

- **source**: `program.md:13-14` (setup section: "Read the in-scope files"), `program.md:26-27` ("What you CAN do: Modify `train.py` — this is the only file you edit. What you CANNOT do: Modify `prepare.py`. It is read-only.")
- **exact text**: "Modify `train.py` — this is the only file you edit." / "Modify `prepare.py`. It is read-only."
- **gap in code-shiniyaya**: STEP 6 has "符号影响分析" (symbol impact analysis) but NO hard file-count boundary. A single "fix" can touch 5+ files without warning. The only limit is rule 10 (方案锁定: files must be listed in plan), but the plan itself can list arbitrarily many files.
- **why this matters for STEP 2/6**: Multi-file fixes are the #1 cause of plan-code gaps, state corruption, and review fatigue. Autoresearch proves that constraining to ONE editable file forces simpler, more focused fixes and makes `git diff --stat` trivial to verify.
- **concrete fix for SKILL.md STEP 2 section** — insert after Phase D definition:

```
**Scope constraint (new, applied during Phase classification)**

Each fix plan must declare `scope.files_modified` with an explicit count:

- **Single-file (preferred)**: 1 file modified. Always approved for Phase A/B.
- **Sibling (acceptable)**: 2-3 files in same directory/module. Requires `scope.reason`.
- **Dispersed (requires justification)**: 4+ files across directories. Requires `scope.justification` + user override at STEP 5 gate.

Scope declared at STEP 2 is ENFORCED at STEP 6: any file Write/Edit outside the declared set triggers Rule 10 (方案偏离 → 新方案+重双批准). This closes the gap where agents drift from 2 files to 5 files during execution.

For P2 fixes: Single-file ONLY. No sibling or dispersed scope permitted.
```

- **concrete fix for high-impact-patterns.md** — add as Pattern 20:

```markdown
### 模式 20: 单文件修改范围为硬边界 (autoresearch)

- **源**: autoresearch-src `program.md:26-27`
- **模式**: Agent 只能编辑一个文件(train.py), 其他文件只读。强制聚焦+简化审查。
- **code-shiniyaya 差距**: STEP 6 无文件数量限制, 单次修复可触及5+文件。
- **修复**: STEP 2 新增 scope.files_modified 字段; STEP 6 强制执行文件边界。
```

- **priority**: P0

---

### Pattern 3: Redirect-All Anti-Flood Strategy (stdout→log, grep-only key metrics)

- **source**: `program.md:97-101`
- **exact text**: "Run the experiment: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)" / "Read out the results: `grep \"^val_bpb:\\|^peak_vram_mb:\" run.log`" / "If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace"
- **gap in code-shiniyaya**: STEP 6 runs fixes and expects agents to return results. But agent stdout can be MASSIVE (verbose build logs, lint output, test output). There's NO redirect-all pattern — agents dump everything into the conversation context. Anti-hang-v2.md's inline log() approach sends structured messages but doesn't prevent verbose tool output from flooding.
- **why this matters for STEP 6**: A single `npm test` run can produce 10,000+ lines of output. A single `pip install` can produce 500+ lines. These fill the context window and cause the agent to lose earlier diagnostic context. The redirect-all pattern ensures only KEY METRICS enter the conversation.
- **concrete fix for anti-hang-v2.md** — insert after section "1. Inline Progress via log()":

```
### 1.5 Redirect-All Agent Output (Anti-Flood, from autoresearch)

Agent commands that produce >50 lines of output MUST redirect to a log file:

```
# CORRECT — redirect everything, grep only key results
Bash: "npm test > test-output.log 2>&1"
Bash: "grep -E 'Tests:.*failed|Test Suites:.*failed' test-output.log"
# Only if grep returns nothing (crash):
Bash: "tail -n 30 test-output.log"

# WRONG — lets output flood the conversation
Bash: "npm test"
```

**Three-tier output handling**:
1. **Tier 1 — Key metrics only (default)**: Redirect to file → grep for structured summary → CC reads only grep output
2. **Tier 2 — Tail on failure**: If Tier 1 returns empty (crash/timeout) → `tail -n 30 <logfile>` for stack trace
3. **Tier 3 — Full read (rare)**: Only when debug needs full context → Read the log file directly (not via stdout)

**What qualifies**: Any command where (a) compile/build output, (b) test suite output, (c) lint output >50 lines, (d) package install output. Rule of thumb: if it can fill more than half the visible conversation pane, redirect it.

**What does NOT redirect**: `grep`, `git diff --stat`, single-file Read, `ast.parse` — these are inherently scoped.
```

- **concrete fix for SKILL.md STEP 6 section** — insert before "每次执行":

```
**Tier-1 output (anti-flood, from autoresearch pattern)**

All execution commands use redirect+grep, not raw stdout:
- Build: `npm run build > build.log 2>&1` then `grep -E 'error|Error|ERROR' build.log`
- Test: `pytest > test.log 2>&1` then `grep -E 'passed|failed|error' test.log`
- Lint: `eslint . > lint.log 2>&1` then `grep -E 'error|warning' lint.log`

Only key metrics enter conversation context. Full output stays on disk. If grep returns nothing → command crashed → `tail -n 30 <logfile>`.
```

- **concrete fix for high-impact-patterns.md** — add as Pattern 21:

```markdown
### 模式 21: Redirect-All 反洪水策略 (autoresearch)

- **源**: autoresearch-src `program.md:97-101`
- **模式**: 所有命令输出重定向到文件 → grep 提取关键指标 → 仅 grep 结果进入对话上下文。
- **code-shiniyaya 差距**: STEP 6 执行命令直接输出到对话, 大量构建/测试输出淹没上下文。
- **修复**: anti-hang-v2.md 新增三层输出处理; SKILL.md STEP 6 新增 Tier-1 输出规范。
```

- **priority**: P0

---

## P1 — Should Adopt (strong benefit, moderate effort)

### Pattern 4: Git as Advance/Rewind State Machine for Fix Execution

- **source**: `program.md:91-105`
- **exact text**: "If val_bpb improved (lower), you 'advance' the branch, keeping the git commit. If val_bpb is equal or worse, you git reset back to where you started."
- **gap in code-shiniyaya**: STEP 6 uses `git diff --stat`+`grep -n` for verification but has no automatic rollback. If a fix is wrong, there's no mechanical undo — the plan just says "新方案+重双批准" (new plan + re-approval), but the broken code is already in the working tree. Rule 10 requires a new plan but doesn't clean up the bad state.
- **why this matters for STEP 6**: Automatic `git checkout -- <file>` on failed verification prevents broken code from accumulating in the working tree. Makes iteration faster — no manual cleanup between attempts.
- **concrete fix for SKILL.md STEP 6 section** — insert after "失败":

```
**Git-based rollback on failure**

Each fix execution follows the advance/rewind pattern:

1. `git stash` before starting fix (save clean state)
2. Execute fix (Edit/Write)
3. Verify (ast.parse + git diff --stat + grep -n)
4. IF verification PASSES → `git add <files>` → advance
5. IF verification FAILS → `git checkout -- <files>` → rewind to clean state
6. `git stash pop` only after step 4 PASSES (restore unrelated changes)

This ensures the working tree is NEVER left in a broken state after a failed fix. No manual cleanup needed between fix attempts.

**Trivial-error exception** (from autoresearch crash taxonomy):
Typos, missing imports, syntax errors → fix the trivial error and re-verify WITHOUT rewinding. These don't count toward the 3-failure limit (Rule 12).
```

- **concrete fix for high-impact-patterns.md** — add as Pattern 22:

```markdown
### 模式 22: Git 作为进退状态机 (autoresearch — STEP 6 特化)

- **源**: autoresearch-src `program.md:91-105`
- **模式**: 每次修复: git stash → 修改 → 验证。通过→git add 推进。失败→git checkout 回退。
- **code-shiniyaya 差距**: STEP 6 失败后无法自动回退, 错误代码残留工作树。
- **修复**: STEP 6 新增 git stash/checkout 自动回退机制; 琐碎错误豁免不消耗重试配额。
```

- **priority**: P1

---

### Pattern 5: Structured Output Summary Block (grep-able delimiter format)

- **source**: `program.md:43-57` + `train.py:621-630`
- **exact text** (program.md): "Once the script finishes it prints a summary like this: `---` / `val_bpb:          0.997900` / `training_seconds: 300.1` / ..." / "You can extract the key metric from the log file: `grep \"^val_bpb:\" run.log`"
- **exact text** (train.py): Lines 621-630 — the `print("---")` delimiter followed by key:value pairs
- **gap in code-shiniyaya**: STEP 6 verification produces unstructured text output. `git diff --stat` is parseable but the surrounding verification output (ast.parse results, encoding checks, file size checks) is free-form text. No standardized grep-able summary format.
- **why this matters for STEP 6**: When running fixes in iteration, CC needs to quickly extract "did this fix pass or fail?" Without a grep-able summary block, CC must read and interpret free-form text on every iteration, which is error-prone.
- **concrete fix for SKILL.md STEP 6 section** — insert after "反馈→确认→继续":

```
**Standard fix-execution summary block**

After every fix execution, output a grep-able summary:

```
---
fix_id:           bug-03
status:           PASS | FAIL | PARTIAL
ast_parse:        ok | error:<msg>
git_diff_files:   2
git_diff_added:   15
git_diff_removed: 8
encoding:         utf-8
simplicity_net:   -3 (removal win)
verification:     ok | error:<msg>
---
```

CC extracts via: `grep "^status:\|^fix_id:" fix-output.log`
FAIL → triggers git rollback (Pattern 22)
PARTIAL → partial rollback, escalate to user
```

- **priority**: P1

---

### Pattern 6: Explicit In-Scope File Declaration at Setup (read-before-edit contract)

- **source**: `program.md:13-14`
- **exact text**: "Read the in-scope files: The repo is small. Read these files for full context: `README.md` — repository context. `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. Do not modify. `train.py` — the file you modify."
- **gap in code-shiniyaya**: STEP 0 (三Skill前置) runs using-superpowers + openspec-explore but never declares `scope.in_scope_files[]` vs `scope.readonly_files[]`. STEP 1 reads source files opportunistically, without declaring upfront what the diagnostic boundary is. This causes scope creep during STEP 6 — agents discover "related" files mid-execution and expand the fix beyond the plan.
- **why this matters for STEP 2**: If STEP 2 declares the in-scope file list explicitly, STEP 6 has a concrete boundary to enforce. The "read-only" file list from autoresearch is especially powerful — it says "you MAY read these for context but MUST NOT edit them."
- **concrete fix for SKILL.md STEP 2 section** — insert after the scope constraint (Pattern 2):

```
**In-scope declaration (from autoresearch setup pattern)**

Each fix plan declares two file lists:

- `scope.in_scope`: Files the fix MAY modify (enforced at STEP 6)
- `scope.readonly`: Files the fix MAY read for context but MUST NOT edit (enforced at STEP 6)

Any file NOT in either list is out-of-scope: do not read, do not reference, do not depend on.

This contract is set at STEP 2 and enforced at STEP 6. Reading a file outside scope → Rule 10 violation. Editing a readonly file → Rule 10 violation + automatic rollback.
```

- **priority**: P1

---

### Pattern 7: Fixed Budget Per Fix (time-equivalent via attempt cap)

- **source**: `program.md:22` + `train.py` line 30 (`TIME_BUDGET = 300`)
- **exact text**: "training runs for a fixed 5-minute time budget (wall clock, excluding startup/compilation)"
- **gap in code-shiniyaya**: STEP 6 has no budget per fix. A single fix can consume unlimited agent calls and user turns. The only limit is Rule 12 (3同文件失败→停止), but a fix that keeps "trying different approaches" on the same file can burn through 10+ attempts before hitting the 3-failure limit (if each attempt is on a different line/function).
- **why this matters for STEP 6**: Without a budget, complex fixes can stall the entire pipeline. A fixed attempt budget per fix (e.g., max 3 attempts per fix, max 2 approaches per fix) ensures the pipeline keeps moving.
- **concrete fix for SKILL.md STEP 6 section** — insert after "前置(执行前)":

```
**Fix budget (per fix, from autoresearch fixed-time-budget pattern)**

Each individual fix has a hard attempt cap:

- P0: max 3 attempts (different approaches), max 5 Edit/Write calls per attempt
- P1: max 2 attempts, max 3 Edit/Write calls per attempt
- P2: max 1 attempt, max 2 Edit/Write calls per attempt

Attempt = one complete fix-try cycle (modify → verify → feedback). If all attempts exhausted → mark FAILED_FIXES.md + move to next fix immediately.

This is SEPARATE from Rule 12 (3次同文件失败→STOP). Rule 12 is per-file across ALL fixes. Fix budget is per-fix across approaches. Both apply simultaneously — whichever triggers first wins.
```

- **priority**: P1

---

## P2 — Consider Adopting (nice to have, context-dependent)

### Pattern 8: Branch-per-Iteration Isolation (namespace via git branches)

- **source**: `program.md:2,9`
- **exact text**: "Agree on a run tag: propose a tag based on today's date (e.g. `mar5`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run." / "Create the branch: `git checkout -b autoresearch/<tag>` from current master."
- **gap in code-shiniyaya**: code-shiniyaya uses file-based session isolation (sessionId[:8] in filenames) but doesn't use git branches for iteration isolation. Multiple fix iterations happen on the same branch, making `git diff --stat` harder to interpret (which changes belong to which fix?).
- **why this matters**: For complex multi-fix sessions, branch-per-fix isolation makes rollback trivial and makes the git history self-documenting. But this adds git branch management overhead — hence P2.
- **concrete fix for SKILL.md STEP 6 section**:

```
**Optional: branch-per-fix isolation (for ≥3 P0 fixes)**

When session has ≥3 P0 fixes: create `fix/{sessionId[:8]}/{bug-id}` branch per fix.
Merge back to session branch only after verification passes.
This isolates each fix's git history and makes parallel P0 fixes safe.
```

- **priority**: P2

---

### Pattern 9: Structured Results Logging per Iteration (TSV-format audit trail)

- **source**: `program.md:64-89`
- **exact text**: TSV format: "commit \t val_bpb \t memory_gb \t status \t description" / statuses: keep, discard, crash
- **gap in code-shiniyaya**: Iteration scanning workflow produces scan-state-{iter}.json (complex nested JSON) but no lightweight per-iteration audit trail. The TSV format is simple to append, grep, and plot.
- **why this matters**: For long-running sessions (50+ fix iterations), a TSV log is easier to scan than JSON state files. But JSON state files serve a different purpose (recovery), so this is additive, not replacement.
- **concrete fix for anti-hang-v2.md**:

```
### 6. Per-Iteration TSV Log (lightweight audit, from autoresearch)

For sessions with ≥5 iterations, maintain `iterations-{sessionId[:8]}.tsv`:

```
iter	fixes_attempted	fixes_passed	fixes_failed	critical_before	critical_after	convergence_rate	duration_min
1	3	2	1	5	3	40.0	2.1
2	2	1	1	3	2	33.3	1.5
```

Append-only. One line per iteration. CC appends after each iteration completes.
```

- **priority**: P2

---

### Pattern 10: NEVER STOP — Autonomous Loop Declaration

- **source**: `program.md:111-112`
- **exact text**: "NEVER STOP: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask 'should I keep going?' or 'is this a good stopping point?'. The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous."
- **gap in code-shiniyaya**: code-shiniyaya's iteration scanning workflow waits for user input at each iteration boundary. There's no "autonomous mode" declaration. The silence threshold (N=4) handles Codex silence but doesn't handle "CC should keep iterating without asking."
- **why this matters**: For automated overnight fix sessions, the agent should NOT pause to ask "continue?" after each iteration. This pattern was already captured as Pattern #9 in high-impact-patterns.md but the concrete integration into STEP 6's iteration loop is missing.
- **concrete fix for SKILL.md STEP 6 section** — add to iteration loop description:

```
**Autonomous iteration mode (from autoresearch "NEVER STOP" pattern)**

When user says "自动迭代" / "auto-iterate" / "keep going" / "继续修复不要停":
- CC enters autonomous mode: after completing one fix, immediately start the next WITHOUT asking
- Only stop on: (a) all fixes done, (b) Rule 12 trigger (3同文件失败), (c) CR < 0 twice (convergence failure)
- Every 5 fixes: brief summary message (not a permission request)
- User can interrupt at any time with "stop" / "暂停" / "停"

Session JSON tracks: `autonomousMode: true|false`, `autonomousStartedAt: ISO`
```

- **priority**: P2

---

## Cross-Cutting Patterns (affect both STEP 2 and STEP 6)

### Pattern 11: Results.tsv as Shared Truth Between Planning and Execution

- **source**: `program.md:64-89` + `.gitignore:23` (`results.tsv`)
- **exact text**: "Record the results in the tsv (NOTE: do not commit the results.tsv file, leave it untracked by git)"
- **gap in code-shiniyaya**: STEP 2 writes FOR_CODEX reports; STEP 6 writes FAILED_FIXES.md and STOP_LOG.md. But there is NO single file that records what was planned vs what actually happened. The plan and the execution results live in separate files.
- **why this matters**: When recovering from interruption, CC must read both the plan file and the execution log files to reconstruct state. A single `fix-results-{sessionId}.tsv` would make recovery trivial.
- **concrete fix** — add to both STEP 2 and STEP 6:

```
**Shared fix-results TSV (plan→execution bridge)**

`fix-results-{sessionId[:8]}.tsv` — created at STEP 2, updated at STEP 6:

```
bug_id	fix_id	phase	files_modified	status	attempts	verification	result
B-01	F-01	A	1	done	1	PASS	net -3 lines
B-02	F-02	A	2	failed	3	FAIL	rollback, needs-replan
B-03	F-03	B	1	pending	0	-	-
```

STEP 2 writes rows with status=pending. STEP 6 updates status+verification+result. Git-ignored (like resultados.tsv).
```

- **priority**: P2

---

## Integration Map: Which Pattern Goes Where

| Pattern | SKILL.md | anti-hang-v2.md | high-impact-patterns.md |
|---------|----------|-----------------|-------------------------|
| 1. Simplicity Criterion | STEP 2 (Phase S) + STEP 6 (pre-check) | — | Pattern 19 |
| 2. Single-File Scope | STEP 2 (scope constraint) + STEP 6 (enforcement) | — | Pattern 20 |
| 3. Redirect-All Anti-Flood | STEP 6 (Tier-1 output) | Section 1.5 | Pattern 21 |
| 4. Git Advance/Rewind | STEP 6 (rollback) | — | Pattern 22 |
| 5. Summary Block Format | STEP 6 (fix-output block) | — | Pattern 23 |
| 6. In-Scope Declaration | STEP 2 (scope.in_scope + scope.readonly) | — | Pattern 24 |
| 7. Fix Budget Per Fix | STEP 6 (fix budget) | — | Pattern 25 |
| 8. Branch-per-Fix | STEP 6 (optional isolation) | — | Pattern 26 |
| 9. TSV Results Log | — | Section 6 | Pattern 27 |
| 10. NEVER STOP | STEP 6 (autonomous mode) | — | Pattern 28 |
| 11. Shared Fix-Results TSV | STEP 2 + STEP 6 | — | Pattern 29 |

## Key Design Insight from autoresearch

The autoresearch project's power comes NOT from complex orchestration but from THREE simple constraints that compound:

1. **One file to edit** → eliminates scope creep
2. **One metric to optimize** (val_bpb) → eliminates multi-objective confusion
3. **One fixed budget** (5 min) → makes all experiments directly comparable

For code-shiniyaya STEP 2/6, the equivalent compounding constraints would be:

1. **One fix = one file** (whenever possible) → eliminates multi-file plan drift
2. **One verification metric** per fix (ast.parse PASS + diff within plan ±5 lines) → eliminates verification ambiguity
3. **One attempt budget** per fix (3 for P0, 2 for P1, 1 for P2) → keeps the pipeline moving

These three, applied together at STEP 2 and enforced at STEP 6, would transform code-shiniyaya's execution reliability more than any single complex feature.
