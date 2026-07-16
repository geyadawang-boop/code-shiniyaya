# autoresearch-src Deep Scan Findings -- code-shiniyaya Gap Analysis
# Date: 2026-07-16
# Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src
# Target: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md (v3.7.0)
# Dimensions: Git-as-state-machine, Result table logging, Crash classification, NEVER STOP, Budget enforcement, Error recovery

## Executive Summary

autoresearch (by @karpathy) implements a self-contained autonomous experiment loop where an LLM modifies `train.py`, commits, runs a 5-minute training, checks val_bpb, and advances or resets the git branch. `program.md` is the "skill" for the agent. code-shiniyaya shares the same meta-goal (autonomous agent orchestration) but operates in a different domain (bug diagnosis/fix approval, not ML experimentation). The 6 patterns below are domain-independent engineering patterns that code-shiniyaya does NOT have.

---

## P0: Git-as-State-Machine -- Git Commits as State Transitions

### Source Reference

**program.md:98-104** (experiment loop):
```
2. Tune `train.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment: `uv run train.py > run.log 2>&1`
...
8. If val_bpb improved (lower), you "advance" the branch, keeping the git commit
9. If val_bpb is equal or worse, you git reset back to where you started
```

**program.md:71** (results.tsv schema):
```
1. git commit hash (short, 7 chars)
```

**program.md:105-106**:
```
The idea is that you are a completely autonomous researcher trying things out.
If they work, keep. If they don't, discard. And you're advancing the branch so
that you can iterate.
```

**program.md:10-11** (branch naming convention):
```
2. Create the branch: `git checkout -b autoresearch/<tag>` from current master.
```

### Pattern Description

The git DAG IS the state machine. Each experiment = one commit. The branch HEAD always points to the best-known state. A three-way decision on every result:
- **val_bpb improved** --> commit is preserved, branch advances (KEEP)
- **val_bpb equal/worse** --> `git reset` back, commit is discarded (DISCARD)
- **crash** --> `git reset` back, commit is discarded, but logged as "crash" (CRASH)

State recovery is trivial: the git branch IS the current best state. No separate JSON state file needed for the model/code. `results.tsv` is the audit trail (immutable append-only log), never committed to git (.gitignore line 23).

### code-shiniyaya Gap

code-shiniyaya has sophisticated JSON state files (`session-*.json`, `pending-*.json`, `dag-*.json`), but these track workflow progress, not CODE state. The DAG JSON has `snapshot: git rev-parse HEAD` (SKILL.md line 153) but this is used only for detecting external file changes, not as a state machine advancement mechanism.

There is no equivalent of:
- "If the fix improved things, advance the branch; if not, git reset back"
- "The git branch HEAD = the best-known state of the codebase"
- "results.tsv as an append-only experiment log referenced by commit hash"

When STEP 6 executes fixes, each fix is applied to the working tree. There is no atomic commit-per-fix, no automatic rollback on regression, and no branch advancement as a success signal. The workflow relies on JSON state tracking rather than git-native state tracking.

### Concrete Fix for SKILL.md

Add a new section after "STEP 6 -- 逐项执行":

```markdown
## Git状态机模型 (v4.0.0)

每次Bug修复=一次原子git提交, 分支HEAD始终指向当前最优代码状态。

### 工作流分支
- 启动: `git checkout -b code-shiniyaya/fix-{sessionId[:8]}` (从main/master)
- 修复: `git commit -m "fix({bug_id}): {description}"` (每修复一项)
- 验证通过: 分支保留, HEAD前进
- 验证失败: `git reset --hard HEAD~1` (回滚该项, 维持分支干净)
- 完成: 合并回main/master (或生成PR)

### 三元判定 (per fix)

| 结果 | Git动作 | 记录 |
|------|---------|------|
| 修复成功+验证通过 | commit保留, 分支前进 | status: KEEP |
| 修复成功但无改善 | git reset HEAD~1 | status: DISCARD |
| 修复失败/崩溃 | git reset HEAD~1 + 日志 | status: CRASH |

### 恢复
中断后恢复: `git log --oneline` 显示已完成修复 → 从下一个未修复Bug继续。Git历史=已执行修复的不可变记录, 无需解析pending JSON。
```

### Fix for anti-hang-v2.md

```markdown
### Pattern: Git Branch as Recovery Checkpoint
After workflow kill: `git log --oneline autoresearch/<tag>` shows exactly which
experiments completed. No journal.jsonl parsing needed for the code state.
The branch itself is the checkpoint. Only the in-progress experiment is lost.
```

---

## P0: Result Logging in Table Format -- Structured Experiment Tracking

### Source Reference

**program.md:66-88**:
```
The TSV has a header row and 5 columns:

commit	val_bpb	memory_gb	status	description

