# code-shiniyaya CHANGELOG

## v4.7.7 Round 3 — 2026-07-17 (收敛验证: 0 P0, 4 P1全修)
- P1-1: STEP 6.0分支创建修正——`git branch`+`git checkout -b`两步必然报错(分支已存在), 合并为单步checkout -b原子操作
- P1-2: >50KB回滚范围重划——git不可用+>50KB=无法回滚→执行前需用户显式确认(原文强制走6.0与git不可用矛盾)
- P1-3: originalSnapshot字段正式声明——加入pending schema字段表+不可变契约白名单(set-once), 消除契约违规
- P1-4: 预算损坏保守恢复对齐档位——"75%(仅P0)"自相矛盾→改">90%档(仅P0)"
- P2: SKILL.md/CHANGELOG.md UTF-8 BOM剥离(自身Agent-1门控要求"无BOM") | "10/20项NON-VIABLE"过时统计→7不可行/2部分/1可行 | 触发头57+→60+对齐metadata
- Round 3裁定: 0 P0残留。遗留P2(行159-166两处准确引用/snapshot草稿哨兵语义/6.0 crash语义)记入下轮维护

## v4.7.7 Round 2 — 2026-07-17 (对抗验证残留修复)
- P0: STEP 6.1回滚机制修正——lastFileHash(SHA-256)不能重建内容, 改git checkout HEAD --/originalSnapshot字段, hash仅验证
- 残留清零: "7步闭环"→9步(反模式24/workflow_context) | 规则22"4源"→5源+台账移至memory/applied-patterns.md | 反模式17更名5源 | 自检头版本v4.2.6-v4.7.7
- 插件消毒范围修正: JSON-RPC仅豁免第6步围栏转义, 字符消毒1-5步仍适用(Bidi/零宽可藏于内容)
- 反模式14对齐自检#1例外(a)-(d); 进度行格式统一(X/Y可含单位词)
- §根本性限制补echo-guard.js已实现声明; 自检#18改"跨turn部分不可行"
- 新增: 自检#20(7方向覆盖+反模式6执行器) | STEP 5用户拒绝/STEP 1列表否决/预算损坏75%保守恢复/STEP 8反思日志失败+槽满 错误行
- 预算增plugin_calls(cap 20, config.json新plugin段); checkpointing增laggard_timeout_seconds 300
- snapshot会话隔离已知限制标注; 5源全量确认计数对齐(autodream 9/autoresearch 5)
- STEP 0探测修正: importlib.util显式导入(部分CPython构建AttributeError)
- 残留行号引用全部→§锚点(行312/551/1437/1505); 主任务栏列表格式修复+项5改可观察产物; Stream-First去重(-5行)

## v4.7.7 — 2026-07-17 (5 Agent交叉扫描迭代 Round 1)
- P0×6全修: push矛盾统一为"commit不push" | STEP 7回滚路径(git revert/lastFileHash) | batch上限config 24→16 | 扫描规格统一5源×4Agent | 规则15恢复完整定义+停止例外(a)-(d) | 可运行边界STEP 0-8统一
- echo-guard.js v2.0: 修复致命bug——v1.0从argv读命令但CC hook走stdin JSON, 30个正则全为死代码。v2.0改stdin解析+BOM剥离+1s超时守卫, 实测阻断echo done/纯数字/wc循环
- settings.json PreToolUse hook重新注册(被zh-cn插件重写丢失), 保留插件SessionStart/Notification
- §根本限制/§外部看门狗重写: 反映echo-guard.js v2.0真实机制, 可靠性排序L2平台>L3恢复>L1文本
- snapshot原子化: tmp+rename+哨兵行`SNAPSHOT-COMPLETE`, "继"恢复先验哨兵; 第三道防线(git不可用→session JSON→冷启动)
- 4 Agent精简扫描组成定义: 5 Agent门控去Agent2(交叉引用)
- 反模式#10/#14/#15降级(v4.7.5诚实模型对齐), #23标注规范级
- 入口路由表补全: stop置顶, A-I全9类显式路由, G类40+ Agent全库扫描
- codex插件7命令全档: 补/codex:status(前置探测)+/codex:cancel(失控刹车); 插件仅替代传输层, 验证深度不降
- 自检#19新增: 消毒流水线合规(出站STEP 3+入站STEP 4粘贴)
- 错误表补STEP 0/1.5/2/Pre-6.0行(python失败/git缺失/参考源全失败/方案对比失败/DAG环)
- 墙钟时间盒诚实修正: 执行主体=hook/Agent工具基础设施, 非模型自查
- 缺口表vs状态表矛盾消除: 合并为单表"规范级", #3/#5/#6/#8补交叉引用, #10补train.py:594
- metadata: 60+ keywords/9类, agent-floor补4(post-compaction slim); "4源"→"5源"全文清理; 残留行号引用→§锚点

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
