# code-shiniyaya 高影响模式 (Top-10 from 4 new reference sources)

跨源交叉验证: 10个模式被≥2个源独立印证。

## Top-10 最高影响模式 (按P0优先级)

### 1. Agent编排 = Hub-and-Spoke (AutoAgent + autonomous-coding)
两Agent模型: 一个Init Agent(创建检查清单), 一个Loop Agent(反复执行修复+验证)。Init Agent只运行一次。Loop Agent每次迭代用fresh context。
- AutoAgent: `system_triage_agent.py:8-64` — transfer_to_* 函数
- autonomous-coding: `agent.py:97-207` — is_first_run门控 + 无限循环

### 2. Git作为状态机 (autoresearch + autonomous-coding)
提交=状态单元。改进→保留提交。回退→`git reset`。消除journal-parser对简单修复迭代的需求。
- autoresearch: `program.md:91-105` — 核心实验循环

**v2 具体机制 (2026-07-16 autoresearch deep scan — 8 个子模式)**:

(2a) **提交即迭代单元** (`program.md:94-104`):
```
LOOP: modify code → git commit → run → grep metric
  → metric improved → keep commit (advance branch)
  → metric worse/equal → git reset (discard)
```
每次修复 = 一个原子 git 提交。提交消息即为描述。分支历史即为实验日志。无需 journal.jsonl 状态文件。

(2b) **二分法保留/重置决策** (`program.md:103-104`): 单指标，二元决策，即时执行。无部分保留，无条件批准，无多维评分。

(2c) **按运行分支隔离** (`program.md:92`): `autoresearch/<tag>` 命名。每次运行一个分支。完全文件系统隔离——零碰撞风险。分支存在性检查替代了版本向量和校验和。

(2d) **结果扁平文件审计轨迹** (`program.md:67-88`): `results.tsv` — 制表符分隔，5 列（commit, val_bpb, memory_gb, status, description）。每次实验均记录，包括崩溃（哨兵值 0.000000）。文件为 git 未跟踪，保持仓库历史清晰。

(2e) **三种结果分类** (`program.md:77`): 仅 3 种状态：`keep`, `discard`, `crash`。无 partial/conditional/degraded/interrupted——简单性确保 agent 不会对下一步操作感到困惑。

(2f) **输出重定向 + grep 提取** (`program.md:99-100`): `uv run train.py > run.log 2>&1` → `grep "^val_bpb:" run.log`。仅提取所需指标进入上下文窗口，原始输出永不清洗上下文。

(2g) **运行中代码快速失败自中止** (`train.py:570-572`): 进程检测自身发散（NaN 损失，loss>100）并立即调用 `exit(1)`。Agent 检查退出码，而非解析完整输出。

(2h) **永不停止指令** (`program.md:112-113`): "不要暂停询问用户是否继续。" 设计用于无人值守隔夜运行。预定吞吐量：每小时约 12 次实验。

- autonomous-coding: `coding_prompt.md:128-140` — git提交消息格式

### 3. 不可变检查清单 (autonomous-coding + autodream)
创建后永不修改检查清单项目。仅变更verified标志。防止Agent销毁自己的任务定义。
- autonomous-coding: `coding_prompt.md:108-126` — "只允许改变一个字段"
- autodream: 文件校验和检查——hash匹配则跳过

### 4. 崩溃分类法 (autoresearch + autonomous-coding)
琐碎错误(拼写错误、缺失导入)→自动修复+重试, 不消耗重试配额。根本性错误(OOM、架构问题)→消耗重试配额, 3次后终止。
- autoresearch: `program.md:108-109` — "如果太蠢且容易修复, 修复后重跑。如果想法本身有问题, 跳过"
- autonomous-coding: `loop.py:84-113` — _is_recoverable分类器

### 5. 双重代表记忆 (autodream + AutoAgent)
Markdown文件=主存储+来源。向量DB=语义索引(衍生, 可重建)。校验和追踪避免重复处理。
- autodream: `auto_dream.py:498-568` — sync_autodream_vector_memory()
- AutoAgent: 注册表单例 — `_registry` 字典

