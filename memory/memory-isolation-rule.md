# Rule: code-shiniyaya 记忆隔离

所有属于 code-shiniyaya Skill 的记忆文件（`.md`, `.json`, `.py` 等）必须写入：
`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\`

不得写入以下 bilisum 记忆目录：
- `C:\Users\shiniyaya\.claude\projects\c--\memory\` （bilisum 专用）

Bilisum 记忆仅作**参考**——不作为 code-shiniyaya 的写入目标。

## 适用场景
- 分析开源参考源 → 写入 `code-shiniyaya/memory/reference-sources*.md`
- 提取模式 → 写入 `code-shiniyaya/memory/patterns*.md`
- Skill 迭代 → 写入 `code-shiniyaya/SKILL.md`
- 状态追踪 → 写入 `code-shiniyaya/memory/state*.json`

**Why:** 用户在 2026-07-16 的会话中明确要求此 Skill 的记忆独立于 bilisum 项目。