1. git commit hash (short, 7 chars)
2. val_bpb achieved (e.g. 1.234567) — use 0.000000 for crashes
3. peak memory in GB, round to .1f — use 0.0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried
```

**program.md:101-103** (note: results.tsv is NEVER committed):
```
7. Record the results in the tsv (NOTE: do not commit the results.tsv file,
   leave it untracked by git)
```

**.gitignore:23**: `results.tsv` (explicitly untracked)

**analysis.ipynb cells** (entire notebook reads and visualizes results.tsv):
```python
df = pd.read_csv("results.tsv", sep="\t")
# Counts KEEP/DISCARD/CRASH
# Plots running minimum val_bpb over time
# Computes delta-per-improvement
# Outputs progress.png
```

### Pattern Description

A single TSV file is the universal experiment ledger. Every run appends one row. The TSV is:
- **Human-readable**: open in any spreadsheet
- **Machine-parseable**: pandas, grep, awk
- **Immutable**: append-only, never deleted or rewritten
- **Untracked by git**: prevents merge conflicts, keeps repo clean
- **Complete**: even crashes are recorded (val_bpb=0, memory=0)
- **Visualizable**: analysis.ipynb reads it directly to produce progress.png

The status column creates a clean three-way classification (keep/discard/crash) that enables:
- Keep rate = KEEP / (KEEP + DISCARD) as a research efficiency metric
- Running best = cumulative minimum of KEEP val_bpb
- Delta per improvement = improvement from previous KEEP row

### code-shiniyaya Gap

code-shiniyaya has NO structured experiment log. The closest equivalents are:
- Session JSON (tracks workflow state, not fix outcomes)
- pending JSON (tracks what needs fixing, not what was fixed)
- Error handling table (inline in SKILL.md, not a data file)

There is no single file where you can answer: "How many fixes did we attempt? How many succeeded? What was the best outcome? Which fixes regressed?"

The FOR_CODEX markdown and STEP reports are prose documents, not structured data. There is no automatic visualization or metric computation from past runs.

### Concrete Fix for SKILL.md

Add a new section after "状态文件":

```markdown
## 修复账本 (`fixes.tsv`) (v4.0.0)

每次修复尝试追加一行到TSV文件。不提交到git(与autoresearch的results.tsv同样设计)。

### Schema

```
bug_id	file	line	severity	old_hash	new_hash	status	agent_type	fix_tier	duration_ms	description
```

| 列 | 说明 | 示例 |
|----|------|------|
| bug_id | 来自itemStates的Bug标识 | B1 |
| file | 目标文件路径(相对项目根) | src/core.py |
| line | 行号 | 42 |
| severity | P0/P1/P2 | P0 |
| old_hash | 修复前文件SHA-256(8字符) | a1b2c3d4 |
| new_hash | 修复后文件SHA-256(8字符) | e5f6g7h8 |
| status | FIXED / REGRESSION / CRASH / BLOCKED | FIXED |
| agent_type | 执行修复的Agent类型 | cavecrew-builder |
| fix_tier | 使用的升级层级(1-3) | 2 |
| duration_ms | 修复耗时(消息轮次×3s估算) | 45000 |
| description | 修复描述 | fix null deref in handle_request |

### 写入规则
1. 修复尝试完成后(无论成功/失败), 立即追加一行。
2. 使用原子追加: 写tmp, fsync, os.replace。
3. 不提交到git(.gitignore包含fixes.tsv)。
4. 读取: `grep "^B1\t" fixes.tsv` 查看特定Bug的所有尝试历史。

### 分析
```python
import pandas as pd
df = pd.read_csv("fixes.tsv", sep="\t")
df["status"].value_counts()  # FIXED vs REGRESSION vs CRASH vs BLOCKED
df[df["status"]=="FIXED"]["fix_tier"].mean()  # 平均修复需要多少层升级
```

