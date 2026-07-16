# code-shiniyaya Gap Analysis: autoresearch Full Autonomy Patterns

Source: `C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src\`
Date: 2026-07-16
Method: Line-by-line deep scan of program.md (entire file), train.py, prepare.py, README.md, analysis.ipynb
Target files: SKILL.md, anti-hang-v2.md, high-impact-patterns.md

---

## Patterns Already Integrated (4 patterns from prior scans)

| Prior Pattern # | Source | Status in code-shiniyaya |
|---|---|---|
| #2 — Git as state machine | program.md:91-105 | Documented in high-impact-patterns.md but NOT operationalized in SKILL.md iteration loop |
| #4 — Crash classification | program.md:108-109 | Documented in high-impact-patterns.md but NOT operationalized in SKILL.md rule 12 |
| #9 — NEVER STOP directive | program.md:111-112 | Briefly mentioned, but contradicted by convergence-failure auto-stop |
| Fixed budget as proxy | program.md:34-35 | Only in the iteration-task.md planning doc, not in SKILL.md |

**Key insight**: The 4 patterns above were identified but ONLY exist in memory docs. They are NOT actually built into the SKILL.md execution workflow. These gaps are re-identified with concrete integrations below.

---

## Newly Discovered Patterns (NOT in any prior scan)

### Pattern A: LOOP FOREVER Without Self-Termination Gate
**Source**: `program.md:94` ("LOOP FOREVER:") and `program.md:111-112` ("NEVER STOP... do NOT pause to ask the human if you should continue... You are autonomous.")
**code-shiniyaya gap**: SKILL.md line 433 has `趋同失败: CRITICAL连续2次迭代上升→强制停止+策略变更`. This is a SELF-TERMINATION gate that contradicts the NEVER STOP philosophy. The autoresearch model runs until the human kills it — the agent never decides to stop.
**Gap**: code-shiniyaya currently conflates "failed strategy" with "stop working". autoresearch separates them: failed strategy = change direction, not stop. The agent NEVER stops itself.
**Priority**: P0

**Fix — Add to SKILL.md iteration workflow section (after line 433)**:
```markdown
### 自主门禁 (Autonomy Gate — from autoresearch program.md:94,111-112)

**NEVER STOP**: 迭代循环一旦启动，CC 绝不自行停止。以下情况均不触发停止：

| 情况 | 错误做法 | 正确做法 |
|------|---------|---------|
| CRITICAL连续上升 | ~~强制停止~~ | 策略变更(换Agent类型、调整提示词、缩小扫描范围)——不停止 |
| 趋同速率<0 | ~~告警并停止~~ | 标记为DIVERGING，切换策略，继续迭代 |
| "目标达成" | ~~停止~~ | 验证(再跑1轮确认零CRITICAL+零HIGH)→报告给用户，但**继续监控**——用户可能添加新文件 |
| 连续N轮无改进 | ~~停止~~ | 增加探索半径(扫描更多文件、引入新参考源)、报告趋同停滞→等用户kill |

**仅用户说"stop"/"停"/CTRL+C 时停止。CC 绝不自行声明完成。**

**长时间静默策略**: 用户可能数小时无消息(睡觉/离开)。这是正常操作模式——不是故障。禁止"用户久未回复"触发任何自动操作。迭代日志持续写入，用户返回时可回放。
```

### Pattern B: Results Log Table (TSV) for Cross-Iteration Comparison
**Source**: `program.md:64-88` (entire "Logging results" section — TSV with 5 columns: commit, val_bpb, memory_gb, status, description) and `program.md:102` ("Record the results in the tsv... do not commit the results.tsv file")
**code-shiniyaya gap**: code-shiniyaya has NO persistent results log. Session JSON tracks per-item status but there is no cross-iteration comparison table. Convergence rate (CR) is computed from CRITICAL counts in CC's working memory — no persisted record. This means if context resets, CR history is lost.
**Gap**: No TSV log = no ability to analyze trends across sessions, no post-hoc analysis, no "wake up and see what happened" user experience.
**Priority**: P0

**Fix — Add to SKILL.md state files section (after line 160)**:
```markdown
### 迭代结果日志 (`results-{project}.tsv`)

制表符分隔(非逗号——逗号在description中破坏解析)。不纳入git追踪(.gitignore)。

