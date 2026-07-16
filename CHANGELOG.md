# code-shiniyaya CHANGELOG

## v4.7.3 — 2026-07-17T01:36:59+08:00
- 上下文感知防饱和机制: 死循环三层防御(L1=事前预防, L2=规则26, L3=PreToolUse hook)
- 优化前5 Agent完整性验证门控: 文件完整性/交叉引用/版本一致性/数据完整性/Git完整性
- 上下文饱和度检测: 4信号(工具调用密度/重复模式/输出衰减/确认词密度)
- 自动压缩阈值建议: 60%/80%/95%分级动作
- 压缩后恢复流程: memory/snapshot-{ts}.md → 4 Agent精简扫描 → CHANGELOG续取

## v4.7.2 — 2026-07-17
- 根本限制文档化: 文本规则无法打破LLM验证强迫
- 外部看门狗: PreToolUse Bash hook安装在settings.json (>8 Bash/turn→阻断)
- 死循环根因分析: 模型进入吸引子状态时认知能力被循环劫持

## v4.7.1 — 2026-07-17
- codex-plugin-cc集成: /codex:review, /codex:adversarial-review, /codex:rescue, /codex:transfer
- 反模式#24: Codex手动粘贴循环
- Codex通信模型升级: plugin-primary + manual-fallback

## v4.7.0 — 2026-07-17
- 优化任务队列: Task 1-6, 3 completed, 3 skipped (valid reasons)
- 1549行(-88, -5.4%), agent确认无低风险优化项
- HANDOFF折叠 + 架构依赖表 + 迭代交叉引用修复

## v4.6.9 — 2026-07-16
- 零bug收敛确认: 20 Agent × 5源扫描, ZERO BUGS
- 10-skill协同开发栈强制激活
- 规则26强化: Read/Grep/Bash/确认词/Write↔Read循环阻断
- 自检#18: 死循环根因阻断(HARD)
- Hook基础设施: 9个ponytail生命周期模式
- 13个反馈机制落地(12个从ponytail移植)
- ponytail:debt自我应用: 30个标记, 零[未实现]残留
- P0验证规格化: 模式区分(非降级2 Agent/降级4 Agent)
