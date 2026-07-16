---
name: reference-source-function-mapping
description: 11参考源 → BiliSum功能映射表 — 每个源最优函数/BiliSum状态/可用代码/导入风险
metadata:
  type: reference
  created: 2026-07-14
  updated: 2026-07-14
---

# 11参考源 → BiliSum功能映射

## bilibili-rag (rag开源文件)
路径: `C:\Users\shiniyaya\Desktop\rag开源文件\project\bilibili-rag\`
文件: ~30 Python
最优函数:
  - `retrieval.py:60-91` keyword_score() — 字段加权计数 ✅ 已导入
  - `retrieval.py:94-116` build_snippet() — 关键词摘要 ⏳ 待导入
  - `retrieval.py:135-195` merge_ranked_documents() — RRF融合 ✅ 已有
  - `rag.py:149-181` _build_metadata_document() — 元数据文档 ✅ 已有
  - `bilibili.py:343` get_video_summary() — B站AI摘要 ❌ 缺失
  - `markdown_export.py:55-113` organize_video_content() — 多分块笔记 ⏳ 待导入
  - `chat.py:769-840` ask_question_stream() — NDJSON进度 ✅ 已有部分

## Bilibili-Obsidian-Clipper
路径: `C:\Users\shiniyaya\Desktop\参考\开源参考\Bilibili-Obsidian-Clipper\`
文件: extension/content.js (~5200行JS)
最优函数:
  - `content.js:4729-4758` buildFrontMatter() — YAML引擎 ❌ 差距最大
  - `content.js:4760-4775` getEnabledFrontmatterFields() — 字段开关 ❌
  - `content.js:4906-4943` formatFixedPropertyYamlLine() — 5类型 ❌
  - `content.js:4884-4893` resolveFrontmatterTemplateValue() — 模板变量 ❌
  - `content.js:4847-4862` groupNotePlaceholderSections() — 3分区 ❌
  - `content.js:4967-5037` buildSubtitleSectionLines() — 章节感知 ❌
  - `content.js:5163-5183` buildNoteFilename() — 日期-标题 ❌
  - `content.js:5062-5069` buildBilibiliEmbedIframe() — iframe嵌入 ❌

## LegalGraphQA
路径: `C:\Users\shiniyaya\Desktop\参考\LegalGraphQA\LegalGraphQA\`
文件: 9 Python
最优函数:
  - `qa_chain_refactored.py:97-137` ROUTER_PROMPT + router_chain — 3路路由 ✅ 已接入2路
  - `qa_chain_refactored.py:34-51` RAG_PROMPT_TEMPLATE — QA prompt ✅ 已接入
  - `qa_chain_refactored.py:302-309` RunnableParallel — 并行检索 ⚠️ BiliSum串行
  - `chat_logger.py:33-136` ChatLogger — 对话日志 ✅ 已接入
  - `kb_manager.py:53-62` calculate_file_hash() — SHA256 ✅ 已有
  - `kb_manager.py:108-110` 三向差异(新增/修改/删除) — ⚠️ BiliSum仅二元
  - `evaluate.py:75-176` RAGAS评测 — ❌ 缺失

## bilibili-auto-transcript-src
路径: `C:\Users\shiniyaya\Desktop\参考\bilibili-auto-transcript-src\`
文件: scripts/transcript_db.py, batch_transcribe.py
最优函数:
  - `transcript_db.py:59-79` insert() UPSERT — ❌ BiliSum JSON覆盖
  - `transcript_db.py:128-203` render_txt() — ✅ 有docx_exporter
  - `batch_transcribe.py:150-188` transcribe_video() 重试循环 — ✅ 有fetch_subtitle_with_retry

## knowledge-rag-src
路径: `C:\Users\shiniyaya\Desktop\参考\knowledge-rag-src\`
文件: index_knowledge.py, knowledge_api.py, query_knowledge.py
最优函数:
  - `index_knowledge.py:314-436` build_index() 增量 — ✅ 有IncrementalIndexer
  - `query_knowledge.py:102-146` search() 混合评分 — ✅ 有UnifiedSearcher
  - `knowledge_api.py:99-125` /api/search 自动build — ⚠️ BiliSum手动触发

## Bili23-Downloader
路径: `C:\Users\shiniyaya\Desktop\Bili23-Downloader\`
文件: Downloader.py, ParserBase, Config
最优函数:
  - `Downloader.py:33-41` TokenBucket — ⏳ 待导入
  - `Downloader.py:258-659` 分块并行下载 — P2
  - `config.py:444-462` check_need_patch() 版本迁移 — ❌ BiliSum无
  - `SubtitlesParser.py:13-133` 多格式导出(SRT/LRC/TXT/ASS) — ⚠️ BiliSum仅SRT/VTT

## karpathy-llm-wiki-vault
路径: `C:\Users\shiniyaya\Desktop\参考\开源参考\karpathy-llm-wiki-vault\`
文件: wiki/ + CLAUDE.md
最优模式:
  - wiki/index.md + wiki/log.md — 结构化知识索引+操作日志 ❌
  - concepts/entities/sources/syntheses 四分类 ❌
  - 强制双向链接 [[page]] ❌
  - 知识冲突追踪 `## 知识冲突` ❌

## awesome-selfhosted
路径: `C:\Users\shiniyaya\Desktop\参考\开源参考\awesome-selfhosted\`
最优参考:
  - Khoj — AI第二大脑/RAG/agent (AGPL-3.0)
  - AnythingLLM — 内置RAG/MCP兼容 (MIT)
  - MeiliSearch — 即时模糊搜索/Rust (MIT)
  - Tube Archivist — YouTube整理/搜索 (GPL-3.0)

## 3-bili-note
路径: `C:\Users\shiniyaya\Desktop\参考\开源参考\3-bili-note\`
最优函数:
  - `archive_bili_materials.py:716-779` assess_visual_dependency() — ✅ BiliSum 4维
  - `archive_bili_materials.py:423-465` flatten_comments() — ✅ 已有CommentReply

## rag数据参考
路径: `C:\Users\shiniyaya\Desktop\rag数据参考\`
状态: 为bilibili-rag旧版快照，无独特新模式

## AI_Animation-src
路径: `C:\Users\shiniyaya\Desktop\参考\AI_Animation-src\`
状态: 前端动画模板，BiliSum React SPA架构不同

## 关联记忆
- [[bilisum-reference-import-registry]]
- [[bilisum-all-reference-sources]]
- [[bilisum-v8.4-session-state]]
