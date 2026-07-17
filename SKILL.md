---
name: code-shiniyaya
description: CC↔Codex双重检验—codex帮我看下/让codex审一下/告诉codex/codex review/codex交叉验证/对敲代码/双向验证/双批准。用于BUG诊断修复/代码审计/方案评审等与Codex对敲代码场景。
version: 4.7.8
metadata:
  type: meta-orchestrator
  author: CC (shiniyaya)
  triggers: 60+ Chinese/English keywords across 9 categories
  agent-floor: 6 (diagnosis), 10 (Codex verify), 5 (reference scan), 5 (pre-optimization integrity), 4 (post-compaction slim)
  batch-floor: 4
  agent-cap: 50
  permissions:
    file-read: true
    file-write: true
    network: false
    shell: true
    agent: true
  auto_update:
    changelog: C:\Users\shiniyaya\Desktop\code-shiniyaya\CHANGELOG.md
    evolution_markers: true
    self_improving_agent_hooks: true
  hooks:
    on_error: { mode: auto, condition: any, context: "Error during code-shiniyaya workflow" }
    before_start: { mode: ask_first, condition: triggers_match, context: "Starting CC↔Codex workflow" }
    after_complete: { mode: auto, condition: step_done, context: "Completed step {step}" }
  evolution_markers: "<!-- Evolution: YYYY-MM-DD | source: ep-id | skill: name -->"
  correction_markers: "<!-- Correction: YYYY-MM-DD | was: 'old' | reason: why -->"
---

# code-shiniyaya v4.7.8 — 平台层防御+外部加速Skill

v4.7.8 — platform-first defense. 一字恢复(v4.7.5)之上: SessionStart hook自动bearings注入、echo-guard v3跨turn指纹、Stop hook对抗审查、permissions声明式备份层、可选外部加速Skill层(fp-check/MMAR/pantheon-fix/variant-analysis)。 CC 请求-响应架构：Claude 不能给自己发消息、不能自主启动新 turn、不能在压缩后自动续跑。全自动做不到。能做到的：保存全部状态 → 用户只需打一个字"继" → 任务无缝恢复。fake full-auto that silently fails < honest semi-auto that reliably works.

编排CC与Codex之间标准化双向验证闭环的元编排Skill。**不修改代码** — 编排诊断、方案生成、双批准门控、执行验证。

## 开发Skill栈 (v4.6.9, 每次对话强制激活)

code-shiniyaya自身的开发/迭代/优化必须在以下10个skill全部激活的状态下进行。缺失skill→先安装再继续。

| # | Skill | 级别 | 职责 |
|---|-------|------|------|
| 1 | **code-shiniyaya** | 编排器 | 9步闭环(STEP 0-8)+26条硬规则+20项自检+5源+ponytail七步阶梯+Hook基础设施 |
| 2 | **ponytail** | ultra | YAGNI极端主义: 删除优先→七步阶梯→ponytail: debt标注。永不新增无必要代码 |
| 3 | **caveman** | full | 输出压缩: 丢弃冠词/填充词/客套话, 代码/安全写正常。**auto-clarity**(v4.7.6,来自caveman CLAUDE.md L54-63): 安全警告/不可逆操作确认/多步骤序列→自动解除压缩写完整语言, 结束后恢复。`# ponytail: 3场景手动触发(无CC hook自动检测)，ceiling: 文本规则提示，upgrade: CC PreToolUse hook检测危险Bash命令时自动切换` |
| 4 | **ponytail-review** | 审查 | 过度工程审查: delete/stdlib/native/yagni/shrink标签, 单行发现, net: -N lines |
| 5 | **ponytail-audit** | 审计 | 全仓过度工程审计: 排序列出可删除的内容, net: -N lines, -M deps |
| 6 | **ponytail-debt** | 债务追踪 | ponytail: 注释收割→债务账本, no-trigger腐烂风险标记, PONYTAIL-DEBT.md |
| 7 | **ponytail-gain** | 计量 | 基准中位分板: LOC 6-20%(减少80-94%)/成本 23-53%(减少47-77%)/速度 3-6x。5任务×3模型。诚实边界: 不打印per-repo估算 |
| 8 | **ponytail-help** | 参考 | 全ponytail模式/子skill/配置快查卡片 |
| 9 | **using-superpowers** | 触发守卫 | 任何操作前先检查skill是否适用, 适用则强制调用, 不可跳过 |
| 10 | **openspec-explore** | 探索 | 思考不实现, 可视化, 质疑假设, 不rush, 不force structure |

**优先级链**: code-shiniyaya(编排) > ponytail(极简) > using-superpowers(触发) > caveman(输出) > ponytail-review/audit/debt/gain/help(审查层) > openspec-explore(探索)

**冲突裁决**: 安全/正确性 > 极简。信任边界验证/数据丢失保护/安全措施/无障碍/校准真实硬件/任何明确要求——6项永不简化。ponytail ultra的"删除优先"不覆盖code-shiniyaya规则1(双批准门控)。

**关键交互**:
- code-shiniyaya STEP 2方案生成: 先用ponytail七步阶梯检查→再生成方案→ponytail-review审查过度工程
- code-shiniyaya STEP 6执行: ponytail阶梯守卫验证修复梯级≤方案梯级
- 每次Write/Edit: caveman确保输出简洁 + ponytail: debt标注有意简化 + using-superpowers确认无遗漏skill触发
- 每轮迭代结束: ponytail-audit全仓审计 + ponytail-debt收割债务 + ponytail-gain诚实计量
- openspec-explore: 仅探索/设计方案时活跃, 执行/修复时降为背景

**ponytail-gain基准来源** (v4.6.9): 5个日常任务(邮箱验证器/debounce/CSV求和/倒计时器/速率限制器) × 3个模型(Haiku/Sonnet/Opus)。每任务分别用"无ponytail"与"ponytail"生成方案, LLM裁判(temperature=0)按公开rubric评分。原始数据见 judge.py + tasks.py。

**ponytail LOC计量代理** (v4.6.9): 源代码文件数 + 源代码LOC(排除测试文件/配置文件/文档/构建产物)。仅计算非测试源代码的实际行数变化。

### 外部加速Skill (v4.7.8, 可选层)

非10-skill栈成员, 不强制激活, 卸载零影响。定位同codex-plugin: 仅替代执行/传输/验证的机械层, 门控与验证深度不降, 规则1双批准语义永不被替代。8挂点: STEP 1预扫(aislop) / STEP 1.4(fp-check inferred加严) / STEP 4(fp-check FP消除) / STEP 6路由(pantheon-fix) / STEP 6.0合并前(differential-review) / STEP 7降级(MMAR) / STEP 7后(variant-analysis) / H类迭代(grilling+designing-workflow-skills+agent-lint)。每处自带"skill不可用→原路径"回退。

**跨模型诚实边界** (v4.7.8): 本机CC(全部model别名)与Codex CLI均经127.0.0.1:15721代理路由到同一后端(deepseek-v4-pro), gemini CLI未装——Codex双向验证/MMAR/pantheon-x的实际增益=**跨harness+新鲜上下文对抗**(不同系统提示/工具面/独立会话), 非模型多样性(同权重=同盲点)。pantheon-x的crossModelVerified戳在本环境仅证明harness隔离。需要真模型多样性时: pantheon-custom/MMAR指向非代理后端(ollama本地或直连非DeepSeek云key); pantheon-model配置verifier=deepseek为无操作(与代理后端同族)。`# ponytail: 静态声明依赖当前代理配置, ceiling: 文本caveat, upgrade: STEP 0环境检测比对ANTHROPIC_BASE_URL与codex config同host时自动注入此警告`

`# ponytail: 可选依赖手动探测(无自动probe)，ceiling: 引用处文本回退声明，upgrade: using-superpowers自动识别已安装skill时`

## Hook基础设施 (v4.6.9)

ponytail hooks/的9个生命周期模式直接适用于code-shiniyaya自身hook开发:

- **沉默失败契约**: 所有hook的写操作必须try/catch, 错误静默吞掉——hook绝对不能冻结会话。stdout EPIPE/close错误不表面为hook失败。
- **UTF-8 BOM剥离**: 所有JSON.parse调用前必须`.replace(/^﻿/, '')`——Windows编辑器会往UTF-8文件前加BOM。
- **stdin超时守卫**: Windows上PowerShell管道包装可能吞掉stdin输入, 'end'事件永不触发。解决: 1秒setTimeout回退(带unref()) + stdin 'error'监听器强制finish()。
- **一次性提醒哨兵文件**: 配置提示前检查哨兵文件(如`.ponytail-statusline-nudged`)——存在则跳过(用户已看过), 不存在则显示一次并写入哨兵, 防止跨会话反复骚扰。
- **Shell安全路径allowlist**: 将插件安装路径嵌入shell命令字符串前, 用`isShellSafe()`校验字符白名单——拒绝含引号/&/$/反引号/分号的路径, 回退到手动设置说明。
- **多级配置解析** (v4.6.9): env var > config file > hardcoded default。环境变量最高优先级, config.json的字段次之, 硬编码默认值兜底。适用: code-shiniyaya自身的任何可配置参数(如静默阈值N/批大小/预算比例)应采用同样三级解析。
- **平台感知配置目录**: Windows用`%APPDATA%\`, POSIX用`~/.config/`, 同时尊重`XDG_CONFIG_HOME`覆盖。适用: 任何持久化配置文件的路径选择。
- **停用检测(全消息匹配)**: 停用短语仅当构成整条消息时识别为停用——防止正常请求中包含这些词误触发。适用: code-shiniyaya自身的模式切换(如"stop"/"normal mode")检测逻辑。
- **子Agent规则集注入** (v4.6.9): SubagentStart hook将规则集注入子Agent。环境变量用正则筛选目标Agent类型。无效正则→fail-open(注入所有)。适用: code-shiniyaya的multi-agent-shiniyaya子Agent启动时应选择性注入规则。

## 可运行边界 (v4.5.4首次明确)

本Skill描述的功能分为两个层级:

### 当前可执行 (STEP 0-8工作流 + 核心纪律层)
所有9步工作流(STEP 0-8): 关键词触发→诊断→方案→Codex→验证→门控→执行→双向验证→元反思。STEP 8的自动触发部分(task-notification驱动)见架构依赖表——手动触发部分当前可执行。
- 26条硬规则中的规则1-14, 18-20, 26: 门控/Agent/Plan-Code Gap/停止线/用户中断/推理空间/死循环阻断
- 反模式1-9, 18: 核心编码和验证纪律+产出路径散落检查(自检#16同级)
- 输出格式化模式中的结果标记/编译验证/Shell脚本代理
- Git状态机模式(STEP 6.0)
- 降级模式(交互式N=4/N=5消息计数)
- 报告路径一致性和产出物写入
- 记忆内容质量规则/文件分类约定(纯文档约束, 无需平台支持)
- 自检#13和#16: 产出物写入+报告路径一致性检查(纯文档约束, 无需平台支持)

### 架构依赖 (文档化待平台升级, 运行时可行性已验证: 见§运行时可行性审计)

| 类别 | 受影响项 | 缺失能力 |
|------|---------|---------|
| 自主迭代 | 规则15-17,21-25, 自检1-5/7-12/14/15, 反模式10-23(除18) | 事件循环/持久后台/跨会话/自主通知 |
| 反思+信号 | STEP 8 Learn+Consolidate, 终端信号协议(类型化返回值/工具调用完成信号) | CC不向Agent注入虚拟工具/无事件驱动引擎 |
| 上下文+工厂 | 工作流上下文总线/CTX_UPDATE, 声明式事件依赖(listen_group), 代理工厂/动态指令闭包/工具预取 | 跨Agent调用无持久上下文/Agent框架层级不支持 |

原子写入协议/状态JSON: 设计完整, 运行时激活, 不依赖CC平台能力升级——仅需文件系统。

机制可行性: 7项不可行/2项部分可行/1项可行(详细矩阵见§运行时可行性审计); 自检#1/#3/#4/#11标记NON-VIABLE。其余标记待激活。

**根本限制** (v4.7.2, v4.7.7修正, v4.7.8更新): 文本规则无法打破LLM验证强迫——模型进入吸引子状态时执行检查的认知能力已被循环劫持。可靠性排序: **L2平台阻断(echo-guard.js v3.0+stop-guard.js双hook+permissions.deny备份层) > L3一字恢复 > L1文本规则**。模型侧最佳努力: 完成实质操作(Write/Edit/Agent启动)后立即停止turn，不确认状态、不echo确认词、不Read已写入文件。用户下一条消息时自然重置。

**外部看门狗** (v4.7.8, echo-guard.js v3.0 + stop-guard.js): 双hook注册于 settings.json。
- **PreToolUse Bash hook** `C:\Users\shiniyaya\.claude\hooks\echo-guard.js` v3.0: stdin JSON读取tool_input.command → (1)拦截无意义echo(done/ok/final/complete/verified/confirmed/纯数字/空串) (2)同turn同文件wc -l第2次拦截 (3)8次Bash/turn上限 (4)30秒空闲窗口≈turn边界(仅重置per-turn计数) (5)**命令指纹**(v3, unloop模式内化): 归一化MD5存跨turn滚动历史(20条/15分钟TTL, **不随turn重置**——hook状态文件天然跨turn, 补齐自检#18(c)(d)在Bash层的空缺) (6)**逐级升级**: 同指纹第2次→systemMessage警告; 第3次→`permissionDecision:"ask"`; ≥4次→`"deny"`+换策略指令(hookSpecificOutput三态契约)。
- **Stop hook** `stop-guard.js` (转移包§七: Stop=对抗审查唯一可靠入口): turn结束时解析transcript末段——最后assistant turn含≥2确认词且零Write/Edit/Agent调用→`{decision:"block"}`注入"写snapshot+输出⚡进度行后停止"。`stop_hook_active=true`必须放行(每stop最多1次干预, 平台级防hook自循环)。覆盖PreToolUse结构性盲区: 无工具调用的纯确认turn。
- **声明式deny备份层(L2.5)**: settings.json `permissions.deny`枚举拦截字面确认echo(6词+done/ok双引号变体+空echo); 项目级`.claude/settings.json` deny硬化L3最高危子集(rm/chmod递归/强推)。permissions与hooks为独立顶层键——插件重写hooks时deny存活。覆盖边界(诚实): 无正则→纯数字echo不覆盖; 无状态→wc去重/8次上限不可表达。echo-guard.js仍为L2主防线。
- 与规则26互补: hook管Bash层+turn终态, 规则26管Read/Grep/Write工具层transcript自查。注意: settings.json的hooks键可能被其他插件重写——每次CC重启后确认PreToolUse/Stop/SessionStart条目仍存在。
`# ponytail: 指纹=归一化精确匹配, ceiling: 改写等价命令逃逸; stop-guard transcript schema随CC版本漂移, ceiling: 解析失败静默放行, upgrade: CC提供结构化turn摘要API时`

**已评估拒绝** (v4.7.8, 转移包§三评估): ①claude-focus——每调用注入变动前缀→prompt cache全未命中, 任务锚定已由iteration-task.md+snapshot承担→拒绝。②LoopLens/unloop-mcp整装安装——MCP依赖违背零依赖hook原则, unloop的指纹+升级模式已内化为echo-guard v3→拒绝安装, 模式采纳。③Semantic Early-Stopping原样实现——无embedding API→降级为规则24词法重叠。④asyncRewake心跳唤醒——后台Agent完成本就自动唤醒, sleep+rewake=重新发明轮询器→拒绝。⑤headroom_compress——文件重定向严格更优(内容不进上下文 vs 压缩副本+原件双份)→拒绝。⑥PAR整体替换"10+ Agent验证"——该块承载grounding协议/re-prompt/规则7/规则20契约, ≥6处下游引用, 替换波及大于收益→拒绝(PAR保留为独立review场景用)。

## 上下文感知防饱和 (v4.7.3, 死循环事前预防)

