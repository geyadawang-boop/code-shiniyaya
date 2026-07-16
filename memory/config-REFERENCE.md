# Configuration Reference for code-shiniyaya v4.4.0+

All tunable constants are centralized here. To adjust a threshold, modify this file instead of searching through SKILL.md text.

## Quick Reference -- Most Commonly Tuned

| 调整项目 | config路径 | 默认值 | 说明 |
|----------|-----------|--------|------|
| Agent批大小上限 | agent.batch_size_max | 24 | 提高到>20即可满足迭代扫描|
| 收敛发现量阈值 | convergence.findings_near_convergence | 5 | 达到此发现量时触发收敛检查|
| 静默询问 | silence.n_ask | 4 | 用户消息条数后询问"继续等?" |
| 自动降级 | silence.n_auto_degrade | 5 | 用户消息条数后无条件降级 |
| 发现内容截断长度 | truncation.max_finding_chars | 600 | 每条发现最大字符数 |
| Codex反馈截断 | truncation.max_codex_feedback_chars | 8000 | 用户粘贴的Codex反馈最大长度 |
| 预算重置周期 | budget.reset_hours | 24 | 小时间隔，预算计数器归零 |
| BREAK_GLASS超标 | budget.break_glass_overage_pct | 10 | 预算耗尽后允许的额外百分比 |
| 反思间隔 | reflection.reflection_min_hours | 8 | 两次反思之间的最小小时数 |
| 整合频率 | reflection.consolidate_every_n_workflows | 3 | Learn-only反思后的整合周期 |
| 工作流超时 | checkpointing.timeout_seconds | 600 | Agent无响应触发timeout的秒数 |
| P0验证Agent数 | agent_selection.p0_verify_agents | 4 | P0双验证使用4 Agent |
| P0验证类型 | agent_selection.p0_verify_types | ["investigator","general-purpose","Plan","debugging"] | 降级模式中P0验证使用的Agent类型 |
| 迭代扫描Agent数 | agent.iteration_scan_agents | 20 | 固定值，非configurable |

## How to Add New Constants

1. Add entry to config.json under appropriate section
2. Update this REFERENCE.md with the new entry
3. Update SKILL.md if the constant is referenced in text (replace hardcoded value with "见 memory/config.json {key}")
