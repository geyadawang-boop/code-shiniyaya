---
name: p0-deep-analysis-before-execute
description: 最高优先级 — 收到 Codex 指令后必须先独立深度分析，验证方案可行性和正确性，确认无误后再执行。不能盲目遵守。
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-12
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# 规则 3：收到 Codex 指令先深度分析再执行

## 规则内容

**收到 Codex 的任何信息后，必须启动至少 6 个独立 Agent 进行深度分析。** 不追求回复速度，只追求分析的深度、纠错的准确性、源码覆盖的完整度、以及代码修改的正确率。

收到 Codex 的反馈、修复报告、确认请求等任何信息后：
- 最少启动 6 个 Agent 并行独立分析，每个 Agent 从不同维度、不同视角交叉验证
- 必须调用**清单中所有可用的 Skill**，尽量覆盖不同视角——每个 Agent 可以同时使用高性能模型 + 1-2 个辅佐 Skill 增强分析深度
- 同一个 Agent 可以组合多个 Skill：一个主 Skill 提供核心分析方法论，另一个辅佐 Skill 提供技术栈专项知识或其他视角
- Skill 可以跨类别组合——如 general-purpose Agent 同时调用 `diagnosing-bugs` + `fastapi` + `tokensave_body`，Extra Agent 同时调用 `code-simplifier` + `electron-security` + `tokensave_search`
- 每个 Agent 承担不少于 2 个 Skill 组合（第一类是分析方法论，第二类是技术栈专项或辅助视角）
- 大型验证任务（40+ Agent）应覆盖清单中 80% 以上的可用 Skill

## 可调用的 Skill 清单（按类别）

以下所有 Skill 均可根据任务需要随时调用。每个 Agent 应根据分配的维度选择最相关的 Skill 组合。

### 调试与错误恢复（debugging Agent 专责）
- `diagnosing-bugs` — Bug 诊断策略和方法论
- `debugging-strategies` — 多维度调试策略
- `systematic-debugging` — 系统性调试流程（按步骤排查）
- `debugging-and-error-recovery` — 调试 + 错误恢复
- `python-debugpy` — Python debugpy 调试器集成
- `python-error-handling` — Python 异常处理最佳实践
- `node-inspect-debugger` — Node.js 运行时调试

### 代码审查与质量（cross-verification Agent 专责）
- `code-review` — 正式代码审查流程
- `code-simplifier` — 代码简化、去冗余
- `refactoring` — 安全重构方法论
- `auditing-python-security` — Python 安全漏洞审计
- `security-triage` — 安全问题分类和优先级
- `verify-release` — 发布前完整性验证
- `qa` — 通用质量保障

### 架构与设计（Plan/architecture Agent 专责）
- `codebase-design` — 代码库架构设计
- `domain-modeling` — 领域模型设计
- `dependency-management` — 依赖关系管理
- `cross-platform-compatibility` — 跨平台兼容检查（Windows/macOS/Linux）
- `request-refactor-plan` — 重构计划生成
- `writing-plans` — 结构化方案撰写

### 技术栈专项（根据修改文件类型选择）
- `fastapi` / `fastapi-python` / `fastapi-templates` — FastAPI 后端
- `electron-builder` / `electron-security` — Electron 桌面应用
- `sqlite-best-practices` — SQLite 数据库操作
- `bili-note` / `bilibili-subtitle` / `bilibili-rag-deploy` — B站 API 集成
- `openai-whisper` / `openai-whisper-api` / `faster-whisper` / `local-whisper` — 语音转文字
- `subtitle-generation` / `srt-to-structured-data` — 字幕处理
- `video-downloader` / `video-frames` — 视频处理
- `rag-eval` / `semantic-search` — RAG 检索增强

### 工具链
- `caveman:cavecrew-investigator` — 字节级精确定位（Agent）
- `caveman:cavecrew-reviewer` — Diff/文件审查（Agent）
- `caveman:caveman-review` — Caveman 风格审查（Skill）
- `caveman:caveman-compress` — Token 压缩（Skill）
- `Explore` — 广域搜索（Agent）
- `general-purpose` — 通用深度分析（Agent）
- `Plan` — 架构规划（Agent）
- `tokensave` (MCP) — 代码图谱分析（tokensave_context / tokensave_search / tokensave_diff / tokensave_diagnostics / tokensave_body / tokensave_callees / tokensave_callers 等）

