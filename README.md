# code-shiniyaya v4.7.10 — CC↔Codex 双向验证元编排 Skill

## 是什么

code-shiniyaya 是 Claude Code 的元编排 Skill——不直接修改代码，而是编排 CC 与 OpenAI Codex 之间标准化的双向验证闭环。CC 负责深度诊断（读源码 + 6+ Agent 并行扫描），Codex 负责独立验证（交叉检查 CC 方案），双方都批准后才执行。

这不是"让 AI 写代码"——是"让两个 AI 系统互相验证对方的工作"。v4.7.8-v4.7.9 新增平台层防御体系（echo-guard 跨 turn 指纹 + stop-guard 干净轮拦截 + bearings 自动恢复注入）、干净轮收敛计数器、预发射防卡顿机制与外部加速 Skill 可选层（8 挂点）。

---

## 核心功能

### 9 步双向验证闭环 (STEP 0-8)

| 步骤 | 做什么 | Agent 数 | 门控 |
|------|--------|----------|------|
| **STEP 0** | 冷启动：三 Skill 前置 + 环境能力检测（git/Python/tiktoken） | — | 无 |
| **STEP 1** | 诊断扫描：6+ Agent 并行（5 类型），去重合并，P0/P1/P2 分类 + grep 所有调用者 | 6+ | 用户确认 |
| **STEP 2** | 方案生成：每 Bug file:line + old/new 代码 + 风险 + 验证命令，3 Agent 对比方案 | 3 | 用户确认 |
| **STEP 3** | Codex 可复制文本：7 步消毒流水线（Bidi→NFKC→零宽→Null→C0/C1→围栏转义→JSON），纯文本，>20000 字符分页 | — | 无 |
| **STEP 4** | Codex 反馈交叉验证：10+ Agent 跨 7 维度（准确性/代码复用/遗漏/安全/架构/回退/执行），Byzantine Codex 防御（5 大错误模式） | 10+ | Codex 验证 |
| **STEP 5** | 双批准门控：CC 批准 + Codex 批准 = 执行。降级模式：用户单批准（P0 仍需 CC 4 Agent） | — | 阻断 |
| **STEP 6** | 逐项执行：Git 状态机（独立项）或 DAG 依赖追踪（跨文件依赖），ast.parse 验证，墙钟时间盒（单 Bug 300s / 工作流 600s） | 1-4 | 逐项 |
| **STEP 7** | 双向验证：CC→Codex→CC，1 轮完成，仅争议时第 2 轮，再有争议→用户裁决 | 6+ | 用户 |
| **STEP 8** | 工作流后元反思：双门控触发（≥8h 或 ≥3 工作流），Learn + Consolidate 两阶段 | — | 条件触发 |

**快速路径**：已有完整方案→跳过 STEP 1-2，直接进入 STEP 5 批准。
**降级模式**：Codex 连续 4 条消息无回复→询问；5 条→自动降级→用户单批准可执行（P0 仍需 CC 4 Agent 验证）。

### v4.7.6 新增功能

| 功能 | 来源 | 说明 |
|------|------|------|
| **墙钟时间盒** | autoresearch | 迭代工作流固定墙钟上限，超时自动终止 + 写 TIMEOUT_LOG.md |
| **GET BEARINGS 检查清单** | autonomous-coding | "继"恢复后 7 步标准化环境确认 |
| **caveman auto-clarity** | ponytail | 安全警告/不可逆操作确认/多步骤序列→自动写完整语言 |
| **selftest 双层门控** | ponytail | Layer 1 离线（免 API）+ Layer 2 LLM 裁判（见 SKILL.md §自应用差距, L1565） |
| **基线优先** | autoresearch | STEP 6 修复前记录指标基线 |
| **输出重定向+grep** | autoresearch | Agent 输出写文件→grep 提取→仅指标入上下文 |

---

## Echo 死循环三层防御

