---
name: bilisum-reference-import-registry
description: BiliSum已从参考源导入的函数清单 — 来源/目标/风险/效果 全追踪
metadata:
  type: reference
  created: 2026-07-14
  updated: 2026-07-14-round7
---

# BiliSum 参考源导入注册表

## 已导入（Round 7）

### 1. keyword_score_docs 计数加权
- 来源: bilibili-rag `retrieval.py:60-91`
- 目标: `backend/rag_service.py:387-415`
- 改进: 单次命中boolean → count(*)加权 (title命中3次 = 3×8.0×w)
- 风险: 零（纯函数，无外部依赖）
- 验证: AST通过

### 2. 查询路由（2路LLM）
- 来源: LegalGraphQA `qa_chain_refactored.py:97-137`
- 目标: `backend/routers/kb.py:235-262`
- 改进: /api/rag/ask先LLM判断"免检索"vs"标准RAG"，路由失败安全回退RAG
- 风险: 零（LLM路由失败→默认RAG，最坏=额外API调用）
- 验证: AST通过

### 3. ChatLogger对话日志
- 来源: LegalGraphQA `chat_logger.py`
- 目标: `backend/chat_logger.py`（新建）
- 改进: JSON持久化QA对话+搜索+统计（total/bvids/avg_time）
- 风险: 零（纯Python+JSON，无外部依赖）
- 验证: AST通过

### QA Prompt增强
- 来源: LegalGraphQA `qa_chain_refactored.py:34-51`
- 目标: `backend/routers/kb.py:262-276`
- 改进: `---`分隔符省token + 分步推理要求 + "信息不足明确指出不要猜测"
- 验证: AST通过

### Cookie提取修复
- 来源: 自研（发现httpx `headers.get()`只返回第一个Set-Cookie）
- 目标: `backend/routers/auth.py:68-84`
- 改进: `r.headers.get_list("Set-Cookie")` 获取全部Cookie头
- 验证: AST通过

### ChromaDB索引修复
- 来源: 自研（收藏夹导入缺向量索引）
- 目标: `backend/routers/favorites.py:61-67, 248-252`
- 改进: 导入后调 `get_rag_service().add_video()` + 修正import路径 + 去await
- 验证: AST通过

### 动态总结6维增强
- 来源: 自研（补充visual_richness + new_concept_count）
- 目标: `backend/quality.py:189-195, 235-242`
- 改进: coefficient ceiling 72000, floor 1500, new_concept*0.05, base*1.6
- 验证: AST通过

## 待导入（零风险）

### build_snippet 关键词摘要
- 来源: bilibili-rag `retrieval.py:94-116`
- 目标: `backend/rag_service.py`
- 功能: 关键词中心700字摘要窗口

### organize_video_content 多分块AI笔记
- 来源: bilibili-rag `markdown_export.py:55-113`
- 目标: `backend/summarizer.py`
- 功能: 长内容LLM分块→多块分别合成→拼接

### TokenBucket 速率限制
- 来源: Bili23-Downloader `Downloader.py:33-41`
- 目标: `backend/rate_limiter.py`（新建）
- 功能: 线程安全速率限制器

### RAGAS自动评测
- 来源: LegalGraphQA `evaluate.py:75-136`
- 目标: `scripts/eval_rag.py`（新建）
- 功能: 5指标自动评测+基准答案生成+CSV导出
- 依赖: pip install ragas datasets pandas

## 关联记忆
- [[bilisum-v8.4-session-state]]
- [[bilisum-all-reference-sources]]
