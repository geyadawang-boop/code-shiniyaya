---
name: bilisum-46-skills-analysis
description: Complete analysis of all 46 Claude Code skills with use/reference/skip verdicts and top 20 skill combinations for BiliSum
metadata:
  type: reference
---

# BiliSum 46 Skill 分析 + TOP 20 组合拳

## 判定分布
- 核心使用: 5 (claude-api, video-summarizer, prompt-optimizer, obsidian-markdown, summarizer)
- 重要使用: 18 (impeccable, taste-skill, design-system, tdd, karpathy-guidelines, code-simplifier, code-review, agent-browser, mcp-builder, officecli, notion-api, obsidian-automation, obsidian-vault, notebooklm, planning-with-files, grill-me, ce-test-browser, argent-metro-debugger)
- 参考使用: 15
- 暂不使用: 8

## 开发准则 Skill (强制遵守)
1. karpathy-guidelines — 外科手术修改、目标驱动、简洁优先
2. code-simplifier — 消除重复、提取公共模块
3. tdd — 红线→绿线→重构
4. code-review — CodeRabbit 自动审查

## 页面美化准则 Skill
5. taste-skill — 禁用纯黑#000/#fff、禁用AI-purple、按钮≤5字单行、CTA对比度≥4.5:1
6. impeccable — audit→critique→polish→harden→bolder 5命令序、字体最小12px、text-wrap:balance
7. design-system — 3层token(primitive→semantic→component)、禁止硬编码hex
8. css-animation-creator — 仅动画transform+opacity(GPU加速)、ease-out-quart、prefers-reduced-motion必需
9. visual-designer — 60-30-10色彩、8pt spacing grid、WCAG AA、阴影tinting

## TOP 20 组合拳
1. claude-api + prompt-optimizer + summarizer — AI引擎系统升级
2. video-summarizer + rag_service + mcp-builder — BiliSum→MCP平台化
3. impeccable + taste-skill + design-system — 前端设计系统重构
4. planning-with-files + tdd + code-review + karpathy — 自动化质量门控
5. obsidian-markdown + automation + vault + summarizer — 知识自动归档流水线
6. officecli + notion-api + obsidian-markdown — 三轨导出(Word+Notion+Obsidian)
7. agent-browser + ce-test-browser + argent-metro-debugger — Electron全栈测试
8. notebooklm + rag_service + claude-api — RAG系统升级(追问+置信度)
9. claude-api + summarizer + firecrawl-deep-research — 视频主题研究平台
10. tdd + code-simplifier + karpathy + code-review — 技术债系统性清理
11. self-improving-agent + quality.py — 摘要质量自优化循环
12. deep-interview + summarizer.py — 5轴结构化总结(目标/范围/约束/标准/影响)
13. letta-api-client + database.py + rag_service.py — 三层记忆KB(核心+档案+对话)
14. notebooklm + main.py RAG chat — 自动追问对话(最多3轮)
15. multi-search-engine + bilibili_client.py — 跨平台搜索(B站+YouTube+知乎)
16. ab-test-designer + quality.py — 科学A/B测试优化4种总结模式
17. skill-vetter + main.py — 安全审计(通过了命令注入检查但CORS/明文Cookie需修复)
18. firecrawl-deep-research + rag_service.py — 网页研究回退(KB无结果→多引擎搜索)
19. lark-openapi-explorer + bilibili_client.py — B站API变化自动检测
20. bazi-skill + summarizer.py — 8步确定性管道启发总结管线架构

**Why:** Each skill has been read, analyzed, and cross-referenced against the BiliSum codebase over 10 rounds.

**How to apply:** Keep this as a reference when making changes to BiliSum. Before any code change, check which skills apply.