| 层 | 机制 | 状态 |
|----|------|------|
| **L1** | 规则 26（事后阻断） | 同 turn 内检测，吸引子状态时失效 |
| **L2** | PreToolUse echo-guard.js v4.3 (平台止损) | deny()阻断echo命令+hookSpecificOutput格式; grep/rg/cat/head/tail/wc/uniq/stat 无条件豁免; find/sort/diff 先豁免后检查破坏性 flag — token-array Set 数据结构 destruct-vet + 8 次/turn 上限 + 跨 turn 指纹升级阶梯(v4.2: 文件参数归一化; v4.3: deny()统一阻断路径) + command-context-aware。CC 重启已验证 |
| **L3** | 一字恢复（事后恢复） | 55% 饱和→保存 snapshot→用户"继"→完整恢复 |

## 一字恢复

用户输入 **"继"** 触发：读 snapshot → 7 步环境确认 → 读 CHANGELOG → 4 Agent 扫描 → 续取任务。

---

## 30 条硬规则 + 20 项自检

**门控** (4)：双批准 / CC 不独立修改源码 / 分析自由修改阻断 / 逐项反馈 stop 优先
**Agent** (4)：动态 batch_size / 语法门控 / 3 层重试升级 / 无共享文件
**Plan-Code Gap** (3)：git diff+grep 双验证 / 方案锁定 / Write/Edit 前必须 Read
**停止线** (7)：崩溃分类 / stop 立即停 / 迭代优先 / 双轨修复 / 方向完整性 / 用户中断 / 工作流不阻断
**迭代** (8)：P0 规格化 / 趋势确认 / 自动应用 / 防卡顿 / 收敛阈值 / Fast-fail + 预热
**阻断** (规则 26，最高优先级)：同 file+offset 阻断 / 确认词无 Write 阻断 / done 循环阻断
**交付** (规则 27-28)：报告路径 / Codex 消息格式

**20 项自检**（#1/#3/#4/#11 标记 NON-VIABLE——CC 架构限制，依赖用户"继"触发恢复）

---

## 10-Skill 协同栈

| # | Skill | 级别 | 职责 |
|---|-------|------|------|
| 1 | code-shiniyaya | 编排 | 9 步闭环 + 30 规则 + 20 自检 |
| 2 | ponytail | ultra | YAGNI 七步阶梯 |
| 3 | caveman | full | 输出压缩 + auto-clarity |
| 4 | ponytail-review | 审查 | delete/stdlib/native/yagni/shrink |
| 5 | ponytail-audit | 审计 | 全仓过度工程审计 |
| 6 | ponytail-debt | 债务 | 标注收割→账本 |
| 7 | ponytail-gain | 计量 | LOC/cost/speed 基准 |
| 8 | ponytail-help | 参考 | 全家桶快查 |
| 9 | using-superpowers | 守卫 | 强制检查 skill 适用性 |
| 10 | openspec-explore | 探索 | 思考不实现 |

---

## 5 个开源参考源 (~172 模式)

| 项目 | 星 | 核心贡献 |
|------|-----|----------|
| AutoAgent (HKUDS) | 9,468 | DAG 引擎、Hub-and-Spoke、3-Tier 重试 |
| autodream | 19 | Learn+Consolidate、双重记忆、孤儿检测 |
| autoresearch (Karpathy) | 91,221 | Git 状态机、崩溃分类、固定预算 |
| autonomous-coding (Anthropic) | 17,248 | Init+Loop、不可变清单、三层安全 |
| ponytail | — | 七步阶梯、debt 标注、9 Hook 模式 |

---

## 触发词 (64+ 短语，9 类 A-I)

恢复关键词：**"继"** — 一字恢复。裸词"继续"不触发。

---

## 版本

**v4.7.10** — v4.7.9: 一字恢复+三hook平台防御(echo-guard v4.3+stop-guard v3.5+bearings v3.0)+预发射防卡顿+干净轮收敛+autoCompactThreshold=55。v4.7.10: 转移包全量落地——30条硬规则(含规则29契约前置TDD/规则30全站一致性审计)+五层验证管线L1-L5+headroom集成+aislop 138基线+agent-lint 51/100基线+token审计。hooks.test 44/44。

## 许可证

MIT
