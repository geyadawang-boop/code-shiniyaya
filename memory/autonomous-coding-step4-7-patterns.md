# autonomous-coding STEP 4-7 Adoption Patterns for code-shiniyaya

**Date**: 2026-07-16
**Source**: `autonomous-coding-src` (Anthropic quickstarts — autonomous-coding/ directory)
**Target**: code-shiniyaya SKILL.md v3.7.0 STEP 4-7 + anti-hang-v2.md
**Scope**: Patterns NOT already in `autonomous-coding-gap-analysis.md` (7 dimensions already covered there). Focused on STEP 4 (Codex反馈交叉验证), STEP 5 (双批准门控), STEP 6 (逐项执行), STEP 7 (双向验证).

---

## Pattern 1: Mandatory Regression Gate Before New Work (P0)

### Source
`autonomous-coding/prompts/coding_prompt.md:48-67`

```markdown
### STEP 3: VERIFICATION TEST (CRITICAL!)

**MANDATORY BEFORE NEW WORK:**

The previous session may have introduced bugs. Before implementing anything
new, you MUST run verification tests.

Run 1-2 of the feature tests marked as `"passes": true` that are most core
to the app's functionality to verify they still work.

**If you find ANY issues (functional or visual):**
- Mark that feature as "passes": false immediately
- Add issues to a list
- Fix all issues BEFORE moving to new features
```

### code-shiniyaya Gap

STEP 4 (Codex反馈交叉验证) has 10+ agents verifying Codex's claims across 7 dimensions, but there is NO pre-STEP-4 regression check that verifies previously-agreed-upon fixes still hold. If a prior STEP 6 fix silently broke during another fix, STEP 4 agents won't detect it because they are verifying Codex's new claims, not existing state.

Similarly, STEP 6 has no "verify nothing broke before executing this fix" gate. Each fix is done in isolation via `git diff --stat` + `grep -n`, but there is no explicit "run the 1-2 most core passing items before touching anything" step.

### Concrete Fix

**Add to SKILL.md**, as a new sub-step in STEP 4 and STEP 6:

```markdown
### STEP 4.0 — Regression Gate (MANDATORY BEFORE VERIFICATION)

Before running 10+ Agent verification on Codex feedback, verify that
previously-fixed items still hold:

1. Read `pending-{sessionId[:8]}.json` — identify items marked "completed"
2. Pick the 2 most core items (highest severity + most files touched)
3. Re-run verification on these items:
   - `ast.parse` the fixed files
   - `grep -n` for the exact fix lines
   - If fix was a logic change: re-run the relevant test command
4. If ANY regression found:
   - Mark the completed item as `status: REGRESSED` in pending JSON
   - Write REGRESSION_LOG.md with file:line + what broke
   - Fix the regression BEFORE processing any Codex feedback
   - Re-request Codex review on the regression fix

This gate prevents: "Fix A works. Fix B breaks Fix A. Nobody notices
because all eyes are on Fix B."

### STEP 6.0.5 — Pre-Fix Regression Check (MANDATORY BEFORE EACH FIX)

Before executing each item in STEP 6:

1. Run `git diff --stat HEAD` — confirm working tree is clean from prior fix
2. Pick 1 previously-passing item that touches the same file(s)
3. Run its verification command (ast.parse, grep -n, test)
4. If FAILS → mark PREVIOUS item as REGRESSED → fix regression first
5. If PASSES → proceed with current fix

This is the code-shiniyaya equivalent of coding_prompt.md Step 3:
"verify previously-passing tests before new work."
```

**Priority: P0** — Without this gate, multi-fix sessions silently accumulate regressions.

---

## Pattern 2: Clean Exit Protocol Before Context Fill (P0)

### Source
`autonomous-coding/prompts/coding_prompt.md:151-158`

```markdown
### STEP 10: END SESSION CLEANLY

Before context fills up:
1. Commit all working code
2. Update claude-progress.txt
3. Update feature_list.json if tests verified
4. Ensure no uncommitted changes
5. Leave app in working state (no broken features)
```

And `coding_prompt.md:192-194`:
```markdown
**You have unlimited time.** Take as long as needed to get it right.
The most important thing is that you leave the code base in a clean
state before terminating the session (Step 10).
```