### 6. 事件驱动DAG引擎 (AutoAgent独有但高度可移植)
`listen_group`包含`retrigger_type="all"`→声明式步骤编排。自动并行扇出。完成追踪内建。
- AutoAgent: `flow/core.py:93-151` — 事件驱动DAG, `already_sent_to_event_group`去重

### 7. 两阶段反思循环 (autodream独有)
STEP 7之后: Learn阶段(分析近期会话→合成新记忆)。Consolidation阶段(每N次dream合并+去重)。
- autodream: `auto_dream.py:97-317` — _run_auto_dream()双阶段

### 8. 3-Tier重试升级 (AutoAgent独有)
尝试1-2: 相同Agent但注入上次错误作为反馈。尝试3+: 升级到有全部工具权限的元验证Agent。全部失败: case_not_resolved, 附完整失败链。
- AutoAgent: `main.py:43-80` — MAX_RETRY=3循环, 元Agent升级

### 9. "NEVER STOP"指令 (autoresearch独有)
显式禁止Agent请求继续操作的权限。Agent在手动停止前无限期自主运行。
- autoresearch: `program.md:111-112` — "NEVER STOP: 开始后不要暂停询问是否继续"

### 10. 轨迹记录 (autonomous-coding独有)
每次Agent调用记录带时间戳的JSONL条目(每个turn一条JSON行)。提取图片到磁盘(JSONL中引用文件路径)。元文件记录model、task、系统提示词。
- autonomous-coding: `trajectory.py:1-61` — 轨迹类

## 集成优先级

| 模式 | code-shiniyaya 目标 | 预期收益 |
|------|------|------|
| Hub-and-Spoke编排 | 防卡顿系统: Init Agent→Checklist, Loop Agent在fresh context中反复执行扫描→修复→验证 | 消除单体式8-Agent挂起问题 |
| 崩溃分类法 | 规则12细化: Type A(琐碎)→自动修复, Type B(根本性)→消耗重试 | 减少P0修复中不必要的重试 |
| Git状态机 | 迭代修复循环: git commit→扫描。CRITICAL降低→保留。CRITICAL上升→reset。分支隔离: fixes/{sessionId}替代文件名会话ID。二分法保留/重置替代多状态(keep/discard/crash仅3种)。扁平文件修复日志(fix-log.tsv)替代journal-parser。快速失败自中止验证脚本。 | 替代journal-parser用于简单修复; 消除版本向量和校验和(由git对象处理); 零碰撞分支隔离; 完整审计轨迹; 更快的失败检测 |
| 事件驱动DAG | 防卡顿系统: 步骤声明依赖关系, 引擎自动并行化独立步骤 | 更快的扫描+修复周期 |
| 轨迹记录 | 每次迭代: runs/{ts}/transcript.jsonl + 元信息 | 跨迭代可调试性 |

---

---

## 新维度: Git 状态机 — 对 code-shiniyaya STEP 6 的具体修复 (autoresearch deep scan, 2026-07-16)

autoresearch 演示了 git 本身如何替代 JSON 状态文件作为状态机：每次状态转换均为 git 操作（commit、reset、branch）。code-shiniyaya v3.7.0 使用 JSON 状态文件（session-*.json、pending-*.json、dag-*.json）追踪完全相同的状态转换。git 原生方法消除了 journal-parser.py、lastFileHash 检查和版本向量冲突检测，因为 git 对象是内容寻址的、分支是隔离的、且保证原子性。

完整的发现文件见：`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\autoresearch-git-state-machine-findings.md`（26 个模式，精确 file:line 引用及具体修复代码）。

### P0 Git 模式（2 个，必须添加到 SKILL.md）

#### 模式 19: STEP 6.0 — 使用 Git 状态机的修复执行
- **来源**: `autoresearch-src/program.md:94-104`（提交即迭代单元）
- **模式**: 每次修复 = 一个原子 git 提交。`fixes/{sessionId}` 分支。修复生效 → 保留提交（分支前进）。修复失败 → `git reset --hard HEAD~1`，重试或标记为 BLOCKED。
- **code-shiniyaya 差距**: STEP 6 使用手动 `git diff --stat` + `grep -n` 验证，不将 git 提交作为迭代单元。pending-*.json 状态文件追踪修复进度，而非分支历史。
- **修复**: 在 STEP 6 头部之后、DAG 预操作之前添加 STEP 6.0 章节。包含：预检查分支创建、提交即修复循环、二分法保留/重置、扁平文件 TSV 审计日志、恢复协议。

