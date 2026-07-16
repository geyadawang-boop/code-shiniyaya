# code-shiniyaya — CC↔Codex 双向验证元编排 Skill

## 是什么

code-shiniyaya是Claude Code的元编排Skill,不做代码修改——而是编排CC与Codex之间标准化的双向验证闭环。当用户需要诊断bug、审查代码、或验证修复方案时,code-shiniyaya启动7步闭环工作流,将CC的多Agent诊断能力与Codex的独立验证能力结合,通过双批准门控确保修复安全可信。

**核心理念**: CC负责深度诊断(读取源码+6+ Agent并行扫描), Codex负责独立验证(交叉检查CC方案), 双方都批准后才执行。这不是"让AI写代码"——这是"让两个AI系统互相验证对方的工作"。

## 功能概览

### 核心工作流 (7步闭环)
1. **诊断扫描** — 6+ Agent并行, 5种类型(investigator/Explore/general-purpose/Plan/debugging)
2. **方案生成** — P0/P1/P2分级, 多方案对比选最优
3. **Codex可复制文本** — 消毒后的纯文本格式, 中英文+术语
4. **Codex反馈交叉验证** — 10+ Agent跨7维度验证Codex回复
5. **双批准门控** — CC批准+Codex批准=执行, 单方禁止
6. **逐项执行** — Git状态机 + DAG依赖追踪
7. **双向验证** — CC↔Codex互相确认, 争议升级至用户裁决

### 26条硬规则
- 门控规则: 双批准/CC不独立修改/分析自由修改阻断/逐项反馈
- Agent规则: 动态batch_size/语法门控/3层重试升级/无共享文件
- Plan-Code Gap规则: 代码=方案验证/方案锁定/盲写禁止
- 停止线: 3次失败崩溃分类/stop立即停/Write成功不Read
- 还有自主迭代/双轨修复/趋势确认/收敛阈值等高级规则

### 自主迭代模式
触发词: 循环迭代/自动更新/自动迭代/自主执行/不中断/持续修复/自动扫描修复/优化skill/根据源文件优化

进入模式后: 生成迭代计划→用户审阅→批准后自主执行、不中断、不等待、直到零bug收敛或用户说停。

### 10 Skill协同开发栈
开发code-shiniyaya自身时,10个Skill全部强制激活:
- code-shiniyaya(编排器) > ponytail(极简主义者) > using-superpowers(强制触发守卫) > caveman(输出压缩) > ponytail-review/audit/debt/gain/help(审查层) > openspec-explore(探索模式)

### 5源模式库
从5个开源项目提取约172个自动化/验证/迭代/审计模式:
- **AutoAgent** (196文件): 事件驱动控制流/GOTO-ABORT/3层重试/Agent工厂
- **autodream**: MD5变更检测/孤儿检测/Learn+Consolidate双重反思
- **autoresearch**: NEVER STOP指令/Git状态机/崩溃分类/固定预算
- **autonomous-coding**: Init+Loop两阶段/不可变检查清单/三层安全模型
- **ponytail**: 七步阶梯验证/债务追踪/三元件裁判/双轴评分/行为探头

### 运行时反馈系统 (12机制)
从ponytail源码移植: 三探头行为验证/正确性门控(keep-discard-crash)/鲁棒性审计(公开rubric+t=0+selftest)/双层selftest门控/代码退化处理/双轴评分(correct+safe)/激活哨兵/一次性提醒/CI一致性检查/金丝雀短语检测/stdin超时防阻塞/Best-effort错误分级+Lean exit

### 30条ponytail:debt标注
所有有意简化或暂未实现的功能都有`# ponytail: <ceiling>, <upgrade path>`标注,可被ponytail-debt扫描收获。

## 安装

```bash
# 复制SKILL.md到桌面code-shiniyaya目录
cp SKILL.md C:\Users\<用户名>\Desktop\code-shiniyaya\

# CC启动时自动加载(从SKILL.md的triggers字段匹配)
```

## 触发

57+中文/英文触发短语,9个类别:
- A. 发送: "告诉codex", "发给codex", "让codex分析", "codex帮我看下"...
- B. 验证+审查: "双重检验", "codex交叉验证", "codex review", "对敲代码"...
- C. 协作: "帮我和codex对一下", "cc和codex一起修"...
- D. 门控: "双批准", "codex审批"...
- E. 方案: "多方案对比", "deep diagnosis"...
- H. 自主迭代: "循环迭代", "自动更新", "持续修复"...

## 版本

v4.7.0 — 1549行, 30条债务标注, 已通过7轮20 Agent+交叉验证收敛到零bug。

## 许可证

MIT