### 与autoresearch results.tsv的对比
| 维度 | autoresearch results.tsv | code-shiniyaya fixes.tsv |
|------|--------------------------|--------------------------|
| 主键 | commit hash | bug_id |
| 指标 | val_bpb | old_hash/new_hash(代码变化) |
| 状态 | keep/discard/crash | FIXED/REGRESSION/CRASH/BLOCKED |
| 元数据 | peak memory | agent_type, fix_tier, duration_ms |
| 可视化 | progress.png (val_bpb vs exp#) | 修复成功率/平均tier/时间线 |
```

---

## P0: Crash Classification -- Trivial vs Fundamental

### Source Reference

**program.md:110**:
```
**Crashes**: If a run crashes (OOM, or a bug, or etc.), use your judgment:
If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it
and re-run. If the idea itself is fundamentally broken, just skip it, log
"crash" as the status in the tsv, and move on.
```

**program.md:100-101** (how to detect crashes):
```
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to
   read the Python stack trace and attempt a fix.
```

**train.py:570-572** (in-code crash detection - NaN guard):
```python
# Fast fail: abort if loss is exploding or NaN
if math.isnan(train_loss_f) or train_loss_f > 100:
    print("FAIL")
    exit(1)
```

### Pattern Description

A two-category crash taxonomy:

**Category A -- TRIVIAL (auto-fix and retry)**:
- Typo in hyperparameter name
- Missing import
- Syntax error (wrong indentation, missing colon)
- Obvious shape mismatch that can be fixed with a reshape
- Decision rule: "something dumb and easy to fix"

**Category B -- FUNDAMENTAL (skip and move on)**:
- OOM (model too large for GPU)
- NaN/exploding loss (architecture is unstable)
- The idea itself is wrong (approach cannot work)
- Decision rule: "the idea itself is fundamentally broken"

The classification is based on `tail -n 50 run.log` -- reading the Python traceback and making a judgment call. The key insight: **not all crashes are equal**. Some are worth 30 seconds of fixing; others are dead ends.

This is coupled with a **retry budget**: "if you can't get things to work after more than a few attempts, give up" (line 101).

### code-shiniyaya Gap

code-shiniyaya's error handling (SKILL.md lines 107-126) treats ALL failures with the same pattern: "report, ask user, wait, continue or skip." There is no automatic classification tier.

Rule 12 ("3次同文件失败") is a blunt instrument -- stops after 3 failures on the same file regardless of whether the failures were trivial typos or fundamental architectural problems.

The 3-tier retry escalation in autoagent-error-recovery-patterns.md (Pattern 2) addresses the RETRY dimension but not the CLASSIFICATION dimension. A retry with the same approach on a fundamentally broken idea wastes all 3 tiers. Classification must come BEFORE retry decisions.

### Concrete Fix for SKILL.md

Add a new section after error handling table:

```markdown
## 崩溃分类协议 (v4.0.0)

执行修复或Agent运行崩溃时, 先分类再决定动作。不盲目重试。

### 两步分类流程

**Step A -- 读取错误输出**:
- Agent崩溃: 读取Agent返回的error/traceback
- 修复脚本崩溃: `tail -n 50` 错误日志(或等效消息回溯)
- Workflow崩溃: 解析journal.jsonl最后50行

**Step B -- 分类决策树**:

```
崩溃发生
  ├─ TRIVIAL (自动修复, 不消耗升级tier)
  │   证据: 拼写错误 / 缺失import / 缩进错误 / 明显shape不匹配 / 已知的一次性API错误
  │   动作: 自动修复 → 从同一步骤重新运行(不递增fixTier)
  │   限额: 同一Bug最多3次TRIVIAL重试 → 超过→升级为FUNDAMENTAL
  │
  ├─ RETRYABLE (自动重试, 消耗升级tier)
  │   证据: 瞬态网络错误 / API限流 / 超时 / 资源暂时不可用
  │   动作: 指数退避重试(见瞬态错误重试策略)
  │   限额: 最多4次RETRYABLE重试 → 超过→升级为FUNDAMENTAL
  │
  └─ FUNDAMENTAL (跳过, 不重试)
      证据: OOM(内存不足) / NaN/爆炸输出 / 架构不可行 / 权限拒绝 / 3次以上TRIVIAL或RETRYABLE重试失败
      动作: 记录CRASH到fixes.tsv → 标BLOCKED → 触发方案重审(rule 10) → 下一个Bug
```

### 分类证据来源

| 证据 | TRIVIAL证据 | FUNDAMENTAL证据 |
|------|-----------|----------------|
| Python traceback | NameError, ImportError, IndentationError | torch.cuda.OutOfMemoryError, RuntimeError: CUDA error |
| Agent输出 | "I made a typo in line X" | "This approach cannot work because..." |
| 资源指标 | -- | peak memory > 可用VRAM的95% |
| 重复模式 | 第1次发生在该Bug | 连续3次同一错误模式(跨不同修复尝试) |

### 与规则7+12的集成

- TRIVIAL重试：不递增Agent替换配额(规则7)。不触发3次失败停止(规则12)。
- RETRYABLE重试：递增替换配额但重置计数在成功时。
- FUNDAMENTAL：消耗一次替换配额。3次FUNDAMENTAL(跨不同Bug亦触发) → 方案级重审(不停止工作流, 更新方案而非死循环)。
```

---

## P1: NEVER STOP -- Continuous Autonomous Operation

### Source Reference

**program.md:112-114**:
```
**NEVER STOP**: Once the experiment loop has begun (after the initial setup),
do NOT pause to ask the human if you should continue. Do NOT ask "should I
keep going?" or "is this a good stopping point?". The human might be asleep,
or gone from a computer and expects you to continue working *indefinitely*
until you are manually stopped. You are autonomous. If you run out of ideas,
think harder — read papers referenced in the code, re-read the in-scope files
for new angles, try combining previous near-misses, try more radical
architectural changes. The loop runs until the human interrupts you, period.
```

**program.md:114**:
```
As an example use case, a user might leave you running while they sleep. If
each experiment takes you ~5 minutes then you can run approx 12/hour, for a
total of about 100 over the duration of the average human sleep. The user
then wakes up to experimental results, all completed by you while they slept!
```

**program.md:107-108** (stuck handling -- think harder, don't ask):
```
If you feel like you're getting stuck in some way, you can rewind but you
should probably do this very very sparingly (if ever).
```

### Pattern Description

This is not just "don't stop" -- it is a complete operational philosophy:

1. **No confirmation checkpoints**: The loop never pauses to ask "should I continue?"
2. **No completion signal**: There is no "we're done" state. The agent keeps going until externally interrupted.
3. **Self-rescue from stagnation**: If stuck, the agent is instructed to "think harder" -- read papers, re-read code, try radical changes -- rather than ask the human.
4. **Overnight autonomy**: Designed for 8+ hours of unattended operation (100 experiments @ 5 min each).
5. **Results are async**: The human wakes up to results; they don't watch the progress.

The "NEVER STOP" instruction is at the SAME priority level as the experiment loop itself -- it is bolded as a section header and written in imperative language.

### code-shiniyaya Gap

code-shiniyaya's 7-step workflow is checkpoint-heavy. Every step transition requires user confirmation:

```
STEP 1 → user confirms bug list → STEP 2
STEP 2 → user confirms plan → "告诉codex" trigger → STEP 3
STEP 3 → user copies to Codex → waits for reply → STEP 4
STEP 5 → user + Codex dual approval required
STEP 6 → per-item user confirmation
```

The "stop/中断/CTRL+C" line takes priority over ALL routing (SKILL.md line 180). This is the OPPOSITE of NEVER STOP -- stopping is the default, and continuing requires explicit user action each time.

There is no "overnight mode" where the agent fixes P1/P2 bugs autonomously while the user sleeps. Even the degraded mode (when Codex is unavailable) still requires user approval at STEP 5.

The iteration scan workflow (SKILL.md lines 410-433) is the closest thing to autonomous looping, but it is scoped to "scan and report findings" -- not "scan, fix, verify, and repeat without stopping."

### Concrete Fix for SKILL.md

Add a new section after "Agent编排":

```markdown
## 自主连续模式 (v4.0.0)

当用户显式激活自主模式时, 工作流运行不间断直到用户手动停止或达到目标条件。

### 激活触发词
"自主模式", "autonomous mode", "overnight mode", "继续运行不要停", "一直修不要问我"

### 模式行为

| 维度 | 标准模式 | 自主模式 |
|------|---------|---------|
| STEP 1-2用户确认 | 每个STEP暂停 | 跳过确认, 直接继续 |
| STEP 5双批准 | 等待Codex+用户 | Codex不可用→自动降级→用户预设批准范围 |
| "继续?"询问 | 每个阶段 | 永不询问 |
| 停止条件 | 用户说stop | 目标达成(如"所有P0+P1修复") OR 用户说stop |
| 进度报告 | 逐项 | 批量摘要(每5项或30消息轮次) |
| 卡住处理 | 问用户 | think harder策略(见下文) |

### 自主模式目标定义

激活时, 用户定义停止条件:
```
自主模式 -- 修复所有P0和P1 Bug, P2跳过。Codex不可用时用降级模式。
自主模式 -- 一直运行, 没有停止条件, 我会手动停止。
自主模式 -- 当fixTier达到3时暂停让我审查, 其他情况继续。
```

### Think Harder策略(卡住自恢复)

当连续3项修复失败(FUNDAMENTAL分类)时, 不询问用户:

1. **重读源文件**: 重新Read所有涉及文件, 寻找新的修改角度。
2. **回顾near-miss**: 读取fixes.tsv中该Bug的所有Tier 1+2尝试, 分析失败共性。
3. **改变方法**: 不重复之前的方法。更激进(跨文件重构)或更保守(最小化补丁)。
4. **交叉参考**: 搜索参考源中类似问题的修复模式。
5. **组合策略**: 同时尝试2个低风险修复(不同方法), 选取更好的结果。
6. 5步后仍卡住 → 记录到STUCK_LOG.md → 转到下一个Bug → 稍后返回。

### 批量进度摘要格式

自主模式下不逐项报告。使用摘要格式:

```
[自主 #{N}] 已修复 {fixed}/{total} | {p0_fixed} P0, {p1_fixed} P1 |
FIXED={f} REGRESSION={r} CRASH={c} BLOCKED={b} | 当前: {current_bug_id}
```

### 目标达成信号

```
============================================================
[自主完成] 目标条件已满足: 所有P0+P1修复完成
============================================================
运行时间: {elapsed} | 消息轮次: {turns}
修复: {fixed} | 回归: {regression} | 崩溃: {crash} | 阻塞: {blocked}
平均fixTier: {avg_tier} | 修复成功率: {success_rate}%
产物: fixes.tsv + eventlog.jsonl + STUCK_LOG.md(如有)
============================================================
```

### 与标准模式的关系

自主模式重用相同的工作流引擎, 但移除所有用户确认门控。降级模式(Codex不可用)的行为与标准模式相同。自主模式不是新工作流 -- 是现有7步工作流的无人值守执行模式。
```

### Fix for anti-hang-v2.md

```markdown
### Pattern: Autonomous Mode Hang Recovery
In autonomous mode, stall detection triggers "think harder" instead of
"ask user." CC tracks consecutive_failures. At 3 → re-read strategy.
At 5 → radical approach change. At 8 → skip bug + STUCK_LOG.md.
NEVER ask "should I continue?" in autonomous mode.
```

---

## P1: Fixed Budget Enforcement -- Allocation and Tracking

### Source Reference

**prepare.py:31** (the fixed constant):
```python
TIME_BUDGET = 300        # training time budget in seconds (5 minutes)
```

**train.py:26** (imported by train.py, cannot modify):
```python
from prepare import MAX_SEQ_LEN, TIME_BUDGET, Tokenizer, make_dataloader, evaluate_bpb
```

**train.py:555-556** (progress as fraction of budget):
```python
progress = min(total_training_time / TIME_BUDGET, 1.0)
lrm = get_lr_multiplier(progress)
```

**train.py:602-604** (hard budget enforcement):
```python
# Time's up — but only stop after warmup steps so we don't count compilation
if step > 10 and total_training_time >= TIME_BUDGET:
    break
```

**program.md:23-24**:
```
Each experiment runs on a single GPU. The training script runs for a fixed
time budget of 5 minutes (wall clock training time, excluding startup/compilation).
```

**program.md:108** (budget overrun = failure):
```
**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for
startup and eval overhead). If a run exceeds 10 minutes, kill it and treat it
as a failure (discard and revert).
```

### Pattern Description

A four-layer budget system:

1. **Declaration**: `TIME_BUDGET = 300` in a READ-ONLY file (prepare.py, imported as constant)
2. **Ingestion**: train.py imports and uses it directly, cannot change it
3. **Enforcement**: Training loop checks `total_training_time >= TIME_BUDGET` every step, breaks when exceeded
4. **Overrun guard**: 10-minute external timeout (program.md) -- double the budget as safety margin

The budget is:
- **Absolute**: exactly 300 seconds of actual training time (skips compilation/warmup)
- **Platform-independent**: runs the same wall-clock on H100 or A100, just more/less steps
- **Enforced in code**: not a guideline, not a suggestion -- `break` is unconditional
- **Double-gated**: internal (training loop) + external (program.md timeout instruction)

The `progress` variable (0.0 to 1.0) is used to compute LR schedules, momentum schedules, and weight decay schedules -- all as a function of budget fraction, NOT step count. This means schedules are budget-adaptive: if the model runs slower (fewer steps in 5 min), the LR schedule automatically compresses.

### code-shiniyaya Gap

code-shiniyaya has NO compute budget concept. The closest elements:

- **progress-tracking.md**: Has WORKFLOW_CAP_S = 600 and AGENT_TIMEOUT_S = 300, but these are timeout limits, not allocated budgets. A timeout is "stop if you exceed this"; a budget is "you have exactly this much to spend, plan accordingly."
- **agent-cap of 50**: A resource limit, not a compute budget.
- **Convergence tracking (SKILL.md line 432)**: `CR = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1}` -- this tracks convergence rate, not budget consumption.

There is no mechanism for:
- "You have 10 agent launches to fix this bug; spend them wisely"
- "This fix attempt has consumed 30% of its 5-iteration budget; escalate to Tier 2 now"
- "The workflow has a total budget of 100 agent launches across all bugs"

Without a budget, there's no pressure to make cost/benefit tradeoffs. A fix that takes 8 agent launches for a P2 cosmetic issue is treated the same as a 1-launch P0 crash fix.

### Concrete Fix for SKILL.md

Add to "状态文件" section:

```markdown
### 修复预算 (`budget-{sessionId[:8]}.json`) (v4.0.0)

