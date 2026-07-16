---
name: all-active-rules
description: BiliSum全部活跃规则一览(22条) — Block A协作6/B四Skill5/C技术6/D输出5
metadata:
  type: reference
  priority: highest
  created: 2026-07-15
  updated: 2026-07-16
---

# BiliSum — 全部活跃规则 (22条)

## Block A: 协作协议 (6条)
1. 用户+Codex双重批准 → p0-dual-approval-before-code-edit
2. CC禁止独立修改代码 → p0-cc-no-solo-edits
3. Codex双向验证 → p0-codex-bidirectional-verification
4. Codex方案10Agent验证 → p0-codex-evaluation-must-verify
5. 收到Codex指令先深度分析 → p0-deep-analysis-before-execute
6. 可复制Codex文本 → p0-copyable-codex-text

## Block B: 四Skill协同 (5条)
7. OpenSpec → 修改前创建proposal
8. multi-agent-shiniyaya → 8 Phase工作流
9. using-superpowers → 每轮检查skill
10. ponytail ⭐NEW (2026-07-16) → 所有代码任务用最简可行方案(YAGNI阶梯), 全部6附属Skill已装: ponytail/review/audit/debt/gain/help
11. 四Skill同步 → p0-triple-skill-workflow (已升级为四位一体: 计划-执行-纪律-精简)

## Block C: 技术约束 (6条)
12. 国内API仅限 → domestic-api-only
13. Codex修复后独立验证 → codex-fix-verification-rule
14. 代码修改前强制审查 → codex-cross-verification-rule
15. 符号影响分析 → symbol-impact-analysis-and-change-mapping
16. 逐任务反馈 → task-feedback-per-item
17. Caveman压缩 → caveman-token-compression-enabled

## Block D: 输出规则 (5条)
18. 报告→桌面文件夹 → reports-output-to-desktop-folder
19. VPN代理规则 → vpn-proxy-config
20. 禁止重复验证 ⭐NEW → no-redundant-verification
21. 潜在优化提出+人工复核 ⭐NEW (2026-07-16) → CC发现优化方向时主动提出[人工复核]标记
22. 人工核验清单 ⭐NEW (2026-07-16) → 每完成一轮修复即生成核验清单写入manual-verification-checklist.md
