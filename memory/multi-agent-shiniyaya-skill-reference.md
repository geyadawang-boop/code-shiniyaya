---
name: multi-agent-shiniyaya-reference
description: "multi-agent-shiniyaya Skill v1.0.0 参考文档 — 28 Skill审计 + 80 Agent 方法论提炼 (2026-07-09)"
metadata:
  type: project
  originSessionId: agent-skill-skill-bug-skill-skill-skill-async-wave
  status: verified-final
  integrity: "MEMORY_INTEGRITY_PASS: true"
---

<!-- Evolution: 2026-07-09 | source: multi-agent-shiniyaya | agent: Agent-final-fix -->

# multi-agent-shiniyaya Skill 参考

> 时间：2026-07-09
> Skill 名称：multi-agent-shiniyaya
> 版本：v1.0.2
> 来源：BiliSum v6.0 (30 Agent) + v7.0 (50 Agent) 实战
>
> 最后更新：2026-07-09 (7 Agent 自指审计 → v1.0.2 修复)

## 背景

用户在 BiliSum v6.0 和 v7.0 中实际执行了 30+50=80 个 Agent 的并行深度开发，产出了 500+ Bug、150+ 代码文件、100+ 交叉利用链。

## 核心方法论提炼

### 8层架构分类法
- Agent 分组按架构层（前端/后端/AI/集成/安全/数据库/测试/架构）
- 每层 5-8 个 Agent
- 总计 10-50 个 Agent（取决于项目规模）

### 5-Section Agent Prompt Template
1. Skill 方法论阅读 → 审查目标代码 → 发现 ≥5 Bug → 产出可执行代码 → 交叉利用链

### Concurrency Management
- batch_size = max(1, min(16, cpu_cores - 2))
- 每批完成后语法验证
- 文件冲突预防：FLEET.md 强制唯一文件分配

### Deliverables
- GROUPS.md, FLEET.md, MULTI_AGENT_BUGS.md, MULTI_AGENT_CHAINS.md, MEMORY.md, REPORT.docx

### Plan-Code Gap (v7.1 核心教训)
- 修复代码必须写入实际源文件（不是 Agent 输出）
- 每修复状态：Applied / Partially Applied / Requires Manual

## 28 Skill 审计（注：非32）

已审计 28 个 debug/bug/code/security/automation skill，四级判定：
- 核心使用 15 个 — 方法论直接编入 SKILL.md
- 重要使用 7 个 — 编入 references/
- 参考使用 2 个 — 设计灵感
- 暂不使用 4 个 — 单工具/平台特定

## 触发词库

A-G 类触发词（来自真实对话），含中文/防误触发规则。

## 实施状态

- [x] SKILL.md (v1.0.2 完成，Phase 0-8 + 16 Hard Rules + 9 Anti-patterns 三段式表格 + 防误触发规则 + 英文触发词库 + Phase 间转换条件表 + 错误处理表 26 行)
- [x] CHANGELOG.md
- [x] README.md (使用说明)
- [x] 桌面文件夹/Claude Code 两位置同步 (SHA256 验证通过)
- [x] 9 个 references/ 文件 (3 完整 + 6 骨架实现)
- [x] 3 个 scripts/ 骨架文件
- [x] 记忆文件 (MULTI_AGENT_GROUPS.md + MEMORY.md 索引更新)
- [x] 写入 ~/.agents/skills/
- [x] 更新 ~/.claude/projects/c--/memory/MEMORY.md

**Why:** 将 80 个 Agent 的实战经验封装为可复用的方法论 Skill。当用户提出深度开发/全面扫描/多 Agent 并行开发等需求时，自动加载本 Skill 提供标准化的编排工作流。

**How to apply:** Skill 文件位于 `~/.agents/skills/multi-agent-shiniyaya/SKILL.md`。更新同步时参见 `skill-upgrade-protocol.md`。