### code-shiniyaya Gap

STEP 6 execution is item-by-item with per-item feedback. But there is NO explicit "clean exit" protocol for when the session must end (context limit approaching, user says stop, etc.). The stop-line rules (13, 14) say "stop immediately on stop/interrupt/CTRL+C" but do not specify what constitutes a "clean state" to leave behind.

STEP 7 says "双方确认=完成" but has no pre-termination checklist. If context fills mid-STEP-6, items may be partially executed with no clean handoff.

### Concrete Fix

**Add to SKILL.md STEP 6**, after the execution loop:

```markdown
### STEP 6.99 — Clean Exit Protocol (MANDATORY before any session end)

Regardless of WHY the session ends (all items complete, context limit,
user stop, error), execute this checklist:

[ ] All successful fixes committed (git status clean on those files)
[ ] All FAILED_FIXES.md entries up to date
[ ] pending-{sessionId[:8]}.json saved with current item states
[ ] STOP_LOG.md written if triggered by Rule 12 (3x same-file failure)
[ ] Git working tree: `git status --porcelain` — any uncommitted changes
    MUST be either committed or documented in pending JSON as IN_PROGRESS
[ ] Next session resume point documented:
    - Current STEP number
    - Next item to execute (item id)
    - Mode: normal | degraded
[ ] If STEP 6.0 (git state machine mode): branch exists, all commits
    verified, fix-log-{sessionId}.tsv up to date

**The most important rule**: Leave the code base in a state where the
NEXT session can start from Step 1 (Get Your Bearings) without
irreversible corruption. If you cannot guarantee this, STOP and notify
the user immediately — do NOT attempt to "fix it a bit more."
```

**Add to SKILL.md STEP 7**, after the verification loop:

```markdown
### STEP 7.99 — Final Clean Handoff

After bidirectional verification completes (or degrades):

1. Write FINAL_STATE.md:
   ```markdown
   # Session {sessionId[:8]} Final State
   - Date: {ISO timestamp}
   - Mode: normal | degraded
   - Items completed: {count}
   - Items regressed: {count}
   - Items disputed: {count}
   - Next steps: {what remains}
   ```
2. All state files flushed + fsync'd (atomic write protocol)
3. Git branch: if STEP 6.0 mode, merge branch → delete branch
4. Report written to `{project_root}/reports/FINAL_{sessionId[:8]}.md`

The FINAL_STATE.md serves the same role as `claude-progress.txt` in
autonomous-coding: a single file the next session reads to understand
exactly where things left off.
```

**Priority: P0** — Without a clean exit protocol, interrupted sessions leave corrupted state.

---

## Pattern 3: Fresh-Context State Reconstruction (P1)

### Source
`autonomous-coding/prompts/coding_prompt.md:3-31`

```markdown
### STEP 1: GET YOUR BEARINGS (MANDATORY)

Start by orienting yourself:

# 1. See your working directory
pwd

# 2. List files to understand project structure
ls -la

# 3. Read the project specification to understand what you're building
cat app_spec.txt

# 4. Read the feature list to see all work
cat feature_list.json | head -50

# 5. Read progress notes from previous sessions
cat claude-progress.txt

# 6. Check recent git history
git log --oneline -20

# 7. Count remaining tests
cat feature_list.json | grep '"passes": false' | wc -l
```

### code-shiniyaya Gap

code-shiniyaya's "中断恢复" section says "读session JSON(mode+step+itemStates)→从断点STEP+项继续". This assumes the session JSON is accurate and complete. But if context was lost unexpectedly (crash, kill), the JSON state file may be stale or missing.

There is no "Get Your Bearings" protocol that reconstructs state from multiple independent sources (state files + git log + pending items + file hashes). The coding_prompt.md approach is more robust: read from multiple independent sources and cross-validate.

### Concrete Fix

**Add to SKILL.md**, in the "中断恢复" section:

```markdown
### 恢复: Get Your Bearings Protocol (MANDATORY)

When resuming after ANY interruption (stop, crash, context loss, degraded
mode transition), execute this orientation sequence BEFORE any action:

```
[1] Read session-{sessionId[:8]}.json → current STEP + itemStates
[2] Read pending-{sessionId[:8]}.json → list + status per item
    Cross-validate: count items in session JSON vs pending JSON
    Mismatch → HALT, report to user, do NOT proceed
