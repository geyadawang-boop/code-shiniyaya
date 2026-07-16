---
name: symbol-impact-analysis-and-change-mapping
description: 最高优先级规则 — 改任何符号必须跑影响分析; 提交前必须跑变更映射
metadata:
  type: feedback
  priority: highest
  created: 2026-07-10
  originSessionId: f2f0e50d-c35d-4ea4-94d4-c2d0e2f3fba5
---

# 最高优先级：符号影响分析 + 变更映射规则

## 规则1：改任何符号必须跑影响分析

修改任何函数名、变量名、类名、常量、import/require、API签名、导出接口前：
1. 搜索所有引用 → 确认每个调用点
2. 列出影响清单 → 哪些文件/调用点受影响
3. 评估后果 → 编译错误/运行时崩溃/静默行为变化
4. 用户确认后才执行

## 规则2：提交前必须跑变更映射

git add/commit前，对每行变更做映射表：

| 列 | 含义 |
|----|------|
| 文件:行号 | 源位置 |
| 变更内容 | 具体改了什么 |
| 影响符号 | 受影响函数/变量/类 |
| 下游依赖 | 哪些文件依赖被改符号 |
| 不修改下游的后果 | 崩溃/403/死代码 |

**Why:** v8.1 中 preload openExternal 改 IPC 未检查渲染进程调用点、sandbox:true 未评估 localStorage、CSRF 单次使用未评估所有 POST 端点 —— 三个错误均因跳过影响分析导致用户应用不可用。

**How to apply:** 每次修改前跑 `grep -rn "symbol_name"`、列出全部引用点、评估后果、等用户确认。

## 关联记忆

- [[codex-cross-verification-rule]]
- [[task-feedback-per-item]]