```
iteration	run_id	start_ts	end_ts	agents_launched	agents_done	pass	partial	fail	critical	high	medium	low	cr	status	description
```

| 字段 | 说明 |
|------|------|
| iteration | 自增整数，会话内从1开始 |
| run_id | 工作流UUID前8字符 |
| start_ts/end_ts | ISO 8601 时间戳 |
| agents_launched/done | 启动/完成的Agent数 |
| pass/partial/fail | 各维度计数 |
| critical/high/medium/low | 严重度分布 |
| cr | 趋同速率 (上一轮CRITICAL vs 本轮) |
| status | `converging` / `plateau` / `diverging` / `crashed` |
| description | 本轮改动简述(<120字符) |

**写入时机**: 每轮迭代完成后追加一行。CSV/appending: 打开文件→seek-to-end→写行+flush——如果文件不存在则写header行。

**分析用途**: 用户返回时可快速扫描TSV了解进展。支持 analysis.ipynb 风格的可视化(jupyter notebook, matplotlib 折线图, 运行最佳值)。
```

### Pattern C: Trivial-Crash Skip (Does Not Consume Retry Budget)
**Source**: `program.md:110` ("If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log 'crash'...")
**code-shiniyaya gap**: SKILL.md rule 12 says "3次同文件失败→停止". This treats ALL failures identically — a typo counts the same as an architectural bug. This wastes retry budget on trivial errors.
**Gap**: No distinction between Type-A crashes (typo/missing import/syntax error — auto-fix, don't count) and Type-B crashes (OOM/architecture broken — count toward retry limit).
**Priority**: P1

**Fix — Add to SKILL.md rule 12 and error handling table**:
```markdown
### 崩溃分类法 (from autoresearch program.md:110)

修复失败分两类，不同处理：

| 类型 | 判断 | 示例 | 处理 |
|------|------|------|------|
| **Type A: Trivial** | 单文件、单函数、确定性修复(无歧义)、修复后100%可验证 | 拼写错误、缺失导入、缩进错误、除零、空指针 | 自动修复+重跑，**不计入重试配额**。连续3次Type A同位置→升级为Type B |
| **Type B: Fundamental** | 多文件、跨模块、架构变更、修复不确定 | OOM、逻辑错误、API不兼容、架构问题、并发竞态 | 计入重试配额。3次Type B同文件→停止(STOP_LOG.md)。不跨调用累计 |

**Type A判定检查** (快速门控，任意否定即升级为Type B):
1. 修复是否仅涉及1个文件？(YES=继续)
2. 修复是否在1个函数/类范围内？(YES=继续)
3. 修复是否确定性(不存在修复后仍需验证歧义)？(YES=继续)
4. 修复后果是否<5行变更？(YES=继续)
→ 全部YES = Type A。任意NO = Type B。
```

### Pattern D: Fixed Iteration Budget (Time/Agent Budget Per Round)
**Source**: `program.md:24` ("fixed time budget of 5 minutes") and `train.py:30` (`TIME_BUDGET = 300` in prepare.py, imported by train.py)
**code-shiniyaya gap**: code-shiniyaya has per-agent timeouts (300s/600s) but no fixed BUDGET per iteration. Different rounds can take wildly different amounts of time/agents, making cross-round comparison noisy. The convergence formula uses CRITICAL counts but doesn't normalize for effort.
**Gap**: No fixed-per-iteration budget means the metric "CRITICAL decreased from 5 to 3" is not comparable if round 1 used 8 agents and round 2 used 12 agents. autoresearch solves this by fixing 5 minutes — always the same effort, so improvement is directly comparable.
**Priority**: P1

**Fix — Add to SKILL.md iteration workflow section**:
```markdown
### 固定迭代预算 (from autoresearch program.md:24, prepare.py:30)

每轮迭代使用固定预算使跨轮结果直接可比较：

| 参数 | 固定值 | 说明 |
|------|--------|------|
| agents_per_iteration | 8 | 每轮固定8 Agent（不动态增减） |
| max_agent_soft_s | 300 | Agent 软超时 |
| max_agent_hard_s | 600 | Agent 硬超时 |
| max_iteration_wall_s | 3600 | 整轮硬上限(1小时) |