[3] Read dag-{sessionId[:8]}.json → dependency edges
    Git rev-parse HEAD vs dag.snapshot → mismatch → rebuild DAG
[4] Run: git log --oneline -20
    If STEP 6.0 mode: git log fixes/{sessionId[:8]} --oneline
[5] Count: grep '"status": "completed"' pending-{id}.json
    = completed items
[6] Count: grep '"status": "in_progress"' pending-{id}.json
    = interrupted items → resume marker
[7] If exists: read STOP_LOG.md / FAILED_FIXES.md / REGRESSION_LOG.md
[8] If STEP 6.0 mode: git status --porcelain
    Uncommitted changes → commit or stash before proceeding

After orientation, state: "Resuming at STEP {N}, item {id}.
{N_done} items completed, {N_pending} remaining, {N_blocked} blocked.
Mode: {mode}. Last git commit: {hash}."
```

This ensures that even if the session JSON is corrupted or stale,
recovery state can be reconstructed from git + pending items + logs.
The orientation message serves the same role as coding_prompt.md's
"progress.txt" — a single snapshot of where things stand.
```

**Priority: P1** — Improves robustness of existing recovery mechanism. Existing session JSON is good but single-point-of-failure.

---

## Pattern 4: Progress Counting as Pre-Work Gate (P1)

### Source
`autonomous-coding/progress.py:11-37`

```python
def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    tests_file = project_dir / "feature_list.json"
    if not tests_file.exists():
        return 0, 0
    try:
        with open(tests_file, "r") as f:
            tests = json.load(f)
        total = len(tests)
        passing = sum(1 for test in tests if test.get("passes", False))
        return passing, total
    except (json.JSONDecodeError, IOError):
        return 0, 0
```

And `coding_prompt.md:30`:
```bash
cat feature_list.json | grep '"passes": false' | wc -l
```

### code-shiniyaya Gap

STEP 4 launches 10+ agents with no pre-count of what state they're verifying against. STEP 6 executes items one-by-one but never produces a "progress count" summary between items. The only progress tracking is in `itemStates` within session JSON — which is CC-internal, not surfaced as a regular "X/Y done" count.

The autonomous-coding pattern counts before AND after each session: `45/200 tests passing`. This creates a simple, verifiable progress metric that persists across sessions and is immune to context loss.

### Concrete Fix

**Add to SKILL.md STEP 4 header**:

```markdown
### STEP 4 — Codex反馈交叉验证

**Pre-STEP gate**: Count current state before verification:
- Completed fixes: {count from pending JSON}
- Pending fixes: {count from pending JSON}
- Blocked fixes: {count from pending JSON}
- Disputed fixes: {count from pending JSON}

Report: "Verifying Codex反馈 against {N_completed} completed fixes.
{N_pending} fixes remaining."

This count serves as a baseline — if verification changes the counts
(items found regressed, etc.), the delta is measurable.
```

**Add to SKILL.md STEP 6**, after each item execution:

```markdown
**After each item**: Update progress summary:

```
[STEP 6] {item_id} COMPLETE. Progress: {done}/{total} items fixed.
{N} remaining, {B} blocked, {R} regressed.
Next: {next_item_id} — {description}
```

This mirrors autonomous-coding's `print_progress_summary()` pattern:
a lightweight, human-readable count that survives context loss and
gives both CC and the user a clear picture of progress at all times.
```

**Priority: P1** — Simple addition, high visibility improvement for user experience and cross-session handoff.

---

## Pattern 5: Single-Task Focus with Evidence-Gated Completion (P1)

### Source
`autonomous-coding/prompts/coding_prompt.md:69-74, 108-126`

```markdown
### STEP 4: CHOOSE ONE FEATURE TO IMPLEMENT

Look at feature_list.json and find the highest-priority feature with
"passes": false.

Focus on completing one feature perfectly and completing its testing
steps in this session before moving on to other features.
It's ok if you only complete one feature in this session.

...

### STEP 7: UPDATE feature_list.json (CAREFULLY!)

**YOU CAN ONLY MODIFY ONE FIELD: "passes"**
**ONLY CHANGE "passes" FIELD AFTER VERIFICATION WITH SCREENSHOTS.**
```

