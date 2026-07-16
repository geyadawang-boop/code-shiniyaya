---
name: p0-rule-compliance-checklist
description: 每轮响应前检查所有P0规则执行状态，报告已执行/未执行
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 规则合规清单 — 每轮强制执行

每轮响应开始前，检查所有活跃P0规则的状态：

## 活跃规则清单（共18条）

### Block A: 协作协议
1. [[p0-dual-approval-before-code-edit]] — 修改源代码前必须获用户+Codex双方批准
2. [[p0-cc-no-solo-edits]] — CC不得在未获Codex确认的情况下修改源代码
3. [[p0-codex-bidirectional-verification]] — 修改前发方案给Codex确认，修改后发结果给Codex验证
4. [[p0-codex-evaluation-must-verify]] — Codex方案必须10+Agent验证
5. [[p0-deep-analysis-before-execute]] — 收到Codex指令先独立深度分析
6. [[p0-copyable-codex-text]] — 每次Codex交互附带可复制中文纯文本

### Block B: 三Skill协同
7. [[p0-triple-skill-workflow]] — OpenSpec(计划)+multi-agent-shiniyaya(执行)+using-superpowers(纪律)
8. OpenSpec — 修改前创建change/proposal/design/tasks
9. multi-agent-shiniyaya — 按8 Phase工作流执行(batch_size=16上限)
10. using-superpowers — 每轮响应前检查skill适用性

### Block C: 技术约束
11. [[domestic-api-only]] — 仅使用国内API，禁止国外端点，无需VPN
12. [[codex-fix-verification-rule]] — Codex修复后CC必须独立验证
13. [[codex-cross-verification-rule]] — 代码修改前强制Codex审查
14. [[symbol-impact-analysis-and-change-mapping]] — 改符号必须跑影响分析
15. [[task-feedback-per-item]] — 每完成一个任务立即反馈用户
16. [[caveman-token-compression-enabled]] — Token压缩65%节省

### Block D: 输出
17. [[reports-output-to-desktop-folder]] — 所有报告输出到桌面报告文件夹
18. [[p0-rule-compliance-checklist]] — 本规则 — 每轮自检

## 合规检查模板

每轮响应开头输出：
```
规则自检:
✅ 已执行: [规则列表]
❌ 未执行: [规则列表 + 原因/计划]
```

## 关联
- [[p0-triple-skill-workflow]]
- [[p0-dual-approval-before-code-edit]]
- [[reports-output-to-desktop-folder]]
