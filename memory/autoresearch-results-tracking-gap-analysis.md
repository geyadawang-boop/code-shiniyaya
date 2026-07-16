# autoresearch Result Tracking Patterns -- Gap Analysis vs code-shiniyaya v3.7.0

Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src
Target: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
Date: 2026-07-16

## DIMENSION: Tabular Results Logging -- TSV append-only log with git commit primary key, ternary taxonomy (keep/discard/crash), sentinel values.

---

## Pattern 19 (P0): TSV Append-Only Cumulative Results Log

**Source**: `program.md:66-88`
```tsv
commit	val_bpb	memory_gb	status	description
a1b2c3d	0.997900	44.0	keep	baseline
b2c3d4e	0.993200	44.2	keep	increase LR to 0.04
c3d4e5f	1.005000	44.0	discard	switch to GeLU activation
d4e5f6g	0.000000	0.0	crash	double model width (OOM)
```

**code-shiniyaya gap**: Each session's state files (session-{id}.json, pending-{id}.json, dag-{id}.json) are isolated per session. There is NO cumulative append-only log spanning sessions. After 10 sessions, there is no file you can read to see which fixes worked across all sessions. The state files are diagnostic state, not a results ledger.

**Why this matters**: Without a cumulative results log, code-shiniyaya has no:
- Cross-session visibility ("did fix X in session 3 survive into session 8?")
- Aggregate statistics (keep/discard/crash rates)
- Reproducibility chain (which commit was this fix attempted on?)
- Improvement trend (is the codebase getting better over time?)

**Concrete fix for SKILL.md -- add after "状态文件" section (line 164)**:

```markdown
## 累积结果日志 (`results.tsv`)

**路径**: `{project_root}/reports/results.tsv` (追加写入, 不随会话删除)
**格式**: TSV (制表符分隔, 5列), Git提交为主键

### Schema
```
commit	score	agents	status	description
```

| 列 | 类型 | 说明 |
|----|------|------|
| commit | str(7) | `git rev-parse --short HEAD` 的前7字符——每次修复尝试的源码快照锚点 |
| score | float | 综合评分: CRITICAL数 + HIGH数/2, 越低越好。crash/未执行=-1.0 (哨兵值) |
| agents | int | 本次修复尝试消耗的Agent总数(诊断+验证+执行)。crash=0 (哨兵值) |
| status | enum | `kept`(改进, 提交保留)/`reverted`(回退, git reset)/`crashed`(崩溃/挂起, 提交保留留痕) |
| description | str | 本次尝试做了什么, 中文简短描述, ≤80字符 |

### 哨兵值
- score=-1.0: 无效运行(崩溃/未完成/全部Agent超时)。哨兵区别于真实0分。
- agents=0: 诊断失败或全部Agent在启动前失败。

### 追加写入协议
1. STEP 6每次修复尝试完成后: 读当前HEAD的短哈希 → 计算score → 写一行TSV
2. 使用追加模式打开(`"a"`), 写后立即flush+fsync
3. 失败回退: 如果该commit已存在行(重复键)→ 追加新行(不覆盖, 保留历史——同一commit可能多次尝试)
4. STEP 6修复成功+验证通过=kept, 验证失败/变差=reverted, 执行中崩溃=crashed
5. results.tsv不可提交到git——加入.gitignore(同autoresearch的`results.tsv`)

### 示例
```
commit	score	agents	status	description
a1b2c3d	4.0	12	kept	baseline diagnostic scan
b2c3d4e	2.0	10	kept	fix null-guard in handlers.py:142
c3d4e5f	5.0	14	reverted	add type annotation (regression, score worsened)
d4e5f6g	-1.0	0	crashed	attempted async chain refactor (agent timeout)
e5f6g7h	1.5	8	kept	replace bare except with specific handlers
```

### 分析能力(由analysis.ipynb参考)
- 保持率 = kept/(kept+reverted+crashed)
- 运行最佳(前沿): 跨所有行的累计最小score
- 每次改进增量: 当前kept行的score - 上一个kept行的score
- 趋势: score向上/向下/平稳横跨会话
```

**Concrete fix for high-impact-patterns.md -- add after pattern 18 (line 117)**:

```markdown
### 模式 19: TSV Append-Only Cumulative Results Log (autoresearch)
- **源**: `autoresearch-src/program.md:66-88`, `autoresearch-src/analysis.ipynb` (notebook cells)
- **模式**: 所有修复尝试写入单一TSV文件(results.tsv), git commit短哈希为主键, 5列(commit/score/agents/status/description), 追加写入, 跨会话持久化
- **code-shiniyaya 差距**: 会话状态JSON文件是临时诊断状态, 非累积结果账本。10个会话后无法看到跨会话改进趋势、保持率、最佳前沿。
- **修复**: SKILL.md新增"累积结果日志"章节; STEP 6每次修复后追加写一行; 新增 `analysis.ipynb` 参考笔记本
- **预期收益**: 跨会话可见性、可复现性链、聚合统计、改进趋势检测
```

---

## Pattern 20 (P0): Ternary Outcome Taxonomy (keep/discard/crash) with Sentinel Values

**Source**: `program.md:82-88` -- explicit three-status outcome taxonomy. Crash uses sentinel values (0.000000 for val_bpb, 0.0 for memory_gb) distinct from valid-but-bad values. `program.md:108-109` -- crash further split into trivial (fix+retry) vs fundamental (abandon).

**code-shiniyaya gap**: code-shiniyaya's 7-step workflow has per-item states (itemStates: status+substep) but no OUTCOME classification per fix attempt. There's no formal taxonomy distinguishing:
- Fix worked, code improved (KEPT equivalent)
- Fix applied but made things worse/neutral, rollback (REVERTED)
- Fix attempt crashed during execution, partial state left (CRASHED)

The 3x failure rule (rule 12: "3次同文件失败→停止") mixes trivial bugs with fundamental bugs -- no distinction between "typo in fix code" (trivial, should auto-retry without consuming quota) vs "approach is fundamentally wrong" (should consume quota).

**Why this matters**: 
- Currently all failures consume the 3-strike quota equally. A typo in a fix line counts the same as an architectural dead end.
- No formal crash taxonomy means crash state is ambiguous: did it crash because code is wrong, or because Agent infrastructure killed it?
- Sentinel values prevent 0.0 score ambiguity (is 0.0 "perfect fix" or "crash"?).

**Concrete fix for SKILL.md -- add to rule 12 (line 83)**:

```markdown
### 修复尝试结果分类法

每次STEP 6修复尝试完成后, 按三元分类法记录:

| 结果 | 状态 | 含义 | 处理 |
|------|------|------|------|
| KEPT | 修复成功, 验证通过, score改进 | 改进 | 提交保留, 前进到下一项 |
| REVERTED | 修复已应用但评分未改进或变差 | 无效或退步 | git reset回退, 标记reverted |
| CRASHED | 修复尝试中崩溃(OOM/Agent超时/语法错误导致无法执行) | 无法评估 | 提交保留留痕(不reset), 标记crashed |

**CRASHED子分类**:
- **Type A -- 琐碎错误**(拼写错误/缺失导入/语法错误): 自动修复(≤2次)后重试同一修复方案。不消耗规则12的重试配额。
- **Type B -- 根本性错误**(OOM/架构不兼容/Agent全超时): 消耗规则12的重试配额。3次Type B→停止。
- **Type C -- 哨兵**(Agent工具基础设施崩溃/TaskStop杀死): 同slot最多2次替换(规则7已有, 此处整合)。2次替换后→永久跳过。

**哨兵值**:
- score=-1.0: 无效运行(CRASHED/未执行)。与真实score=0.0(零CRITICAL+零HIGH)明确区分。
- agents=0: 诊断/验证全部失败, 无有效Agent完成。
```

**Concrete fix for high-impact-patterns.md -- add after pattern 19**:

```markdown
### 模式 20: Ternary Outcome Taxonomy with Sentinel Values (autoresearch)
- **源**: `autoresearch-src/program.md:82-88`, `autoresearch-src/program.md:108-109`
- **模式**: 每次尝试三态分类(keep/discard/crash), crash使用哨兵值(0.0)与有效但糟糕的结果区分, crash进一步细分为琐碎(自动重试不耗配额)vs根本性(耗配额)
- **code-shiniyaya 差距**: itemStates的status字段没有三元结果分类; 3次失败规则混合所有失败类型; 无哨兵值区分0分vs未执行
- **修复**: SKILL.md规则12扩展为三元分类+CRASHED子分类+哨兵值; 琐碎错误自动修复不消耗重试配额
- **预期收益**: 更精准的重试配额管理, 可分析的修复历史, 无歧义的哨兵值
```

---

## Pattern 21 (P1): Git Commit as State Machine Primary Key

**Source**: `program.md:91-105` -- "commit→run→grep results→if improved keep commit, else git reset". The commit hash is the state-machine primary key. Branch advances only on improvements. `program.md:102` -- results.tsv NOT committed to git (untracked), keeping the ledger separate from source history.