### code-shiniyaya Gap

STEP 6 says "P0/P1逐项; P2微改动(<3行)可批量2项" — this allows batching P2 items, but there's no explicit "complete ONE item PERFECTLY before moving to the next" discipline. The batch allowance for P2 items creates a loophole where multiple items are partially done.

More importantly, there's no **evidence-gated completion**: code-shiniyaya verifies via `ast.parse` + `git diff --stat` + `grep -n`, but doesn't tie the "passes" status flip to specific evidence artifacts. autonomous-coding requires SCREENSHOTS for UI changes and end-to-end testing.

For code-shiniyaya (non-UI code), the equivalent evidence would be: test output, git diff showing exact old→new lines, ast.parse output, and verification command results.

### Concrete Fix

**Add to SKILL.md STEP 6**, replacing the P2 batch allowance:

```markdown
### STEP 6 — 逐项执行

**Single-Task Focus Rule**: Complete ONE item perfectly before moving to
the next. Even for P2 items (<3 lines), do NOT batch — each item gets
its own verification cycle.

**Exception**: Two P2 items touching different files with no shared
imports may be batched, but ONLY if both complete within the same
verification step. If either fails, unbatch and fix individually.

### Per-Item Evidence Packet

Before marking any item as complete, produce an evidence packet:

```
Item: {item_id} — {description}
Evidence:
  [ ] git diff showing OLD → NEW lines (exact, with line numbers)
  [ ] ast.parse output (PASS / FAIL with specific error)
  [ ] grep -n confirming fix at expected line(s)
  [ ] Test command output (if applicable)
  [ ] Symbol impact analysis: {affected_callers}
Verdict: COMPLETE | FAILED | REGRESSED_OTHER
```

Only flip status to "completed" when ALL evidence checks pass.
This mirrors coding_prompt.md:108-126: "ONLY CHANGE 'passes' FIELD
AFTER VERIFICATION WITH SCREENSHOTS" — for code-shiniyaya, evidence
is diff+ast+grep+test, not screenshots.
```

**Priority: P1** — Tightens execution discipline in STEP 6, prevents partial completions.

---

## Pattern 6: MessageHistory Token-Aware Truncation for Sub-Agents (P1)

### Source
`agents/utils/history_util.py:69-111`

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
            self.total_tokens += TRUNCATION_NOTICE_TOKENS - original_input_tokens
```

### code-shiniyaya Gap

When dispatching sub-agents in STEP 1 (6+ agents), STEP 4 (10+ agents), STEP 7 (6+ agents), code-shiniyaya has no token-aware context management for the sub-agents themselves. If a sub-agent's context window fills, it either:
- Gets truncated by the API (losing critical instructions)
- Fails silently with incomplete output

The `MessageHistory.truncate()` pattern solves this: before each API call, check total tokens vs context window. If exceeded, truncate oldest message pairs and inject a truncation notice so the agent KNOWS it lost history.

### Concrete Fix

**Add to anti-hang-v2.md**, under a new `## Sub-Agent Token Management` section:

```markdown
## Sub-Agent Token Management

### Problem

When code-shiniyaya dispatches sub-agents with large prompts + accumulated
tool results, the sub-agent's context window can fill silently, causing
truncated output or API errors.

### Solution: Token-Aware Truncation Pattern

Adapt the autonomous-coding `MessageHistory.truncate()` pattern for
code-shiniyaya sub-agent dispatch:

**Before each sub-agent launch**, estimate token consumption:

```
estimated_tokens =
    system_prompt_tokens (~500 for short prompts)
  + user_message_tokens
  + accumulated_tool_results_tokens (if reusing agent across turns)
  + expected_output_tokens (reserve 2000)
```

If estimated_tokens > 80% of context_window:
1. Truncate oldest message pairs from the agent's accumulated history
2. Inject: "[Earlier context has been truncated to fit context window.]"
3. Recalculate

**In agent dispatch prompts**, add a truncation-awareness instruction:

```markdown
If you see "[Earlier context has been truncated...]" in your history,
this means some previous turns were removed to fit the context window.
Do NOT re-do work from those turns — trust that completed work is
reflected in the current state files on disk.
```

### Why This Matters

Without this pattern, sub-agents with long histories may:
- Produce truncated output (missing findings)
- Re-do previously completed work (because they don't see it in history)
- Fail with API context-length errors (undetected by CC)

The truncation notice injection is critical — it prevents the agent
from being confused by "missing" conversation turns.
```

