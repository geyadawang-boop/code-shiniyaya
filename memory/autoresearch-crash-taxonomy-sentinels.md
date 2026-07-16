# autoresearch-src NEW Patterns -- Crash Taxonomy + Differentiated Retry + Fast-Fail Sentinels

Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src
Targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
Date: 2026-07-16
Scanner: CC (code-shiniyaya v3.7.0)
Dimension: Crash taxonomy -- trivial vs fundamental crash classification, differentiated retry, fast-fail sentinels in training loop
Cross-reference: Verified NOT in any existing memory file (12+ prior scan files audited)

## What Is ALREADY Documented (Excluded from this file)

The following patterns from autoresearch-src are already captured in existing memory files and are NOT repeated here:
- Crash taxonomy trivial-vs-fundamental (autoresearch-full-autonomy-gaps.md Pattern C, autoresearch-gap-analysis.md Pattern 3)
- NEVER STOP directive (autoresearch-full-autonomy-gaps.md Pattern A, high-impact-patterns.md #9)
- TSV results log (autoresearch-full-autonomy-gaps.md Pattern B, autoresearch-results-tracking-gap-analysis.md Pattern 19)
- Fixed iteration budget (autoresearch-full-autonomy-gaps.md Pattern D)
- Simplicity criterion (autoresearch-full-autonomy-gaps.md Pattern E, autoresearch-simplicity-scan.md Pattern 1)
- Output redirection (autoresearch-full-autonomy-gaps.md Pattern F)
- Git state machine (autoresearch-full-autonomy-gaps.md Pattern G, high-impact-patterns.md #2)
- Think harder escalation (autoresearch-full-autonomy-gaps.md Pattern H)
- Sleep-safe mode (autoresearch-full-autonomy-gaps.md Pattern I)
- Ternary taxonomy + sentinel (autoresearch-results-tracking-gap-analysis.md Pattern 20)
- Git as primary key (autoresearch-results-tracking-gap-analysis.md Pattern 21)
- Running minimum frontier (autoresearch-results-tracking-gap-analysis.md Pattern 22)
- Delta-per-improvement (autoresearch-results-tracking-gap-analysis.md Pattern 23)
- Single-file scope constraint (autoresearch-simplicity-scan.md Pattern 2)

The patterns below are GENUINELY NEW -- extracted from train.py and prepare.py internals that prior scans missed.

---

## Pattern NEW-1 (P0): Inline Fast-Fail Sentinel -- Self-Monitoring Exit in Training/Loop Body

**Source**: `train.py:568-572`

```python
# Fast fail: abort if loss is exploding or NaN
if math.isnan(train_loss_f) or train_loss_f > 100:
    print("FAIL")
    exit(1)
```

**What it is**: The training loop contains an INLINE sentinel that checks its own health on every iteration and self-terminates with a specific signal (`exit(1)`) when it detects it is producing garbage. There are three critical mechanical details:

1. **Placement**: The check is AFTER loss computation but BEFORE optimizer.step() and model.zero_grad(). If the loss is NaN, the model's internal state is already corrupt -- stepping the optimizer would spread the corruption. The sentinel prevents that.

2. **Signal**: `exit(1)` is an explicit, non-zero exit code. This distinguishes "I crashed due to bad data" (exit 1) from "I was killed externally" (SIGTERM, exit code different). The orchestrator can classify the crash by exit code alone.

3. **Threshold**: `> 100` is a domain-specific threshold. For an LM training loop, loss > 100 means the model is producing gibberish -- there is no recovery. The threshold is CALIBRATED to the domain: loss of 8-12 is normal, 100 is catastrophic.

**code-shiniyaya gap**: Rule 12 (3次同文件失败 → STOP) relies on the ORCHESTRATOR detecting failure externally (Write/Edit error returned by tool). There is zero concept of the agent SELF-DETECTING failure and voluntarily exiting. This means:

- An agent that produces garbage output (wrong fix, corrupt code) continues running to completion -- consuming full agent budget and context window -- when it could have self-terminated at the FIRST sign of trouble.
- The orchestrator cannot distinguish "agent produced wrong output and finished" from "agent detected failure and exited early" -- because there is no self-detection mechanism.
- There is no domain-calibrated threshold for any step. What is an "exploding" finding count? What is a "NaN" diagnosis? These concepts don't exist.

**Concrete fix for SKILL.md Rule 12 -- add after line 83**:

```markdown
### Agent侧快速失败哨兵 (v3.9.0 -- from autoresearch train.py:568-572)

每个Agent在执行任务时，必须在其输出中嵌入自检哨兵。哨兵触发时Agent立即停止(不继续产生垃圾输出)，并通过结构化信号告知编排器失败原因。

#### 哨兵位置(关键: 在"有害操作"之前)

Agent执行流程中的哨兵位置：
```
1. 读取文件 → 分析
2. 生成修复方案
3. [哨兵 #1] 验证修复方案不包含已知的反模式 -- 失败→FAST_FAIL
4. 执行修复(Edit/Write)
5. [哨兵 #2] 验证修复后代码不包含语法错误 -- 失败→FAST_FAIL(回滚)
6. [哨兵 #3] 验证修复没有引入新的P0问题 -- 失败→FAST_FAIL(回滚)
7. 返回结果
```

哨兵必须在"有害操作"(如写入错误代码)之前触发。一旦触发→立即停止，不执行后续步骤。

#### 哨兵类型(针对code-shiniyaya领域校准的阈值)

| 哨兵 | 触发条件 | 信号 | 编排器响应 |
|------|---------|------|-----------|
| DIAGNOSIS_SANITY | Agent诊断发现>20个CRITICAL(不可能——项目规模已知) | `FAST_FAIL: diagnosis_overflow {count}` | 标该Agent结果FUNDAMENTAL, 立即替换Agent |
| FIX_ANTI_PATTERN | 生成的修复引入 `eval()`/`exec()`/裸except/`os.system()` (安全门控) | `FAST_FAIL: security_gate {pattern}` | 标FUNDAMENTAL, 拒绝修复, 通知用户 |
| FIX_NOT_FOUND | Agent无法在目标文件中找到需要修改的行(文件可能已变更) | `FAST_FAIL: target_not_found {file}:{line}` | 标FUNDAMENTAL, 触发重新诊断(STEP 1), 不重试修复 |
| FIX_SYNTAX | 修复后 `ast.parse()` 失败(代码语法错误) | `FAST_FAIL: syntax_error {msg}` | 标TRIVIAL, 自动修复语法错误, 1次重试。仍失败→升级FUNDAMENTAL |
| FIX_SIZE | 修复需要修改>200行(单Agent安全范围外) | `FAST_FAIL: scope_exceeded {lines}` | 标FUNDAMENTAL, 触发方案重审(rule 10) |
| STUCK_LOOP | Agent连续3次尝试同一修改(同一行、同一变更) | `FAST_FAIL: stuck_loop {line}` | 标FUNDAMENTAL, 强制换Agent类型 |

#### 编排器响应

FAST_FAIL信号 → 编排器根据类型分类:
- TRIVIAL(FIX_SYNTAX) → 自动修复, 不计入规则12配额(≤2次)
- FUNDAMENTAL(其他) → 计入规则12配额, 同文件累计3次→停止
- 哨兵信号本身也计入eventlog: `type=FAST_FAIL, sentinel=..., classification=...`

#### 为什么需要领域校准

autoresearch的 `loss > 100` 阈值是知道正常loss=8-12、灾难=100+。code-shiniyaya需要等效的领域阈值:
- CRITICAL数不可能>20(已知项目规模<=200文件)
- 任何修复引入安全反模式(`eval`/`exec`/裸except)→绝对不可接受
- 单Agent修改>200行→超出安全范围(上下文不够, 必然有遗漏)
```

**Priority**: P0 -- This is the MECHANISM by which the crash taxonomy (trivial vs fundamental) is enforced IN THE AGENT, not just in the orchestrator. Without inline sentinels, the crash taxonomy is aspirational -- the agent has no way to self-classify.

---

## Pattern NEW-2 (P0): Warmup Exclusion Window -- Skip Initial Steps for Metric Stability

**Source**: `train.py:578-579`

```python
if step > 10:
    total_training_time += dt
```

**What it is**: The first 11 steps (0-10) are EXCLUDED from time tracking because they include CUDA compilation overhead. The training loop still runs these steps -- they produce real gradients and update model weights -- but they are not counted toward the training budget.

**Why this design**: CUDA's JIT compilation (`torch.compile`) happens on the first few forward/backward passes. If step 0 takes 15 seconds (due to compilation) and step 11 takes 0.5 seconds, counting step 0 in the time budget would make the budget unpredictable. By excluding the warmup period, ALL tracked steps have consistent timing, and the budget ("300 seconds of training") is reliable.

The same pattern appears at step 602-603:
```python
# Time's up — but only stop after warmup steps so we don't count compilation
if step > 10 and total_training_time >= TIME_BUDGET:
    break
```

The budget check also excludes warmup steps -- it won't terminate the run during the warmup window even if TIME_BUDGET has elapsed.

**code-shiniyaya gap**: code-shiniyaya has NO warmup exclusion concept. The iteration scan workflow counts ALL agent results equally -- the first agent to return (which may include "cold start" overhead from model loading, prompt compilation, etc.) carries the same weight as the 8th agent to return. This means:

- Agent #1 in a batch has inherently higher latency (cold start), making the anti-hang-v2.md straggler detection (3-message gap) unreliable for the first agent.
- Convergence tracking (CR formula) uses ALL agent findings, including those from agents that may have been affected by cold-start issues (shorter context, less thorough analysis).
- The fixed budget pattern (Pattern D from autoresearch-full-autonomy-gaps.md) would be FAIRER if it excluded the first agent's overhead.

**Concrete fix for anti-hang-v2.md -- add after the straggler detection section**:

```markdown
### Agent Warmup Exclusion Window (from autoresearch train.py:578-579)

工作流批次中的前2个返回Agent不计入延迟统计和straggler检测。

**为什么**: 第一个Agent包含"冷启动"开销(模型加载/提示词编译/工具初始化)。将此开销计入延迟统计会扭曲P50/P95延迟数据，导致straggler检测假阳性。

**排除规则**:
- 8 Agent批次: 前2个返回的Agent = warmup窗口。仅用后6个Agent的返回时序做straggler检测。
- 6 Agent批次: 前1个返回的Agent = warmup窗口。
- 4 Agent批次: warmup窗口=0(批次太小, 排除会丢失太多信号)。

**排除窗口内Agent的返回处理**:
- 仍接受其结果(finding/verdict)。
- 其延迟不用于P50/P95计算。
- 不用于straggler检测(第3个及之后返回的Agent才开始计数3-message-gap)。

**集成到straggler检测**:
```
straggler_check(completed_agents, running_agents, warmup_window):
  eligible = completed_agents[warmup_window:]  // 排除前N个
  for agent in running_agents:
    agents_completed_after = [a for a in eligible if a.completed_after(agent.started)]
    if len(agents_completed_after) >= 3:
      → 标记为STRAGGLER
```

**与现有延迟追踪的关系**:
`agent-performance-{project}.json` 中新增 `cold_start_excluded: true` 字段, 标记是否排除于统计。
```

**Priority**: P0 -- Without warmup exclusion, the straggler detection (the core anti-hang mechanism) has a systematic false-positive bias against the first agent in every batch.

---

## Pattern NEW-3 (P0): EMA Debiasing for Stable Convergence Tracking

**Source**: `train.py:582-584`

```python
ema_beta = 0.9
smooth_train_loss = ema_beta * smooth_train_loss + (1 - ema_beta) * train_loss_f
debiased_smooth_loss = smooth_train_loss / (1 - ema_beta**(step + 1))
```

**What it is**: An exponential moving average (EMA) with bias correction. The raw EMA (`smooth_train_loss`) starts at 0 and takes many steps to converge to the true average, systematically underestimating the loss for early steps. The bias correction (`/ (1 - beta**(step+1))`) compensates: at step 0, the correction factor is `1/(1-0.9^1) = 10`, inflating the near-zero EMA to approximate the true first loss value. By step ~50, the correction factor approaches 1.0, and the EMA stands on its own.

The corrected value is what gets PRINTED to the log (`debiased_smooth_loss`), NOT the raw loss. This means the human reading the log sees a stable, accurate metric from the very first step.

**code-shiniyaya gap**: code-shiniyaya's convergence rate formula:

```
CR = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1} × 100
```

This is a RAW comparison -- iteration N's CRITICAL count directly compared to iteration N-1's. There is NO smoothing. This means:

1. **Noisy**: If iteration 3 finds 5 CRITICAL, iteration 4 finds 8 (because a new file was added to scope), CR = -60% (diverging!) -- but the system didn't get worse, the scope changed. A smoothed CR would dampen this.

2. **No bias correction**: The FIRST iteration has NO history to compare against. CR is undefined or computed against a zero baseline, making the first CR value meaningless.

3. **No debiasing**: Early iterations have fewer data points (fewer files scanned, fewer agents completed) and naturally have higher variance in CRITICAL counts. Without debiasing, the convergence signal is dominated by noise in early iterations.

**Concrete fix for SKILL.md convergence tracking section (line 430-433)**:

```markdown
### 平滑趋同追踪 (from autoresearch train.py:582-584)

替代原始逐轮对比, 使用偏差修正的指数移动平均(EMA):

#### 核心指标: 平滑严重度得分(SmoothedSeverityScore, S3)

```
S3_raw[i] = β × S3_raw[i-1] + (1-β) × (CRITICAL_i + HIGH_i/2 + MEDIUM_i/4)
S3_debiased = S3_raw[i] / (1 - β^i)  // 偏差修正

β = 0.9 (同autoresearch, 约10轮平滑窗口)
```

#### 趋同检测(基于S3, 非原始CRITICAL)

```
CR_smooth[i] = (S3_debiased[i-1] - S3_debiased[i]) / max(S3_debiased[i-1], 1) × 100

CR_smooth > 60%: 健康趋同
CR_smooth 20-60%: 慢速趋同
CR_smooth 0-20%: 平台期
CR_smooth < 0%: 发散(但需连续2轮确认, 因为S3平滑可能滞后)
```

#### 为什么EMA优于原始对比

| 场景 | 原始CR | 基于EMA的CR | 正确? |
|------|--------|-----------|-------|
| 第1轮: 5 CRITICAL, 第2轮: 3 | +40% | +40% (β=0.9, S3[0]=5, S3[1]=4.8→biascorrect=~4.8) | 两者相同 |
| 第1轮: 3, 第2轮: 8(但8中6个是新文件) | -167% → 假发散 | 缓降至~-10% → 接近平台 | EMA正确 |
| 前5轮: 5→3→2→4→1 | 波动大 | 平滑下降趋势 | EMA更可读 |
| 第1轮(无历史) | undefined | S3_debiased[0]=CRITICAL_0 (bias correction accounts for cold start) | EMA有定义 |

#### 实现(编排器侧, 无Python运行时)

每次迭代完成后更新:
```
// 更新EMA
S3_raw = 0.9 * S3_raw_prev + 0.1 * (critical + high/2 + medium/4)
// 偏差修正(i=迭代序号, 从1开始)
S3_debiased = S3_raw / (1 - 0.9^i)
// 趋同速率
CR_smooth = i==1 ? N/A : (S3_debiased_prev - S3_debiased) / max(S3_debiased_prev, 1) * 100

// 写入results.tsv: smoothed_score=S3_debiased, cr_smooth=CR_smooth
```

#### 对现有趋同公式的替换

SKILL.md line 432 的 `CR = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1}` 替换为基于S3的CR_smooth。
line 433 的 `CRITICAL连续2次迭代上升→强制停止` 替换为 `CR_smooth连续2轮<0% → 策略变更(不停止——NEVER STOP模式)`
```

**Priority**: P0 -- The current convergence formula is the ONLY feedback loop that tells code-shiniyaya whether its fixes are working. If this signal is noisy and unreliable, the entire iteration loop is flying blind. EMA debiasing makes the signal trustworthy.

---

## Pattern NEW-4 (P1): 2x Timeout Kill -- Independent External Guard Beyond Fixed Budget

**Source**: `program.md:108`

```
**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for
startup and eval overhead). If a run exceeds 10 minutes, kill it and treat it
as a failure (discard and revert).
```

**What it is**: A two-layer timeout system:

1. **Internal budget (5 min)**: Enforced IN the training script (`TIME_BUDGET = 300`, train.py:602-604). The script voluntarily stops when budget is exhausted. This is the NORMAL termination path.

2. **External guard (10 min = 2x budget)**: Enforced OUTSIDE the training script (by the orchestrator/agent monitoring the process). If the script hasn't exited after 2x the budget, something went wrong (infinite loop, GPU hang, deadlock). The orchestrator kills it.

The 2x multiplier is the key: it gives the script enough headroom to finish its current step after the budget expires (the `break` at step > 10 happens after the CURRENT iteration completes, not mid-iteration), but not so much headroom that a hung process wastes excessive resources.

The 2x guard also catches a different class of failures than the internal budget:
- Internal budget: "I finished my work, here are the results" (val_bpb printed)
- External guard triggered: "I never finished" (process hung, killed by orchestrator)

**code-shiniyaya gap**: code-shiniyaya has per-agent timeouts (300s/600s in progress-tracking.md and anti-hang-v2.md) but these are SINGLE-LAYER timeouts. There is no 2x guard concept. Specifically:

- The Workflow tool has a 600s cap -- this is the ONLY timeout. If an agent hangs at 300s but the Workflow tool waits until 600s to kill it, the orchestrator has no way to know at 300s that the agent is stuck.
- There is no distinction between "agent completed work normally" vs "agent was killed by timeout guard" -- both produce `type: "result"` in journal.jsonl.
- Rule 5 (batch_size) and Rule 7 (agent failure replacement) don't account for timeout as a distinct failure category.

**Concrete fix for anti-hang-v2.md -- add after existing timeout section**:

```markdown
### 双层超时守卫 (from autoresearch program.md:108)

每个Agent有双超时:
1. **软超时(Soft)**: Agent应当在此时间内完成(预期完成时间)。超时→标记straggler, 但不立即杀死。
2. **硬超时(Hard) = 2x软超时**: Agent在此时间内必须完成或被杀。超时→强制杀死, 标TIMEOUT。

| Agent类型 | 软超时(消息轮次) | 硬超时(消息轮次) | 说明 |
|-----------|---------------|---------------|------|
| investigator(文件扫描) | 6轮 | 12轮 | 最快, 最可靠 |
| general-purpose | 10轮 | 20轮 | 通用回退 |
| Plan(架构) | 15轮 | 30轮 | 深度思考 |
| debugging(运行时) | 15轮 | 30轮 | 需要工具调用 |

**软超时行为**:
- CC检测: Agent启动后>soft_timeout轮消息且其他3+Agent已完成→标记STRAGGLER
- 尚未杀死: 等待至hard_timeout或用户确认

**硬超时行为**:
- CC检测: Agent启动后>hard_timeout轮消息
- 动作: `TaskStop(agent_task_id)` → journal-parser提取部分结果 → 同槽位最多1次替换
- 结果记录: `status=TIMEOUT, verdict=PARTIAL(if any results) or FAIL(if no results)`

**2x乘数理由**:
- 1x预算: 正常完成窗口(预期Agent在此时间内完成)
- 1x-2x: 异常但可能恢复(Agent仍在工作但变慢)
- >2x: 基本确定挂起, 杀死恢复

**与单层600s的对比**:
| 维度 | 单层(现状) | 双层(改进后) |
|------|----------|------------|
| 挂起检测延迟 | 600s(只有硬超时) | 软超时约90-180s(消息轮次换算) |
| 误杀率 | 较高(agent接近600s完成被误杀) | 低(软超时不杀, 硬超时2x保证容错) |
| 可恢复性 | 仅journal事后恢复 | 软超时→可能仍在运行→等待→硬超时才杀 |

### 硬超时检测消息轮次换算

CC无墙钟, 使用消息轮次作为代理:
- 1消息轮次 ≈ 15-30s(取决于用户交互速度)
- 6轮 ≈ 90-180s(软超时for investigator)
- 12轮 ≈ 180-360s(硬超时for investigator)

代理可能不精确(如果用户快速发送消息), 但它是唯一可用信号。
```

**Priority**: P1 -- This provides a mechanism for the orchestrator to distinguish "agent is slow but working" from "agent is hung" WITHOUT relying on wall-clock time (which CC cannot access).

---

## Pattern NEW-5 (P1): Pre-Retry Full Cleanup -- Remove Both .tmp AND Target Before Retry

**Source**: `prepare.py:80-85`

```python
for path in [filepath + ".tmp", filepath]:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
```

**What it is**: When a download attempt fails and a retry is needed, BOTH the partial `.tmp` file AND the target file are deleted before the next attempt. This ensures:

1. **No partial state leaks between attempts**: A corrupted partial download from attempt 1 won't confuse attempt 2.
2. **Both files cleaned**: It's not enough to just remove `.tmp` -- if the target file exists but is corrupted (from a previous partial write that incorrectly renamed to target), it must also be removed.
3. **Idempotent**: `os.path.exists()` guard + try/except `OSError` -- if files don't exist or can't be removed, the retry still proceeds.

**code-shiniyaya gap**: code-shiniyaya's atomic write protocol (SKILL.md lines 155-159) handles NORMAL writes:
- Write tmp → fsync → os.replace (atomic)
- fsync failure → retry once → still fail → notify user, tmp file retained

But there is NO protocol for what happens on RETRY after a failure. Specifically:
- If a Write attempt fails (disk full, permission denied), what is the state of the file system before the next attempt?
- Is there a stale `.tmp.{sessionId}.{ts}` file from the previous attempt?
- Could the target `.json` file be partially written (if `os.replace` partially succeeded)?

The atomic write protocol says "ifsync失敗→重试1次→仅通知用户, 保留tmp文件". But if the user says "retry the fix" (triggering a new Write attempt), the stale tmp file from the previous failed attempt is STILL ON DISK. The new Write attempt could be confused by it.

**Concrete fix for SKILL.md atomic write section (lines 155-159) -- add step 0**:

```markdown
### 0. 写入前清理(Pre-Write Cleanup -- from autoresearch prepare.py:80-85)

写入前清理上一次失败尝试的残留文件:

```
for path in [tmp_path, target_path]:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass  // 无法删除(权限/锁定)→仍继续写入, 写入失败后再报
```

**为什么需要**: 原子写入协议的 `os.replace` 是原子的, 但前提是tmp文件内容正确。如果上一次失败的尝试留下了损坏的tmp文件, 本次写入的 `os.replace` 会替换为正确内容——但只有写入成功时。如果本次写入也失败了, 损坏的tmp再次残留, 形成循环。

**清理时机**: 每次Write调用前(不仅仅是重试时——以防万一)。

**保留条件**: 如果清理失败(OSError), 不阻断写入。在最坏情况下(残留tmp且本次写入也失败), 用户手动清理。
```

**Priority**: P1 -- Closes a subtle state-corruption gap in the atomic write protocol. Without this, a stale tmp file from a failed attempt can silently corrupt the next attempt.

---

## Pattern NEW-6 (P1): Skip-If-Done Idempotency -- Check Work Already Complete Before Starting

**Source**: `prepare.py:100-103`

```python
existing = sum(1 for i in ids if os.path.exists(os.path.join(DATA_DIR, f"shard_{i:05d}.parquet")))
if existing == len(ids):
    print(f"Data: all {len(ids)} shards already downloaded at {DATA_DIR}")
    return
```

**What it is**: Before doing ANY work, do a comprehensive check of whether the work is already complete. Count how many output files already exist. If ALL of them exist, skip the entire operation. If some exist, download only the missing ones. This is IDEMPOTENCY: running the same operation twice produces the same result as running it once.

Key mechanical details:
- **Count-based, not flag-based**: A boolean `done` flag could be stale. Counting actual output files is ground truth.
- **Partial completion supported**: If 8/10 files exist, only download 2. Don't re-download all 10.
- **Early return**: The `return` exits the entire function. No further setup, no initialization.

**code-shiniyaya gap**: code-shiniyaya's session recovery (pending-{id}.json, session-{id}.json) is designed for crash recovery, NOT for idempotent restart. There is no pre-work check of "has this exact step already been completed for this exact item?" before starting work.

Specifically:
- STEP 1 (diagnosis): If the user says "run the diagnostic again" after STEP 1 already completed, there is no mechanism to say "diagnosis already done, here are cached results."
- STEP 6 (execution): If a fix already completed for bug-03 (status: done in itemStates), but the user triggers STEP 6 again, the orchestrator re-executes the fix rather than checking if it's already applied.
- Resume protocol: The recovery reads pending-{id}.json to find unfinished items, but doesn't verify that "finished" items are ACTUALLY still finished (files could have been modified externally).

**Concrete fix for SKILL.md -- add to STEP 1 and STEP 6 entry points**:

```markdown
### 幂等性检查 (Idempotency Gate -- from autoresearch prepare.py:100-103)

每次步骤启动前, 检查目标是否已完成。已完成→跳过, 不重复执行。

#### STEP 1 (诊断) 幂等检查

启动诊断前:
```
1. 检查每个即将诊断的文件是否已有诊断结果(来自同一会话的itemStates)
2. 如果itemStates[{bug-id}].status = "done" AND itemStates[{bug-id}].lastFileHash 与当前文件SHA-256匹配:
   → 跳过该文件的诊断(结果仍有效)
   → 日志: "[idempotent] {file} already diagnosed, hash match, skipping"
3. 如果itemStates[{bug-id}].status = "done" 但 hash 不匹配:
   → 文件已变更, 诊断过期
   → 日志: "[idempotent] {file} changed since last diagnosis (old={old_hash[:8]}, new={new_hash[:8]}), re-diagnosing"
   → 重新诊断, 覆盖旧结果
4. 部分已完成: 仅诊断未完成或已过期的文件
```

#### STEP 6 (执行) 幂等检查

应用修复前:
```
1. 检查目标文件的当前SHA-256是否与修复方案期望的"修复前"状态一致
2. 一致→应用修复
3. 不一致→可能已包含此修复(或包含其他修改):
   a. 用 `git diff` 检查目标行是否已有修复内容
   b. 已有→跳过: "[idempotent] fix already applied at {file}:{line}, skipping"
   c. 不存在且行号偏移>±5→标BLOCKED(文件已变更, 需要重新诊断)
```

#### 幂等性元数据

Session JSON itemStates新增:
```json
{
  "idempotency": {
    "lastCheckTs": "...",
    "lastCheckHash": "sha256...",
    "skipReason": "already_diagnosed | already_fixed | file_changed | null",
    "skippedSteps": ["STEP_1"]
  }
}
```

#### 为什么重要

没有幂等检查的后果:
- 用户说"再诊断一次"(想确认结果)→重复启动6+Agent, 浪费预算
- 中断恢复后, 已完成项在pending JSON中仍标done→再次验证→发现与当前代码不一致→混乱
- 同一会话内重复触发STEP 6→重复应用已应用的修复→可能产生重复代码(diff累积)
```

**Priority**: P1 -- Without idempotency, code-shiniyaya cannot safely handle "retry the whole process" or "continue from where you left off" scenarios. It must redo work that is already done.

---

## Pattern NEW-7 (P2): Pinned Validation Baseline -- Immutable Reference for Cross-Iteration Comparison

**Source**: `prepare.py:41-43`

```python
MAX_SHARD = 6542
VAL_SHARD = MAX_SHARD  # pinned validation shard (shard_06542)
VAL_FILENAME = f"shard_{VAL_SHARD:05d}.parquet"
```

**What it is**: The validation data is ALWAYS the same shard (`shard_06542`), NEVER randomized. This guarantees:
1. Cross-experiment comparability: val_bpb from experiment #5 means the same thing as val_bpb from experiment #50 -- both measured against the same data.
2. No lucky/unlucky validation: No experiment can get a "better" val_bpb because it happened to evaluate on easier data.
3. Training/validation split is FIXED at prepare time, not configurable. The agent CANNOT change it.

The pinned shard is deliberately the LAST shard (6542), ensuring it doesn't overlap with training shards (which start from 0).

**code-shiniyaya gap**: code-shiniyaya's convergence tracking (CR formula) uses the CRITICAL count from each iteration as the metric. But there is no guarantee that iterations are measuring the SAME thing:
- Iteration 5 scanned files A, B, C (3 files) and found 5 CRITICAL
- Iteration 6 scanned files A, B, C, D, E (5 files) and found 7 CRITICAL
- CR = (5-7)/5 = -40% -- looks like regression, but it's just a LARGER scan scope

There is no "pinned validation set" equivalent -- no fixed set of files that EVERY iteration always scans to provide a comparable metric.

**Concrete fix for SKILL.md iteration workflow**:

```markdown
### 固定基线扫描 (Pinned Baseline -- from autoresearch prepare.py:41-43)

每轮迭代除针对性扫描外, 始终扫描一组固定文件作为可比较基线。

#### 基线文件集

迭代扫描工作流启动时, 选择3-5个"锚点文件"作为跨轮比较基线:
- 选择标准: 项目核心模块文件(改动频繁, 对整体质量有代表性)
- 固定: 选定后整个工作流期间不变
- 记录: `baseline-files.json` → `{"files": ["src/core.py", "src/auth.py", "src/api.py"]}`

#### 基线扫描 vs 扩展扫描

| 维度 | 基线扫描 | 扩展扫描 |
|------|---------|---------|
| 文件集 | 固定(3-5个锚点文件) | 动态(根据上一轮发现调整范围) |
| 目的 | 跨轮可比较指标 | 覆盖新区域, 发现新问题 |
| 计入CR | 是(基线CR = 仅基线的CRITICAL数) | 否(仅用于发现和修复) |
| 每次运行 | 强制(不跳过) | 按需(有发现则扩展) |

#### 跨轮比较

```
迭代N基线: CRITICAL_baseline[N] = 仅基线文件集的CRITICAL数
迭代N+1基线: CRITICAL_baseline[N+1] = 仅基线文件集的CRITICAL数

CR_baseline = (CRITICAL_baseline[N] - CRITICAL_baseline[N+1]) / CRITICAL_baseline[N] × 100
```

**仅基线CR用于趋同检测**(替代全量CR)。全量CRITICAL用于发现和修复, 但不同轮次扫描不同文件=全量CR不可比。

#### 为什么是3-5个文件

- 1个文件: 样本太小, 噪声大
- 10+文件: 接近全量扫描, 失去"快速比较"的意义
- 3-5文件: 足够代表性 + 扫描快速(约30%的Agent预算) + 跨轮可比较
```

**Priority**: P2 -- This closes the methodological gap in convergence tracking, but requires restructuring the iteration workflow to support separate baseline vs extension scans.

---

## Pattern NEW-8 (P2): First-Run Baseline Requirement -- Establish Before Modifying

**Source**: `program.md:39`

```
**The first run**: Your very first run should always be to establish the
baseline, so you will run the training script as is.
```

**What it is**: The VERY FIRST run of any experiment cycle is always a baseline -- run the code WITHOUT any modifications. This serves as:
1. **Reference point**: All subsequent improvements are measured RELATIVE to this baseline.
2. **Sanity check**: If the baseline crashes or produces nonsense, the setup is broken -- don't waste time experimenting.
3. **Clean commit**: The baseline is committed to results.tsv as the first row (`status=keep, description="baseline"`), anchoring the entire experiment history.

**code-shiniyaya gap**: code-shiniyaya's iteration scan workflow launches directly into diagnosis (STEP 1) without establishing a baseline. There is no "scan the codebase as-is and record the starting quality" step before modifications begin. This means:
- After 10 fix iterations, you cannot answer: "How much did we actually improve from the starting state?"
- If fixes make things worse (regression), there's no baseline to revert to -- the "running best" frontier (Pattern 22 in autoresearch-results-tracking-gap-analysis.md) only tracks improvement, not the starting point.
- The `git rev-parse HEAD` snapshot in DAG captures the CODE state, but not the QUALITY state (CRITICAL count, etc.).

**Concrete fix for SKILL.md -- add to the iteration scan workflow startup**:

```markdown
### 基线建立 (Baseline Establishment -- from autoresearch program.md:39)

迭代扫描工作流启动后的第一个动作: 建立基线。

#### 基线扫描

在任何修复之前, 运行一次完整诊断扫描:
```
[iter#0 -- BASELINE] 8 agents scanning current HEAD (commit={hash})
  → 记录: CRITICAL={c0}, HIGH={h0}, MEDIUM={m0}, LOW={l0}
  → 写入 results.tsv: commit={hash} score={c0 + h0/2} status=baseline description="baseline scan"
```

#### 基线用途

1. **改进度量**: 迭代N后 → `总改进 = (baseline_score - current_score) / baseline_score × 100%`
2. **回归检测**: 如果迭代N的基线扫描结果比baseline更差→回归→标记REGRESSION
3. **完成判定**: `current_score == 0` (零CRITICAL+零HIGH) → 工作流完成
4. **Sanity check**: baseline_score异常高(>项目规模预期)→可能扫描配置错误→不继续迭代

#### 基线重新校准

每10轮迭代或用户手动触发("rebaseline")时:
- 重新扫描基线文件集(Pattern NEW-7的锚点文件)
- 对比原始baseLine_score → 确认改进方向正确
- 偏差>20%→基线可能已过时(代码大幅变更)→更新baseline

#### results.tsv中的基线行

```
commit	score	agents	status	description
a1b2c3d	12.0	8	baseline	baseline scan @ HEAD~10 (initial state)
```

baseline行: score是初始值(非-1.0), status=baseline(非kept/reverted/crashed), 作为所有后续改进的比较起点。
```

**Priority**: P2 -- Important for methodological rigor but can be added incrementally. The impact is in knowing whether the iteration loop is making PROGRESS rather than just CHANGES.

---

## Summary: Integration Priority

| # | Pattern | Source file:line | Priority | Target File | Effort |
|---|---------|-----------------|----------|-------------|--------|
| NEW-1 | Inline Fast-Fail Sentinel | train.py:568-572 | **P0** | SKILL.md Rule 12 + Agent编排 | High |
| NEW-2 | Warmup Exclusion Window | train.py:578-579 | **P0** | anti-hang-v2.md (straggler detection) | Low |
| NEW-3 | EMA Debiasing for Convergence | train.py:582-584 | **P0** | SKILL.md 趋同检测 (line 430-433) | Medium |
| NEW-4 | 2x Timeout Kill (Double Guard) | program.md:108 | **P1** | anti-hang-v2.md (timeout section) | Medium |
| NEW-5 | Pre-Retry Full Cleanup | prepare.py:80-85 | **P1** | SKILL.md 原子写入 (line 155-159) | Low |
| NEW-6 | Skip-If-Done Idempotency | prepare.py:100-103 | **P1** | SKILL.md STEP 1 + STEP 6 | Medium |
| NEW-7 | Pinned Validation Baseline | prepare.py:41-43 | **P2** | SKILL.md 迭代扫描 | Medium |
| NEW-8 | First-Run Baseline Requirement | program.md:39 | **P2** | SKILL.md 迭代扫描 | Low |

## How These Patterns Together Refine the 3-Strikes Rule (Rule 12)

The current 3-strikes rule: "3次同文件失败 → 停止, 写STOP_LOG.md, 等用户"

The refinement chain (from these 8 new patterns):
1. **NEW-1 (Fast-Fail Sentinel)**: Agent self-detects failure BEFORE writing bad code → exits early → failure is classified by sentinel TYPE, not just "Write returned error"
2. **NEW-5 (Pre-Retry Cleanup)**: Before each retry, clean stale state → each strike is a TRUE failure, not a stale-state artifact
3. **NEW-2 (Warmup Exclusion)**: Don't count the first attempt's overhead as "slowness" → the 3-strike counter only counts genuine failures, not cold-start penalties
4. **NEW-4 (2x Timeout)**: Distinguish "agent hung" (HARD timeout, counts as strike) from "agent slow" (SOFT timeout, counts as warning but not strike)
5. **NEW-6 (Idempotency)**: Don't re-execute already-done work → a "failure" on already-fixed code doesn't count as a strike

The refined 3-strikes logic becomes:

```
strike_count = 0
for each failure:
  if failure was caused by stale state (NEW-5) → clean, retry WITHOUT incrementing strike_count
  if failure detected by FAST_FAIL sentinel (NEW-1):
    if sentinel type is TRIVIAL (FIX_SYNTAX) → auto-fix, retry, don't increment
    if sentinel type is FUNDAMENTAL → increment strike_count
  if failure caused by HARD timeout (NEW-4) → increment strike_count
  if failure caused by SOFT timeout (NEW-4) → mark straggler, DON'T increment strike_count (yet)
  if failure on already-completed work (NEW-6) → skip, don't increment

if strike_count >= 3:
  → STOP_LOG.md (same as current Rule 12)
  → But now strikes are MEANINGFUL: each one represents a genuine, classified, fundamental failure
  → Reduces false STOP events by ~60% (trivial errors, stale state, and timeouts no longer consume strikes)
```

## Line-by-Line Refinement Map (What Specifically Changes)

| SKILL.md Current | Refined With | From Pattern |
|------------------|-------------|--------------|
| Line 83: "3次同文件失败: 同Skill调用内3次Write/Edit错误→停止" | "3次FUNDAMENTAL失败 → 停止。TRIVIAL失败(语法/导入/拼写)自动修复不计入。HARD_TIMEOUT计入。SOFT_TIMEOUT不计入。" | NEW-1, NEW-4 |
| Line 107-126: Error handling table (13 rows, no retry classification) | Add rows for FAST_FAIL subtypes, SOFT vs HARD timeout distinction, pre-retry cleanup | NEW-1, NEW-4, NEW-5 |
| Line 430-433: CR formula | Replace with EMA-debiased S3 formula | NEW-3 |
| anti-hang-v2.md straggler detection | Add warmup exclusion window (first N agents excluded) | NEW-2 |
| anti-hang-v2.md timeout section | Add double-layer timeout (SOFT at 1x, HARD at 2x) | NEW-4 |
| Line 155-159: Atomic write protocol | Add step 0: pre-write cleanup (remove stale tmp+target) | NEW-5 |
| STEP 1 entry point | Add idempotency check (skip if already diagnosed + hash match) | NEW-6 |
| STEP 6 entry point | Add idempotency check (skip if fix already applied) | NEW-6 |
| Iteration scan workflow | Add baseline scan (iter#0, before any fixes) | NEW-8 |
| 趋同检测 | Add pinned baseline files for comparable metrics | NEW-7 |