**code-shiniyaya gap**: code-shiniyaya's DAG snapshot (`dag-{id}.json` → `snapshot`: `git rev-parse HEAD`) captures the starting state at session begin but is NOT used as a primary key for results tracking. Restore checks use `lastFileHash` (SHA-256 of individual target files) but not the git commit as a holistic state anchor.

**Why this matters**: Without git commit as primary key, you cannot:
- Reproduce the exact code state when a fix was attempted
- Know if two sessions started from the same code
- Reset cleanly when a fix chain goes bad

**Concrete fix for SKILL.md -- add to STEP 6 (line 281, before "前置")**:

```markdown
**Git锚点**: 每次修复尝试前 → `git rev-parse HEAD` → 记录为attempt_commit。修复后:
- kept: commit保留, 当前分支前进到此commit
- reverted: `git reset --hard attempt_commit` 回退到尝试前状态
- crashed: commit保留(留痕可查), 代码状态可能不干净→`git reset --hard attempt_commit`后重新应用已kept的修复链
```

**Concrete fix for high-impact-patterns.md -- add after pattern 20**:

```markdown
### 模式 21: Git Commit as State Machine Primary Key (autoresearch)
- **源**: `autoresearch-src/program.md:91-105`
- **模式**: 每次实验=一个git commit。改进→分支前进(keep commit)。退步→git reset回退(discard)。崩溃→commit保留留痕(crash)。分支状态=所有已kept改进的累积。
- **code-shiniyaya 差距**: DAG用snapshot锚定初始状态, 但每次修复尝试不以git commit为主键。reset/keep决策不基于git操作。
- **修复**: SKILL.md STEP 6添加Git锚点流程: attempt_commit记录→kept/reverted/crashed各对应git操作
- **预期收益**: 可复现的修复链, 干净的失败回退, git log本身成为改进历史
```

---

## Pattern 22 (P1): Running Minimum Frontier (Cumulative Best Across Sessions)

**Source**: `analysis.ipynb` cell `79jh74veqg9` -- `running_min = kept_bpb.cummin()` tracks the best result achieved so far. Cell `re1f8za8oj9` -- baseline vs best comparison with total improvement percentage.

**code-shiniyaya gap**: Convergence rate (CR) in SKILL.md line 431 tracks CRITICAL changes within a single iteration but does NOT track a running-best frontier across sessions. After N sessions, there's no instant read of "best score ever achieved was X in session Y".

**Why this matters**: Running minimum provides instant answer to "are we making progress overall?" Without it, you can only compare adjacent iterations, not the full history.

**Concrete fix for SKILL.md -- add to 趋同检测 section (line 430)**:

```markdown
**运行最佳前沿(Running Best)**: 跨会话追踪累计最佳score。
- 每次results.tsv追加后: 读所有行的score列→`cummin()`→最新值=运行最佳
- 当前score > 运行最佳: 本次修复有效(改进达到新前沿)
- 当前score = 运行最佳: 保持前沿
- 当前score < 运行最佳但行状态=kept: 本次改进但未超越历史最佳
- 报告格式: `[前沿] best_score=X.X (session={id}, commit={hash}) | 当前=X.X | 总改进={(baseline-best)/baseline*100:.1f}%`
```

**Concrete fix for high-impact-patterns.md -- add after pattern 21**:

```markdown
### 模式 22: Running Minimum Frontier (autoresearch)
- **源**: `autoresearch-src/analysis.ipynb` cells `79jh74veqg9` + `re1f8za8oj9`
- **模式**: 所有实验结果DataFrame上计算cummin()作为运行最佳前沿, 每次新实验后自动对比baseline与最佳
- **code-shiniyaya 差距**: 趋同检测(CR)是迭代内的, 不提供跨会话的"最佳成绩"追踪
- **修复**: SKILL.md趋同检测扩展为跨会话前沿追踪, results.tsv作为数据源, cummin()计算运行最佳
- **预期收益**: 跨会话的改进趋势一眼可见, 避免在已最优的维度上继续消耗Agent
```

---

## Pattern 23 (P1): Delta-Per-Improvement Ranking

**Source**: `analysis.ipynb` cell `q86hxu10djk` -- each kept experiment's delta = prev_kept_bpb - current_kept_bpb. Sorted descending. Total improvement sum at bottom. This ranks which changes contributed most.

**code-shiniyaya gap**: No per-fix improvement magnitude tracking. When multiple fixes are applied in a chain, there's no record of which fix contributed how much. All fixes are treated as equally valuable.

