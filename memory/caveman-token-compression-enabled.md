---
name: caveman-token-compression-enabled
description: Caveman token压缩skill已启用 — 65% token节省，lite/full/ultra/极致4档
metadata: 
  node_type: memory
  type: project
  created: 2026-07-10
  source: JuliusBrussee/caveman
  originSessionId: f2f0e50d-c35d-4ea4-94d4-c2d0e2f3fba5
---

# Caveman Token 压缩已启用

## 安装 Skill (4个)

| Skill | 用途 | 使用方法 |
|-------|------|---------|
| `caveman` | 对话 token 压缩 65% | `/caveman` 切换模式 |
| `caveman-commit` | 压缩 git 提交信息 | 自动压缩 |
| `caveman-compress` | 压缩 CLAUDE.md/todos 等文件 | `caveman-compress <file>` |
| `caveman-stats` | Token 节省统计 | `caveman-stats` |

## 模式说明

| 模式 | 压缩强度 | 适用场景 |
|------|---------|---------|
| `lite` | 轻量 | 短对话/简单任务 |
| `full` | 标准 | 正常开发流程 |
| `ultra` | 极限 | 长对话/多Agent场景 |
| `极致` | 最大 | Token预算紧张时 |

## 当前配置
- 模式: `full`
- 目标节省: >50%
- 关联: [[codex-cross-verification-rule]]

**Why:** 1,010 个 skill 的长对话会消耗大量 token。Caveman 压缩模式可节省 65%，确保 Codex 交叉验证流程不会因 token 不足而中断。

**How to apply:** 每次对话开始时运行 `/caveman` 选择模式。长对话使用 `ultra` 模式。运行 `caveman-stats` 跟踪节省量。
