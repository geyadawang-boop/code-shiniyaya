---
name: p0-cc-no-solo-edits
description: 最高优先级 — CC 不得独立修改代码。任何修改：执行前发方案给 Codex 确认，执行后发结果给 Codex 验证。不经过 Codex 双向确认的修改不得执行。
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-12
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 规则：CC 禁止独立修改代码

## 规则内容

**CC 不得主动修改任何源代码文件。** 所有修改必须经过 Codex 双向确认流程：

1. CC 发现问题 → 分析根因 → 写入修复方案（精确行号 + old/new 代码）
2. **发送方案给 Codex**，等待 Codex 确认方案合理
3. Codex 确认后 → CC 才能执行修改
4. 修改完成后 → **发送结果给 Codex**，附带实际代码行号证据
5. Codex 验证通过 → 修改完成

唯一例外：写入记忆/规则文件（`~/.claude/projects/c--/memory/*.md`）和 review 文档（`review/*.md`）不需要 Codex 确认。

## 为什么

本次会话中 CC 独立执行了 14 项修改（textLength、弹幕、CSRF、LLM注入等），没有先发送 Codex 确认。这违反了 [[p0-codex-bidirectional-verification]] 的双向验证协议。虽然修改本身通过了语法验证，但 Codex 没有机会：
- 独立分析每个修复方案是否最优
- 发现方案中的潜在副作用
- 验证修改后的代码是否引入新问题

CC 单方面修改代码会导致 Codex 不知道当前源码状态，后续修复可能基于过时的假设。

## 如何应用

1. 收到 Codex 消息或用户指令后 → **先分析**，不要立即修改文件
2. 分析结果写入 `review/CC_PROPOSAL.md`，附 old/new 代码 + 行号
3. 将提案发送给 Codex（附带可复制文本）
4. **等待 Codex 确认**后才执行修改
5. 修改后验证 ast.parse + compile，然后反馈 Codex

## 关联记忆

- [[p0-codex-bidirectional-verification]] — 双向验证流程
- [[p0-no-auto-edit]] — 修改前必须获用户批准
- [[codex-fix-verification-rule]] — 不信任 Codex 自我验证
- [[codex-message-protocol]] — 给 Codex 发信息时的格式要求
- [[p0-deep-analysis-before-execute]] — 收到指令先深度分析