### 调用原则
1. **每个 Agent 至少组合 2 个 Skill**：第一个是分析方法论类（debugging/code-review/refactoring），第二个是技术栈专项或辅助视角（fastapi/electron-security/tokensave）
2. **尽可能多覆盖清单中的 Skill**：大型深度扫描任务（40+ Agent）应覆盖清单中 80% 以上可用 Skill
3. **同一个 Agent 可以同时使用不同 Agent 类型（如 general-purpose）+ 任意 Skill 组合**，充分利用不同视角
4. **每个 Skill 和 Agent 都对最后的代码审查有不同视角的增益**——通过多样性最大化发现隐藏问题
5. 按维度匹配核心 Skill：debugging Agent → debugging 类，cross-verification Agent → code-review/qa 类，Plan Agent → codebase-design/domain-modeling 类
6. 不限制调用数量：有利于代码质量即可，无上限
- 维度至少覆盖：编码健康（字节级 0x3F/BOM/UTF-16）、语法正确性（ast.parse/JS 语法）、逻辑完整性（修复覆盖所有边界）、副作用扫描（跨文件影响）、Codex 声明交叉验证（逐项核实是否真的改了）、遗漏项检查
- 每个 Agent 必须直接读取源文件验证，不信任 Codex 的文字总结
- 不秒回——等待所有 Agent 完成后再汇总结论
- 发现任何问题立即反馈用户和 Codex，不盲目相信 Codex 的自我评估
- **Agent 扫描期间必须定期反馈进度**：Agent 启动后每 15-30 秒向用户汇报当前完成数/总 Agent 数，防止用户误判后台任务已停止或 CC 无响应。汇报格式简洁："X/6 Agent 完成，扫描中..."

## 为什么

出现过 CC 方案正确但执行时编码损坏或漏掉步骤的情况。Codex 的指令可能：
- 使用了不安全的方法（如 PowerShell Set-Content）
- 遗漏了关键的验证步骤
- 假设了错误的文件状态
- 自我验证结论与源码实际情况不符（如多次声称已修复但源码未变）

单个 Agent 或简单 grep 无法发现所有问题。必须多 Agent 多维度交叉验证才能确保结论可靠。
如果 CC 盲目相信 Codex 而不深度分析，会重复已有错误。

## 具体流程

1. **收到信息**: 完整阅读 Codex 发来的所有文件和指令
2. **启动至少 6 个不同维度的 Agent**: 每个 Agent 分配独立的验证维度 + 不同的 Agent 类型，并行执行。每个 Agent 至少调用 1-2 个相关 Skill 增强分析。
3. **维度 + Agent 类型分配**（不少于 6 个维度，不少于 5 种 Agent 类型）：
   - caveman:cavecrew-investigator × 1-2: 字节级精确定位（0x3F 损坏、BOM、UTF-16 编码问题、精确行号匹配）
   - Explore × 1-2: 广域搜索遗漏项、跨文件不一致、Codex 声明中未提及的副作用
   - general-purpose × 1-2: 深度逻辑分析、语法验证（ast.parse）、修复完整性评估
   - Plan × 1: 架构级评估——修改是否引入技术债务、是否影响其他模块、是否需要同步修改其他文件
   - debugging × 1: 调试和错误恢复——模拟运行时行为、验证函数调用链、检查异常处理路径、验证 try/except 覆盖、确认无 NameError/ImportError
   - 编码健康检查（BOM、UTF-16、0x3F 损坏字节）—— 至少 1 个 Agent 专责
   - 语法正确性（ast.parse / JS 语法检查）—— 至少 1 个 Agent 专责
   - Codex 声明交叉验证（逐项核实 Codex 声称已修复的每一项是否真的改了）—— 至少 1 个 Agent 专责
   - 遗漏项检查（Codex 声称已修复的列表中是否有遗漏）—— 至少 1 个 Agent 专责
4. **等待全部完成**: 不秒回，等所有 Agent 结果就绪后再汇总结论
5. **汇总结论**: 交叉对比所有 Agent 的发现，写出最终验证报告
6. **发现问题**: 立即写入 `review\FROM_CLAUDE.md` 并通知用户
7. **确认后执行**: 方案验证通过后，逐项执行修改
8. **执行后验证**: 每项修改完成后立即验证语法 + 编码 + 文件大小

## 重点检查项

- 文件编码安全：修改方法是否会损坏 UTF-8（严禁 PowerShell Set-Content）
- 语法正确性：修改后代码是否能通过 ast.parse 检查
- 文件完整性：修改后文件大小是否正常（不能是 0 字节或只含 BOM）
- 副作用检查：修改一个文件是否会影响其他文件（如 import 链）

## 关联记忆

- [[p0-no-auto-edit]] — 修改前必须先获用户批准
- [[p0-codex-bidirectional-verification]] — Codex 双向验证流程
- [[codex-message-protocol]] — 给 Codex 发信息时的格式要求

**Why:** Codex 曾要求使用 PowerShell Set-Content 修改文件，导致大面积 UTF-8 中文永久损坏。如果 CC 在 3 轮损坏发生前先独立验证方案安全性，可以避免全部损失。

**How to apply:** 每次收到 Codex 指令后强制执行。先启动子 Agent 读源码验证方案，发现问题立即反馈用户，不盲目执行。执行后立即跑 ast.parse + 编码检查 + 文件大小检查。
