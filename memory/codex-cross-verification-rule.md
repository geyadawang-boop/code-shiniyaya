---
name: codex-cross-verification-rule
description: 最高优先级规则 — 写入/修改任何代码前必须与Codex交叉验证，Bug扫描不遗漏Codex视角
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-10
  originSessionId: f2f0e50d-c35d-4ea4-94d4-c2d0e2f3fba5
---

# 最高优先级：Codex 交叉验证规则

## 规则内容

**任何代码写入/修改前，必须与 Codex 交叉验证。** 不遗漏 Codex 视角。

## 为什么

Claude 16 Agent 修复的 32 项 Bug 中，Codex 独立审查发现了 Claude 遗漏的 2 个 Plan-Code Gap（Counter import 缺失、CSRF httponly=True 导致前端无法读取 Cookie），以及 CSRF 豁免检查执行顺序错误。Claude 发现 Codex 遗漏了 26 项额外问题（RAG 嵌入、prompt 注入等）。两种视角互补。

## 具体流程

1. **代码修改前**: 运行 `/codex:adversarial-review` 审查修改计划
2. **Bug 扫描时**: 同时启动 Codex 和 Claude 扫描，交叉对比结果
3. **修复后验证**: Codex 独立验证修复是否写入源文件（Plan-Code Gap 检测）
4. **不遗漏任何视角**: Claude 扫描后端/CSS/前端细节；Codex 扫描逻辑缺陷/架构问题

## 编译代码强制 Codex 核对

**任何代码编译/运行前，必须经过 Codex 交叉核对。** 这是防止编译时错误和生产环境崩溃的最后防线。

- 修改 Python 文件后 → Codex 检查语法/import/类型错误
- 修改 JavaScript 文件后 → Codex 检查语法/逻辑/边界条件
- 修改前端 HTML/CSS 后 → Codex 检查兼容性/布局破坏
- 保证每个被修改的文件都在 Codex 核对范围内

## 关联记忆

- [[bilisum-p0-bugs]] — 23 P0 bugs fixed with Codex+Claude dual verification
- [[bilisum-v7.1-fix-report]] — v7.2 dual audit report

**Why:** Codex 发现的 Counter import 缺失和 CSRF httponly 问题在 Claude 独立审查前都不明显 — 双重验证防止静默 bug 进入生产。

**How to apply:** 每次代码修改前强制执行。修改后必须通过 `git diff` + Codex `adversarial-review` 验证。
