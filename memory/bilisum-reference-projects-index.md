---
name: bilisum-reference-projects-index
description: BiliSum开源参考项目完整索引 — 10个参考源的路径、可复用内容、已验证的移植建议
metadata:
  type: reference
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum 开源参考项目完整索引

## 4 个新源文件 (已克隆到桌面, 10 Agent已分析)

### note-skill (Unclecheng-li/note-skill)
- 路径: C:\Users\shiniyaya\Desktop\note-skill-src\
- 核心: SKILL.md, assets/template.html, assets/template-journal.html, references/layouts.md, references/components.md
- 可复用: 18布局模板, CSS变量系统, 4色语义系统, 笔记本风格HTML
- 验证结论: ✅ 可用于KB详情页+评论UI+DOCX模板+思维导图配色

### AI_Animation (Unclecheng-li/AI_Animation)
- 路径: C:\Users\shiniyaya\Desktop\AI_Animation-src\
- 核心: dynamic-archify(7导出格式), scholar-notes(笔记本), ppt-animation(26模板), flowchart, network-protocol-viz
- 可复用: PNG/SVG/WebM导出流水线, gif.js, MediaRecorder API, Dark/Light主题切换
- 验证结论: ✅ 可用于思维导图导出+总结幻灯片+主题切换

### bilibili-auto-transcript (54Lynnn/bilibili-auto-transcript)
- 路径: C:\Users\shiniyaya\Desktop\bilibili-auto-transcript-src\
- 核心: SKILL.md, bilibili_scanner.py, batch_transcribe.py, transcript_db.py, architecture.md, bilibili-fav-api.md
- 可复用: 3级字幕回退(CC→AI→Whisper), 收藏夹批量扫描+去重+断点续传, GPU智能模型选择, 年-月目录组织
- 验证结论: ✅ 可用于收藏夹增强+GPU VRAM检测+多语言字幕

### knowledge-rag (54Lynnn/knowledge-rag)
- 路径: C:\Users\shiniyaya\Desktop\knowledge-rag-src\
- 核心: SKILL.md, index_knowledge.py, knowledge_api.py, query_knowledge.py, start.py, web/src/server.ts
- 可复用: ChromaDB RAG, BGE-M3嵌入, 多知识库, CUDA加速
- 验证结论: ✅ 可用于CUDA自动检测+多KB集合+嵌入模型升级

## 6 个已有参考项目

### bilibili-rag (最高ROI)
- 路径: C:\Users\shiniyaya\Desktop\rag开源文件\project\bilibili-rag\
- 核心文件: content_fetcher.py(609行), bilibili.py(560行), rag.py+rag_original.py(1139行), chat.py(859行), markdown_export.py(143行), retrieval.py(195行)
- Codex建议移植: A1 ContentFetcher, A2 BilibiliService, A3 RAG hash, A4 SSE
- 验证结论: A1/A2/A3/A4全部应拒绝或推迟(BiliSum已有更优实现或移植风险过高)

### bilibili-subtitle
- 路径: 记忆文件 bilisum-open-source-references.md
- 可用: SRT/VTT/MD解析渲染, BBDown CLI重试, 语言标准化
- 状态: 部分已集成

### bili-note
- 路径: 记忆文件 bilisum-open-source-references.md
- 可用: WBI签名, 多ASR, 质量评分, 笔记预算, 证据溯源
- 状态: WBI已集成, 质量评分部分集成

### subbatch-local
- 路径: 记忆文件 bilisum-open-source-references.md
- 可用: 中文智能分句, 前端Whisper WebGPU/WASM, 繁简转换
- 状态: 未集成

### BOC (Bilibili-Obsidian-Clipper)
- 路径: 记忆文件 bilisum-open-source-references.md
- 可用: Obsidian Local REST API, vault推送
- 状态: 已集成

### vsummary
- 路径: C:\Users\shiniyaya\Desktop\总结工具修改\reference_repos\vsummary\
- 可用: SSE流式, markmap, CSS tokens, atomic file writes
- 状态: 部分模式已参考

## 已验证的移植建议汇总

| 来源 | 移植内容 | 结论 |
|------|---------|------|
| note-skill | CSS变量+笔记本风格 → KB详情页+评论UI | ✅ 可行 |
| AI_Animation | 导出流水线 → 思维导图PNG/SVG | ✅ 可行 |
| bilibili-auto-transcript | 收藏夹去重+断点续传 | ✅ 可行 |
| bilibili-auto-transcript | GPU VRAM模型选择 | ✅ 可行 |
| knowledge-rag | CUDA自动检测 | ✅ 可行 |
| knowledge-rag | 多KB集合 | ✅ 可行 |
| bilibili-rag | ContentFetcher移植 | ❌ 模型不兼容 |
| bilibili-rag | BilibiliService封装 | ❌ 91+行×8文件高风险 |

## 关联记忆
- [[bilisum-open-source-references]] — 原始6项目分析(15代码块)
- [[bilisum-v7-50-agent-scan]] — v7.0 50 Agent扫描
- [[bilisum-v8-session-state]] — 当前会话状态
- [[codex-bilisum-v8-verification-results]] — Codex方案验证结果
