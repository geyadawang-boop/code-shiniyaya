---
name: p0-codex-bidirectional-verification
description: 最高优先级 — 每次修改前发方案给 Codex 确认，每次修改后发结果给 Codex 验证。不经过 Codex 验证的修复不算完成。
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-12
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# 规则 2：Codex 双向验证

## 规则内容

**每次修改前发方案给 Codex 确认，每次修改后发结果给 Codex 验证。** 不经过 Codex 验证的修复不算完成。

## 为什么

多次出现 CC 方案正确但执行缺失的情况——Codex 声称修复了但实际源码未变（如 model NameError 连续 3 次声称已修复），或 CC 执行正确但 Codex 视角发现了遗漏（如 Counter import 缺失、CSRF httponly=True 导致前端无法读取 Cookie）。双向验证是唯一可靠的质量关口。

## 具体流程

1. **修改前**: 将修复方案发送给 Codex，附文件路径和预期改动
2. **等待 Codex 深度分析**: Codex 启动至少 6 个不同维度、不同类型的 Agent 独立分析方案可行性，反馈确认或修正意见。不秒回，追求深度和准确性
3. **Codex 反馈后，CC 启动至少 6 个 Agent 深度分析**: 对 Codex 的反馈进行多维度交叉验证，调用不同类型 Agent（caveman/Explore/general-purpose/Plan），确认无误后才执行
4. **执行修改**: 按确认后的方案修改代码
5. **修改后**: 将修改结果发送给 Codex
6. **Codex 验证**: Codex 启动至少 6 个不同维度的 Agent 独立验证修改是否正确
7. **CC 再次深度验证**: CC 启动至少 6 个 Agent，调用不同类型交叉验证，逐项核实 Codex 的验证结论
8. **双方确认**: CC 和 Codex 都确认修复成功后，才能标记为"已完成"

## 不可跳过的情况

- 任何 P0 级 Bug 修复：必须双向验证
- 任何涉及多文件的修改：必须双向验证
- 任何涉及编码/文件读写的修改：必须双向验证
- 简单的单行注释修改：可以跳过

## 关联记忆

- [[p0-no-auto-edit]] — 修改前必须先获用户批准
- [[codex-cross-verification-rule]] — 修改前 Codex 交叉审查的原始规则
- [[codex-fix-verification-rule]] — Codex 每次修复后 CC 必须独立扫描验证
- [[codex-message-protocol]] — 给 Codex 发信息时的格式要求

**Why:** Codex 连续 3 次错误声称 model NameError 已修复但实际源码未变。双向验证是防止 Plan-Code Gap 的唯一可靠机制。

**How to apply:** 每次修改 P0 级或涉及多文件的修改，必须走完"方案确认→执行→结果验证→双方确认"四个步骤。修改后必须用实际代码行号作为证据，不能仅凭 Codex 的自我验证结论。