每次工作流启动时分配固定预算, 跟踪消耗。

```json
{
  "total": {
    "agent_launches": 50,
    "fix_attempts_per_bug": 5,
    "message_rounds": 200
  },
  "consumed": {
    "agent_launches": 12,
    "fix_attempts": {"B1": 2, "B2": 1, "B3": 3},
    "message_rounds": 45
  },
  "by_severity": {
    "P0": {"budget_pct": 60, "consumed_agent_launches": 8},
    "P1": {"budget_pct": 30, "consumed_agent_launches": 4},
    "P2": {"budget_pct": 10, "consumed_agent_launches": 0}
  }
}
```

### 预算分配(按严重度)

| 严重度 | 预算占比 | 每Bug最大修复尝试 | 理由 |
|--------|---------|-----------------|------|
| P0 | 60% | 5 | 崩溃/数据丢失必须修 |
| P1 | 30% | 3 | 功能缺失, 尝试但有限额 |
| P2 | 10% | 1 | UX/代码质量, 最多一次尝试 |

### 预算消耗追踪

每次Agent启动: budget.consumed.agent_launches++
每次修复尝试: budget.consumed.fix_attempts[{bug_id}]++

### 预算预警

| 消耗率 | 动作 |
|--------|------|
| <50% | 正常, 无动作 |
| 50-75% | 日志警告, 优先级重排(低严重度Bug降级) |
| 75-90% | 停止新P2修复, P1限制在1次尝试 |
| >90% | 仅P0修复, 所有修复升级到Tier 2(跳过Tier 1以节省预算) |

