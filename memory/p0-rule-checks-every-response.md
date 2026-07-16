---
name: p0-rule-checks-before-every-response
description: 每次回复前强制执行全部规则检查，报告执行状态和违规纠正方案
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 最高规则 — 每次回复前强制执行

## 规则

**CC在每次产生文本/工具调用之前，必须先执行完整的规则检查，并在回复中报告状态。**

如果跳过检查或在检查通过后违规（如未经审批修改源码），必须在下一轮立即纠正（回退+报告）。

## 检查模板（每轮输出）

```
规则自检:
✅ 已执行: [...]
❌ 未执行: [...] 
违规纠正: [如上一轮有违规，报告纠正结果]
```

## 18项活跃规则

### Block A: 协作协议 (P0双批准)
1. [[p0-dual-approval-before-code-edit]] — 修改源码前需用户+Codex批准
2. [[p0-cc-no-solo-edits]] — CC不得在未获Codex确认时修改源码
3. [[p0-codex-bidirectional-verification]] — 修改前发方案→Codex确认→执行→发结果→Codex验证
4. [[p0-codex-evaluation-must-verify]] — Codex方案必须10+Agent验证
5. [[p0-deep-analysis-before-execute]] — 收到指令先独立深度分析
6. [[p0-copyable-codex-text]] — Codex交互附带可复制纯文本

### Block B: 三Skill协同
7. [[p0-triple-skill-workflow]] — OpenSpec+multi-agent+superpowers三位一体
8. OpenSpec — 修改前→change/create/proposal/design/tasks
9. multi-agent-shiniyaya — 8 Phase工作流(batch_size=16)
10. using-superpowers — 每轮开始检查skill适用性

### Block C: 技术约束
11. [[domestic-api-only]] — 仅国内API, 无需VPN
12. [[codex-fix-verification-rule]] — Codex修复后CC独立验证
13. [[codex-cross-verification-rule]] — 代码修改前强制Codex审查
14. [[symbol-impact-analysis-and-change-mapping]] — 改符号必须跑影响分析
15. [[task-feedback-per-item]] — 每完成一个任务立即反馈
16. [[caveman-token-compression-enabled]] — Token压缩

### Block D: 输出
17. [[reports-output-to-desktop-folder]] — 报告→桌面报告文件夹
18. [[p0-rule-compliance-checklist]] — 本规则

## 违规追溯

如上一轮存在违规修改：
- 识别commit → `git revert` → `git push --force`
- 标记v8.1.0 tag到前一个正确commit
- 报告纠正结果

## 关联
- [[p0-triple-skill-workflow]]
- [[p0-dual-approval-before-code-edit]]
- [[reports-output-to-desktop-folder]]
- [[p0-rule-compliance-checklist]]