**禁止**: 因趋势不理想而增加Agent数量。"再加2个Agent看看"——这使结果不可比较。改为变更策略(Agent类型/提示词/扫描范围)。

**固定预算下的公平比较**:
- CR = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1} — 仅在agent_count_{n-1} == agent_count_n 时有效
- 如果agent_count不同(如因超时部分slot失败)→标注 `agents_skewed` → CR标为 unreliable
```

### Pattern E: Simplicity Criterion as Explicit Decision Rule
**Source**: `program.md:37` ("Simplicity criterion: All else being equal, simpler is better... A 0.001 val_bpb improvement that adds 20 lines of hacky code? Probably not worth it. A 0.001 val_bpb improvement from deleting code? Definitely keep. An improvement of ~0 but much simpler code? Keep.")
**code-shiniyaya gap**: code-shiniyaya has NO simplicity weighing. Fixes are evaluated purely on correctness/risk — a 20-line hack for a minor fix passes the same gates as a 3-line elegant fix. The "keep or discard" decision has no complexity axis.
**Gap**: Without simplicity criterion, code-shiniyaya may make the codebase worse over successive iterations (complexity/entropy creep).
**Priority**: P2

**Fix — Add to SKILL.md STEP 6 (after line 288)**:
```markdown
#### 简洁性门控 (from autoresearch program.md:37)

每次修复前评估简洁性成本。修复方案通过此门控才执行：

```
修复效果 (delta_quality) = severity_before - severity_after
复杂度成本 (delta_complexity) = new_lines - deleted_lines + risk_score

IF delta_complexity <= 0 AND delta_quality >= 0:
    → KEEP (净简化，自动通过)
ELIF delta_quality > 3 * delta_complexity:
    → KEEP (效果远超成本)
ELIF delta_complexity > 0 AND delta_quality == 0:
    → DISCARD (仅增加复杂度，无效果)
ELSE:
    → REVIEW (需要用户判断)
```

**risk_score**: 每跨文件依赖+3, 每新增导入+1, 每正则表达式/反射/动态代码+5, 每删除共享函数-2。

**"删除即胜利"原则**: 删除代码且指标不退化 → 自动KEEP(不通过双批准门控——纯删除无风险)。
```

### Pattern F: Output Redirection (No Context Flooding)
**Source**: `program.md:99` ("Run the experiment: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)") and `program.md:101` ("Read out the results: `grep "^val_bpb:\|^peak_vram_mb:" run.log`")
**code-shiniyaya gap**: code-shiniyaya has inline log() but NO mechanism to prevent agent output from flooding context. In an 8-agent workflow, verbose agent output consumes massive context tokens. autoresearch redirects ALL output to file and only reads the key metrics — keeping context window free for strategic reasoning.
**Gap**: The iteration scan workflow launches 8 agents whose full output streams through log(). For 100 iterations (8-hour sleep), this generates enormous context. code-shiniyaya has no mechanism to suppress verbose output.
**Priority**: P1

**Fix — Add to anti-hang-v2.md and SKILL.md iteration workflow**:
```markdown
### Context Budget Protection (from autoresearch program.md:99,101)

Agent 输出采用两级模式：完整输出写文件，仅指标通过 log() 暴露。

**Agent 输出处理**:
```
Agent 完整结果 → 写入 {workflow_dir}/outputs/{agent_key}.json
                → CC 仅通过 log() 输出: "[{key}] verdict={PASS/FAIL} issues={N}"
```

**绝不**让完整Agent报告进入对话上下文。需要细读时用 Read tool 读特定输出文件。

**log() 格式** (极致压缩):
```
log('[{k}] {v} {s}+{c}+{h}')  // 例: "[usability-1] PASS 0+0+0"
log('[{k}] HANG')              // 超时
log('[iter{N}] DONE {p}/{f}/{c} CR={cr}%')
```

