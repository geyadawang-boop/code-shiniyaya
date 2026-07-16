---
name: bilisum-v8-full-scan-report
description: 三Skill协同全量扫描报告 (2026-07-13) — BiliSum软件+Skill源+参考源+P0规则审计，优化计划和执行优先级
metadata:
  type: project
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum v8.0 全量扫描 + 优化计划

## 扫描范围

- **BiliSum 软件**: 57 .py (28,177行) + 12 前端 (7,710行) + 3 Electron (1,026行)
- **Skill 源**: .claude 194个 + .cc-switch 236个
- **参考源**: 4新克隆 (实际路径 `C:\Users\shiniyaya\Desktop\参考\`)
- **P0 规则**: 15条全量审计

## 发现的问题（按优先级）

### 🔴 P0 阻断 — 立即修复

| 编号 | 问题 | 文件 | 影响 |
|------|------|------|------|
| G1 | KB详情页路由错误 | frontend/kb.html L154 | 知识库显示错误视频内容 |
| G2 | KB LLM注入缺口 | backend/routers/kb.py | RAG上下文未消毒 |
| B2 | CSRF过期token续命 | backend/main.py L244 | 安全漏洞 |
| B3 | favorites端点无豁免 | backend/main.py L217 | 收藏夹同步403 |
| B4 | sandbox:true冲突 | main.js L555 | Electron preload崩溃 |

### 🟡 P0 规则矛盾 — 立即修复

| 编号 | 矛盾 | 修复 |
|------|------|------|
| C1 | p0-no-auto-edit vs p0-dual-approval | ✅ 已标记superseded |
| C2 | Agent数量不一致 (6 vs 10) | 统一为10 Agent |
| C3 | codex-message-protocol vs p0-copyable-codex-text | 后者已取代前者 |
| C4 | session-state待办未反映验证结论 | 需更新 |

### 🟠 P1 功能修复

| 编号 | 问题 | 状态 |
|------|------|------|
| 7 | misc.py DNS异步化 | 待Codex |
| 11 | browse.html 骨架屏 | 待Codex |
| 17e-g | delete_kb_entry 完整清理 | 待Codex |
| 18 | saveToKB bvid修复 | 待Codex |
| G3 | 评论精选优化 | Codex遗漏 |
| G4 | 弹幕分段 | Codex遗漏 |
| G9 | CSP阻止思维导图CDN | Codex遗漏 |
| G10 | docx_exporter.py死代码 | Codex遗漏 |

### 🔵 P2 架构增强

| 编号 | 问题 |
|------|------|
| G5 | 视频/音频下载 |
| G6 | 下载路径设置 |
| G7 | N+1 收藏夹同步 |
| G8 | Cookie 5位置统一 |
| G11 | AI上下文不足 |

### ⚪ 参考源移植建议

| 源 | 移植内容 | 优先级 |
|----|---------|--------|
| bilibili-auto-transcript | 3级字幕回退 + 收藏夹去重 + GPU检测 | P1 |
| knowledge-rag | CUDA自动检测 + 多KB集合 | P1 |
| note-skill | CSS变量 + 笔记本风格 HTML | P2 |
| AI_Animation | 导出流水线 PNG/SVG | P2 |

### ⚙ Skill配置修复

| 问题 | 修复 |
|------|------|
| .cc-switch 缺少 caveman | ✅ 已同步 |
| .cc-switch 缺少 openspec | ✅ 已同步 |
| 参考源路径错误 (桌面 vs 参考/) | ✅ 已确认实际路径 |

## 优化执行计划

```
Phase A (立即, ~1h): P0阻断修复 — G1, G2, B2, B3, B4
Phase B (P0规则, ~30min): C2, C3, C4 矛盾修复 — 统一Agent数量标准
Phase C (P1功能, ~4h): Items 7/11/17e-g/18 + G3/G4/G9/G10
Phase D (P2架构, ~6h): G5/G6/G7/G8/G11
Phase E (参考移植, ~4h): bilibili-auto-transcript + knowledge-rag
```

## 关联记忆

- [[bilisum-v8-session-state]] — 更新
- [[bilisum-19-user-issues-diagnosis]] — 更新
- [[codex-bilisum-v8-verification-results]]
- [[p0-triple-skill-workflow]]
- [[p0-dual-approval-before-code-edit]]
