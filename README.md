# code-shiniyaya — CC↔Codex 双向验证元编排 Skill

## 是什么

code-shiniyaya是Claude Code的元编排Skill——不直接修改代码，而是编排CC与Codex之间标准化的双向验证闭环。CC负责深度诊断（读源码+6+ Agent并行扫描），Codex负责独立验证（交叉检查CC方案），双方都批准后才执行。这不是"让AI写代码"——是"让两个AI系统互相验证对方的工作"。

## 核心功能

### 7步双向验证闭环 (STEP 0-7)

| 步骤 | 做什么 | Agent数 | 门控 |
|------|--------|---------|------|
| STEP 0 | 冷启动: 三Skill前置 + 环境能力检测(git/Python/tiktoken) | — | 无 |
| STEP 1 | 诊断扫描: 6+ Agent并行, 5类型, 去重合并, P0/P1/P2分类 + grep所有调用者 | 6+ | 用户确认 |
| STEP 2 | 方案生成: 每Bug file:line+old/new代码+风险+验证命令, 多方案3 Agent对比 | 3 | 用户确认 |
| STEP 3 | Codex可复制文本: 消毒(防Bidi/零宽/控制字符), 纯文本, >20000字符分部分 | — | 无 |
| STEP 4 | Codex反馈交叉验证: 10+ Agent跨7维度(准确性/代码复用/遗漏/安全/架构/回退/执行) | 10+ | Codex验证 |
| STEP 5 | **双批准门控**: CC批准 + Codex批准 = 执行。单方禁止。降级模式: 用户单批准 | — | ⚠️阻断 |
| STEP 6 | 逐项执行: Git状态机(独立项)或DAG依赖追踪(跨文件依赖), ast.parse验证 | 1-4 | 逐项 |
| STEP 7 | 双向验证: CC→Codex→CC, 1轮完成, 仅争议时第2轮, 再有争议→用户裁决 | 6+ | 用户 |

**快速路径**: 已有完整方案→跳过STEP 1-2, 直接进入STEP 5批准。
**降级模式**: Codex连续4条消息无回复→询问; 5条→自动降级→用户单批准可执行(P0仍需CC 4 Agent验证)。

### 26条硬规则 + 18项自检

**门控**: 双批准/CC不独立修改源码/分析自由修改阻断/逐项反馈stop优先
**Agent**: 动态batch_size(max(4,min(16,cpu_cores-2)))/语法门控(ast.parse→前进→失败回滚)/3层重试升级(同类型→同类型+反馈→general-purpose)/无共享文件
**Plan-Code Gap**: git diff+grep -n双验证/方案锁定(偏离→新方案+重新双批准)/Write/Edit前必须Read
**停止线**: 3次同文件失败+Type A/B崩溃分类/stop立即停保存JSON/Write成功不Read验证
**死循环阻断** (规则26, 最高优先级): 同一file+offset在第2次Read前阻断; 确认词输出无Write/Edit→阻断; Write↔Read done循环→阻断; 阻断后静默等待用户, 不输出确认信息

**18项自检**: 工作流通知=继续信号/不等待/不静默/工作流存活/循环持续/有意义迭代/任务保真/工作流时间预算/元迭代完整性/稳定性积累/任务规格锁定/Agent卡住/4源深度利用/产出物写入/4源自我迭代/源文件旋转/报告路径/死循环根因阻断

### 自主迭代模式 (9 触发词)

触发词: **循环迭代/自动更新/自动迭代/自主执行/不中断/持续修复/自动扫描修复/优化skill/根据源文件优化**

进入模式后:
1. 分析需求 → 生成迭代计划 → 写入报告目录 → 呈现用户审阅
2. 批准后(或5分钟无回复自动批准) → 自主执行
3. **不中断**: 工作流完成→处理→修复→下一轮, 不等用户
4. **不结束**: 直到零bug收敛 / 用户说停 / 预算耗尽
5. **不等待**: 绝不说"要继续吗?"
6. 每轮仅输出一行进度, 达标时输出最终签收单
7. P0安全敏感修复(数据丢失/安全漏洞/权限提升)仍触发用户中断
8. Agent失败零静默: 必须报告失败数量/原因/修复动作

### 运行时反馈系统