#### 模式 20: 分支隔离替代文件名 Session ID
- **来源**: `autoresearch-src/program.md:9-10, 92`（分支存在性预检查 + 按运行分支）
- **模式**: 每次修复会话 = 一个独立的 git 分支，而非文件名会话 ID。Git 强制零碰撞。分支存在性检查替代了基于校验和的冲突检测。
- **code-shiniyaya 差距**: 会话隔离使用 `{sessionId[:8]}` 在文件名中 + 版本向量冲突检测。概率性碰撞分析（65K 会话时生日悖论达 50%）。对于同一仓库中的并行 CC 会话，分支隔离更简单、更安全。
- **修复**: 在会话隔离章节（第 164 行之后）添加"Git 分支隔离"小节。包含分支命名规范、预检查命令和恢复模型。

### P1 Git 模式（3 个）

#### 模式 21: 扁平文件修复日志（results.tsv 等价物）
- **来源**: `autoresearch-src/program.md:67-88`（5 列制表符分隔的结果）
- **模式**: 每次修复尝试均记录到 git 未跟踪的 TSV 文件：commit | bug_id | status(keep|discard|crash) | description。崩溃使用哨兵值（val_bpb=0.000000），而非缺失行。
- **修复**: 新增 `fix-log-{sessionId[:8]}.tsv`，原子更新。仅 3 种状态。Git 未跟踪以保持仓库历史清晰。

#### 模式 22: 三种结果分类法
- **来源**: `autoresearch-src/program.md:77, 87`
- **模式**: 仅 3 种结果：keep、discard、crash。无 partial/conditional/degraded/interrupted。简单性确保 agent 不会对下一步操作感到困惑。
- **修复**: 在 git 状态机模式下，将 itemStates 映射到 3 种结果。保留现有的丰富状态用于复杂多文件修复。

#### 模式 23: 输出重定向实现上下文效率
- **来源**: `autoresearch-src/program.md:99-100`
- **模式**: 将所有输出重定向到文件（`> run.log 2>&1`），然后仅 grep 提取所需指标。上下文窗口永不被原始日志淹没。
- **修复**: 在 STEP 1 诊断过程中，将 agent 输出路由到 `.claude/memory/code-shiniyaya/scan-output-{sessionId}.log`。仅提取发现计数、严重程度分布和 P0 列表用于上下文窗口。

### P2 Git 模式（3 个）

#### 模式 24: 运行中代码快速失败自中止
- **来源**: `autoresearch-src/train.py:570-572`（NaN/爆炸检测 + `exit(1)`）
- **模式**: 运行中进程检测自身发散并立即退出。Agent 检查退出码，而非解析输出中的错误。
- **修复**: 为验证脚本添加快速失败门控：ast.parse 失败 → `exit(1)`；diff 为空 → `exit(1)`；测试失败 → `exit(1)`。

#### 模式 25: 永不停止 — 抑制每次迭代提示
- **来源**: `autoresearch-src/program.md:112-113`
- **模式**: "不要暂停询问用户是否继续。" 设计用于无人值守隔夜运行，每次实验约 5 分钟。
- **修复**: 在 git 状态机模式下，抑制"继续？"提示。仅停止条件：(a) 所有项完成，(b) 同一 BUG 连续 3 次崩溃，(c) 用户中断。

#### 模式 26: 累积最小值前沿追踪
- **来源**: `autoresearch-src/analysis.ipynb`（单元格 79jh74veqg9，`running_min = kept_bpb.cummin()`）
- **模式**: 单调曲线显示迄今最佳结果，作为每步增量的补充。
- **修复**: 在 SKILL.md 收敛追踪中添加 `best_so_far` 字段。当 CRITICAL_n < 之前最佳值时更新。

---

## 新维度: 溯源归因 (AutoDream deep scan, 2026-07-16)

