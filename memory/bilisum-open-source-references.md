---
name: bilisum-open-source-references
description: 6 open-source reference projects analyzed — 15 directly copyable code blocks with source:line → target:line mappings
metadata:
  type: reference
---

# BiliSum 6 个开源参考项目分析

## 项目列表
1. bilibili-rag — 完整RAG系统 + ChromaDB + MMR + 3级内容获取
2. bilibili-subtitle — SRT/VTT/MD解析渲染 + BBDown CLI + 语言标准化
3. bili-note — WBI + 多ASR + 质量评分 + 笔记预算 + 证据溯源
4. subbatch-local — 中文智能分句 + 前端Whisper + WebGPU/WASM + 繁简转换
5. rag开源文件 — 项目1的本地修改版(MD5 Hash嵌入兜底)
6. BOC (Bilibili-Obsidian-Clipper) — Obsidian Local REST API + vault推送

## 可直接复用的15个代码块
1. bilibili-rag/retrieval.py:22-57 → rag_service.py (extract_keywords 中文n-gram版)
2. bilibili-rag/retrieval.py:60-91 → rag_service.py (keyword_score_docs 字段加权)
3. bilibili-rag/retrieval.py:135-196 → rag_service.py (merge_rrf + channel_weights)
4. bilibili-rag/content_fetcher.py:451-540 → bilibili_client.py (_try_subtitle 4级降级+pick_subtitle)
5. bilibili-rag/rag.py:149-181 → rag_service.py (_build_metadata_document)
6. bilibili-subtitle/languages.py:4-28 → text_utils.py (normalize_lang 全别名映射)
7. bilibili-subtitle/converters/srt_converter.py:8-38 → bilibili_client.py (srt_to_segments)
8. bili-note/score_bili_note.py:16-23 → quality.py (visible_text_chars 精确字数)
9. bili-note/score_bili_note.py:26-31 → quality.py (count_evidence_refs 证据溯源)
10. bili-note/extract_bilibili.py:684-681 → wbi.py (sign_params 健壮WBI)
11. bilibili-rag/markdown_export.py:23-38 → summarizer.py (split_content 智能截断)
12. bilibili-rag/asr.py:58-90 → asr_service.py (_transcode_audio_to_pcm)
13. bilibili-rag/cancellation.py:1-15 → cancellation.py (CancelCheck + 回滚)
14. bili-note/update_note_budget_section.py:67-124 → summarizer.py (build_section 质量评估段注入)
15. subbatch-local/script.js → text_utils.py (保护列表+繁简转换+去重)

## 7个隐藏协同
1. bilibili-rag `_is_better_source()` + BiliSum多通道 → 防止缓存降级
2. bili-note `resolve_asr_backend()` + BiliSum字幕 → 本地ASR第4通道
3. subbatch-local 繁简转换+乱码检测 → 输入质量飞跃
4. bilibili-subtitle BBDown重试+致命检测 → 字幕可靠性飞跃
5. bilibili-subtitle preflight模式 → 启动健康检查
6. bilibili-rag cancellation token → 长总结可中止
7. bilibili-subtitle errors.py分类 → 结构化错误

**Why:** These projects have been thoroughly reverse-engineered to find every reusable pattern for BiliSum.

**How to apply:** When implementing new features, first check if one of these code blocks solves the problem. Prefer adapting existing tested code over writing from scratch.