**根因分析**: 死循环(echo done/ok/wc -l × N)不是规则设计缺陷——是LLM在上下文窗口接近饱和时进入验证强迫吸引子状态的结果。文本规则(规则26/自检#18/外部hook)只能事后阻断已发生的循环，不能防止模型进入吸引子。唯一有效的事前预防=避免上下文饱和——定期保存记忆+关键状态并压缩。

### 上下文饱和度检测

**饱和度检测信号** (v4.7.5, 启发式——CC无token计数API，依赖transcript自查):

CC在每个turn开始前检查以下信号:

1. **历史工具调用密度**: 最后20条消息中工具调用占比>70%→潜在验证循环
2. **重复模式出现**: 同一工具+同一参数在最近10次调用中出现≥2次→饱和信号
3. **输出长度衰减**: 最后5条消息的平均长度<前5条的50%→认知能力衰减
4. **确认词密度**: 最近10条输出中done/ok/final/complete/verified出现≥3次且无实质Write/Edit→吸引子状态
5. **上下文膨胀**: 最近turn中引用的不同文件/代码块>20个→上下文可能即将饱和(间接代理)

`# ponytail: 5个信号无自动执行机制(CC无法在turn开始前自查transcript, 吸引子状态下自查失效)——这是启发式指南，不是自动化检测。实际触发依赖versionVector × 12%(§自动压缩阈值)，ceiling: 模型自觉执行，upgrade: CC公开token计数或会话心跳API时`

任一信号触发=上下文饱和风险。不输出分析，直接执行记忆保存流程。

### 记忆保存+一字恢复 (v4.7.5, 诚实面对架构极限)

**架构现实**: CC 是请求-响应模型。Claude 不能给自己发消息、不能自主启动新 turn、压缩后不能自动续跑。任何声称"AI 可以自主压缩+自动继续"的说法都是伪功能——因为 Claude 没有跨 turn 的自主执行能力。

**能做到的**: 保存状态到 snapshot 文件 + 把恢复成本降到一字。

```
55%饱和信号触发:
  1. 保存 memory/snapshot-{ts}.md (版本号/todo/关键数据/**nextAction/干净轮计数i/2**)——原子写入(tmp+rename)+末尾哨兵行`<!-- SNAPSHOT-COMPLETE {ts} -->`。nextAction赋值: 预发射成功Agent在飞→**await**; pending非空→fix; 干净轮计数≥2→verify; 其余→scan(与恢复决策①-④对应)
  2. CHANGELOG 追加一行
  3. git add + commit（不push——push可能因网络失败阻塞保存，snapshot本地保存即安全）
  4. 输出: "⚡ 55% — /compact + 继"
  5. 不echo done/ok/final/complete等确认词，不Read刚写的文件，不启动新Agent，不调用任何新工具。输出仅允许饱和警告单行(步骤4)。**CC不能主动终止turn——此约束靠模型自觉: 输出警告后不再调用工具，自然结束turn。**

用户: /compact
系统: 压缩完成
用户: 继
AI: 读最新snapshot → 恢复全部状态 → 继续执行
     ├─ 读 memory/snapshot-{latest_ts}.md
     ├─ `ls memory/snapshot-*.md | sort | tail -1` 取最新文件（压缩后AI不知时间戳）
     ├─ 读 CHANGELOG.md 最后一条snapshot记录
     ├─ 运行4 Agent精简完整性扫描(跳过完整5 Agent验证)
     ├─ 恢复未完成任务列表 + 关键指标
     └─ 恢复决策(v4.7.8, 替代模糊的"从断点继续"; 分支①②③自上而下求值首中即行, nextAction与实际状态矛盾时以实际状态(pending/计数)为准):
        ├─ ① nextAction=await OR 有在飞Agent/未处理的预发射结果 → **不重复启动**——先查journal/task-notification处理已到结果(回§自主执行item 1主循环); 确认无在飞且无未处理结果后才按②启动
        ├─ ② nextAction=scan OR (干净轮计数<2 AND 无pending项) → 立即启动下一轮扫描Agent(同turn; 启动前过三硬门: 饱和/预算/在飞)
        ├─ ③ nextAction=fix OR pending非空 → 从首个pending项继续修复
        └─ ④ nextAction=verify OR 干净轮计数≥2 → 确认收敛(=按规则24跑最终50 Agent验证, P0=0方可)→写goal-reached→输出签收单; goal-reached.md已存在→直接签收单
```

**恢复触发词** (v4.7.5新增):
- "继" → 读最新snapshot → 恢复执行（一字恢复专有触发词，不冲突）
- "继续执行" / "继续迭代" / "继续优化" → 同上(snapshot恢复)
- "继续修复" → session JSON恢复(session级)——若session JSON不存在则回退snapshot恢复
- "resume" / "go on" / "pick up" → 先尝试session JSON恢复，不存在则snapshot恢复
- "继续" (裸词) → 不触发恢复 → 提示用户明确意图
- "继续等" / "继续等待" / "继续等Codex" → 保持静默等待，不触发恢复路由
- snapshot不存在且session JSON也不存在 → "无活动会话或快照可恢复。开始新任务吗?"


**一字恢复标准化启动检查清单** (v4.7.6, 来自autonomous-coding coding_prompt.md GET YOUR BEARINGS):
当"继"触发恢复时，在执行snapshot恢复后，CC应立即执行7步标准化环境确认：
1. `pwd` → 确认工作目录
2. `ls memory/snapshot-*.md` → 列出所有快照
3. `git log --oneline -5` → 确认当前HEAD
4. `git status --short` → 确认工作区clean
5. `cat CHANGELOG.md | head -30` → 了解最近变更
6. `ls memory/ | wc -l` → 确认记忆文件数
7. 交叉对比snapshot版本号 vs git HEAD → 不匹配则警告用户
`# ponytail: upgrade条件已达成(v4.7.8)——步骤1-6由SessionStart hook(bearings.js, matcher: startup|resume|compact)自动注入为系统上下文, 步骤7(版本交叉比对)仍由模型在"继"时执行。hook缺失→回退手动7步。ceiling: hook只消除信息收集成本, 恢复执行仍需用户"继"(CC不能自启turn)`

**基线优先原则** (v4.7.6, 来自autoresearch program.md:39): 任何优化/修复循环的第一步永远是建立无修改基线。STEP 6修复前必须先记录当前指标基线——修复后才知是否改善。`# ponytail: 手动记录基线(CC无自动benchmark)，ceiling: 人工比对，upgrade: CC集成自动化benchmark时`

**为什么不自动`/compact`?** 见§记忆保存架构现实——`/compact`是终端命令, Claude不能向自己发送; ScheduleWakeup/CronCreate均不能替代。任何绕过声明=伪功能。

**一字恢复的可靠性保证**:
- snapshot 文件是结构化的，恢复时不需要重新理解上下文；写入走原子协议(tmp+rename)+末尾哨兵行`<!-- SNAPSHOT-COMPLETE {ts} -->`——"继"恢复时先验证哨兵，缺失=截断快照，进入第二道防线
- CHANGELOG 记录了精确的断点版本和未完成任务
- Git 提交保证了 snapshot 不会因压缩丢失
- 4 Agent 精简扫描为第一道防线——验证恢复后文件完整性
- 4 Agent扫描发现不可自动修复的损坏→从git恢复上一版本snapshot为第二道防线
- 第三道防线: git不可用或无历史版本→回退session JSON恢复→仍不可→冷启动STEP 0，损坏snapshot保留为`.corrupt`供人工审查

### 饱和保存的网络可靠性 (v4.7.5)
保存时不尝试push（见55%流程步骤3）。snapshot通过git commit保存在本地即安全；网络恢复后统一推送。commit失败→snapshot仍在磁盘，输出警告行，不阻塞turn终止。

### 优化前5 Agent完整性验证

任何时候在触发自主迭代优化（"优化skill"/"根据源文件优化"等H类触发词）之前，必须先运行完整性门控:

```
5 Agent 并行 → 4维度扫描:
  Agent 1: 文件完整性 — 检查 SKILL.md/README.md/CHANGELOG.md/memory/*.md 是否存在 + 非空 + 编码正确(UTF-8无BOM)
  Agent 2: 交叉引用完整性 — 检查 SKILL.md 中所有 `[[link]]` 引用的目标文件是否存在 + 行号引用有效近似(±15行)
  Agent 3: 版本一致性 — 检查 SKILL.md 版本号 vs CHANGELOG.md 最新条目 vs memory/*.md 版本引用是否一致
  Agent 4: 数据完整性 — 检查 memory/ 目录下所有JSON文件是否有效JSON(可解析) + 关键字段非空
  Agent 5: Git完整性 — git status 检查无未跟踪关键文件 + 最近提交消息是否合理
```

**通过标准**: 5/5通过→进入优化。1-2失败→自动修复(缺失文件→从git恢复，错误编码→修正，JSON损坏→从备份恢复)→重新扫描→通过后继续。3+失败→告警+停止，输出缺失/损坏文件清单提示用户审查。

此门控=防止压缩/恢复过程中因文件丢失或损坏导致的无声优化偏差——确保每次优化前所有关键文件完整且一致。

### 压缩后恢复流程

用户发送 /compact 后新会话:
1. 读取 `memory/snapshot-{latest_ts}.md` → 验证末尾哨兵行 → 恢复版本号、未完成任务、关键指标
2. 运行4 Agent精简完整性扫描 = 5 Agent门控去掉Agent 2(交叉引用, 成本最高): Agent1文件完整性 + Agent3版本一致性 + Agent4数据完整性 + Agent5 Git完整性
3. 从CHANGELOG.md最后一条snapshot记录续取任务。CHANGELOG.md不存在→`git checkout -- CHANGELOG.md`恢复→git无历史→以snapshot自身任务清单为准重建CHANGELOG头部
4. git log为空或HEAD不存在(全新仓库)→跳过7步检查清单的步骤3/7，以snapshot+CHANGELOG为唯一基准，输出"无git历史"警告

### 自动压缩阈值 (v4.7.5, 诚实语义)

| 估算占用 | 动作 |
|---------|------|
| <55% | 正常执行 |
| 55-70% | **一字恢复**: 保存snapshot+git commit(不push) → 输出"⚡ 55% — /compact + 继" → 终止turn |
| 70-90% | 同上 + 输出时不调用新Agent + 标注紧急 |
| >90% | 仅保存snapshot+git commit(不push)，输出"⚠️ >90% /compact 继"，不启动任何Agent |

阈值估算: versionVector × ~12% (每轮20 Agent ≈ 10-15%上下文消耗)。Write密集型会话此估算准确；Read密集型会话严重低估（versionVector仅追踪写入次数，Read/Grep不产生versionVector递增 → 此为本机制的已知天花板）。压缩后恢复时versionVector清零。

`# ponytail: 阈值估算是启发式的(无token计数API)，ceiling: versionVector × 12% (Read密集型会话低估~30-50%)，upgrade: CC公开token计数API时替换为精确百分比；或增加turn计数作为辅助估算信号`

### 与现有机制的关系

- **规则26(循环阻断)**: 事后阻断——循环已发生时的止损。事前预防优先于事后阻断。
- **PreToolUse hook**: 事后阻断——平台级工具调用上限。事前预防优先于事后阻断。
- **STEP 8 Learn+Consolidate**: 事后反思——知识合并到记忆。压缩保存用的是同一机制但触发条件更宽(饱和信号而非反思门控)。
- **本机制 (v4.7.5)**: 保存=事前预防(避免饱和进吸引子)，恢复=事后止损。可靠性排序: echo-guard.js(L2平台) > 一字恢复(L3) > 规则26(L1文本)——文本规则在吸引子状态下失效，平台阻断不依赖模型认知。

`# ponytail: 无法自主压缩(CC架构限制)，ceiling: 一字恢复模型，upgrade: CC支持AI自主发送终端命令时`

<!-- 死循环三层防御: L1=规则26(事后阻断 v4.6.9), L2=PreToolUse hook(平台止损 v4.7.2), L3=一字恢复(保存+续跑 v4.7.5) -->

## 多Agent并行时主任务栏工作 (v4.7.5, 防echo循环)

根因: 多个Agent后台跑时CC空转等待→验证强迫→echo "done"/"ok"/"1"/"2"。解法: 不等——主任务栏同步做有产出的事。

Agent并行启动后，主任务栏同步执行（不等Agent返回）:

1. **写snapshot草稿**: 基于当前已知状态写memory/snapshot-{ts}.md(不要等Agent完成后才写→那时可能已进入echo循环)。草稿必含nextAction(Agent在跑→scan; 已入修复→fix)+当前干净轮计数——恢复决策树的两个输入必须在草稿期即落盘。
2. **更新CHANGELOG**: 写本轮迭代的CHANGELOG条目草稿(版本号/日期/已知修复摘要)
3. **读取上一轮产出**: 如有journal.jsonl→预提取模式→准备交叉对比
4. **git操作**: git status + git log --oneline -3 → 确认工作树状态(注意: 消耗echo-guard 8次Bash/turn配额中的2次)
5. **预填充snapshot草稿的P0/P1/P2分类骨架**: 把分类框架写入步骤1的snapshot草稿文件(可观察产物, 非仅thinking)→Agent返回直接填充

**Agent输出重定向+grep结构化提取** (v4.7.6, 来自autoresearch program.md:99-101): Agent输出全量写入独立文件→grep/结构化解析提取关键指标→仅指标进入对话上下文。避免Agent原始输出涌入主上下文窗口。`# ponytail: CC当前将所有Agent输出读取到主上下文(不同于autoresearch全量重定向模型)，ceiling: 主任务栏摘要+后台文件写入，upgrade: CC支持管道重定向bash时`

禁止:
- echo "done"/"ok"/"1"/"2"等任何占位输出
- 重复Read同一文件(规则26(a))
- Grep同一pattern同一path(规则26(b))
- 输出确认词(done/final/complete/verified/confirmed)且无Write/Edit

Agent全部返回→汇总→去重→分类→修复→提交→下一轮验证。

`# ponytail: 主任务栏工作防echo循环，ceiling: Agent快时主任务可能未完成，upgrade: CC暴露Agent进度事件时用事件驱动`

<!-- CC架构基准: CLI请求-响应, 无事件循环, 无守护进程, 无后台任务通知 -->
<!-- 最终验证: 5 Agent PASS, 源文件引用正确, 跨文件一致, 无内部矛盾, 0不可实现模式 -->

<!-- P1-FUTURE: Config Externalization — v4.4.0 RESOLVED: 所有硬编码常量已集中到 memory/config.json。剩余散落引用仅在需要覆盖默认值时查阅config.json。详见 memory/config.json schema。-->

**Codex通信模型**: 首选通过 codex-plugin-cc (OpenAI官方插件, github.com/openai/codex-plugin-cc) 直接调用Codex CLI, 替代手动复制粘贴。插件提供 `/codex:review` (只读审查), `/codex:adversarial-review` (对抗性审查), `/codex:rescue` (任务委派) 等斜杠命令, 通过本地Codex app server的JSON-RPC接口自动收发。回退模式: 插件不可用时→手动复制粘贴(用户手动在CC和Codex之间传递消息)。

**codex-plugin-cc 集成** (v4.7.1):
- 安装: `/plugin marketplace add openai/codex-plugin-cc` → `/plugin install codex@openai-codex` → `/reload-plugins` → `/codex:setup`
- 需求: ChatGPT订阅(含Free tier)或OpenAI API key, Node.js 18.18+, Codex CLI (`@openai/codex`) 已登录
- STEP 4 验证: `/codex:review` 自动化——不再粘贴文本→解析回复→验证, 而是直接调用Codex审查uncommitted变更或分支diff。**插件仅替代传输层**: 返回内容视同粘贴回复, STEP 4的10+ Agent 7维验证/Byzantine防御/grounding检查/输入上限全部照常适用——验证深度不因插件降低。
- STEP 4 交叉验证: `/codex:adversarial-review` 替代手动Codex回复解析——定向skeptical审查, 挑战设计决策/假设/失败模式
- STEP 6 执行: `/codex:rescue` 委派bug修复/回归追踪给Codex子Agent——CC编排, Codex执行
- 可用性探测: `/codex:status` 作为STEP 4前置检查——status报错→立即切换手动粘贴回退, 不等N=5超时
- 失控刹车: `/codex:cancel` 取消运行中Codex任务——`--enable-review-gate` 产生CC↔Codex循环时的应急手段
- session转移: `/codex:transfer` 将当前CC会话转为持久Codex线程——可恢复
- 注意: 启用 `--enable-review-gate` 可产生CC↔Codex循环, 迅速消耗用量——谨慎使用, 失控时`/codex:cancel`
- 回退: 插件不可用(status报错/JSON-RPC不可解析/认证失效)→单次重试→仍失败→手动复制粘贴模型, silentMsgCount重置。消毒流水线(规则28)完整6步适用于手动粘贴路径; 插件JSON-RPC直传内容豁免第6步(围栏转义——结构化传输无边界混淆), 但字符消毒1-5步(Bidi/NFKC/零宽/Null/C0C1)仍适用——Codex内容内嵌的恶意字符不因传输方式而消失。静默阈值N=4仅手动模式适用。
**会话ID**: 取自CCD会话UUID(CCD session UUID, 由会话管理API返回的sessionId字段), 取前8十六进制字符用于文件名。如果session UUID不可用→回退使用`uuid4().hex[:8]`。
**静默阈值**: N=4——连续4条用户消息无Codex回复粘贴触发询问（"继续等/跳过?"）。多部分Codex粘贴保护: 相邻消息<3s且连续内容→计为1条消息, 不触发N=4; 含`[MSG-{4hex} i/N]`标记→按标记权威判定(见STEP 3消息关联ID)。注: CC无法观察Codex是否真正回复——这是手动复制粘贴模型的固有局限。静默计数基于CC侧用户消息中是否出现Codex回复粘贴模式匹配。这不是Codex是否回复的权威检测——仅检测用户是否在CC中粘贴了回复。
**恢复触发词**: 见§一字恢复触发词表(行159-166)——"继"/"继续执行"/"继续迭代"/"继续优化"→snapshot恢复; "继续修复"/"resume"→session JSON恢复。裸词"继续"不触发(过于宽泛)。静默等待: "继续等"/"继续等待"→保持静默计数, 不触发恢复路由。

## 触发 (60+ 短语, 9类)

**A. 发送 (8):** "告诉codex", "发给codex", "让codex分析", "让Codex确认", "把结果告诉codex", "把方案告诉codex让他分析", "请完全遵守规则现在先告诉codex", "codex帮我看下"

**B. 验证+审查 (17):** "双重检验", "双向验证", "codex交叉验证", "对敲代码", "交叉验证codex", "用codex验证", "codex核验", "codex把关", "codex review", "codex复审", "让codex审一下", "给Codex过一遍", "codex也跑一遍", "让codex看看", "codex双重检查", "codex交叉审计", "codex协同审查"

**C. 协作/对照 (8):** "帮我和codex对一下", "发给Codex审核", "codex协同", "cc和codex一起修", "cc和codex", "两边对照", "双向审核", "联合审查"

**D. 门控 (5):** "双批准", "双重批准", "双方确认后执行", "codex审批", "发给codex审批"

**E. 方案/扫描 (7):** "多方案对比", "源文件交叉验证", "deep diagnosis", "cross-verify with codex", "启动方案验证", "方案审批", "修复方案审批"

**F. AI通用 (3):** "发给AI审查", "让AI也看看", "交叉检查"

**G. 全量 (3):** "全量扫描", "full scan", "codex全量"

**H. 自主迭代 (9):** "循环迭代", "自动更新", "自动迭代", "自主执行", "不中断", "持续修复", "自动扫描修复", "优化skill", "根据源文件优化"

**I. Agent错误反馈 (v4.6.11):** "agent错误", "agent失败", "静默无反馈", "agent报错"

**假阳性门控**: "双重检查"、"交叉审计"、"协同审查" — 仅在含"codex"前缀的版本(如"codex双重检查")触发skill时弹出确认。无前缀的裸短语不匹配任何触发类别，不弹出确认。

## 自主迭代模式 (v4.6.10, 触发词: 循环迭代/自动更新/自动迭代/自主执行/不中断/持续修复/自动扫描修复)

当用户消息包含触发词H类时，进入自主迭代模式:

### 计划生成
1. **分析需求** → 识别任务目标、范围边界、成功标准
2. **生成迭代计划** → 写入 `C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\iteration-plans\plan-{ts}.md`
   - 任务分解（阶段×步骤）
   - 每步的验证标准
   - 停止条件（零bug / 用户显式停 / 预算耗尽）
   - 预计Agent数量和工作流轮次
3. **呈现计划供审阅** → 输出计划摘要，提示"审阅后回复'批准执行'或提出修改"
3b. (v4.7.8可选) grilling可用→呈现前先对迭代计划跑压力测试(挑战假设/失败模式)→修正后再呈现审阅; 不可用→直接呈现

### 自主执行
一旦用户批准（或用户下一条消息为非否决/非修改内容的任意回复→视为批准）:
1. **不中断+预发射** (v4.7.5 降级, v4.7.8消除干净轮卡顿): 同turn内工作流完成→立即处理结果→修复→**若未收敛→同turn内立即启动下一轮扫描Agent(不等用户"继")→然后输出进度行+等待结果**。若turn自然结束→输出"第N轮[dim]: X→Y→继"或"第N轮: 干净轮i/2→继"→等用户"继"→从snapshot恢复→继续下一轮。不可跨turn自主启动(CC架构: 无自主跨turn执行)。**关键**: 扫描结果返回且未收敛时——在同turn内启动下一轮扫描Agent, Agent启动后才输出进度行结束turn。预发射失败(turn token不足等)→输出进度行+等待用户"继"。`# ponytail: 预发射Agent结果跨turn可靠性=CC Agent生命周期保证, ceiling: Agent超时/CC重启→回退原"继→发射"路径, upgrade: CC保证跨turn结果可靠投递`
2. **不结束**: 直到 (a)零bug收敛(**干净轮计数器≥2**, 见规则24), (b)用户说停/stop, (c)预算耗尽
3. **不等待** (v4.7.5 降级): 同turn内绝不在迭代中途输出"要继续吗?"。turn结束=停止——等用户"继"恢复。
4. **每轮输出**: 一行进度。正常轮: "第N轮[dim]: X→Y→继"(X=发现数, Y=修复数, dim=本轮维度名/干净轮状态——两者二选一填一个); 干净轮: "第N轮: 干净轮i/2→继"(i=当前计数)。不输出长篇分析。turn结束符——用户"继"时下轮结果已就绪可直接处理。预发射失败→回退简式"第N轮: X→Y→继"。
5. **达标时输出**: 最终签收单（发现总数、修复总数、当前零bug确认）
6. **5源深度优化** (v4.6.10): 每轮迭代必须从5个源文件(AutoAgent/autodream/autoresearch/autonomous-coding/ponytail)中提取可优化点——扫描→对比→提取→写入SKILL.md→验证。循环持续直到所有源文件中无可提取的优化点(连续2轮零新发现且规则24干净轮计数器≥2=收敛)。收敛后(v4.7.8可选): designing-workflow-skills单次质量轴过检(触发词/描述/阶段出入口/路由关键词/子Agent提示词/工具调用规模AP-18/19——5源内容扫描不覆盖的维度; AP-2超500行=已知WONTFIX不计发现); 不可用→跳过。
`# ponytail: skill-improver被此取代——skill-improver的fix-review loop与H类自身循环冗余, 且硬需plugin-dev skill-reviewer agent(本环境未装)→slot永走不可用分支==dead text; designing-workflow-skills纯Read/Grep/Glob, review-checklist.md覆盖slot全部维度+AP-18/19(直接审计代码规模驳杂的20-Agent batching)`
7. **Agent失败零静默** (v4.6.11): 任何Agent/工作流调用失败必须立即报告: (a)失败数量, (b)失败原因(超时/JSON Schema错误/API错误/内容过滤/其他), (c)尝试的修复动作(重试/切换Agent类型/回退纯agent()调用/放弃该维度)。静默跳过失败Agent=致命违反。若JSON Schema为根因→下一次调用禁用schema参数直接使用纯文本输出。若某维度所有Agent类型均失败→标记PERMANENTLY_FAILED并写入ERRORS.md, 不静默跳过。
8. **逐项优化逐项验证** (v4.7.0): 每个优化任务完成后立即20 Agent全维度扫描→发现bug→修复→重新扫描→零bug后进入下一优化任务。不批量优化, 不跳过验证。优化序列化执行确保每步变更可追溯。

### 迭代任务定义 (v4.6.10)
默认迭代任务: **根据五个源文件优化SKILL.md直到没有可以优化的地方。**
- 每轮: 20 Agent × 5源(每源4 Agent)深度扫描
- 维度: 自动化模式/验证机制/代码质量/迭代连续性/记忆模式/工具API/Agent协调/输入输出/配置基础设施/基准测试
- 每轮产出: 新发现的模式→写入SKILL.md→ponytail:debt标注→验证无bug
- 收敛条件: 连续2轮零新发现 + P0=0 + P1=0 + **干净轮计数器≥2**(规则24干净轮——修复轮永不计为干净轮, v4.7.8实证×2)
- 源文件利用深度: 每轮轮换未读文件/未扫描函数/交叉配对组合

### 中断恢复
- stop/CTRL+C → 保存session状态 → 等用户
- "继续修复" → 从session JSON恢复继续
- "继" → snapshot恢复 → **snapshot中`nextAction`字段决定恢复后首个动作("scan"=启动下一轮扫描/"fix"=从pending项继续修复/"verify"=进入验证)。scan→在同turn内启动扫描Agent, 启动后输出进度行; 启动失败→回退fix或verify→仍失败→输出进度行+等用户"继"。**`# ponytail: nextAction字段规范级(手工写入snapshot), ceiling: 恢复动作依赖模型读取+执行(非自动), upgrade: 同bearings.js自动注入一起自动化`
- 预算完全耗尽(>90%+BREAK_GLASS, 见§修复预算) → 写FINAL-STATUS.md → 停止并通知

### 与其他规则的关系
- 规则1（双批准门控）: 迭代模式下降级为事后CHANGELOG.md审计
- 规则4（逐项反馈）: 暂停，P0/P1自动执行
- 规则15（迭代不中断）: 此为本模式的基础规则
- P0安全敏感修复（数据丢失/安全漏洞/权限提升）: 仍需在CHANGELOG.md审计记录后触发用户中断确认

<EXTREMELY-IMPORTANT>
触发词匹配 → 调用此Skill。先诊断→写方案→可复制文本→等Codex→验证→双批准→执行。不跳过。不无批准修改源码。假阳性触发: 用户说"no"/"不是"→立即退出。
</EXTREMELY-IMPORTANT>

## 硬规则 (26条, 交付规则27-28)

### 门控
1. **双批准门控**: 用户+Codex双方批准 = 必须。单方禁止。Codex批准需每项file:line证据(拒绝笼统"all items approved")。CC必须独立验证每项Codex批准(读源码+ast.parse)。Codex "approved IF X" = 部分: 批准项执行, 条件项重做方案+再审批。Codex不可用(codex静默→降级模式): 用户单批准可执行(Step 5降级条款)。
2. **CC不独立修改源码**: 无例外(记忆/规则/review/报告/迭代自修复除外)。迭代自修复仅限: 语法错误/导入缺失/配置修正/反模式更新, 且每轮写入CHANGELOG.md审计轨迹。P0逻辑变更仍需用户批准。
3. **分析自由, 修改阻断**: 诊断/方案/报告=无门控; 触及Edit/Write到源码→阻断。
4. **逐项反馈, stop优先, 迭代豁免** (v4.2.6, v4.6.9 P0例外): 每项→反馈→确认→继续。禁止批量。stop→立即停, 项=INTERRUPTED(已完成子步骤保留, 未开始子步骤待恢复)。唯一例外: STEP 6 P2微改动(<3行)可批量2项——P0/P1不适用。**迭代模式(规则15激活时): 规则4暂停——STEP 6执行时不要求逐项用户确认, P0/P1项自动执行+写入CHANGELOG.md审计轨迹, P2项可批量2项。例外: P0安全敏感修复(数据丢失/安全漏洞/权限提升)仍需在CHANGELOG.md审计记录后触发用户中断确认——迭代模式不覆盖安全敏感项的门控。用户显式中断(stop/CTRL+C)仍然优先。**

### Agent
5. **批次**: batch_size = max(4, min(16, cpu_cores-2)), cpu_cores=`python -c "import os; print(os.cpu_count() or 4)"`, 回退=4。总Agent上限=50(超出则排队复用)。迭代扫描20 Agent分2批: 第一批batch_size个, 剩余在首批首个完成后立即追加, 总并发窗口<60s。预发射轮的批2追加移至"继"turn首个动作(在分支①守卫内: 有在飞批1→先追加批2, 非新轮; 自检#6不可因预发射轮批1-only判为规格缩小)。
6. **语法门控**: 批次间验证(ast.parse/tsc/eslint)→前进→失败回滚。
7. **失败替换与3层重试升级**: Agent异常终止或挂起→替换, 每槽位最多2次→第3次升级(见下方3层重试表)。超时由Agent工具基础设施处理。

| 尝试 | Agent类型 | 权限 | 提示词注入 |
|------|----------|------|-----------|
| 1 | 原始类型(如investigator) | 标准 | 无 |
| 2 | 原始类型 | 标准 | 注入上次失败原因作为反馈 |
| 3 | general-purpose(升级) | 全部文件读取 + 全部Skill | "原Agent 2次尝试失败。失败原因: {reason}。请使用不同方法解决。" |

第3次升级后仍失败→标记PERMANENTLY_FAILED, 写入ERRORS.md, 不重试。若原始类型已是general-purpose: 升级到Plan Agent(架构视角)。

Agent返回无TERMINAL行→标记TIMED_OUT, 触发替换。连续2次TERMINAL: UNRESOLVED→触发升级到第3层(general-purpose)。TERMINAL: PARTIAL→不替换, 排队补全(若配额允许)。
8. **无共享文件**: 单Agent=串行安全。多Agent=CC自保(共享文件检测+串行排队)。

### Plan-Code Gap
9. **代码≠方案**: `git diff --stat`+`grep -n`双验证。不一致→回滚+报告。
10. **方案锁定**: 偏离=(a)未列出文件OR(b)函数/类范围外OR(c)机制改变。行号±5内允许。偏离→新方案+重双批准。
11. **盲写禁止**: Write/Edit前必须Read。

### 停止线
12. **3次同文件失败 + 崩溃分类**: 同Skill调用内3次Write/Edit错误→停止, 写STOP_LOG.md, 等用户。不跨调用累计。
    - **Type A (琐碎错误)**: 拼写错误/缺失导入/语法错误 → 自动修复+重试, 不消耗重试配额。
    - **Type B (根本性错误)**: OOM/架构问题/权限拒绝 → 消耗重试配额, 3次后终止。
13. **stop/中断/CTRL+C** → 立即停, 等下条消息。完成项保留(逐项确认保证), 未开始项待恢复。
14. **Write/Edit成功** = 已写入 → 不Read验证代码正确性(语法/逻辑审查)。始终执行原子写入协议的checksum验证性Read(≤1次, 仅计算SHA-256, 不做内容审查)。
15. **迭代不中断** (v4.7.7 恢复完整定义): 迭代模式下持续执行不停顿。**停止例外**: (a)零bug收敛达标 (b)用户显式stop (c)致命错误无法继续 (d)预算完全耗尽(>90%+BREAK_GLASS, 见§修复预算)。此规则优先于规则1(双批准门控)、规则4(逐项反馈)、规则9(代码不符回滚)和规则10(方案锁定)——但不覆盖规则2(P0逻辑变更仍需用户批准)和冲突裁决(行55)中的安全护栏(6项永不简化)。安全关键的门控检查和P0逻辑变更即使在迭代模式下也不可跳过。turn结束时输出进度行"第N轮: X→Y→继"(自检#1例外d)。
16. **双轨修复** (v3.9.1): 每次迭代修复必须同时推进两条轨道——(a) SKILL.md内容优化(功能/安全/工作流完整性), (b) 迭代流程本身优化(防中断/防偏离/防缩小/防无意义重复/5源深度利用/自我迭代能力)。两轨不可偏废。轨道(b)的优化目标来自上一轮元迭代自检发现的能力缺口。轨道(a)的优化目标来自5源交叉验证的缺口分析。
17. **优化方向完整性** (v3.9.1): 每次迭代必须覆盖全部7大优化方向(持续性/保真性/有意义性/稳定性/5源深度利用/自我迭代/报告规范), 详见memory/optimization-plan.md。不得只优化其中1-2个方向而忽略其余。
18. **用户中断处理** (v3.9.1, v4.7.8增交错顺序): 用户发"停"/"stop"/"报告"=唯一合法的迭代停止信号。收到后允许CC写用户可见汇报。但用户消息≠停止——只有显式中断词才触发。普通消息("检查下进度", "怎么样了")=CC可简短回复状态然后继续迭代, 不停止。**普通消息到达且有已返回未处理的Agent结果→同turn顺序: ①简短回答用户(≤3行, 计自检#1例外(e)) ②处理结果→修复→按§自主执行item 1预发射 ③末尾输出进度行。回答不中断迭代、不重置计数器。**
19. **工作流输出不阻断** (v3.9.2): CC在task-notification处理期间产生的"思考过程"(thinking)≠用户可见输出。只有最终文本响应(role=assistant的text content)才算用户可见。即: CC可以在thinking中分析问题+规划修复, 只要最终不写用户可见消息即可。这允许CC静默迭代而无需完全禁用分析能力。
20. **P0验证规格化** (v3.9.2, v4.6.9 明确模式区分, v4.7.8 verifier槽位): P0项的双Agent验证必须指定: 类型=investigator+general-purpose, 维度=正确性(代码逻辑)+编码安全(注入/越权/泄露)。不指定类型和维度的"2+ Agent验证"为空话。**非降级模式=2 Agent(investigator+general-purpose), 降级模式=4 Agent(investigator+general-purpose+Plan+debugging)**——所有引用此规则处必须根据当前模式使用对应Agent规格。模式区分见§错误处理-降级模式条款。验证槽位优先使用自定义类型`code-shiniyaya-verifier`(~/.claude/agents/, 平台侧钉死维度+只读工具集(均含Read/Grep/Glob; Bash含但不用于写操作——写禁止为提示词级约束)); 不可用→原规格不变。
21. **趋势确认而非单点验证** (v3.9.3): 单次50 Agent验证返回非零不表示"目标未达成"——需对比上一轮结果看趋势。若本轮50 Agent发现数 < 上一轮发现数且P0下降, 则为健康趋同。只有连续2轮发现数不变且P0>0才触发"无意义重复"检查(自检#5)。单次非零→正常继续迭代, 不警告。
22. **自动化模式自我应用** (v3.9.10, v4.7.7): 从5源提取的自动化模式不能只文档化——必须实际应用于code-shiniyaya自身的迭代流程。已提取但未应用=伪优化。每轮迭代必须至少将1个提取的自动化模式实际集成到当前工作流中(不仅仅是写入SKILL.md文本)。已应用模式台账见`memory/applied-patterns.md`(v4.7.7从本条移出——台账属CHANGELOG性质, 不属规则文本)。待激活: GOTO/ABORT类型化返回值在迭代主循环中的实际路由——已定义(§Agent终端信号协议)但迭代循环仍以文本TERMINAL解析为主。
23. **防卡顿并行启动** (v3.9.19): 所有Agent在单一planar并行块中启动(`Promise.all`), 不使用`pipeline()`, 不使用`phase()`门控。这避免了phase gate阻塞问题——一个慢agent不会阻止其他阶段的agent启动。交叉验证/修复/benchmark/bug扫描等后续步骤在20扫描Agent全部返回后串联执行(使用`await`), 但不使用phase门控。
24. **收敛阈值自调整** (v3.9.23, v4.7.8增补第二信号+干净轮计数器): 若迭代#N扫描发现数<5且连续2轮<10且均为P1/P2(无P0)→已接近收敛, 触发最终50 Agent验证确认。若50 Agent确认P0=0→目标达成, 写入memory/goal-reached.md。不必严格到零——剩余P1/P2可在后续维护迭代中处理。**内容重合度第二信号**(Semantic Early-Stopping无embedding降级版): overlap=|R_n∩R_{n-1}|/|R_n∪R_{n-1}|, 发现键=file:line(±5行, 同config.json line_tolerance)+严重度; 连续2轮≥80%且P0=0→视同"连续2轮零新发现"——防止Agent非确定性导致发现计数波动时的收敛误判(两轮各N个发现但全为同一批≠未收敛)。计算: 两轮报告发现键排序比对, 零外部依赖。`# ponytail: 词法代理语义, ceiling: 大幅改写+行号大漂移逃逸, upgrade: CC暴露embedding API时替换为嵌入余弦`
**干净轮计数器** (v4.7.8, 防过早停止——修复自身实证bug): 干净轮=本轮扫描返回0 P0+0 P1**且本轮未应用任何修复**。修复轮永不计为干净轮——修复本身可能引入新bug(v4.7.8实证×2: R1修复引入bearings未注册P0, R1修复引入deny档ReferenceError P0, 均由下一轮扫描才发现)。任何修复应用→干净轮计数器清零→下一轮必须重新扫描。收敛宣布前强制自查: 干净轮计数≥2? 否→输出"第N轮: 干净轮i/2→继", 不宣布收敛。"发现已全部修复"≠"收敛达成"。**计数器<2时: 干净轮不是空闲态——等同发现P0: 强制启动下轮扫描(同turn预发射; 预发射失败→进度行+"继"; 恢复路径见§一字恢复-恢复决策分支①)。启动扫描即唯一动作——但"跳过分析门控"永不豁免以下三个启动前硬门: (i)饱和检查 (ii)预算检查 (iii)在飞检查。**
**干净轮前置条件** (v4.7.8): 本轮扫描Agent按自检#6规格全部成功返回(失败/TIMED_OUT槽位经规则7处理后再计); scan-state `scannedFiles`与上轮重叠<80% 或显式标注"轮换空间已尽", 否则该轮不计(覆盖盲区→自检#15轮换排空检测); 计入前hooks.test.js 17/17通过+agent-lint分数不降(机器证据附进度行)。"无结果到达"≠"0发现"——预发射批次死亡(API错误/无TERMINAL)→该轮不计数, 按item 7报告失败+规则7重启该批。
**预发射预算守卫**: 启动前查agent_launches余额——剩余<整轮规格(20)→不启动、不缩规模(自检#6禁缩), 走预算耗尽路径: 写FINAL-STATUS.md+输出"第N轮: 预算X/50不足下轮→停", 等24h重置或用户显式追加。BREAK_GLASS仅资助P0修复, 永不资助扫描轮启动。
**饱和优先线**: 上下文≥55%→饱和流程覆盖强制扫描/预发射/分支①启动——保存snapshot(nextAction=scan)+输出"⚡ 第N轮: 干净轮i/2 — /compact + 继", 扫描推迟至压缩后"继"恢复(分支①在新上下文启动)。
计数器持久化: 随每份snapshot落盘(格式"干净轮i/2"); 恢复时缺失/不可辨→按0处理(安全方向: 宁多扫一轮, 不误宣收敛)。
**turn-end统一决策** (v4.7.8, 权威——in-turn与"继"恢复共用, 消除双规范分叉): ①pending非空→继续修复; ②否则干净轮<2→启动下一轮扫描; ③否则未跑最终验证→启动50 Agent最终验证; ④50 Agent确认P0=0→写goal-reached→签收单→停。修复应用→干净轮清零→回②。§一字恢复三分支=本决策的nextAction快捷入口, 冲突时以本决策为准。
25. **Fast-fail内联守卫 + 预热排除** (v4.2.0, 从autoresearch train.py L570-572+step>10守卫): 运行中关键指标(如loss/错误率/token消耗)必须内联检查——不委托Agent、不等事后分析。异常值(NaN/超出阈值)立即abort+写ERRORS.md。前N步(预热期, N=10或5%总预算)不计入统计和预算消耗——防止冷启动误判。适用场景: 工作流连续3次同类型失败、token消耗率>90%、P0发现率连续上升。实现: 每个工作流完成后CC内联检查关键指标→任何一项触发阈值→立即切换策略(同规模不同Agent类型组合)→不等待、不汇报。

26. **无意义输出循环阻断** (v4.6.9, 最高优先级, HARD ENFORCEMENT):

**每个工具调用前必须执行阻断检查。这不是事后建议——这是工具调用前的硬性门控。**

CC必须在调用任何工具(Read/Grep/Bash/Write/Edit)前，对照调用栈缓存(最后15次工具调用记录)执行以下检查:

**(a) Read阻断**: 同一file+同一offset(±5行)→第2次调用前阻断。Read已缓存内容→阻断。
**(b) Grep阻断**: 同一pattern+同一path→第2次调用前阻断。Grep结果已在上下文中→阻断。
**(c) Bash wc -l阻断**: 同一file的wc -l→第2次调用前阻断。行数已知→阻断。
**(d) 确认词输出阻断**: 上个turn输出含done/final/complete/verified/confirmed且无Write/Edit/Agent启动→本次turn开始前阻断全部操作。
**(e) Write↔Read done循环阻断** (v4.7.5 降级为尽力而为): CC在同一个turn内跟踪done文件的Write/Read——若同一turn内出现Write done→Read done≥3次→阻断。跨turn的Write→Read→Write循环: 规则26无法检测（需要跨turn持久状态，CC架构不支持），由L3(一字恢复)承接——用户"继"触发恢复时自然打断循环。
`# ponytail: 规则26(e)跨turn部分无法执行(需要跨turn状态追踪 v4.6.10审计已确认)，ceiling: 同turn内检测，upgrade: CC支持跨turn状态时`

**阻断结果**: 阻断=(a)-(d)及(e)同turn部分执行阻断检查→任一触发→不执行工具调用，本轮到此结束。输出:"⚡ 阻断: {触发项}。下一条消息时重置。"。用户可见阻断原因，非静默失败。(d)例外: 用户新指令到达=重置——不阻断新任务的合法首次操作(含"继"恢复所需的Read)。

### 迭代自检 (v4.2.6-v4.7.8)

每次工作流完成通知到达时, CC尽力执行以下自检——标记NON-VIABLE的项(因CC架构限制无法自主执行)依赖用户"继"触发恢复后补充检查。未通过则修复行为+重启动:
1. **工作流完成通知=继续信号, 用户可见消息=停止** (v4.7.5 标记NON-VIABLE): task-notification跨turn自主处理不可行(CC无自主通知处理能力)。降级替代: 用户"继"触发恢复→CC读取最近journal.jsonl→提取问题→应用修复→同turn内启动下一轮。CC若写了分析/汇报/状态文本→已违反规则15, 已停止。CC只能在(a)达标停止确认 (b)致命错误无法继续 (c)用户显式要求报告 (d)规则15要求的同turn结束进度行("第N轮: X→Y→继", X/Y可含单位词如"X个发现"; 干净轮变体"第N轮: 干净轮i/2→继"同属此例外; [dim]维度标注变体"第N轮[dim]: X→Y→继"同属此例外) (e)规则18允许的对普通用户消息的简短回答(≤3行) 这四种情况下输出用户可见消息。
   `# ponytail: 自检#1依赖task-notification自主处理(不可行 v4.6.10审计)，ceiling: 用户"继"→读取journal.jsonl→恢复，upgrade: CC自主通知处理时`
2. **不等待检查** (v4.7.5 降级): CC是否在等用户回复才继续? 若当前turn内可继续→立即处理结果+继续。若turn已结束→输出"第N轮: X→Y→继"→等用户"继"恢复。`# ponytail: 自检#2跨turn依赖用户"继"恢复，ceiling: 同turn内连续处理+跨turn一字恢复，upgrade: CC支持turn边界自动检测时`
3. **不静默检查** (v4.7.5 标记NON-VIABLE): CC是否在工作流完成后退出了? 若退出→等用户"继"触发恢复→读取最后journal.jsonl+应用修复+启动下一轮。`# ponytail: 自检#3依赖跨turn自主重启(不可行 v4.6.10审计)，ceiling: 用户"继"→读取journal.jsonl→恢复，upgrade: CC支持SessionStart hook自动检测退出状态时`
4. **工作流存活检查** (v4.7.5 标记NON-VIABLE): 上一个工作流是否被kill/崩溃/超时? 若崩溃→等用户"继"恢复时解析journal.jsonl标记TIMED_OUT/KILLED的部分结果→仅重跑失败维度。`# ponytail: 自检#4依赖自主进程终止检测(不可行 v4.6.10审计)，ceiling: 用户"继"恢复时解析journal.jsonl部分结果→仅重跑失败维度，upgrade: CC支持进程存活检测API时`

5. **有意义迭代检查** (v3.9.0, v4.3.3 #5收敛卫士): 每轮迭代前后对比: (a) CRITICAL数是否下降? (b) 新发现是否为全新类别(非重复)? (c) 5源文件利用深度是否增加(深入之前未读的文件/函数/模式)? 若连续2轮无新类别发现+CRITICAL不变→停止当前策略, 切到5源文件中未充分利用的部分。禁止同一维度同一文件反复扫描无产出——每次扫描必须比上一轮深入新文件或新维度。**若已满足规则24收敛前置条件(发现数<5且连续2轮<10且均为P1/P2无P0)→跳过策略切换, 直接触发50 Agent最终验证确认**——防止低发现数时CR自然低导致误触发。
6. **任务保真检查** (v3.9.0, v4.7.7同步规格): 迭代中的每一步必须匹配§迭代任务定义——20 Agent × 5源(每源4 Agent, 10维度轮换) → 应用修复 → 基准测试门控(流水线5 Agent vs 单体1 Agent) → 8 Agent bug扫描(Read→Analyze→Report管线)。不得将20 Agent缩小为4/8 Agent简单扫描, 不得跳过基准测试门控, 不得减少源数(必须5源), 不得缩小bug扫描规模(必须8 Agent)。若上一步偏离原始设定→立即纠正+用正确规模重跑, 不等待用户指出。

7. **工作流时间预算检查** (v3.9.0): 若连续3个工作流因脚本bug(非Agent超时)崩溃→停止使用含后处理代码的工作流, 改用纯agent()调用+CC直接处理结果。`'P0' in l`对字符串迭代字符是已知的脚本语法错误——任何后处理中只能用`String(r).split('\n')`迭代行, 不能用`for l in String(r)`迭代字符。

8. **元迭代完整性检查** (v3.9.0): 每次完成一轮完整迭代(扫描→修复→基准→bug扫描)后, CC必须自检本轮迭代是否提升了以下能力的稳定性: (a) 任务持续进行不中断—本轮是否有≥1次无故停顿? (b) 任务规模不偏离—Agent数量/维度数/门控是否与原始设定一致? (c) 修复效率—同类型bug是否重复出现(代表修复未根除)? (d) 防挂起—工作流是否因脚本bug崩溃? 若任何一项未通过→将该能力缺口作为优化目标写入memory, 下一轮迭代的20 Agent扫描维度中新增一维专门扫描该缺口。写入位置: `memory/meta-iteration-quality.md`, 追加本轮评分+缺口+下轮改进措施。

9. **稳定性积累检查** (v3.9.0): 每次迭代的修复必须同时包含: (a) SKILL.md内容bug修复, (b) 迭代流程本身的稳定性修复(防中断/防偏离/防缩小)。两者不可偏废——只修复内容不修复流程会积累流程债, 导致后续再次中断。若本轮只修复了内容未修复流程→流程修复优先, 内容修复排后。

10. **任务规格锁定 + zero-drift活文档** (v3.9.0, v4.7.8): 原始迭代任务规格已写入memory/iteration-task.md——此文件是任务地面真相, 任何偏离=致命违规。(a)iteration-task.md必须是**活文档**——规格变更(如4源→5源)时同步更新规格块, 历史记录移入附录; 陈旧地面真相=反向漂移源。(b)不止启动时读——每完成一个STEP或每5turn重读规格块re-anchor。(c)规则15进度行点名当前维度: "第N轮[维度名]: X→Y→继"。
`# ponytail: (b)为L1文本规则——drift发生在正常认知期(非吸引子劫持期), L1对drift有效, ceiling: 模型自觉, upgrade: PostToolUse additionalContext自动注入规格摘要时`

11. **工作流Agent卡住处理** (v3.9.0, v4.7.5 标记NON-VIABLE): 若Pipeline中某Agent超时未返回(同批其他Agent均完成, 差距>5分钟)→CC自动TaskStop该工作流→解析journal.jsonl→仅重跑未完成维度(最多2次/维度)。不写用户可见分析, 不等待用户, 不汇报。
   `# ponytail: 墙钟超时检测不可行(CC无wall-clock监控能力 v4.6.10审计)，ceiling: 基于turn的替代方案(同一turn内3+ Agent完成且某Agent落后→等待自然超时→事后恢复)，upgrade: CC支持Agent进度事件流时`

12. **5源深度利用检查** (v3.9.0, v4.7.7增补ponytail): 5个开源项目的价值不仅在于模式提取, 更在于它们展示了如何实现自我迭代/自动化接管/持续优化的完整机制。每轮扫描必须深入这些项目的核心自动化能力:(a) AutoAgent的flow/dynamic.py—事件驱动+GOTO/ABORT控制流, flow/core.py—listen_group依赖声明, main.py—3层重试+元Agent升级, constant.py—环境变量特征检测。(b) autodream的auto_dream.py—Learn+Consolidate双重反思, checksum幂等写入, MAX_*上限常量系统, 向量记忆同步。(c) autoresearch的program.md—NEVER STOP指令, Git状态机, TSV结果日志, 崩溃分类法, 固定预算。(d) autonomous-coding的agent.py—Init+Loop两阶段, 不可变检查清单, auto-continue延迟, 轨迹记录, 三层安全模型。(e) ponytail的七步阶梯/selftest双层门控/hooks生命周期/judge基准。这些能力是code-shiniyaya自我迭代的蓝本——每次迭代必须至少从2个项目中提取"如何自动化自身"的模式并写入SKILL.md。仅提取静态代码质量模式=未充分利用源文件。

13. **产出物写入检查**: 每次迭代的产出(报告/计划/记忆)必须写入正确的目录: (a) 报告路径见规则27, (b) 记忆→`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\`, (c) 优化计划→`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\optimization-plan.md`。写入错误路径=违规, 立即纠正。

14. **5源自我迭代能力提取检查** (v3.9.1, v4.7.7增补ponytail): 5源的核心价值=展示"AI如何自动化自身"。每轮20 Agent扫描必须包含以下5个维度的深度挖掘: (a) 事件驱动自动化—AutoAgent的GOTO/ABORT/listen_group/transfer_back, (b) 记忆驱动反思—autodream的Learn+Consolidate/向量同步/孤儿检测, (c) 自主连续性—autoresearch的NEVER STOP/固定预算/崩溃自分类, (d) 两阶段执行—autonomous-coding的Init+Loop/不可变清单/ThinkTool, (e) 极简自验证—ponytail的selftest门控/judge裁判/debt账本。仅提取表层模式(如截断/上限)=浪费源文件价值。每轮迭代结束时检查: 本轮是否从至少2个源中提取了"自动化自身"的模式并写入SKILL.md?

15. **源文件旋转利用检查** (v3.9.1): 禁止连续2轮扫描同一源文件的同一段代码。每轮必须轮换: (a) 从未读文件列表中选取新文件, (b) 从已读文件中选取之前未扫描的函数/段落, (c) 交叉配对——2个源的2个不同函数组合形成新对比维度。未读文件列表见memory/iteration-task.md每个源底部的"未扫描文件"条目。

16. **报告路径一致性检查** (v3.9.1): 报告路径见规则27。写入前检查路径存在(不存在→mkdir创建)。禁止写入 `C:\Users\shiniyaya\Desktop\报告\`(旧路径, 已废弃)。若上一轮产出写入错误路径→立即移动到正确路径+更新所有引用。

17. **防卡死检查** (v4.6.1, 规则26优先): CC在迭代循环中自动检查自身行为——连续3次相同Write操作(同文件+同内容)→触发卡死。连续3轮迭代产生相同发现(相同file:line+描述)→触发重复。连续输出"done"/"final"/"complete"等无实质变更→触发等待陷阱。**规则26(无意义输出循环阻断)优先于此自检执行**——先阻断无意义输出，再执行自检纠正。触发后切换策略(Agent类型/维度/源文件)，若仍无进展→暂停+等用户指令。每次操作必须产生可验证的新进展。纠正动作不计入重试配额。

18. **死循环根因阻断** (v4.6.9, v4.7.5 降级为部分可行, v4.7.8 Bash层hook承接): CC在同turn内追踪最后10个工具调用。(a)同turn内Read-Grep-Read同信息≥2次→阻断(可行); (b)同turn内Write done→Read done→Write done≥3次→阻断(可行); (c)跨turn连续3次输出无≥1新信息→阻断(模型侧不可行——需要跨turn内容hash比对，CC每turn fresh context); (d)跨turn输出内容hash与上次相同度>80%且无Write/Edit→阻断(模型侧不可行——同(c))。可行项(a)(b)阻断→写DEAD_LOOP_LOG.md→切换策略→等用户。不可行项(c)(d): Bash层重复命令子集由echo-guard v3跨turn指纹覆盖, 纯确认turn由stop-guard拦截(§外部看门狗); 其余由一字恢复(L3)承接——用户"继"恢复时自然打断循环。
   `# ponytail: 自检#18(c)(d)模型侧不可行(需跨turn持久状态)，ceiling: 同turn内(a)(b)+Bash层echo-guard v3指纹(跨turn)+stop-guard turn终态，upgrade: CC支持跨turn状态时`

19. **消毒流水线合规检查** (v4.7.7): STEP 3产出FOR_CODEX文本前自查规则28消毒6步已应用(Bidi→NFKC→零宽→Null→C0/C1→围栏转义); STEP 4解析Codex手动粘贴回复前对粘贴内容执行同一流水线(防Codex回复携带控制序列注入)。插件JSON-RPC直传内容豁免第6步(围栏转义)但1-5步字符消毒仍适用。

20. **7方向覆盖检查** (v4.7.7, 规则17执行器): 每轮迭代结束时确认规则17的7大优化方向(持续性/保真性/有意义性/稳定性/5源深度利用/自我迭代/报告规范)本轮各有≥1项动作或显式"本轮无适用项"标注。缺失方向→下轮扫描维度补入。同时确认Agent启动提示词含输出格式示例+必填字段清单(反模式6执行器)。

标记NON-VIABLE的自检项(#1/#3/#4/#11)依赖用户触发恢复后补充检查——不可自纠正。其余可行自检项违反时=立即自纠正。

### 交付 (v4.6.9 统一编号: 规则27-28)
27. **报告路径(权威定义)**: 所有报告→`C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\iteration-reports\iter-{N}\`。交叉验证报告/基准测试报告/bug扫描报告/优化计划均写入此路径。CODE_SHINIYAYA_REPORT_DIR可覆盖根路径(默认=`C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\`)。自检#13和#16引用此处路径定义。
28. **Codex消息可复制**: 纯文本, `=`分隔, 无Markdown表格, 中文+术语。用 `-->` 不用 `→`。用户提供内容消毒后嵌入(转义 ``` 围栏, 不允许Codex控制序列)。CC从源文件读取并嵌入的内容也需经过相同消毒流水线(Bidi移除→NFKC→零宽→Null→C0/C1控制字符)。

## 反模式 (24个)

| # | 反模式 | 症状 | 正确做法 |
|---|--------|------|---------|
| 1 | Plan-Code Gap | 报告已修复但行号偏移≥±10/改了不同函数 | `git diff --stat`+`grep -n` |
| 2 | 共享文件争用 | 两Agent同写一个文件 | 串行执行; CC自保(共享文件检测+串行排队) |
| 3 | 批次膨胀 | >16 Agent并发→超时 | batch_size硬上限 |
| 4 | 静默失败 | Agent报成功但源码未变 | 错误→ERRORS.md+通知 |
| 5 | 上下文饥渴 | Agent零Skill裸跑 | 至少1 Skill/Agent |
| 6 | 模糊提示词 | 无结构化输出, 无file:line | 扁平化标准提示词(单段, 含必填字段) |
| 7 | 单Agent盲信 | 1 Agent→通过 | 最少6交叉验证 |
| 8 | 跳过Read直接写 | 基于过期假设修改 | Write/Edit前Read |
| 9 | Codex自我验证盲信 | Codex说"已修复"/"approved"→CC跳过验证 | 必须独立验证每项Codex批准+拒绝 |
| 10 | 迭代静默停止 (v3.9.0, v4.7.7降级) | 工作流完成后CC无输出不继续 | 同turn内可继续→立即处理+继续; turn已结束→输出进度行"第N轮: X→Y→继"+等用户"继"(规则15) |
| 11 | **迭代范围漂移** (v3.9.0) | Agent数量逐轮缩小(20→8→4→2), 维度减少, 基准测试被跳过 | 自检#6: 每次启动前验证Agent数≥原始定义 |
| 12 | **流程稳定性忽视** (v3.9.0) | 只修复内容bug, 不修复流程本身的稳定性问题 | 自检#8+#9: 流程修复优先于内容修复 |
| 13 | **自适应降级** (v3.9.0) | 工作流连续失败→CC自动缩小规模"适应"→偏离设定 | 规模不可缩小, 修复bug后同规模重跑 |
| 14 | **输出即停止** (v3.9.0, v4.7.7降级) | 工作流完成后CC写长篇分析/汇报→已停止迭代 | 允许的用户可见输出仅限自检#1例外(a)-(d)(达标签收单/致命错误/用户要求报告/进度行); 长篇分析→写入报告文件而非对话 |
| 15 | **等待幻觉** (v3.9.0, v4.7.7降级) | CC持续轮询工作流进度并写可见输出→每轮检查=一次停止 | 同turn内: task-notification到达时处理, 不主动轮询; 跨turn: 等用户"继"(自检#1 NON-VIABLE降级) |
| 16 | **无意义重复** (v3.9.0) | 连续多轮扫描同一文件同一维度→无新发现 | 自检#5: 连续2轮无新类别→切到未读文件+新维度 |
| 17 | **5源模式浅层利用** (v3.9.1, v4.7.7更名) | 只提取截断/上限等表层模式, 忽略GOTO/ABORT/Learn+Consolidate等自动化能力 | 自检#12+#14: 每轮至少从2个源提取自动化模式 |
| 18 | **产出路径散落** (v3.9.1) | 报告写入错误目录 | 自检#16: 写入前验证路径=code-shiniyaya/报告/ |
| 19 | **源文件重复扫描** (v3.9.1) | 连续多轮扫描core.py/main.py同一段, 未利用dynamic.py/history_util.py等 | 自检#15: 每轮轮换, memory/iteration-task.md跟踪 |
| 20 | **自我迭代能力未提升** (v3.9.1) | 每轮只修复SKILL.md内容, 不提升code-shiniyaya自身的自动化水平 | 自检#12+#14: 每轮至少从2个源提取一个自动化模式。已实现: Terminal+3层重试+Init+Loop+崩溃分类+无阶段门控; 待实现: 声明式事件依赖+完成信号工具调用 |
| 21 | **阶段门控卡死** (v3.9.21) | pipeline()和phase()调用导致后续阶段block在慢agent上, cross-validate/bug-scan agent超时卡死 | 所有agent用单一Promise.all并发块启动, 不用pipeline(), 不用phase()。交叉验证直接提取P0结果不委托单独agent。bug扫描与20扫描agent同一并发块运行 |
| 22 | **预热期计入预算/统计** (v4.2.0, train.py L578+step>10守卫) | 前N步(编译/缓存预热)的高延迟/低效率被计入性能统计, 产生虚假低效警报 | 前10步(或5%总预算)的耗时/错误率不计入统计和预算消耗。step>10后才开始累计total_training_time等指标 |
| 23 | **隐式步骤依赖** (v4.2.1, workflow_former.py listen_group, 规范级——运行时以串行await为实际机制, 见§可运行边界) | 工作流步骤间的依赖是隐式的(串行await硬编码), 步骤不声明自己需要什么输入→依赖错乱时无法自动检测 | 每个步骤显式声明listen(依赖前序步骤的哪些输出key)和outputs(产出哪些key)。依赖未满足→步骤不启动。三模式: If-Else(互斥分支)、并行化(多步骤listen同一父级→聚合器等全部完成)、Evaluator-Optimizer(GOTO循环) |
| 24 | **Codex手动粘贴循环** (v4.7.1) | codex-plugin-cc未集成, 仍用手动复制粘贴→等待Codex回复→粘贴回CC→验证→等待→... 9步闭环中STEP 3/4/5全部依赖用户手工介入, 迭代速度受限于人类复制粘贴延迟 | 安装codex-plugin-cc: `/plugin marketplace add openai/codex-plugin-cc` → `/codex:review` 自动化STEP 4审查 → `/codex:rescue` 委派STEP 6修复 → `/codex:transfer` session持久化。回退: 插件不可用时降级手动模型 |

## 错误处理

| 步骤 | 失败模式 | 用户消息 | 恢复 |
|------|---------|---------|------|
| STEP 0 | python探测失败 | "环境探测失败" | caps全取回退值(cpu=4, tiktoken=否, git单独探测), 继续STEP 1 |
| STEP 0 | git不可用 | "git缺失→mode受限" | 禁用STEP 6.0状态机+snapshot git提交 |
| STEP 1 | Agent全超时 | "缩小范围重试" | 减文件50%, 重试 |
| STEP 1 | 个别超时 | "X/Y完成" | 每维度≥1成功; 全失败→人工审查 |
| STEP 1 | 源文件不存在 | "跳过此项" | 标无法验证, 继续 |
| STEP 1.5 | 参考源全失败 | "跳过交叉验证" | 同STEP 1源文件不存在语义, 继续STEP 2 |
| STEP 2 | 写失败(磁盘满等) | "写入失败" | 内联纯文本 |
| STEP 2 | 3 Agent方案对比全失败 | "单方案直出" | 用最小更改方案+标注未对比, 继续 |
| Pre-6.0 | DAG检测到环(A→B→A) | "依赖环" | 环内所有项标BLOCKED+用户裁决合并或排序 |
| STEP 3 | >20000 chars(~10000 tokens) | "分N部分" | P0优先, ≤10000 chars/部分, ≥3→用文件. Token-chars换算: ~2 chars/token保守估算 |
| STEP 3 | 仅状态更新 | "生成完成摘要" | 格式C |
| STEP 3 | Codex静默(连续N=4条用户消息无Codex回复) | "继续等/跳过?" | 跳过→独立验证→降级 |
| STEP 4 | Codex不可解析 | "确认完整粘贴" | 展示可解析; 全不可解析→重格式化 |
| STEP 4 | Codex 0发现 | "CC交叉验证中" | CC 6 Agent, 不一致则报告 |
| STEP 4 | 维度全失败 | "维度{dim}人工审查" | 继续其他, 记录缺失 |
| STEP 5 | 用户久未回复 | "等待批准中" | 无自动操作(规则13) |
| STEP 5 | Codex部分批准 | "执行批准项, 重做拒项" | 独立执行+重方案 |
| STEP 5 | Codex不可用(降级模式) | "Codex不可用——降级模式: 用户单批准可执行。P0双验证: CC 4 Agent(规则20)仍强制。" | 用户批准即执行; P0项仍需CC 4 Agent独立验证(规则20); STEP 7降级为CC 6+ Agent自我验证 |
| STEP 6 | 单文件失败 | "跳过, 继续" | FAILED_FIXES.md, 继续; 依赖项→BLOCKED |
| STEP 6 | 3次同文件 | "STOP" | STOP_LOG.md, 等用户 |
| STEP 7 | Codex超时(连续N=4条消息无回复) | "CC先行验证" | CC 6+ Agent独立验证, 不等 |
| 迭代扫描(workflow) | Agent卡住(>300s)/工作流崩溃 | "工作流异常" | 解析journal.jsonl部分结果, 仅重跑失败slot |
| ANY | TERMINAL: GOTO接收 | "跳转到STEP {N}" | 保留触发Agent结果; 其余Agent标ABORTED; 若STEP 6期间→git stash; GOTO目标不存在→回退STEP 1 |
| ANY | TERMINAL: ABORT_BRANCH接收 | "分支 {name} 已中止" | 分支部分结果保存到ABORTED_BRANCHES.md; 被阻塞项标ORPHANED(用户审查) |
| ANY | TERMINAL: UNRESOLVED/RESOLVED/PARTIAL | 按信号类型 | RESOLVED→正常流程; UNRESOLVED→规则7替换; PARTIAL→排队补全 |
| ANY | 无TERMINAL行+无工具调用 | "Agent无响应" | 标记TIMED_OUT, 触发规则7 |
| ANY | case_resolved/case_not_resolved同时调用 | "Agent矛盾信号" | 标记UNRESOLVED, 触发规则7替换逻辑 |
| STEP 8 Learn | DirtyJson解析失败/LLM输出无JSON | "反思结果不可解析" | 原始LLM输出写learn-parse-error-{ts}.json; P0/P1发现内联写MEMORY.md |
| STEP 8 Consolidate | MD5冲突/合并失败 | "Consolidate部分完成" | 写consolidate-conflict-{ts}.json+差异; 保留原始记忆文件不变; 增量修复不全局回滚 |
| 预算监控 | 消耗率>90%含BREAK_GLASS | "预算耗尽" | 暂停迭代(规则15例外d), 写FINAL-STATUS.md; 24h后重置续跑 |
| 预算监控 | 消耗率50-90% | 按级降级 | 50-75%→日志警告+P2降级; 75-90%→停止新P2+P1限1次; >90%→仅P0, P0修复按规则20验证(非降级2 Agent/降级4 Agent), P1/P2延迟到backlog |
| STEP 4降级 | Codex插件不可用或N=5超时 | "Codex超时→降级" | N=5超时→先试插件路由(`/codex:status`探测); 插件也不可用→STEP 4中止, 跳转STEP 5降级路径(用户单批准; P0 4 Agent验证) |
| STEP 5 | 用户拒绝方案("不批准"/"拒绝") | "方案被拒" | 记录拒绝理由→回STEP 2重方案(重走双批准) |
| STEP 1 | 用户否决Bug列表 | "列表被否" | 标注误报项→按反馈重扫争议维度→重新确认 |
| 预算监控 | budget JSON checksum不匹配 | "预算文件损坏" | 保守恢复: 按>90%已消耗处理(仅P0档——预算保守上限, 安全默认), 直至用户确认重置 |
| STEP 8 | 反思日志写失败 | "反思日志失败" | 摘要内联追加到CHANGELOG.md, 不阻塞 |
| STEP 8 | 反思排队槽满(槽位=1) | — | 丢弃第2个排队反思+计数, 下次门控触发时补偿(计数不清零) |
| STEP 6降级 | 用户单批准后执行(降级模式) | 按降级条款 | 同STEP 5降级→单批准→执行; P0仍需4 Agent |
| STEP 8降级 | 反思阶段Codex不可用 | 降级反思 | 仅提取CC来源模式; 跳过Codex交叉引用依赖; 降级标注写入反思日志 |
| 任意 | 自主模式下DISPUTED(第2轮双向仍有争议) | "CC 4 Agent仲裁(规则20)" | 规则20规定的4 Agent多数投票; 2:2平局→采纳CC方案(源码访问权优势) |

## 状态文件 (JSON, 会话隔离, 原子写入)

**路径**: `{project_root}/.claude/memory/code-shiniyaya/` (运行时产物——状态文件/校验和/会话JSON。非用户可读内容)
**报告路径**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\` (规则27强制, CODE_SHINIYAYA_REPORT_DIR可覆盖根路径)。迭代报告写入子目录 `iteration-reports\iter-{N}`, FOR_CODEX文件写入根目录。

### 会话状态 (`session-{sessionId[:8]}.json`)
```json
{ "schemaVersion": "3.9.0", "sessionId": "...", "step": 1, "itemStates": {},
  "mode": "normal|degraded", "degradedAt": "", "silentMsgCount": 0, "waitRounds": 0,
  "versionVector": 0,
  "workflow_context_snapshot": {},
  "checksum": "" }
```
`itemStates`: {"bug-id": {"status": "...", "substep": "..."}, ...}——每项独立追踪, key=bug-id, value含status+substep。替代单一itemIndex。
`checksum`: SHA-256(key排序JSON, 排除此字段, UTF-8, 无空格)。嵌套对象(itemStates, edges)递归key排序。读取时: 读入内存→剥离checksum→计算→对比。不匹配→`.corrupt.{ts}.json`+通知。

### 待修复项 (`pending-{sessionId[:8]}.json`)
```json
{ "schemaVersion": "3.9.0", "items": [],
  "checksum": "" }
```
`items[]`: each with id, severity, root_cause, status, blockedBy, blocks, file, line, deps, substep, lastFileHash, originalSnapshot。`lastFileHash`: STEP 6 Write成功时记录目标文件SHA-256, 恢复时重计算对比。`originalSnapshot`: STEP 6修复前set-once存储原文件内容(仅git不可用时填充, ≤50KB), 供回滚写回。
**不可变契约**: 创建后 `id`/`file`/`severity`/`root_cause` 不可修改(与Init+Loop两阶段模型中的不可变检查清单一致, 见迭代扫描工作流-Init+Loop)。仅 `status`/`substep`/`lastFileHash`/`originalSnapshot`(set-once) 可写。修复中若发现根因错误→标记DISPUTED, 创建新pending项, 原项保留(含原file/severity/root_cause)。永远禁止删除pending项或修改诊断信息。违反此契约=灾难性操作(CATASTROPHIC)。

### DAG (`dag-{sessionId[:8]}.json`)
```json
{ "schemaVersion": "3.9.0", "edges": [], "files": {}, "snapshot": "", "checksum": "" }
```
`snapshot`: `git rev-parse HEAD`。恢复时不匹配→重建DAG。

### 原子写入协议
1. 序列化JSON到 `.tmp.{sessionId[:8]}.{ts}`。序列化失败→立即中止。
2. flush + fsync。fsync失败→重试1次(100ms)→仍失败→保留tmp文件在磁盘, 通知用户tmp路径, 不写任何额外文件(磁盘可能已满)。当前target仍为上版本(os.replace保证失败时target不变)。
3. `os.replace(tmp, target)` (原子——在POSIX上是rename原子操作; Windows上Python 3.3+的os.replace内部调用MoveFileEx+替换标志, 语义上等价为原子替换。借用prepare.py L75 download_single_shard函数内的temp+rename模式)。失败→tmp文件保留, 通知用户路径, 当前target仍为上版本(由os.replace保证: 失败时target不变)。
4. 读取: 读前先复制target到内存→计算SHA-256(排除checksum字段, key排序, UTF-8, 无空格)→不匹配→写 `.corrupt.{ts}.json` 副本+通知。匹配→使用内存副本, 不重读文件。
5. 旧版Markdown(v2.x): 仅读, 迁移到JSON, 不删旧版。

### 会话隔离
- `{sessionId[:8]}` 文件名——并发会话不会争用, 碰撞概率: 65K 并发会话时生日悖论达 50%, 实际操作中可忽略
- 读取-写入-版本比对(versionVector: 单调递增整数, 每次写入+1, 持久化于会话JSON的versionVector可选字段——仅在多进程并发写入时使用): 磁盘versionVector与读取时一致→写入; 不一致→冲突→ `.conflict.{ts}.json` + 通知用户
- **已知限制** (v4.7.7): snapshot文件名为`snapshot-{ts}.md`(无sessionId)——并发会话共享snapshot命名空间, "继"恢复取全局最新, 可能续取另一会话任务。单会话使用(实际主导场景)无影响。`# ponytail: snapshot无会话隔离, ceiling: ls|tail -1全局最新, upgrade: 并发会话成为常态时改snapshot-{sessionId[:8]}-{ts}.md`

### Git分支隔离 (STEP 6.0修复执行模式)

对于使用Git状态机模式的修复会话(STEP 6.0), 用git分支替代文件名会话ID:

- **分支命名**: `fixes/{sessionId[:8]}` — git强制唯一性。`git rev-parse --verify` 提前检查碰撞。
- **并行会话**: 每个CC会话 = 一个分支。零碰撞风险(由git而非checksum保证)。
- **恢复**: 分支状态即已提交的修复状态。无需 `lastFileHash` 重算——git对象是内容寻址的。
- **清理**: 合并后删除分支。未解决的分支保留作为审计轨迹。
- **tradeoff**: 仅适用于无共享文件的独立修复。跨文件依赖修复仍用文件名会话ID(传统隔离)。

### 修复预算 (`budget-{sessionId[:8]}.json`) (v4.0.0)

```json
{
  "schemaVersion": "4.0.0",
  "total": {"agent_launches": 50, "fix_attempts_per_bug": 5, "message_rounds": 200, "plugin_calls": 20},
  "consumed": {"agent_launches": 12, "fix_attempts": {"B1": 2, "B2": 1}, "message_rounds": 45, "plugin_calls": 3},
  "by_severity": {
    "P0": {"budget_pct": 60, "consumed": 8},
    "P1": {"budget_pct": 30, "consumed": 4},
    "P2": {"budget_pct": 10, "consumed": 0}
  },
  "checksum": ""
}
```

| 消耗率 | 动作 | 备注 |
|--------|------|------|
| <50% | 正常 | — |
| 50-75% | 日志警告, P2 降级 | — |
| 75-90% | 停止新 P2, P1 限制 1 次尝试 | — |
| >90% | 仅 P0, P0修复按规则20验证(非降级2 Agent/降级4 Agent), P1/P2延迟到backlog | — |
| Tier 2规格 | 每修复2次agent+交叉验证investigator+general-purpose | 仅非P0修复。P0仍须规则20 |
| >90%+BREAK_GLASS | 预算完全耗尽(含BREAK_GLASS) | 停止迭代(规则15例外d), 写FINAL-STATUS.md。预算每24小时重置 |

降级模式: P0 预算从 60% 增加到 80% (CC 自我验证更昂贵)。预算消耗 >90% 且 Codex 不可用: BREAK_GLASS 允许超支 10%, 仅 P0。自主迭代模式下: Codex降级不依赖用户消息计数——连续3个工作流完成周期(task-notification)内无Codex回复→自动降级。自主模式下DISPUTED→CC 4 Agent仲裁(规则20规定的investigator+general-purpose+Plan+debugging), 多数投票; 2:2平局→采纳CC方案。
`# ponytail: 墙钟时间盒来自autoresearch TIME_BUDGET模式(program.md:23,108)，ceiling: echo-guard.js 8次Bash/turn上限 + Agent工具基础设施自带超时(非hook职责)，upgrade: CC支持子进程信号时`
**墙钟时间盒** (v4.7.6, v4.7.7诚实修正): 每次迭代工作流设固定墙钟上限——超时终止+写入TIMEOUT_LOG.md。防止无限等待Agent返回（自检#11 NON-VIABLE的补偿方案）。**执行主体=外部hook/Agent工具基础设施, 非模型自查**（模型无墙钟监控能力, 见§运行时可行性审计）: Agent工具自带超时由CC平台强制; 单Bug 300s/工作流600s上限=规范级指引, TIMEOUT_LOG.md由观察到超时的下一个turn补写。hook未安装→时间盒不生效, 回退消息计数阈值(N=4/N=5)。


## 核心工作流: STEP 0-8闭环 (9步, 含冷启动STEP 0)

**入口路由 (每次触发)**

```
触发 → 路由 (短语匹配优先于状态匹配):
  ├─ stop/中断/CTRL+C → 停止线优先于所有路由
  ├─ 恢复触发词("继"/"继续执行"/"继续修复"等) → 详见§一字恢复触发词表(行159-166)
  ├─ "告诉codex" (A类) → 有方案→STEP 3; 无方案→STEP 2+提示"先生成方案"
  ├─ 用户粘贴Codex回复 → STEP 4(检查mode: normal=正常验证, degraded=提取新发现但不等批准)
  ├─ "批准"/"执行" (D类) → STEP 5(mode: normal=双批准, degraded=用户单批准)
  ├─ "方案审批"/"修复方案审批" (E类) → STEP 5; "多方案对比" (E类) → STEP 2多方案分支
  ├─ B/C/F类(验证/协作/AI通用) → 状态路由: 无诊断→STEP 0→1; 有诊断无方案→STEP 2; 有方案→STEP 3
  ├─ G类(全量): "全量扫描"/"full scan" → STEP 0→1 全库扫描规格(40+ Agent, 分批≤batch_size, §Agent编排)
  ├─ H类(自主迭代): "循环迭代"/"自主执行"/"优化skill"/"根据源文件优化" → §自主迭代模式
  ├─ I类(Agent错误): "agent错误"/"agent失败" → 错误诊断→Agent替换→重试(规则7)
  ├─ 无诊断 → STEP 0→1 (冷启动)
  ├─ 有诊断无方案 → STEP 2
  └─ 未识别输入(空消息/垃圾文本) → 提示用户明确意图, 不执行任何操作(安全默认: 无触发→无路由)
```

stop→路由: stop/中断/CTRL+C优先于所有路由。
静默→降级: 连续N=4条用户消息无Codex回复 → 询问"继续等/跳过?"("继续等"→不重置计数,继续向上累积; N=5→自动降级)。多部分Codex粘贴保护: 相邻消息<3s到达且以连续内容结尾→计为1条消息; 含匹配`[MSG-{4hex} i/N]`标记的粘贴→按标记判归属与完整性(权威, 见STEP 3消息关联ID), <3s启发式仅无标记时使用。"继续等"/"继续等待"→保持静默计数, 不触发恢复路由。
恢复→路由: 用户说"继续修复"→读session JSON(mode+step+itemStates)→从断点STEP+项继续。session JSON不存在→回退snapshot恢复(读最新memory/snapshot-*.md)。snapshot也不存在→冷启动STEP 0。checksum损坏→尽力读取+用户确认→继续; 或放弃→冷启动。
  └─ mode:degraded→STEP 5用户单批准; STEP 7 CC自我验证(维度: 正确性+编码安全+架构+回退)

### STEP 0 — 双Skill前置 + 环境检测 (冷启动, 尽力而为)

1. `using-superpowers` — 确认触发正确
2. `openspec-explore` — 检测项目是否存在 `openspec/` 目录+配置文件。存在→运行; 不存在→静默跳过, 不等待, 不报错, 直接继续STEP 1。
3. **环境能力检测** (v3.9.14, v4.7.7修正importlib探测): `python -c "import os, shutil, json, importlib.util; caps={'git':shutil.which('git') is not None,'python':os.cpu_count() or 4,'disk_free_gb':round(shutil.disk_usage('.').free/(1024**3),1),'tiktoken':importlib.util.find_spec('tiktoken') is not None}; print(json.dumps(caps))"`（显式`import importlib.util`——`__import__('importlib').util`在部分CPython构建上抛AttributeError, 会把整个探测拖入回退）。python本身不可用→探测失败→caps全取回退值(cpu=4, tiktoken=否, git=按`git --version`单独探测), 继续STEP 1。git不可用→禁用STEP 6.0状态机+snapshot git提交, 标注mode受限。tiktoken不可用→token计数回退字符估算。磁盘<1GB→减少报告写入。自动根据模型名称适配工具格式(AutoAgent constant.py模式: NOT_USE_FN_CALL/MUST_ADD_USER列表检测)。

### 概览

```
用户需求 → [0:双Skill+环境] → [1:诊断] → [2:方案] → "告诉codex"
→ [3:可复制文本] → [Codex回复 OR 静默>N条消息]
→ [4:10+ Agent验证] → [5:双批准门控 ⚠️阻断]
→ [6:逐项执行] → [7:双向验证] → [8:元反思] → 完成
```

**快速路径** (v4.2.6): **预验证修复→跳过1-2**: 仅在上一轮会话已完成STEP 1-2且方案完整(有session JSON且所有pending项status=PLANNED)时可用。恢复时读取上一轮session JSON→若plan字段完整→快速路径可用, 跳过诊断+方案生成, 直接进入STEP 5。若session JSON不存在或plan为空→回退冷启动STEP 0。注释/文档→跳过3-7。

**降级模式**: Codex静默→N=4→"跳过?"→触发降级。session JSON中标注 `mode: degraded, degradedAt: "<ISO8601>"`。降级后STEP 5: 用户单批准(正常项+UNREVIEWED项); P0项仍需CC 4 Agent独立验证(investigator+general-purpose+Plan+debugging, 降级模式不豁免P0双验证)。STEP 7: CC 6+ Agent自我验证。降级为用户可逆——降级不会自动回到normal模式，但用户可在Codex回归后手动说"恢复双批准"重置mode为normal。晚到Codex回复: 未执行项→STEP 4验证(提取新发现, 与CC已验证项对比), 已执行项→不重做但Codex发现记录在案供用户审查。冲突(Codex反对CC已执行项)→记录在DISPUTED_LOG.md, 用户裁决。

**中断恢复**: stop→读 `pending-{sessionId[:8]}.json`(未完成项) + `session-{sessionId[:8]}.json`(当前STEP+项索引 + mode字段)→从断点继续。恢复时 `mode: degraded` 表明无需等待Codex。

### STEP 1 — 诊断扫描 (无门控)

1. 读源文件 → 初始假设
2. 启动 6+ Agent并行(5种类型): investigator(字节), Explore(遗漏), general-purpose(逻辑+语法), Plan(架构), debugging(运行时)
   - Agent类型不可用时: 回退链 → general-purpose(通用回退)
3. 每维度≥1成功; 全失败→人工审查
4. **去重合并**: (a) group by `file:line±3`容差, (b) 组内合并→最高严重度+最完整根因+最具体修复方向, (c) 去重后计数≤唯一发现的2x
5. 相关参考源→5+ Agent扫描(STEP 1.5)
6. Bug分类: P0(崩溃/数据丢失/安全) → P1(功能缺失/性能) → P2(UX/代码质量)
7. **grep所有调用者** (v4.6.9, STEP 1内部规则7, ponytail trace-before-fix): 对每个疑似bug(在目标源码仓中), grep该函数/方法的所有调用者, 确认影响范围后再提修复方案——修补共享函数一次(one guard in shared function is smaller diff than per-caller guard, 根因修复), 不修补仅被ticket命名的路径。

**确定性预扫**(v4.7.8可选, aislop CLI): 目标仓语言∈{TS/JS/Python/Go/Rust/Ruby/PHP}时, Agent启动前先跑`npx aislop .`(亚秒纯规则, 零LLM成本)——结果按严重度注入Agent prompt, 每条计为grounding=grounded发现(evidence=规则ID+file:line, 工具输出即证据), Agent聚焦语义问题不重复机械检查。CLI不可用→跳过, 零影响。

🔴 诊断→用户确认Bug列表→STEP 2

### Agent Finding Provenance (STEP 1.4, P0强制)

每个 finding MUST 包含:

```json
{
  "severity": "P0",
  "file": "src/auth.py",
  "line": 42,
  "description": "Null pointer dereference in authenticate()",
  "grounding": "grounded",
  "evidence": "Line 42: user = get_user(); Line 43: user.name — user may be None",
  "inference_chain": null,
  "source_agent_ids": ["a1b2c3d4"],
  "source_agent_types": ["investigator"]
}
```

**grounding 取值**:
- `grounded`: 直接从源文件/日志/测试输出中观察到。必须含 `evidence` 字段 (精确引文或行号)
- `inferred`: 从模式/启发式推断, 无直接观察。必须含 `inference_chain` (推理路径)
- `partial`: 部分证据存在但关键假设未验证。同时含 `evidence` + `inference_chain`

**合并时 grounding 继承** (v4.2.6 完整3值逻辑): 任一 agent 含 grounded → 合并后 = grounded (含所有 agent evidence 并集; evidence冲突(不同行号>5行或矛盾根因)→标记evidence_conflict:true+人工审查)。无 grounded + 任一 agent 含 partial → 合并后 = partial (含 partial agents的evidence并集 + 所有inference_chain并集)。全部 inferred → 合并后 = inferred (含所有inference_chain并集)。

**grounding=null**: CC must re-prompt the SAME agent (not discard immediately). Re-prompt = agent's existing output + "Missing grounding field. Re-submit with grounding=grounded|inferred|partial." Track re-prompt count per agent per batch (max 2). re-prompt计数per-agent(替换后重置), 规则7替换计数per-slot(跨替换累积)——一个slot理论上最多6次re-prompt(2 per agent × 3 replacement tiers)但最多3 agents before PERMANENTLY_FAILED。Only discard agent output after 2 re-prompt failures. After discard, the finding slot is treated as UNRESOLVED and triggers Rule 7 replacement logic.

**inferred加严**(v4.7.8, fp-check可选): fp-check可用时, 用户可要求对grounding=inferred项先跑TRUE/FALSE POSITIVE判定——FALSE→标fp-rejected不进STEP 2; TRUE→升grounding=partial(fp-check证据填入evidence, 符合三值合并逻辑: 已验证证据+剩余推理=partial)。skill不可用→原路径(inferred项直接进🔴用户确认)。

**STEP 4 Codex 验证**: Codex "Bug X已修复" 含 grounding=grounded → 检查证据引用真实文件/行号; Codex 含 grounding=inferred 或不含 grounding → 该项 Gate FAIL (Byzantine Codex defense)。**FP消除**(v4.7.8, fp-check可选): grounding检查仅验证引用存在, 不验证bug真伪——Codex可引用真实file:line却报虚假bug。防御通过后, 对每条Codex新报bug调用`fp-check` skill判定: FALSE POSITIVE→标REJECTED_FP不进STEP 5(不计入Bot举报阈值——伪报≠伪造引用); TRUE→正常进双批准。skill不可用→回退现行准确性维度Agent判定。

### STEP 1.5 — 参考源交叉验证 (条件触发)

涉及功能领域有参考源→5+ Agent扫描→每Agent: 可复用代码+source:line+风险→交叉对比→最优方案

### STEP 2 — 方案生成

每个Bug: 文件+行号+old代码+new代码+风险+验证命令

**Phase定义**:
- **Phase A** (立即): P0修复(充分理解+无API改变+可逐字节验证 — 不按行数限定) + 极小风险修复(≤5行)
- **Phase B** (优先): 低风险少量代码
- **Phase C** (随后): 中风险
- **Phase D** (优化): 需评估

多方案→3 Agent对比(最小更改/长期最优/最低风险)→最佳推荐

🔴 方案写入 `C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\FOR_CODEX_{描述}.md` (规则27强制报告路径) → 用户确认→STEP 3

### STEP 3 — Codex可复制文本

**触发**: "告诉codex"/"发给codex"

**消毒规则** (用户提供的值: bvid, title, author, file paths, code snippets):
1. 删除双向外覆字符(U+202A-E, U+2066-9)——必须在NFKC之前删除(Unicode TR36: bidi控制字符应在规范化前移除, 防止规范化改变bidi字符行为)
2. NFKC规范化
3. 删除零宽字符(U+200B/C/D, U+FEFF)
4. 删除null字节(\0)
5. 删除C0/C1控制字符(除换行/回车)——单步完成，不重复
6. 转义```围栏(防止Codex误解析消息边界)
7. JSON状态文件: 当前仅做JSON序列化(简化实现)——未统一走完整消毒流水线。`# ponytail: JSON嵌入需经Bidi-NFKC-零宽-Null-C0/C1消毒(规则28强制)，ceiling: 仅序列化层转义，upgrade: 规则28与STEP 3统一时纳入完整流水线`

**模板**: 标准格式(轻量版对话内/完整版文件形/状态报告格式C)。 `=`分隔, 无Markdown表格, 中文+术语, `-->` 非 `→`, `[!]` 非 `⚠️`。>20000 chars(~10000 tokens) → N部分, P0优先, ≤10000 chars/部分(~5000 tokens)。

**消息关联ID** (v4.7.8, bilibili-subtitle Layer1Protocol请求-响应关联降级版): 每份FOR_CODEX文本首行嵌入`[MSG-{4hex} {i}/{N}]`({4hex}=uuid4().hex[:4], 单部分N=1), 模板末尾要求Codex回复首行原样回显该标记。STEP 4匹配: 回复含匹配[MSG-*]→权威关联+部分完整性判定(缺部分→提示"缺第i/N部分"); 无标记→回退<3s+连续内容启发式, 不拒收。晚到Codex回复凭旧MSG-ID直接归属原轮次。
`# ponytail: 30s超时/reconnect不移植(无墙钟, N=4消息计数已覆盖; 插件JSON-RPC自带关联→仅手动粘贴路径适用), ceiling: Codex不回显标记时退化为现行启发式, upgrade: 手动路径退役时删除`

### STEP 4 — Codex反馈交叉验证

**触发**: 用户粘贴 "Codex --> CC, ..." OR Codex静默(连续N=4条用户消息无Codex回复)

**静默回退**(消息计数, 非墙钟): N=4→询问"继续等/跳过?"。用户说"继续等"→silentMsgCount不重置(继续向上计数)→再等待消息。用户每说一次"继续等"→提示"已等待{X}轮, 可随时说'跳过'进入降级模式"。N=5→无条件自动降级。

**10+ Agent, 7维度**(每维度≥1): 准确性/代码复用/遗漏/编码安全/架构/回退/执行。维度全失败→人工审查。

**产出**: CC|Codex|实际|结论对照表

**Codex 5大错误模式**(必须假设): 声称修复未变/诊断偏离根因/数量夸大/不验证源文件/遗漏用户反馈
**Byzantine Codex防御**(P0强制, v4.2.6验证基准): "文件/行号不存在"验证基准: (1)优先git rev-parse HEAD当前tree; (2)文件不存在→git log --diff-filter=D检查被删→被rename(git log --follow)追踪新路径比对内容; (3)行号不存在→git blame -L检查, 搜索窗口±10行→有相似代码则标记行号偏移, 仅当实际偏移≤±5行时接受(规则10), 超出±5→Gate FAIL。grounding=partial处理: 验证evidence部分(同grounded), 标记inference_chain部分(同inferred)。Codex引用不存在的文件或行号→该项Gate FAIL, 拒绝该项批准, 该项直接进入CC独立判断(同降级模式: 非P0→用户批准, P0→CC 4 Agent验证: investigator+general-purpose+Plan+debugging)。不因单条虚假引用强制全局降级——仅隔离伪造项, 其余项正常流程。Bot举报(模式化伪造, >3条虚假引用)触发全局警告+人工审查, 不是自动降级。≥5维度全部或多数项上报矛盾→批量ABORT: 将所有Codex项标记REJECTED_BATCH, 退回STEP 2以非Codex方式重新生成方案。

**规则冲突**: 规则3/4 vs 冗余验证 → 只验证Codex新内容; 仅确认→跳过。用git blob hash锚定诊断版本; 文件变更后强制重验。

### STEP 5 — 双批准门控 (⚠️阻断)

**正常模式**: Codex批准(每项file:line证据, 拒绝笼统批准) + 用户批准 → 通过。单方=不通过。

**降级模式**(Codex不可用): 用户单批准→通过(P0项除外——P0项仍需CC 4 Agent独立验证, 见规则20, 即使降级模式也不豁免)(Step 4静默回退触发)。

**部分批准**: Codex "Bug 0-3 approved, Bug 4需要方案B" → 批准项执行, 拒项重方案, 再审批。

**P0双验证** (v4.6.9 模式区分): P0修复→即使Codex批准, CC也需独立验证(规则20): 非降级模式=2 Agent(investigator+general-purpose), 降级模式=4 Agent(investigator+general-purpose+Plan+debugging)。任一Agent异议→用户手动override。降级模式下不因Codex缺失降低P0验证强度。

**未经审核项**: Codex未提及→标UNREVIEWED→CC独立判断(同降级模式: 用户批准即执行(P0项除外——P0项仍需CC 4 Agent独立验证(规则20)), STEP 7 CC自我验证)。

🔴 通过→STEP 6

### STEP 6 — 逐项执行

#### Pre-6.0 — 共享DAG构建 (所有修复项执行前)

1. **构建DAG**: 批量grep共享文件/函数/类/导入, 为所有待修复项构建依赖图。
2. **依赖规则**: 1跳——仅直接依赖(B依赖A, C依赖B——B→C表示B必须在C之前执行, A→B在B的DAG条目中记录。C对A的传递依赖不单独记录)。
3. **失败处理**: 直接依赖→BLOCKED, 传递依赖→自动标SUSPENDED(不执行)。用户审查依赖链后可显式override解除SUSPENDED继续执行传递项。

**分支路由**:
- DAG空 + 无共享文件 → STEP 6.0 (Git状态机模式)
- DAG非空 或 有共享文件 → STEP 6.1 (传统逐项执行)
- 复杂P0项 + DAG空 + 用户显式opt-in("用pantheon修") → **pantheon-fix替代路由**(v4.7.8): 多候选修复+隔离worktree+回归门控+对抗验证一步完成, 覆盖STEP 6.0+STEP 7的CC侧机械部分。前提: 必须已过STEP 5双批准——仅替代执行层, 不替代门控; 结果回填fix-log.tsv+session itemStates; STEP 7 CC侧信任pantheon对抗验证结论(不重复), Codex侧双向验证照常。skill不可用→原6.0/6.1路径

#### STEP 6.0 — Git状态机模式 (可选, 用于独立修复项)

**适用条件**: DAG空且无共享文件(所有待修复项完全独立)。

**不适用**: DAG非空或有共享文件→使用传统STEP 6.1逐项执行(下方)。

**流程**:

1. **分支预检查+创建(原子)**: `git checkout -b fixes/{sessionId[:8]}`（checkout -b = 创建+切换, 原子操作, git enforce唯一性——分支已存在则立即失败, 回退传统模式）。无需分两步。失败→回退传统模式。
2. **修复循环** (每项):
   a. 确认已在分支: `git branch --show-current` → `fixes/{id}`; 非目标分支→切换或6.1处理
   b. 修复代码 → `git add {file}` → `git commit -m "fix({bug-id}): {简短描述}"`
   c. 验证: `ast.parse` → `grep -n` → 测试
   d. 验证通过 → 保留提交(分支前进, git log记录修复)
   e. 验证失败 → `git reset --hard HEAD~1`, 重试一次
   f. 连续2次失败 → 标BLOCKED, `git reset --hard HEAD~1`清除最后失败提交, 继续下一项
3. **结果记录**: 每次尝试追加到 `.claude/memory/code-shiniyaya/fix-log-{sessionId[:8]}.tsv`:
   ```
   commit	bug_id	status	description
   a1b2c3d	BUG-01	keep	fix null deref in parser
   d4e5f6g	BUG-02	discard	wrong approach, retry
   h7i8j9k	BUG-03	crash	fix caused syntax error
   ```
   - `status`: keep(验证通过) | discard(验证失败, 已reset) | crash(语法错误, 无法commit)
   - 此文件git不跟踪(加入.gitignore)
   - 崩溃项: commit列留空(N/A), status=crash, description记录错误
4. **合并**(全部项完成→`git checkout {原始分支}`→`git merge fixes/{sessionId[:8]}`→合并成功→`git branch -d fixes/{sessionId[:8]}`)。合并前: `git diff {原始分支}...fixes/{sessionId[:8]}`非空→调用`differential-review` skill做聚合diff安全审查(仅安全维度, 不重复STEP 7逐项正确性): CRITICAL发现→按fix-log.tsv定位commit→排除该commit后合并, 其余照常。skill不可用→跳过(STEP 7编码安全维度兜底)。合并冲突→`git merge --abort`, 列出冲突文件, 报告用户选择(手动解决/丢弃修复分支/逐个cherry-pick通过验证的commit)。
5. **中断恢复**: 分支存在且非当前分支→`git checkout fixes/{sessionId[:8]}`→`git log --oneline`→从最后commit续修

**决策规则**: 二分法保留/重置——修复有效→保留; 修复无效→`git reset`。禁止部分保留。3种结果: keep | discard | crash。

**优势**: 原生审计轨迹(git log), 原子回退(git reset), 零碰撞隔离(git分支), 无需lastFileHash/versionVector/checksum(git对象自带)。

#### STEP 6.1 — 传统逐项执行 (用于跨文件依赖项)

**每次执行**: 符号影响分析→修改→ `git diff --stat`+`grep -n`→ast.parse→编码→文件大小→反馈→确认→继续

**失败**: 失败项→FAILED_FIXES.md + 直接依赖项标BLOCKED。传递依赖不自动阻断。用户手动审查传递受影响项后解除。

P0/P1逐项; P2微改动(<3行)可批量2项。

**手动编辑检测**: 恢复时读pending item的 `lastFileHash` → 重新计算目标文件SHA-256 → 对比。不匹配→`git diff --stat`+`grep -n`→行号偏移±5内→自动校准lastFileHash+行号; >±5或函数签名变更→规则10触发→标BLOCKED+重新方案。

### STEP 7 — 双向验证

**默认**: 1轮(CC→Codex→CC), 双方确认=完成。

**仅当争议时才进入第2轮**(新Bug/修复错误/方案不匹配)。第2轮后仍有争议→DISPUTED→用户裁决→(a)支持CC: 项标VERIFIED完成; (b)支持Codex: 项标FAILED_VERIFY→回STEP 2重方案(重走双批准); (c)搁置: 项写入DISPUTED_LOG.md，不阻塞STEP 8——STEP 8对DISPUTED项仅记录不提取模式。

**变体扩扫**(v4.7.8, 可选): P0/P1项VERIFIED后, variant-analysis可用且用户opt-in→扫描同根因模式的变体bug→新发现写入`C:\Users\shiniyaya\Desktop\code-shiniyaya\报告\VARIANTS_{ts}.md`并作为下一轮STEP 1输入(带grounding字段, 走正常溯源/去重管线), 不阻塞本轮闭环与STEP 8。skill不可用→跳过(零影响)。

**回滚路径** (验证确认修复错误且已合并): 6.0模式→`git revert {commit}`(fix-log.tsv定位commit); 6.1模式→`git checkout HEAD -- {file}`恢复(同文件多修复时用`git diff`定位仅回滚错误hunk; git不可用→修复前存入pending项originalSnapshot字段的原文内容写回；>50KB+git可用→优先6.0分支模式；>50KB+git不可用→无法回滚→执行前需用户显式确认)。originalSnapshot: pending项创建时set-once字段(不可变契约白名单项——与status/substep/lastFileHash同级), 存储修复前文件原文; lastFileHash(SHA-256)仅用于验证恢复结果正确, 不能重建内容。回滚后项回STEP 2。无回滚规则=坏代码静默留存主分支，双向验证失效。

**降级模式**(无Codex, v4.7.8跨模型对抗恢复): 先尝试恢复跨模型对抗——调用`multi-model-adversarial-review`(MMAR; codex/gemini CLI任一存活时)审查修复diff, 成功→产出视同Codex粘贴回复走正常双向验证(mode保持degraded, 不恢复双批准语义——MMAR≠Codex批准, 用户单批准仍必需)。MMAR不可用→CC 6+ Agent独立自我验证→完成(附注"Codex不可用")。6+ Agent split-verdict裁决: 任一P0维度FAIL→整体不通过→用户仲裁; 仅P1/P2维度split→多数Agent通过则整体通过。
`# ponytail: 跨模型对抗恢复依赖skill运行时可用，ceiling: CC 6+ Agent自我验证，upgrade: MMAR稳定后设为降级默认`

## STEP 8 — 工作流后元反思 (v4.0.0)

STEP 7完成后, 自动运行反思, 将本工作流的发现合成为持久知识。

### 触发条件 (双门控, OR逻辑)
- 门控A: 距上次反思 >= `reflection_min_hours` 小时 (默认 8)
- 门控B: 累计完成 >= `reflection_min_workflows` 个工作流 (默认 3)
- 首次运行 (last_reflection_at is None): 立即触发

### Phase 1: Learn — 从本工作流提取新记忆

**输入** (注入LLM): workflow_context_bus 快照 (diagnosis + plan + codex + execution + meta), 现有记忆文件 (最多24个, 每个≤2500字符, 60/40截断), MEMORY.md 索引 (≤6000字符)

**LLM输出** (JSON, DirtyJson容错解析——提取被Markdown围栏/注释/多余文本包裹的JSON, 容忍尾部逗号等常见LLM格式错误。参考autodream auto_dream.py L246 `DirtyJson.parse_string`):
```json
{
  "summary": "本工作流修复了2个P0空指针和1个P1竞态条件...",
  "changes": [
    {"action": "upsert", "path": "null-pointer-init-order.md", "title": "...", "description": "...", "content": "...", "grounding": "grounded", "source_context_ids": ["a1b2c3d4"], "source_first_prompts": ["..."], "source_memory_ids": ["..."]},
    {"action": "delete", "path": "stale-guide.md", "reason": "被新文件完全覆盖"}
  ]
}
```

### Phase 2: Consolidate — 周期性合并去重

**触发**: 每 `consolidate_every_n_workflows` 个 Learn-only 反思后 (默认 3, 0=禁用)
**MD5校验和变更检测** (v4.2.0, autodream auto_dream.py L535-539): 写入前检查文件MD5——若校验和未变→跳过重写(幂等写入优化)。若校验和已变→比对前版本(如果存在)→仅当内容真正变更时写入。
**孤儿检测** (v4.2.0, autodream auto_dream.py L846-918): 使用token重叠分数(`score_token_overlap`——当前项目名称token vs 兄弟项目名称token的交集/最大集)发现可能被遗留在错误memory子目录下的记忆文件。重叠分数>0.5的候选最多返回4个。CC在Consolidate阶段审查这些候选——决定移动到正确子目录或删除。
**输入**: 所有现有记忆文件 (不包含session数据, 仅文件列表)
**LLM**: "只合并语义重叠的文件, 强制删除冗余文件。仅合并和修剪已有内容, 不创造新知识。"

### 反思日志 (.reflection-log.md)
每次反思追加一条记录 (最新在前, 最多40条): timestamp, summary, scope, phase, inputs, created/updated/pruned 列表

### 并发防护
`_REFLECTION_SCOPES` set + 线程锁: 同范围同时最多一个反思运行。排队槽位: 1。

## Agent编排

| 阶段 | 最少 | 类型 | 说明 |
|------|------|------|------|
| 诊断 | 6+ | Inv+Exp+GP+Plan+Debug(5类型) | 并行, 5+维度 |
| 参考源 | 5+ | Inv, GP | 并行 |
| Codex验证 | 10+ | 7维≥1 | 并行 |
| 全库扫描 | 40+ | 全覆盖 | 分批≤batch_size, 总Agent上限50 |
| 执行 | 串行为主 | caveman:cavecrew-builder | 独立文件项可并行(≤4) |
| 迭代扫描 | 20总Agent(5源×4Agent, 10维轮换) | Inv+GP | 分2批(规则5): 首批batch_size个, 首个完成后追加剩余 |

**类型选择**: caveman:cavecrew-investigator(编码/字节) | Explore(遗漏) | general-purpose(逻辑/诊断/回退) | Plan(架构) | debugging(运行时) | caveman:cavecrew-builder(修改) | caveman:cavecrew-reviewer(diff审查)

**类型不可用时**: 回退链 — investigator→general-purpose(通用回退)。Explore仅用于单文件内模式扫描(不跨文件, 不查引用), 跨文件/多文件/依赖分析永不使用Explore。debugging不可用时→general-purpose(含堆栈分析提示词注入)。P0验证槽位专用回退链(v4.7.8): code-shiniyaya-verifier(~/.claude/agents/, 平台侧钉死维度+只读工具集)→investigator→general-purpose。**所有回退链general-purpose Agent必须至少附带1个Skill(默认为code-shiniyaya自身, 若为多Agent场景则为multi-agent-shiniyaya), 防止零Skill裸跑**(反模式#5)。

**缓存前缀纪律** (v4.7.8, 转移包§七): 同批N个Agent提示词=共享前缀(任务规格+规则+输出schema, 逐字节一致)+末尾差异段(源×维度)。前缀命中缓存→N个并行的前缀成本≈1次写入+(N-1)次~10%读取; 前缀任何微小变化(含非确定性枚举顺序)→全部未命中。[WORKFLOW_CONTEXT]注入已在末尾(§工作流上下文总线)——规格块保持字节稳定, 差异只放末尾。缓存按模型分池——Haiku Agent不与Sonnet前缀共享, 同批同模型互享。

**模型阶梯** (v4.7.8, Agent工具原生model参数, Agent工厂模式债务收割): 机械定位/清单扫描Agent(cavecrew-investigator定位/文件完整性/参考源扫描)→`model: haiku`(成本≈Sonnet的1/3、Opus的1/15; cavecrew输出压缩再省~60%主线程token); 诊断/7维验证/P0仲裁/方案对比→inherit不降级。质量敏感判断永不下放Haiku——省钱不覆盖规则20。

## Agent Safety — Three-Layer Defense (v4.0.0)

### Layer 1 — Sandbox + ThinkTool (Agent推理空间 v4.0.1)

- 所有子 Agent 启用 sandbox 模式 (如平台支持, 不可用→检测并降级)
- **Sandbox不可用降级** (v4.6.9): 当sandbox不可用时, Layer 2(项目目录Read/Write)和Layer 3(Bash allowlist)成为主要防线。但Layer 3 allowlist中的`python`/`node`/`npm`/`npx`可通过`-e`/`-c`/`exec`参数执行任意代码——sandbox缺失时这些命令降级为每次调用需用户确认, 或启用参数级检查(拦截`-e`/`-c`/`-exec`标志)。
- Sandbox 防止文件系统逃逸, 即使 shell 权限被授予
- `autoAllowBashIfSandboxed: true`
- **ThinkTool** (v4.0.1, 从 autonomous-coding agents/tools/think.py 移植): 每个 Agent 在调用工具前必须先写入结构化推理到think日志。ThinkTool 内容持久化(不受上下文截断影响), 格式: `[THINK: {agent_id}] {reasoning}`。CC 在迭代后汇总所有 think 日志生成审计轨迹。

### Layer 2 — Permissions (Filesystem)
- 文件操作限制在项目目录: `Read(./**), Write(./**), Edit(./**)`
- 绝不授予自主 Agent `Read(/**)` 或 `Write(/**)`
- Bash 仅在 Layer 3 hooks 有效时授予

### Layer 3 — Security Hooks (Bash Allowlist)

**最低允许命令集**:
```
ls, cat, head, tail, wc, grep  (文件检查)
cp, mkdir                        (文件操作, sandbox+permissions内安全)
pwd                              (导航)
npm, node, npx, python, pip, uv  (开发工具)
git                              (版本控制)
ps, lsof, sleep                  (进程管理, 需额外验证)
```

**敏感命令额外验证**:
- `rm`: 完全禁止 (Agent 不应删除文件; 用 git 清理)
- `pkill`/`kill`: 仅允许杀 dev 相关进程 (node, npm, vite, next, python)
- `chmod`: 仅允许 `+x` (脚本执行权限), 禁止递归 (`-R` 和 `--recursive` 均阻断)

**复合命令防御**: 解析 `&&`, `||`, `;`, `|`, `$()`, `` ` ``, `>`, `<`, `>>` 命令链, **每段独立验证**。任一段不通过 → 整条命令阻断。解析失败 (畸形命令) → 阻断 (fail-safe)。

**危险参数拦截** (强制执行, 非条件): `-e`, `-c`, `--eval`, `--code`, `exec` 参数传入 shell/解释器一律阻断。此拦截对所有命令生效, 不受 sandbox 状态影响。

**实现模板**: 参考 `autonomous-coding-src/autonomous-coding/security.py` — `extract_commands()`, `split_command_segments()`, `bash_security_hook()`

### Agent Handoff协议 (v3.8.0)

HANDOFF = Agent委派后续任务给同类型Agent。CC作为hub维护`agent_teams`→子Agent完成时`transfer_back`返回控制权。

**格式**: `HANDOFF: <target> | <reason>`。investigator未达max_retries(每Agent 2次)=排队新任务; `HANDOFF: none | completed`=不触发新任务。

**Handoff限额** (v4.7.0 折叠): 每Agent最多1次、同目标类型最多2次/批次、handoff Agent计入50上限。HANDOFF目标接收`[HANDOFF_AGENT_OUTPUT]`(≤800 tokens)或`[HANDOFF_WORKFLOW_SNAPSHOT]`(≤1200 tokens)上下文前缀。

`# ponytail: HANDOFF protocol, ceiling: all agents report directly to CC orchestrator (not agent-to-agent), upgrade: when CC supports inter-agent communication natively`

### 重试感知关闭 (v4.2.3, tenacity_stop.py should_exit模式)
tenacity/retry库的stop条件不仅基于重试次数或超时，还应检查外部关闭信号。定义`stop_if_should_exit`类——在每次重试前调用`should_exit()`检查系统关闭标志。若标志为true，立即停止重试（不等最大重试次数）。适用场景：用户CTRL+C中断、工作流被TaskStop杀死、磁盘空间耗尽检测。实现：在重试循环中通过上下文变量传递`_SHOULD_EXIT`回调，或在环境变量中设置`CC_STOP_REQUESTED`标记。

### 信号驱动的分段睡眠 (v4.2.3, shutdown_listener.py sleep_if_should_continue模式)
长时间等待不能使用单次`time.sleep(timeout)`——期间无法响应中断信号。将长睡眠分割为1秒粒度的小睡眠，每秒检查`should_continue()`标志。若中断信号到达→立即退出睡眠。同步版本(`sleep_if_should_continue`)和异步版本(`async_sleep_if_should_continue`)均适用。code-shiniyaya适用场景：等待工作流完成通知时使用此模式（而非固定时间睡眠），确保用户中断能立即响应。

### 流水线恢复编辑模式 (v4.2.3, metachain_meta_workflow.py profiling+editing两阶段+反馈注入)
多阶段创建流程（表单生成→编译验证→创建执行）的恢复模式：每阶段有独立MAX_RETRY=3，失败时注入反馈消息到下一轮（`FEEDBACK: {上一轮错误}`），而非重新开始整个流程。code-shiniyaya在迭代扫描→修复→基准→bug扫描的多阶段流程中适用：若修复阶段失败→注入上一轮失败原因+重试修复（最多3次），不重新启动20 Agent扫描（已扫描结果保留）。

### 分块批量写入 (v4.2.3, rag_tools.py chunk_size=200模式)
批量操作（向量化/记忆写入/报告生成）超过单次上限时，按chunk_size分块处理，每批独立添加，用chunk索引追踪。适用场景：40+ Agent的发现结果合并写入STEP4_TRIM_LOG时按200条/批分块，批间不超时。

**批量**: batch_size=max(4,min(16,cpu_cores-2)), cpu_cores=`python -c "import os; print(os.cpu_count() or 4)"`, 回退=4, 总Agent上限=50

**进度**: 执行中用户可见叙述(STEP转换, 非定时器刷新)

### Agent终端信号协议 v4.4.0 (统一优先级, 消息治理消除歧义)

**优先级链** (v4.4.0 消息治理): 类型化返回值(ReturnBehavior) > 工具调用完成信号(case_resolved/case_not_resolved) > 文本TERMINAL行。冲突时高优先级为准。文本TERMINAL行向后兼容老Agent。**消息治理**: 任意Agent输出仅允许三选一信号——禁止同时使用多种信号类型。若类型返回值存在但含TERMINAL文本行→警告"冗余信号"但以类型返回值为准。关键：CC处理Agent输出时遵循单一信源原则——永远只有一个权威完成信号。

所有Agent必须输出以下终端信号之一(三选一, 按优先级):

```
# 方式1(优先): 类型化返回值 {behavior: "GOTO"|"ABORT"|"NORMAL", returns: [...]}
# 方式2: 工具调用 task_resolved / task_not_resolved
# 方式3(向后兼容): 文本TERMINAL行
TERMINAL: RESOLVED | <做了什么>
TERMINAL: UNRESOLVED | <原因>
TERMINAL: PARTIAL | <发现了什么> | <需要后续跟进什么>
TERMINAL: GOTO | step=<N> | reason=<为什么需要跳转>
TERMINAL: ABORT_BRANCH | <分支名> | reason=<为什么终止此分支>
```

**v4.2.1工具调用完成信号 (AutoAgent tool_editor.py case_resolved/case_not_resolved模式)**: CC注入`task_resolved`/`task_not_resolved`虚拟工具到Agent工具列表。Agent完成任务时调用其一。Agent同时调用两个→标记UNRESOLVED(矛盾信号)。工具调用失败(平台错误)→回退到文本TERMINAL行解析。

**v4.2.0类型化GOTO/ABORT (AutoAgent flow/dynamic.py ReturnBehavior枚举)**: 每个Agent调用返回 `{behavior: "GOTO"|"ABORT"|"NORMAL", returns: [...]}`。behavior="GOTO"→CC终止当前Agent批次, 跳转到指定STEP; behavior="ABORT"→终止指定分支; behavior="NORMAL"→正常流程。类型返回值与工具调用/TERMINAL文本行冲突时→以类型返回值为准。

CC解析规则(v4.4.0 Stream-First Dispatch): 详见§First-Completed Dispatch——首个Agent返回即分发下游, P0立即启动STEP 2, 非P0全返回后批量去重; 落后/停滞检测阈值见 memory/config.json checkpointing (laggard 300s)。

**声明式事件依赖 (AutoAgent workflow_former.py listen_group模式)** (v4.2.1): code-shiniyaya的迭代工作流步骤间存在隐式依赖(20扫描→修复→基准→bug扫描)。将这些依赖转为显式声明: 每个步骤定义`listen`(依赖哪些前序步骤的哪些输出key)和`outputs`(产出哪些key供后续步骤消费)。依赖未满足时步骤不启动——替代原始的串行await硬编码。三模式: If-Else(互斥条件分支，只有一个RESULT输出)、并行化(多事件listen同一父事件，聚合器等所有并行完成)、Evaluator-Optimizer(GOTO迭代循环+评估条件)。

**编译验证管线 (AutoAgent edit_workflow.py XML→Python代码生成+edit_agents.py create_agent→python编译验证)** (v4.2.1): workflow_former生成XML表单→workflow_creator将XML编译为Python代码(`create_workflow`函数)→`python autoagent/workflows/{name}_flow.py`编译验证→`run_workflow`执行测试。agent创建同样: `create_agent`生成Python代码→`python autoagent/agents/{name}.py`编译→`run_agent`执行测试。code-shiniyaya适用: 工作流生成/修复后必须经过编译验证（而不是直接执行）。如果编译失败(语法错误/导入错误)→自动回退+修复+重编译(最多3次)，不执行未通过编译的代码。

### 工作流上下文总线 (v3.8.0)

`workflow_context` 是一个在9步流程中持久化的dict, 在所有Agent调用间共享:

```json
{
  "diagnosis": {
    "bugs": [{"id":"B1","file":"...","line":42,"severity":"P0","root_cause":"..."}],
    "agent_results": {"investigator":{"findings":[...]}, "debugging":{"stack_trace":"..."}}
  },
  "plan": {"phase_a": [...], "phase_b": [...]},
  "codex": {"sent": false, "response_received": false, "approved_items": [], "rejected_items": []},
  "execution": {"completed": [], "failed": [], "blocked": []},
  "meta": {"mode": "normal", "degraded_reason": null, "round": 1}
}
```

注入规则:
1. Agent调用时: 将 `context_variables`(序列化为JSON) 追加到Agent系统提示词末尾, 以 `[WORKFLOW_CONTEXT]` 分隔。
2. Agent返回后: CC解析 `CTX_UPDATE: {"key":"value"}` 行, 合并到workflow_context。
3. `codex.sent` 等元数据字段在Agent注入时移除(Agent不可见)。
4. 恢复时从session JSON的 `workflow_context_snapshot` 恢复上下文总线。
5. **跨handoff上下文累加** (v3.9.14): Agent通过HANDOFF委托时, 当前workflow_context的摘要(诊断中的P0 bugs + 已修复项IDs, 最多1200 tokens)以`[HANDOFF_WORKFLOW_SNAPSHOT]`为前缀注入目标Agent。目标Agent的CTX_UPDATE与源Agent的context合并(深度合并, 冲突时目标Agent优先)。Agent完成后的TERMINAL信号自动携带上下文快照hash, 用于跨handoff验证上下文未被篡改。

### CTX_UPDATE 安全防护 (P0强制)

Agent输出中的CTX_UPDATE注入存在伪造风险。强制的防护措施:

1. **白名单字段**: 仅允许写入 `diagnosis`、`plan`、`execution` 三个顶级键，以及 `meta.suggested_mode`（嵌套键——Agent可建议降级但不可直接变更mode）。Agent通过CTX_UPDATE写入codex字段被拦截。Agent向codex写入的间接路径: CC在STEP 4→5转换时将execution中的codex_verdict提升到workflow_context.codex.approved_items/rejected_items。`codex`、`meta`(除suggested_mode外)被拦截并丢弃（日志警告）。`execution`的schema验证包括`blocked`数组(v4.2.6)。
2. **格式锚定**: CTX_UPDATE必须出现在输出的**最后10行**内且以 `CTX_UPDATE: ` 开头（行首，无前导空格）。输出主体中出现的CTX_UPDATE忽略。CTX_UPDATE值必须是单行JSON——含换行符的JSON字符串被整行丢弃(防多行注入绕过格式锚定)。
3. **值验证**: JSON值必须匹配预期schema（diagnosis→{bugs:[{id,file,line,...}]}，plan→{phase_a:[],phase_b:[]}，execution→{completed:[],failed:[],blocked:[]}）。schema不匹配→整行丢弃。
4. **重复CTX_UPDATE**: 同一Agent输出的所有CTX_UPDATE行合并为一条（最后一条优先）。不允许累积注入。
5. **审计日志**: 每次CTX_UPDATE合并记录到WORKFLOW_LOG.md（agent_id、合并前的context_snapshot、合并后的context_snapshot、被丢弃的键）。

### STEP 4 输入上限 (P0强制, 常量见 memory/config.json truncation)

每项进入STEP 4验证提示词的数据源必须有明确上限:

| 常量 (默认值见 memory/config.json) | 用途 |
|---|---|
| truncation.max_findings_per_dimension | 每验证维度Agent发现数 |
| truncation.max_finding_chars | 每条发现字符上限(头尾截断) |
| truncation.max_codex_feedback_chars | 用户粘贴的Codex反馈总量 |
| truncation.max_source_file_chars | 每源文件加载用于交叉引用 |
| truncation.max_verify_prompt_chars | STEP 4组装后总提示词上限 |

截断函数(60/40头尾分割, v4.2.6):
```python
import os, datetime
from pathlib import Path

def truncate_for_prompt(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max(0, max_chars - head - 5)  # v4.6.9: guard against negative tail
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()

def truncate_with_file_fallback(text: str, max_chars: int, output_dir: str, label: str) -> str:
    """v4.2.0 AutoAgent tools/tool_utils.py模式: 溢出→保存完整文件+返回截断+告知路径"""
    if len(text) <= max_chars:
        return text
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"{output_dir}/overflow_{label}_{timestamp}.txt"
    os.makedirs(output_dir, exist_ok=True)
    Path(filepath).write_text(text, encoding="utf-8")
    truncated = truncate_for_prompt(text, max_chars)
    return truncated + f"\n\n[输出过长——完整内容已保存到: {filepath}]"

def paginate_large_output(text: str, page_size: int = 8192) -> list[str]:
    """v4.2.2 AutoAgent terminal_tools.py 分页模式: viewport_current_page/total_pages/page_up/page_down/page_to。
    超大输出不截断也不保存文件——而是分页, 提供翻页导航。适用场景: 日志文件/编译输出/批量grep结果。
    """
    lines = text.split('\n')
    pages = []
    for i in range(0, len(lines), page_size):
        pages.append('\n'.join(lines[i:i+page_size]))
    return pages
```
超过上限时: 按严重度排序(P0 > P1 > P2), 取前N条, 其余写入STEP4_TRIM_LOG.md。同严重度时二级排序: 按文件路径字母序, 再按行号升序。同文件同严重度≥3条时取行号最近的2条(避免单文件垄断)。

### 记忆

所有记忆文件位于 `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\`:
- **MEMORY.md** — 记忆索引
- **reference-sources-v2.md** — 4个新增参考源 (65个模式)
- **high-impact-patterns.md** — Top-10可集成模式
- **reference-sources.md** — 全部41个参考源清单
- **upgrade-transfer-package.md** (v4.7.7) — **升级资源转移包索引**: 5源穷尽后的第一升级参考。主文件`C:\Users\shiniyaya\Desktop\skill辅助文件夹\skill升级开发-完整转移包.md`(373行, 8板块: 可装Skill/已装Skill提取规则/外部工具/CC内置能力/参考仓库file:line/DSPy/新Skill方案/9条Action Items) + 补充文件`最终轮补充-自动化迭代与防bug转移包.md`(329行, 8方向: 5层验证体系/防循环LoopLens+unloop/token节省数据/CC真实边界: Stop hook=对抗审查唯一入口+exit code 2=唯一可靠阻塞)。后续升级从转移包提取, 不重扫5源; 新模式集成仍走ponytail阶梯+20 Agent验证。
- **applied-patterns.md** — 规则22已应用模式台账

**规则**: 此Skill对应的所有记忆和修改只能写入本目录, 不得写入 `~/.claude/projects/c--/memory/` (bilisum记忆)。Bilisum及其记忆仅供参考, 不作为本Skill的写入目标。
- **多Agent协调**: `multi-agent-shiniyaya` Skill; 不可用时单Agent串行
- **迭代扫描恢复协议**: `references/resume-protocol.md` — 被杀死/卡住的Agent工作流恢复设计
- **日志解析器**: `references/journal-parser.py` — 从journal.jsonl提取部分结果
- **扫描状态JSON Schema**: `references/scan-state.schema.json` — scan-state-{iter}.json模式
- **延续规划器**: `references/continuation-planner.py` — 最小重跑计划生成
- **延续工作流模板**: `references/resume-workflow.md` — CC编排器和纯CLI延续模式

## 迭代扫描恢复 (v3.8.0)

### 问题场景

10 Agent扫描工作流在中途被杀(7个Agent返回结果, 3个卡住)。部分结果丢失——journal.jsonl包含已完成Agent的 `type: "result"` 行, 但CC默认不自动读取。

### 恢复流水线

```
被杀工作流 → [1:日志解析] → scan-state-001.json → [2:延续规划] → 仅重跑3个 → [3:合并] → scan-state-002.json(完整)
```

**步骤1 — 事后分析**: 对被杀工作流目录运行 `journal-parser.py`。解析journal.jsonl中所有 `type: "result"` 行, 提取已完成的Agent判决和issue。计算摘要: 启动/完成/卡住计数, 按严重程度分布。生成 `scan-state-{iter}.json`。

**步骤2 — 延续规划**: 运行 `continuation-planner.py scan-state-001.json`。识别仅需重跑的维度(状态为 `timed_out`)。不重跑已完成的PASS/PARTIAL/FAIL维度。输出重跑维度数量及节省百分比(例如7/10完成 = 仅重跑3个 = 节省62.5%)。

**步骤3 — 合并**: 延续工作流完成后, 对新的journal.jsonl运行 `journal-parser.py --iter 2 --merge-from scan-state-001.json`。将新Agent结果合并到已有维度上: 卡住维度替换, 已解决维度叠加, 重新计算摘要。

### scan-state-{iter}.json Schema

每个扫描维度一个条目, 包含: key(v2哈希), agentId, label, status(completed|timed_out), verdict(PASS|PARTIAL|FAIL), issues数组(严重程度+描述), iterDetected, iterResolved, `scanned_files`(字符串数组——本维度实际扫描的源文件路径, 用于自检#15旋转验证)。

`continuation` 块包含: completedKeys(已清洁维度, 不重跑), retryKeys(卡住维度, 需重跑), parentIteration, retryReason。

### 集成到SKILL.md停止/中断

规则12-14处理**会话内**逐项恢复。v3.9+ RESUME协议扩展至**跨会话工作流级**恢复——即整个工作流被 `TaskStop` 杀死或超过600秒超时时。

**执行工作流时**: 在启动时保存工作流目录路径。规则5(batch_size) + 规则7(Agent失败替换)处理Agent超时。但若最终工作流仍被杀死 → 运行事后分析流程恢复已完成项。

**恢复规则**:
- 已完成维度(PASS/PARTIAL/FAIL) → 不重跑。仅重跑状态为 `timed_out` 的维度。
- 重跑计数 = 仅卡住Agent的数量(非所有10个)。
- 合并后摘要重新计算。迭代计数器递增。
- 所有迭代完成后做最终聚合: 累积issue × 迭代的并集(按维度key去重)。

### 规则集成

| 现有规则 | RESUME扩展 |
|---------|-----------|
| 规则7 — Agent失败替换 | 每槽位最多2次替换, 被替换Agent的结果仍然写入journal.jsonl(type: "result")。事后分析将这些视为已完成(verdict=PARTIAL, 标注替换次数)。 |
| 规则12 — 3次同文件失败 | STOP_LOG.md触发后, 其他维度的部分结果通过日志解析器可恢复。不丢失已完成工作。 |
| 规则13 — stop/中断/CTRL+C | 立即停止。工作流目录在磁盘保留完整。后续事后分析可提取所有已完成Agent结果——等同于干净恢复。 |
| 错误表 — STEP 1个别超时 | "每维度≥1成功; 全失败→人工审查"扩展为: 部分成功维度通过日志解析器恢复, 仅失败的维度排入重跑队列。 |
| progress-tracking.md(已由inline log()取代) — 600秒杀死 | 在600秒时TaskStop。立即对被杀工作流运行journal-parser.py恢复部分结果。延续规划器计算精确重跑集合。 |

## DO/DON'T

**做**: 多源文件后诊断/6+ Agent(5类型)/精确old→new代码/ast.parse验证/报告写入正确路径/纯文本格式/逐项反馈/符号影响分析/遵守全部28条规则/Codex静默→跳过选项/stop→立即停→保存JSON状态。调参查阅 memory/config.json。

**不做**: 无批准修改/单源文件结论/批量汇报(P0/P1)/报告散落桌面/Markdown表格或Unicode/信任Codex自验证("已修复"/"approved")/跳过符号分析/P0跳过4 Agent验证/零Skill Agent

### 输出格式化和工具模式 (v4.2.4-v4.5.2, 从4源工具链提取)

<!-- 分类: [I/O]输入输出 [AGENT]Agent生命周期 [MEM]记忆 [VAL]验证 [INFRA]基础设施 -->

**结果标记模式** [I/O] (edit_agents.py list_agents L40-49 start/end marker): 文本输出中嵌入标记对(`AGENT_LIST_START`/`AGENT_LIST_END`)包围JSON数据——确保正则可靠提取结构化数据而不依赖首尾行。适用: 所有Agent输出含JSON时嵌入标记。

**Shell脚本代理模式** [I/O] (edit_agents.py run_agent L131-138): 复杂命令通过临时shell脚本执行(先`create_file`→`chmod +x`→执行→用完即弃)，避免shlex.quote转义问题和命令行长度限制。

**速率限制处理** [I/O] (github_client.py _handle_rate_limit L248-256): API速率限制剩余<10时，计算reset_time并sleep(最多5秒), 不盲目等待完整时间窗口。

**print_stream灰暗日志** [I/O] (io_utils.py print_stream): `[grey42]`标签标记非关键流输出，与关键结果视觉区分。Agent输出分类: 关键=P0发现/Error，灰暗=进度/中间日志。

### 工具保护和编译验证模式 (v4.3.1, 从 AutoAgent 工具链提取)

**protect_tools不可修改检测** [VAL] (edit_tools.py L27-29 protect_tools): 创建/删除工具前检查工具名是否已存在于registry——已存在则拒绝修改。`# ponytail: protect_tools registry not implemented, ceiling: manual schema checks (CTX_UPDATE 安全防护+hand-coded validation), upgrade: when agent tool registry exceeds ~20 tools`

**工具编译自验证** [VAL] (edit_tools.py create_tool L91-103): 创建工具后立即执行`python {tool_path}`编译验证——编译失败就回滚。适用: 任何Write/Edit操作后立即做ast.parse或编译检查, 不等到验证阶段才发现语法错误。

**tiktoken编码器全局单例** [INFRA] (autoagent-src/autoagent/memory/utils.py L1-9 ENCODER全局变量): tiktoken编码器只初始化一次(全局变量+is None检查)，避免每个chunk重复加载tokenizer(~500ms节省)。适用: STEP 0环境检测的tiktoken可用性检查后应缓存编码器实例。

**分块重叠** [I/O] (autoagent-src/autoagent/memory/utils.py chunking_by_token_size L18-36): 按token分块时overlap_token_size=128——确保块边界不切断上下文。适用: 超大输出分块处理/向量化场景（报告生成/大型日志解析）。

**工作流XML Pydantic约束验证** [VAL] (worklow_form_complie.py): WorkflowForm使用Pydantic model_validator+field_validator进行多层约束: (a) 事件只能listen前面定义的事件→无循环依赖, (b) 输入数量=listen事件数量→数据流完整性, (c) RESULT输出最多1个→互斥分支保证, (d) GOTO action必须含value→非空检查。`# ponytail: Pydantic/Jsonschema workflow validation not implemented, ceiling: manual schema checks (§CTX_UPDATE 安全防护), upgrade: when workflow complexity > 10 steps or agent count > 30`

**transfer_back惯用完成信号** [AGENT] (programming_agent.py L84 system_agent transfer_back): 子Agent完成任务后通过`transfer_back_to_{orchestrator}`将控制权返回给编排Agent，而非自行声明完成——编排Agent始终是完成信号的唯一汇聚点。适用: code-shiniyaya的多Agent批次中，子Agent报告发现→编排器CC汇总，子Agent不应自行声明"迭代完成"。

**Markdown浏览器viewport分页抽象** [I/O] (abstract_markdown_browser.py): 所有浏览器统一实现address/viewport/page_up/page_down/visit_page/find_on_page接口——分页导航独立于底层获取方式(requests/Selenium/Playwright)。[部分应用] `paginate_large_output()`(§STEP 4 输入上限)已实现分页模式，但多Agent输出未统一到抽象viewport接口。

**LocalEnv回退 + conda自动发现** [INFRA] (local_env.py L22-73 _find_conda_sh): 环境检测采用多路径尝试链(path列表→conda info→失败None返回)，任一命中即停止。无Docker时自动回退本地执行，不等人工。适用: STEP 0环境能力检测的多路径回退模式——tiktoken不可用→字符估算，git不可用→跳过状态机，Python不可用→纯文本诊断。

**URL→Markdown多格式管道** [I/O] (mdconvert.py 开头30行): PDF(docling+pdfminer)/DOCX(mammoth)/PPTX/HTML→Markdown统一管道，每种格式独立转换器——任一失败时不影响其他格式。适用: 多源文件读取的格式容错模式——源文件不存在/格式不支持时跳过该项而非整体失败。

### 记忆分类法和Agent工厂模式 (v4.3.2, 从 AutoAgent + autodream 残余文件提取)

**双轨Agent注册** [AGENT] (dummy_agent.py): `register_agent`(标准Agent) vs `register_plugin_agent`(插件Agent)——两级注册系统，插件Agent有不同生命周期。适用: code-shiniyaya的Agent类型应分为核心类型(investigator/general-purpose/Plan/debugging)和扩展类型(caveman系列)，核心类型不可删除，扩展类型可动态加载。

**动态指令closure** [AGENT] (dummy_agent.py `instructions(context_variables)`): Agent指令不限于静态字符串——可以是一个接收运行时context_variables并返回动态生成指令的闭包函数。`# ponytail: dynamic instruction closure not implemented, ceiling: fixed prompt templates per agent type, upgrade: when agent types exceed 10 or need context-aware prompts`

**Agent工厂模式** [AGENT] (dummy_agent.py `get_xxx_agent(model: str) -> Agent`): 所有Agent通过工厂函数创建，model选择外部化——Agent定义与具体模型解耦。`# ponytail: upgrade trigger reached (v4.7.8, CC Agent工具已原生支持model参数: sonnet/opus/haiku)——resolved by §Agent编排-模型阶梯; factory abstraction itself仍不需要, ceiling: per-call model param`

**`parallel_tool_calls = False` 每Agent工具序列化** [AGENT] (github_agent.py): 单个Agent可强制自己的工具调用串行执行——与批级别的并行启动(规则23)是不同维度的控制。适用: P0修复执行Agent应串行调用工具(Read→Edit→ast.parse逐项序列), 而扫描Agent可并行。

**工具预取Meta-Agent** [AGENT] (tool_retriver_agent.py): 专用Agent在执行前预取+合并下游Agent所需的所有工具文档——将"需要什么工具"与"如何使用工具"分离。`# ponytail: tool pre-fetch meta-agent not implemented, ceiling: agents discover tool signatures on-demand at first call, upgrade: when agent types exceed 20 or MCP servers exceed 5`

**`.promptinclude.md` 规则vs事实分离** [MEM] (autodream autodream.msg.md): 记忆文件按性质分为`.promptinclude.md`(行为规则/约束——系统自动加载)和`.md`(事实/架构——按需检索)。适用: code-shiniyaya的记忆应区分规则类文件(如memory-isolation-rule.md→自动加载)和事实类文件(如reference-sources-v2.md→按需检索)，防止规则被错误修剪。

**宿主重建索引+行限制** [MEM] (autodream autodream.msg.md): MEMORY.md索引由宿主(非Agent)从文件描述重建，有硬性行数限制——Agent管理内容，宿主管理索引。`# ponytail: host-rebuilt MEMORY.md index with line limit not implemented, ceiling: manual index maintenance, upgrade: when memory files exceed 50 or cross-reference density exceeds manual tracking`

**记忆内容质量3规则** [MEM] (autodream autodream.msg.md): (1)禁止原始转录转储到记忆, (2)精确计数需有证据支撑否则用谨慎语言, (3)文件名偏好稳定概念导向而非会话主题导向。适用: code-shiniyaya的memory/文件写入应遵循这三条规则——防止虚假精确记忆和命名漂移。

### v4.5.1 自主编码Agent完整管线 (autonomous-coding全量读取)

**两阶段Agent模式** [AGENT] (initializer_prompt.md + coding_prompt.md): (a) Initializer Agent——首会话创建不可变检查清单(feature_list.json)、环境脚本、Git仓库。(b) Coding Agent——后续会话从fresh context重新定向(读取spec→检查清单→progress→git log)。适用: code-shiniyaya的Init+Loop模型确认为正确方向——Init创建不可变plan→Loop每轮fresh context从磁盘续取。

**MANDATORY启动验证** [VAL] (coding_prompt.md L48-60 STEP 3): 每个新会话先验证上一会话未引入bug——跑1-2个已标记passing的核心测试确认仍通过。若失败→立即标passes:false→修复→再做新功能。适用: code-shiniyaya的每次迭代启动前应验证上一轮修复是否引入回归——跑快速冒烟测试。

**回归优先协议** [VAL] (v4.5.2新增, coding_prompt.md STEP 3): 实现新功能前必须重验证此前已通过的1-2项——若发现回归→标记失败+修复回归→然后才能开始新工作。适用: 迭代扫描在每轮修复前应重验上一轮已修复项——防止修复引入新bug。

**工具级并行+单工具错误隔离** [AGENT] (v4.5.2新增, tool_util.py L27-39): `asyncio.gather`并发执行多工具调用→每个工具独立try/except→`is_error:True`标记失败工具→一个工具崩溃不影响并行工具。适用: 当单个Agent需Read多个文件时使用asyncio.gather并发读取——单文件失败不阻塞其他文件。

**Replace-all计数警告** [VAL] (v4.5.2新增, file_tools.py L255-265): Edit时count(old_text)→若出现次数>1→替换全部但返回警告含计数。适用: STEP 6 Edit操作应检查匹配次数——多次匹配时警告编排器而非静默全替换。

**UnicodeDecodeError行内二进制检测** [I/O] (v4.5.2新增, file_tools.py L272): 读取文件时catch UnicodeDecodeError→标记为二进制文件——单次读取即检测, 无需预检。适用: Agent文件读取时内联检测二进制文件——避免两次读取。

**消息对截断+通知注入** [I/O] (v4.5.2新增, history_util.py L85-111): 超出token预算时删除最旧的user+assistant对(而非单条消息)→注入"[Earlier history has been truncated.]"通知——保持对话结构完整(user+assistant成对)。适用: 长对话截断应保持消息对完整性——不截断单个消息。

**系统提示词token估算回退** [I/O] (v4.5.2新增, history_util.py L29-41): API count_tokens成功→精确计数; API不可用→`len(text)/4`估计回退。适用: STEP 0 tiktoken检测的二级回退——tiktoken可用→精确; 不可用→字符估算。

**`{ts}`变量约定** (v4.6.9): 全文`{ts}`均表示当前ISO8601时间戳(如`20260716T143022`), 精确到秒, 不含冒号以兼容Windows文件名。首次使用为§记忆保存-snapshot-{ts}.md。

**Prompt Caching 提示词缓存** [INFRA] (v4.5.2新增, history_util.py L58-67,119-123): 最后一条消息content块注入`cache_control:{"type":"ephemeral"}`→重复系统提示词+历史前缀自动缓存→降低延迟和成本。需分别追踪cache_read_input_tokens和cache_creation_input_tokens(计费标准不同于常规input tokens)。适用: 迭代扫描中固定系统提示词和工作流上下文可启用缓存——20+ Agent扫描成本降低。

**feature_list.json不可变清单** [VAL] (coding_prompt.md L107-127): 仅passes字段可翻转, 禁止删除/编辑/合并/重排。适用: scan-plan的verified字段同样模式——唯一可变字段。

**progress.txt跨会话交接** [MEM] (coding_prompt.md L143-149): 每会话结束时写完成内容、测试结果、发现&修复的bug、下一步建议、完成度(x/y tests)。适用: code-shiniyaya的journal.jsonl或CHANGELOG.md应承担同样角色。

**clean exit原则** [VAL] (coding_prompt.md L151-158): 结束前必须commit所有代码→更新progress→确保无未提交变更→保证app可运行。适用: 每轮迭代结束前必须commit SKILL.md变更→更新memory→写journal→状态clean, 下一轮可直接续跑。

**UI验证+截图强制** [VAL] (coding_prompt.md L84-104): 禁止仅用curl测后端, 必须用浏览器工具验证UI+截图+检查控制台错误。适用: 修复验证不能仅看diff——必须ast.parse验证语法+测试运行验证功能。

**agent.py message_params伞参数** [AGENT]: Agent的message_params支持extra_headers、metadata、API参数(top_k/temperature/max_tokens)——所有LLM API参数通过单伞参数对象传递。适用: 配置外部化方向正确——所有Agent参数应通过config dict注入。

**MCPTool动态加载** [INFRA]: MCP服务器工具通过Connection→session→call_tool动态调用, 无需静态注册。适用: 扩展Agent工具链应支持MCP协议——动态发现工具签名。

**autonomous_agent_demo.py CLI参数化** [INFRA]: --project-dir, --model, --max-iterations参数化所有可调维度。适用: 所有调参应CLI可控, 不在代码中硬编码。

**5源全量确认** (v4.7.7对齐v4.6.12计数): AutoAgent 196文件(全部.py+.md+docs+eval), autodream 9, autoresearch 5, autonomous-coding 30, ponytail(见§v4.6.0第5源)。未读残余仅__init__.py(stub)、build/配置文件和纯文档页面——零可提取自动化模式残留。

### 基准测试10条黄金原则 (AutoAgent evaluation/ 提取)

1. **断点续跑** [VAL] (`utils.py prepare_dataset L64-113`): 读取已有output.jsonl→收集已完成的instance_id→从数据集中过滤掉。长跑可中断重续，不丢失进度。适用: code-shiniyaya的迭代扫描应支持中断恢复——每轮写入scan-state.json, 重跑时读取已完成维度, 仅跑剩余。
2. **标准化输出Schema** [VAL] (`types.py EvalOutput L32-48`): 所有基准测试产出统一的`{instance_id, test_result, metadata, messages, error}`记录。适用: 迭代报告和bug扫描输出应统一schema——跨迭代可比。
3. **元数据复现指纹** [VAL] (`types.py EvalMetadata L8-19`): 每次运行记录agent_func/model/eval_output_dir/start_time/dataset/data_split。适用: 每次迭代记录SKILL.md版本+Agent配置+时间戳(git commit hash可在details字段自定义添加)。
4. **多类型答案评分** [VAL] (`gaia/scorer.py L28-79`): 检查ground truth类型(number/list/string)后选对应比较方法。适用: bug验证不应单一评分——按P0/P1/P2分级评分。
5. **重试+硬失败** [AGENT] (`utils.py _process_instance_wrapper L272-323`): 瞬时失败重试N次→永久失败后写ERROR并继续。适用: Agent超时重试最多2次后标PERMANENTLY_FAILED(规则7)。
6. **资源finally清理** [INFRA] (`gaia/run_infer.py L213-234`): Docker容器和端口文件在finally块释放。适用: 工作流目录和临时文件在每次迭代后清理。
7. **并行+速率限制** [INFRA] (`utils.py run_evaluation L114-265`): daemon=False子进程可自生子进程, time.sleep(3)限速生成, 三级清理(join→terminate→kill)。适用: Agent启动限速。
8. **答案提取+回退** [I/O] (`gaia/run_infer.py L182-187`): 正则提取`<solution>...</solution>`→失败回退原始文本。适用: Agent输出解析——结构化提取优先→回退原始文本。
9. **每类别分解** [VAL] (`gaia/get_score.py L20-41`): 不止总分——按难度/类别分解准确率。适用: 迭代报告不止P0总数——按维度/源分解发现分布。
10. **Few-shot格式演示** [I/O] (`math500/prompts.py`): few-shot示例不仅展示推理—也展示机器可解析的最终答案格式。适用: 所有Agent提示词必须包含期望输出格式的示例。

### v4.5.0 元编程和基础设施模式

**内容寻址延迟向量索引** [MEM]: 代码库zip→MD5哈希→collection名含哈希→`if count()==0`仅首次索引。代码变更自动触发重索引(新哈希=新collection)。适用: code-shiniyaya的memory写入应使用内容寻址——MD5未变则跳过重写。

**特性门控优雅降级** [INFRA] (mdconvert.py L31-55): `IS_AUDIO_TRANSCRIPTION_CAPABLE`(L35)/`IS_YOUTUBE_TRANSCRIPT_CAPABLE`(L43)基于可选依赖是否可导入设定门控。不可用时跳过该功能而非崩溃。适用: STEP 0环境检测的tiktoken/git/Python检测——不可用→跳过相关功能, 不阻断。

**Registry驱动动态API生成** [INFRA] (server.py): 启动时遍历registry.tools/agents→inspect.signature提取参数→为每个工具生成FastAPI POST端点+自动参数验证。添加新工具→自动暴露HTTP端点, 零手动路由。适用: code-shiniyaya的agent类型注册应支持自省——CC自动发现可用类型和能力签名。

**@mention多Agent路由** [AGENT] (cli.py): 用户在提示词中`@AgentName`路由到特定agent, `PromptSession+UserCompleter`提供tab补全。适用: 用户可通过@mention直接将任务分配给特定Agent类型。

**原子端口分配** [INFRA] (cli.py port file lock): `filelock.FileLock`保护端口分配→`.port_{N}`标记文件追踪→Docker查询现有容器端口重用。适用: 多工作流并发时资源分配需文件锁保护。

**结构化输出提取+回退** [I/O] (cli.py 答案提取): 正则提取`<solution>...</solution>`→失败回退原始文本。适用: Agent输出提取——结构优先→回退原始文本(与基准测试原则8同一模式)。

**分层优雅关闭** [INFRA] (browser_env.py close L569-587): 4层升级: signal→join(5s)→terminate()→kill()。适用: 工作流终止不应单层——先TaskStop→join→强制kill。

**动作感知超时** [AGENT] (browser_env.py step L551-554): 不同动作类型不同超时(正常=30s, 页面访问含下载=600s)。适用: Agent超时应按任务类型区分——文件操作长超时, 纯推理短超时。

**双向心跳+命令复用** [AGENT] (browser_env.py L491-543): 单Pipe同时承载数据+IS_ALIVE/SHUTDOWN控制消息。适用: CC与子Agent间的信号通道——数据和控制用同一通道, 定期ping。

**依赖注入+签名擦除** [AGENT] (file_surfer_tool.py with_env L26-39): decorator注入env为第一参数→`signature.replace`从公共签名中隐藏→Agent不可见注入参数。适用: CC可将workflow_context注入Agent提示词而不暴露给Agent。

**多源格式检测** [I/O] (mdconvert.py L920-962): `convert_response`从4个独立源猜测文件扩展名(Content-Type→Content-Disposition→URL路径→puremagic字节检查), 按可靠性排序。适用: 当Agent产出可能有多种格式时, 多源检测优于单一检测。

**数据→源码编译器** [INFRA] (browser_cookies.py L12-39): JSON→Python模块——运行时数据转为可导入源码。适用: 动态配置数据可序列化为Python模块, import加载, 免JSON解析开销。

**闭包命名空间隔离** [MEM] (mdconvert.py 全文件嵌套类): 所有converter类嵌套在单一函数内——函数返回后类被GC回收, 零命名空间污染。适用: 注入到Agent的One-shot代码应使用闭包隔离, 防止污染全局。

**browser_env.py + web_tools.py 统一观察结构** [I/O]: (a) `WebObservation`数据类标准化所有浏览器工具输出→ `{content, url, screenshot, open_pages_urls, active_page_index, error}`。适用: 所有Agent应返回标准化observation结构，CC统一解析。(b) `wrap_return_value`模板化——原始观察包装为预设格式文本(URL+Accessibility Tree)。适用: Agent输出标准化——定义统一的AgentObservation接口。

**plugin.yaml 三层配置钩子** [INFRA]: (a) `plugin_loaded`事件→插件加载时一次性初始化, (b) `before_agent_start`事件→每个Agent启动前pre-flight检查。适用: ThinkTool强制检查可作为before_agent_start钩子——检查agent工具列表是否含ThinkTool, 无则注入。

**agent.py auto_continue_delay** [AGENT]: Agent自动继续前的可中断窗口(默认3秒)。适用: 自主迭代循环中每轮启动前加0.5s中断窗口。

**progress.py ChecklistManager** [MEM]: 不可变检查清单的verified状态翻转管理器。适用: scan-plan的verified字段应采用同类不可变管理模式。

**pyproject.toml 依赖极简主义** [INFRA]: autoresearch仅7个依赖。适用: 每个外部库需证明必要性——依赖审计。

**分析结论**: 本轮3 Agent平行扫描~15个残余文件。autodream残余(4文件)=零新发现。AutoAgent残余(9文件)+autoresearch/autonomous-coding残余(5文件)=5个边际模式(上列)+以下2个。4源核心自动化、自我迭代、防卡顿、记忆管理模式已在v4.4.0前穷尽。

**CLAUDE.md/AGENTS.md .gitignore隔离** [INFRA]: autoresearch的.gitignore将CLAUDE.md和AGENTS.md列入忽略——launcher每会话生成新的提示词文件，防止上一会话的生成指令污染项目永久配置。适用: code-shiniyaya的SKILL.md在迭代中被修改后，不应自动提交——需显式审查后再commit。

**文件系统作为唯一跨会话状态** [MEM]: agent.py每轮在`async with client:`内创建新的client——完全的fresh context。跨会话状态仅通过磁盘文件(feature_list.json存在性=是否为首次运行)传递。适用: code-shiniyaya的迭代状态应完全外部化到scan-state JSON和journal.jsonl——不依赖内存中的上下文传递。

**首次运行时长警告** [AGENT]: agent.py首次运行时显式警告用户预计耗时(10-20分钟)、原因(生成200条测试)、以及如何判断未卡死(观察[Tool: ...]输出)。适用: 任何首次运行成本显著高于后续迭代的Agent应在启动时发出类似警告。

### v4.6.0 第5源: ponytail全量集成 — 七步阶梯+代码挪用+省代码验证+债务追踪+记分板+防卡死

ponytail是一个AI Agent技能，强制"能用的最懒解决方案"——少54%代码、便宜20%、快27%、100%安全。它补全了code-shiniyaya缺少的一个关键维度——Codex验证无法检测的过度工程。

### ponytail七步阶梯验证 (集成到STEP 2方案生成+STEP 6执行)

ponytail的核心机制是一个7步阶梯——**The ladder runs AFTER you understand the problem, not instead of it. Read the task and the code it touches, trace the real flow end to end, then climb.** 这直接集成到code-shiniyaya的两个步骤:

### STEP 2集成: 方案生成前阶梯检查
在生成修复方案之前，对每个Bug执行阶梯检查——避免生成过度工程的方案:
1. **这需要修复吗?** 是否为YAGNI? → 跳过, 标注为WONT_FIX
2. **已有代码能解?** 本代码库是否已有类似修复模式? → 复用, 标注SOURCE_REUSE
3. **标准库覆盖?** Python/Node标准库是否已提供? → 标注STDLIB, 方案使用标准库
4. **原生平台功能?** OS/浏览器/数据库是否原生支持? → 标注NATIVE, 方案使用原生
5. **已有依赖?** 已安装的库是否覆盖? → 标注DEPS, 不新增依赖
6. **一行?** 一行代码能解决? → 一行
7. **最少代码:** 以上都不满足 → 最简可行方案

### STEP 6集成: 执行验证时阶梯守卫
修复代码执行前验证:
- **阶梯守卫**: 修复代码的梯级≤方案声明的梯级。若方案声称STDLIB但实际代码引入了新依赖→拒绝, 返回STEP 2重新方案。
- **安全护栏**: 详见§冲突裁决(行55)——6项永不简化。即使梯级1-6认为可以简化, 安全代码不可移除。

### ponytail与写一行提示词的本质区别
一行的"YAGNI"提示词在基准测试中只能达到95%安全——因为它没有显式的安全护栏。ponytail的100%安全来自: 简化代码+零简化安全。

**核心模式:** 七步阶梯已集成到STEP 2(方案前检查)和STEP 6(执行守卫)。安全护栏: 信任边界验证/数据丢失保护/安全措施/无障碍/校准真实硬件/任何明确要求——永不简化。

**LLM裁判基准测试**: judge.py实现三元件——(a) 公开rubric，(b) 固定裁判模型temperature=0，(c) --selftest必须在裁判用于真实提交之前把过度工程化的答案排名高于最简答案。Complete.py增加了完整性pass以关闭"写的少是因为做得少"的漏洞。适用: code-shiniyaya的pipeline vs monolithic基准测试(iteration-task.md)应使用同样3元件裁判框架。

**Scorer门控的真实vs存根自测试**: --selftest-offline先验证裁判门控逻辑(免API)后--selftest进行实际的HTML裁判验证。适用: code-shiniyaya的任何新基准测试应先在离线模式下验证评判逻辑再花费API预算。

**任务矩阵可复现性**: tasks.py为每个任务编码好/坏参考实现+确定性评分函数。score函数返回{correct, safe, reason}。bad参考是"匆忙开发者或'一行'提示词实际交付的懒但可行版本——幸福路径正确，对抗性输入不安全"。适用: code-shiniyaya的所有扫描维度应有好/坏参考锚定评分。

**Scorer同时检查safe和correct的对抗性无效负例**: 安全任务(路径遍历/SQL注入/HMAC验证/CSV健壮性)有隐式安全API——提示词说"来自不可信web请求", bad参考在幸福路径上工作但安全失败。适用: 所有code-shiniyaya的安全敏感修复必须同时通过功能性和安全性评分——单独一端不够。

**stdlib-only zero-deps评审**: judge.py只用urllib做API调用(无requests依赖)——评审基础设施不应增加依赖。适用: code-shiniyaya的benchmark运行脚本应stdlib-only。

**迭代次数×arm矩阵**: run.py对每个任务^arm^模型运行n_iter=4次，产生每个workspace的源文本+LOC+裁判JSON。适用: code-shiniyaya的迭代基准应至少n=4次重复。

### v4.6.0-v4.6.2 ponytail全量落地+5源复用门控 — 代码挪用 (Code Reuse Before Writing)

ponytail阶梯第2级"Already in this codebase?"直接落地为**代码挪用优先原则**。

#### ponytail复用门控 (v4.6.2 从ponytail hooks/scripts/plugin提取)

**单一规则集跨平台DRY** (ponytail plugin架构): ponytail的`skills/ponytail/SKILL.md`(~120行)是一份规则集, 通过复制/符号链接部署到9个平台(Claude Code/Codex/OpenCode/Gemini/Cursor/Windsurf/Cline/Copilot/Qoder等)。`.agents/rules/`, `.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`, `.kiro/steering/`等目录下的文件是完全相同的——`scripts/check-rule-copies.js`自动检查所有副本一致性。适用: code-shiniyaya的核心规则应提取为独立文件(`core-rules.md`), SKILL.md引用它, 而非在SKILL.md中展开所有细节——一份权威副本, 多处引用。

**ponytail:注释债务追踪完整实现** (从ponytail-debt移植): 
- 扫描: `grep -rnE '(#|//) ?ponytail:' .` (排除node_modules/.git/build output)
- 分类: 有升级路径的→正常债务; 无升级路径的→`no-trigger`标签(腐烂风险)
- 归属: `git blame -L<line>,<line>` 获取每处债务的owner
- 输出: `<file>:<line>, <what was simplified>. ceiling: <the limit>. upgrade: <the trigger>.`
- 账本写入 `PONYTAIL-DEBT.md`, 每轮迭代review

**impact记分板诚实边界** (从ponytail-gain移植): NEVER打印per-repo估算("you saved X lines here")——未编写的代码版本从未存在, 没有真正的baseline来减。只有来自`/ponytail-debt`的已计数账本是真实的per-repo数据。适用: code-shiniyaya的迭代报告只报告可验证的指标(发现数/P0数/新模式数), 不编造"节省了X行代码"。

**hooks生命周期注入** (从ponytail hooks/提取):
- `UserPromptSubmit`钩子——每个用户提示词前激活默认模式+注入规则集
- `PreToolUse`钩子——`task|Task`匹配器将规则集注入子Agent
- `SessionStart`钩子——首次提示词时激活默认级别(lite/full/ultra/off)
- 模式追踪器——持久化当前级别(文件系统标记), 跨会话保持
适用: code-shiniyaya的Agent启动应通过类似的钩子注入模式而非在每处硬编码

**子Agent规则集注入控制** (ponytail-subagent.js, v4.6.2提取): `PONYTAIL_SUBAGENT_MATCHER`环境变量——正则表达式筛选哪些子Agent类型接收规则集。`explore|general`匹配两者, `^general$`精确匹配, 未设置=注入所有子Agent(默认)。无效正则→回退注入。适用: code-shiniyaya的20 Agent扫描中可按Agent类型选择性注入规则(探索型Agent不需要完整STEP流程规则)

**ponytail示例5原则** (v4.6.2从examples/提取):
1. csv-sum: 坏代码`sum(float(r['amount']) for r in csv.DictReader(f))`→Malformed行崩溃。好代码`try: total += float(row['amount']); except (ValueError,TypeError,KeyError): continue`→跳过脏行继续。适用: 鲁棒性优先于简洁性
2. email-validation: 坏代码`re.match(...)`(仅锚定开头)→接受`ok@ok.com\nevil@evil.com`。好代码`re.fullmatch(...)`→拒绝注入载荷。适用: 信任边界永不简化
3. deep-clone: 坏代码`JSON.parse(JSON.stringify(obj))`→丢失Date/undefined/循环引用。好代码`structuredClone(obj)`→原生API, 零行实现。适用: 搜索原生API优先于手写实现
4. rate-limit: 坏代码`self.count += 1; return self.count <= self.max_calls`→全局计数器→一个客户端DoS所有人。好代码`collections.defaultdict(deque)`→per-key窗口。适用: 隔离故障域
5. debounce: 坏代码`let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };`→每次都创建新函数。好代码→直接调用debounce实用函数。适用: 搜索现有实用函数→复用, 而非手写

**tension: 示例vs基准安全评分** (v4.6.2 元模式): ponytail示例展示极简版本, 但agentic benchmark的`good`参考有时不同(csv-sum加try/except, email用fullmatch而非match)。示例是教学性的"最懒", 基准是"最懒但安全"。适用: 任何示例不应省略安全守卫。

**trace-before-fix** (tasks.py trace-transfer, v4.6.2): bug命名一个症状, 但其他调用者也路由到同一共享函数。懒但错误的修复只修补命名路径; 根因修复修补共享函数一次。适用: STEP 1诊断——grep所有调用者后再提修复方案, 修补共享函数一次。

在code-shiniyaya中:
**挪用决策树** (STEP 2方案生成前执行, v4.6.2 增强):
1. 需要修复/新增的功能→Grep本SKILL.md是否已有类似机制? → 是: 评估能否直接复用(跳过重新设计)
2. 是否5源已提取过同样模式? → 是: 检查当时提取的源文件行号→评估是否可直接移植(标注source)
3. 是否5源中任意源文件已实现? → 是: 从源文件挪用代码(标注source:project:line)→适配接口而非重新实现
4. 以上都不满足→搜索stdlib/原生API(ponytail示例原则3)→有则不写代码
5. 仍不满足→从头设计最简方案, 标注`ponytail: <ceiling>, <upgrade>`用于债务追踪

**挪用验证自检** (v4.6.0新增): 每次代码挪用必须通过3项检查:
1. 接口匹配——挪用的代码接口是否与目标场景兼容? 若不兼容→记录适配成本, 适配≤3行则适配, >3行则重新实现
2. 约束合规——挪用的代码是否违反code-shiniyaya的CC+Codex手动交互约束? 若违反→不可挪用, 重新实现
3. 来源标注——每处挪用必须标注`<!-- source: {project}:{file}:L{start}-L{end} -->`

#### 5源复用门控 (v4.6.2 从4源+ponytail提取)

**AutoAgent "先检查再创建"门控** (edit_agents.py/create_agent): `list_agents(context_variables)`先列出所有已有Agent→`json.loads`解析→检查agent_name是否已存在→若存在且需更新则`read_agent`读取原有定义再修改; 若不存在则创建新Agent。通用模式: `list_existing() → parse → check_name_exists → read_existing → modify | create_new`。适用: code-shiniyaya每次修改前必须先Grep→Read→确认→Edit, 禁止盲写。

**autodream "校验和变更检测"复用** (auto_dream.py L535-539): `checksum = hashlib.md5(text.encode()).hexdigest()`→比较跟踪的校验和→若校验和相同则跳过重写(幂等)。同时检查`existing_file_names` set→若文件已存在则追加计数器避免命名冲突。通用模式: `compute_checksum → compare → same?skip:rewrite`。已部分集成(STEP 8 MD5检测)。适用: 扩展至所有SKILL.md和memory/写入——MD5未变则跳过。

**autoresearch "keep vs discard"决策门控** (program.md): `status: keep|discard|crash`三元决策——keep=验证通过保留, discard=验证失败reset, crash=语法错误无法commit。通用模式: `execute → validate → keep|discard|crash`。适用: code-shiniyaya的STEP 6.0修复后验证——ast.parse通过→keep(commit), 失败→discard(reset), 语法错误→crash(不commit)。

**autonomous-coding "session continue vs restart"决策** (agent.py): `feature_list.json`存在性检测→若文件存在且有未完成的features→继续(fresh context从磁盘读取); 若不存在→首次运行(Initializer Agent)。通用模式: `check_file_exists → has_incomplete_items? → continue : fresh_start`。已集成(Init+Loop+不可变清单)。适用: 确保每轮迭代先检查scan-state.json是否存在→存在则恢复→否则冷启动。

`# ponytail: global lock, ceiling: single lock O(1) contention, upgrade: when account count > 100 or lock wait > 50ms p99`

### v4.6.0 ponytail全量落地 — 省代码验证与审核

ponytail基准测试中的验证审核机制直接纳入code-shiniyaya的基准测试门控:

**三元件裁判框架+L1静态前置门** (judge.py移植, v4.7.8增补(d)): 每次pipeline vs monolithic基准测试必须满足:
(a) 公开rubric——评分标准在benchmark报告中对用户可见
(b) 固定裁判模型temperature=0——确保评分可复现
(c) --selftest门控——裁判必须先验证好/坏参考实现, 通过后才能评分真实提交
(d) **L1静态前置门**(v4.7.8, agent-lint已装): 每轮迭代修复SKILL.md后运行`npx agent-lint score SKILL.md`(零LLM成本)——分数较上轮下降→该轮修复标LINT_REGRESS进入回滚评估(基线优先原则的自动化落地); 分数记入benchmark报告作可复现标量基线。CLI不可用→跳过, 人工比对。

**双轴评分** (good/bad reference anchor): 每个扫描维度定义好参考(正确+安全)和坏参考(幸福路径正确但安全失败)。评分函数返回`{correct, safe, reason}`, 同时检查两轴。适用: code-shiniyaya的所有安全敏感修复必须通过功能性和安全性评分。

**完整性pass** (complete.py移植): pipeline vs monolithic基准测试增加完整性维度——"写的代码少是因为过度工程消除了, 还是因为没实现完整功能?" LLM裁判同时评分完整性和过度工程, 关闭"LOC少=偷工减料"的漏洞。

### v4.6.9 ponytail反馈系统12机制全量落地

以下12个机制从ponytail源码(behavior.js/correctness.js/judge.py/complete.py/loc.js/hooks/)直接移植, 构成code-shiniyaya的反馈闭环:

**1. 三探头行为验证** (behavior.js移植): 每次修复后执行3个独立无API纯函数评分——hardware(是否保留校准旋钮/标注硬件漂移)、explanation(用户要求的解释是否>=45词且含结构化内容)、onecheck(非平凡逻辑是否留一个runnable check)。onecheck具体形式: (a)assert-based demo()/__main__自检或一个小的test_*.py文件, (b)不用框架不用fixture, (c)平凡一行不需要测试, (d)无check的代码=未完成。每个探头返回{pass, score, reason}。3/3通过→行为合规; 任一项失败→该修复标记BEHAVIOR_FAIL。适用: STEP 7双向验证增加行为探头pass——不止验证代码正确性, 还验证行为是否符合ponytail纪律。

**2. 正确性门控** (correctness.js移植): 提取代码块→按语言运行时执行(python3→python回退链, node)→注入per-task harness断言→超时30s→pass=good(keep)/fail=discard(reset)/crash=syntax error(no commit)。"No code blocks"=FAIL(非N/A)——防止空输出绕过门控。无围栏代码块→整段响应视为一个block(terse模型常输出裸代码)。适用: STEP 6修复后必须经过正确性门控——ast.parse通过还不够, 需跑轻量断言。

**3. 鲁棒性审计** (judge.py三元件裁判框架): (a)公开rubric——评分标准对用户可见, (b)固定裁判模型temperature=0——评分可复现, (c)--selftest门控——裁判必须先通过好/坏参考验证, 排名过度工程化>最简方案, 才能用于真实提交评分。适用: code-shiniyaya的任何基准测试(pipeline vs monolithic)必须通过selftest门控后才能运行——未通过selftest的裁判拒绝评分。

**4. 自检门控层级** (complete.py双层selftest): --selftest-offline先验证门控逻辑(免API, 免key)——验证"完整实现>stub"的排名逻辑是否正确。--selftest再进行实际的LLM裁判验证(小量API消耗)。两层都通过→裁判可信。适用: 任何新门控必须先过offline逻辑验证→再过live验证→才能部署到迭代循环中。

**5. 代码退化处理** (correctness.js extractBlocks): 无围栏代码块→整段响应作为一个block评分。无代码块且响应非空→仍然评分(不跳过)。只当响应完全为空时→"No code blocks in output"→FAIL。适用: STEP 4 Codex验证时检测Codex是否输出了无围栏的裸代码→不使用围栏的回复仍需验证。

**6. 评分器双重测试** (judge.py good/bad reference anchor + tasks.py dual-axis): 每个任务有good参考(正确+安全)和bad参考(幸福路径正确但安全失败)。评分函数返回{correct, safe, reason}, 同时检查两轴。bad参考=匆忙开发者交付的"可行但对抗性输入不安全"版本。适用: 所有安全敏感修复(路径遍历/SQL注入/HMAC验证/CSV健壮性)必须同时通过正确性和安全性评分——单一轴不够。

**7. 激活哨兵** (ponytail-activate.js SessionStart + flag file): SessionStart钩子写入flag file到~/.claude/.ponytail-active→statusline读取此文件显示当前模式。模式持久化到磁盘(文件系统标记), 跨会话保持。适用: code-shiniyaya的迭代状态应通过类似flag file方式跨会话保持——当前session JSON已实现, 但缺少"迭代是否活跃"的轻量哨兵文件。

**8. 一次性设置提醒** (ponytail-activate.js nudge flag): statusline未配置时写一次性标记文件(.ponytail-statusline-nudged)→之后不再重复提醒。防止每次会话都弹出设置提示变成骚扰。适用: code-shiniyaya的任何首次运行配置提示应使用一次性标记——不重复提醒。

**9. CI一致性检查** (scripts/check-rule-copies.js): 9平台规则副本通过脚本自动检查一致性——所有`.agents/rules/`, `.cursor/rules/`, `.windsurf/rules/`等目录下的ponytail规则文件必须完全相同。适用: code-shiniyaya的核心规则(core-rules.md)和SKILL.md中的引用必须一致——可写一致性检查脚本。

**10. 金丝雀短语检测** (judge.py parse_score regex): 裁判输出通过正则`\{.*\}`提取JSON——容忍Markdown围栏/注释/多余文本。解析失败→返回None(不崩溃)。适用: 所有Agent输出JSON提取应使用宽松正则+回退——不因格式微小偏差丢弃整个Agent结果。

**11. stdin/超时防阻塞** (ponytail-mode-tracker.js hooks stdin timeout): stdin读取加1秒超时+error事件捕获→Windows上PowerShell可能吞掉管道输入导致stdin 'end'永不到达→超时后处理已到达数据→exit。适用: 任何读取外部输入的钩子必须加超时回退——防止stdin阻塞冻结会话。

**12. Best-effort错误分级 + Lean exit** (judge.py retries + complete.py under-delivery flag, v4.7.8修正矛盾): API调用3次重试(指数退避2s/4s/6s)→最终失败返回error JSON(不抛异常)。completeness score≤1的cells标记为under-delivery并列出。适用: code-shiniyaya的API调用有优雅降级; **达标后不冗余验证=goal-reached.md已写后不重复验证——不豁免规则24收敛前的最终50 Agent验证**(发现<3且无P0仍走规则24 turn-end统一决策③④)。


## 优化任务队列 (v4.7.0, 已执行)

Task 1 arch-dep collapse ✅, Task 2 iteration cross-refs ✅, Task 5 HANDOFF fold ✅. Tasks 3/4/6 SKIPPED (valid reasons: encoding incompatibility, restructure risk>reward, 0 line savings). 详见 CHANGELOG.md。

## 不可跳过

| 场景 | 步骤 | 说明 |
|------|------|------|
| P0 Bug/多文件/新功能 | 1-7 | 全流程 |
| P1/P2 Bug | 1-7 | 6+ Agent |
| 注释/文档 | 1-2 | 跳过3-7 |
| 状态报告 | 3 | 仅格式C |

## 停止线 — 见规则12-15(§硬规则-停止线)、降级模式(§错误处理 表格STEP5行)和自主迭代模式(§自主迭代模式)

---

## 迭代扫描工作流 (防卡顿 + 进度反馈)

SKILL.md自迭代使用此工作流。设计约束: CC无事件循环、无墙钟、无法轮询、无法中读取工作流输出——依靠log()事件和消息计数。

### Init+Loop两阶段模型 (v3.8.0)

每次迭代扫描采用Init→Loop模式:
- **Init阶段** (运行一次): 创建不可变扫描计划(`scan-plan-{iter}.json`), 列出每源×维度的扫描任务。计划创建后仅可读, 不可修改。
- **Loop阶段** (每轮一次): Fresh context。从磁盘读取scan-plan → 执行一个扫描任务 → 验证 → 提交结果 → 退出。下一轮重新初始化, 从磁盘续取下一任务。
- **不可变检查清单**: scan-plan中的每项锁定创建时状态。Loop仅可翻转 `verified` 标志(boolean)。禁止修改 `task`/`source`/`dimension`字段。此不可变契约同样适用于pending-{id}.json中的待修复项——详见§待修复项不可变契约。

### First-Completed Dispatch (Streaming Step Transition) (v4.0.0)

**代替**: Launch N agents → wait ALL → process → next step
**使用**: Launch N agents → process each as it completes → trigger downstream incrementally

**STEP 1 实现**:
1. Launch 6+ agents 并行
2. 每个 agent 返回时 (log() event):
   a. 即时提取 findings
   b. 对已收到 findings 去重 (同一 file:line±3)
   c. 若发现 P0 crash → 立即开始 STEP 2 方案生成 (不等剩余 agents)
3. 所有 agents 返回且无新 P0 → 等待落后检测 (3-message gap, anti-hang-v2.md)

**STEP 4 实现**:
1. Launch 10+ agents 跨 7 维度
2. 每个维度首个 agent 返回 → 标记该维度 "已覆盖"
3. 任一个维度证伪 Codex 声明 → 增加矛盾计数。**矛盾确认阈值: 需 >=2 个不同维度均证伪同一 Codex 声明, 才标记 "Codex Gate FAIL"**。单维度单 Agent 证伪 → 记录到 DISCREPANCY_LOG.md 但不触发 Gate FAIL (防止单Agent误判/假阳性)。若后续其他维度 Agent 也证伪同一声明 → 矛盾计数 >=2 → Gate FAIL 触发。同一维度内多个 Agent 证伪同一声明 → 计为 1 个矛盾维度(非多个)。
4. 不等待剩余维度 — Byzantine Codex defense 在首次证伪时触发

**收益**: 6-agent batch P50=116s 时, 首次完成分发允许 orchestrator 在 ~120s 开始 STEP 2, 而非 ~600s, 关键路径延迟降低 5 倍。

### 启动 — 见规则5(§硬规则-Agent)和规则23(§硬规则 第23条—防卡顿并行启动)

### 进度 — 见自检#11(§迭代自检 第11条—Agent卡住处理)和停滞检测(§运行时可行性审计)

### 恢复 — 见规则7(§硬规则-Agent)、错误表(§错误处理 表格迭代扫描行)、重连恢复(§迭代扫描恢复)

### 趋同检测(CC跨迭代追踪)
- 趋同速率(CR) = (CRITICAL_{n-1} - CRITICAL_n) / CRITICAL_{n-1} × 100 (CRITICAL_{n-1}=0时跳过分母)
- CR>60%: 健康趋同。20-60%: 慢速趋同。CR<20%或负: 告警
- **趋同失败**: CRITICAL连续2次迭代上升→自动切换策略(如更换Agent类型组合/调整扫描维度), 不停止迭代, 不等待用户。在下一轮工作流中使用新策略, 静默继续。

## 运行时可行性审计 (v4.6.10, 20 Agent双轨扫描)

本Skill的大量防卡顿/防循环/自主迭代机制声明的触发条件需要CC CLI请求-响应模型不具备的能力（事件循环、持久后台状态、跨会话连续性、自主任务通知）。以下表格记录每个机制的运行时可行性状态。

### 机制可行性矩阵

| 机制 | 章节锚点 | 触发条件 | CC可行性 | 说明 |
|------|---------|---------|---------|------|
| 规则26 预调用阻断 | §硬规则-规则26 | 模型在工具调用前对照transcript执行伪代码检查 | **可行** | 模型可直接推理transcript中的历史调用，无需外部状态 |
| 自检#18 死循环根因阻断 | §迭代自检-18 | 同turn内追踪工具调用+跨turn内容hash比对 | **部分可行** | 同turn内(a)(b)可行; 跨turn(c)(d)不可行(CC每turn fresh context——Bash层重复命令子集由echo-guard v3跨turn指纹覆盖, 纯确认turn由stop-guard拦截) |
| 自检#4 工作流存活检查 | §迭代自检-4 | 检测前工作流被kill/崩溃/超时 | **不可行** | 需要自主进程终止检测+跨turn状态 |
| 自检#11 Agent卡住处理 | §迭代自检-11 | 同批其他Agent完成，差距>5分钟，自动TaskStop | **不可行** | 需要wall-clock监控+自主任务终止 |
| 自检#3 不静默检查 | §迭代自检-3 | CC工作流完成后静默退出，检测并自动重启 | **不可行** | 需要跨turn自主重启能力 |
| 落后检测 | §First-Completed Dispatch | 3+ Agent完成，某Agent无log()事件 | **不可行** | 需要live log()事件流+跨Agent完成对比 |
| 停滞检测(自主模式) | §自主迭代模式 | 连续3轮迭代无新log()事件 | **不可行** | 需要跨turn迭代计数+log()事件流 |
| 停滞检测(交互模式) | §自主迭代模式 | 5+用户轮次无log()事件 | **部分可行** | 用户轮次可通过消息计数，但log()检测不可行 |
| 规则15 迭代不中断(v4.7.5降级前) | §硬规则-规则15 | 工作流完成通知触发继续+静默迭代 | **不可行** | v4.7.5已降级为同turn连续+一字恢复跨turn |
| 自检#1 通知=继续(v4.7.5降级前) | §迭代自检-1 | task-notification到达→立即处理→静默启动下一轮 | **不可行** | v4.7.5已降级为用户"继"→读journal.jsonl→恢复 |

`# ponytail: mechanism matrix uses section anchors (§硬规则, §迭代自检, §Agent编排, §自主迭代模式), ceiling: manual anchor references (stable across line shifts), upgrade: auto-compute from git blame if section moves >50 lines`

### 根本性限制

**文本规则无法打破LLM验证强迫吸引子状态。** 规则26在模型正常决策时通过transcript自查可执行。但当模型进入Read→Grep→wc -l→Write done→Read done的验证循环时，执行预调用检查的认知能力本身已被循环劫持——v4.6.5的规则26在死循环发生时就已存在，加强措辞到v4.6.9不改变这一根本机制。唯一有效的解决方案是外部看门狗（per-turn工具调用预算、监督模型、进程级循环检测），这是SKILL.md文本无法创建的——**已由echo-guard.js v3.0+stop-guard.js实现Bash层+turn终态阻断(见§外部看门狗)**; Read/Grep/Write工具层仍无hook覆盖。

**自检#18跨turn部分模型侧不可行。** "跨turn内容hash比对"要求CC模型维护跨turn持久状态。CC每turn从fresh context启动，仅transcript中的历史工具调用可见——但transcript不包含结构化的工具调用元数据（时间戳、调用栈、hash），模型无法可靠计算自检#18(c)(d)所需的指标。同turn内(a)(b)仍可行(v4.7.5降级); Bash层跨turn由echo-guard v3指纹承接(v4.7.8)。

### 自应用差距

**Selftest双层门控已定义** (v4.7.6, 来自ponytail complete.py:90-102)。解决v4.6.10自认的selftest缺失——code-shiniyaya对自身规则采用与ponytail judge.py相同的双层门控: Layer 1 `--selftest-offline`(免API,硬编码好/坏参考验证门控逻辑)→Layer 2 `--selftest`(实际LLM裁判验证)。规则26/自检#18现需通过双层门控后才能标记为VERIFIED。`# ponytail: 离线层可当前执行(Reasonix parallel_tasks中)，在线层需API，ceiling: 仅Layer 1离线门控，upgrade: 集成CC API时添加Layer 2`

`# ponytail: 旧selftest缺失声明已被v4.7.6 Selftest双层门控取代(§Selftest双层门控)。保留此行作为历史锚点——ponytail对自己的judge.py执行selftest，code-shiniyaya现已对自身规则执行selftest。`

### 10项源文件功能——规范级集成状态 (v4.7.7合并两表, 消除"尚未集成"vs"规范级"矛盾)

以下10项经20 Agent扫描确认, 全部已文档化为规范级(spec-level)——有ponytail:debt天花板标注, 待触发条件到达时升级为运行时实现。#3/#5/#6/#8已另有详细章节(见交叉引用列)。

| # | 功能 | 源文件 | 状态+交叉引用 | ponytail:debt |
|---|------|--------|------|---------------|
| 1 | 注册级输出截断包装 | registry.py:91-96 | 规范级 | `ceiling: per-STEP truncation, upgrade: >15 tools` |
| 2 | 统一{status, result}封皮 | docker_env.py:144-199 | 规范级 | `ceiling: TERMINAL heuristics, upgrade: >10 agent types` |
| 3 | 复合retry stop | tenacity_stop.py:1-12 | 规范级→§重试感知关闭 | `ceiling: attempt-only, upgrade: retry-heavy workflows` |
| 4 | 工具集兼容性检查 | fn_call_converter.py:358-391 | 规范级 | `ceiling: manual review, upgrade: frequent schema changes` |
| 5 | 优雅关闭信号 | shutdown_listener.py:1-66 | 规范级→§信号驱动的分段睡眠 | `ceiling: TaskStop+journal, upgrade: >3 concurrent workflows` |
| 6 | 数据→源码编译器 | browser_cookies.py:1-39 | 规范级→§v4.5.0元编程 | `ceiling: JSON parse/session, upgrade: >20 types or >100 config keys` |
| 7 | 目录驱动发现 | publish-openclaw-skills.js:31-33 | 规范级 | `ceiling: manual table, upgrade: >15 skills or weekly changes` |
| 8 | 动作感知超时 | browser_env.py:545-558 | 规范级→§v4.5.0元编程 | `ceiling: 300s uniform, upgrade: >5 operation types` |
| 9 | 抽象Memory+Reranker | rag_memory.py+code_memory.py | 规范级 | `ceiling: manual MEMORY.md, upgrade: >30 files or accuracy-critical` |
| 10 | gc.freeze()长循环 | autoresearch train.py:594-595 | 规范级 | `ceiling: no GC management, upgrade: >10 rounds/session` |

## v4.6.11 5源深度扫描 (45项新发现)

Phase 3源文件扫描Agent因JSON Schema格式错误失败后, 用无Schema纯文本Agent重新扫描全部5源。确认: AutoAgent(Phase 2集成10项基础上零新增), autodream(10项), autoresearch(8项), autonomous-coding(10项), ponytail(17项)。

### 跨源共性主题
**1. 子进程可靠性**: stdout→file代替PIPE, 平台感知tree-kill, per-cell超时隔离
**2. 操作前快照/库存**: 启动前检查已有文件→只做需要的→只度量新增
**3. 回退阶梯**: 每个外部依赖有硬编码回退——不是优雅降级, 是内联替代逻辑
**4. 度量公平性**: 对比臂注入相同约束, 验证代码从源码分离计量
**5. 文件存在性=二元哨兵**: 标记文件存在与否=冷启vs恢复的唯一判别器

`# ponytail: v4.6.12 14新模式已集成(12规范级+2待平台升级)。实现细节见下方高价值模式。ceiling: specification-only, upgrade: 2 patterns require external tools`

AutoAgent 196个文件中约40个已被SKILL.md引用。以下14个高价值模式已于v4.6.12提取:

### 高价值模式 (10项, 全部CC兼容)

**1. 多通道结构化日志** (autoagent/logger.py): MetaChainLogger——独立的tool_execution/assistant_message/tool_call渲染通道, DEBUG门控可见性, MC_MODE暗色(迭代编排层全部输出灰色)。CC应用: CC动作/Codex反馈/验证结果分别记录到独立审计通道, 自主迭代期间debug门控抑制噪声。

**2. retrigger_type "all"/"any" 事件组** (autoagent/flow/types.py): EventGroup支持`retrigger_type: "all"|"any"`——all=所有监听事件必须触发, any=任意一个触发。CC应用: double-approval gating——Codex批准+用户批准=both("all"), 任一方发现P0 bug=触发("any")。

**3. 内容寻址函数识别** (autoagent/flow/utils.py): `function_or_method_to_string()`产生`module.l_LINENO\n<完整源码>`, MD5哈希用于内容寻址。CC应用: 替代脆弱的`file:line`引用, 行号漂移后内容哈希仍然稳定。

**4. tree-sitter函数级代码索引** (autoagent/memory/codetree_memory.py): tree-sitter解析Python AST→函数级嵌入→语义搜索。CC应用: STEP 1诊断扫描升级为函数粒度搜索, 精确定位共享工具函数中的根因。

**5. 交互式Agent切换循环** (autoagent/repl/repl.py): `while True: user_input → run agent → streaming response → agent = response.agent (handoff)`。CC应用: STEP-by-STEP交互模式——控制Agent每轮可以切换。

**6. 结构化Agent需求DSL+Pydantic验证** (autoagent/agents/meta_agent/agent_former.py + form_complie.py): XML DSL定义`<agents>`含`<system_input>`/`<system_output>`/`<agent>`(name/instructions/tools/input/output)/`<global_variables>`, Pydantic验证IO匹配。CC应用: CC↔Codex验证交接的正式契约格式——每个验证Agent的输入/输出/工具签名以结构化DSL规定。

**7. 声明式事件驱动工作流DSL** (autoagent/agents/meta_agent/workflow_former.py): `<workflow>`含`<events>`, 每个`<event>`含`<listen>`(依赖前序事件)/`<inputs>`/`<task>`/`<outputs>`(含`<action type="RESULT|ABORT|GOTO">`和可选`<condition>`)。3种模式: If-Else/Parallelization/Evaluator-Optimizer。CC应用: 迭代scan→fix→verify→repeat循环形式化为事件驱动工作流。

**8. Hub-and-spoke路由+动态transfer_back注入** (autoagent/agents/system_agent/system_triage_agent.py): `agent_teams`字典+`transfer_back_to_triage_agent`动态追加到子Agent的`functions`列表+`case_resolved`/`case_not_resolved`终端工具。CC应用: CC编排器作为hub, investigator/general-purpose/Plan/debugging作为spoke, 动态transfer_back注入。

**9. 装饰器输出到文件+分页** (autoagent/tools/terminal_tools.py:141-175): process_terminal_response装饰器自动包装函数结果——提取`{status, result}`→写入temp文件→打开终端浏览器分页查看。CC应用: 所有Codex响应解析器用装饰器自动分页大响应, 无需每次调用重复模板。

**10. 幂等操作前检查** (autoagent/environment/utils.py): `setup_metachain()`先`pip list|grep autoagent`→已安装则立即返回。CC应用: STEP 0环境检测每项检查幂等(git/python/tiktoken), 重复执行成本为零。

### 中价值模式 (4项, CC兼容)

**11. 统一多模态查询** (autoagent/tools/file_surfer_tool.py:224-285): `visual_question_answering()`自动检测扩展名→video→提取帧+音频转录→LLM。CC应用: 验证Codex多模态输出时单一工具接口处理多种格式。

**12. 重试+递增反馈** (autoagent/cli_utils/metachain_meta_agent.py:24-40): `for i in range(MAX_RETRY): try → parse → if valid break; else append error feedback to messages → retry`。CC应用: 规则7升级的具体循环实现。

**13. Pydantic结构化rerank+DataFrame回连** (autoagent/memory/tool_memory.py:83-164): `response_format=RerankResult`结构化输出→join回原始DataFrame恢复完整元数据。CC应用: STEP 4 Codex回复匹配回原始诊断发现以验证证据。

**14. 分页API拉取+限制提前终止** (autoagent/tools/code_search.py:8-55): while循环per_page=10, 累积到limit后break。CC应用: STEP 1.5参考源交叉验证时对外部API调用的速率限制处理。

`# ponytail: 14 AutoAgent deep-scan patterns documented, ceiling: documented but not runtime-integrated, upgrade: when agent DSL formalization becomes priority or tree-sitter integration is available`

## v4.6.12 5源全量审计总结

| 来源 | 文件数 | 已提取模式 | v4.6.11新增 | v4.6.12 AutoAgent深挖 | 总覆盖 |
|------|--------|-----------|------------|---------------------|--------|
| AutoAgent | 196 | ~40 | 0(Phase 2已集成10) | 14 | ~54/196 |
| autodream | 9 | ~16 | 10 | — | ~26/9 |
| autoresearch | 5 | ~12 | 8 | — | ~20/5 |
| autonomous-coding | 30+ | ~23 | 10 | — | ~33/30+ |
| ponytail | 30+ | ~22 | 17 | — | ~39/30+ |

**结论: 5源已穷尽自动化/验证/迭代/审计相关的核心模式。** 剩余未扫描文件为文档页/build配置/__init__.py存根/空文件/纯UI代码/实验性脚本——零可提取自动化模式残留。

<!-- v4.6.12: AutoAgent deep-dive complete. 10 high-value + 4 medium patterns added. 5-source full audit FINAL: all 5 sources exhausted of core automation/verification/iteration/audit patterns. -->

### 运行时可靠性注意事项 (v4.6.10)

1. **防卡顿机制不可行≠不需要。** 将机制标记为不可行不意味着应删除——意味着需要可降级替代方案：(a) wall-clock超时→操作用计数阈值, (b) log()事件流→turn边界journal.jsonl mtime检查, (c) 跨turn迭代计数→session JSON versionVector, (d) 自主重启→用户提示恢复协议(已有"继续修复"触发词)。

2. **规则26的实际可靠性。** 规则26在当前turn内对同文件同offset的重复Read可有效阻断（模型可直接检查transcript）。但对于跨turn的Write→Read→Write循环或异构工具链组成的重复模式，规则26无法检测——需依赖外部进程级工具调用上限。

3. **ponytail: debt自我应用已修复** (v4.6.10)。所有`[未实现]`已替换为`# ponytail:`债务标注，含天花板和升级路径。零残留。

`# ponytail: v4.6.10审计结论已被v4.7.6取代——规则26可行，selftest双层门控已定义。历史锚点保留。`