**Priority: P1** — Important for STEP 4 reliability where 10+ agents may accumulate large tool-result histories.

---

## Pattern 7: KeyboardInterrupt Safe Recovery for Tool Execution (P2)

### Source
`browser-use-demo/browser_use_demo/loop.py` (sampling_loop pattern) — the approach to handling interruptions mid-tool-execution

The autonomous-coding agent.py also handles errors gracefully:
```python
elif status == "error":
    print("\nSession encountered an error")
    print("Will retry with a fresh session...")
    await asyncio.sleep(AUTO_CONTINUE_DELAY_SECONDS)
```

### code-shiniyaya Gap

STEP 6 executes fixes sequentially. If a fix is interrupted mid-Write/Edit (user says stop, tool timeout, etc.), the rule says "stop immediately". But there's no pattern for determining whether the interrupted Write was successful (partially written) or not. The code-shiniyaya approach is "Write/Edit成功=完成 → 不Read" (Rule 14), which is optimistic.

The autonomous-coding pattern is more defensive: on error/interrupt, check `git status --porcelain` to see if files actually changed, and if so, commit or reset to known state.

### Concrete Fix

**Add to SKILL.md Rule 13 (stop/中断)**, as a sub-rule:

```markdown
### Rule 13.1 — Interrupted Write Detection

When a stop/interrupt occurs during a Write/Edit operation:

1. IMMEDIATELY run `git diff --stat` — detect if the interrupted file
   was actually modified (partial write may have succeeded)
2. If file was modified:
   a. Read the file — compare against pre-edit state (from git)
   b. If complete (the full intended change was written) → mark item DONE
   c. If partial (truncated or incomplete lines) → `git checkout -- {file}`
      to restore pre-edit state, mark item INTERRUPTED
   d. If corrupted (syntax error from partial write) → `git checkout -- {file}`,
      mark item CORRUPTED, write CORRUPTION_LOG.md
3. If file was NOT modified:
   a. Write never started → mark item INTERRUPTED, retry from scratch next session

This prevents: (a) assuming a partial Write succeeded, (b) losing the
ability to resume because the file is in an unknown intermediate state.
```

**Priority: P2** — Edge case handling, important for robustness but less frequent than the P0/P1 patterns above.

---

## Pattern 8: Evidence-Based "passes" Flip Protocol for STEP 7 Verification (P0)

### Source
`autonomous-coding/prompts/coding_prompt.md:108-126` (STEP 7: UPDATE feature_list.json CAREFULLY!) combined with STEP 6 (VERIFY WITH BROWSER AUTOMATION)

### code-shiniyaya Gap

STEP 7 (双向验证) says "1轮(CC→Codex→CC), 双方确认=完成". This is a **process-based** completion check: if both parties agree, the item is done.

The autonomous-coding approach is **evidence-based**: an item is done ONLY when there is concrete verification evidence (screenshots for UI, test output for logic, console-error check for frontend). The "passes" flip is gated on evidence, not agreement.

For code-shiniyaya STEP 7, the equivalent would be: an item is verified complete ONLY when:
1. `ast.parse` passes on the modified file
2. `git diff` shows the exact intended change
3. Any applicable test command passes
4. No regressions detected in related items (Pattern 1 above)

The current STEP 7 relies on CC↔Codex mutual confirmation, which is a **social** gate, not a **technical** gate. The autonomous-coding pattern shows that technical evidence gates are more reliable for long-running autonomous work.

### Concrete Fix

**Add to SKILL.md STEP 7**, replacing the simple "双方确认=完成":

