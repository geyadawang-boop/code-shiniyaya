# code-shiniyaya CHANGELOG

## v4.7.6 — 2026-07-17 (Reasonix 迭代)
- 集成4个高价值模式(ponytail筛选自25候选):
  - 墙钟时间盒(autoresearch): 迭代工作流固定墙钟上限, 防无限等待Agent
  - GET BEARINGS启动检查清单(autonomous-coding): 7步标准化环境确认
  - caveman auto-clarity安全解压(ponytail): 安全警告/不可逆操作→自动写完整语言
  - selftest双层门控(ponytail): 规则26/自检#18须通过门控才能标记VERIFIED
- Round 2集成2个辅助模式:
  - 基线优先(autoresearch): STEP 6修复前记录指标基线
  - Agent输出重定向+grep(autoresearch): 全量写文件→grep提取→仅指标入上下文
- 迭代收敛: 2轮扫描→25候选→ponytail筛至6→全5源确认收敛
- 平台: Reasonix (parallel_tasks + review, 无echo循环卡住
- Iter 1-4 自优化 (14处修复, SKILL.md: 1736→1606行(-7.5%), -7.5%):
  - Iter 1 (7处): 8步→9步修正, 自检#2/#3/#4 ponytail标注, selftest矛盾消除, NON-VIABLE降级, Codex消毒补全
  - Iter 2 (3处): 触发词路由/不可变契约/安全6项去重引用
  - Iter 3 (3处): no-trigger格式标准化, JSON消毒冗余声明, 规则15优先级澄清
  - Iter 4 (1处): v4.6.12章节去重(-132行) + 消毒编号修正(5→6→7)
- 最终审计修复 (6处): 自检#5b→#5, 规则15编号, StreamFirst引用, v4.6.10注释, H/I路由, CHANGELOG补全)

## v4.7.5 — 2026-07-17
- 一字恢复: 诚实面对CC架构极限 — AI不能自主跨turn执行，full-auto是伪功能
- 55%阈值→保存snapshot+git提交→用户"继"→4 Agent精简扫描→从CHANGELOG续取
- 入口路由表更新: 新增继/继续执行/继续迭代/继续优化触发词，裸词"继续"仍不触发恢复
- 章节交叉引用统一为§表示法 — 行号引用全部替换(防止编辑偏移)
- 修复: 入口路由表与v4.7.5快照恢复触发词的矛盾
- 修复: .gitignore *-src/ 实际落地(之前提交声称已添加但未执行)

## v4.7.4 — 2026-07-17
- 55%阈值自主压缩: 检测到饱和→保存snapshot+git提交→终止turn→系统自动压缩→下轮恢复
- 阈值降低: 55%/70%/90%三级，versionVector清零重启
- AI不能调用 /compact 终端命令 → 终止turn=等价替代 — turn边界是系统压缩的自然触发点
- 压缩后恢复时versionVector清零，重新计数

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
