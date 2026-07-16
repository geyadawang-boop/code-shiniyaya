---
name: task-feedback-per-item
description: 最高优先级规则 — 每完成一个任务先反馈给用户，确认后才能写入已完成，继续下一个
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-10
  originSessionId: f2f0e50d-c35d-4ea4-94d4-c2d0e2f3fba5
---

# 最高优先级：逐任务反馈规则

## 规则内容

**每完成一个任务 → 立即反馈用户 → 用户确认 → 写入已完成 → 继续下一个。** 禁止批量完成多个任务后再汇报。

## 为什么

用户需要实时了解进度，防止批量操作中某个任务出错而未被发现。与 [[codex-cross-verification-rule]] 互补——Codex 验证代码正确性，反馈规则保证用户知晓每一步。

## 工作流

1. 执行一个任务
2. 完成后立即反馈用户："Task X done: [具体做了什么]"
3. 等待用户确认
4. 标记已完成 → 继续下一个任务
5. 不能跳过反馈步骤，不能批量汇报

**Why:** 用户是最终决策者，必须实时了解每个修复的详情。批量操作风险高。

**How to apply:** TodoWrite 中的每个任务必须逐个完成并反馈。完成后才能进入下一个。