**三探头行为验证**: 每次修复后3个独立纯函数评分——hardware(是否保留校准)/explanation(用户要求的解释是否>=45词)/onecheck(非平凡逻辑是否留assert/demo/test, 无框架无fixture, 一行不需要测试, 无check=未完成)

**正确性门控**: 提取代码→按语言执行(python3→python回退,node)→注入per-task harness→超时30s→pass=keep/fail=discard/crash=no commit。无代码块=FAIL(非N/A)

**三元件裁判框架**: (a)公开rubric, (b)temperature=0裁判, (c)--selftest门控(裁判先通过好/坏参考验证才能评分真实提交)

**双轴评分**: 每个安全敏感修复同时检查correct+safe——单独一轴不够。bad参考=幸福路径正确但对抗输入不安全

**完整性pass**: "代码少是因为过度工程消除还是偷工减料?" LLM裁判同时评分完整性和过度工程

**自检门控层级**: --selftest-offline先验证门控逻辑(免API)→--selftest再实际裁判验证(小量API)→两层都通过→裁判可信

**代码退化处理**: 无围栏代码→整段响应作为一个block评分的; 无代码非空→仍然评分的; 仅完全空响应→FAIL

**激活哨兵**: flag file写入磁盘→statusline读取→跨会话保持; 一次性提醒哨兵→不重复骚扰

**金丝雀短语检测**: `\{.*\}`宽松正则提取JSON→容忍Markdown/注释/多余文本; 解析失败返回None不崩溃

**stdin/超时防阻塞**: 1秒超时+error捕获→Windows PowerShell吞管道输入时恢复; Best-effort错误分级: API 3次重试(2s/4s/6s指数退避)→最终失败返回error JSON不抛异常

**Lean exit**: 发现<3且无P0→跳过50-agent验证, 输出"通过, 已达标"

### ponytail:debt 债务追踪

所有有意简化或暂未实现的功能都有 `# ponytail: <天花板>, <升级触发>` 标注。运行 `grep -rnE '# ?ponytail:' .` 即可扫描全部债务, 生成 `PONYTAIL-DEBT.md` 账本。无升级路径的标记为 `no-trigger` (腐烂风险)。

当前30条债务标注, 全部有天花板+升级路径。

### Hook基础设施 (9模式)

沉默失败契约 / UTF-8 BOM剥离 / stdin超时守卫 / 一次性提醒哨兵 / Shell安全路径allowlist / 多级配置解析(env > config > default) / 平台感知配置目录 / 停用全消息匹配 / 子Agent规则集注入

### 状态机 + 原子写入

会话JSON状态文件(session/pending/DAG/budget四种), SHA-256 checksum防损坏, os.replace原子写入, versionVector并发控制, Git分支隔离(独立修复项), keep|discard|crash三分法执行日志

### 自我保护机制

- **规则26预调用阻断**: 每个工具调用前对照transcript执行阻断检查(同file+offset→阻断, 同pattern+path→阻断, 确认词无Write→阻断, done文件循环→阻断)
- **规则12崩溃分类**: Type A(琐碎)自动修复不消耗配额, Type B(根本性)消耗配额3次后终止
- **收敛阈值自调整** (规则24): 发现数<5且连续2轮<10且均为P1/P2→触发50 Agent最终确认
- **Fast-fail内联守卫** (规则25): 关键指标(NaN/超阈值)立即abort, 预热期不计统计

## 安装

将 `SKILL.md` 放入 Claude Code 可访问的路径。CC启动时自动从 triggers 字段匹配触发词。

## 触发 (57+ 短语, 9类)

| 类别 | 示例 |
|------|------|
| A. 发送 | "告诉codex", "发给codex", "codex帮我看下" |
| B. 验证+审查 | "双重检验", "codex交叉验证", "对敲代码", "codex review" |
| C. 协作 | "帮我和codex对一下", "cc和codex一起修" |
| D. 门控 | "双批准", "codex审批" |
| E. 方案/扫描 | "多方案对比", "源文件交叉验证", "deep diagnosis" |
| H. 自主迭代 | "循环迭代", "自动更新", "持续修复", "优化skill" |
| I. Agent错误 | "agent错误", "agent失败", "静默无反馈" |

## 版本

v4.7.0 — 1549行, 30条债务标注, 7轮20+ Agent交叉验证收敛到零bug, 5源~172模式全量集成。

## 许可证

MIT