**Why this matters**: Ranking improvements by magnitude lets you identify which fix strategies work best, and which are "marginal" (cost many agents for tiny gain).

**Concrete fix for SKILL.md -- add to results.tsv analysis section**:

```markdown
**增量排名**: 每次results.tsv追加后计算:
- kept行: delta = 前一kept行的score - 当前kept行的score (正=改进, 负=退步但被误标kept→修正为reverted)
- 排名: kept行按delta降序排列→识别高影响修复策略
- 效率: delta/agents = 每Agent的改进效率。低效修复(delta>0但delta/agents<0.1)→标记为marginal, 优先使用高策略模式
```

**Concrete fix for high-impact-patterns.md -- add after pattern 22**:

```markdown
### 模式 23: Delta-Per-Improvement Ranking (autoresearch)
- **源**: `autoresearch-src/analysis.ipynb` cell `q86hxu10djk`
- **模式**: 每次kept改进记录与前一kept的delta, 按delta降序排名, 底部汇总total improvement
- **code-shiniyaya 差距**: 无每修复增量追踪, 所有修复等权对待
- **修复**: results.tsv分析层添加delta计算+排名+效率指标(delta/agents)
- **预期收益**: 识别高影响修复策略, 淘汰边际修复, Agent支出回报率优化
```

---

## Pattern 24 (P2): Autonomous Continuous Loop (No Human Checkpoints)

**Source**: `program.md:94-95` -- "LOOP FOREVER" with enumerated steps: tune→commit→run→grep→record→keep/reset→repeat. `program.md:112` -- "NEVER STOP: do NOT pause to ask the human if you should continue."

**code-shiniyaya gap**: code-shiniyaya's 7-step flow requires user confirmation at STEP 1→2 (confirm diagnosis), STEP 2→3 (confirm plan), STEP 5 (dual approval gate). There is no fully autonomous mode where CC iterates through diagnose→fix→verify→repeat without human checkpoints.

