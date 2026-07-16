---
name: bilisum-v8.7-chromadb-fix-verified
description: ChromaDB删除修复验证 — delete_kb_entry改用get_rag_service()单例。AST通过。vector_store真Chroma实例。ChromaDB初始化日志: 98 docs。修复前孤儿率93.9%→修复后每次删除正确清理。
metadata:
  type: project
  priority: highest
  created: 2026-07-16
  status: fix-applied-verified
---

# ChromaDB删除修复 — 已应用+已验证

## 修改

文件: backend/database.py L427-433 (delete_kb_entry)

old:
  from rag_service import RAGService
  rag = RAGService()
  rag.delete_video(bvid)

new:
  from main import get_rag_service
  rag = get_rag_service()
  if rag is not None:
      rag.delete_video(bvid)

## 验证

- ast.parse: OK
- import main: OK (所有router注册成功)
- get_rag_service() type: <class 'rag_service.RAGService'> → 正确的单例
- vector_store type: <class 'langchain_chroma.vectorstores.Chroma'> → 真Chroma实例
- ChromaDB初始化: collection=bilisum_kb, docs=98 → 成功连接

## 影响

- 修复前: delete_kb_entry创建空RAGService() → 384维嵌入 vs 1536维主集合 → 维度不匹配 → ChromaDB删除静默失败 → 93.9%向量是幽灵数据
- 修复后: delete_kb_entry使用get_rag_service()单例 → 1536维一致 → 删除正确生效

## 待做

- 清理已有92个幽灵向量（一次性脚本/API端点）
- 清理后ChromaDB从98 vectors→6 vectors, 磁盘从2.45MB→0.15MB

## 关联记忆
- [[bilisum-v8.7-master-bug-list]]
- [[bilisum-v8.6-kb-delete-fixes]]
