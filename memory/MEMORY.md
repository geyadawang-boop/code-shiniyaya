# code-shiniyaya Memory Index

本目录存储 code-shiniyaya Skill 的持久化记忆，独立于 bilisum 的记忆系统。

**重要规则**: 此Skill对应的所有记忆和修改只能写入 `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\`，不得写入 bilisum 的记忆目录。

## 规则文件 (.promptinclude.md -- 自动执行)

- [记忆隔离规则](memory-isolation-rule.md) -- 重要: 所有记忆只写入 code-shiniyaya/memory/, 不得写入 bilisum 记忆目录

## 记忆文件

### 迭代与优化 (核心)

- [优化计划](optimization-plan.md) — 7大优化方向(持续性/保真性/有意义性/稳定性/4源深度利用/自我迭代/报告规范) — **COMPLETE**
- [迭代任务定义](iteration-task.md) — 完整迭代循环流程 + 4源已读/未读文件清单 + 优化7大方向 — **COMPLETE**
- [4源全覆盖最终状态](4-source-complete.md) — ~95 files read, ~100 patterns extracted, 4 sources TRULY EXHAUSTED — **COMPLETE**
- [全部新功能汇总](new-features-final.md) — v4.3.0至v4.5.2全部新功能发现 + 文件清单 — **COMPLETE**
- [元迭代质量](meta-iteration-quality.md) — Iter#001评分: 5.1/10, 4大能力缺口, 下轮改进措施
- [目标达成](goal-reached.md) — 2026-07-17: 12轮迭代完成, SKILL.md v3.9.28
- [目标确认 v4.0.7](goal-confirmed-v4.0.7.md) — 2026-07-17: iter#20 zero-confirmed(0 bug+0发现), 20轮迭代完成, SKILL.md v4.1.3
- [最终收敛确认 v4.5.2](goal-confirmed-v4.5.2.md) — 2026-07-16: 34轮迭代完成, ~95 files read, ~100 patterns, 4 sources TRULY EXHAUSTED, SKILL.md v4.5.2-final 1040 lines

### 配置

- [集中配置](config.json) — 80+ tunable constants in 9 sections (agent, silence, truncation, budget, reflection, agent_selection, convergence, git_branch, output, checkpointing)
- [配置参考](config-REFERENCE.md) — 快速参考 + 常见调优表 + 新增常量指南

### 参考源索引

- [参考源索引 v2](reference-sources-v2.md) — 4个新增开源参考源，65个模式提取自 AutoAgent, autodream, autoresearch, autonomous-coding (2026-07-16)
- [参考源清单](reference-sources.md) — 全部41个参考源清单 (桌面22 + GitHub 17 + ClawHub 2)
- [高影响模式 Top-10](high-impact-patterns.md) — 跨源交叉验证的最高影响模式 + 集成优先级

### AutoAgent 分析

- [AutoAgent 差距分析](autoagent-gap-analysis.md)
- [AutoAgent 安全模式](autoagent-security-patterns.md)
- [AutoAgent 进度模式](autoagent-progress-patterns.md)
- [AutoAgent 错误恢复模式](autoagent-error-recovery-patterns.md)
- [事件驱动编排发现](staged-event-driven-patterns.md) — case_resolved 协议, transfer-back 交接, 流式分发, 声明式步骤依赖

### autodream 分析

- [AutoDream 归因溯源发现](autodream-grounding-attribution-findings.md) — 18 个模式来自 AutoDream: grounded vs inferred 溯源, source_context_ids 追踪, Rules vs Facts 分类法
- [autodream 差距分析](autodream-gap-analysis.md)
- [autodream 模式转移](autodream-pattern-transfer.md) — autodream记忆模式
- [autodream 上下文模式](autodream-context-patterns.md) — autodream上下文上限
- [autodream 配置驱动模式](autodream-config-driven-patterns.md)

### autoresearch 分析

- [autoresearch 差距分析](autoresearch-gap-analysis.md)
- [autoresearch 崩溃分类哨兵](autoresearch-crash-taxonomy-sentinels.md)
- [autoresearch 全自主缺口](autoresearch-full-autonomy-gaps.md)
- [autoresearch Git状态机发现](autoresearch-git-state-machine-findings.md)
- [autoresearch 结果追踪缺口](autoresearch-results-tracking-gap-analysis.md)
- [autoresearch 简单性扫描](autoresearch-simplicity-scan.md)

### autonomous-coding 分析

- [autonomous-coding 差距分析](autonomous-coding-gap-analysis.md)
- [autonomous-coding 深度扫描发现](autonomous-coding-deep-scan-findings.md)
- [autonomous-coding 错误处理发现](autonomous-coding-error-handling-findings.md)
- [autonomous-coding 安全发现](autonomous-coding-security-findings.md)
- [autonomous-coding Step4-7模式](autonomous-coding-step4-7-patterns.md)
- [autonomous-coding 工具模式发现](autonomous-coding-tool-patterns-findings.md)

- [快照 2026-07-17](snapshot-20260717T013659.md) — v4.7.3上下文感知防饱和机制 + 5 Agent完整性门控
- [会话最终状态](session-final-state.md) — v4.7.2压缩前最终状态
- [优化全记录](code-shiniyaya-skill-optimization.md) — v4.1.3→v4.7.3完整迭代史

### 会话与维护

- [清理验证记录](cleanup-verification.md) — 2026-07-16 清理: bilisum记忆目录中已无孤立文件, 隔离验证通过
- [清理确认记录](cleanup-confirmed.md)
- [会话状态 2026-07-16](session-state-2026-07-16-compression.md)
- [会话状态 2026-07-17](session-state-2026-07-17.md)
- [迭代#1合并报告](iteration-1-merge-report.md)
- [合并报告](MERGE_REPORT.md)

---

## 最终状态摘要

| 指标 | 值 |
|------|-----|
| SKILL.md版本 | v4.5.2-final |
| SKILL.md行数 | 1040 |
| 总迭代次数 | 34 |
| 4源文件读取 | ~95 |
| 模式提取 | ~100 |
| 硬规则 | 25+ |
| 反模式 | 23+ |
| 自检项 | 16+ |
| 集中配置常量 | 80+ (config.json) |
| 记忆文件数 | 40+ |
| 4源未读文件 | 0 (ALL EXHAUSTED) |