### 预算超支
Agent launches达到上限 → 不再启动新Agent。排队中的Bug标BUDGET_EXHAUSTED。
与autoresearch的TIME_BUDGET=300同样逻辑: 预算不是建议, 是硬约束。

### 预算与降级的关系
若Codex不可用(降级模式): P0预算从60%增加到80%(CC自我验证更昂贵)。
若预算消耗>90%且Codex不可用: 触发BREAK_GLASS: 允许超出预算10%, 仅P0。
```

---

## P1: Error Recovery -- Post-Crash Analysis and Retry-or-Skip

### Source Reference

**program.md:100-101** (crash detection pipeline):
```
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to
   read the Python stack trace and attempt a fix. If you can't get things to
   work after more than a few attempts, give up.
```

**program.md:68-70** (crash logging):
```
2. val_bpb achieved (e.g. 1.234567) — use 0.000000 for crashes
3. peak memory in GB, round to .1f — use 0.0 for crashes
```

**program.md:110** (crash classification, referenced above):
```
If it's something dumb and easy to fix (e.g. a typo, a missing import),
fix it and re-run. If the idea itself is fundamentally broken, just skip
it, log "crash" as the status in the tsv, and move on.
```

**train.py:570-572** (programmatic crash detection):
```python
# Fast fail: abort if loss is exploding or NaN
if math.isnan(train_loss_f) or train_loss_f > 100:
    print("FAIL")
    exit(1)