```markdown
### STEP 7 — 双向验证 (Evidence-Gated Completion)

**Evidence Gate** — An item is VERIFIED COMPLETE only when ALL of these
are true (in addition to CC↔Codex mutual confirmation):

| # | Gate | How to verify | Fallback if fails |
|---|------|---------------|-------------------|
| 1 | Syntax integrity | `ast.parse(file)` on every modified file | Rollback, mark FAILED |
| 2 | Change accuracy | `git diff` matches intended OLD→NEW exactly | Rollback, re-plan |
| 3 | No regressions | Pattern 1 regression gate (re-verify 1-2 related items) | Mark REGRESSED, fix first |
| 4 | Symbol consistency | `grep -rn "import {symbol}"` — all callers still resolve | Update callers or re-plan |
| 5 | File integrity | `wc -l {file}` matches expected post-fix line count ±5 | Re-examine, possibly re-do |
| 6 | Test passage | Run related test command (if exists) | Mark FAILED, debug |
| 7 | Codex confirmation | Codex has reviewed AND approved with file:line evidence | Degrade to CC self-verify |

**Only when ALL 7 gates pass** → mark item as COMPLETED in pending JSON.

**Gate order matters**: Gates 1-3 are fast (<1s each), catch 90% of issues.
Gate 7 (Codex) is slowest (requires human round-trip) — do it LAST.
If Gates 1-3 fail, don't waste Codex's time on a broken fix.
```

This mirrors the autonomous-coding evidence hierarchy:
- Fast automated checks first (syntax, diff, imports)
- Medium checks second (regression, test)
- Human review last (Codex confirmation)

**Priority: P0** — This transforms STEP 7 from "social agreement" to "technical verification + social agreement", making it robust for autonomous operation.

---

## Summary: All Patterns and Priorities

| # | Pattern | Source file:line | Gap filled | Priority | Target file |
|---|---------|-----------------|------------|----------|-------------|
| 1 | Mandatory Regression Gate Before New Work | `coding_prompt.md:48-67` | STEP 4 + STEP 6: no pre-work regression check | **P0** | SKILL.md |
| 2 | Clean Exit Protocol Before Context Fill | `coding_prompt.md:151-158` | STEP 6 + STEP 7: no clean handoff protocol | **P0** | SKILL.md |
| 3 | Fresh-Context State Reconstruction | `coding_prompt.md:3-31` | Recovery: single-point-of-failure in session JSON | **P1** | SKILL.md |
| 4 | Progress Counting as Pre-Work Gate | `progress.py:11-37` | STEP 4 + STEP 6: no regular progress metric | **P1** | SKILL.md |
| 5 | Single-Task Focus + Evidence-Gated Completion | `coding_prompt.md:69-74, 108-126` | STEP 6: allows P2 batching, no evidence packet | **P1** | SKILL.md |
| 6 | MessageHistory Token-Aware Truncation | `history_util.py:69-111` | Sub-agent dispatch: no token management | **P1** | anti-hang-v2.md |
| 7 | KeyboardInterrupt Safe Recovery for Write | `agent.py:169-181` + loop.py pattern | STEP 6: optimistic "Write成功=完成" on interrupt | **P2** | SKILL.md |
| 8 | Evidence-Based "passes" Flip Protocol | `coding_prompt.md:108-126` | STEP 7: social gate only, no technical evidence gate | **P0** | SKILL.md |

## Comparison: Existing Gap Analysis vs This Analysis

The existing `autonomous-coding-gap-analysis.md` covers architectural patterns:
- Init+Loop model (whole-workflow architecture)
- Immutable checklist (data model)
- Safety layers (infrastructure)
- Prompt structure (template)

This analysis covers **operational** patterns specific to STEP 4-7:
- Regression gate (STEP 4.0 — before verification)
- Clean exit (STEP 6.99 — before session end)
- State reconstruction (recovery protocol)
- Progress counting (visibility)
- Evidence-gated completion (STEP 6 + STEP 7 discipline)

The two analyses are complementary: architectural patterns define WHAT to build; operational patterns define HOW to execute reliably.

## Implementation Order

1. **Pattern 1 + Pattern 8 (P0)**: Regression gate + evidence-based completion — these form a pair: verify nothing broke (Pattern 1), verify the fix is real (Pattern 8)
2. **Pattern 2 (P0)**: Clean exit protocol — ensures handoff between these gates
3. **Pattern 3 + Pattern 4 (P1)**: State reconstruction + progress counting — improve existing recovery
4. **Pattern 5 + Pattern 6 (P1)**: Single-task focus + token management — execution discipline
5. **Pattern 7 (P2)**: Interrupt recovery — edge case hardening
