---
name: codex-fix-verification-rule
description: Codex每次修复bug或修改代码后必须由Claude Code扫描验证
metadata: 
  node_type: memory
  type: rule
  priority: highest
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# Codex 修复验证规则

当 Codex 完成任何修复或修改代码后：
1. 立即读取 Codex 修改的文件
2. 逐行验证修复是否正确
3. 验证 Codex 声称已修复的 bug 是否真的修复了（代码与声明一致）
4. 验证是否引入了新 bug
5. 将验证结果写入 FROM_CLAUDE.md

**Why:** Codex 连续3次错误声称 model NameError 已修复但实际未修复。Codex 的验证不可靠，需要 Claude Code 独立交叉验证每一处修改。

**How to apply:** 每次收到 Codex 的修复报告或 FOR_CC_*.md 文件时，立即启动扫描 agent 逐项核实。不信任 Codex 的自我验证结论。每项修复必须附上实际代码行号和证据才能标记为"已修复"。

Related: [[task-feedback-per-item]], [[codex-cross-verification-rule]]