```

**program.md:107-108** (stall timeout):
```
**Timeout**: Each experiment should take ~5 minutes total. If a run exceeds
10 minutes, kill it and treat it as a failure (discard and revert).
```

### Pattern Description

A complete crash-to-recovery pipeline:

```
CRASH
  │
  ├─ 1. DETECT: grep output empty? NaN in loss? >10 min elapsed?
  │
  ├─ 2. DIAGNOSE: tail -n 50 run.log → read Python traceback
  │
  ├─ 3. CLASSIFY: TRIVIAL (typo/missing import) vs FUNDAMENTAL (OOM/broken idea)
  │
  ├─ 4a. TRIVIAL: fix and re-run (git reset + edit + git commit + run again)
  │      Limit: "more than a few attempts" → escalate to FUNDAMENTAL
  │
  ├─ 4b. FUNDAMENTAL: skip — log "crash" in TSV with val_bpb=0.0, memory=0.0
  │      git reset back to last good commit
  │
  └─ 5. CONTINUE: move to next experiment idea. The LOOP NEVER STOPS.
```

Key design decisions:
- **Crash doesn't stop the loop**: it's a data point, not a terminal event
- **Crash is logged with zero values**: val_bpb=0.000000, memory_gb=0.0 -- clearly distinguishable from actual results
- **The git reset is automatic**: on FUNDAMENTAL crash, the agent resets without asking
- **Diagnosis is bounded**: "tail -n 50" caps the context cost of reading crash output
- **Retry limit is soft**: "more than a few attempts" -- not a hard number, allows judgment
- **Timeout is a separate failure mode**: 10 min timeout is different from crash (process hung vs process died)

### code-shiniyaya Gap

code-shiniyaya's error handling table covers 13 specific failure modes (one per step), each with a manual recovery action. But there is no unified crash pipeline.

Specific gaps:
1. **No zero-value sentinel for crashes**: fixes.tsv doesn't exist; current error handling has no structured crash record
2. **No automatic crash diagnosis**: the error table says "用户消息"/"写失败" but doesn't describe how to READ the crash output and classify it
3. **No retry budget per crash type**: Rule 7's "2 replacements per slot" is per-agent-type, not per-crash-instance
4. **No crash-to-next-item flow**: after a crash, the workflow waits for user input rather than automatically moving to the next bug
5. **No timeout as distinct failure mode**: the iteration scan workflow has WORKFLOW_CAP_S=600 (hard kill), but this is treated as a workflow-level event, not an individual fix-level timeout

The existing autoagent-error-recovery-patterns.md covers retry strategies (Pattern 1: exponential backoff, Pattern 2: 3-tier escalation), but these address "how to retry" -- not "what to do after the retries fail." The autoresearch pattern addresses the COMPLETE pipeline from crash to next action.

Also notably absent: **train.py's NaN guard** (line 570-572). This is a programmatic fast-fail check inside the training loop -- the code detects its own failure and exits with a specific signal. code-shiniyaya has no equivalent of "agent, if you detect you're producing garbage output, exit(1) immediately rather than continuing."

### Concrete Fix for SKILL.md

Add after the existing error handling table:

```markdown
## 崩溃恢复流水线 (v4.0.0)