**Why this matters**: For overnight/autonomous operation (like autoresearch's "while user sleeps" use case), code-shiniyaya cannot run without a human pressing "approve" at each gate.

**Concrete fix for SKILL.md -- add to 不可跳过 table (line 387)**:

```markdown
## 自主循环模式 (实验性)

**触发**: "全自主" / "autonomous" / "overnight" / "自主运行"

进入自主循环模式后:
1. STEP 0-2: 照常执行(诊断+方案), 用户确认门控替换为: 方案写入FOR_CODEX文件后自动进入STEP 3(无需用户确认)
2. STEP 3-4: Codex静默阈值降为N=2(更快触发降级)。10分钟内无Codex回复→自动降级
3. STEP 5: 降级模式下用户单批准自动通过。CC自主决策(基于score改进预测)执行P1/P2修复。P0修复仍需Codex批准或降级模式下CC 6+ Agent验证
4. STEP 6-7: 照常执行
5. 自主门控: 3次连续reverted/crashed→自动暂停, 写SUSPEND_LOG.md, 等待用户。单次kept→继续。连续5次kept→加速(跳过STEP 3 Codex等待, 直接降级模式)
6. 循环: fix→verify→kept→下一项(无需用户确认)。全部P0/P1修复完成后自动停止, 写COMPLETION_LOG.md
7. 结果: 全自主运行期间所有修复追加到results.tsv, 用户回来后可审查完整历史

**自主循环停止条件**:
- P0+P1全部修复完成→自动停止
- 连续3次reverted/crashed→自动暂停
- 用户说"停止"/"停"→立即停(同规则13)
- 磁盘空间<100MB→自动暂停(防止results.tsv写满)
```

**Concrete fix for high-impact-patterns.md -- add after pattern 23**:

```markdown
### 模式 24: Autonomous Continuous Loop (autoresearch)
- **源**: `autoresearch-src/program.md:94-112` (LOOP FOREVER + NEVER STOP)
- **模式**: 全自主实验循环: tune→commit→run→record→advance/reset→repeat。无人类检查点。明确禁止Agent请求继续操作的许可。
- **code-shiniyaya 差距**: 7步流程在STEP 1→2, 2→3, 5各需要用户确认。无自主模式。
- **修复**: SKILL.md新增"自主循环模式"章节, 替代用户确认门控为自动推进, 定义自主停止条件
- **预期收益**: 支持过夜自主运行, ~100次修复/8小时睡眠
```

---

## Pattern 25 (P2): Per-Iteration Run Log Capture

**Source**: `program.md:99` -- `uv run train.py > run.log 2>&1` captures complete output to a file, not just the summary. Crash recovery reads `tail -n 50 run.log` for stack trace.

**code-shiniyaya gap**: code-shiniyaya's workflow agents produce journal.jsonl but CC's own fix-execution cycle (STEP 6) produces no dedicated per-iteration run log. If a fix crashes, there's no captured output to diagnose why.

**Why this matters**: When STEP 6 fix execution fails, there's no systematic output capture. Error diagnosis relies on conversation context (which may be truncated after /clear or long sessions).

**Concrete fix for SKILL.md -- add to STEP 6**:

```markdown
**运行日志**: 每次修复尝试→ `{project_root}/reports/runs/{sessionId[:8]}/{item_id}/run.log`
- 修复执行前: 写header(commit + item_id + timestamp)
- 执行中: 每个验证命令(pytest/ast.parse/git diff)的stdout+stderr追加到run.log
- 结束时: 追加结果行(status + score + elapsed)
- crash时: run.log包含完整错误堆栈, 用于诊断
- 保留: 不随会话结束删除, 跨会话可查
```

**Concrete fix for high-impact-patterns.md -- add after pattern 24**:

```markdown
### 模式 25: Per-Iteration Run Log Capture (autoresearch)
- **源**: `autoresearch-src/program.md:99-101` (run.log capture + tail for crash diagnosis)
- **模式**: 每次运行完整stdout+stderr捕获到独立run.log文件, crash后tail最后N行获取堆栈
- **code-shiniyaya 差距**: STEP 6修复执行无输出捕获机制, 崩溃后依赖对话上下文诊断
- **修复**: STEP 6每次修复尝试写 `reports/runs/{session}/{item}/run.log`
- **预期收益**: 可诊断的修复崩溃, 跨会话的调试信息持久化
```

---

## Pattern 26 (P2): Trivial-vs-Fundamental Crash Triage

**Source**: `program.md:108-109` -- "If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log crash."

**code-shiniyaya gap**: Rule 12 (3次同文件失败→停止) treats all failures equally. No distinction between correctable errors (typo/missing import) and uncorrectable errors (fundamental approach flaw). Rule 7 (Agent failure replacement, 2 retries) similarly doesn't distinguish failure types.

**Why this matters**: Trivial errors consume the 3-strike quota unnecessarily. If all 3 strikes are consumed by typos, the 4th (fundamental) approach flaw triggers STOP prematurely.

**Concrete fix for SKILL.md**: Already covered in Pattern 20's CRASHED子分类. Add to rule 12:

```markdown
**规则12扩展**: "3次同文件失败"仅计数Type B(根本性)失败。Type A(琐碎)失败自动修复+重试, 不消耗配额。Type C(哨兵)由规则7处理。
- Type A示例: 语法错误/缺失import/缩进错误/变量名拼写 → 自动修复, ≤2次, 不计入3次配额
- Type B示例: OOM/架构死锁/Agent全超时/3次Type A修复后仍失败 → 计入3次配额
- Type B配额耗尽→停止(同规则12现状)
```

---

## Summary: Integration Priority

| # | Pattern | Priority | Lines Changed | SKILL.md Section | high-impact-patterns.md |
|---|---------|----------|---------------|------------------|-------------------------|
| 19 | TSV Append-Only Results Log | P0 | ~55 | "累积结果日志" after 状态文件 | 模式 19 |
| 20 | Ternary Taxonomy + Sentinels | P0 | ~30 | 规则12扩展 + 分类法表 | 模式 20 |
| 21 | Git Commit as State Machine PK | P1 | ~10 | STEP 6 Git锚点 | 模式 21 |
| 22 | Running Minimum Frontier | P1 | ~10 | 趋同检测扩展 | 模式 22 |
| 23 | Delta-Per-Improvement | P1 | ~8 | results.tsv分析层 | 模式 23 |
| 24 | Autonomous Continuous Loop | P2 | ~25 | 自主循环模式(新章节) | 模式 24 |
| 25 | Per-Iteration Run Log | P2 | ~12 | STEP 6 运行日志 | 模式 25 |
| 26 | Trivial-vs-Fundamental Triage | P2 | ~8 | 规则12扩展(含于模式20) | --(含于模式20) |

**所有8个模式均来自autoresearch-src, 之前未被code-shiniyaya集成。**
**核心维度: 累积结果记录(TSV + 三元分类法 + 哨兵值 + Git锚点 + 前沿追踪)**