**恢复**: 用户说"展开agent-3"→CC Read完整输出文件。不预先加载。
```

### Pattern G: Results-Driven Branch Advancement (Git as Comparison Engine)
**Source**: `program.md:92` ("dedicated branch"), `program.md:103` ("git reset --hard HEAD~1" implicitly via "reset back"), `program.md:106` ("you 'advance' the branch, keeping the git commit... If val_bpb is equal or worse, you git reset back")
**code-shiniyaya gap**: code-shiniyaya tracks state via JSON files (session-{id}.json, dag-{id}.json) and only uses git for DAG snapshot (`git rev-parse HEAD`). The actual iteration results (improved/not improved) are NOT encoded in git commits. There is no mechanism to "reset to before this iteration's changes" using native git.
**Gap**: autoresearch's git-based state model is simpler and more robust than code-shiniyaya's JSON state model — git already handles snapshot, rollback, and history. A single `git reset --hard` replaces multiple JSON state recovery steps.
**Priority**: P2

**Fix — Add to SKILL.md iteration workflow**:
```markdown
### Git-Based Iteration State (from autoresearch program.md:92,103,106)

使用 git 而非 JSON 状态文件追踪每轮迭代：

**每轮迭代前**:
1. `git stash` 当前修改 → 干净工作区
2. 应用本轮修复
3. `git add -A && git commit -m "iter{N}: {description}"`
4. 运行验证(本轮扫描)
5. CRITICAL 减少 → 保留提交(`keep`)
6. CRITICAL 不变或增加 → `git reset --soft HEAD~1` (撤销提交，但保留修改在暂存区以便对比)

**优势**:
- `git log --oneline` = 自动迭代历史
- `git diff iter{5}..iter{10}` = 跨轮差异查看
- `git reset` = 无状态文件损坏风险
- session JSON 仅追踪当前STEP和itemStates(细粒度逐项追踪仍需要)，但迭代级快照由git负责

**与现有状态文件的职责分工**:
- session-{id}.json: 当前STEP、itemStates逐项状态、mode (CC内存——不持久)
- git: 迭代间代码历史 (持久)
- results-{project}.tsv: 迭代间指标趋势 (持久)
```

### Pattern H: "Think Harder" Escalation (Not Stop, Change Strategy)
**Source**: `program.md:112` ("If you run out of ideas, think harder — read papers referenced in the code, re-read the in-scope files for new angles, try combining previous near-misses, try more radical architectural changes.")
**code-shiniyaya gap**: code-shiniyaya's convergence failure message says "策略变更(非更多修复——不同方法)" at line 433, but provides NO concrete escalation path. What does "different method" mean? autoresearch gives an explicit escalation playbook.
**Gap**: No "think harder" playbook. The agent hits convergence failure and has no structured way to generate new ideas.
**Priority**: P2

**Fix — Add to SKILL.md convergence section**:
```markdown
### 策略升级阶梯 (from autoresearch program.md:112)

趋同失败(CRITICAL连续2次迭代上升)不停止——沿此阶梯升级：

| 阶梯 | 策略 | 具体行动 |
|------|------|---------|
| **L1: 审计** | 读先前失败项 | 重新读FAILED_FIXES.md, STOP_LOG.md → 寻找"为什么上次修复没生效" |
| **L2: 扩源** | 增加参考源 | 扫描之前未使用的参考源(reference-sources.md 中未复用的项目) → 寻找被遗漏的模式 |
| **L3: 重组** | 更换Agent角色 | 把investigator换到之前用general-purpose的维度，换提示词模板 |
| **L4: 激进** | 放宽约束 | 临时提升agent_cap到80，允许更高并发，接受更大风险 |
| **L5: 外脑** | 人工介入 | "我卡住了。当前CRITICAL={c} HIGH={h}。已尝试L1-L4。建议?" → 展示results.tsv趋势 + 最后3轮description → 等用户反馈 |

**每个阶梯最多3轮迭代 → 无改进 → 升下一阶梯。L5无用户响应 → 回到L2(重新扫描不同参考源)**。

**绝不**: 因为趋同失败而停止。
```

### Pattern I: Sleep-Safe Design Philosophy
**Source**: `program.md:114` ("As an example use case, a user might leave you running while they sleep. If each experiment takes you ~5 minutes then you can run approx 12/hour, for a total of about 100 over the duration of the average human sleep. The user then wakes up to experimental results, all completed by you while they slept!")
**code-shiniyaya gap**: code-shiniyaya's convergence detection and "用户久未回复→等待批准中"(error table STEP 5) assumes synchronous interaction. The sleep scenario is not designed for — there is no "just keep going, I'll check in the morning" mode.
**Gap**: code-shiniyaya is designed as a synchronous CC<->Codex<->User loop, not as an autonomous overnight process. But the iteration scan workflow IS autonomous (no Codex needed in degraded mode) — the gap is that the skill doesn't ADVERTISE or SUPPORT this use case.
**Priority**: P2

**Fix — Add to SKILL.md header or "不可跳过" table**:
```markdown
### 无人值守模式 (Sleep-Safe Autonomous Mode)