AutoDream 实现了完整的溯源追踪: 每条持久化记忆携带 grounded/inferred 标记、source_context_ids 链、source_first_prompts 锚点、source_memory_ids 交叉引用, 以及 Rules vs Facts 分类法 (.promptinclude.md)。code-shiniyaya v3.7.0 的 Agent 发现只有 severity 字段, 没有任何溯源基础设施。

### P0 溯源模式 (4个, 必须添加到 SKILL.md)

#### 模式 11: Grounded vs Inferred 溯源声明
- **源**: `autodream-src/helpers/auto_dream.py:425-427`, `prompts/autodream.sys.md:53-54`
- **模式**: 每条记忆必须声明 grounded(有直接证据) 或 inferred(推测/合成)
- **code-shiniyaya 差距**: Agent 发现(STEP 1/4)没有 grounding 字段, 无法区分直接观察 vs Agent 幻觉
- **修复**: 所有 finding 必须添加 `grounding: grounded|inferred|partial` 字段 + `evidence` 或 `inference_chain`

#### 模式 12: source_context_ids 会话溯源链
- **源**: `autodream-src/helpers/auto_dream.py:428-430`, `prompts/autodream.msg.md`
- **模式**: 每条记忆记录源自哪些会话(context_id), 形成可审计的溯源链
- **code-shiniyaya 差距**: 去重合并后的 finding 不记录贡献 Agent ID, 错误发现无法追溯到源 Agent
- **修复**: 合并 finding 添加 `merged_from[]` + `source_context_ids[]` + `consensus` 字段

#### 模式 13: source_first_prompts 用户意图锚定
- **源**: `autodream-src/helpers/auto_dream.py:431-439`, `prompts/autodream.sys.md:56-57`
- **模式**: 每条记忆记录触发它的用户原始提示, 锚定知识到用户意图
- **code-shiniyaya 差距**: Finding 没有链接到用户原始请求, 无法检测 scope creep
- **修复**: Agent 输出添加 `source_user_intent` + `relevance: DIRECT|RELATED|INCIDENTAL`

#### 模式 14: Taxonomy -- Rules (.promptinclude.md) vs Facts (.md)
- **源**: `autodream-src/prompts/autodream.sys.md:47-49`, `auto_dream.py:1306-1318`
- **模式**: 行为规则用 `.promptinclude.md` 扩展名(自动执行), 事实知识用 `.md`
- **code-shiniyaya 差距**: SKILL.md 混合规则+事实; memory/ 文件无扩展名区分
- **修复**: 拆分 SKILL.md 为规则/参考两部分; memory/ 采用 `.promptinclude.md` 用于行为规则

### P1 溯源模式 (4个)

#### 模式 15: Cross-Session Fingerprinting (跨会话内容指纹)
- **源**: `autodream-src/helpers/auto_dream.py:499-568` (vector_state.json checksum sync)
- **模式**: 每个文件记录 SHA-256 校验和, 匹配则跳过重复诊断
- **修复**: 新增 `fingerprints-{project}.json`, STEP 1 前检查指纹

#### 模式 16: Consolidation Phase (独立合并阶段)
- **源**: `autodream-src/helpers/auto_dream.py:264-315`, `prompts/autodream.consolidate.sys.md`
- **模式**: 每 N 次 dream 运行专门合并阶段: 检测语义重叠→合并文件→删除冗余
- **修复**: memory/ 每 10 次写操作触发合并, 使用专用 consolidate prompt

#### 模式 17: Orphan Candidate Detection (跨项目孤儿检测)
- **源**: `autodream-src/helpers/auto_dream.py:846-918`
- **模式**: 项目重命名后检测旧名称的记忆文件夹, token overlap 评分 ≥0.5 标记为候选孤儿
- **修复**: 添加跨项目记忆孤儿检测, `cross-project-references.json`

#### 模式 18: Standardized Memory Frontmatter
- **源**: `autodream-src/helpers/auto_dream.py:418-448`
- **模式**: 所有记忆文件携带统一 YAML frontmatter: title, description, grounding, source_context_ids, updated_at
- **修复**: 标准化 memory/ 所有文件的 frontmatter schema

### 完整发现文件
详见 `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\autodream-grounding-attribution-findings.md` (18 个模式, 含精确 file:line 引用和具体修复代码)
