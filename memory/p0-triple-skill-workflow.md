---
name: p0-triple-skill-workflow
description: 最高优先级 — 后续所有开发任务必须同步使用OpenSpec + multi-agent-shiniyaya + using-superpowers + ponytail四个Skill，形成计划-执行-纪律-精简四位一体工作流
metadata:
  type: feedback
  priority: highest
  created: 2026-07-13
  updated: 2026-07-16
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 规则：四Skill同步工作流

后续所有开发、优化、审计、修复任务，必须同步使用以下四个Skill：

## 四个Skill及其角色

### 1. OpenSpec — 计划层 (What & Why)
- 6个Skill: `openspec-propose`, `openspec-explore`, `openspec-apply-change`, `openspec-sync-specs`, `openspec-archive-change`, `openspec-update-change`
- 6个命令: `/opsx:propose`, `/opsx:explore`, `/opsx:apply`, `/opsx:sync`, `/opsx:archive`, `/opsx:update`
- 职责: 规格驱动开发 — 把需求转化为结构化提案(specs + changes + tasks)，追踪变更生命周期
- 触发场景: 新功能规划、需求梳理、方案设计、变更追踪、规格同步

### 2. multi-agent-shiniyaya — 执行层 (How)
- Skill: `multi-agent-shiniyaya`
- 职责: 多Agent并行深度开发编排 — 8层架构分类 + Agent-Skill自动分配 + 分批并发 + 去重聚合 + DOCX报告 + 3轮记忆验证
- 触发场景: 深度开发、代码审计、Bug扫描、Skill创建/升级、计划管理、产物应用、安全兼容检查
- 核心约束: batch_size上限、语法门控、Plan-Code Gap防护、用户确认门控、Stop-the-Line规则

### 3. using-superpowers — 纪律层 (Discipline)
- Skill: `using-superpowers`
- 职责: 强制Skill优先 — 任何响应/行动前必须先检查并调用相关Skill，禁止跳过Skill直接行动
- 触发场景: 所有对话开始、所有任务执行前
- 核心约束: 1%可能适用就必须调用，不可协商，不可自我合理化跳过

### 4. ponytail — 精简层 (How Little) ⭐NEW 2026-07-16
- 来源: https://github.com/DietrichGebert/ponytail
- **已安装全部6个附属Skill** (全部验证SKILL.md完整):
  1. `ponytail` (120行) — 主模式: YAGNI阶梯7级懒惰资深开发, lite/full/ultra三档
  2. `ponytail-review` (57行) — diff过度工程审查: 重造stdlib/多余依赖/投机抽象, 一行一发现
  3. `ponytail-audit` (41行) — 全库膨胀扫描: 排名列出可删/可简化/可换stdlib
  4. `ponytail-debt` (44行) — 债务台账: 收集所有`ponytail:`注释成清单, 防止"以后"变"永不"
  5. `ponytail-gain` (50行) — 效果计分板: 展示节省的代码量/成本/速度
  6. `ponytail-help` (71行) — 快速参考卡: 所有模式/技能/命令
- 职责: 强制最简可行方案 — YAGNI阶梯: 需要存在吗?→代码库已有?→stdlib有?→原生平台特性?→已装依赖?→能一行吗?→才写最少代码
- 触发场景: 所有写代码/重构/修复/审查任务; Bug修复=根因修复(在共享函数加一个guard比每个调用者各加一个更小)
- 核心约束: 禁止无要求的抽象(单实现接口/单产品工厂)、禁止"以后用"脚手架、删除优先于新增、最少文件、最短可行diff
- 刻意简化必须留`ponytail:`注释标注上限和升级路径 → `ponytail-debt`定期收账
- 实测: ~54%代码减少(最高94%), ~20%省钱, ~27%提速, 100%保留安全守卫

## 协同工作流

```
用户需求
    │
    ▼
┌──────────────────────────────────────────────────┐
│ Step 0: using-superpowers                        │
│ 先检查三个Skill哪个适用 → 全部调用               │
└──────────────────────────────────────────────────┘
    │
    ├── 新功能/规划 ──→ OpenSpec explore/propose
    │                      │
    │                      ▼
    │                   OpenSpec 生成 specs + tasks
    │                      │
    ├── 执行开发 ────────→ multi-agent-shiniyaya
    │                      │
    │                      ▼
    │                   Fleet 分批执行 tasks
    │                      │
    └── 归档/同步 ──────→ OpenSpec sync/archive
                           │
                           ▼
                       multi-agent-shiniyaya
                       记忆验证 + DOCX报告
```

## 具体规则

1. **收到任何开发相关任务** → 先用 `using-superpowers` 检查 → 强制调用 `openspec-propose` 或 `openspec-explore` 生成结构化方案
2. **方案确认后** → `multi-agent-shiniyaya` 接手执行 — 按FLEET分批、语法门控、Plan-Code Gap防护
3. **执行过程中** → OpenSpec的tasks追踪进度，multi-agent-shiniyaya的MEMORY.md记录状态
4. **执行完成后** → `openspec-archive-change` 归档 + `multi-agent-shiniyaya` 3轮记忆验证 + DOCX报告
5. **涉及Codex协作时** → OpenSpec方案同时发给Codex确认（满足[[p0-dual-approval-before-code-edit]]），Codex也使用OpenSpec格式反馈

## 不可跳过的情况

- 任何需要写代码的任务 → 三个Skill必须全部参与
- 任何Bug修复 → `using-superpowers` + `openspec-explore`(根因分析) + `multi-agent-shiniyaya`(执行+验证)
- 任何新功能 → `using-superpowers` + `openspec-propose`(规格) + `multi-agent-shiniyaya`(分批执行)
- 记忆/规则文件写入 → 可用 `multi-agent-shiniyaya` 3轮验证确保完整性
- 仅简单问答(不涉及代码修改) → 可跳过

## 与现有P0规则的关系

- 本规则是**元规则** — 规定用哪三个Skill来执行所有其他P0规则
- [[p0-codex-bidirectional-verification]] → OpenSpec方案作为Codex双向验证的输入格式
- [[p0-codex-evaluation-must-verify]] → multi-agent-shiniyaya提供10+Agent验证能力
- [[p0-deep-analysis-before-execute]] → using-superpowers确保分析前先调用正确Skill
- [[p0-dual-approval-before-code-edit]] → OpenSpec方案发给用户+Codex双方审批
- [[codex-fix-verification-rule]] → multi-agent-shiniyaya分批验证Codex修复

## 关联记忆

- [[p0-dual-approval-before-code-edit]]
- [[p0-codex-bidirectional-verification]]
- [[p0-codex-evaluation-must-verify]]
- [[p0-deep-analysis-before-execute]]
- [[codex-fix-verification-rule]]
- [[multi-agent-shiniyaya-skill-reference]]
- [[bilisum-v8-session-state]]