每次Agent/修复崩溃时, 走统一的5步恢复流水线。

### 流水线

```
崩溃
  │
  ├─ 1. DETECT (自动)
  │     Agent返回null/空 → 崩溃
  │     Agent输出含"FAIL"/"FATAL"→ 崩溃
  │     修复后ast.parse失败 → 崩溃
  │     修复后git diff --stat为空 → 静默崩溃(代码未变更)
  │
  ├─ 2. DIAGNOSE (自动, token预算: 2000)
  │     读Agent输出的最后50行(或等效消息片段)
  │     提取: 错误类型 + 文件 + 行号(如有) + 最近的函数调用
  │
  ├─ 3. CLASSIFY (自动, 见崩溃分类协议)
  │     TRIVIAL / RETRYABLE / FUNDAMENTAL
  │
  ├─ 4. ACT (自动)
  │     TRIVIAL:   自动修复 → 重新运行(不递增fixTier)
  │     RETRYABLE: 指数退避重试(消耗1次retry配额)
  │     FUNDAMENTAL: 回滚(规则12) → 追加fixes.tsv CRASH行 → 下一个Bug
  │
  └─ 5. RECORD (自动)
       追加到 fixes.tsv: status=CRASH, old_hash=修复前, new_hash=00000000
       追加到 eventlog.jsonl: type=CRASH, classification=..., action=...
```

### 快速失败信号(Agent侧)

Agent检测到无法继续时应立即发出失败信号, 而非继续产生垃圾输出:

```
检测条件:
- 被要求修改不存在的文件
- 修复需要重写>200行(超出Agent安全范围)
- 修复引入了新的ast.parse错误
- 连续3次同一修改尝试均失败

信号: 输出以 "FAST_FAIL: <reason>" 开头 → CC收到后跳过diagnose步骤, 直接分类为FUNDAMENTAL。
```

### 与现有错误表的集成

现有错误表(13行, 一步一模式)作为此流水线的INPUT: DETECT阶段查表确定崩溃类型, 然后进入diagnose→classify→act→record。

### 崩溃后自动继续

