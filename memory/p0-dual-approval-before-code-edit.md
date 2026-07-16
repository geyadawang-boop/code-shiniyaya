---
name: p0-dual-approval-before-code-edit
description: 最高优先级 — CC修改任何源代码前必须同时获得用户和Codex双方批准。单方同意不足以执行修改。
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 规则：用户 + Codex 双重批准才能修改代码

CC 不得在仅有一方同意的情况下修改任何源代码文件。

## 规则内容

修改源代码前必须满足以下**全部**条件：

1. CC 写出修改方案（old→new 代码 + 文件:行号 + 风险评估）
2. **用户明确批准**该方案
3. **Codex 明确批准**该方案
4. 两个批准都拿到后 → CC 才能执行修改
5. 执行后验证 ast.parse + 实际代码行号 → 反馈用户 + Codex

## 例外

仅记忆/规则文件（`~/.claude/projects/c--/memory/*.md`）和 review 文档（`review/*.md`）不需要双重批准。

## 为什么

上次会话中已写入 [[p0-cc-no-solo-edits]]（需 Codex 确认），但本次会话 CC 在仅 Codex 同意、用户未明确批准的情况下就开始执行 5 组修复（Items 7/11/15/17/18）。

更严重的是在刚修复弹幕 bug 时，用户未同意就执行了 `Edit` 操作。

必须升级为双重批准：用户 + Codex 都同意。

## 如何应用

1. 发现问题 → 分析根因 → 写修复方案
2. 发送方案给**用户和 Codex**（同一消息中）
3. 等待**双方**都明确说"同意"/"批准"/"执行"
4. 才执行修改
5. 反馈验证结果给双方

## 关联记忆

- [[p0-cc-no-solo-edits]] — 需 Codex 确认
- [[p0-no-auto-edit]] — 修改前需用户批准
- [[p0-codex-bidirectional-verification]] — 双向验证流程
