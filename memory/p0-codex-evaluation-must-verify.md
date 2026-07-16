---
name: p0-codex-evaluation-must-verify
description: 最高优先级 — 收到Codex任何方案/分析/修复后，必须启动至少10个不同维度Agent独立验证，Codex经常误判
metadata:
  type: feedback
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# P0 规则：Codex 方案必须严格交叉验证

## 规则内容

**Codex 的任何方案、分析、修复清单都不能直接信任。** 必须经过 CC 独立严格验证。

本次会话验证结果：Codex 14项Bug中4项误判(B1/B9/B10/B13)，6项代码复用中5项应拒绝(A1/A2/A3/A4/A6)，11项CC用户问题被遗漏。

## 验证要求

1. 收到 Codex 方案后 → 启动至少 10 个不同维度 Agent
2. 每个 Agent 直接读取实际源码逐项核实，不信任任何文字总结
3. 验证维度必须覆盖:
   - Bug修复 — 源码实际状态 vs Codex声称
   - 代码复用 — 源文件实际存在性 + 兼容性 + 风险
   - 遗漏检查 — CC问题 vs Codex覆盖
   - Git/编码安全 — 文件编码BOM/UTF-16/0x3F
   - 架构影响 — 依赖链断裂风险
   - 回退路径 — 每个修复独立可回退
   - 执行计划 — 估时准确性 + 文件重叠

## Codex 常见错误模式

1. **声称已修复但源码未变** — 多次出现 (如 CSRF token pop 被声称修复但实际仍是续命代码)
2. **诊断偏离根因** — 如 B8 声称缺fallback但实际是忽略db设置
3. **数量夸大** — 如 B14 声称26处 except:pass 实际9处
4. **不检查源文件是否存在就建议移植** — 如 A1/A2 依赖不兼容的模型
5. **遗漏用户直接反馈的问题** — 只关注代码层面Bug，忽略功能缺失

## 如何应用

1. Codex 发来任何方案 → 不秒回，先启动 10 Agent
2. 等全部 Agent 返回 → 交叉对比 → 写验证报告
3. 发现误判 → 逐项标注并提供源码证据
4. 验证通过 → 才发送给用户审批
5. 用户+Codex双方批准 → 才执行修改

## 关联记忆
- [[p0-dual-approval-before-code-edit]] — 用户+Codex双重批准
- [[p0-cc-no-solo-edits]] — CC禁止独立修改
- [[p0-codex-bidirectional-verification]] — 双向验证流程
- [[p0-deep-analysis-before-execute]] — 收到Codex指令先深度分析
- [[codex-bilisum-v8-verification-results]] — 本次验证的具体结论