迭代扫描工作流支持完全无人值守运行——用户启动后可离开数小时。

**启动**: 用户说"迭代扫描, 无人值守" 或 "全自动扫描" 或 "auto-scan overnight"

**行为变更**:
- 所有假阳性门控 → 自动跳过(不询问确认)
- STEP 5 双批准 → 自动降级(Codex不可用→用户单批准→但由于无人值守→CC自我验证6+Agent代替)
- 所有"等用户"/"等Codex" → 自动超时→降级(不等待)
- 禁止发送"继续等/跳过?"类询问
- 所有报告写入 results-{project}.tsv + 桌面/报告/
- 收敛检测后不停止——升级策略阶梯(Pattern H)

**用户返回时**:
1. 读 results-{project}.tsv → 展示进展摘要
2. 读 桌面/报告/ 最新报告 → 展示发现
3. "共{N}轮迭代, {kept}轮改进, {critical_remaining} CRITICAL 剩余。继续?"
```

### Pattern J: Pre-Commit Before Experiment (Immutable Record)
**Source**: `program.md:3` ("git commit") inside the loop — commit BEFORE running experiment, so the commit hash is an immutable record of what was tried.
**code-shiniyaya gap**: code-shiniyaya does `git diff --stat` for plan-code gap verification but does NOT commit before applying fixes. This means if a fix goes wrong, there's no single-command rollback.
**Gap**: No pre-fix commit = no atomic rollback unit. Rule 12's "3次同文件失败→STOP_LOG.md" writes a log file but doesn't restore clean state.
**Priority**: P2

**Fix — Add to SKILL.md STEP 6**:
```markdown
**前置(新增)**: 执行修复前 `git add -A && git commit -m "pre: iter{N} {bug_id}"` — 创建回滚点。修复失败→`git reset --hard HEAD~1`恢复。修复成功且验证通过→`git commit --amend -m "fix: iter{N} {bug_id}"` 标记为已确认修复。
```

---

## Priority Summary

| # | Pattern | Source file:line | Priority | Target file |
|---|---------|-----------------|----------|-------------|
| A | LOOP FOREVER — 永不自行停止 | program.md:94,111-112 | **P0** | SKILL.md |
| B | Results TSV日志 | program.md:64-88 | **P0** | SKILL.md |
| C | Type-A vs Type-B 崩溃分类 | program.md:110 | **P1** | SKILL.md |
| D | 固定迭代预算 | program.md:24, prepare.py:30-31 | **P1** | SKILL.md |
| E | 简洁性门控 | program.md:37 | **P2** | SKILL.md |
| F | 输出重定向(防上下文溢出) | program.md:99,101 | **P1** | anti-hang-v2.md |
| G | Git分支推进(状态模型) | program.md:92,103,106 | **P2** | SKILL.md |
| H | "思考更深入"策略阶梯 | program.md:112 | **P2** | SKILL.md |
| I | 睡眠安全/无人值守模式 | program.md:114 | **P2** | SKILL.md |
| J | 修复前提交(原子回滚) | program.md:3 | **P2** | SKILL.md |

## Quick Integration Map

To achieve full autonomy parity with autoresearch, apply these minimal changes:

1. **SKILL.md line 433**: Replace `趋同失败: CRITICAL连续2次迭代上升→强制停止` with Pattern A (NEVER STOP + strategy escalation ladder, Pattern H)
2. **SKILL.md after line 160**: Add Pattern B (results TSV)
3. **SKILL.md rule 12**: Refine with Pattern C (Type A/Type B crash classification)
4. **SKILL.md iteration workflow**: Add Pattern D (fixed budget) + Pattern I (sleep-safe mode)
5. **anti-hang-v2.md**: Add Pattern F (context budget protection / output redirection)
6. **SKILL.md STEP 6**: Add Pattern E (simplicity gate) + Pattern J (pre-commit)
7. **high-impact-patterns.md**: Update Pattern #9 (NEVER STOP) with concrete operationalization from Pattern A