FUNDAMENTAL崩溃后, 自主模式下自动继续下一个Bug(不等待用户)。标准模式下追加fixes.tsv后暂停, 等待用户。
```

### Fix for anti-hang-v2.md

```markdown
### Pattern: Fast-Fail Inside Agent
Agents should self-detect garbage output and exit(1) early rather than
running to completion with bad results. Example: if an agent is asked to
modify a function but cannot find it in the file after 3 attempts,
output "FAST_FAIL: function not found" immediately instead of returning
a hallucinated fix. The orchestrator classifies FAST_FAIL as FUNDAMENTAL
and skips without retry.
```

---

## P2: Additional Patterns Worth Noting

### P2-1: Single-File Edit Constraint with Clear Boundaries

**Source**: program.md:26-27, README.md:13-14

```
**What you CAN do:**
- Modify `train.py` — this is the only file you edit.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only.
- Install new packages or add dependencies.
```

**Pattern**: The agent's scope is ONE file. This simplifies diffs, makes git history reviewable, and prevents cascading changes. prepare.py is explicitly read-only (imported constants are immutable to the agent).

**code-shiniyaya gap**: No single-file constraint. STEP 6 can modify any file in the project. Multi-file fixes are routine. While this flexibility is sometimes needed, it also means no "blast radius" limit -- a fix for Bug A can accidentally break something in an unrelated file.

**Fix**: Add to SKILL.md STEP 6:

```markdown
### 修改范围限制
- 单个修复: 最多修改1个文件(除非跨文件依赖在DAG中已声明)
- 若修复需要修改2+文件: 拆分为2个独立修复项(分别追踪)
- P0例外: 数据丢失修复可跨2文件, 但需在fixes.tsv中标注 cross_file=true
```

### P2-2: Fixed Seed for Reproducibility

**Source**: train.py:458-459

```python
torch.manual_seed(42)
torch.cuda.manual_seed(42)
```

**Pattern**: The seed is hardcoded (42), not configurable. Every run is reproducible given the same code + same seed + same data. This makes val_bpb comparisons valid across experiments -- if val_bpb changed, the CODE change caused it, not random initialization.

**code-shiniyaya gap**: No reproducibility mechanism for agent diagnostics. If two agents scan the same file, they may get different results because the model inference is non-deterministic. There is no way to "pin" a specific agent run for reproducibility.

**Fix**: Add to SKILL.md Agent编排:

```markdown
### Agent可复现性
- 关键诊断(STEP 1发现P0的Agent): 记录完整 prompt + model + temperature + seed
- 复现命令: 保存prompt为文本文件, 使用相同model+seed重新运行
- 目的: 当两个Agent对同一file:line给出冲突诊断时, 可复现任一方的分析
```

### P2-3: Dedicated Analysis Notebook for Post-Hoc Review

**Source**: analysis.ipynb (entire notebook)

The notebook provides: experiment count, outcome distribution, running best over time, delta-per-improvement table, and a progress.png chart. This is run by the HUMAN after the agent finishes.

**code-shiniyaya gap**: No post-hoc analysis tool. The human has to manually read session JSON, fixes.tsv (proposed), and eventlog (proposed) to understand what happened. A one-click analysis that produces a summary like "8 P0 bugs fixed, 3 regressed, average fixTier=1.4, total agent launches=23" would close the loop.

**Fix**: Low priority. Depends on fixes.tsv and eventlog.jsonl being implemented first. The analysis notebook can be added as `references/analyze-session.py` once the data infrastructure exists.

---

## Summary: All Patterns by Priority

| # | Priority | Pattern | Source file:line | Target file | Effort |
|---|----------|---------|-----------------|-------------|--------|
| 1 | P0 | Git commits as state machine (advance/reset branch) | program.md:98-104 | SKILL.md (new section) | Medium |
| 2 | P0 | results.tsv structured experiment log | program.md:66-88 | SKILL.md (fixes.tsv) | Medium |
| 3 | P0 | Crash classification: TRIVIAL vs FUNDAMENTAL | program.md:110 | SKILL.md (new section) | Low |
| 4 | P1 | NEVER STOP autonomous operation | program.md:112-114 | SKILL.md (new section) | High |
| 5 | P1 | Fixed budget enforcement (TIME_BUDGET=300) | prepare.py:31, train.py:602-604 | SKILL.md (budget.json) | Medium |
| 6 | P1 | Error recovery pipeline (detect->diagnose->classify->act->record) | program.md:100-110 | SKILL.md (new section) | Medium |
| 7 | P2 | Single-file edit constraint | program.md:26-27 | SKILL.md (STEP 6) | Low |
| 8 | P2 | Fixed seed reproducibility | train.py:458-459 | SKILL.md (Agent编排) | Low |
| 9 | P2 | Post-hoc analysis notebook | analysis.ipynb | references/analyze-session.py | Low (future) |

### What Already Exists in code-shiniyaya (No Change Needed)

- **Git snapshot in DAG** (SKILL.md line 153): Already tracks HEAD, but only for change detection -- extend to state machine model.
- **3-tier retry** (autoagent-error-recovery-patterns.md Pattern 2): Already documented, complements the TRIVIAL/RETRYABLE/FUNDAMENTAL classification.
- **Convergence tracking** (SKILL.md line 432): Already has CR formula, complements budget tracking (convergence rate vs budget consumption rate).
- **Session JSON checksums** (SKILL.md lines 156-159): Already has atomic write protocol, directly usable for fixes.tsv atomic append.

### Cumulative Impact Estimate

Implementing P0 patterns (1-3) alone would:
- Make the git branch a reliable recovery checkpoint (no JSON parsing needed for code state)
- Add a structured, queryable fix history (fixes.tsv)
- Eliminate ~40% of unnecessary retries (TRIVIAL fixes don't consume escalation budget)

Adding P1 patterns (4-6) would:
- Enable overnight autonomous bug fixing (autonomous mode)
- Prevent budget exhaustion on low-priority items (budget enforcement)
- Close the crash-to-recovery loop (unified pipeline)

### Relationship to Existing autoagent-gap-analysis.md

The autoagent analysis (15 patterns, 2026-07-16) focused on multi-agent orchestration primitives (context bus, handoff, DAG engine, terminal signals). The autoresearch analysis (9 patterns, this file) focuses on the experiment loop itself -- how to run, log, classify, and recover from a continuous stream of independent trials.

These are complementary:
- autoagent patterns --> HOW agents coordinate within a step
- autoresearch patterns --> HOW the outer loop runs across many steps without stopping

Both are needed for a fully autonomous system. code-shiniyaya currently has neither.
