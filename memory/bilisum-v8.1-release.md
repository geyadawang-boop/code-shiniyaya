---
name: bilisum-v8-1-release
description: "BiliSum v8.1.0 发布 — 12 commits, 17 files, +394/-144, tag v8.1.0"
metadata: 
  node_type: memory
  type: project
  priority: highest
  created: 2026-07-13
  updated: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum v8.1.0

## GitHub
- 仓库: github.com/geyadawang-boop/BiliSum
- 分支: fix-claude-findings
- TAG: v8.1.0
- 基线: 54535c5 → 12 commits

## v8.1.0 全部12 Commits

| Commit | Phase | 内容 |
|--------|-------|------|
| 5c6a6f1 | v8.1 P0 | CDN+评论mode2/fallback+收藏夹进度+弹幕3通道 |
| 2b3dd9d | v8.1 P1 | cover->pic+textLength+null检查x3+字幕翻译 |
| b5789e6 | v8.1 P1 | stream=True流式+schema迁移 |
| de985f2 | v8.1 P1 | 管理已导入+智能分类CSRF+Obsidian CSRF |
| 7e117c5 | v8.1 P1 | 菜单栏统一 |
| 61593e8 | v8.1 P1 | SSRF修复 |
| ea1c541 | v8.1 P2 | 评论精选40条 |
| a92d77b | v8.1 H | DB连接异常+弹幕通道1→logger |
| a51e033 | v8.1 I | LLM消毒(classifier+prompt_engine)+kb_chunks_fts CREATE |
| f5fae33 | v8.1 J | 12处bare except→logger(6 files) |
| 4816e6a | v8.1 K | cancellation集成 |
| 6e85f85 | v8.1 K | 错误中文化(50处 str(e)→中文) |

## 改动: 17 files, +394/-144

## 修复统计

| 维度 | 已修复 | 未修复 |
|------|--------|--------|
| 用户反馈(19) | 18 | 1 (P2-6图谱) |
| CC诊断(38) | 29 | 9 |
| bare except:pass | 14处→logger | 20处P2保留(搜索引擎回退等) |

## 关联
- [[bilisum-v8-final-state]]
- [[bilisum-v8.1-session-state]]
- [[bilisum-v8-full-scan-report]]
- [[bilisum-19-user-issues-diagnosis]]
- [[codex-bilisum-v8-verification-results]]
- [[p0-rule-compliance-checklist]]
